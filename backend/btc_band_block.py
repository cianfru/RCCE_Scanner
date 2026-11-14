"""The BTC weekly-band entry block (docs/reviews/executor-gap-study.md, approved by the owner on 14 November 2026).

No new long while BTC's weekly close has been under the mid of its weekly band (the 20-week SMA and the 21-week EMA,
averaged) for at least CONSECUTIVE_WEEKS completed weeks. It is the rule the backtest position manager and the
executor-gap study's X2 used (backtest/larsson_study._compute_bmsb_filter), on weeks that run Monday to Sunday,
from BTC's stored daily closes. Positions already open are not touched; their exits run as before.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

CONSECUTIVE_WEEKS = 2
SMA_WEEKS, EMA_WEEKS = 20, 21
DAY_S = 86_400
SUNDAY = 3                       # day % 7 for Sunday (day 0 = Thursday 1 January 1970)
_cache: dict = {}


def weekly_closes(ts_s: List[int], closes: List[float]) -> List[Tuple[int, float]]:
    """(Sunday's day number, close) for each completed Monday-to-Sunday week, from daily candles given by their open
    time in seconds, completed days only."""
    by_day = {int(t) // DAY_S: float(c) for t, c in zip(ts_s, closes)}
    return [(d, by_day[d]) for d in sorted(by_day) if d % 7 == SUNDAY]


def state(weeks: List[Tuple[int, float]]) -> Optional[dict]:
    """The block's state after the last completed week: blocked, weeks closed under the mid in a row, the mid and
    the last weekly close, and the Sunday the run under started. None with fewer than EMA_WEEKS weeks."""
    if len(weeks) < EMA_WEEKS:
        return None
    close = np.array([c for _, c in weeks], dtype=float)
    n = len(close)
    sma = np.full(n, np.nan)
    for i in range(SMA_WEEKS - 1, n):
        sma[i] = close[i - SMA_WEEKS + 1:i + 1].mean()
    ema = np.full(n, np.nan)
    ema[EMA_WEEKS - 1] = close[:EMA_WEEKS].mean()
    k = 2 / (EMA_WEEKS + 1)
    for i in range(EMA_WEEKS, n):
        ema[i] = k * close[i] + (1 - k) * ema[i - 1]
    mid = (sma + ema) / 2
    below = 0
    for i in range(n):
        below = below + 1 if np.isfinite(mid[i]) and close[i] < mid[i] else 0
    since = weeks[n - below][0] if below else None
    return {"blocked": below >= CONSECUTIVE_WEEKS, "weeks_below": below, "mid": round(float(mid[-1]), 2),
            "close": round(float(close[-1]), 2), "week": weeks[-1][0], "since": since}


def current(store=None, now: Optional[float] = None) -> Optional[dict]:
    """The block's state from the stored BTC daily candles, cached until a new day closes. None without data."""
    now = time.time() if now is None else now
    try:
        if store is None:
            from data_fetcher import _ohlcv_store as store
        import setup_map
        ts, cs = [], []
        for sym in ("BTC/USDT", "BTC/USDC"):
            ts, cs = setup_map.closes(store.get(sym, "1d"), "1d", now)
            if cs:
                break
    except Exception as exc:
        logger.warning("BTC band block: no BTC daily closes (%s)", exc)
        return None
    if not cs:
        return None
    key = ts[-1]
    if _cache.get("key") == key:
        return _cache["state"]
    # setup_map.closes gives close times; the daily candle's own day is the one before
    st = state(weekly_closes([t - DAY_S for t in ts], cs))
    _cache.update(key=key, state=st)
    return st


def blocked(store=None, now: Optional[float] = None) -> bool:
    """True while the block is on. Without BTC data the block stays off (as in the backtest)."""
    st = current(store, now)
    return bool(st and st["blocked"])
