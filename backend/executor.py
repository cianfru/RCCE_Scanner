"""
executor.py
~~~~~~~~~~~
Execution engine that converts scanner signals into trading orders.
Supports paper trading (default) and live trading (Hyperliquid) modes.

Signal flow:
    Scanner → synthesize_signal() → Executor → TradingEngine → orders

The executor is a singleton — access via get_executor().
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

import asyncio

from trading_engine import TradingEngine, PaperEngine, HyperliquidEngine, EngineError
from price_sanity import PRICE_SANITY_MAX_RATIO, price_rejection, reference_prices

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Prefer Railway persistent volume (/data), fall back to local directory
_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).parent / "data"
_STATE_FILE = _PERSIST_DIR / "executor_state.json"

# Reuse sizing logic from backtest position_manager
_ENTRY_SIZING: Dict[str, Dict[str, float]] = {
    "STRONG_LONG":  {"STRONG": 1.00, "MODERATE": 0.75, "WEAK": 0.50, "CONFLICTING": 0.50, "UNKNOWN": 0.50},
    "LIGHT_LONG":   {"STRONG": 0.50, "MODERATE": 0.50, "WEAK": 0.25, "CONFLICTING": 0.25, "UNKNOWN": 0.25},
    # ACCUMULATE is not an entry: adding it as the executor did cost 18-19 points of compounded
    # return on both replay coin sets (docs/reviews/entry-quality-study.md); the backtest never took it.
    "REVIVAL_SEED": {"STRONG": 0.10, "MODERATE": 0.10, "WEAK": 0.00, "CONFLICTING": 0.00, "UNKNOWN": 0.05},
    # LIGHT_SHORT is not an entry: shorting on it lost money on both replay coin sets
    # (docs/reviews/timing-and-exits-study.md, X1). Open shorts, if any, keep their exits.
}

_ENTRY_SIGNALS = set(_ENTRY_SIZING.keys())
_EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "NO_LONG", "RISK_OFF"}

# ─── Stop-loss rails (decided with user 2026-04-21) ──────────────────────────
# Hard stop: catastrophic floor only. Fires when unrealized P&L ≤ -8%.
# Intent: prevent another TAO/ZRO scenario where signal-flip exit didn't
# fire in time. Should almost never trigger on a trade that works normally.
_HARD_STOP_PCT = -8.0
# Break-even stop arming threshold: once a position peaks at +5%, mark it
# "armed" so a retrace back to entry closes it. Only triggers on true
# reversals (not normal pullbacks) — strictly less restrictive than a
# trailing stop. Backtest showed trailing stops kill bull-run performance,
# so we explicitly avoid them.
_BE_ARM_PCT = 5.0

# Leverage per signal — used in live (Hyperliquid) mode
_LEVERAGE_MAP: Dict[str, int] = {
    "STRONG_LONG":  5,
    "LIGHT_LONG":   3,
    "ACCUMULATE":   2,
    "REVIVAL_SEED": 1,
    "LIGHT_SHORT":  3,
}

# Minimum order size in USD
_MIN_ORDER_USD = 5.0

# Default whitelist: only trade symbols validated by backtesting
DEFAULT_WHITELIST = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
]

# Price rejections kept for the status endpoint.
_MAX_PRICE_REJECTIONS = 20

# One-time paper-ledger corrections, approved by the owner. Each entry names a
# closed trade by its recorded fields and the market price it is corrected to.
# The trade stays closed at the same time and size; only the fill is replaced.
_LEDGER_CORRECTIONS = (
    {
        "symbol": "PURR/USDT", "entry_time": 1790425994.2996264, "exit_time": 1790489004.928304,
        "entry_price": 0.12409, "exit_price": 13.015, "volume": 314.79, "cost_usd": 39.0625,
        "exit_signal": "TRIM",
        # Close of Hyperliquid's PURR 1h candle for 2026-09-27 06:00-07:00 UTC, the
        # hour of the exit (o 0.13096, h 0.1324, l 0.13083, c 0.13194).
        "corrected_exit_price": 0.13194,
        "reason": "exit filled ~100x above market (price feed error)",
    },
)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class ExecutorPosition:
    """An open position tracked by the executor."""
    symbol: str                     # scanner format: BTC/USDT
    exchange_pair: str              # exchange format: BTC (Hyperliquid) or BTCUSD (legacy)
    side: str = "LONG"              # LONG or SHORT
    entry_price: float = 0.0
    entry_time: float = 0.0
    entry_signal: str = ""
    volume: float = 0.0             # base currency amount
    cost_usd: float = 0.0           # USD cost at entry
    size_pct: float = 0.0           # % of allocation used
    confluence_at_entry: str = "UNKNOWN"
    order_id: str = ""              # order ID from engine
    entry_reason: str = ""          # signal_reason at entry time
    entry_warnings: List[str] = field(default_factory=list)
    # Stop-loss tracking (populated during live monitoring)
    peak_unrealized_pct: float = 0.0   # highest +% reached since entry
    be_armed: bool = False             # True once peak >= BE_ARM_PCT (+5%)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Backward compat: also emit kraken_pair for any old state readers
        d["kraken_pair"] = d["exchange_pair"]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ExecutorPosition:
        # Accept both old "kraken_pair" and new "exchange_pair"
        if "exchange_pair" not in d and "kraken_pair" in d:
            d["exchange_pair"] = d.pop("kraken_pair")
        elif "kraken_pair" in d and "exchange_pair" in d:
            d.pop("kraken_pair")
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ExecutorTrade:
    """A completed trade."""
    symbol: str
    exchange_pair: str
    side: str = "LONG"
    entry_price: float = 0.0
    entry_time: float = 0.0
    entry_signal: str = ""
    exit_price: float = 0.0
    exit_time: float = 0.0
    exit_signal: str = ""
    volume: float = 0.0
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0
    cost_usd: Optional[float] = None
    order_ids: List[str] = field(default_factory=list)
    entry_reason: str = ""
    entry_warnings: List[str] = field(default_factory=list)
    # Present only on a trade whose recorded fill was corrected; keeps the originals.
    correction: Optional[dict] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kraken_pair"] = d["exchange_pair"]
        if d.get("correction") is None:
            d.pop("correction", None)
        return d


# ---------------------------------------------------------------------------
# Executor errors
# ---------------------------------------------------------------------------

class ExecutorError(Exception):
    """Raised when an executor operation fails."""
    def __init__(self, category: str, message: str):
        self.category = category
        self.message = message
        super().__init__(f"[{category}] {message}")


# ---------------------------------------------------------------------------
# Main Executor class
# ---------------------------------------------------------------------------

class Executor:
    """Converts scanner signals into trading orders.

    Modes:
        paper  — uses PaperEngine for simulated trading
        live   — uses HyperliquidEngine for real orders (future)
        disabled — no execution
    """

    def __init__(
        self,
        mode: str = "paper",
        initial_balance: float = 10000.0,
    ):
        self.mode = mode
        self.initial_balance = initial_balance
        self.enabled = False
        self.initialized = False

        # Trading engine
        self.engine: Optional[TradingEngine] = None

        # State
        self.positions: Dict[str, ExecutorPosition] = {}
        self.trade_log: List[ExecutorTrade] = []
        self.pair_map: Dict[str, str] = {}  # {scanner_sym: exchange_pair}
        self.last_scan_signals: Dict[str, str] = {}
        self.last_error: Optional[str] = None
        self.last_execution_time: Optional[float] = None
        self.total_executions: int = 0

        # Price sanity: last accepted price per open position, recent rejections,
        # and the reference lookup (symbol -> {name: price}); tests replace it.
        self.last_marks: Dict[str, float] = {}
        self.last_price_rejections: List[dict] = []
        self.reference_provider = reference_prices

        # Whitelist: only trade these symbols (default: backtested set)
        self.whitelist: List[str] = DEFAULT_WHITELIST.copy()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self, scanner_symbols: List[str]) -> dict:
        """Initialize the executor: create engine, build pair map."""
        logger.info("Executor state file: %s (volume: %s)",
                     _STATE_FILE, "yes" if "/data" in str(_STATE_FILE) else "no")

        if self.mode == "paper":
            # Paper mode: pure simulation, no network calls needed
            self.engine = PaperEngine(self.initial_balance)

            # Map all scanner symbols directly (paper trades any symbol)
            self.pair_map = {
                sym: sym.split("/")[0].upper()
                for sym in scanner_symbols
            }
            logger.info(
                "Paper engine initialized: $%.0f balance, %d symbols mapped",
                self.initial_balance, len(self.pair_map),
            )

        elif self.mode == "live":
            # Live mode: Hyperliquid
            self.engine = HyperliquidEngine()

            # Discover which scanner symbols are tradeable on Hyperliquid
            try:
                from hyperliquid_data import fetch_hyperliquid_metrics
                metrics = await fetch_hyperliquid_metrics()
                hl_coins = {m.coin for m in metrics.values()}

                self.pair_map = {}
                for sym in scanner_symbols:
                    coin = sym.split("/")[0].upper()
                    if coin in hl_coins:
                        self.pair_map[sym] = coin

                logger.info(
                    "Hyperliquid engine: %d/%d scanner symbols available",
                    len(self.pair_map), len(scanner_symbols),
                )
            except Exception as e:
                logger.error("Failed to discover Hyperliquid pairs: %s", e)
                self.pair_map = {}

        else:
            raise ExecutorError("config", f"Unknown mode: {self.mode}")

        # Load persisted state if exists
        self._load_state()
        # Same synchronous step as the load: nothing else can touch the ledger in between.
        self._apply_ledger_corrections()

        self.initialized = True
        return {
            "mode": self.mode,
            "pairs_available": len(self.pair_map),
            "pairs": list(self.pair_map.keys()),
            "initial_balance": self.initial_balance,
        }

    # ------------------------------------------------------------------
    # Signal processing (called after each scan)
    # ------------------------------------------------------------------

    async def process_scan_results(self, results: List[dict]) -> dict:
        """Process scan results and execute trades.

        Called at the end of each scan cycle. Iterates through all results,
        checks for actionable signals, and executes orders.

        Returns summary of actions taken.
        """
        if not self.initialized or not self.enabled:
            return {"status": "disabled"}

        actions_taken = []
        self.last_scan_signals = {}

        for r in results:
            symbol = r.get("symbol", "")
            signal = r.get("signal", "WAIT")
            price = r.get("price", 0.0)
            confluence = r.get("confluence", {})
            confluence_label = confluence.get("label", "UNKNOWN") if isinstance(confluence, dict) else "UNKNOWN"

            self.last_scan_signals[symbol] = signal

            # Skip symbols not in pair map
            if symbol not in self.pair_map:
                continue

            # Skip non-whitelisted symbols (but always allow exits for open positions)
            if symbol not in self.whitelist and symbol not in self.positions:
                continue

            # Price sanity: no entry, exit or stop on a quote the references disown.
            if symbol in self.positions or signal in _ENTRY_SIGNALS or r.get("price_rejected"):
                rejection = self._price_rejection(symbol, price, r)
                if rejection:
                    self._record_price_rejection(symbol, signal, price, rejection)
                    continue
                if symbol in self.positions:
                    self.last_marks[symbol] = float(price)

            signal_reason = r.get("signal_reason", "")
            signal_warnings = r.get("signal_warnings", [])

            try:
                action = await self._process_signal(
                    symbol, signal, price, confluence_label,
                    signal_reason, signal_warnings,
                )
                if action:
                    actions_taken.append(action)
            except (ExecutorError, EngineError) as e:
                logger.error("Executor error for %s: %s", symbol, e)
                self.last_error = str(e)
            except Exception as e:
                logger.exception("Unexpected executor error for %s", symbol)
                self.last_error = str(e)

        self.last_execution_time = time.time()
        self.total_executions += 1

        # Save state after processing
        self._save_state()

        if actions_taken:
            logger.info(
                "Executor: %d actions taken: %s",
                len(actions_taken),
                ", ".join(actions_taken),
            )

        return {
            "status": "ok",
            "actions": actions_taken,
            "open_positions": len(self.positions),
        }

    async def _process_signal(
        self,
        symbol: str,
        signal: str,
        price: float,
        confluence_label: str,
        signal_reason: str = "",
        signal_warnings: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Process a single symbol's signal. Returns action description or None."""

        has_position = symbol in self.positions

        # ------ STOP-LOSS CHECKS (run BEFORE signal logic) ------
        # Applies only to LONG positions with a valid current price.
        if has_position and price > 0:
            pos = self.positions[symbol]
            if pos.side == "LONG" and pos.entry_price > 0:
                unrealized_pct = (price - pos.entry_price) / pos.entry_price * 100

                # Track peak for BE-stop arming
                if unrealized_pct > pos.peak_unrealized_pct:
                    pos.peak_unrealized_pct = unrealized_pct
                if not pos.be_armed and pos.peak_unrealized_pct >= _BE_ARM_PCT:
                    pos.be_armed = True
                    logger.info(
                        "BE stop armed for %s: peak %.1f%% >= %.1f%%",
                        symbol, pos.peak_unrealized_pct, _BE_ARM_PCT,
                    )

                # Hard stop: catastrophic floor
                if unrealized_pct <= _HARD_STOP_PCT:
                    logger.warning(
                        "HARD STOP triggered for %s: unrealized %.1f%% <= %.1f%%",
                        symbol, unrealized_pct, _HARD_STOP_PCT,
                    )
                    return await self._execute_exit(symbol, "STOP_LOSS", price)

                # BE stop: only after armed (peaked >= +5%)
                if pos.be_armed and unrealized_pct <= 0.0:
                    logger.info(
                        "BE STOP triggered for %s: retraced to entry after peak %.1f%%",
                        symbol, pos.peak_unrealized_pct,
                    )
                    return await self._execute_exit(symbol, "BE_STOP", price)

        # ------ EXIT SIGNALS ------
        # RISK_OFF / TRIM / TRIM_HARD / NO_LONG — close THIS symbol's position
        if signal in _EXIT_SIGNALS and has_position:
            action = await self._execute_exit(symbol, signal, price)
            return action

        # ------ ENTRY SIGNALS ------
        if signal in _ENTRY_SIGNALS and not has_position:
            # Calculate position size
            size_pct = _ENTRY_SIZING[signal].get(confluence_label, 0.0)
            if size_pct <= 0:
                logger.debug(
                    "Skipping %s for %s — confluence=%s gives 0%% size",
                    signal, symbol, confluence_label,
                )
                return None

            action = await self._execute_entry(
                symbol, signal, price, size_pct, confluence_label,
                signal_reason, signal_warnings or [],
            )
            return action

        return None

    # ------------------------------------------------------------------
    # Price sanity
    # ------------------------------------------------------------------

    def _price_rejection(self, symbol: str, price, row: Optional[dict] = None) -> Optional[str]:
        """Why this cycle's price for *symbol* must not be traded, or None."""
        flagged = (row or {}).get("price_rejected")
        if flagged:
            reason = flagged.get("reason") if isinstance(flagged, dict) else flagged
            return f"scanner rejected the quote: {reason}"
        try:
            references = self.reference_provider(symbol) or {}
        except Exception:
            logger.debug("Price references unavailable for %s", symbol, exc_info=True)
            references = {}
        pos = self.positions.get(symbol)
        last_mark = self.last_marks.get(symbol) or (pos.entry_price if pos else None)
        return price_rejection(price, references, last_mark=last_mark,
                               max_ratio=PRICE_SANITY_MAX_RATIO)

    def _record_price_rejection(self, symbol: str, signal: str, price, reason: str) -> None:
        logger.warning("Executor skipped %s this cycle (signal %s): %s", symbol, signal, reason)
        self.last_price_rejections.append({
            "symbol": symbol, "signal": signal, "price": price,
            "reason": reason, "at": time.time(),
        })
        del self.last_price_rejections[:-_MAX_PRICE_REJECTIONS]

    # ------------------------------------------------------------------
    # Ledger corrections (paper only, applied once)
    # ------------------------------------------------------------------

    def _apply_ledger_corrections(self) -> int:
        """Apply each entry of _LEDGER_CORRECTIONS once to the paper ledger.

        The trade keeps its time, size and exit reason; its fill becomes the
        corrected market price, P&L is recomputed as _execute_exit computes it,
        and paper cash gives back the P&L difference. The original values are
        kept under trade.correction, which also marks the trade as done.
        Positions are not touched. Returns the number of trades corrected.
        """
        if self.mode != "paper" or not isinstance(self.engine, PaperEngine):
            return 0
        applied = 0
        for spec in _LEDGER_CORRECTIONS:
            for trade in self.trade_log:
                if trade.correction is not None or not _trade_matches(trade, spec):
                    continue
                fill = spec["corrected_exit_price"]
                if trade.side == "SHORT":
                    pnl_pct = (trade.entry_price - fill) / trade.entry_price * 100
                else:
                    pnl_pct = (fill - trade.entry_price) / trade.entry_price * 100
                cost = trade.cost_usd if trade.cost_usd is not None else trade.entry_price * trade.volume
                pnl_usd = cost * (pnl_pct / 100)
                cash_change = pnl_usd - trade.pnl_usd
                trade.correction = {
                    "original_exit_price": trade.exit_price,
                    "original_pnl_usd": trade.pnl_usd,
                    "original_pnl_pct": trade.pnl_pct,
                    "corrected_at": time.time(),
                    "reason": spec["reason"],
                    "cash_change_usd": cash_change,
                }
                cash_before = self.engine.cash
                trade.exit_price, trade.pnl_pct, trade.pnl_usd = fill, pnl_pct, pnl_usd
                self.engine.cash += cash_change
                applied += 1
                logger.warning(
                    "LEDGER CORRECTION %s %s exit at %s: exit %s -> %s, P&L $%.2f -> $%.2f, "
                    "paper cash $%.2f -> $%.2f (%s)",
                    trade.symbol, trade.exit_signal, trade.exit_time,
                    trade.correction["original_exit_price"], fill,
                    trade.correction["original_pnl_usd"], pnl_usd,
                    cash_before, self.engine.cash, spec["reason"],
                )
        if applied:
            self._save_state()
        return applied

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    async def _execute_entry(
        self,
        symbol: str,
        signal: str,
        price: float,
        size_pct: float,
        confluence_label: str,
        signal_reason: str = "",
        signal_warnings: Optional[List[str]] = None,
    ) -> str:
        """Place an entry order (buy for LONG, sell for SHORT)."""
        exchange_pair = self.pair_map[symbol]
        side = "SHORT" if signal == "LIGHT_SHORT" else "LONG"

        # Calculate volume
        allocation = self.initial_balance / max(len(self.whitelist), 1)
        usd_amount = allocation * size_pct
        if usd_amount < _MIN_ORDER_USD:
            logger.debug("Skipping %s — amount $%.2f below minimum", symbol, usd_amount)
            return None

        volume = usd_amount / price if price > 0 else 0
        if volume <= 0:
            return None

        # Format volume to appropriate precision
        volume = _format_volume(volume, price)

        # Determine leverage (only meaningful for live mode)
        leverage = _LEVERAGE_MAP.get(signal, 3) if self.mode == "live" else None

        # Place order via trading engine
        # Hyperliquid SDK is synchronous — use asyncio.to_thread for live mode
        if side == "SHORT":
            if self.mode == "live":
                result = await asyncio.to_thread(self.engine.sell, symbol, volume, price, leverage)
            else:
                result = self.engine.sell(symbol, volume, price)
        else:
            if self.mode == "live":
                result = await asyncio.to_thread(self.engine.buy, symbol, volume, price, leverage)
            else:
                result = self.engine.buy(symbol, volume, price)

        # Record position
        order_id = result.get("order_id", "")
        fill_price = result.get("price", price)

        self.positions[symbol] = ExecutorPosition(
            symbol=symbol,
            exchange_pair=exchange_pair,
            side=side,
            entry_price=fill_price,
            entry_time=time.time(),
            entry_signal=signal,
            volume=volume,
            cost_usd=usd_amount,
            size_pct=size_pct,
            confluence_at_entry=confluence_label,
            order_id=order_id,
            entry_reason=signal_reason,
            entry_warnings=signal_warnings or [],
        )

        self.last_marks.pop(symbol, None)  # the entry price is the first mark
        self._save_state()  # persist immediately after entry

        action = f"{side} {symbol} @ ${fill_price:,.2f} ({signal}, {size_pct*100:.0f}%, vol={volume})"
        logger.info("ENTRY: %s", action)
        return action

    async def _execute_exit(
        self,
        symbol: str,
        exit_signal: str,
        price: float,
    ) -> Optional[str]:
        """Close an existing position."""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Place closing order via trading engine (reverse direction)
        # For live mode, use market_close for full position closure
        if self.mode == "live" and hasattr(self.engine, "close_position"):
            try:
                result = await asyncio.to_thread(self.engine.close_position, symbol)
                # market_close doesn't return fill price — use provided price
                result["price"] = price
                result["order_id"] = result.get("order_id", f"hl-close-{symbol}")
            except Exception:
                # Fallback to regular sell/buy if market_close fails
                if pos.side == "SHORT":
                    result = await asyncio.to_thread(self.engine.buy, symbol, pos.volume, price)
                else:
                    result = await asyncio.to_thread(self.engine.sell, symbol, pos.volume, price)
        elif pos.side == "SHORT":
            if self.mode == "live":
                result = await asyncio.to_thread(self.engine.buy, symbol, pos.volume, price)
            else:
                result = self.engine.buy(symbol, pos.volume, price)
        else:
            if self.mode == "live":
                result = await asyncio.to_thread(self.engine.sell, symbol, pos.volume, price)
            else:
                result = self.engine.sell(symbol, pos.volume, price)

        fill_price = result.get("price", price)

        # Calculate PnL
        if pos.side == "SHORT":
            pnl_pct = (pos.entry_price - fill_price) / pos.entry_price * 100
        else:
            pnl_pct = (fill_price - pos.entry_price) / pos.entry_price * 100

        pnl_usd = pos.cost_usd * (pnl_pct / 100)

        # Record trade
        trade = ExecutorTrade(
            symbol=symbol,
            exchange_pair=pos.exchange_pair,
            side=pos.side,
            entry_price=pos.entry_price,
            entry_time=pos.entry_time,
            entry_signal=pos.entry_signal,
            exit_price=fill_price,
            exit_time=time.time(),
            exit_signal=exit_signal,
            volume=pos.volume,
            pnl_pct=pnl_pct,
            pnl_usd=pnl_usd,
            cost_usd=pos.cost_usd,
            order_ids=[pos.order_id, result.get("order_id", "")],
            entry_reason=pos.entry_reason,
            entry_warnings=pos.entry_warnings,
        )
        self.trade_log.append(trade)

        # Remove position
        del self.positions[symbol]
        self.last_marks.pop(symbol, None)
        self._save_state()  # persist immediately after exit

        pnl_sign = "+" if pnl_pct >= 0 else ""
        action = (
            f"CLOSE {pos.side} {symbol} @ ${fill_price:,.2f} "
            f"({exit_signal}, {pnl_sign}{pnl_pct:.1f}%, ${pnl_sign}{pnl_usd:.2f})"
        )
        logger.info("EXIT: %s", action)
        return action

    # ------------------------------------------------------------------
    # Status & queries
    # ------------------------------------------------------------------

    async def get_status(self) -> dict:
        """Return current executor status."""
        portfolio = {}
        if self.initialized and self.engine:
            try:
                if self.mode == "live":
                    portfolio = await asyncio.to_thread(self.engine.get_portfolio)
                else:
                    portfolio = self.engine.get_portfolio()
            except Exception as e:
                logger.warning("Failed to get portfolio status: %s", e)

        # Capital-weighted P&L: sum actual dollar P&L across closed trades,
        # divided by total cost. Previous logic summed raw percentages which
        # is mathematically meaningless across differently-sized positions.
        total_pnl_usd = sum(getattr(t, "pnl_usd", 0.0) or 0.0 for t in self.trade_log)
        total_cost = 0.0
        for t in self.trade_log:
            # Prefer explicit cost if present, else reconstruct from entry_price * volume
            cost = getattr(t, "cost_usd", None)
            if cost is None:
                cost = (t.entry_price or 0.0) * (t.volume or 0.0)
            total_cost += cost or 0.0
        total_pnl_pct = (total_pnl_usd / total_cost * 100) if total_cost > 0 else 0.0
        wins = sum(1 for t in self.trade_log if t.pnl_pct > 0)

        result = {
            "mode": self.mode,
            "enabled": self.enabled,
            "initialized": self.initialized,
            "positions": {
                sym: pos.to_dict() for sym, pos in self.positions.items()
            },
            "open_position_count": len(self.positions),
            "total_trades": len(self.trade_log),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "total_pnl_usd": round(total_pnl_usd, 2),
            "total_cost_usd": round(total_cost, 2),
            "win_rate": round(wins / len(self.trade_log) * 100, 1) if self.trade_log else 0,
            "last_scan_signals": self.last_scan_signals,
            "last_error": self.last_error,
            "last_price_rejections": list(self.last_price_rejections),
            "last_execution_time": self.last_execution_time,
            "total_executions": self.total_executions,
            "available_pairs": len(self.pair_map),
            "whitelist": sorted(self.whitelist),
            "whitelist_count": len(self.whitelist),
            "paper_balance": self.initial_balance,
            "portfolio": portfolio,
            "state_file": str(_STATE_FILE),
            "state_persistent": _STATE_FILE.exists(),
        }

        # Include live account info when in HL mode
        if self.mode == "live" and portfolio:
            result["account_value"] = portfolio.get("account_value", 0)
            result["margin_used"] = portfolio.get("margin_used", 0)
            result["available_margin"] = portfolio.get("available_margin", 0)
            result["hl_positions"] = portfolio.get("positions", [])

        return result

    def get_trades(self) -> List[dict]:
        """Return trade history."""
        from executor_ledger_audit import closure_issue
        rows = [t.to_dict() for t in self.trade_log]
        return [{**row, "quality_issue": closure_issue(row)} for row in rows]

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        """Persist executor state to disk (Railway volume or local)."""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            logger.debug("Saving executor state to %s", _STATE_FILE)
            state = {
                "mode": self.mode,
                "enabled": self.enabled,
                "initial_balance": self.initial_balance,
                "whitelist": self.whitelist,
                "positions": {
                    sym: pos.to_dict()
                    for sym, pos in self.positions.items()
                },
                "trade_log": [t.to_dict() for t in self.trade_log],
                "pair_map": self.pair_map,
                "last_scan_signals": self.last_scan_signals,
                "total_executions": self.total_executions,
                "engine_state": self.engine.get_state() if self.engine else {},
                "saved_at": time.time(),
            }
            _STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error("Failed to save executor state: %s", e)

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        if not _STATE_FILE.exists():
            return

        try:
            state = json.loads(_STATE_FILE.read_text())

            # Only restore if same mode
            if state.get("mode") != self.mode:
                logger.info("Mode changed (%s → %s) — starting fresh",
                           state.get("mode"), self.mode)
                return

            # Restore enabled flag
            if state.get("enabled"):
                self.enabled = True

            # Restore positions
            for sym, pos_dict in state.get("positions", {}).items():
                self.positions[sym] = ExecutorPosition.from_dict(pos_dict)

            # Restore trade log
            for t_dict in state.get("trade_log", []):
                # Accept both old "kraken_pair" and new "exchange_pair"
                if "exchange_pair" not in t_dict and "kraken_pair" in t_dict:
                    t_dict["exchange_pair"] = t_dict.pop("kraken_pair")
                elif "kraken_pair" in t_dict and "exchange_pair" in t_dict:
                    t_dict.pop("kraken_pair")
                self.trade_log.append(ExecutorTrade(**{
                    k: v for k, v in t_dict.items()
                    if k in ExecutorTrade.__dataclass_fields__
                }))

            # Restore pair map only if not already populated by discovery
            if not self.pair_map:
                self.pair_map = state.get("pair_map", {})

            # Restore whitelist (or keep default if not in saved state)
            saved_whitelist = state.get("whitelist")
            if saved_whitelist is not None:
                self.whitelist = saved_whitelist

            self.total_executions = state.get("total_executions", 0)

            # Restore engine state
            engine_state = state.get("engine_state")
            if engine_state and self.engine:
                self.engine.load_state(engine_state)

            logger.info(
                "Restored executor state: %d positions, %d trades",
                len(self.positions), len(self.trade_log),
            )
        except Exception as e:
            logger.error("Failed to load executor state: %s", e)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    async def reset(self) -> dict:
        """Reset trading engine and clear all state."""
        result = {}
        if self.engine:
            try:
                result = self.engine.reset(self.initial_balance)
            except Exception as e:
                logger.warning("Engine reset error: %s", e)

        self.positions.clear()
        self.trade_log.clear()
        self.last_scan_signals.clear()
        self.last_error = None
        self.total_executions = 0
        self.whitelist = DEFAULT_WHITELIST.copy()
        self._save_state()

        return {"status": "reset", "mode": self.mode, **result}

    # ------------------------------------------------------------------
    # Whitelist management
    # ------------------------------------------------------------------

    def get_whitelist(self) -> dict:
        """Return whitelist and all available pairs."""
        return {
            "whitelist": sorted(self.whitelist),
            "available_pairs": sorted(self.pair_map.keys()),
            "whitelist_count": len(self.whitelist),
            "available_count": len(self.pair_map),
        }

    def set_whitelist(self, symbols: List[str]) -> dict:
        """Replace the entire whitelist."""
        self.whitelist = [s.upper().replace("-", "/") for s in symbols]
        self._save_state()
        logger.info("Whitelist updated: %d symbols", len(self.whitelist))
        return self.get_whitelist()

    def add_to_whitelist(self, symbol: str) -> dict:
        """Add a single symbol to the whitelist."""
        symbol = symbol.upper().replace("-", "/")
        if symbol not in self.whitelist:
            self.whitelist.append(symbol)
            self._save_state()
            logger.info("Added %s to whitelist (%d total)", symbol, len(self.whitelist))
        return self.get_whitelist()

    def remove_from_whitelist(self, symbol: str) -> dict:
        """Remove a single symbol from the whitelist."""
        symbol = symbol.upper().replace("-", "/")
        if symbol in self.whitelist:
            self.whitelist.remove(symbol)
            self._save_state()
            logger.info("Removed %s from whitelist (%d total)", symbol, len(self.whitelist))
        return self.get_whitelist()


def _trade_matches(trade: ExecutorTrade, spec: dict) -> bool:
    """True when *trade* is the closed trade that *spec* names (recorded values)."""
    def same(a, b) -> bool:
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=0.0)
        except (TypeError, ValueError):
            return False
    try:
        times = (int(trade.entry_time) == int(spec["entry_time"])
                 and int(trade.exit_time) == int(spec["exit_time"]))
    except (TypeError, ValueError, OverflowError):
        return False
    return (trade.symbol == spec["symbol"] and trade.exit_signal == spec["exit_signal"] and times
            and all(same(getattr(trade, k), spec[k])
                    for k in ("entry_price", "exit_price", "volume", "cost_usd")))


# ---------------------------------------------------------------------------
# Volume formatting
# ---------------------------------------------------------------------------

def _format_volume(volume: float, price: float) -> float:
    """Format volume to appropriate precision.

    High-value assets (BTC): 8 decimal places
    Mid-value assets: 4-6 decimal places
    Low-value assets: 0-2 decimal places
    """
    if price > 10000:
        return round(volume, 8)
    elif price > 100:
        return round(volume, 6)
    elif price > 1:
        return round(volume, 4)
    elif price > 0.01:
        return round(volume, 2)
    else:
        return round(volume, 0)


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_executor: Optional[Executor] = None


def get_executor() -> Optional[Executor]:
    """Return the global executor instance, or None if not initialized."""
    return _executor


async def init_executor(
    mode: str = "paper",
    balance: float = 10000.0,
    scanner_symbols: Optional[List[str]] = None,
) -> Executor:
    """Initialize and return the global executor."""
    global _executor

    if scanner_symbols is None:
        from data_fetcher import DEFAULT_SYMBOLS
        scanner_symbols = DEFAULT_SYMBOLS

    _executor = Executor(mode=mode, initial_balance=balance)
    await _executor.initialize(scanner_symbols)
    return _executor


def get_or_create_executor() -> Optional[Executor]:
    """Return existing executor without async init."""
    return _executor
