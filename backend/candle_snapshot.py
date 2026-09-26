"""Causal OHLCV snapshots shared by live scanning and historical replay."""
from __future__ import annotations

import hashlib
import time

import numpy as np

TF_MS = {"4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}
FIELDS = ("timestamp", "open", "high", "low", "close", "volume")


def closed_candles(data: dict | None, timeframe: str, as_of_ms: float) -> dict | None:
    """Include a bar only once its entire interval has elapsed (timestamps are opens)."""
    if data is None:
        return None
    timestamps = np.asarray(data["timestamp"], dtype=np.float64)
    mask = timestamps + TF_MS[timeframe] <= as_of_ms
    return {key: np.asarray(values)[mask] for key, values in data.items()}


def snapshot_key(ohlcv, timeframe, weekly=None, btc=None, eth=None, *, as_of_ms=None):
    """Invalidate on closed-bar revisions and reference/weekly changes, not live ticks."""
    as_of_ms = time.time() * 1000 if as_of_ms is None else as_of_ms
    digest = hashlib.blake2b(digest_size=16)
    for data, tf in ((ohlcv, timeframe), (weekly, "1w"), (btc, timeframe), (eth, timeframe)):
        snapshot = closed_candles(data, tf, as_of_ms)
        if snapshot is None:
            digest.update(b"missing")
            continue
        for field in FIELDS:
            values = np.asarray(snapshot[field], dtype="<f8")
            digest.update(len(values).to_bytes(8, "little"))
            digest.update(values.tobytes())
    return digest.hexdigest()


def consistent_weekly(weekly: dict | None, sub: dict | None, sub_timeframe: str, tolerance: float = 0.02) -> dict | None:
    """Drop weekly bars whose close lies outside that week's low-high range in *sub*.

    *sub* is the same market on a shorter timeframe (4h or 1d). Only weeks the
    shorter candles cover end to end are checked; older weeks are kept as they are.
    """
    if weekly is None or sub is None or len(sub["timestamp"]) == 0 or len(weekly["timestamp"]) == 0:
        return weekly
    w_ts = np.asarray(weekly["timestamp"], dtype=np.float64)
    w_close = np.asarray(weekly["close"], dtype=np.float64)
    s_ts = np.asarray(sub["timestamp"], dtype=np.float64)
    s_low = np.asarray(sub["low"], dtype=np.float64)
    s_high = np.asarray(sub["high"], dtype=np.float64)
    covered_until = s_ts[-1] + TF_MS[sub_timeframe]
    start = np.searchsorted(s_ts, w_ts, "left")
    end = np.searchsorted(s_ts, w_ts + TF_MS["1w"], "left")
    keep = np.ones(len(w_ts), dtype=bool)
    for i in range(len(w_ts)):
        if w_ts[i] < s_ts[0] or w_ts[i] + TF_MS["1w"] > covered_until or end[i] <= start[i]:
            continue
        low = np.nanmin(s_low[start[i]:end[i]])
        high = np.nanmax(s_high[start[i]:end[i]])
        keep[i] = low * (1 - tolerance) <= w_close[i] <= high * (1 + tolerance)
    if keep.all():
        return weekly
    return {key: np.asarray(values)[keep] for key, values in weekly.items()}
