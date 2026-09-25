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
