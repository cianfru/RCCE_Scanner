"""
auth.py — Sign-In-With-Ethereum (SIWE) wallet authentication.

Wallet = account. No email, no passwords. Flow:

  1. GET  /api/auth/nonce?address=0x..   → server returns a message to sign
  2. the user signs that message in their wallet (Rabby / MetaMask)
  3. POST /api/auth/verify {address, signature}
        → server recovers the signer, checks it matches, and returns a JWT

Subsequent requests carry `Authorization: Bearer <jwt>`; `verify_session()`
returns the authenticated wallet address (the user's account id).

Security notes
--------------
* Nonces are single-use and expire after 10 min — a signature can't be replayed.
* The signed message is generated and stored server-side, so the client can't
  substitute a different message.
* Sessions are stateless JWTs signed with SESSION_SECRET (HS256).
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Dict, Optional, Tuple

import jwt
from eth_account import Account
from eth_account.messages import encode_defunct

logger = logging.getLogger("auth")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_SESSION_SECRET = os.environ.get("SESSION_SECRET", "").strip()
if not _SESSION_SECRET:
    _SESSION_SECRET = secrets.token_hex(32)
    logger.warning(
        "SESSION_SECRET not set — using a random per-process secret; "
        "user sessions reset on every restart. Set SESSION_SECRET to persist them."
    )

_SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", str(7 * 24 * 3600)))  # 7 days
_NONCE_TTL = 600  # 10 minutes
_DOMAIN = os.environ.get("AUTH_DOMAIN", "reflex.app")

# address(lower) -> (message, expiry_ts)
_nonces: Dict[str, Tuple[str, float]] = {}


# ---------------------------------------------------------------------------
# Nonce / message
# ---------------------------------------------------------------------------

def _prune() -> None:
    now = time.time()
    stale = [a for a, (_, exp) in _nonces.items() if exp < now]
    for a in stale:
        _nonces.pop(a, None)


def build_nonce_message(address: str) -> str:
    """Generate and store a one-time sign-in message for ``address``."""
    address = address.lower()
    nonce = secrets.token_hex(16)
    issued = int(time.time())
    message = (
        f"{_DOMAIN} wants you to sign in with your Ethereum account:\n"
        f"{address}\n\n"
        f"Sign in to Reflex. This request will not trigger a blockchain "
        f"transaction or cost any gas.\n\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued}"
    )
    _prune()
    _nonces[address] = (message, time.time() + _NONCE_TTL)
    return message


def verify_signature(address: str, signature: str) -> bool:
    """Verify ``signature`` over the stored nonce message for ``address``.

    Consumes the nonce on success (single-use).
    """
    address = address.lower()
    entry = _nonces.get(address)
    if not entry:
        return False
    message, expiry = entry
    if expiry < time.time():
        _nonces.pop(address, None)
        return False
    try:
        recovered = Account.recover_message(
            encode_defunct(text=message), signature=signature
        )
    except Exception as exc:
        logger.warning("Signature recovery failed: %s", exc)
        return False
    if recovered.lower() != address:
        return False
    _nonces.pop(address, None)  # single-use
    return True


# ---------------------------------------------------------------------------
# Session tokens (stateless JWT)
# ---------------------------------------------------------------------------

def issue_session(address: str) -> str:
    address = address.lower()
    now = int(time.time())
    payload = {"sub": address, "iat": now, "exp": now + _SESSION_TTL}
    return jwt.encode(payload, _SESSION_SECRET, algorithm="HS256")


def verify_session(token: str) -> Optional[str]:
    """Return the wallet address for a valid session token, else None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, _SESSION_SECRET, algorithms=["HS256"])
        sub = payload.get("sub")
        return sub.lower() if isinstance(sub, str) else None
    except Exception:
        return None
