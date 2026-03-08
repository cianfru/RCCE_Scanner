"""
executor.py
~~~~~~~~~~~
Execution engine that converts scanner signals into Kraken orders.
Supports paper trading (default) and live trading modes.

Signal flow:
    Scanner → synthesize_signal() → Executor → kraken CLI → orders

The executor is a singleton — access via get_executor().
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from kraken_pairs import (
    discover_tradeable_pairs,
    scanner_to_kraken,
    get_kraken_binary,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATE_FILE = Path(__file__).parent / "data" / "executor_state.json"

# Reuse sizing logic from backtest position_manager
_ENTRY_SIZING: Dict[str, Dict[str, float]] = {
    "STRONG_LONG":  {"STRONG": 1.00, "MODERATE": 0.75, "WEAK": 0.50, "CONFLICTING": 0.50, "UNKNOWN": 0.50},
    "LIGHT_LONG":   {"STRONG": 0.50, "MODERATE": 0.50, "WEAK": 0.25, "CONFLICTING": 0.25, "UNKNOWN": 0.25},
    "ACCUMULATE":   {"STRONG": 0.25, "MODERATE": 0.25, "WEAK": 0.15, "CONFLICTING": 0.15, "UNKNOWN": 0.15},
    "REVIVAL_SEED": {"STRONG": 0.10, "MODERATE": 0.10, "WEAK": 0.00, "CONFLICTING": 0.00, "UNKNOWN": 0.05},
    "LIGHT_SHORT":  {"STRONG": 0.30, "MODERATE": 0.25, "WEAK": 0.15, "CONFLICTING": 0.15, "UNKNOWN": 0.15},
}

_ENTRY_SIGNALS = set(_ENTRY_SIZING.keys())
_EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "NO_LONG", "RISK_OFF"}

# Minimum order sizes on Kraken (approximate, in base currency)
_MIN_ORDER_USD = 5.0  # Kraken minimum is usually ~$5-10


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class ExecutorPosition:
    """An open position tracked by the executor."""
    symbol: str                     # scanner format: BTC/USDT
    kraken_pair: str                # kraken format: BTCUSD
    side: str = "LONG"              # LONG or SHORT
    entry_price: float = 0.0
    entry_time: float = 0.0
    entry_signal: str = ""
    volume: float = 0.0             # base currency amount
    cost_usd: float = 0.0           # USD cost at entry
    size_pct: float = 0.0           # % of allocation used
    confluence_at_entry: str = "UNKNOWN"
    order_id: str = ""              # Kraken order ID
    entry_reason: str = ""          # signal_reason at entry time
    entry_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ExecutorPosition:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ExecutorTrade:
    """A completed trade."""
    symbol: str
    kraken_pair: str
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
    order_ids: List[str] = field(default_factory=list)
    entry_reason: str = ""
    entry_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Executor errors
# ---------------------------------------------------------------------------

class ExecutorError(Exception):
    """Raised when a Kraken CLI call fails."""
    def __init__(self, category: str, message: str):
        self.category = category
        self.message = message
        super().__init__(f"[{category}] {message}")


# ---------------------------------------------------------------------------
# Main Executor class
# ---------------------------------------------------------------------------

class Executor:
    """Converts scanner signals into Kraken orders.

    Modes:
        paper  — uses kraken paper buy/sell (no auth, live prices)
        live   — uses kraken order buy/sell (requires auth)
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

        # State
        self.positions: Dict[str, ExecutorPosition] = {}
        self.trade_log: List[ExecutorTrade] = []
        self.pair_map: Dict[str, str] = {}  # {scanner_sym: kraken_pair}
        self.last_scan_signals: Dict[str, str] = {}
        self.last_error: Optional[str] = None
        self.last_execution_time: Optional[float] = None
        self.total_executions: int = 0

        # Kraken binary path
        self._kraken_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self, scanner_symbols: List[str]) -> dict:
        """Initialize the executor: find kraken, discover pairs, init paper."""
        self._kraken_path = get_kraken_binary()
        if not self._kraken_path:
            raise ExecutorError("config", "kraken-cli not found. Install: curl --proto '=https' --tlsv1.2 -LsSf https://github.com/krakenfx/kraken-cli/releases/latest/download/kraken-cli-installer.sh | sh")

        # Discover which scanner symbols are tradeable on Kraken
        self.pair_map = await discover_tradeable_pairs(
            scanner_symbols, self._kraken_path
        )
        logger.info("Executor: %d tradeable pairs discovered", len(self.pair_map))

        # Initialize paper trading account
        if self.mode == "paper":
            try:
                result = await self._kraken_call([
                    "paper", "init",
                    "--balance", str(self.initial_balance),
                ])
            except ExecutorError as e:
                if "already initialized" in str(e).lower():
                    # Reset clears AND re-initializes with default balance
                    result = await self._kraken_call(["paper", "reset"])
                    # If we need a different balance, re-init
                    if self.initial_balance != 10000.0:
                        try:
                            result = await self._kraken_call([
                                "paper", "init",
                                "--balance", str(self.initial_balance),
                            ])
                        except ExecutorError:
                            pass  # reset already initialized with default
                else:
                    raise
            logger.info("Paper account initialized: %s", result)

        # Load persisted state if exists
        self._load_state()

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

            # Skip symbols not on Kraken
            if symbol not in self.pair_map:
                continue

            signal_reason = r.get("signal_reason", "")
            signal_warnings = r.get("signal_warnings", [])

            try:
                action = await self._process_signal(
                    symbol, signal, price, confluence_label,
                    signal_reason, signal_warnings,
                )
                if action:
                    actions_taken.append(action)
            except ExecutorError as e:
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
        kraken_pair = self.pair_map[symbol]
        side = "SHORT" if signal == "LIGHT_SHORT" else "LONG"

        # Calculate volume
        allocation = self.initial_balance / max(len(self.pair_map), 1)
        usd_amount = allocation * size_pct
        if usd_amount < _MIN_ORDER_USD:
            logger.debug("Skipping %s — amount $%.2f below minimum", symbol, usd_amount)
            return None

        volume = usd_amount / price if price > 0 else 0
        if volume <= 0:
            return None

        # Format volume (Kraken expects reasonable precision)
        volume = _format_volume(volume, price)

        # Place order
        if self.mode == "paper":
            order_cmd = "sell" if side == "SHORT" else "buy"
            result = await self._kraken_call([
                "paper", order_cmd, kraken_pair, str(volume),
            ])
        else:
            # Live mode (future)
            order_cmd = "sell" if side == "SHORT" else "buy"
            result = await self._kraken_call([
                "order", order_cmd, kraken_pair, str(volume),
                "--type", "market",
            ])

        # Record position
        order_id = result.get("order_id", "")
        fill_price = result.get("price", price)

        self.positions[symbol] = ExecutorPosition(
            symbol=symbol,
            kraken_pair=kraken_pair,
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
        kraken_pair = pos.kraken_pair

        # Place closing order (reverse direction)
        if self.mode == "paper":
            close_cmd = "buy" if pos.side == "SHORT" else "sell"
            result = await self._kraken_call([
                "paper", close_cmd, kraken_pair, str(pos.volume),
            ])
        else:
            close_cmd = "buy" if pos.side == "SHORT" else "sell"
            result = await self._kraken_call([
                "order", close_cmd, kraken_pair, str(pos.volume),
                "--type", "market",
            ])

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
            kraken_pair=kraken_pair,
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
            order_ids=[pos.order_id, result.get("order_id", "")],
            entry_reason=pos.entry_reason,
            entry_warnings=pos.entry_warnings,
        )
        self.trade_log.append(trade)

        # Remove position
        del self.positions[symbol]

        pnl_sign = "+" if pnl_pct >= 0 else ""
        action = (
            f"CLOSE {pos.side} {symbol} @ ${fill_price:,.2f} "
            f"({exit_signal}, {pnl_sign}{pnl_pct:.1f}%, ${pnl_sign}{pnl_usd:.2f})"
        )
        logger.info("EXIT: %s", action)
        return action

    # ------------------------------------------------------------------
    # Kraken CLI wrapper
    # ------------------------------------------------------------------

    async def _kraken_call(
        self,
        args: List[str],
        retries: int = 0,
    ) -> dict:
        """Call kraken CLI and return parsed JSON response."""
        if not self._kraken_path:
            raise ExecutorError("config", "kraken-cli not found")

        cmd = [self._kraken_path] + args + ["-o", "json"]
        logger.debug("Kraken call: %s", " ".join(args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
        except asyncio.TimeoutError:
            raise ExecutorError("network", f"Kraken CLI timed out: {' '.join(args)}")

        stdout_str = stdout.decode().strip() if stdout else ""
        if not stdout_str:
            raise ExecutorError("io", f"No output from kraken CLI: {' '.join(args)}")

        try:
            data = json.loads(stdout_str)
        except json.JSONDecodeError:
            raise ExecutorError("parse", f"Invalid JSON from kraken: {stdout_str[:200]}")

        if proc.returncode != 0:
            category = data.get("error", "unknown")
            message = data.get("message", str(data))

            # Retry on transient errors
            if category == "rate_limit" and retries < 2:
                wait = 5 * (retries + 1)
                logger.warning("Rate limited — waiting %ds before retry", wait)
                await asyncio.sleep(wait)
                return await self._kraken_call(args, retries + 1)

            if category == "network" and retries < 3:
                wait = 2 ** retries
                logger.warning("Network error — retrying in %ds", wait)
                await asyncio.sleep(wait)
                return await self._kraken_call(args, retries + 1)

            raise ExecutorError(category, message)

        return data

    # ------------------------------------------------------------------
    # Status & queries
    # ------------------------------------------------------------------

    async def get_status(self) -> dict:
        """Return current executor status."""
        portfolio = {}
        if self.initialized and self.mode == "paper":
            try:
                portfolio = await self._kraken_call(["paper", "status"])
            except Exception as e:
                logger.warning("Failed to get paper status: %s", e)

        total_pnl = sum(t.pnl_pct for t in self.trade_log)
        wins = sum(1 for t in self.trade_log if t.pnl_pct > 0)

        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "initialized": self.initialized,
            "positions": {
                sym: pos.to_dict() for sym, pos in self.positions.items()
            },
            "open_position_count": len(self.positions),
            "total_trades": len(self.trade_log),
            "total_pnl_pct": round(total_pnl, 2),
            "win_rate": round(wins / len(self.trade_log) * 100, 1) if self.trade_log else 0,
            "last_scan_signals": self.last_scan_signals,
            "last_error": self.last_error,
            "last_execution_time": self.last_execution_time,
            "total_executions": self.total_executions,
            "available_pairs": len(self.pair_map),
            "paper_balance": self.initial_balance,
            "portfolio": portfolio,
        }

    def get_trades(self) -> List[dict]:
        """Return trade history."""
        return [t.to_dict() for t in self.trade_log]

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        """Persist executor state to disk."""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "mode": self.mode,
                "enabled": self.enabled,
                "initial_balance": self.initial_balance,
                "positions": {
                    sym: pos.to_dict()
                    for sym, pos in self.positions.items()
                },
                "trade_log": [t.to_dict() for t in self.trade_log],
                "pair_map": self.pair_map,
                "last_scan_signals": self.last_scan_signals,
                "total_executions": self.total_executions,
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
                self.trade_log.append(ExecutorTrade(**{
                    k: v for k, v in t_dict.items()
                    if k in ExecutorTrade.__dataclass_fields__
                }))

            # Restore pair map only if not already populated by discovery
            if not self.pair_map:
                self.pair_map = state.get("pair_map", {})

            self.total_executions = state.get("total_executions", 0)

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
        """Reset paper account and clear all state."""
        if self.mode == "paper":
            # reset both clears state AND re-initializes with default balance
            result = await self._kraken_call(["paper", "reset"])
        else:
            result = {}

        self.positions.clear()
        self.trade_log.clear()
        self.last_scan_signals.clear()
        self.last_error = None
        self.total_executions = 0
        self._save_state()

        return {"status": "reset", "mode": self.mode, **result}


# ---------------------------------------------------------------------------
# Volume formatting
# ---------------------------------------------------------------------------

def _format_volume(volume: float, price: float) -> float:
    """Format volume to appropriate precision for Kraken.

    High-value assets (BTC): 8 decimal places
    Mid-value assets: 4-6 decimal places
    Low-value assets: 0-2 decimal places
    """
    if price > 10000:
        # BTC-class: up to 8 decimals
        return round(volume, 8)
    elif price > 100:
        # ETH/BNB-class: up to 6 decimals
        return round(volume, 6)
    elif price > 1:
        # Mid-cap: up to 4 decimals
        return round(volume, 4)
    elif price > 0.01:
        # Small-cap: up to 2 decimals
        return round(volume, 2)
    else:
        # Micro-cap (SHIB, PEPE): integer volume
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
