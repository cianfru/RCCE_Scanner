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
from collections import deque

# Hard cap on tracked keys so a flood of unique identities (e.g. rotating IPs)
# can't grow the map without bound. At capacity, new keys are rejected rather
# than admitted — existing keys keep their history untouched.
_MAX_KEYS = 20_000


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds). Records the hit when allowed."""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            dq = self._hits.get(key)
            if dq is None:
                # New identity. Enforce the key cap before admitting it.
                if len(self._hits) >= _MAX_KEYS:
                    self._prune(cutoff)
                if len(self._hits) >= _MAX_KEYS:
                    # Still saturated with active identities: fail closed for
                    # this new key instead of growing the map without bound.
                    return False, self.window
                dq = deque()
                self._hits[key] = dq
            else:
                while dq and dq[0] < cutoff:
                    dq.popleft()
            if len(dq) >= self.max:
                retry_after = self.window - (now - dq[0])
                return False, max(0.0, retry_after)
            dq.append(now)
            return True, 0.0

    def _prune(self, cutoff: float) -> None:
        """Drop keys with no hits inside the current window. Caller holds lock."""
        stale = [k for k, d in self._hits.items() if not d or d[-1] < cutoff]
        for k in stale:
            del self._hits[k]
