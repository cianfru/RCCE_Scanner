"""
Horizontal levels and level events (version ``levels-1``) — research, shadow only.

Deterministic, rule-based levels in the spirit of the Larsson process. A
proprietary level picker cannot be reproduced exactly, so these rules are
tuned on trading outcome in the study, never on agreement with any vendor.

Levels at bar i use completed bars < i only:

1. Body pivots: bar j is a pivot high when max(open, close) is the maximum
   of that quantity over [j-n, j+n] (pivot low likewise on min(open, close)).
   A pivot is confirmed only once j+n < i.
2. Pivots inside the lookback W are sorted by price and clustered: a pivot
   joins the current cluster while it is within ``tol`` of the cluster's
   first price.
3. Level price = mean of the cluster. ``touches`` counts pivots at least
   ``gap`` bars apart; ``n_high``/``n_low`` count pivot highs/lows;
   ``last_touch_age`` is bars since the most recent pivot in the cluster.
4. Keep a level when touches >= min_touches and last_touch_age <= max_last.

Events on the close of bar i (buffer b):

    breakout   close > L(1+b) and prev close <= L(1+b)        needs n_high >= 2
    breakdown  close < L(1-b) and prev close >= L(1-b)        needs n_low  >= 2
    bounce     low <= L(1+b), close > L(1+b), prev close > L  needs n_low  >= 2
    rejection  high >= L(1+b) and close < L                   needs n_high >= 2

Fakeouts: at most ``max_attempts`` events per level and direction (up =
breakout/bounce, down = breakdown/rejection); after that the level is
ignored for ``cooldown`` bars. Level identity is carried across bars while
the recomputed price stays within ``tol``.

Range regime: on when the last R closes sit between one support and one
resistance level (each >= 2 touches) and the band is at most k x ATR(14), or
when the ribbon changed colour >= ``range_flips`` times in the last R bars
with net displacement under 2 x ATR. The band is fixed when the range starts
and the range ends on a close beyond it by the buffer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

LEVELS_VERSION = "levels-1"
UP_EVENTS = ("breakout", "bounce")
DOWN_EVENTS = ("breakdown", "rejection")


@dataclass(frozen=True)
class LevelConfig:
    n: int = 5
    tol: float = 0.015
    W: int = 730
    gap: int = 10
    min_touches: int = 2
    max_last: int = 30
    b: float = 0.01
    max_attempts: int = 3
    cooldown: int = 30
    R: int = 40
    k_atr: float = 8.0
    range_flips: int = 4
    range_disp_atr: float = 2.0


@dataclass
class Level:
    price: float
    touches: int
    n_high: int
    n_low: int
    last_touch_age: int
    first_touch_age: int
    span: int
    std_pct: float
    id: int = -1


def body_pivots(open_: np.ndarray, close: np.ndarray, n: int) -> List[tuple]:
    """All body pivots (j, price, 'H'|'L'); ties count, as in the calibration."""
    top = np.maximum(open_, close)
    bot = np.minimum(open_, close)
    out = []
    for j in range(n, len(close) - n):
        if top[j] == top[j - n:j + n + 1].max():
            out.append((j, float(top[j]), "H"))
        if bot[j] == bot[j - n:j + n + 1].min():
            out.append((j, float(bot[j]), "L"))
    return out


def levels_at(i: int, pivots: Sequence[tuple], cfg: LevelConfig, *, filtered: bool = True) -> List[Level]:
    """Levels visible at bar i from pivots confirmed before it."""
    pts = sorted((p for p in pivots if i - cfg.W <= p[0] and p[0] + cfg.n < i), key=lambda p: p[1])
    clusters, cur = [], []
    for p in pts:
        if cur and p[1] > cur[0][1] * (1 + cfg.tol):
            clusters.append(cur)
            cur = []
        cur.append(p)
    if cur:
        clusters.append(cur)
    out = []
    for c in clusters:
        js = sorted(p[0] for p in c)
        touches = [js[0]]
        for j in js[1:]:
            if j - touches[-1] >= cfg.gap:
                touches.append(j)
        prices = np.array([p[1] for p in c])
        lvl = Level(price=float(prices.mean()), touches=len(touches),
                    n_high=sum(1 for p in c if p[2] == "H"), n_low=sum(1 for p in c if p[2] == "L"),
                    last_touch_age=i - js[-1], first_touch_age=i - js[0], span=js[-1] - js[0],
                    std_pct=float(prices.std() / prices.mean() * 100))
        if not filtered or (lvl.touches >= cfg.min_touches and lvl.last_touch_age <= cfg.max_last):
            out.append(lvl)
    return out


def classify(level: float, n_high: int, n_low: int, c0: float, c1: float, hi: float, lo: float, b: float) -> List[str]:
    """Events a single level produces on one bar (usually none)."""
    ev = []
    up, dn = level * (1 + b), level * (1 - b)
    if c0 > up and c1 <= up and n_high >= 2:
        ev.append("breakout")
    if c0 < dn and c1 >= dn and n_low >= 2:
        ev.append("breakdown")
    if lo <= up and c0 > up and c1 > level and n_low >= 2:
        ev.append("bounce")
    if hi >= up and c0 < level and n_high >= 2:
        ev.append("rejection")
    return ev


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> np.ndarray:
    prev = np.concatenate(([close[0]], close[:-1]))
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    out = np.full(len(close), np.nan)
    if len(close) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(close)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


@dataclass
class BarLevels:
    """Module B output for one bar (all inputs from bars <= i)."""
    events: List[dict] = field(default_factory=list)
    levels: List[Level] = field(default_factory=list)
    # Support/resistance for order placement: every >= min_touches level in
    # the lookback, regardless of last-touch age (event levels are filtered).
    sr_levels: List[float] = field(default_factory=list)
    range_state: bool = False
    range_band: Optional[tuple] = None
    atr: float = float("nan")


def compute_levels(ohlcv: Dict[str, np.ndarray], cfg: LevelConfig = LevelConfig(),
                   ribbon_states: Optional[Sequence[Optional[str]]] = None, start: int = 0) -> List[BarLevels]:
    """Bar-by-bar levels, events and range regime for one chart (ALT/USD or ALT/BTC).

    ``ribbon_states`` (Module A states per bar) enables the colour-churn range
    trigger. Bars before ``start`` are skipped (returned empty) but still feed
    pivots, so the output does not depend on where the caller starts reading.
    """
    o, h, l, c = (np.asarray(ohlcv[k], dtype=np.float64) for k in ("open", "high", "low", "close"))
    n_bars = len(c)
    pivots = body_pivots(o, c, cfg.n)
    atr = wilder_atr(h, l, c)
    out: List[BarLevels] = [BarLevels() for _ in range(n_bars)]

    tracked: List[list] = []              # [id, price]
    next_id = 0
    attempts: Dict[tuple, int] = {}       # (level id, direction) -> count
    ignored_until: Dict[int, int] = {}
    in_range, band = False, None

    begin = max(start, 1)
    for i in range(begin, n_bars):
        every = levels_at(i, pivots, cfg, filtered=False)
        lvls = [lv for lv in every if lv.touches >= cfg.min_touches and lv.last_touch_age <= cfg.max_last]
        sr = sorted(lv.price for lv in every if lv.touches >= cfg.min_touches)
        for lv in lvls:                   # stable identity across bars
            match = next((t for t in tracked if abs(lv.price / t[1] - 1) <= cfg.tol), None)
            if match is None:
                match = [next_id, lv.price]
                next_id += 1
                tracked.append(match)
            match[1] = lv.price
            lv.id = match[0]

        events = []
        for lv in lvls:
            if ignored_until.get(lv.id, -1) >= i:
                continue
            if lv.id in ignored_until:
                ignored_until.pop(lv.id)
                attempts.pop((lv.id, "up"), None)
                attempts.pop((lv.id, "down"), None)
            for ev in classify(lv.price, lv.n_high, lv.n_low, c[i], c[i - 1], h[i], l[i], cfg.b):
                direction = "up" if ev in UP_EVENTS else "down"
                key = (lv.id, direction)
                attempts[key] = attempts.get(key, 0) + 1
                if attempts[key] >= cfg.max_attempts:
                    ignored_until[lv.id] = i + cfg.cooldown
                events.append({"event": ev, "level": lv.price, "level_id": lv.id, "touches": lv.touches,
                               "n_high": lv.n_high, "n_low": lv.n_low, "attempt": attempts[key],
                               "close": float(c[i]), "last_touch_age": lv.last_touch_age})

        # Range regime (band fixed at entry; ends on a close beyond it)
        if in_range and band is not None:
            if c[i] > band[1] * (1 + cfg.b) or c[i] < band[0] * (1 - cfg.b):
                in_range, band = False, None
        if not in_range and i >= cfg.R and np.isfinite(atr[i]):
            window = c[i - cfg.R + 1:i + 1]
            lo_c, hi_c = window.min(), window.max()
            sup = max((lv.price for lv in lvls if lv.touches >= 2 and lv.price <= lo_c), default=None)
            res = min((lv.price for lv in lvls if lv.touches >= 2 and lv.price >= hi_c), default=None)
            if sup is not None and res is not None and res - sup <= cfg.k_atr * atr[i]:
                in_range, band = True, (sup, res)
            elif ribbon_states is not None:
                recent = [s for s in ribbon_states[i - cfg.R + 1:i + 1] if s]
                changes = sum(1 for a, b2 in zip(recent, recent[1:]) if a != b2)
                if changes >= cfg.range_flips and abs(c[i] - c[i - cfg.R]) < cfg.range_disp_atr * atr[i]:
                    in_range, band = True, (float(lo_c), float(hi_c))

        out[i] = BarLevels(events=events, levels=lvls, sr_levels=sr, range_state=in_range, range_band=band, atr=float(atr[i]))
    return out


def nearest_support(prices: Sequence[float], price: float) -> Optional[float]:
    below = [p for p in prices if p < price]
    return max(below) if below else None


def nearest_resistance(prices: Sequence[float], price: float) -> Optional[float]:
    above = [p for p in prices if p > price]
    return min(above) if above else None


def level_dict(level: Level) -> dict:
    return asdict(level)
