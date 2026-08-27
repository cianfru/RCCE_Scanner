"""
user_store.py — wallet-keyed accounts + per-user data (SQLite).

The wallet address is the account id. This is the multi-tenant store that
replaces the single-user JSON files as the app moves to wallet login.

MVP scope: accounts + per-user favorites. Watchlists / groups / settings
migrate onto the same pattern next. SQLite (aiosqlite, already a dependency)
on the Railway volume — zero new infrastructure; move to Postgres if it scales.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import List, Optional

import aiosqlite

logger = logging.getLogger("user_store")

_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _DIR.is_dir():
    _DIR = Path(__file__).resolve().parent / "data"
_DIR.mkdir(parents=True, exist_ok=True)
_DB = str(_DIR / "users.db")


async def init() -> None:
    async with aiosqlite.connect(_DB) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "  address TEXT PRIMARY KEY,"
            "  created_at REAL,"
            "  last_login REAL"
            ")"
        )
        await db.execute(
            "CREATE TABLE IF NOT EXISTS user_favorites ("
            "  address TEXT,"
            "  symbol TEXT,"
            "  created_at REAL,"
            "  PRIMARY KEY (address, symbol)"
            ")"
        )
        await db.commit()
    logger.info("user_store initialized at %s", _DB)


async def upsert_user(address: str) -> None:
    """Create the account on first login, else bump last_login."""
    address = address.lower()
    now = time.time()
    async with aiosqlite.connect(_DB) as db:
        await db.execute(
            "INSERT INTO users(address, created_at, last_login) VALUES(?,?,?) "
            "ON CONFLICT(address) DO UPDATE SET last_login=excluded.last_login",
            (address, now, now),
        )
        await db.commit()


async def get_user(address: str) -> Optional[dict]:
    address = address.lower()
    async with aiosqlite.connect(_DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT address, created_at, last_login FROM users WHERE address=?",
            (address,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_favorites(address: str) -> List[str]:
    address = address.lower()
    async with aiosqlite.connect(_DB) as db:
        async with db.execute(
            "SELECT symbol FROM user_favorites WHERE address=? ORDER BY created_at",
            (address,),
        ) as cur:
            return [r[0] for r in await cur.fetchall()]


async def add_favorite(address: str, symbol: str) -> None:
    address = address.lower()
    async with aiosqlite.connect(_DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_favorites(address, symbol, created_at) VALUES(?,?,?)",
            (address, symbol, time.time()),
        )
        await db.commit()


async def remove_favorite(address: str, symbol: str) -> None:
    address = address.lower()
    async with aiosqlite.connect(_DB) as db:
        await db.execute(
            "DELETE FROM user_favorites WHERE address=? AND symbol=?",
            (address, symbol),
        )
        await db.commit()
