"""
Server-side access control for the API and the scan WebSocket.

Enforced only when REFLEX_ACCESS_CODE is set (Railway variable). Until then the API
stays open as before, so deploying this cannot lock anyone out. The frontend logs in
with the access code and receives a signed token (HMAC-SHA256, 30 days), which it
sends as "Authorization: Bearer <token>" (or ?token= for the WebSocket).

REFLEX_AUTH_SECRET, if set, signs tokens; otherwise the access code does, so changing
the code also signs everyone out.

Per-person invite codes (invites.py) are taken at the same login. Their token also names
the invite, so a session is attributed to a person and ends when the invite is revoked
or expires. Tokens from the shared code keep their old form.

Writes are guarded separately: once REFLEX_ADMIN_KEY is set, every non-GET API request
(executor controls, TradFi markets, feature flags, watchlists, chat, backtests, scan
refresh...) must carry "X-Admin-Key: <key>", whether or not viewing is open. Login, the
usage beacon and an account's own lists (/api/me/, which need a wallet session instead;
accounts_api.py) are exempt. Until the variable is set nothing changes.
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
# The usage beacon (usage_api.py) checks the token in its body itself, since
# navigator.sendBeacon cannot send headers.
BEACON_PATH = "/api/usage/beacon"
PUBLIC_PATHS = frozenset({"/health", "/api/health", BEACON_PATH})


def enforced() -> bool:
    return bool(os.environ.get("REFLEX_ACCESS_CODE"))


def _secret() -> bytes:
    return (os.environ.get("REFLEX_AUTH_SECRET") or os.environ.get("REFLEX_ACCESS_CODE") or "").encode()


def check_code(code: str) -> bool:
    expected = os.environ.get("REFLEX_ACCESS_CODE", "")
    return bool(expected) and hmac.compare_digest(str(code).encode(), expected.encode())


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(now: Optional[float] = None, invite: Optional[str] = None) -> str:
    """``expires.sig`` for the shared code; ``expires.invite.sig`` for an invite."""
    expires = int((time.time() if now is None else now) + TOKEN_SECONDS)
    if invite:
        return f"{expires}.{invite}.{_sign(f'{expires}.{invite}')}"
    return f"{expires}.{_sign(str(expires))}"


def token_person(token: Optional[str], now: Optional[float] = None) -> Optional[str]:
    """Who a valid token belongs to: an invite id, or "shared" for the shared code. None when
    the token is not valid (bad signature, expired, or its invite revoked or expired)."""
    if not token or "." not in token or not _secret() or len(token) > 200:
        return None
    parts = token.split(".")
    if len(parts) == 2:
        expires, sig = parts
        payload, person = expires, "shared"
    elif len(parts) == 3:
        expires, person, sig = parts
        payload = f"{expires}.{person}"
    else:
        return None
    if not (hmac.compare_digest(sig.encode("utf-8", "replace"), _sign(payload).encode()) and expires.isdigit()
            and int(expires) > (time.time() if now is None else now)):
        return None
    if person != "shared":
        import invites
        if not invites.ID_RE.match(person) or not invites.active(person, now):
            return None
    return person


def token_valid(token: Optional[str], now: Optional[float] = None) -> bool:
    return token_person(token, now) is not None


def login(code: str, now: Optional[float] = None) -> Optional[str]:
    """A token for the shared code or an active invite code, else None."""
    if check_code(code):
        return issue_token(now)
    import invites
    inv = invites.match(code, now)
    if inv is None:
        return None
    invites.record_login(inv, now)
    return issue_token(now, invite=inv)


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
WRITE_EXEMPT = ("/api/auth/", "/api/me/", BEACON_PATH)


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
