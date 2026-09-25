"""
larsson_manager.py
~~~~~~~~~~~~~~~~~~
Position management for the Larsson-process study (Module C). Shadow research
only: selected by the study's config, never by the live scanner, and the RCCE
``PositionManager`` is left untouched.

Execution model (daily bars):
  * Every decision is made on a bar's close and fills at the next bar's open
    (a close-checked "manual" stop, as in the course). A gap through a stop
    fills at that open.
  * Resting support limits fill when the bar's low reaches them, at the lower
    of the open and the limit.
  * Costs: ``fee_bps`` + ``slip_bps`` per side, spot, leverage 1.

Sizing: ``risk_pct`` of current equity at risk per position,
allocation = risk x equity / ((entry - stop) / entry), capped at 25% of
equity. Stop = event level x (1 - stop_buffer), or 12% below entry when the
entry has no level (trend flips). Open risk across "alts" (90-day correlation
to BTC > 0.6) is capped at 5% of equity, with at most two new alt entries per
bar; the rest wait for the next bar while their setup stays valid. The stop
trails to the latest broken (breakout) level once price is more than 2R in
profit. No rebalancing: capital returns to the pool only on exit.

Variants (see docs/reviews/larsson-study.md):
  L1  trend only: gold flip -> 50% next open + 50% limit at nearest support
      (20-bar expiry); blue flip -> 50% next open, rest at the first close at
      or above nearest resistance, or after 10 bars.
  L2  L1 + adds on breakout/bounce while gold (1/3 size, max 2) + full exit on
      the breakdown of a distinct range.
  L3  L2, but while in a range: ignore flips, enter on bounce/breakout (stop at
      the level), exit 50% on rejection and 100% on breakdown.
  L4  L3 + trim 50% on the first grey after gold, restored if gold returns
      within 15 bars.
  L5  L3 with new longs only when the RCCE/BMSB gate allows it.
  B2  L1 mechanics driven by cto_engine's up state instead of the ribbon.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from engines.levels_engine import nearest_resistance, nearest_support

VARIANTS = ("L1", "L2", "L3", "L4", "L5", "B2", "L2P", "L3X50", "L3X100")
# Pattern variants run on a parent's rules plus one pattern rule (see docs/reviews/larsson-study.md).
PARENT = {"L2P": "L2", "L3X50": "L3", "L3X100": "L3"}
BULL_PATTERNS, BEAR_PATTERNS = {10, 11, 12, 13}, {20, 21, 23}


@dataclass(frozen=True)
class ManagerConfig:
    variant: str = "L1"
    risk_pct: float = 0.01
    stop_buffer: float = 0.01
    fallback_stop: float = 0.12
    max_alloc: float = 0.25
    alt_risk_budget: float = 0.05
    max_new_alt_per_bar: int = 2
    fee_bps: float = 5.0
    slip_bps: float = 5.0
    support_limit_bars: int = 20
    exit_tranche_bars: int = 10
    trail_R: float = 2.0
    add_fraction: float = 1.0 / 3.0
    max_adds: int = 2
    grey_restore_bars: int = 15
    enter_at_start: bool = True


@dataclass
class DayBar:
    """One symbol's daily bar plus everything known at its close."""
    symbol: str
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    trend: Optional[str] = None            # gold / blue / grey (B2: gold = CTO up, blue = not up)
    last_actionable: Optional[str] = None
    flip: Optional[str] = None
    grey_after_gold: bool = False
    events: List[dict] = field(default_factory=list)
    sr_levels: List[float] = field(default_factory=list)
    range_state: bool = False
    prev_range_state: bool = False
    gate_ok: bool = True
    is_alt: bool = False
    first_bar: bool = False                # first bar of the evaluation window
    patterns: List[int] = field(default_factory=list)   # pattern codes confirmed on this bar


@dataclass
class Position:
    symbol: str
    qty: float
    cost: float                            # USD paid incl. costs, for the open quantity
    entry_time: float
    entry_kind: str
    stop: float
    initial_risk_usd: float
    r_per_unit: float
    planned_alloc: float                   # USD allocation of the full position
    adds: int = 0
    realized: float = 0.0                  # proceeds from partial exits
    bars: int = 0
    broken_level: Optional[float] = None
    trimmed_qty: float = 0.0
    trim_bar: Optional[int] = None

    @property
    def avg_entry(self) -> float:
        return self.cost / self.qty if self.qty > 0 else 0.0


@dataclass
class ClosedTrade:
    symbol: str
    entry_time: float
    exit_time: float
    entry_kind: str
    exit_reason: str
    pnl_usd: float
    r_multiple: float
    bars_held: int


@dataclass
class _Order:
    symbol: str
    side: str                              # buy / sell
    reason: str
    fraction: float = 1.0                  # sell: fraction of current qty; buy: fraction of planned allocation
    stop_level: Optional[float] = None     # buy: event level for the stop, None -> fallback
    kind: str = ""                         # buy: entry / add / restore
    qty: Optional[float] = None            # restore: explicit quantity
    created: int = 0


class LarssonManager:
    """Same public surface as PositionManager: process_bar, mark_to_market,
    close_all_at_end, get_equity (plus process_day for multi-symbol bars)."""

    def __init__(self, initial_capital: float, symbols: List[str], config: ManagerConfig = ManagerConfig()):
        if config.variant not in VARIANTS:
            raise ValueError(f"Unknown variant {config.variant}")
        self.cfg = config
        self.symbols = list(symbols)
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[ClosedTrade] = []
        self.equity_curve: List[Tuple[float, float]] = []
        self.exposure_curve: List[Tuple[float, float]] = []
        self._orders: List[_Order] = []
        self._limits: Dict[str, dict] = {}          # symbol -> {price, alloc, expires, stop}
        self._exit_watch: Dict[str, dict] = {}      # symbol -> {resistance, deadline}
        self._last: Dict[str, float] = {}
        self._alt: Dict[str, bool] = {}
        self._sr: Dict[str, List[float]] = {}       # support/resistance known at each symbol's last close
        self._bar_index = 0
        self.fills = 0

    # ------------------------------------------------------------------ public API
    def process_bar(self, bar: DayBar) -> None:
        self.process_day(bar.timestamp, {bar.symbol: bar})

    def process_day(self, timestamp: float, bars: Dict[str, DayBar]) -> None:
        self._bar_index += 1
        for sym, b in bars.items():
            self._alt[sym] = b.is_alt
        self._execute_open(bars)
        self._execute_limits(bars)
        for sym in self.symbols:
            if sym in bars:
                self._on_close(bars[sym])
        self.mark_to_market(timestamp, {s: b.close for s, b in bars.items()})

    def mark_to_market(self, timestamp: float, prices: Dict[str, float]) -> None:
        self._last.update(prices)
        equity = self.get_equity()
        exposure = sum(p.qty * self._last.get(s, p.avg_entry) for s, p in self.positions.items())
        self.equity_curve.append((timestamp, equity))
        self.exposure_curve.append((timestamp, exposure / equity if equity > 0 else 0.0))

    def close_all_at_end(self, timestamp: float) -> None:
        for sym in list(self.positions):
            self._sell(sym, self._last[sym], 1.0, "WINDOW_END", timestamp)
        self._orders.clear()
        self._limits.clear()
        self._exit_watch.clear()

    def get_equity(self) -> float:
        return self.cash + sum(p.qty * self._last.get(s, p.avg_entry) for s, p in self.positions.items())

    # ------------------------------------------------------------------ fills
    def _cost_rate(self) -> float:
        return (self.cfg.fee_bps + self.cfg.slip_bps) / 10_000.0

    def _buy(self, sym: str, price: float, usd: float, timestamp: float, kind: str,
             stop: Optional[float] = None, planned: Optional[float] = None) -> float:
        usd = min(usd, self.cash)
        if usd <= 0 or price <= 0:
            return 0.0
        qty = usd * (1 - self._cost_rate()) / price
        self.cash -= usd
        self.fills += 1
        pos = self.positions.get(sym)
        if pos is None:
            r_unit = price - stop
            self.positions[sym] = Position(symbol=sym, qty=qty, cost=usd, entry_time=timestamp, entry_kind=kind,
                                           stop=stop, initial_risk_usd=qty * r_unit, r_per_unit=r_unit,
                                           planned_alloc=planned if planned is not None else usd)
        else:
            pos.qty += qty
            pos.cost += usd
            pos.initial_risk_usd += qty * max(price - pos.stop, 0.0)
        return qty

    def _sell(self, sym: str, price: float, fraction: float, reason: str, timestamp: float) -> None:
        pos = self.positions.get(sym)
        if pos is None:
            return
        fraction = min(max(fraction, 0.0), 1.0)
        qty = pos.qty * fraction
        proceeds = qty * price * (1 - self._cost_rate())
        cost_part = pos.cost * fraction
        self.cash += proceeds
        self.fills += 1
        pos.realized += proceeds - cost_part
        pos.qty -= qty
        pos.cost -= cost_part
        if fraction >= 1.0 or pos.qty <= 1e-12:
            pnl = pos.realized
            r = pnl / pos.initial_risk_usd if pos.initial_risk_usd > 0 else 0.0
            self.trades.append(ClosedTrade(sym, pos.entry_time, timestamp, pos.entry_kind, reason, pnl, r, pos.bars))
            del self.positions[sym]
            self._limits.pop(sym, None)
            self._exit_watch.pop(sym, None)

    # ------------------------------------------------------------------ open of bar
    def _open_risk_alts(self) -> float:
        return sum(p.qty * max(p.avg_entry - p.stop, 0.0) for s, p in self.positions.items() if self._alt.get(s))

    def _execute_open(self, bars: Dict[str, DayBar]) -> None:
        pending, self._orders = self._orders, []
        # Exits first so their cash is available to entries on the same open.
        for o in sorted(pending, key=lambda o: o.side != "sell"):
            b = bars.get(o.symbol)
            if b is None:
                self._orders.append(o)
                continue
            if o.side == "sell":
                self._sell(o.symbol, b.open, o.fraction, o.reason, b.timestamp)
        new_alts = 0
        equity = self.get_equity_at_open(bars)
        for o in [o for o in pending if o.side == "buy"]:
            b = bars.get(o.symbol)
            if b is None:
                continue
            price = b.open
            if o.kind == "restore":
                if o.symbol in self.positions and o.qty:
                    self._buy(o.symbol, price, o.qty * price, b.timestamp, "restore")
                continue
            if o.kind == "add":
                pos = self.positions.get(o.symbol)
                if pos is not None:
                    self._buy(o.symbol, price, pos.planned_alloc * o.fraction, b.timestamp, "add")
                continue
            if o.symbol in self.positions:
                continue
            stop = o.stop_level * (1 - self.cfg.stop_buffer) if o.stop_level else price * (1 - self.cfg.fallback_stop)
            if stop >= price:
                continue                                   # opened through the stop: no valid risk
            dist = (price - stop) / price
            alloc = min(self.cfg.risk_pct * equity / dist, self.cfg.max_alloc * equity)
            if self._alt.get(o.symbol):
                if new_alts >= self.cfg.max_new_alt_per_bar:
                    self._orders.append(o)                 # queue to the next bar
                    continue
                room = self.cfg.alt_risk_budget * equity - self._open_risk_alts()
                alloc = min(alloc, max(room, 0.0) / dist)
                if alloc <= 0:
                    self._orders.append(o)
                    continue
                new_alts += 1
            self._buy(o.symbol, price, alloc * o.fraction, b.timestamp, o.reason, stop=stop, planned=alloc)
            if o.reason in ("gold_flip", "cto_up") and o.fraction < 1.0:
                support = nearest_support(self._sr.get(o.symbol, []), price)
                if support is not None and support < price:
                    self._limits[o.symbol] = {"price": support, "alloc": alloc * (1 - o.fraction),
                                              "expires": self._bar_index + self.cfg.support_limit_bars}

    def get_equity_at_open(self, bars: Dict[str, DayBar]) -> float:
        return self.cash + sum(p.qty * (bars[s].open if s in bars else self._last.get(s, p.avg_entry))
                               for s, p in self.positions.items())

    def _execute_limits(self, bars: Dict[str, DayBar]) -> None:
        for sym, lim in list(self._limits.items()):
            b = bars.get(sym)
            if b is None:
                continue
            if self._bar_index > lim["expires"] or sym not in self.positions:
                self._limits.pop(sym)
                continue
            if b.low <= lim["price"]:
                self._buy(sym, min(b.open, lim["price"]), lim["alloc"], b.timestamp, "support_limit")
                self._limits.pop(sym)

    # ------------------------------------------------------------------ close of bar
    def _queue(self, order: _Order) -> None:
        order.created = self._bar_index
        if any(o.symbol == order.symbol and o.side == order.side and o.kind == order.kind for o in self._orders):
            return
        self._orders.append(order)

    def _entry(self, sym: str, reason: str, fraction: float, level: Optional[float], b: DayBar) -> None:
        if self.cfg.variant == "L5" and not b.gate_ok:
            return
        if sym in self.positions or any(o.symbol == sym and o.side == "buy" for o in self._orders):
            return
        self._queue(_Order(sym, "buy", reason, fraction=fraction, stop_level=level, kind="entry"))

    def _exit(self, sym: str, fraction: float, reason: str) -> None:
        if sym in self.positions:
            self._queue(_Order(sym, "sell", reason, fraction=fraction))

    def _on_close(self, b: DayBar) -> None:
        sym, v = b.symbol, PARENT.get(self.cfg.variant, self.cfg.variant)
        self._sr[sym] = b.sr_levels
        # Drop queued entries whose setup no longer holds (e.g. no longer gold).
        self._orders = [o for o in self._orders if not (o.symbol == sym and o.side == "buy" and o.kind == "entry"
                                                         and o.reason in ("gold_flip", "cto_up") and b.trend == "blue")]
        pos = self.positions.get(sym)
        if pos is not None:
            pos.bars += 1
            # Close-checked stop -> exit at the next open (a gap fills at that open).
            if b.close <= pos.stop:
                self._orders = [o for o in self._orders if o.symbol != sym]
                self._exit(sym, 1.0, "stop")
                self._limits.pop(sym, None)
                return
            for e in b.events:
                if e["event"] == "breakout" and e["level"] < b.close:
                    pos.broken_level = e["level"]
            if pos.r_per_unit > 0 and b.close >= pos.avg_entry + self.cfg.trail_R * pos.r_per_unit and pos.broken_level:
                pos.stop = max(pos.stop, pos.broken_level * (1 - self.cfg.stop_buffer))

        if self.cfg.variant in ("L3X50", "L3X100") and sym in self.positions and BEAR_PATTERNS & set(b.patterns):
            self._exit(sym, 0.5 if self.cfg.variant == "L3X50" else 1.0, "bear_pattern")
        ranging = v in ("L3", "L4", "L5") and b.range_state
        if ranging:
            self._range_rules(b)
        else:
            self._trend_rules(b)
            if v in ("L2", "L3", "L4", "L5"):
                self._level_rules(b)
        if v == "L4" and not ranging:
            self._grey_trim(b)

    def _trend_rules(self, b: DayBar) -> None:
        sym = b.symbol
        entry_reason = "cto_up" if self.cfg.variant == "B2" else "gold_flip"
        start_gold = b.first_bar and self.cfg.enter_at_start and b.last_actionable == "gold"
        if b.flip == "gold" or start_gold:
            self._exit_watch.pop(sym, None)
            self._entry(sym, entry_reason, 0.5, None, b)
        watch = self._exit_watch.get(sym)
        if b.flip == "blue" and sym in self.positions and watch is None:
            self._limits.pop(sym, None)
            self._exit(sym, 0.5, "blue_flip")
            res = nearest_resistance(b.sr_levels, b.close)
            self._exit_watch[sym] = {"resistance": res, "deadline": self._bar_index + self.cfg.exit_tranche_bars}
        elif watch is not None and sym in self.positions:
            hit = watch["resistance"] is not None and b.close >= watch["resistance"]
            if hit or self._bar_index >= watch["deadline"]:
                self._exit(sym, 1.0, "blue_flip_rest")
                self._exit_watch.pop(sym, None)

    def _level_rules(self, b: DayBar) -> None:
        sym = b.symbol
        pos = self.positions.get(sym)
        kinds = {e["event"] for e in b.events}
        if pos is not None and b.prev_range_state and "breakdown" in kinds:
            self._exit(sym, 1.0, "range_breakdown")
            return
        if self.cfg.variant == "L2P" and not BULL_PATTERNS & set(b.patterns):
            return
        if pos is not None and b.trend == "gold" and kinds & {"breakout", "bounce"} and pos.adds < self.cfg.max_adds:
            if self.cfg.variant == "L5" and not b.gate_ok:
                return
            if not any(o.symbol == sym and o.kind == "add" for o in self._orders):
                pos.adds += 1
                self._queue(_Order(sym, "buy", "add", fraction=self.cfg.add_fraction, kind="add"))

    def _range_rules(self, b: DayBar) -> None:
        sym = b.symbol
        by_kind = {e["event"]: e for e in b.events}
        if sym in self.positions:
            if "breakdown" in by_kind:
                self._exit(sym, 1.0, "range_breakdown")
            elif "rejection" in by_kind:
                self._exit(sym, 0.5, "range_rejection")
            return
        for kind in ("bounce", "breakout"):
            if kind in by_kind:
                self._entry(sym, f"range_{kind}", 1.0, by_kind[kind]["level"], b)
                return

    def _grey_trim(self, b: DayBar) -> None:
        sym = b.symbol
        pos = self.positions.get(sym)
        if pos is None:
            return
        if b.grey_after_gold and pos.trim_bar is None:
            pos.trimmed_qty = pos.qty * 0.5
            pos.trim_bar = self._bar_index
            self._exit(sym, 0.5, "grey_trim")
        elif pos.trim_bar is not None:
            if b.trend == "gold" and self._bar_index - pos.trim_bar <= self.cfg.grey_restore_bars:
                self._queue(_Order(sym, "buy", "restore", kind="restore", qty=pos.trimmed_qty))
                pos.trim_bar, pos.trimmed_qty = None, 0.0
            elif self._bar_index - pos.trim_bar > self.cfg.grey_restore_bars:
                pos.trim_bar, pos.trimmed_qty = None, 0.0
