"""
The one SQLite file behind invites and usage counts (usage.db on the data volume).

Tables
  invites   one row per invite code: label, code, expiry, revoked, logins
  people    one row per person (an invite id, "shared" or "open"): first and last seen,
            whether a wallet was signed in and Telegram linked
  sessions  one row per app session: day, start, last event, event count, country, city,
            device class and browser family
  activity  (person, day) for every day a person used the app
  counts    per day, person and event: how many times (a count, not a click log)

Nothing here holds an IP address, a user agent string or a wallet address.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Iterable, List, Optional

_dir = Path(os.environ["RAILWAY_VOLUME_MOUNT_PATH"]) if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") \
    else Path(__file__).resolve().parent / "data"
PATH = _dir / "usage.db"
_conn: Optional[sqlite3.Connection] = None
lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (id TEXT PRIMARY KEY, label TEXT, code TEXT, code_key TEXT UNIQUE,
  created REAL, expires REAL, revoked REAL, first_login REAL, last_login REAL, logins INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS people (person TEXT PRIMARY KEY, first_seen REAL, last_seen REAL,
  wallet INTEGER DEFAULT 0, telegram INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, person TEXT, day TEXT, start REAL, last REAL,
  n INTEGER DEFAULT 0, country TEXT, city TEXT, device TEXT, browser TEXT);
CREATE INDEX IF NOT EXISTS sessions_person ON sessions (person, start);
CREATE INDEX IF NOT EXISTS sessions_day ON sessions (day);
CREATE TABLE IF NOT EXISTS activity (person TEXT, day TEXT, PRIMARY KEY (person, day));
CREATE INDEX IF NOT EXISTS activity_day ON activity (day);
CREATE TABLE IF NOT EXISTS counts (day TEXT, person TEXT, name TEXT, v TEXT, n INTEGER,
  PRIMARY KEY (day, person, name, v));
"""


def conn() -> sqlite3.Connection:
    global _conn
    with lock:
        if _conn is None:
            PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(PATH), check_same_thread=False, isolation_level=None)
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
        return _conn


def use_path(path) -> None:
    """Point storage at another file (tests)."""
    global PATH, _conn
    with lock:
        if _conn is not None:
            _conn.close()
        PATH, _conn = Path(path), None
    try:
        import invites
        invites.forget()
    except ImportError:
        pass


def q(sql: str, args: Iterable = ()) -> List[tuple]:
    with lock:
        return conn().execute(sql, tuple(args)).fetchall()


def x(sql: str, args: Iterable = ()) -> int:
    with lock:
        return conn().execute(sql, tuple(args)).rowcount
