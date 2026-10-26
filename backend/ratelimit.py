"""
Tiny in-process rate limiters: a sliding window for the assistant endpoints and
token buckets (``RateLimitMiddleware``) for the other expensive endpoints.

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


# ---------------------------------------------------------------------------
# Token buckets for the expensive endpoints (see RateLimitMiddleware below)
# ---------------------------------------------------------------------------

import json
import os
import re
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs


class TokenBucket:
    """Per-key token bucket: *burst* requests at once, refilled at *per_minute*.

    Idle keys refill to full and are dropped when the map is pruned, so memory
    follows the number of recently active clients.
    """

    def __init__(self, burst: float, per_minute: float, max_keys: Optional[int] = None):
        self.burst = max(1.0, float(burst))
        self.rate = max(1e-6, float(per_minute) / 60.0)
        self.max_keys = _MAX_KEYS if max_keys is None else max_keys
        self._b: Dict[str, Tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str, now: Optional[float] = None) -> Tuple[bool, float]:
        """Spend one token. Returns (allowed, seconds until one is available)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if key not in self._b and len(self._b) >= self.max_keys:
                self._prune(now)
                if len(self._b) >= self.max_keys:
                    return False, 1.0 / self.rate
            tokens, last = self._b.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + max(0.0, now - last) * self.rate)
            if tokens >= 1.0:
                self._b[key] = (tokens - 1.0, now)
                return True, 0.0
            self._b[key] = (tokens, now)
            return False, (1.0 - tokens) / self.rate

    def _prune(self, now: float) -> None:
        full = [k for k, (t, last) in self._b.items() if t + (now - last) * self.rate >= self.burst]
        for k in full:
            del self._b[k]


def client_ip(headers, peer: Optional[str], mode: Optional[str] = None) -> str:
    """The client's address behind the platform proxy.

    RATE_LIMIT_CLIENT_IP picks the source: ``xff-first`` (default: the first
    X-Forwarded-For entry), ``xff-last``, ``real-ip`` (X-Real-IP) or ``peer``
    (the TCP peer, for running without a proxy).
    """
    mode = (mode or os.environ.get("RATE_LIMIT_CLIENT_IP") or "xff-first").strip().lower()
    if mode == "peer":
        return peer or "unknown"
    if mode == "real-ip":
        real = (headers.get("x-real-ip") or "").strip()
        return real or peer or "unknown"
    parts = [p.strip() for p in (headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    if parts:
        return parts[-1] if mode == "xff-last" else parts[0]
    return peer or "unknown"


# Endpoints that read an exchange (mostly Hyperliquid) on the request itself.
_EXCHANGE_READS = re.compile(
    r"^/api/("
    r"setup-map/(ladder|mine)"
    r"|trade/(account|positions|fills|history)"
    r"|chart/.+"
    r"|positioning/cross-exchange/.+"
    r"|perpetuals/hyperliquid(/debug)?"
    r"|hyperlens/entries/.+"
    r"|hyperlens/follows/check/.+"
    r"|confirm(/.+)?"
    r"|derivatives-shadow|derivatives-comparison|geo-test|test-binance-derivatives|debug/sm-test"
    r"|coinglass/macro"
    r"|hyperliquid/bridge(/.+)?"
    r"|whales/(holders|history)/.+"
    r"|executor/hl/.+"
    r")$")
# These read the given wallet's positions when an address is passed.
_WALLET_NOTICES = re.compile(r"^/api/notifications/(position-warnings|exhaustion-opportunities|market-setups)$")
_TRADER = re.compile(r"^/api/traders/0x[0-9a-fA-F]{40}(/fills|/history)?$")
# The Portfolio page's per-coin context and events (memory and the signal log, keyed by coin).
_PORTFOLIO = re.compile(r"^/api/portfolio/(context|events)$")
# Login keeps its own guard and chat its own limiter (see main.py).
_WRITE_EXEMPT = ("/api/auth/", "/api/chat", "/api/usage/beacon")   # the beacon has its own limit

# Class -> (per client "burst/per_minute", all clients together "burst/per_minute" or None).
DEFAULTS: Dict[str, Tuple[str, Optional[str]]] = {
    "trader": ("30/20", "120/120"),     # trader profiles, fills and history
    "exchange": ("60/60", "300/600"),   # other endpoints that read an exchange per request
    "write": ("60/60", None),           # changes (POST, PUT, PATCH, DELETE)
    "portfolio": ("30/30", "600/1200"), # the Portfolio page's coin context and events
}


def classify(method: str, path: str, query) -> Optional[str]:
    """The rate-limit class of a request, or None when it is not limited."""
    method = method.upper()
    if method == "GET":
        if _TRADER.match(path):
            return "trader"
        if _PORTFOLIO.match(path):
            return "portfolio"
        if _EXCHANGE_READS.match(path):
            return "exchange"
        if _WALLET_NOTICES.match(path) and query.get("address"):
            return "exchange"
        return None
    if method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/") \
            and not path.startswith(_WRITE_EXEMPT):
        return "write"
    return None


def _parse(spec: Optional[str]) -> Optional[Tuple[float, float]]:
    if not spec or spec.strip().lower() in ("0", "off", "none"):
        return None
    try:
        burst, per_min = spec.split("/", 1)
        return float(burst), float(per_min)
    except ValueError:
        return None


def enabled() -> bool:
    return os.environ.get("RATE_LIMIT", "1").strip().lower() not in ("0", "false", "off", "no")


class Limits:
    """The buckets, from DEFAULTS overridden by RATE_LIMIT_<CLASS> and RATE_LIMIT_<CLASS>_GLOBAL
    (for example RATE_LIMIT_TRADER=30/20: bursts of 30, then 20 a minute; "off" removes one)."""

    def __init__(self, env: Optional[dict] = None) -> None:
        env = os.environ if env is None else env
        self.per_client: Dict[str, TokenBucket] = {}
        self.everyone: Dict[str, TokenBucket] = {}
        for name, (client_spec, global_spec) in DEFAULTS.items():
            c = _parse(env.get(f"RATE_LIMIT_{name.upper()}", client_spec))
            g = _parse(env.get(f"RATE_LIMIT_{name.upper()}_GLOBAL", global_spec or "off"))
            if c:
                self.per_client[name] = TokenBucket(*c)
            if g:
                self.everyone[name] = TokenBucket(*g)

    def check(self, cls: str, client: str, now: Optional[float] = None) -> Tuple[bool, float]:
        per = self.per_client.get(cls)
        if per:
            ok, wait = per.take(client, now)
            if not ok:
                return False, wait
        together = self.everyone.get(cls)
        if together:
            ok, wait = together.take("*", now)
            if not ok:
                return False, wait
        return True, 0.0


LIMITED: Dict[str, int] = {}     # class -> requests refused since start (for /api/net-stats)


class RateLimitMiddleware:
    """429 with Retry-After when a client (or all clients together) exceeds a class's budget.

    RATE_LIMIT=0 turns it off. Buckets are in memory: one API instance.
    """

    def __init__(self, app, limits: Optional[Limits] = None) -> None:
        self.app = app
        self.limits = limits

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or not enabled():
            await self.app(scope, receive, send)
            return
        query = {k: v[-1] for k, v in parse_qs((scope.get("query_string") or b"").decode("latin-1")).items()}
        cls = classify(scope.get("method", "GET"), scope.get("path", ""), query)
        if cls is None:
            await self.app(scope, receive, send)
            return
        if self.limits is None:
            self.limits = Limits()
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        peer = (scope.get("client") or (None,))[0]
        ok, wait = self.limits.check(cls, client_ip(headers, peer))
        if ok:
            await self.app(scope, receive, send)
            return
        LIMITED[cls] = LIMITED.get(cls, 0) + 1
        body = json.dumps({"detail": "Too many requests. Please slow down and try again shortly."}).encode()
        await send({"type": "http.response.start", "status": 429, "headers": [
            (b"content-type", b"application/json"),
            (b"retry-after", str(int(wait) + 1).encode()),
            (b"access-control-allow-origin", b"*"),
            (b"access-control-expose-headers", b"Retry-After"),
            (b"cache-control", b"no-store"),
        ]})
        await send({"type": "http.response.body", "body": body})
