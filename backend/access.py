"""
Server-side access control for the API and the scan WebSocket.

Enforced only when REFLEX_ACCESS_CODE is set (Railway variable). Until then the API
stays open as before, so deploying this cannot lock anyone out. The frontend logs in
with the access code and receives a signed token (HMAC-SHA256, 30 days), which it
sends as "Authorization: Bearer <token>" (or ?token= for the WebSocket).

REFLEX_AUTH_SECRET, if set, signs tokens; otherwise the access code does, so changing
the code also signs everyone out.

Writes are guarded separately: once REFLEX_ADMIN_KEY is set, every non-GET API request
(executor controls, TradFi markets, feature flags, watchlists, chat, backtests, scan
refresh...) must carry "X-Admin-Key: <key>", whether or not viewing is open. Login is
exempt. Until the variable is set nothing changes.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

TOKEN_SECONDS = 30 * 86400
# Paths that stay public while enforcement is on: login itself, health checks and the
# landing page's five-coin preview.
PUBLIC_PREFIXES = ("/api/auth/", "/api/public/")
PUBLIC_PATHS = frozenset({"/health", "/api/health"})


def enforced() -> bool:
    return bool(os.environ.get("REFLEX_ACCESS_CODE"))


def _secret() -> bytes:
    return (os.environ.get("REFLEX_AUTH_SECRET") or os.environ.get("REFLEX_ACCESS_CODE") or "").encode()


def check_code(code: str) -> bool:
    expected = os.environ.get("REFLEX_ACCESS_CODE", "")
    return bool(expected) and hmac.compare_digest(str(code).encode(), expected.encode())


def issue_token(now: Optional[float] = None) -> str:
    expires = int((time.time() if now is None else now) + TOKEN_SECONDS)
    sig = hmac.new(_secret(), str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def token_valid(token: Optional[str], now: Optional[float] = None) -> bool:
    if not token or "." not in token or not _secret():
        return False
    expires, sig = token.split(".", 1)
    good = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good) and expires.isdigit() and int(expires) > (time.time() if now is None else now)


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES) or not path.startswith(("/api/", "/ws/"))


def request_token(headers, query_params) -> Optional[str]:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return query_params.get("token")


def allowed(path: str, headers, query_params) -> bool:
    return not enforced() or is_public(path) or token_valid(request_token(headers, query_params))


WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
WRITE_EXEMPT = ("/api/auth/",)


def admin_enforced() -> bool:
    return bool(os.environ.get("REFLEX_ADMIN_KEY"))


def write_allowed(method: str, path: str, headers) -> bool:
    """Non-GET API calls need the admin key once REFLEX_ADMIN_KEY is set."""
    if not admin_enforced() or method.upper() not in WRITE_METHODS:
        return True
    if not path.startswith("/api/") or path.startswith(WRITE_EXEMPT):
        return True
    given = headers.get("x-admin-key", "")
    return bool(given) and hmac.compare_digest(given.encode(), os.environ["REFLEX_ADMIN_KEY"].encode())
