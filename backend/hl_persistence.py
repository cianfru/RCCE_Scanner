"""
hl_persistence.py
~~~~~~~~~~~~~~~~~
SQLite persistence layer for HyperLens wallet data.

Persists snapshots, trade log, and position-first-seen across restarts.
Data survives Railway redeploys when using a persistent volume.

Tables:
  snapshots          — position history per wallet (positions stored as JSON)
  trade_log          — reconstructed trade events
  position_first_seen — when each position was first detected

On Railway, mount a persistent volume at /data and set
  HYPERLENS_DB_PATH=/data/hyperlens.db
For local dev, defaults to ./hyperlens.db in the backend directory.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("HYPERLENS_DB_PATH", str(Path(__file__).parent / "hyperlens.db"))

# Retention: how many days of snapshots to keep in DB
# In-memory deque stays at 300 (24h), but DB keeps 7 days for equity curves
_SNAPSHOT_RETENTION_DAYS = 30

# Max trade log entries per wallet in DB
_MAX_TRADES_PER_WALLET = 500

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,
    timestamp REAL NOT NULL,
    account_value REAL NOT NULL DEFAULT 0,
    positions_json TEXT NOT NULL,
    UNIQUE(address, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_snap_addr_ts ON snapshots(address, timestamp DESC);

CREATE TABLE IF NOT EXISTS trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,
    coin TEXT NOT NULL,
    side TEXT NOT NULL,
    size_usd REAL,
    entry_px REAL,
    leverage REAL,
    pnl REAL,
    pnl_pct REAL,
    opened_at REAL,
    closed_at REAL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tl_addr ON trade_log(address);

CREATE TABLE IF NOT EXISTS position_first_seen (
    address TEXT NOT NULL,
    coin TEXT NOT NULL,
    first_seen_at REAL NOT NULL,
    PRIMARY KEY (address, coin)
);
"""


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        db_dir = os.path.dirname(_DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")      # Better concurrent reads
        _conn.execute("PRAGMA synchronous=NORMAL")     # Faster writes, still safe
        _conn.execute("PRAGMA busy_timeout=5000")      # Wait up to 5s on locks
        _conn.executescript(_SCHEMA)
        _conn.commit()
        logger.info("HyperLens DB: opened at %s", _DB_PATH)
    return _conn


# ---------------------------------------------------------------------------
# Save operations (called after each poll)
# ---------------------------------------------------------------------------

def save_snapshots(snapshots_dict: Dict[str, deque]) -> int:
    """Persist latest snapshot for each wallet to DB.

    Only saves the most recent snapshot per wallet (the one just fetched).
    Returns number of snapshots saved.
    """
    conn = _get_conn()
    count = 0

    rows = []
    for address, snaps in snapshots_dict.items():
        if not snaps:
            continue
        latest = snaps[-1]
        # Serialize positions to JSON
        positions_data = []
        for p in latest.positions:
            positions_data.append(asdict(p))

        rows.append((
            address,
            latest.timestamp,
            latest.account_value,
            json.dumps(positions_data),
        ))

    if rows:
        try:
            conn.executemany(
                "INSERT OR IGNORE INTO snapshots (address, timestamp, account_value, positions_json) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            count = len(rows)
        except Exception as exc:
            logger.warning("HyperLens DB: snapshot save error: %s", exc)

    return count


def save_trade_events(trade_log: Dict[str, List[dict]], since_timestamp: float = 0) -> int:
    """Persist new trade events to DB.

    Args:
        trade_log: address -> list of trade dicts
        since_timestamp: only save trades with closed_at or opened_at > this timestamp

    Returns number of trades saved.
    """
    conn = _get_conn()
    count = 0

    rows = []
    for address, trades in trade_log.items():
        for t in trades:
            # Only save recent events (avoid re-inserting old ones)
            event_time = t.get("closed_at") or t.get("opened_at") or 0
            if event_time and event_time > since_timestamp:
                rows.append((
                    address,
                    t["coin"],
                    t["side"],
                    t.get("size_usd", 0),
                    t.get("entry_px", 0),
                    t.get("leverage", 0),
                    t.get("pnl", 0),
                    t.get("pnl_pct", 0),
                    t.get("opened_at"),
                    t.get("closed_at"),
                    t["status"],
                ))

    if rows:
        try:
            conn.executemany(
                "INSERT INTO trade_log "
                "(address, coin, side, size_usd, entry_px, leverage, pnl, pnl_pct, opened_at, closed_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            count = len(rows)
        except Exception as exc:
            logger.warning("HyperLens DB: trade save error: %s", exc)

    return count


def save_position_first_seen(first_seen: Dict[str, Dict[str, float]]) -> int:
    """Persist position first-seen timestamps (upsert)."""
    conn = _get_conn()
    count = 0

    rows = []
    for address, coins in first_seen.items():
        for coin, ts in coins.items():
            rows.append((address, coin, ts))

    if rows:
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO position_first_seen (address, coin, first_seen_at) "
                "VALUES (?, ?, ?)",
                rows,
            )
            conn.commit()
            count = len(rows)
        except Exception as exc:
            logger.warning("HyperLens DB: first_seen save error: %s", exc)

    return count


# ---------------------------------------------------------------------------
# Load operations (called on startup)
# ---------------------------------------------------------------------------

def load_snapshots(max_age_hours: int = 24) -> Dict[str, list]:
    """Load recent snapshots from DB.

    Args:
        max_age_hours: only load snapshots from the last N hours

    Returns: {address: [list of (timestamp, account_value, positions_list)]}
    """
    conn = _get_conn()
    cutoff = time.time() - (max_age_hours * 3600)

    result: Dict[str, list] = {}
    try:
        cursor = conn.execute(
            "SELECT address, timestamp, account_value, positions_json "
            "FROM snapshots WHERE timestamp > ? ORDER BY timestamp ASC",
            (cutoff,),
        )
        for address, ts, av, pos_json in cursor:
            try:
                positions = json.loads(pos_json)
            except (json.JSONDecodeError, TypeError):
                positions = []

            if address not in result:
                result[address] = []
            result[address].append({
                "timestamp": ts,
                "account_value": av,
                "positions": positions,
            })
    except Exception as exc:
        logger.warning("HyperLens DB: snapshot load error: %s", exc)

    logger.info("HyperLens DB: loaded snapshots for %d wallets (cutoff=%dh)", len(result), max_age_hours)
    return result


def load_trade_log() -> Dict[str, List[dict]]:
    """Load all trade events from DB.

    Returns: {address: [list of trade dicts]}
    """
    conn = _get_conn()
    result: Dict[str, List[dict]] = {}

    try:
        cursor = conn.execute(
            "SELECT address, coin, side, size_usd, entry_px, leverage, "
            "pnl, pnl_pct, opened_at, closed_at, status "
            "FROM trade_log ORDER BY id ASC"
        )
        for row in cursor:
            address = row[0]
            trade = {
                "coin": row[1],
                "side": row[2],
                "size_usd": row[3],
                "entry_px": row[4],
                "leverage": row[5],
                "pnl": row[6],
                "pnl_pct": row[7],
                "opened_at": row[8],
                "closed_at": row[9],
                "status": row[10],
            }
            if address not in result:
                result[address] = []
            result[address].append(trade)
    except Exception as exc:
        logger.warning("HyperLens DB: trade log load error: %s", exc)

    total = sum(len(v) for v in result.values())
    logger.info("HyperLens DB: loaded %d trades for %d wallets", total, len(result))
    return result


def load_position_first_seen() -> Dict[str, Dict[str, float]]:
    """Load position first-seen timestamps from DB.

    Returns: {address: {coin: timestamp}}
    """
    conn = _get_conn()
    result: Dict[str, Dict[str, float]] = {}

    try:
        cursor = conn.execute(
            "SELECT address, coin, first_seen_at FROM position_first_seen"
        )
        for address, coin, ts in cursor:
            if address not in result:
                result[address] = {}
            result[address][coin] = ts
    except Exception as exc:
        logger.warning("HyperLens DB: first_seen load error: %s", exc)

    total = sum(len(v) for v in result.values())
    logger.info("HyperLens DB: loaded %d position first-seen entries", total)
    return result


# ---------------------------------------------------------------------------
# Cleanup (called periodically)
# ---------------------------------------------------------------------------

def cleanup_old_data() -> dict:
    """Remove data older than retention period.

    Returns summary of rows deleted.
    """
    conn = _get_conn()
    cutoff = time.time() - (_SNAPSHOT_RETENTION_DAYS * 24 * 3600)
    deleted = {"snapshots": 0, "trades": 0}

    try:
        # Delete old snapshots
        cursor = conn.execute("DELETE FROM snapshots WHERE timestamp < ?", (cutoff,))
        deleted["snapshots"] = cursor.rowcount

        # Trim trade log: keep only last N per wallet
        # First get wallets with too many trades
        wallets = conn.execute(
            "SELECT address, COUNT(*) as cnt FROM trade_log "
            "GROUP BY address HAVING cnt > ?",
            (_MAX_TRADES_PER_WALLET,),
        ).fetchall()

        for address, cnt in wallets:
            excess = cnt - _MAX_TRADES_PER_WALLET
            conn.execute(
                "DELETE FROM trade_log WHERE id IN ("
                "  SELECT id FROM trade_log WHERE address = ? ORDER BY id ASC LIMIT ?"
                ")",
                (address, excess),
            )
            deleted["trades"] += excess

        # Clean up first_seen for positions that no longer exist
        # (old entries where the position was closed long ago)
        old_first_seen_cutoff = time.time() - (7 * 24 * 3600)  # 7 days
        cursor = conn.execute(
            "DELETE FROM position_first_seen WHERE first_seen_at < ?",
            (old_first_seen_cutoff,),
        )
        deleted["first_seen"] = cursor.rowcount

        conn.commit()

        if any(v > 0 for v in deleted.values()):
            logger.info("HyperLens DB cleanup: %s", deleted)

    except Exception as exc:
        logger.warning("HyperLens DB: cleanup error: %s", exc)

    return deleted


def get_db_stats() -> dict:
    """Get DB statistics for status endpoint."""
    conn = _get_conn()
    try:
        snap_count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        snap_wallets = conn.execute("SELECT COUNT(DISTINCT address) FROM snapshots").fetchone()[0]
        trade_count = conn.execute("SELECT COUNT(*) FROM trade_log").fetchone()[0]
        trade_wallets = conn.execute("SELECT COUNT(DISTINCT address) FROM trade_log").fetchone()[0]
        fs_count = conn.execute("SELECT COUNT(*) FROM position_first_seen").fetchone()[0]

        # Oldest/newest snapshot
        oldest = conn.execute("SELECT MIN(timestamp) FROM snapshots").fetchone()[0]
        newest = conn.execute("SELECT MAX(timestamp) FROM snapshots").fetchone()[0]

        # DB file size
        db_size_mb = os.path.getsize(_DB_PATH) / (1024 * 1024) if os.path.exists(_DB_PATH) else 0

        return {
            "db_path": _DB_PATH,
            "db_size_mb": round(db_size_mb, 2),
            "snapshots": snap_count,
            "snapshot_wallets": snap_wallets,
            "trades": trade_count,
            "trade_wallets": trade_wallets,
            "position_first_seen": fs_count,
            "oldest_snapshot": oldest,
            "newest_snapshot": newest,
            "retention_days": _SNAPSHOT_RETENTION_DAYS,
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Extended equity history (longer than in-memory deque)
# ---------------------------------------------------------------------------

def load_equity_history(address: str, days: int = 7) -> List[dict]:
    """Load extended equity curve from DB for a wallet.

    Returns up to `days` worth of AV history — much longer than the
    300-snapshot in-memory deque (~24h).
    """
    conn = _get_conn()
    cutoff = time.time() - (days * 24 * 3600)

    result = []
    try:
        cursor = conn.execute(
            "SELECT timestamp, account_value FROM snapshots "
            "WHERE address = ? AND timestamp > ? ORDER BY timestamp ASC",
            (address, cutoff),
        )
        for ts, av in cursor:
            if av > 0:
                result.append({"timestamp": ts, "value": round(av, 2)})
    except Exception as exc:
        logger.warning("HyperLens DB: equity history load error: %s", exc)

    return result


def load_full_trade_history(address: str, limit: int = 200) -> List[dict]:
    """Load extended trade history from DB for a wallet.

    Returns more trades than the in-memory 200-entry limit.
    """
    conn = _get_conn()
    result = []

    try:
        cursor = conn.execute(
            "SELECT coin, side, size_usd, entry_px, leverage, pnl, pnl_pct, "
            "opened_at, closed_at, status "
            "FROM trade_log WHERE address = ? ORDER BY id DESC LIMIT ?",
            (address, limit),
        )
        for row in cursor:
            result.append({
                "coin": row[0],
                "side": row[1],
                "size_usd": row[2],
                "entry_px": row[3],
                "leverage": row[4],
                "pnl": row[5],
                "pnl_pct": row[6],
                "opened_at": row[7],
                "closed_at": row[8],
                "status": row[9],
            })
    except Exception as exc:
        logger.warning("HyperLens DB: trade history load error: %s", exc)

    return result
