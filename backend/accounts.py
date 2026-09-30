"""
User accounts, keyed by wallet address: follows, the Radar watch list and a Telegram chat
per user. Off unless REFLEX_ACCOUNTS is set; with it off nothing here is read or written
and the app keeps its single-owner lists.

The owner's account (REFLEX_OWNER_ADDRESS) is the existing single-owner data: its follows
are followed_traders.json, its watch list watched_coins.json and its Telegram chat the
bot's allowed chats, so nothing is copied and the owner's alerts keep working as before.
Every other account lives in one SQLite file on the data volume (accounts.db).

Followed wallets are read once for everyone: ``followed_union`` feeds the wallet poller
(through followed_traders.addresses) and user_alerts fans each change out per user.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
TRUE = ("1", "true", "on", "yes")


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


def enabled() -> bool:
    return os.environ.get("REFLEX_ACCOUNTS", "").strip().lower() in TRUE


def follow_cap() -> int:
    return _env_int("REFLEX_FOLLOW_CAP", 10)


def watch_cap() -> int:
    return _env_int("REFLEX_WATCH_CAP", 30)


def owner() -> Optional[str]:
    a = os.environ.get("REFLEX_OWNER_ADDRESS", "").strip().lower()
    return a if ADDRESS_RE.match(a) else None


def is_owner(address: Optional[str]) -> bool:
    return bool(address) and address.lower() == owner()


def valid_address(address) -> bool:
    return isinstance(address, str) and bool(ADDRESS_RE.match(address.strip()))


# ------------------------------------------------------------------ storage
_dir = Path(os.environ["RAILWAY_VOLUME_MOUNT_PATH"]) if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") \
    else Path(__file__).resolve().parent / "data"
PATH = _dir / "accounts.db"
_conn: Optional[sqlite3.Connection] = None
_lock = threading.RLock()
_union: Optional[Set[str]] = None          # every wallet some account follows (cache)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (address TEXT PRIMARY KEY, created REAL, last_seen REAL);
CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, address TEXT, domain TEXT, issued REAL, expires REAL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, address TEXT, created REAL, expires REAL);
CREATE INDEX IF NOT EXISTS sessions_address ON sessions (address);
CREATE TABLE IF NOT EXISTS follows (user TEXT, wallet TEXT, note TEXT, added REAL, PRIMARY KEY (user, wallet));
CREATE INDEX IF NOT EXISTS follows_wallet ON follows (wallet);
CREATE TABLE IF NOT EXISTS watch (user TEXT, coin TEXT, tf TEXT, added REAL, PRIMARY KEY (user, coin));
CREATE TABLE IF NOT EXISTS tg (user TEXT PRIMARY KEY, chat_id INTEGER UNIQUE, linked REAL, state TEXT);
CREATE TABLE IF NOT EXISTS tg_codes (code TEXT PRIMARY KEY, user TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS wallet_events (wallet TEXT, ts REAL, body TEXT);
CREATE INDEX IF NOT EXISTS wallet_events_wallet ON wallet_events (wallet, ts);
"""


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(PATH), check_same_thread=False, isolation_level=None)
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
        return _conn


def use_path(path) -> None:
    """Point storage at another file (tests)."""
    global PATH, _conn, _union
    with _lock:
        if _conn is not None:
            _conn.close()
        PATH, _conn, _union = Path(path), None, None


def _q(sql: str, args: Iterable = ()) -> List[tuple]:
    with _lock:
        return conn().execute(sql, tuple(args)).fetchall()


def _x(sql: str, args: Iterable = ()) -> int:
    with _lock:
        return conn().execute(sql, tuple(args)).rowcount


# ------------------------------------------------------------------ users
def ensure_user(address: str, now: Optional[float] = None) -> None:
    now = now or time.time()
    a = address.lower()
    with _lock:
        _x("INSERT OR IGNORE INTO users (address, created, last_seen) VALUES (?, ?, ?)", (a, now, now))
        _x("UPDATE users SET last_seen = ? WHERE address = ?", (now, a))


def user_exists(address: str) -> bool:
    return bool(_q("SELECT 1 FROM users WHERE address = ?", (address.lower(),)))


def user_count() -> int:
    return _q("SELECT COUNT(*) FROM users")[0][0]


# ------------------------------------------------------------------ follows
def follows(user: str) -> Dict[str, dict]:
    rows = _q("SELECT wallet, note, added FROM follows WHERE user = ? ORDER BY added", (user.lower(),))
    return {w: {"note": n or "", "added": a} for w, n, a in rows}


def follow(user: str, wallet: str, note: str = "", now: Optional[float] = None) -> str:
    """"added", "exists" or "cap" (at most follow_cap() wallets per account)."""
    global _union
    u, w = user.lower(), wallet.lower()
    with _lock:
        if _q("SELECT 1 FROM follows WHERE user = ? AND wallet = ?", (u, w)):
            return "exists"
        if _q("SELECT COUNT(*) FROM follows WHERE user = ?", (u,))[0][0] >= follow_cap():
            return "cap"
        _x("INSERT INTO follows (user, wallet, note, added) VALUES (?, ?, ?, ?)",
           (u, w, str(note or "")[:80], now or time.time()))
        _union = None
    return "added"


def unfollow(user: str, wallet: str) -> bool:
    global _union
    with _lock:
        n = _x("DELETE FROM follows WHERE user = ? AND wallet = ?", (user.lower(), wallet.lower()))
        _union = None
    return n > 0


def followers_of(wallet: str) -> List[Tuple[str, str]]:
    """(user, note) for every account following the wallet."""
    return [(u, n or "") for u, n in _q("SELECT user, note FROM follows WHERE wallet = ?", (wallet.lower(),))]


def followed_union() -> Set[str]:
    """Every wallet some account follows (empty when accounts are off). Kept in memory."""
    global _union
    if not enabled():
        return set()
    with _lock:
        if _union is None:
            _union = {w for (w,) in _q("SELECT DISTINCT wallet FROM follows")}
        return set(_union)


# ------------------------------------------------------------------ watch list (the Radar's Watch)
def watch_list(user: str) -> Dict[str, dict]:
    rows = _q("SELECT coin, tf, added FROM watch WHERE user = ? ORDER BY added", (user.lower(),))
    return {c: {"tf": tf, "added": a} for c, tf, a in rows}


def watch(user: str, coin: str, tf: str = "1d", now: Optional[float] = None) -> str:
    """"added", "exists" (timeframe updated) or "cap"."""
    u = user.lower()
    tf = tf if tf in ("4h", "1d") else "1d"
    with _lock:
        if _q("SELECT 1 FROM watch WHERE user = ? AND coin = ?", (u, coin)):
            _x("UPDATE watch SET tf = ? WHERE user = ? AND coin = ?", (tf, u, coin))
            return "exists"
        if _q("SELECT COUNT(*) FROM watch WHERE user = ?", (u,))[0][0] >= watch_cap():
            return "cap"
        _x("INSERT INTO watch (user, coin, tf, added) VALUES (?, ?, ?, ?)", (u, coin, tf, now or time.time()))
    return "added"


def unwatch(user: str, coin: str) -> bool:
    return _x("DELETE FROM watch WHERE user = ? AND coin = ?", (user.lower(), coin)) > 0


def all_watch() -> Dict[str, Dict[str, dict]]:
    out: Dict[str, Dict[str, dict]] = {}
    for u, c, tf in _q("SELECT user, coin, tf FROM watch"):
        out.setdefault(u, {})[c] = {"tf": tf}
    return out


# ------------------------------------------------------------------ Telegram
CODE_S = 15 * 60
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def tg_code(user: str, now: Optional[float] = None) -> Tuple[str, float]:
    """A one-time code the user sends to the bot as /start <code>. Replaces any earlier one."""
    now = now or time.time()
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(10))
    expires = now + CODE_S
    with _lock:
        _x("DELETE FROM tg_codes WHERE user = ? OR expires < ?", (user.lower(), now))
        _x("INSERT INTO tg_codes (code, user, expires) VALUES (?, ?, ?)", (code, user.lower(), expires))
    return code, expires


def tg_claim(code: str, chat_id: int, now: Optional[float] = None) -> Optional[str]:
    """Bind the chat to the code's account (once; the code is used up). Returns the address."""
    now = now or time.time()
    code = str(code or "").strip().upper()
    with _lock:
        row = _q("SELECT user, expires FROM tg_codes WHERE code = ?", (code,))
        if not row:
            return None
        _x("DELETE FROM tg_codes WHERE code = ?", (code,))
        user, expires = row[0]
        if expires < now:
            return None
        # One chat, one account: a chat linked elsewhere moves here.
        _x("UPDATE tg SET chat_id = NULL WHERE chat_id = ? AND user != ?", (int(chat_id), user))
        if _q("SELECT 1 FROM tg WHERE user = ?", (user,)):
            _x("UPDATE tg SET chat_id = ?, linked = ? WHERE user = ?", (int(chat_id), now, user))
        else:
            _x("INSERT INTO tg (user, chat_id, linked, state) VALUES (?, ?, ?, NULL)", (user, int(chat_id), now))
    return user


def tg_chat(user: str) -> Optional[int]:
    row = _q("SELECT chat_id FROM tg WHERE user = ?", (user.lower(),))
    return int(row[0][0]) if row and row[0][0] is not None else None


def tg_user_of(chat_id: int) -> Optional[str]:
    row = _q("SELECT user FROM tg WHERE chat_id = ?", (int(chat_id),))
    return row[0][0] if row else None


def tg_unlink(user: Optional[str] = None, chat_id: Optional[int] = None) -> bool:
    if user:
        return _x("UPDATE tg SET chat_id = NULL WHERE user = ? AND chat_id IS NOT NULL", (user.lower(),)) > 0
    if chat_id is not None:
        return _x("UPDATE tg SET chat_id = NULL WHERE chat_id = ?", (int(chat_id),)) > 0
    return False


def tg_linked() -> List[Tuple[str, int]]:
    """(user, chat_id) for every account with a linked chat."""
    return [(u, int(c)) for u, c in _q("SELECT user, chat_id FROM tg WHERE chat_id IS NOT NULL")]


def tg_state(user: str) -> Optional[dict]:
    row = _q("SELECT state FROM tg WHERE user = ?", (user.lower(),))
    if not row or not row[0][0]:
        return None
    try:
        return json.loads(row[0][0])
    except ValueError:
        return None


def tg_save_state(user: str, state: dict) -> None:
    body = json.dumps(state)
    with _lock:
        if not _x("UPDATE tg SET state = ? WHERE user = ?", (body, user.lower())):
            _x("INSERT INTO tg (user, chat_id, linked, state) VALUES (?, NULL, NULL, ?)", (user.lower(), body))


# ------------------------------------------------------------------ changes of followed wallets
EVENTS_KEEP_S = 7 * 86400


def record_events(wallet: str, cohort: str, ts: float, changes: List[dict]) -> None:
    w = wallet.lower()
    with _lock:
        for c in changes:
            _x("INSERT INTO wallet_events (wallet, ts, body) VALUES (?, ?, ?)",
               (w, ts, json.dumps({"address": w, "cohort": cohort, "ts": ts, **c})))
        _x("DELETE FROM wallet_events WHERE ts < ?", (ts - EVENTS_KEEP_S,))


def events_for(wallets: Iterable[str], limit: int = 50) -> List[dict]:
    ws = [w.lower() for w in wallets]
    if not ws:
        return []
    marks = ",".join("?" * len(ws))
    rows = _q(f"SELECT body FROM wallet_events WHERE wallet IN ({marks}) ORDER BY ts DESC LIMIT ?", (*ws, int(limit)))
    return [json.loads(b) for (b,) in rows]
