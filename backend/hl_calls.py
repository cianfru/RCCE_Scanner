"""
Count of Hyperliquid info API calls, by request type, for /api/hyperlens/status.

Every call site that posts to https://api.hyperliquid.xyz/info calls ``record(type)``.
Counts are kept per minute for the last hour (a fixed ring of 60 buckets per type),
plus a running total since the process started. Memory: a few KB for a dozen types.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

WINDOW_MIN = 60

_lock = threading.Lock()
_started = time.time()
_totals: Dict[str, int] = {}
_rings: Dict[str, List[int]] = {}     # type -> 60 per-minute counts, indexed by minute % 60
_ring_minute: Dict[str, List[int]] = {}   # type -> the absolute minute each slot holds


def _minute(now: float) -> int:
    return int(now // 60)


def record(kind: str, n: int = 1, now: Optional[float] = None) -> None:
    """One (or n) info API calls of this type (e.g. "clearinghouseState", "userFills")."""
    kind = str(kind or "unknown")
    m = _minute(time.time() if now is None else now)
    i = m % WINDOW_MIN
    with _lock:
        ring = _rings.get(kind)
        if ring is None:
            ring = _rings[kind] = [0] * WINDOW_MIN
            _ring_minute[kind] = [-1] * WINDOW_MIN
        mins = _ring_minute[kind]
        if mins[i] != m:
            mins[i], ring[i] = m, 0
        ring[i] += n
        _totals[kind] = _totals.get(kind, 0) + n


def _window_sum(kind: str, now_min: int, minutes: int) -> int:
    ring, mins = _rings[kind], _ring_minute[kind]
    # Only whole minutes that have ended: the current minute is still filling.
    return sum(ring[i] for i in range(WINDOW_MIN) if now_min - minutes <= mins[i] < now_min)


def stats(now: Optional[float] = None) -> dict:
    """Calls per minute by type over the last 5 and 60 finished minutes, and totals since start."""
    now = time.time() if now is None else now
    m = _minute(now)
    up_min = max(1e-9, (now - _started) / 60)
    with _lock:
        kinds = sorted(_rings)
        per5 = {k: round(_window_sum(k, m, 5) / min(5, max(1, int(up_min))), 2) for k in kinds}
        per60 = {k: round(_window_sum(k, m, 60) / min(60, max(1, int(up_min))), 2) for k in kinds}
        totals = dict(_totals)
    return {
        "per_min_5m": per5,
        "per_min_60m": per60,
        "per_min_60m_total": round(sum(per60.values()), 2),
        "total_since_start": totals,
        "since": _started,
    }


def reset() -> None:
    """Tests only."""
    global _started
    with _lock:
        _totals.clear()
        _rings.clear()
        _ring_minute.clear()
        _started = time.time()
