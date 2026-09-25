"""
Larsson Line (v2.51) — Python / numpy port
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Four EMAs of the close (32/35/50/58). The ribbon is:

    gold  when e32 > e35 > e50 > e58   (full bullish order)
    blue  when e32 < e35 < e50 < e58   (full bearish order)
    grey  otherwise                    (no trend; never actionable)

Flips are defined on the *last actionable* (non-grey) state, so
gold -> grey -> gold and blue -> grey -> blue emit nothing:

    gold_flip  bar is gold and the last non-grey state before it was blue
    blue_flip  bar is blue and the last non-grey state before it was gold

The first grey bar after a gold run is reported as ``grey_after_gold``, a
warning only.

Research use, shadow only. Designed for 1D crypto; nothing in the live
signal path reads it. Mirrors the ``cto_engine`` public API shape so chart,
scanner and replay can share it later under their own key.

Public API
----------
    compute_larsson_series(close, timestamps) -> dict
    compute_larsson_snapshot(ohlcv, timeframe, as_of_ms) -> dict
"""
from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np

LARSSON_VERSION = "larsson-2.51"
LENGTHS = (32, 35, 50, 58)
READY_BARS = 600            # EMAs have infinite memory; below this TradingView can disagree
TF_MS = {"4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}

GOLD, BLUE, GREY = "gold", "blue", "grey"


def ema(close: np.ndarray, n: int) -> np.ndarray:
    """Pine ``ta.ema``: SMA of the first n values as the seed, then alpha = 2/(n+1)."""
    close = np.asarray(close, dtype=np.float64)
    out = np.full(len(close), np.nan)
    if len(close) < n:
        return out
    out[n - 1] = close[:n].mean()
    k = 2.0 / (n + 1.0)
    for i in range(n, len(close)):
        out[i] = close[i] * k + out[i - 1] * (1.0 - k)
    return out


def compute_larsson_series(close, timestamps) -> dict:
    """Per-bar ribbon state and flips.

    Returns arrays (``e32``, ``e35``, ``e50``, ``e58``) and per-bar lists:
    ``state`` (gold/blue/grey, or None during EMA warm-up), ``last_actionable``
    (last non-grey state up to and including the bar), ``flip`` (gold/blue on a
    flip bar, else None), ``grey_after_gold`` and ``bars_since_flip``.
    """
    close = np.asarray(close, dtype=np.float64)
    timestamps = np.asarray(timestamps, dtype=np.float64)
    if len(close) != len(timestamps):
        raise ValueError("close and timestamps must have matching lengths")
    if len(close) and (not np.all(np.isfinite(close)) or np.any(close <= 0)):
        raise ValueError("Larsson Line requires finite, positive closes")
    e32, e35, e50, e58 = (ema(close, n) for n in LENGTHS)

    n = len(close)
    state = [None] * n
    last_actionable = [None] * n
    flip = [None] * n
    grey_after_gold = [False] * n
    bars_since_flip = [None] * n
    lat: Optional[str] = None
    since: Optional[int] = None
    for i in range(n):
        if np.isnan(e58[i]):
            continue
        if e32[i] > e35[i] > e50[i] > e58[i]:
            s = GOLD
        elif e32[i] < e35[i] < e50[i] < e58[i]:
            s = BLUE
        else:
            s = GREY
        state[i] = s
        if s == GOLD and lat == BLUE or s == BLUE and lat == GOLD:
            flip[i] = s
            since = 0
        elif since is not None:
            since += 1
        grey_after_gold[i] = s == GREY and i > 0 and state[i - 1] == GOLD
        if s != GREY:
            lat = s
        last_actionable[i] = lat
        bars_since_flip[i] = since
    return {
        "timestamps": timestamps, "e32": e32, "e35": e35, "e50": e50, "e58": e58,
        "state": state, "last_actionable": last_actionable, "flip": flip,
        "grey_after_gold": grey_after_gold, "bars_since_flip": bars_since_flip,
    }


def _closed(ohlcv: dict, timeframe: str, as_of_ms: float) -> dict:
    ts = np.asarray(ohlcv["timestamp"], dtype=np.float64)
    mask = ts + TF_MS[timeframe] <= as_of_ms
    return {k: np.asarray(v)[mask] for k, v in ohlcv.items()}


def compute_larsson_snapshot(ohlcv: dict, timeframe: str, as_of_ms: float) -> dict:
    """Latest completed-bar ribbon state. Never reads a bar still in progress."""
    base = {"version": LARSSON_VERSION, "timeframe": timeframe, "state": None,
            "last_actionable": None, "flip": None, "bars_since_flip": None,
            "grey_after_gold": False, "e32": None, "e58": None, "spread_pct": None,
            "data_quality": "unavailable", "candle_close_time": None, "input_id": None}
    try:
        closed = _closed(ohlcv, timeframe, as_of_ms)
        close, ts = closed["close"], closed["timestamp"]
        if len(close) < LENGTHS[-1]:
            return dict(base, reason="insufficient completed history")
        s = compute_larsson_series(close, ts)
    except (KeyError, ValueError, TypeError):
        return dict(base, reason="invalid candle data")
    e32, e58 = float(s["e32"][-1]), float(s["e58"][-1])
    digest = hashlib.blake2b(np.ascontiguousarray(close, dtype="<f8").tobytes()
                             + np.ascontiguousarray(ts, dtype="<f8").tobytes(), digest_size=16)
    return dict(
        base,
        state=s["state"][-1], last_actionable=s["last_actionable"][-1], flip=s["flip"][-1],
        bars_since_flip=s["bars_since_flip"][-1], grey_after_gold=s["grey_after_gold"][-1],
        e32=e32, e58=e58, spread_pct=(e32 - e58) / e58 * 100.0,
        data_quality="ready" if len(close) >= READY_BARS else "warmup",
        candle_close_time=(float(ts[-1]) + TF_MS[timeframe]) / 1000.0,
        input_id=digest.hexdigest(), history_bars=len(close),
    )


CHART_WARMUP = 3 * LENGTHS[-1]  # SMA seed differs from TradingView's; after 3x58 bars the gap is < 1%


def compute_larsson_chart(close, timestamps) -> dict:
    """Ribbon for the terminal chart, as compact parallel arrays (the client colours it).

    Display only. ``timestamps`` in ms; output times in unix seconds. Bars inside
    the warm-up are left out because a short chart history seeds the EMAs later
    than TradingView does.
    """
    s = compute_larsson_series(close, timestamps)
    n = len(s["state"])
    idx = [i for i in range(min(CHART_WARMUP, n), n) if s["state"][i] is not None]
    sig = lambda v: float(f"{v:.8g}")
    return {
        "version": LARSSON_VERSION,
        "time": [int(s["timestamps"][i] / 1000) for i in idx],
        **{k: [sig(s[k][i]) for i in idx] for k in ("e32", "e35", "e50", "e58")},
        "state": [s["state"][i] for i in idx],
        "current": s["state"][-1] if n else None,
        "last_actionable": s["last_actionable"][-1] if n else None,
        "bars_since_flip": s["bars_since_flip"][-1] if n else None,
    }
