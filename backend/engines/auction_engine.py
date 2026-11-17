"""
Auction levels (version ``auction-2``): the volume profile of each swing (the move from a swing
low to the next swing high, or from a high to the next low), its value area and point of
control, and the opens and prior extremes drawn with them. Display only: nothing here is read
by signals or the executor. The rules and what they stand for are in
docs/reviews/auction-levels-spec.md.

The chart draws swings (``swing_ranges``, from hourly candles). The profiles of calendar
sessions (``sessions``: UTC days, weeks from Monday, months) are what version 1 drew and what
the declared studies measured; they stay here for those.

Profile of a swing or a session, from candles below the chart's:

1. Rows of ``step`` (a round number near a fixed fraction of price, STEP_FRACTION). Row k
   covers [base + k * step, base + (k + 1) * step).
2. Each candle's volume is split evenly between the rows its low-to-high range touches.
3. Point of control (POC): the row with the most volume (ties: the one nearest the middle
   of the session's range), reported at the row's centre.
4. Value area: start at the POC row; compare the two rows above with the two rows below,
   add the pair with more volume (ties go up), and repeat until the area holds 70% of the
   session's volume. VAH is the top of its highest row, VAL the bottom of its lowest.

A completed session's POC is "naked" until a later candle's range includes it; ``touched``
is the time of that candle.

Candle-built profiles are an approximation of tick-built ones: on BTC and ETH the daily
value area from 15m candles was within about 0.3% of the one from 1m candles.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

AUCTION_VERSION = "auction-2"
VALUE_SHARE = 0.70
DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS
_MONDAY_MS = 4 * DAY_MS               # 1970-01-05, the first Monday
STEP_FRACTION = {"day": 2e-4, "week": 5e-4, "month": 1e-3, "swing": 5e-4}
GRID_ROWS = 120                       # rows of the coarse grid a window of sessions shares
RANGE_ROWS = 60                       # rows of each swing's own histogram, from its low to its high
RANGE_PULLBACK = 0.5                  # a pullback of less than half a move does not end it, when the move then goes on

# The charts the layer is drawn on. All three read the same candles, so one answer serves them.
PLANS: Dict[str, dict] = {tf: {"interval": "1h", "days": 180} for tf in ("1h", "4h", "1d")}
INTERVAL_MS = {"15m": 900_000, "1h": 3_600_000}

# The retracement zone of major swings (studied in docs/reviews/fib-zone-study.md).
FIB_REVERSAL = 3.0                    # a swing is confirmed when price has come back 3 daily ATRs from it
FIB_MIN_LEG = 6.0                     # a leg counts once it is 6 daily ATRs tall
FIB_ZONE = (0.618, 0.66)


def session_starts(ts_ms, period: str) -> np.ndarray:
    """The start (ms) of the session each timestamp falls in."""
    ts = np.asarray(ts_ms, dtype=np.int64)
    if period == "day":
        return ts // DAY_MS * DAY_MS
    if period == "week":
        return (ts - _MONDAY_MS) // WEEK_MS * WEEK_MS + _MONDAY_MS
    if period == "month":
        return ts.astype("datetime64[ms]").astype("datetime64[M]").astype("datetime64[ms]").astype(np.int64)
    raise ValueError(f"unknown period {period!r}")


def session_end(start_ms: int, period: str) -> int:
    if period == "day":
        return int(start_ms) + DAY_MS
    if period == "week":
        return int(start_ms) + WEEK_MS
    if period == "month":
        nxt = np.datetime64(int(start_ms), "ms").astype("datetime64[M]") + np.timedelta64(1, "M")
        return int(nxt.astype("datetime64[ms]").astype(np.int64))
    raise ValueError(f"unknown period {period!r}")


def nice_step(raw: float) -> float:
    """The largest of 1, 2, 2.5 and 5 times a power of ten that is at most ``raw``."""
    if not (isinstance(raw, (int, float)) and math.isfinite(raw) and raw > 0):
        raise ValueError("step needs a positive price")
    unit = 10.0 ** math.floor(math.log10(raw))
    for m in (5.0, 2.5, 2.0):
        if m * unit <= raw * (1 + 1e-12):
            return m * unit
    return unit


def _decimals(step: float) -> int:
    return max(0, -math.floor(math.log10(step))) + 2


def profile(high, low, volume, step: float, base: Optional[float] = None,
            rows: Optional[int] = None) -> Tuple[float, np.ndarray]:
    """Volume by price row: (price of the bottom of row 0, volume per row)."""
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    volume = np.asarray(volume, dtype=np.float64)
    if base is None:
        base = math.floor(float(low.min()) / step) * step
    i0 = np.floor((low - base) / step).astype(np.int64)
    i1 = np.floor((high - base) / step).astype(np.int64)
    n = int(rows) if rows else int(i1.max()) + 1
    i0 = np.clip(i0, 0, n - 1)
    i1 = np.clip(i1, i0, n - 1)
    per_row = volume / (i1 - i0 + 1)
    edges = np.zeros(n + 1)
    np.add.at(edges, i0, per_row)
    np.add.at(edges, i1 + 1, -per_row)
    out = np.cumsum(edges)[:n]
    out[out < out.max() * 1e-12] = 0.0      # the running sum leaves rounding dust in rows no candle touched
    return base, out


def value_area(vol: np.ndarray, share: float = VALUE_SHARE) -> Tuple[int, int, int]:
    """(POC row, lowest row, highest row) of the value area of a profile."""
    n = len(vol)
    peak = np.flatnonzero(vol >= vol.max() * (1 - 1e-12))
    poc = int(peak[np.argmin(np.abs(peak - (n - 1) / 2))])
    lo = hi = poc
    held, wanted = float(vol[poc]), share * float(vol.sum())
    while held < wanted and (lo > 0 or hi < n - 1):
        up = float(vol[hi + 1:hi + 3].sum()) if hi < n - 1 else -1.0
        down = float(vol[max(lo - 2, 0):lo].sum()) if lo > 0 else -1.0
        if up >= down:
            hi = min(hi + 2, n - 1)
            held += up
        else:
            lo = max(lo - 2, 0)
            held += down
    return poc, lo, hi


def session_levels(high, low, volume, step: float) -> Tuple[float, float, float]:
    """(POC, VAH, VAL) of one session's candles, each kept inside the session's own range."""
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    base, rows = profile(high, low, volume, step)
    poc, lo, hi = value_area(rows)
    top, bottom = float(high.max()), float(low.min())
    return (min(max(base + (poc + 0.5) * step, bottom), top),
            min(base + (hi + 1) * step, top),
            max(base + lo * step, bottom))


def _arrays(candles: dict):
    ts = np.asarray(candles["timestamp"], dtype=np.int64)
    return (ts,) + tuple(np.asarray(candles[k], dtype=np.float64) for k in ("open", "high", "low", "close", "volume"))


def sessions(candles: dict, period: str, step: float, now_ms: float,
             grid: Optional[Tuple[float, float, int]] = None) -> List[dict]:
    """One entry per session with volume in ``candles`` (times in seconds, oldest first).

    A session the candles start inside is left out: its profile would be a part of it.
    ``grid`` = (bottom, row height, rows): also give each session its volume on that coarse
    grid as ``bins`` {"from": first row, "v": volume per row}, for a profile of several sessions.
    """
    ts, o, h, l, c, v = _arrays(candles)
    if not len(ts):
        return []
    starts = session_starts(ts, period)
    dec = _decimals(step)
    out: List[dict] = []
    for s in np.unique(starts):
        idx = np.flatnonzero(starts == s)
        if s < ts[0]:
            continue
        if not v[idx].sum() > 0:
            continue
        price, vah, val = session_levels(h[idx], l[idx], v[idx], step)
        end = session_end(int(s), period)
        live = end > now_ms
        touched = None
        if not live:
            later = np.flatnonzero((ts >= end) & (l <= price) & (h >= price))
            if later.size:
                touched = int(ts[later[0]] // 1000)
        row = {
            "start": int(s // 1000), "end": int(end // 1000), "live": bool(live),
            "open": float(o[idx[0]]), "high": float(h[idx].max()), "low": float(l[idx].min()), "close": float(c[idx[-1]]),
            "poc": round(price, dec), "vah": round(vah, dec), "val": round(val, dec),
            "touched": touched,
        }
        if grid is not None:
            g_base, g_step, g_rows = grid
            _, coarse = profile(h[idx], l[idx], v[idx], g_step, base=g_base, rows=g_rows)
            filled = np.flatnonzero(coarse > 0)
            row["bins"] = {"from": int(filled[0]), "v": coarse[filled[0]:filled[-1] + 1]}
        out.append(row)
    return out


def reference_levels(daily: Optional[dict], period: str, now_ms: float) -> Dict[str, float]:
    """Opens and prior extremes from daily candles (the live day included).

    Days as sessions: today's open, the previous day's high and low, this week's and this
    month's open. Weeks as sessions: this week's open, the previous week's high and low, this
    month's open. A level whose day is not in ``daily`` is left out.
    """
    if not daily or not len(daily.get("timestamp", [])):
        return {}
    ts = np.asarray(daily["timestamp"], dtype=np.int64)
    o, h, l = (np.asarray(daily[k], dtype=np.float64) for k in ("open", "high", "low"))
    today = int(now_ms) // DAY_MS * DAY_MS
    week = int(session_starts([now_ms], "week")[0])
    month = int(session_starts([now_ms], "month")[0])

    def at(t: int) -> Optional[int]:
        i = int(np.searchsorted(ts, t))
        return i if i < len(ts) and ts[i] == t else None

    out: Dict[str, float] = {}
    for key, t in (("w_open", week), ("m_open", month)):
        i = at(t)
        if i is not None:
            out[key] = float(o[i])
    if period == "day":
        i, j = at(today), at(today - DAY_MS)
        if i is not None:
            out["d_open"] = float(o[i])
        if j is not None:
            out["pd_high"], out["pd_low"] = float(h[j]), float(l[j])
    else:
        prev = (ts >= week - WEEK_MS) & (ts < week)
        if prev.any():
            out["pw_high"], out["pw_low"] = float(h[prev].max()), float(l[prev].min())
    return out


def initial_balance(candles: dict, now_ms: float) -> Dict[str, float]:
    """High and low of the running UTC day's first hour (the Initial Balance), once it has a candle."""
    ts, _, h, l, _, _ = _arrays(candles)
    today = int(now_ms) // DAY_MS * DAY_MS
    first = (ts >= today) & (ts < today + 3_600_000)
    return {"ib_high": float(h[first].max()), "ib_low": float(l[first].min())} if first.any() else {}


def swings(high: np.ndarray, low: np.ndarray, atr: np.ndarray, k: float = FIB_REVERSAL) -> list:
    """Swing highs and lows of daily candles: (kind, price, its day, the day it was confirmed).
    A high is confirmed on the first later day whose low is k ATRs (the day before's) under it; lows mirror."""
    n = len(high)
    i0 = next((i for i in range(n) if np.isfinite(atr[i])), n)
    if i0 >= n - 1:
        return []
    out, mode = [], None
    hi, hi_i, lo, lo_i = high[i0], i0, low[i0], i0
    for i in range(i0 + 1, n):
        a = atr[i - 1]
        if mode != "down" and high[i] > hi:
            hi, hi_i = high[i], i
        if mode != "up" and low[i] < lo:
            lo, lo_i = low[i], i
        if mode != "down" and hi_i < i and low[i] <= hi - k * a:
            out.append(("H", float(hi), hi_i, i))
            mode = "down"
            j = hi_i + 1 + int(np.argmin(low[hi_i + 1:i + 1]))
            lo, lo_i = low[j], j
        elif mode != "up" and lo_i < i and high[i] >= lo + k * a:
            out.append(("L", float(lo), lo_i, i))
            mode = "up"
            j = lo_i + 1 + int(np.argmax(high[lo_i + 1:i + 1]))
            hi, hi_i = high[j], j
    # A first "swing" on the very first day is only where the candles begin, not a turn in price.
    return out[1:] if out and out[0][2] == i0 else out


def fib_zones(daily: Optional[dict]) -> List[dict]:
    """The 0.618 to 0.66 retracement band of each live major leg, from daily candles (the live day included).

    A leg runs from the last confirmed swing low to the highest price since (an up-leg; the band is where a
    pullback of it would be), or from the last confirmed swing high to the lowest price since (a down-leg). It is
    live until price trades beyond its start, and shown once it is FIB_MIN_LEG daily ATRs tall. ``touched``: price
    has traded into the band since the leg's extreme. Times in seconds."""
    if not daily or len(daily.get("timestamp", [])) < 30:
        return []
    from engines.levels_engine import wilder_atr
    ts = np.asarray(daily["timestamp"], dtype=np.int64)
    hi, lo, cl = (np.asarray(daily[k], dtype=np.float64) for k in ("high", "low", "close"))
    atr = wilder_atr(hi, lo, cl)
    unit = atr[-2] if len(atr) > 1 else np.nan           # the last finished day's ATR
    if not np.isfinite(unit) or unit <= 0:
        return []
    piv = swings(hi, lo, atr)
    out = []
    for kind, s in (("L", 1), ("H", -1)):
        mine = [p for p in piv if p[0] == kind]
        if not mine:
            continue
        _, base, at, _ = mine[-1]
        up, down = (hi, lo) if s > 0 else (-lo, -hi)        # a down-leg is an up-leg of the negated prices
        b = s * base
        if at + 1 < len(ts) and down[at + 1:].min() < b:
            continue                                         # price has traded beyond the leg's start
        k = at + int(np.argmax(up[at:]))
        top = float(up[k])
        height = top - b
        if height < FIB_MIN_LEG * unit:
            continue
        first, second = (top - d * height for d in FIB_ZONE)
        touched = bool(k + 1 < len(ts) and down[k + 1:].min() <= first)
        out.append({"direction": s, "base": float(base), "base_time": int(ts[at] // 1000),
                    "extreme": s * top, "extreme_time": int(ts[k] // 1000),
                    "from": s * first, "to": s * second, "touched": touched})
    return out


def merge_moves(points: list, share: float = RANGE_PULLBACK) -> list:
    """Swing points (kind "L" or "H", price, ...) in turn, without the pullbacks that did not end a move.

    A rise from a low to a high, a dip, then a higher high: when the dip gave back less than ``share`` of the rise,
    the dip's two points are dropped and the rise runs on to the higher high. Falls mirror. A merged move is
    measured again against the pullback after it, and the move before it against the merged one."""
    pts = list(points)
    i = 0
    while i + 3 < len(pts):
        a, b, c, d = pts[i:i + 4]
        s = 1 if a[0] == "L" else -1
        size, back, beyond = s * (b[1] - a[1]), s * (b[1] - c[1]), s * (d[1] - b[1])
        if size > 0 and back < share * size and beyond > 0:
            del pts[i + 1:i + 3]
            i = max(i - 2, 0)
        else:
            i += 1
    return pts


def swing_ranges(candles: dict, daily: Optional[dict], step: float, now_ms: float) -> List[dict]:
    """The volume profile of each move inside ``candles`` (hourly, oldest first): every rise from a swing low to
    the next swing high, every fall from a high to the next low, and the move still running from the last swing.

    Swings are the daily ones the retracement zone uses (``swings``: a high is a swing once price has come back
    FIB_REVERSAL daily ATRs from it), with the price furthest from the last swing as the running move's end, and
    without the pullbacks that did not end a move (``merge_moves``). A move starts at the candle with the lowest
    low of the swing low's day (the highest high of a swing high's day) and ends at the candle of the next swing;
    the running move ends at the last candle and is ``live``. A move the candles start inside is left out: its
    profile would be a part of it.

    Each entry: ``direction`` (1 up, -1 down), ``start`` and ``end`` (seconds; ``end`` is the close of its last
    candle), ``low`` and ``high``, ``poc``, ``vah`` and ``val`` (the same rule as a session's), and ``bins``
    {"low", "step", "v"}: its volume on RANGE_ROWS rows from low to high, in whole parts per thousand of the
    fullest row.
    """
    if not daily or len(daily.get("timestamp", [])) < 30:
        return []
    from engines.levels_engine import wilder_atr
    ts, _, h, l, _, v = _arrays(candles)
    if len(ts) < 2:
        return []
    dts = np.asarray(daily["timestamp"], dtype=np.int64)
    dh, dl, dc = (np.asarray(daily[k], dtype=np.float64) for k in ("high", "low", "close"))
    piv = swings(dh, dl, wilder_atr(dh, dl, dc))
    if not piv:
        return []
    kind, _, day, _ = piv[-1]
    if day + 1 < len(dts):                                   # where the running move has reached so far
        j = day + 1 + int(np.argmax(dh[day + 1:]) if kind == "L" else np.argmin(dl[day + 1:]))
        piv = piv + [("H", float(dh[j]), j, j) if kind == "L" else ("L", float(dl[j]), j, j)]
        piv = merge_moves(piv)[:-1]                          # its end is the last candle, not that price
    else:
        piv = merge_moves(piv)
    span = int(np.median(np.diff(ts)))

    def anchor(kind: str, day: int) -> Optional[int]:
        idx = np.flatnonzero((ts >= dts[day]) & (ts < dts[day] + DAY_MS))
        if not idx.size:
            return None
        return int(idx[np.argmax(h[idx])] if kind == "H" else idx[np.argmin(l[idx])])

    marks = [(kind, anchor(kind, day)) for kind, _, day, _ in piv]
    legs = [(1 if k0 == "L" else -1, a, b, False) for (k0, a), (_, b) in zip(marks, marks[1:])
            if a is not None and b is not None and b > a]
    kind, a = marks[-1]
    if a is not None and a < len(ts) - 1:
        legs.append((1 if kind == "L" else -1, a, len(ts) - 1, True))
    dec = _decimals(step)
    out: List[dict] = []
    for direction, a, b, live in legs:
        hh, ll, vv = h[a:b + 1], l[a:b + 1], v[a:b + 1]
        if not vv.sum() > 0:
            continue
        poc, vah, val = session_levels(hh, ll, vv, step)
        low, high = float(ll.min()), float(hh.max())
        r_step = (high - low) / RANGE_ROWS or step
        _, rows = profile(hh, ll, vv, r_step, base=low, rows=RANGE_ROWS)
        out.append({
            "direction": direction, "start": int(ts[a] // 1000), "end": int((ts[b] + span) // 1000), "live": live,
            "low": round(low, dec), "high": round(high, dec),
            "poc": round(poc, dec), "vah": round(vah, dec), "val": round(val, dec),
            "bins": {"low": low, "step": r_step, "v": [int(x) for x in np.rint(rows * 1000 / (rows.max() or 1.0))]},
        })
    return out


def build(candles: dict, daily: Optional[dict], now_ms: float) -> dict:
    """The Value layer of a coin's charts: the profile of each swing, the reference levels (the day's and the
    week's; the chart picks its own) and the retracement zone."""
    ts, _, _, _, c, _ = _arrays(candles)
    step = nice_step(float(c[-1]) * STEP_FRACTION["swing"])
    dec = _decimals(step)
    refs = {**reference_levels(daily, "week", now_ms), **reference_levels(daily, "day", now_ms), **initial_balance(candles, now_ms)}
    return {
        "version": AUCTION_VERSION,
        "interval": PLANS["1d"]["interval"],
        "as_of": int(now_ms // 1000),
        "from": int(ts[0] // 1000),
        "step": step,
        "ranges": swing_ranges(candles, daily, step, now_ms),
        "levels": {k: round(p, dec) for k, p in refs.items()},
        "fib": [{**z, **{k: round(z[k], dec) for k in ("base", "extreme", "from", "to")}} for z in fib_zones(daily)],
    }
