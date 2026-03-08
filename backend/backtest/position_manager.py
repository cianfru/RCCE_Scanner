"""
position_manager.py
~~~~~~~~~~~~~~~~~~~
Tracks positions, executes trades based on scanner signals,
and records P&L for backtesting.

Entry sizing is gated by confluence strength.
Exit rules follow the scanner's signal hierarchy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    """A completed (or open) trade."""
    symbol: str
    side: str = "LONG"
    entry_time: float = 0.0
    entry_price: float = 0.0
    entry_signal: str = ""
    exit_time: Optional[float] = None
    exit_price: Optional[float] = None
    exit_signal: Optional[str] = None
    size_pct: float = 0.0          # % of per-symbol allocation used
    pnl_pct: Optional[float] = None
    pnl_usd: Optional[float] = None
    bars_held: int = 0
    confluence_at_entry: Optional[str] = None


@dataclass
class Position:
    """An open position for a single symbol."""
    symbol: str
    entry_price: float
    entry_time: float
    entry_signal: str
    size_pct: float              # current size as % of allocation
    side: str = "LONG"           # "LONG" or "SHORT"
    bars_held: int = 0
    confluence_at_entry: str = "UNKNOWN"
    peak_price: float = 0.0      # highest price since entry (for trailing stop)


# ---------------------------------------------------------------------------
# Sizing rules  (confluence-gated)
# ---------------------------------------------------------------------------

# {signal: {confluence_label: size_pct}}
_ENTRY_SIZING: Dict[str, Dict[str, float]] = {
    "STRONG_LONG":   {"STRONG": 1.00, "MODERATE": 0.75, "WEAK": 0.50, "CONFLICTING": 0.50, "UNKNOWN": 0.50},
    "LIGHT_LONG":    {"STRONG": 0.50, "MODERATE": 0.50, "WEAK": 0.25, "CONFLICTING": 0.25, "UNKNOWN": 0.25},
    # "ACCUMULATE":    {"STRONG": 0.25, "MODERATE": 0.25, "WEAK": 0.15, "CONFLICTING": 0.15, "UNKNOWN": 0.15},  # DISABLED for testing
    "REVIVAL_SEED":  {"STRONG": 0.10, "MODERATE": 0.10, "WEAK": 0.00, "CONFLICTING": 0.00, "UNKNOWN": 0.05},
    "LIGHT_SHORT":   {"STRONG": 0.30, "MODERATE": 0.25, "WEAK": 0.15, "CONFLICTING": 0.15, "UNKNOWN": 0.15},
}

_ENTRY_SIGNALS = set(_ENTRY_SIZING.keys())

# Exit signals and their behaviour
_EXIT_100_SIGNALS = {"TRIM_HARD", "NO_LONG", "TRIM"}
_EXIT_50_SIGNALS: set = set()  # TRIM moved to 100% for cleaner trade tracking
_EXIT_ALL_SIGNAL = "RISK_OFF"

_SIGNAL_DECAY_THRESHOLD = 20  # consecutive WAIT/neutral bars before stale exit

_STOP_LOSS_PCT = -0.08        # -8% stop-loss per position (LONG)
_SHORT_STOP_LOSS_PCT = 0.05   # +5% above entry triggers short stop


# ---------------------------------------------------------------------------
# Position Manager
# ---------------------------------------------------------------------------

class PositionManager:
    """Manages positions across multiple symbols for a backtest run."""

    def __init__(self, initial_capital: float, symbols: List[str], leverage: float = 1.0):
        self.initial_capital = initial_capital
        self.leverage = max(leverage, 1.0)
        self.num_symbols = max(len(symbols), 1)
        self.per_symbol_alloc = (initial_capital * self.leverage) / self.num_symbols

        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[float, float]] = []   # (timestamp, equity)

        # Cash not allocated to positions (leveraged buying power)
        self.cash = initial_capital * self.leverage

        # Track consecutive WAIT signals per symbol for decay exit
        self._wait_counts: Dict[str, int] = {s: 0 for s in symbols}

        # Track latest prices for mark-to-market
        self._latest_prices: Dict[str, float] = {}

        # Macro filter: when True, all entry signals are blocked
        # Set externally by runner (e.g. BMSB below for 2+ weeks)
        self.macro_blocked: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_bar(self, bar) -> Optional[Trade]:
        """Process a single BarResult. Returns a Trade if one was opened or closed.

        Parameters
        ----------
        bar : BarResult
            From the replay engine.

        Returns
        -------
        Trade or None
        """
        sym = bar.symbol
        price = bar.price
        signal = bar.signal
        self._latest_prices[sym] = price

        # Increment bars held on open positions
        if sym in self.positions:
            self.positions[sym].bars_held += 1

        # --- STOP-LOSS: check before any signal logic ---
        if sym in self.positions:
            pos = self.positions[sym]
            if pos.side == "SHORT":
                # SHORT stop: price moved UP against us
                unrealized = (pos.entry_price - price) / pos.entry_price if pos.entry_price > 0 else 0
                if unrealized <= -_SHORT_STOP_LOSS_PCT:
                    trade = self._close_position(sym, bar.timestamp, price, "STOP_LOSS", close_pct=1.0)
                    self._wait_counts[sym] = 0
                    return trade
            else:
                # LONG stop: price moved DOWN against us
                unrealized = (price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
                if unrealized <= _STOP_LOSS_PCT:
                    trade = self._close_position(sym, bar.timestamp, price, "STOP_LOSS", close_pct=1.0)
                    self._wait_counts[sym] = 0
                    return trade

        # SHORT exits are managed by stop loss (5%) and macro flip only.
        # No regime exit — RCCE reclassifies bear rallies as MARKUP/REACC,
        # and shorts enter during those regimes. Regime exit would close
        # them immediately.

        # --- RISK_OFF: close ALL positions ---
        if signal == _EXIT_ALL_SIGNAL:
            trades = self._close_all(bar.timestamp, price_override=None, exit_signal=signal)
            self._wait_counts[sym] = 0
            # Return last trade (or None)
            return trades[-1] if trades else None

        # --- Exit signals for this symbol ---
        if signal in _EXIT_100_SIGNALS:
            self._wait_counts[sym] = 0
            if sym in self.positions:
                return self._close_position(sym, bar.timestamp, price, signal, close_pct=1.0)
            return None

        if signal in _EXIT_50_SIGNALS:
            self._wait_counts[sym] = 0
            if sym in self.positions:
                return self._close_position(sym, bar.timestamp, price, signal, close_pct=0.5)
            return None

        # --- Signal decay (stale WAIT) ---
        if signal == "WAIT":
            self._wait_counts[sym] = self._wait_counts.get(sym, 0) + 1
            if self._wait_counts[sym] >= _SIGNAL_DECAY_THRESHOLD and sym in self.positions:
                trade = self._close_position(sym, bar.timestamp, price, "DECAY_EXIT", close_pct=1.0)
                self._wait_counts[sym] = 0
                return trade
            return None

        # --- Entry signals ---
        if signal in _ENTRY_SIGNALS:
            self._wait_counts[sym] = 0

            # No macro gating here — the synthesizer enforces direction:
            # BMSB bullish → long signals only, BMSB bearish → LIGHT_SHORT only

            confluence = bar.confluence_label

            # ACCUMULATE: can add to existing position (DCA)
            if signal == "ACCUMULATE" and sym in self.positions:
                return self._add_to_position(sym, bar, confluence)

            # Other entry: only if no existing position
            if sym not in self.positions:
                return self._open_position(sym, bar, confluence)

        # Reset wait count on any non-WAIT signal
        if signal != "WAIT":
            self._wait_counts[sym] = 0

        return None

    def mark_to_market(self, timestamp: float, prices: Dict[str, float]):
        """Update equity curve with current prices."""
        self._latest_prices.update(prices)
        equity = self._compute_equity()
        self.equity_curve.append((timestamp, equity))

    def close_all_at_end(self, timestamp: float):
        """Force-close all remaining positions at the end of the backtest."""
        for sym in list(self.positions.keys()):
            price = self._latest_prices.get(sym, self.positions[sym].entry_price)
            self._close_position(sym, timestamp, price, "BACKTEST_END", close_pct=1.0)

    def get_equity(self) -> float:
        """Current total equity (cash + mark-to-market positions)."""
        return self._compute_equity()

    # ------------------------------------------------------------------
    # Position operations
    # ------------------------------------------------------------------

    def _open_position(self, sym: str, bar, confluence: str) -> Optional[Trade]:
        """Open a new position."""
        size_table = _ENTRY_SIZING.get(bar.signal, {})
        size_pct = size_table.get(confluence, size_table.get("UNKNOWN", 0.0))

        if size_pct <= 0:
            return None

        # Cap at available allocation
        alloc_usd = self.per_symbol_alloc * size_pct
        if alloc_usd > self.cash:
            alloc_usd = self.cash
            size_pct = alloc_usd / self.per_symbol_alloc if self.per_symbol_alloc > 0 else 0

        if alloc_usd <= 0:
            return None

        self.cash -= alloc_usd

        side = "SHORT" if bar.signal == "LIGHT_SHORT" else "LONG"
        pos = Position(
            symbol=sym,
            entry_price=bar.price,
            entry_time=bar.timestamp,
            entry_signal=bar.signal,
            size_pct=size_pct,
            side=side,
            confluence_at_entry=confluence,
            peak_price=bar.price,
        )
        self.positions[sym] = pos

        logger.debug(
            "OPEN %s %s: %s @ %.4f, size=%.0f%%, confluence=%s",
            side, sym, bar.signal, bar.price, size_pct * 100, confluence,
        )
        return None  # Trade not recorded until closed

    def _add_to_position(self, sym: str, bar, confluence: str) -> Optional[Trade]:
        """DCA into an existing position (ACCUMULATE signal)."""
        pos = self.positions[sym]
        size_table = _ENTRY_SIZING.get(bar.signal, {})
        add_pct = size_table.get(confluence, size_table.get("UNKNOWN", 0.0))

        if add_pct <= 0:
            return None

        # Cap total at 100% of allocation
        new_total = min(pos.size_pct + add_pct, 1.0)
        actual_add = new_total - pos.size_pct
        if actual_add <= 0:
            return None

        alloc_usd = self.per_symbol_alloc * actual_add
        if alloc_usd > self.cash:
            alloc_usd = self.cash
            actual_add = alloc_usd / self.per_symbol_alloc if self.per_symbol_alloc > 0 else 0

        if alloc_usd <= 0:
            return None

        self.cash -= alloc_usd

        # Weighted average entry price
        old_value = pos.size_pct * pos.entry_price
        new_value = actual_add * bar.price
        pos.entry_price = (old_value + new_value) / (pos.size_pct + actual_add)
        pos.size_pct += actual_add

        logger.debug(
            "DCA %s: +%.0f%% @ %.4f, total=%.0f%%",
            sym, actual_add * 100, bar.price, pos.size_pct * 100,
        )
        return None

    def _close_position(
        self, sym: str, timestamp: float, price: float,
        exit_signal: str, close_pct: float = 1.0,
    ) -> Optional[Trade]:
        """Close (fully or partially) a position and record a trade."""
        if sym not in self.positions:
            return None

        pos = self.positions[sym]
        close_size = pos.size_pct * close_pct
        alloc_usd = self.per_symbol_alloc * close_size

        # P&L calculation — inverted for shorts
        if pos.side == "SHORT":
            pnl_pct = (pos.entry_price - price) / pos.entry_price * 100.0 if pos.entry_price > 0 else 0.0
        else:
            pnl_pct = (price - pos.entry_price) / pos.entry_price * 100.0 if pos.entry_price > 0 else 0.0
        pnl_usd = alloc_usd * (pnl_pct / 100.0)

        # Return capital + P&L to cash
        self.cash += alloc_usd + pnl_usd

        trade = Trade(
            symbol=sym,
            side=pos.side,
            entry_time=pos.entry_time,
            entry_price=pos.entry_price,
            entry_signal=pos.entry_signal,
            exit_time=timestamp,
            exit_price=price,
            exit_signal=exit_signal,
            size_pct=close_size,
            pnl_pct=pnl_pct,
            pnl_usd=pnl_usd,
            bars_held=pos.bars_held,
            confluence_at_entry=pos.confluence_at_entry,
        )
        self.trades.append(trade)

        if close_pct >= 1.0:
            del self.positions[sym]
        else:
            pos.size_pct -= close_size

        logger.debug(
            "CLOSE %s: %s @ %.4f, pnl=%.2f%% ($%.2f), held=%d bars",
            sym, exit_signal, price, pnl_pct, pnl_usd, pos.bars_held,
        )
        return trade

    def close_all_shorts(
        self, timestamp: float, exit_signal: str = "MACRO_FLIP",
    ) -> List[Trade]:
        """Close all SHORT positions (macro regime flipped bullish)."""
        trades = []
        for sym in list(self.positions.keys()):
            if self.positions[sym].side == "SHORT":
                price = self._latest_prices.get(sym, self.positions[sym].entry_price)
                t = self._close_position(sym, timestamp, price, exit_signal, close_pct=1.0)
                if t:
                    trades.append(t)
        return trades

    def _close_all(
        self, timestamp: float, price_override: Optional[float], exit_signal: str,
    ) -> List[Trade]:
        """Close all open positions (RISK_OFF)."""
        trades = []
        for sym in list(self.positions.keys()):
            price = price_override or self._latest_prices.get(sym, self.positions[sym].entry_price)
            t = self._close_position(sym, timestamp, price, exit_signal, close_pct=1.0)
            if t:
                trades.append(t)
        return trades

    # ------------------------------------------------------------------
    # Equity helpers
    # ------------------------------------------------------------------

    def _compute_equity(self) -> float:
        """Equity = cash + mark-to-market positions - borrowed amount.

        With leverage, we borrow (leverage - 1) * initial_capital. The equity
        curve tracks returns against the actual capital deposited.
        """
        borrowed = self.initial_capital * (self.leverage - 1)
        equity = self.cash - borrowed
        for sym, pos in self.positions.items():
            price = self._latest_prices.get(sym, pos.entry_price)
            alloc_usd = self.per_symbol_alloc * pos.size_pct
            if pos.side == "SHORT":
                pnl_pct = (pos.entry_price - price) / pos.entry_price if pos.entry_price > 0 else 0
            else:
                pnl_pct = (price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
            equity += alloc_usd * (1 + pnl_pct)
        return equity
