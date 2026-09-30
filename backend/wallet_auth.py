"""
Sign-in with a wallet (EIP-4361 "Sign-In with Ethereum" message) and account sessions.

1. The app asks for a message: ``issue`` stores a one-time nonce for the address and
   returns the message text, bound to the app's domain and valid for ten minutes.
2. The wallet signs it (personal_sign); ``verify`` checks the text, the domain, the
   expiry, the signature (eth-account) and uses the nonce up.
3. ``start_session`` returns a token the app sends as the X-Reflex-Session header.

A header token (not a cookie) because the app and the API are on different sites, the
same way the access-code token already travels.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import accounts

NONCE_S = 10 * 60
SKEW_S = 5 * 60
HEADER = "x-reflex-session"
STATEMENT = "Sign in to Reflex. This signs a message only: no transaction, no fee."


class AuthError(Exception):
    """Sign-in refused; ``reason`` is one of: format, domain, expired, nonce, signature."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def session_days() -> int:
    try:
        return max(1, int(os.environ.get("REFLEX_SESSION_DAYS", 30)))
    except ValueError:
        return 30


def allowed_domains() -> set:
    """The app's host names (REFLEX_SIWE_DOMAINS, comma separated; otherwise the host of
    REFLEX_APP_URL and its www. form)."""
    raw = os.environ.get("REFLEX_SIWE_DOMAINS", "").strip()
    if raw:
        return {d.strip().lower() for d in raw.split(",") if d.strip()}
    host = urlparse(os.environ.get("REFLEX_APP_URL", "https://reflexsignal.xyz")).netloc.lower()
    if not host:
        return set()
    bare = host[4:] if host.startswith("www.") else host
    return {bare, "www." + bare}


# ------------------------------------------------------------------ the message
def _iso(ts: float) -> str:
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_iso(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def checksum(address: str) -> str:
    from eth_utils import to_checksum_address
    return to_checksum_address(address)


def build_message(address: str, domain: str, nonce: str, issued: float, expires: float,
                  chain_id: int = 1) -> str:
    return (f"{domain} wants you to sign in with your Ethereum account:\n"
            f"{checksum(address)}\n\n"
            f"{STATEMENT}\n\n"
            f"URI: https://{domain}\n"
            f"Version: 1\n"
            f"Chain ID: {int(chain_id)}\n"
            f"Nonce: {nonce}\n"
            f"Issued At: {_iso(issued)}\n"
            f"Expiration Time: {_iso(expires)}")


_MESSAGE = re.compile(
    r"^(?P<domain>[a-z0-9.\-:]+) wants you to sign in with your Ethereum account:\n"
    r"(?P<address>0x[0-9a-fA-F]{40})\n\n"
    r"(?P<statement>[^\n]*)\n\n"
    r"URI: (?P<uri>[^\n]+)\n"
    r"Version: 1\n"
    r"Chain ID: (?P<chain>\d{1,12})\n"
    r"Nonce: (?P<nonce>[A-Za-z0-9]{8,64})\n"
    r"Issued At: (?P<issued>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\n"
    r"Expiration Time: (?P<expires>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)$")


def parse_message(message: str) -> dict:
    m = _MESSAGE.match(message or "")
    if not m:
        raise AuthError("format")
    try:
        f = dict(m.groupdict(), issued=_from_iso(m["issued"]), expires=_from_iso(m["expires"]),
                 chain=int(m["chain"]))
    except ValueError:
        raise AuthError("format")
    # Only the exact text this server writes is accepted.
    if build_message(f["address"], f["domain"], f["nonce"], f["issued"], f["expires"], f["chain"]) != message:
        raise AuthError("format")
    return f


# ------------------------------------------------------------------ issue and verify
def issue(address: str, domain: str, chain_id: int = 1, now: Optional[float] = None) -> Dict:
    """A sign-in message for the address on this domain, with a fresh one-time nonce."""
    now = now or time.time()
    if not accounts.valid_address(address):
        raise AuthError("format")
    domain = str(domain or "").strip().lower()
    if domain not in allowed_domains():
        raise AuthError("domain")
    nonce = secrets.token_hex(16)
    expires = now + NONCE_S
    accounts._x("DELETE FROM nonces WHERE expires < ?", (now,))
    accounts._x("INSERT INTO nonces (nonce, address, domain, issued, expires) VALUES (?, ?, ?, ?, ?)",
                (nonce, address.lower(), domain, now, expires))
    return {"message": build_message(address, domain, nonce, now, expires, chain_id), "expires": expires}


def recover(message: str, signature: str) -> str:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    try:
        return Account.recover_message(encode_defunct(text=message), signature=signature).lower()
    except Exception:
        raise AuthError("signature")


def verify(message: str, signature: str, now: Optional[float] = None) -> str:
    """The signing address, or AuthError. Each nonce signs in once."""
    now = now or time.time()
    f = parse_message(message)
    if f["domain"] not in allowed_domains() or f["uri"] != f"https://{f['domain']}":
        raise AuthError("domain")
    if f["expires"] <= now or f["issued"] > now + SKEW_S:
        raise AuthError("expired")
    address = f["address"].lower()
    if recover(message, str(signature or "")) != address:
        raise AuthError("signature")
    with accounts._lock:
        row = accounts._q("SELECT address, domain, expires FROM nonces WHERE nonce = ?", (f["nonce"],))
        if not row or row[0][0] != address or row[0][1] != f["domain"]:
            raise AuthError("nonce")
        accounts._x("DELETE FROM nonces WHERE nonce = ?", (f["nonce"],))
    if row[0][2] <= now:
        raise AuthError("expired")
    return address


# ------------------------------------------------------------------ sessions
_cache: Dict[str, Tuple[str, float]] = {}
_CACHE_MAX = 5000


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(address: str, now: Optional[float] = None) -> Tuple[str, float]:
    now = now or time.time()
    accounts.ensure_user(address, now)
    token = secrets.token_urlsafe(32)
    expires = now + session_days() * 86400
    accounts._x("DELETE FROM sessions WHERE expires < ?", (now,))
    accounts._x("INSERT INTO sessions (token_hash, address, created, expires) VALUES (?, ?, ?, ?)",
                (_hash(token), address.lower(), now, expires))
    return token, expires


def session_address(token: Optional[str], now: Optional[float] = None) -> Optional[str]:
    """The signed-in address for a session token, or None (unknown, ended or expired)."""
    if not token or len(token) > 200:
        return None
    now = now or time.time()
    h = _hash(token)
    hit = _cache.get(h)
    if hit is None:
        row = accounts._q("SELECT address, expires FROM sessions WHERE token_hash = ?", (h,))
        if not row:
            return None
        hit = (row[0][0], row[0][1])
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[h] = hit
    return hit[0] if hit[1] > now else None


def end_session(token: Optional[str]) -> bool:
    if not token:
        return False
    h = _hash(token)
    _cache.pop(h, None)
    return accounts._x("DELETE FROM sessions WHERE token_hash = ?", (h,)) > 0


def request_address(headers) -> Optional[str]:
    """The signed-in address of a request (accounts on and a live session), else None."""
    if not accounts.enabled():
        return None
    return session_address(headers.get(HEADER))
