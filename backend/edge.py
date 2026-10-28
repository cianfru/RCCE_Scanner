"""
edge.py
~~~~~~~
Shared CDN cache for the heavy read-only feeds (the scan, the Radar map, positioning...).

Every visible tab polls the same few feeds, and every copy leaves Railway as egress.
With a CDN in front, one copy per region and TTL leaves Railway and the CDN serves
the rest. The frontend reaches these feeds through a same-origin path on its own
host (``/edge/api/...``, a rewrite in ``frontend/vercel.json``); everything else,
and the WebSocket, still goes straight to the API.

A shared cache must never hand a feed to someone who could not read it directly.
The CDN keys its copies by full URL and does not store answers to requests that carry
credentials, so these requests carry none: instead the URL holds a short key for the
reader's access level (:func:`issue`), which the API hands to logged-in pages at
``/api/edge/key``. Only URLs with a current key reach a cached copy or the API, and
the key changes on a fixed window. With access control off the API is open anyway.

Cacheable answers (GET, 200, JSON, an edge path, a valid key, no credentials) get
``CDN-Cache-Control`` (the CDN's lifetime; browsers ignore it) and a browser
``Cache-Control`` that still revalidates every time. ETags stay as they are.

Switches (Railway variables):
    EDGE_CACHE=1             turn it on (off by default: pages then call the API directly)
    EDGE_TTL_S=30            CDN lifetime of a copy
    EDGE_SWR_S=30            serve a copy this much longer while the CDN refetches it
    EDGE_STALE_IF_ERROR_S=600  serve the last copy this long when the API errors
    EDGE_KEY_WINDOW_S=21600  how long one key is issued for
    EDGE_PUBLIC_TTL_S=300    CDN lifetime of the public landing payloads

The landing's public payloads (PUBLIC_PATHS) need no key: they are public by design and
the same for everyone, so they are always marked cacheable, whatever EDGE_CACHE says.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

import access

PREFIX = "/edge"

# Feeds that are the same for every reader at one access level.
EDGE_PATHS = frozenset({
    "/api/scan",
    "/api/scan/sparklines",
    "/api/scan/row",
    "/api/setup-map",
    "/api/market-history",
    "/api/market-history/spark",
    "/api/market-history/wallets",
    "/api/hyperlens/consensus",
    "/api/hyperlens/positioning",
    "/api/traders/leaderboard",
    "/api/tradfi",
    "/api/universe",
    "/api/sectors",
    # The Portfolio page's per-coin scanner context: keyed by coin only, never an address.
    "/api/portfolio/context",
    "/api/portfolio/events",
})

# Public by design (access.PUBLIC_PREFIXES) and the same for every visitor: no key needed.
PUBLIC_PATHS = frozenset({"/api/public/preview", "/api/public/landing"})

LEVEL = "member"          # the one access level there is today


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    return os.environ.get("EDGE_CACHE", "0").strip().lower() in ("1", "true", "yes", "on")


def ttl() -> int:
    return max(1, _int_env("EDGE_TTL_S", 30))


def window() -> int:
    return max(600, _int_env("EDGE_KEY_WINDOW_S", 21600))


def cdn_cache_control() -> str:
    return (f"max-age={ttl()}, stale-while-revalidate={_int_env('EDGE_SWR_S', 30)}, "
            f"stale-if-error={_int_env('EDGE_STALE_IF_ERROR_S', 600)}")


def public_cdn_cache_control() -> str:
    t = max(1, _int_env("EDGE_PUBLIC_TTL_S", 300))
    return f"max-age={t}, stale-while-revalidate={2 * t}, stale-if-error=86400"


def _key_for(level: str, slot: int) -> str:
    secret = access._secret()
    msg = f"edge|{level}|{slot}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:32]


def issue(level: str = LEVEL, now: Optional[float] = None) -> dict:
    """The key a page at *level* puts in edge URLs, and when to ask for a new one."""
    now = time.time() if now is None else now
    w = window()
    slot = int(now // w)
    if not access.enforced():
        return {"key": "open", "expires_at": (slot + 1) * w}
    return {"key": _key_for(level, slot), "expires_at": (slot + 1) * w}


def key_valid(key: Optional[str], level: str = LEVEL, now: Optional[float] = None) -> bool:
    """A key from this window or the one before (pages refresh theirs as it ends)."""
    if not key:
        return False
    if not access.enforced():
        return True
    now = time.time() if now is None else now
    slot = int(now // window())
    return any(hmac.compare_digest(key.encode(), _key_for(level, s).encode()) for s in (slot, slot - 1))


def is_edge_request(method: str, path: str, headers, query_params) -> bool:
    """A credential-free GET of an edge feed carrying a valid key."""
    if not enabled() or method.upper() != "GET" or path not in EDGE_PATHS:
        return False
    # An account session changes some bodies (the Radar map with access tiers on), so it
    # never goes through the shared copy.
    if headers.get("authorization") or headers.get("x-reflex-session"):
        return False
    return key_valid(query_params.get("k"))


def request_allowed(method: str, path: str, headers, query_params) -> bool:
    """Access check for edge URLs (they carry the key instead of a token)."""
    return is_edge_request(method, path, headers, query_params)


def key_response() -> dict:
    if not enabled():
        return {"enabled": False}
    return {"enabled": True, "prefix": PREFIX, "ttl_s": ttl(), **issue()}


# ---------------------------------------------------------------------------
# ASGI middleware: marks cacheable answers. Sits inside ConditionalGetMiddleware.
# ---------------------------------------------------------------------------

class _Headers:
    def __init__(self, raw) -> None:
        self._d = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw or []}

    def get(self, name: str, default=None):
        return self._d.get(name.lower(), default)


def _query(scope) -> dict:
    from urllib.parse import parse_qs
    qs = parse_qs((scope.get("query_string") or b"").decode("latin-1"))
    return {k: v[-1] for k, v in qs.items()}


def is_public_request(method: str, path: str) -> bool:
    return method.upper() == "GET" and path in PUBLIC_PATHS


class EdgeCacheMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        public = is_public_request(scope.get("method", ""), scope.get("path", ""))
        if not public and not is_edge_request(
                scope.get("method", ""), scope.get("path", ""), _Headers(scope.get("headers")), _query(scope)):
            await self.app(scope, receive, send)
            return
        lifetime = public_cdn_cache_control() if public else cdn_cache_control()

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start" and message.get("status") == 200:
                headers = [(k, v) for k, v in message.get("headers") or []]
                ctype = next((v for k, v in headers if k.lower() == b"content-type"), b"").lower()
                cc = next((v for k, v in headers if k.lower() == b"cache-control"), b"").lower()
                if ctype.startswith(b"application/json") and b"no-store" not in cc and b"private" not in cc:
                    headers = [(k, v) for k, v in headers
                               if k.lower() not in (b"cache-control", b"cdn-cache-control")]
                    headers += [
                        (b"cache-control", b"max-age=0, must-revalidate"),
                        (b"cdn-cache-control", lifetime.encode("latin-1")),
                        (b"vercel-cache-tag", b"reflex-api"),
                    ]
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
