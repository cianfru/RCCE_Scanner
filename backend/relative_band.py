"""A coin against BTC: the ratio of their daily closes with the weekly band drawn on the ratio.

The band is band_stretch's (20-week SMA and 21-week EMA, weeks starting Thursday, the week under way counted at the
day's close), applied to coin / BTC instead of the coin's price. Above the band: the coin has been beating BTC as a
trend; under it: lagging.

A **cross up** is a day the ratio closes above its band after at least GAP_DAYS days without closing above it; a
**cross down** is the mirror (under, after GAP_DAYS days not under). Used by the scanner's list, the coin page and
the declared study (docs/reviews/relative-band-study.md).
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np

import band_stretch

GAP_DAYS = 14
SPARK_DAYS = 90
SPARK_STEP = 2


def align(days_a: np.ndarray, close_a: np.ndarray, days_b: np.ndarray, close_b: np.ndarray):
    """The days both consecutive daily series cover, and the ratio a / b on them."""
    lo, hi = max(days_a[0], days_b[0]), min(days_a[-1], days_b[-1])
    if hi < lo:
        return np.array([], dtype=np.int64), np.array([])
    a = close_a[(days_a >= lo) & (days_a <= hi)]
    b = close_b[(days_b >= lo) & (days_b <= hi)]
    return np.arange(lo, hi + 1, dtype=np.int64), a / b


def readings(days: np.ndarray, ratio: np.ndarray) -> Dict[str, np.ndarray]:
    """Per day: the band's lower and upper edge on the ratio, and the state (1 above, 0 inside, -1 under, nan
    while the band is not yet defined)."""
    sma, ema = band_stretch.band_edges(days, ratio)
    lo, hi = np.fmin(sma, ema), np.fmax(sma, ema)
    state = np.where(np.isnan(lo), np.nan, np.where(ratio > hi, 1.0, np.where(ratio < lo, -1.0, 0.0)))
    return {"lo": lo, "hi": hi, "state": state}


def crosses(state: np.ndarray, gap: int = GAP_DAYS) -> Dict[str, List[int]]:
    """Indexes of the cross-up and cross-down days (see the module doc). A day needs `gap` defined days before it."""
    up, down = [], []
    for i in range(gap, len(state)):
        w = state[i - gap:i]
        if np.isnan(state[i]) or np.isnan(w).any():
            continue
        if state[i] == 1 and not (w == 1).any():
            up.append(i)
        elif state[i] == -1 and not (w == -1).any():
            down.append(i)
    return {"up": up, "down": down}


def summary(days: np.ndarray, ratio: np.ndarray) -> Optional[dict]:
    """What the scanner and the coin page show: today's state, the last cross and its day, the ratio's change over
    30 and 90 days, and a small sparkline of the last SPARK_DAYS days (ratio and band edges, as a share of the
    last ratio). None while the band is not defined."""
    if len(ratio) < 2:
        return None
    rd = readings(days, ratio)
    if np.isnan(rd["state"][-1]):
        return None
    cx = crosses(rd["state"])
    last_up = cx["up"][-1] if cx["up"] else None
    last_down = cx["down"][-1] if cx["down"] else None
    trend, since = None, None
    if last_up is not None and (last_down is None or last_up > last_down):
        trend, since = "up", int(days[last_up])
    elif last_down is not None:
        trend, since = "down", int(days[last_down])
    k = slice(max(0, len(ratio) - SPARK_DAYS), len(ratio))
    ref = float(ratio[-1])

    def chg(n):
        return None if len(ratio) <= n else round(float(100 * (ratio[-1] / ratio[-1 - n] - 1)), 1)

    def sp(x):
        return [None if not np.isfinite(v) else round(float(v / ref), 4) for v in x[k][::-1][::SPARK_STEP][::-1]]
    return {"state": {1.0: "above", 0.0: "inside", -1.0: "under"}[float(rd["state"][-1])], "trend": trend,
            "since": since, "day": int(days[-1]), "chg30": chg(30), "chg90": chg(90),
            "spark": {"r": sp(ratio), "lo": sp(rd["lo"]), "hi": sp(rd["hi"])}}


def history(days: np.ndarray, ratio: np.ndarray, n_days: int = 365) -> dict:
    """The coin page's chart: the last n_days of the ratio and its band edges, and the cross days in that span."""
    rd = readings(days, ratio)
    cx = crosses(rd["state"])
    start = max(0, len(days) - n_days)
    keep = lambda xs: [int(days[i]) for i in xs if i >= start]
    num = lambda x: [None if not np.isfinite(v) else float(f"{v:.6g}") for v in x[start:]]
    return {"days": [int(d) for d in days[start:]], "ratio": num(ratio), "lo": num(rd["lo"]), "hi": num(rd["hi"]),
            "up": keep(cx["up"]), "down": keep(cx["down"])}


def series(timestamps_ms: Iterable[float], closes: Iterable[float]):
    """Consecutive daily closes (band_stretch.daily_series)."""
    return band_stretch.daily_series(timestamps_ms, closes)
