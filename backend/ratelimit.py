"""
Tiny in-process rate limiter.

The API runs as a single Railway instance, so a per-IP sliding window kept in
memory is enough to protect the public LLM endpoints from abuse without pulling
in a Redis/slowapi dependency. Not a distributed limiter — if the app is ever
scaled horizontally this needs to move to a shared store.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

# Cap the number of tracked keys so a flood of unique IPs can't grow the map
# without bound. When exceeded we drop keys whose windows have fully drained.
_MAX_KEYS = 20_000


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds). Records the hit when allowed."""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            dq = self._hits[key]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max:
                retry_after = self.window - (now - dq[0])
                return False, max(0.0, retry_after)
            dq.append(now)
            if len(self._hits) > _MAX_KEYS:
                self._prune(cutoff)
            return True, 0.0

    def _prune(self, cutoff: float) -> None:
        """Drop keys with no hits inside the current window. Caller holds lock."""
        stale = [k for k, d in self._hits.items() if not d or d[-1] < cutoff]
        for k in stale:
            del self._hits[k]
