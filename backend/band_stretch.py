"""Band stretch: how far price is from the weekly band, scaled to the coin ("band z").

The reading of the TradingView script (tradingview/reflex_band_stretch.pine) and of the stretch-at-tops study
(docs/reviews/stretch-tops-study.md), computed the same way:

- the band: the 20-week SMA and the 21-week EMA of weekly closes (weeks start Thursday 00:00 UTC, as Hyperliquid's),
  the week under way counted at the day's close, the EMA seeded with the SMA of its first 21 weeks; its mid is their
  average;
- stretch: the log of the close over the band mid;
- band z (the study's scaling A): stretch over its root mean square across the last 730 days (all of it while there
  is less, shown from 180 days);
- volatility units (the study's C) and the divergence mark (D) are recorded for a fair test on tops after the study.

Context, not a signal: the engine does not read it. The study's guide for band z is 1.61 (shown as the 1.6 line).
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np

SMA_WEEKS, EMA_WEEKS = 20, 21
RMS_DAYS = 730
MIN_DAYS = 180                 # band z is shown once 180 days of stretch exist (as the script)
VOL_DAYS = 730
MIN_VOL_DAYS = 365
LINE = 1.6                     # the line the app draws: the study's guide for band z, 1.61, rounded
GUIDE_A = 1.61                 # the study's guides (95th percentile of its calibration coins' days)
GUIDE_C = 9.20
DIV_HIGH, DIV_SKIP = 365, 30   # the divergence mark: a new 365-day closing high, a stretched day 30-365 days back
DAY_S = 86_400


def band_mid(days: np.ndarray, close: np.ndarray) -> np.ndarray:
    """The band's mid each day (days: whole days since 1 January 1970, a Thursday, one per row, consecutive)."""
    k = 2.0 / (EMA_WEEKS + 1)
    weeks: List[float] = []
    ema_done = None
    mid = np.full(len(close), np.nan)
    for i in range(len(close)):
        if i > 0 and days[i] // 7 != days[i - 1] // 7:
            weeks.append(float(close[i - 1]))
            n = len(weeks)
            if n == EMA_WEEKS:
                ema_done = sum(weeks) / n
            elif n > EMA_WEEKS:
                ema_done = weeks[-1] * k + ema_done * (1 - k)
        n = len(weeks)
        if n < SMA_WEEKS - 1 or n < EMA_WEEKS - 1:
            continue
        sma = (close[i] + sum(weeks[n - (SMA_WEEKS - 1):])) / SMA_WEEKS
        ema = close[i] * k + ema_done * (1 - k) if n >= EMA_WEEKS else (sum(weeks) + close[i]) / EMA_WEEKS
        mid[i] = (sma + ema) / 2
    return mid


def _rolling_mean(x: np.ndarray, window: int) -> tuple:
    """Mean of the finite values among the last `window` (the day included), and how many there were."""
    ok = np.isfinite(x)
    cs = np.cumsum(np.where(ok, x, 0.0))
    cn = np.cumsum(ok.astype(float))
    cs = cs - np.concatenate([np.zeros(window), cs[:-window]])[: len(x)]
    cn = cn - np.concatenate([np.zeros(window), cn[:-window]])[: len(x)]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cn > 0, cs / np.maximum(cn, 1), np.nan), cn


def readings(days: np.ndarray, close: np.ndarray) -> Dict[str, np.ndarray]:
    """Per day: the band mid, percent from it, band z (a), volatility units (c); nan where not yet defined."""
    days = np.asarray(days, dtype=np.int64)
    close = np.asarray(close, dtype=float)
    mid = band_mid(days, close)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.log(close / mid)
    ms, n_s = _rolling_mean(s * s, RMS_DAYS)
    have_s = np.cumsum(np.isfinite(s))
    rms = np.sqrt(ms)
    r = np.concatenate([[np.nan], np.diff(np.log(close))])
    m1, _ = _rolling_mean(r, VOL_DAYS)
    m2, _ = _rolling_mean(r * r, VOL_DAYS)
    vol = np.sqrt(np.maximum(m2 - m1 * m1, 0.0))
    have_r = np.cumsum(np.isfinite(r))
    with np.errstate(invalid="ignore", divide="ignore"):
        a = np.where((have_s >= MIN_DAYS) & (rms > 0), s / rms, np.nan)
        c = np.where((have_r >= MIN_VOL_DAYS) & (vol > 0) & np.isfinite(s), s / vol, np.nan)
        pct = 100 * (close / mid - 1)
    return {"mid": mid, "pct": pct, "a": a, "c": c}


def divergence_at(close: np.ndarray, x: np.ndarray, guide: float, t: int) -> Optional[bool]:
    """The divergence mark on day t: a new DIV_HIGH-day closing high; some day DIV_SKIP to DIV_HIGH days back at or
    above the guide; today's reading above 0 and under the highest reading of those days. None when unknown."""
    if t < DIV_HIGH - 1 or not np.isfinite(x[t]):
        return None
    if close[t] < close[t - DIV_HIGH + 1: t + 1].max() or x[t] <= 0:
        return False
    w = x[max(0, t - DIV_HIGH): t - DIV_SKIP + 1]
    w = w[np.isfinite(w)]
    return bool(len(w) and w.max() >= guide and x[t] < w.max())


def _num(v) -> Optional[float]:
    return round(float(v), 4) if v is not None and np.isfinite(v) else None


def on_days(days: np.ndarray, close: np.ndarray, wanted: Iterable[int]) -> Dict[int, dict]:
    """The readings on each wanted day present in the series (closes up to and including it only)."""
    days = np.asarray(days, dtype=np.int64)
    close = np.asarray(close, dtype=float)
    rd = readings(days, close)
    pos = {int(d): i for i, d in enumerate(days)}
    out = {}
    for d in wanted:
        i = pos.get(int(d))
        if i is None or not np.isfinite(rd["mid"][i]):
            continue
        da = divergence_at(close, rd["a"], GUIDE_A, i)
        dc = divergence_at(close, rd["c"], GUIDE_C, i)
        out[int(d)] = {"close": float(close[i]), "mid": float(rd["mid"][i]), "pct": _num(rd["pct"][i]),
                       "a": _num(rd["a"][i]), "c": _num(rd["c"][i]), "d_a": da, "d_c": dc}
    return out


def daily_series(timestamps_ms: Iterable[float], closes: Iterable[float]):
    """Closes on consecutive whole days (a missing day takes the close before it)."""
    by_day = {}
    for t, c in zip(timestamps_ms, closes):
        if c is not None and float(c) > 0:
            by_day[int(float(t) // 1000 // DAY_S)] = float(c)
    if not by_day:
        return np.array([], dtype=np.int64), np.array([])
    days = np.arange(min(by_day), max(by_day) + 1, dtype=np.int64)
    out, last = [], None
    for d in days:
        last = by_day.get(int(d), last)
        out.append(last)
    return days, np.array(out, dtype=float)


def aggregate(day: int, per_coin: Dict[str, dict]) -> Optional[list]:
    """One market row: [day, coins with band z, coins at or above the line, median band z]."""
    vals = [v["a"] for v in per_coin.values() if v.get("a") is not None]
    if not vals:
        return None
    return [int(day), len(vals), sum(1 for v in vals if v >= LINE), round(float(np.median(vals)), 3)]


# ---------------------------------------------------------------------------------------------------------- replay
def bar_state(days: np.ndarray, close: np.ndarray) -> Dict[str, np.ndarray]:
    """For each day of a daily series, what a bar on that day can know before the day closes: the weekly closes of
    the completed weeks before the day's week (their count, the sum of the last SMA_WEEKS - 1, the EMA through them,
    and their sum while fewer than EMA_WEEKS), and the root mean square of the daily stretch over the RMS_DAYS
    completed days before the day (with how many there were). band_z_at() then reads band z at any price that day
    (docs/reviews/band-exit-study.md)."""
    days = np.asarray(days, dtype=np.int64)
    close = np.asarray(close, dtype=float)
    n = len(close)
    k = 2.0 / (EMA_WEEKS + 1)
    nw = np.zeros(n, dtype=np.int64)
    s_sma = np.full(n, np.nan)
    ema = np.full(n, np.nan)
    s_all = np.full(n, np.nan)
    weeks: List[float] = []
    ema_done = None
    for i in range(n):
        if i > 0 and days[i] // 7 != days[i - 1] // 7:
            weeks.append(float(close[i - 1]))
            m = len(weeks)
            if m == EMA_WEEKS:
                ema_done = sum(weeks) / m
            elif m > EMA_WEEKS:
                ema_done = weeks[-1] * k + ema_done * (1 - k)
        m = len(weeks)
        nw[i] = m
        if m >= SMA_WEEKS - 1:
            s_sma[i] = sum(weeks[m - (SMA_WEEKS - 1):])
        if m >= EMA_WEEKS:
            ema[i] = ema_done
        if m == EMA_WEEKS - 1:
            s_all[i] = sum(weeks)
    rd = readings(days, close)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.log(close / rd["mid"])
    ms, cnt = _rolling_mean(s * s, RMS_DAYS)
    rms_before = np.concatenate([[np.nan], np.sqrt(ms[:-1])]) if n else ms
    cnt_before = np.concatenate([[0.0], cnt[:-1]]) if n else cnt
    return {"days": days, "nw": nw, "s_sma": s_sma, "ema": ema, "s_all": s_all, "rms": rms_before, "cnt": cnt_before}


def band_z_at(state: Dict[str, np.ndarray], day: int, price: float) -> Optional[float]:
    """Band z on `day` at `price` (the day's close so far): the band with the week under way at that price, over the
    RMS of the completed days before the day. None when the band or 180 days of stretch are not there yet."""
    days = state["days"]
    if not len(days) or price is None or price <= 0:
        return None
    i = int(day - days[0])
    if i < 0 or i >= len(days) or days[i] != day:
        return None
    m = state["nw"][i]
    if m < SMA_WEEKS - 1 or m < EMA_WEEKS - 1 or state["cnt"][i] < MIN_DAYS or not state["rms"][i] > 0:
        return None
    k = 2.0 / (EMA_WEEKS + 1)
    sma = (price + state["s_sma"][i]) / SMA_WEEKS
    ema = price * k + state["ema"][i] * (1 - k) if m >= EMA_WEEKS else (state["s_all"][i] + price) / EMA_WEEKS
    mid = (sma + ema) / 2
    return float(np.log(price / mid) / state["rms"][i])
