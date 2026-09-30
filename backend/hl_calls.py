"""
Count of Hyperliquid info API calls, by request type, for /api/hyperlens/status.

Every call site that posts to https://api.hyperliquid.xyz/info calls ``record(type)``.
Counts are kept per minute for the last hour (a fixed ring of 60 buckets per type),
plus a running total since the process started. Memory: a few KB for a dozen types.

Weight: Hyperliquid limits each IP to 1,200 weight a minute. Each call is counted at its
type's base weight (BASE_WEIGHT: 2 for position and book reads, 20 for most others); callers
that know the per-item weight of a paginated answer (fills: +1 per 20 fills) add it with
``record_weight``. Candle answers' per-item weight is not counted, so the total is a floor.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

WINDOW_MIN = 60
BASE_WEIGHT = {"clearinghouseState": 2, "l2Book": 2, "allMids": 2, "orderStatus": 2,
               "spotClearinghouseState": 2, "exchangeStatus": 2, "userRole": 60}
DEFAULT_WEIGHT = 20

_lock = threading.Lock()
_started = time.time()
_totals: Dict[str, int] = {}
_rings: Dict[str, List[int]] = {}     # type -> 60 per-minute counts, indexed by minute % 60
_ring_minute: Dict[str, List[int]] = {}   # type -> the absolute minute each slot holds
_wtotals: Dict[str, int] = {}                # the same, for weight
_wrings: Dict[str, List[int]] = {}
_wring_minute: Dict[str, List[int]] = {}


def _minute(now: float) -> int:
    return int(now // 60)


def _bump(rings: Dict[str, List[int]], minutes: Dict[str, List[int]], totals: Dict[str, int],
          kind: str, n: int, m: int) -> None:
    i = m % WINDOW_MIN
    ring = rings.get(kind)
    if ring is None:
        ring = rings[kind] = [0] * WINDOW_MIN
        minutes[kind] = [-1] * WINDOW_MIN
    mins = minutes[kind]
    if mins[i] != m:
        mins[i], ring[i] = m, 0
    ring[i] += n
    totals[kind] = totals.get(kind, 0) + n


def record(kind: str, n: int = 1, now: Optional[float] = None) -> None:
    """One (or n) info API calls of this type (e.g. "clearinghouseState", "userFills"), counted
    at the type's base weight too."""
    kind = str(kind or "unknown")
    m = _minute(time.time() if now is None else now)
    with _lock:
        _bump(_rings, _ring_minute, _totals, kind, n, m)
        _bump(_wrings, _wring_minute, _wtotals, kind, n * BASE_WEIGHT.get(kind, DEFAULT_WEIGHT), m)


def record_weight(kind: str, weight: int, now: Optional[float] = None) -> None:
    """Weight beyond the base of an already recorded call (the per-item part of a paginated answer)."""
    if weight <= 0:
        return
    kind = str(kind or "unknown")
    with _lock:
        _bump(_wrings, _wring_minute, _wtotals, kind, int(weight), _minute(time.time() if now is None else now))


def _window_sum(kind: str, now_min: int, minutes: int, rings=None, ring_minute=None) -> int:
    ring, mins = (rings or _rings)[kind], (ring_minute or _ring_minute)[kind]
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
        span5, span60 = min(5, max(1, int(up_min))), min(60, max(1, int(up_min)))
        w5 = {k: round(_window_sum(k, m, 5, _wrings, _wring_minute) / span5, 1) for k in sorted(_wrings)}
        w60 = {k: round(_window_sum(k, m, 60, _wrings, _wring_minute) / span60, 1) for k in sorted(_wrings)}
    return {
        "per_min_5m": per5,
        "per_min_60m": per60,
        "per_min_60m_total": round(sum(per60.values()), 2),
        "total_since_start": totals,
        "since": _started,
        # Hyperliquid request weight per minute (limit 1,200 per IP); see the module note.
        "weight_per_min_5m": w5,
        "weight_per_min_5m_total": round(sum(w5.values()), 1),
        "weight_per_min_60m_total": round(sum(w60.values()), 1),
        "weight_limit_per_min": 1200,
    }


def reset() -> None:
    """Tests only."""
    global _started
    with _lock:
        for d in (_totals, _rings, _ring_minute, _wtotals, _wrings, _wring_minute):
            d.clear()
        _started = time.time()
