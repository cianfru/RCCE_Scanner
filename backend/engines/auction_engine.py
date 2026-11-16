"""
Auction levels (version ``auction-1``): the volume profile of each session, its value area and
point of control, the points of control price has not come back to, and the opens and prior
extremes drawn with them. Display only: nothing here is read by signals or the executor.
The rules and what they stand for are in docs/reviews/auction-levels-spec.md.

Sessions are UTC: a day starts at 00:00, a week on Monday 00:00, a month on its first day.

Profile of a session, from candles one step below the chart's (15m for days, 1h for weeks
and months):

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

AUCTION_VERSION = "auction-1"
VALUE_SHARE = 0.70
DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS
_MONDAY_MS = 4 * DAY_MS               # 1970-01-05, the first Monday
STEP_FRACTION = {"day": 2e-4, "week": 5e-4, "month": 1e-3}
GRID_ROWS = 120                       # rows of the coarse grid behind the chart's side histogram

# Chart timeframe -> the candles read and the sessions built from them.
PLANS: Dict[str, dict] = {
    "4h": {"interval": "15m", "days": 30, "period": "day", "outer": "week"},
    "1d": {"interval": "1h", "days": 180, "period": "week", "outer": "month"},
}
INTERVAL_MS = {"15m": 900_000, "1h": 3_600_000}


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
        base, rows = profile(h[idx], l[idx], v[idx], step)
        poc, lo, hi = value_area(rows)
        high, low = float(h[idx].max()), float(l[idx].min())
        price = min(max(base + (poc + 0.5) * step, low), high)
        end = session_end(int(s), period)
        live = end > now_ms
        touched = None
        if not live:
            later = np.flatnonzero((ts >= end) & (l <= price) & (h >= price))
            if later.size:
                touched = int(ts[later[0]] // 1000)
        row = {
            "start": int(s // 1000), "end": int(end // 1000), "live": bool(live),
            "open": float(o[idx[0]]), "high": high, "low": low, "close": float(c[idx[-1]]),
            "poc": round(price, dec),
            "vah": round(min(base + (hi + 1) * step, high), dec),
            "val": round(max(base + lo * step, low), dec),
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


def build(candles: dict, daily: Optional[dict], timeframe: str, now_ms: float) -> dict:
    """The Value layer of one chart: sessions with their value areas, the outer period's
    sessions (weeks under days, months under weeks) and the reference levels."""
    plan = PLANS[timeframe]
    ts, _, h, l, c, v = _arrays(candles)
    price = float(c[-1])
    step = nice_step(price * STEP_FRACTION[plan["period"]])
    outer_step = nice_step(price * STEP_FRACTION[plan["outer"]])
    g_low, g_high = float(l.min()), float(h.max())
    g_step = (g_high - g_low) / GRID_ROWS or step
    inner = sessions(candles, plan["period"], step, now_ms, grid=(g_low, g_step, GRID_ROWS))
    # The side histogram only compares rows, so bins go out as whole parts per million of the window's volume.
    total = sum(float(s["bins"]["v"].sum()) for s in inner) or 1.0
    for s in inner:
        s["bins"]["v"] = [int(x) for x in np.rint(s["bins"]["v"] * 1e6 / total)]
    outer = [{k: s[k] for k in ("start", "end", "live", "poc", "vah", "val", "touched")}
             for s in sessions(candles, plan["outer"], outer_step, now_ms)]
    dec = _decimals(step)
    return {
        "version": AUCTION_VERSION,
        "timeframe": timeframe,
        "interval": plan["interval"],
        "period": plan["period"],
        "outer_period": plan["outer"],
        "as_of": int(now_ms // 1000),
        "from": int(ts[0] // 1000),
        "step": step,
        "sessions": inner,
        "outer": outer,
        "grid": {"low": g_low, "step": g_step, "rows": GRID_ROWS},
        "levels": {k: round(p, dec) for k, p in reference_levels(daily, plan["period"], now_ms).items()},
    }
