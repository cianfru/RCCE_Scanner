"""
Hyperliquid info API calls: a count by request type, and one weight budget shared by every caller.

Count (for /api/hyperlens/status): every call site that posts to https://api.hyperliquid.xyz/info
goes through ``acquire`` or ``record``. Counts are kept per minute for the last hour (a fixed
ring of 60 buckets per type), plus a running total since the process started. Memory: a few KB.

Weight: Hyperliquid limits each IP to 1,200 weight a minute. Each call is counted at its type's
base weight (BASE_WEIGHT: 2 for position and book reads, 20 for most others); callers that know
the per-item weight of an answer add it with ``record_weight`` (fills: +1 per 20 fills) or
``settle`` (candles: +1 per 60 candles, see ``candle_weight``).

Shared budget: every Hyperliquid info call in the process draws on one token bucket
(``budget``), sized below the per-IP limit (HL_WEIGHT_PER_MIN, default 1,000 a minute, burst
BURST). Consumers that can wait call ``await acquire(consumer, type)`` before the request;
calls that cannot wait (a page view, market metadata) call ``record`` and are taken from the
bucket at once as "other". Each waiting consumer has a priority and a cap (weight a minute):

    scanner     candles for the scan pass                 priority 0, cap 800
    positions   tracked wallets' positions and books      priority 1, cap 300
    fills       the fills store                           priority 2, cap 300
    cohorts     the cohort sweep and other backfills      priority 3, cap 400

(caps: HL_SCANNER_WEIGHT_PER_MIN, HL_POSITIONS_WEIGHT_PER_MIN, HL_FILLS_WEIGHT_PER_MIN,
HL_COHORTS_WEIGHT_PER_MIN.) Priority works by reserve: a consumer of priority p draws only while
at least p * RESERVE_STEP weight would stay in the bucket, so when the bucket runs low the higher
priorities are served first; the caps keep any one consumer from taking the whole budget. A 429
(``rate_limited``) halves the bucket's rate for PENALTY_S and empties it, so every consumer
backs off together.
"""
from __future__ import annotations

import asyncio
import os
import random
import threading
import time
from typing import Callable, Dict, List, Optional

WINDOW_MIN = 60
BASE_WEIGHT = {"clearinghouseState": 2, "l2Book": 2, "allMids": 2, "orderStatus": 2,
               "spotClearinghouseState": 2, "exchangeStatus": 2, "userRole": 60}
DEFAULT_WEIGHT = 20
OTHER = "other"

_lock = threading.Lock()
_started = time.time()
_totals: Dict[str, int] = {}
_rings: Dict[str, List[int]] = {}     # type -> 60 per-minute counts, indexed by minute % 60
_ring_minute: Dict[str, List[int]] = {}   # type -> the absolute minute each slot holds
_wtotals: Dict[str, int] = {}                # the same, for weight
_wrings: Dict[str, List[int]] = {}
_wring_minute: Dict[str, List[int]] = {}
_ctotals: Dict[str, int] = {}                # the same, weight by consumer
_crings: Dict[str, List[int]] = {}
_cring_minute: Dict[str, List[int]] = {}


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


def _count(kind: str, n: int, weight: int, consumer: str, now: Optional[float]) -> None:
    m = _minute(time.time() if now is None else now)
    with _lock:
        if n:
            _bump(_rings, _ring_minute, _totals, kind, n, m)
        if weight:
            _bump(_wrings, _wring_minute, _wtotals, kind, weight, m)
            _bump(_crings, _cring_minute, _ctotals, consumer, weight, m)


def record(kind: str, n: int = 1, now: Optional[float] = None, consumer: str = OTHER) -> None:
    """One (or n) info API calls of this type (e.g. "clearinghouseState", "userFills") made without
    waiting for the budget: counted at the type's base weight and taken from the budget at once."""
    kind = str(kind or "unknown")
    weight = n * BASE_WEIGHT.get(kind, DEFAULT_WEIGHT)
    _count(kind, n, weight, consumer, now)
    budget.charge(consumer, weight)


def record_weight(kind: str, weight: int, now: Optional[float] = None, consumer: str = OTHER) -> None:
    """Weight beyond the base of an already recorded call (the per-item part of a paginated answer)."""
    if weight <= 0:
        return
    kind = str(kind or "unknown")
    _count(kind, 0, int(weight), consumer, now)
    budget.charge(consumer, int(weight))


async def acquire(consumer: str, kind: str, weight: Optional[int] = None) -> float:
    """Wait for room in the shared budget, then count one call of this type for ``consumer``.
    ``weight``: the call's expected weight (default: the type's base weight). Returns the wait (s)."""
    kind = str(kind or "unknown")
    w = int(BASE_WEIGHT.get(kind, DEFAULT_WEIGHT) if weight is None else weight)
    waited = await budget.acquire(consumer, w)
    _count(kind, 1, w, consumer, None)
    return waited


def settle(consumer: str, kind: str, delta: int) -> None:
    """The answer's real weight differed from the weight acquired by ``delta`` (either sign)."""
    if not delta:
        return
    kind = str(kind or "unknown")
    _count(kind, 0, int(delta), consumer, None)
    budget.charge(consumer, int(delta))


def rate_limited(consumer: str = OTHER) -> None:
    """Hyperliquid answered 429: every consumer slows down for a while."""
    budget.penalize(consumer)


def candle_weight(candles: int) -> int:
    """candleSnapshot weight: 20, plus 1 per 60 candles in the answer (Hyperliquid's rate-limit docs)."""
    return DEFAULT_WEIGHT + max(0, int(candles)) // 60


def backoff_delay(attempt: int, base: float = 2.0, cap: float = 60.0,
                  rng: Callable[[], float] = random.random) -> float:
    """Seconds before retry ``attempt`` (0 for the first retry) after a 429: exponential, with
    jitter so callers refused together do not come back together. Between half and all of
    min(cap, base * 2**attempt)."""
    d = min(cap, base * (2 ** max(0, attempt)))
    return d / 2 + rng() * d / 2


# ---------------------------------------------------------------------------
# Shared budget
# ---------------------------------------------------------------------------

def _env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


TARGET_PER_MIN = _env("HL_WEIGHT_PER_MIN", 1000)
BURST = 120.0
RESERVE_STEP = 20.0
PENALTY_S = 60.0
MAX_SLEEP_S = 2.0                # a waiting consumer looks again at least this often
CONSUMERS: Dict[str, tuple] = {  # name -> (priority, cap in weight a minute)
    "scanner": (0, _env("HL_SCANNER_WEIGHT_PER_MIN", 800)),
    "positions": (1, _env("HL_POSITIONS_WEIGHT_PER_MIN", 300)),
    "fills": (2, _env("HL_FILLS_WEIGHT_PER_MIN", 300)),
    "cohorts": (3, _env("HL_COHORTS_WEIGHT_PER_MIN", 400)),
}


class Budget:
    """Token bucket shared by every consumer, with a cap bucket per consumer (see the module note).
    Thread-safe; ``clock`` and ``sleep`` can be replaced in tests."""

    def __init__(self, per_min: float = TARGET_PER_MIN, burst: float = BURST,
                 consumers: Optional[Dict[str, tuple]] = None,
                 clock: Callable[[], float] = time.monotonic, sleep=None,
                 reserve_step: float = RESERVE_STEP, penalty_s: float = PENALTY_S):
        self.clock = clock
        self.sleep = sleep or asyncio.sleep
        self.base_rate = self.rate = per_min / 60.0
        self.capacity = burst
        self.reserve_step = reserve_step
        self.penalty_s = penalty_s
        now = clock()
        self.level, self.last, self.penalty_until = burst, now, 0.0
        self.consumers: Dict[str, dict] = {}
        for name, (priority, cap) in (CONSUMERS if consumers is None else consumers).items():
            cap_burst = max(30.0, cap / 10)
            self.consumers[name] = {"priority": priority, "cap_per_min": cap, "rate": cap / 60.0,
                                    "capacity": cap_burst, "level": cap_burst, "last": now,
                                    "waits": 0, "wait_s": 0.0, "rate_limited": 0}
        self.other_rate_limited = 0
        self._lock = threading.Lock()

    def _refill(self, now: float) -> None:
        if self.penalty_until and now >= self.penalty_until:
            self.rate, self.penalty_until = self.base_rate, 0.0
        self.level = min(self.capacity, self.level + max(0.0, now - self.last) * self.rate)
        self.last = now

    @staticmethod
    def _refill_c(c: dict, now: float) -> None:
        c["level"] = min(c["capacity"], c["level"] + max(0.0, now - c["last"]) * c["rate"])
        c["last"] = now

    def try_take(self, consumer: str, weight: float) -> float:
        """Take ``weight`` for ``consumer`` if its priority and cap allow it now: returns 0. Otherwise
        takes nothing and returns the seconds until it might (if no one else draws meanwhile)."""
        c = self.consumers.get(consumer)
        with self._lock:
            now = self.clock()
            self._refill(now)
            if c is None:                          # not a waiting consumer: taken at once
                self.level -= weight
                return 0.0
            self._refill_c(c, now)
            # Weight above a bucket's size could never fit: it waits for a full bucket instead.
            need = min(self.capacity, c["priority"] * self.reserve_step + weight)
            need_c = min(c["capacity"], weight)
            if self.level + 1e-9 >= need and c["level"] + 1e-9 >= need_c:
                self.level -= weight
                c["level"] -= weight
                return 0.0
            wait = max((need - self.level) / self.rate if self.level < need else 0.0,
                       (need_c - c["level"]) / c["rate"] if c["level"] < need_c else 0.0)
            return max(1e-3, wait)

    async def acquire(self, consumer: str, weight: float) -> float:
        """Wait until ``weight`` can be taken for ``consumer``, then take it. Returns the seconds waited."""
        waited = 0.0
        while True:
            wait = self.try_take(consumer, weight)
            if wait <= 0:
                c = self.consumers.get(consumer)
                if waited and c is not None:
                    with self._lock:
                        c["waits"] += 1
                        c["wait_s"] += waited
                return waited
            step = min(wait, MAX_SLEEP_S)
            await self.sleep(step)
            waited += step

    def charge(self, consumer: str, weight: float) -> None:
        """Take (or, negative, give back) weight without waiting; the bucket may go below zero."""
        with self._lock:
            now = self.clock()
            self._refill(now)
            self.level = min(self.capacity, self.level - weight)
            c = self.consumers.get(consumer)
            if c is not None:
                self._refill_c(c, now)
                c["level"] = min(c["capacity"], c["level"] - weight)

    def penalize(self, consumer: str = OTHER) -> None:
        """A 429: half the rate (down to an eighth) for penalty_s, and an empty bucket."""
        with self._lock:
            now = self.clock()
            self._refill(now)
            self.rate = max(self.base_rate / 8, self.rate / 2)
            self.level = min(self.level, 0.0)
            self.penalty_until = now + self.penalty_s
            c = self.consumers.get(consumer)
            if c is not None:
                c["rate_limited"] += 1
            else:
                self.other_rate_limited += 1

    def status(self) -> dict:
        with self._lock:
            now = self.clock()
            self._refill(now)
            return {
                "target_per_min": round(self.base_rate * 60),
                "rate_per_min": round(self.rate * 60),
                "penalty_s_left": round(max(0.0, self.penalty_until - now)) if self.penalty_until else 0,
                "level": round(self.level, 1), "burst": self.capacity,
                "consumers": {name: {"priority": c["priority"], "cap_per_min": c["cap_per_min"],
                                     "waits": c["waits"], "wait_s": round(c["wait_s"], 1),
                                     "rate_limited": c["rate_limited"]}
                              for name, c in self.consumers.items()},
                "other_rate_limited": self.other_rate_limited,
            }


def unlimited() -> Budget:
    """A budget that never waits (tests, or HL_BUDGET_ENABLED=0)."""
    return Budget(per_min=1e12, burst=1e12, consumers={k: (0, 1e12) for k in CONSUMERS})


budget = Budget() if os.environ.get("HL_BUDGET_ENABLED", "1") not in ("0", "false", "no") else unlimited()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

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
        c5 = {k: round(_window_sum(k, m, 5, _crings, _cring_minute) / span5, 1) for k in sorted(_crings)}
        c60 = {k: round(_window_sum(k, m, 60, _crings, _cring_minute) / span60, 1) for k in sorted(_crings)}
        ctotals = dict(_ctotals)
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
        "budget": _budget_rows(c5, c60, ctotals),
    }


def _budget_rows(c5: dict, c60: dict, ctotals: dict) -> dict:
    out = budget.status()
    for name in list(out["consumers"]) + [OTHER]:
        row = out["consumers"].setdefault(name, {"priority": None, "cap_per_min": None})
        row["weight_per_min_5m"] = c5.get(name, 0.0)
        row["weight_per_min_60m"] = c60.get(name, 0.0)
        row["weight_since_start"] = ctotals.get(name, 0)
    return out


def budget_status(now: Optional[float] = None) -> dict:
    """The shared budget and each consumer's use (weight a minute over the last 5 and 60 finished
    minutes, and since start), for /api/net-stats."""
    return stats(now)["budget"]


def reset() -> None:
    """Tests only."""
    global _started
    with _lock:
        for d in (_totals, _rings, _ring_minute, _wtotals, _wrings, _wring_minute, _ctotals, _crings, _cring_minute):
            d.clear()
        _started = time.time()
