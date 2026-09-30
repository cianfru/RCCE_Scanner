"""
Per-person invite codes, next to the one shared access code (access.py).

The owner creates a code with a label (the person's name) and, optionally, an expiry,
from the Intel page. The login screen takes it like the shared code; the token issued
at login carries the invite's id, so every session is attributed to that person.
Revoking a code (or reaching its expiry) ends the sessions it opened.

Ids of people that are not invites: "shared" (the shared access code) and "open" (the
API while no access code is configured).
"""
from __future__ import annotations

import re
import secrets
import time
from typing import Dict, List, Optional, Tuple

import usage_db as db

SHARED = "shared"
OPEN = "open"
ID_RE = re.compile(r"^[0-9a-f]{8}$")
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LABEL_MAX = 40

_state: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]] = None   # id -> (expires, revoked)


def forget() -> None:
    global _state
    _state = None


def _load() -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    global _state
    with db.lock:
        if _state is None:
            _state = {i: (e, r) for i, e, r in db.q("SELECT id, expires, revoked FROM invites")}
        return _state


def key(code: str) -> str:
    """Codes compare without case, spaces or dashes."""
    return re.sub(r"[^0-9A-Z]", "", str(code or "").upper())


def _new_code() -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"RFX-{body[:4]}-{body[4:]}"


def create(label: str, expires: Optional[float] = None, now: Optional[float] = None) -> dict:
    now = now or time.time()
    label = " ".join(str(label or "").split())[:LABEL_MAX]
    if not label:
        raise ValueError("label")
    if expires is not None and expires <= now:
        raise ValueError("expires")
    with db.lock:
        while True:
            inv, code = secrets.token_hex(4), _new_code()
            if not db.q("SELECT 1 FROM invites WHERE id = ? OR code_key = ?", (inv, key(code))):
                break
        db.x("INSERT INTO invites (id, label, code, code_key, created, expires) VALUES (?, ?, ?, ?, ?, ?)",
             (inv, label, code, key(code), now, expires))
        forget()
    return get(inv)


def revoke(inv: str, now: Optional[float] = None) -> bool:
    with db.lock:
        n = db.x("UPDATE invites SET revoked = ? WHERE id = ? AND revoked IS NULL", (now or time.time(), inv))
        forget()
    return n > 0


def active(inv: str, now: Optional[float] = None) -> bool:
    """Whether sessions opened with this invite are still good (exists, not revoked or expired)."""
    st = _load().get(inv)
    if st is None:
        return False
    expires, revoked = st
    return revoked is None and (expires is None or expires > (now or time.time()))


def match(code: str, now: Optional[float] = None) -> Optional[str]:
    """The id of the active invite with this code, or None."""
    k = key(code)
    if len(k) < 8:
        return None
    row = db.q("SELECT id FROM invites WHERE code_key = ?", (k,))
    return row[0][0] if row and active(row[0][0], now) else None


def record_login(inv: str, now: Optional[float] = None) -> None:
    now = now or time.time()
    db.x("UPDATE invites SET logins = logins + 1, last_login = ?, first_login = COALESCE(first_login, ?) "
         "WHERE id = ?", (now, now, inv))


_COLS = ("id", "label", "code", "created", "expires", "revoked", "first_login", "last_login", "logins")


def get(inv: str) -> Optional[dict]:
    row = db.q(f"SELECT {', '.join(_COLS)} FROM invites WHERE id = ?", (inv,))
    return dict(zip(_COLS, row[0])) if row else None


def all_invites() -> List[dict]:
    return [dict(zip(_COLS, r)) for r in db.q(f"SELECT {', '.join(_COLS)} FROM invites ORDER BY created DESC")]


def labels() -> Dict[str, str]:
    out = {i: l for i, l in db.q("SELECT id, label FROM invites")}
    out[SHARED] = "shared code"
    out[OPEN] = "open access"
    return out
