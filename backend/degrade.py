"""
degrade.py
~~~~~~~~~~
Last good data, with its time, when a feed cannot be rebuilt.

When Hyperliquid (or another source) is slow, erroring or limiting, the main feeds
keep serving what they last built instead of an error or an empty panel:

* :class:`LastGood` keeps the last good body per feed and parameters. :meth:`serve`
  builds a fresh body; if the build raises, or returns an empty body where the last
  one had data, the last good body goes out with ``"stale": true``.
* Every such body carries ``as_of``: when its underlying data was read (the last
  completed scan pass, or the newest wallet reading for trader positioning), and
  ``stale`` when that is older than the feed's limit. Pages show a small
  "as of HH:MM" only when ``stale`` is true.

Limits (Railway variables, seconds):
    DEGRADE_SCAN_STALE_S=900        scan-derived feeds
    DEGRADE_POSITIONS_STALE_S=1200  trader positioning (consensus, positioning, the Radar map)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Awaitable, Callable, Dict, Hashable, Optional, Tuple

logger = logging.getLogger("degrade")


def _limit(name: str, default: int) -> int:
    try:
        return max(60, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def scan_limit() -> int:
    return _limit("DEGRADE_SCAN_STALE_S", 900)


def positions_limit() -> int:
    return _limit("DEGRADE_POSITIONS_STALE_S", 1200)


def scan_as_of() -> Optional[float]:
    """When the last scan pass completed."""
    try:
        from scanner import cache
        return cache.last_scan_time
    except Exception:
        return None


def positions_as_of() -> Optional[float]:
    """When the newest tracked-wallet reading arrived (it stops moving when reads fail)."""
    try:
        import hl_intelligence as hl
        newest = 0.0
        for snaps in list(hl._snapshots.values()):
            if snaps:
                ts = getattr(snaps[-1], "timestamp", 0.0) or 0.0
                if ts > newest:
                    newest = ts
        # To the minute: pages show HH:MM, and a time that moved every second would change
        # the body (and its ETag) on every request.
        return float(int(newest // 60) * 60) or None
    except Exception:
        return None


def is_stale(as_of: Optional[float], limit: int, now: Optional[float] = None) -> bool:
    if not as_of:
        return False          # nothing read yet: a loading state, not an outage
    return (time.time() if now is None else now) - as_of > limit


def stamp(body: Any, *sources: Tuple[Optional[float], int], now: Optional[float] = None) -> Any:
    """Add ``as_of`` (the oldest of the sources' times) and ``stale`` (any source past its
    limit) to a dict body, as a copy. A body already marked stale keeps its own time."""
    if not isinstance(body, dict):
        return body
    out = dict(body)
    times = [t for t, _ in sources if t]
    if out.get("stale") and out.get("as_of"):
        return out
    out["as_of"] = min(times) if times else None
    out["stale"] = any(is_stale(t, limit, now) for t, limit in sources)
    return out


def _has_data(body: Any) -> bool:
    """False for a body whose main list is empty (an empty panel)."""
    if not isinstance(body, dict):
        return body is not None
    for key in ("rows", "results", "consensus", "coins", "days", "wallets"):
        v = body.get(key)
        if isinstance(v, (list, dict)):
            return len(v) > 0
    return True


class LastGood:
    """The last good body per key (bounded)."""

    def __init__(self, max_keys: int = 64) -> None:
        self.max_keys = max_keys
        self._d: Dict[Hashable, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.fallbacks = 0          # bodies served from here since start

    def remember(self, key: Hashable, body: Any, now: Optional[float] = None) -> None:
        with self._lock:
            if key not in self._d and len(self._d) >= self.max_keys:
                self._d.pop(next(iter(self._d)))
            self._d[key] = (time.time() if now is None else now, body)

    def get(self, key: Hashable) -> Optional[Tuple[float, Any]]:
        with self._lock:
            return self._d.get(key)

    def _fallback(self, key: Hashable, reason: str) -> Optional[Any]:
        hit = self.get(key)
        if hit is None:
            return None
        built_at, body = hit
        self.fallbacks += 1
        logger.info("serving last good %s (%s)", key, reason)
        if isinstance(body, dict):
            body = dict(body)
            body["stale"] = True
            body.setdefault("as_of", built_at)
            if not body.get("as_of"):
                body["as_of"] = built_at
        return body

    def serve_sync(self, key: Hashable, build: Callable[[], Any]) -> Any:
        try:
            body = build()
        except Exception as exc:
            out = self._fallback(key, f"build failed: {exc}")
            if out is None:
                raise
            return out
        if not _has_data(body):
            out = self._fallback(key, "empty")
            if out is not None:
                return out
            return body
        self.remember(key, body)
        return body

    async def serve(self, key: Hashable, build: Callable[[], Awaitable[Any]]) -> Any:
        try:
            body = await build()
        except Exception as exc:
            out = self._fallback(key, f"build failed: {exc}")
            if out is None:
                raise
            return out
        if not _has_data(body):
            out = self._fallback(key, "empty")
            if out is not None:
                return out
            return body
        self.remember(key, body)
        return body


LAST_GOOD = LastGood()
