"""
SQLite-based time-series store for whale balance snapshots.

Periodically persists holder balances so we can compute
balance changes over 1d / 7d / 14d and detect accumulation
or distribution from real on-chain data.

Uses aiosqlite for async SQLite access.  DB file lives in the
same persist directory as whale_tracker.json.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from .config import SNAPSHOT_MIN_BALANCE_PCT, SNAPSHOT_RETENTION_DAYS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence directory (same as store.py)
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _PERSIST_DIR / "whale_snapshots.db"

# Time constants
_1D = 86400
_7D = 7 * 86400
_14D = 14 * 86400
# Tolerance: snapshots within ±3 hours of the target timestamp are acceptable
_SNAP_TOLERANCE = 3 * 3600


class SnapshotDB:
    """Async SQLite manager for holder balance snapshots."""

    _instance: Optional["SnapshotDB"] = None

    def __init__(self) -> None:
        self._db: Optional[aiosqlite.Connection] = None

    @classmethod
    def get(cls) -> "SnapshotDB":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def init(self) -> None:
        """Open database and create tables if needed."""
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(_DB_PATH))
        self._db.row_factory = aiosqlite.Row

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS holder_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                contract TEXT NOT NULL,
                address TEXT NOT NULL,
                balance REAL NOT NULL,
                pct_supply REAL NOT NULL DEFAULT 0.0,
                snapshot_ts INTEGER NOT NULL,
                UNIQUE(chain, contract, address, snapshot_ts)
            );
            CREATE INDEX IF NOT EXISTS idx_snap_lookup
                ON holder_snapshots(chain, contract, address, snapshot_ts);
            CREATE INDEX IF NOT EXISTS idx_snap_token_ts
                ON holder_snapshots(chain, contract, snapshot_ts);
        """)
        await self._db.commit()
        logger.info("Snapshot DB initialized at %s", _DB_PATH)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SnapshotDB not initialized — call init() first")
        return self._db

    # ── Save snapshot ─────────────────────────────────────────────────────

    async def save_snapshot(
        self,
        chain: str,
        contract: str,
        holders: List[Dict[str, Any]],
    ) -> int:
        """Persist a batch of holder balances as a point-in-time snapshot.

        Args:
            holders: list of dicts with keys: address, balance, pct_supply

        Returns:
            Number of rows inserted.
        """
        db = self._ensure_db()
        now = int(time.time())
        contract_key = contract.lower() if chain != "solana" else contract

        rows = []
        for h in holders:
            pct = h.get("pct_supply", 0.0)
            if pct < SNAPSHOT_MIN_BALANCE_PCT:
                continue
            rows.append((
                chain,
                contract_key,
                h["address"],
                h["balance"],
                pct,
                now,
            ))

        if not rows:
            return 0

        await db.executemany(
            """INSERT OR REPLACE INTO holder_snapshots
               (chain, contract, address, balance, pct_supply, snapshot_ts)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await db.commit()
        logger.info(
            "Saved %d holder snapshots for %s/%s",
            len(rows), chain, contract_key[:12],
        )
        return len(rows)

    # ── Query: holders with balance changes ───────────────────────────────

    async def get_holders_with_changes(
        self,
        chain: str,
        contract: str,
        min_pct: float = 0.0,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        """Get current holders enriched with 1d/7d/14d balance changes.

        Strategy:
        1. Get the most recent snapshot_ts for this token
        2. For each holder at that timestamp, look up the nearest snapshot
           to 1d/7d/14d ago and compute deltas
        3. Classify trend from the deltas

        Returns list of dicts with fields:
            address, balance, pct_supply, change_1d, change_7d, change_14d,
            change_1d_pct, change_7d_pct, change_14d_pct, trend
        """
        db = self._ensure_db()
        contract_key = contract.lower() if chain != "solana" else contract
        now = int(time.time())

        # Step 1: Get the latest snapshot timestamp for this token
        cursor = await db.execute(
            """SELECT MAX(snapshot_ts) FROM holder_snapshots
               WHERE chain = ? AND contract = ?""",
            (chain, contract_key),
        )
        row = await cursor.fetchone()
        if not row or row[0] is None:
            return []
        latest_ts = row[0]

        # Step 2: Get all holders at the latest snapshot
        cursor = await db.execute(
            """SELECT address, balance, pct_supply
               FROM holder_snapshots
               WHERE chain = ? AND contract = ? AND snapshot_ts = ?
               ORDER BY pct_supply DESC""",
            (chain, contract_key, latest_ts),
        )
        current_holders = await cursor.fetchall()
        if not current_holders:
            return []

        # Step 3: For each target period, find the nearest snapshot timestamp
        target_periods = {
            "1d": now - _1D,
            "7d": now - _7D,
            "14d": now - _14D,
        }

        # Pre-fetch historical snapshots for this token (batch query)
        # For each period, get all holder balances at the nearest snapshot
        historical: Dict[str, Dict[str, float]] = {}  # period -> {addr: balance}

        for period_key, target_ts in target_periods.items():
            # Find the snapshot timestamp closest to the target
            cursor = await db.execute(
                """SELECT snapshot_ts FROM holder_snapshots
                   WHERE chain = ? AND contract = ?
                     AND snapshot_ts BETWEEN ? AND ?
                   ORDER BY ABS(snapshot_ts - ?)
                   LIMIT 1""",
                (chain, contract_key,
                 target_ts - _SNAP_TOLERANCE, target_ts + _SNAP_TOLERANCE,
                 target_ts),
            )
            ts_row = await cursor.fetchone()
            if not ts_row:
                historical[period_key] = {}
                continue

            hist_ts = ts_row[0]
            # Don't use a historical snapshot that's actually the same as current
            if hist_ts == latest_ts:
                historical[period_key] = {}
                continue

            cursor = await db.execute(
                """SELECT address, balance FROM holder_snapshots
                   WHERE chain = ? AND contract = ? AND snapshot_ts = ?""",
                (chain, contract_key, hist_ts),
            )
            rows = await cursor.fetchall()
            historical[period_key] = {r[0]: r[1] for r in rows}

        # Step 4: Build result with changes
        results = []
        for h in current_holders:
            addr = h[0]
            balance = h[1]
            pct_supply = h[2]

            if min_pct > 0 and pct_supply < min_pct:
                continue

            record: Dict[str, Any] = {
                "address": addr,
                "balance": balance,
                "pct_supply": pct_supply,
            }

            # Compute changes for each period
            for period_key in ("1d", "7d", "14d"):
                hist_balance = historical[period_key].get(addr)
                if hist_balance is not None:
                    delta = balance - hist_balance
                    delta_pct = (
                        (delta / hist_balance * 100)
                        if hist_balance != 0
                        else (100.0 if delta > 0 else 0.0)
                    )
                    record[f"change_{period_key}"] = round(delta, 6)
                    record[f"change_{period_key}_pct"] = round(delta_pct, 2)
                else:
                    record[f"change_{period_key}"] = None
                    record[f"change_{period_key}_pct"] = None

            # Classify trend
            record["trend"] = self._classify_trend(record)
            results.append(record)

            if len(results) >= limit:
                break

        return results

    @staticmethod
    def _classify_trend(record: Dict[str, Any]) -> str:
        """Classify wallet trend from balance changes."""
        c7d = record.get("change_7d")
        c14d = record.get("change_14d")
        c7d_pct = record.get("change_7d_pct")

        # No historical data yet
        if c7d is None and c14d is None:
            return "NEW"

        # Both 7d and 14d point same direction → strong signal
        if c7d is not None and c14d is not None:
            if c7d > 0 and c14d > 0:
                return "ACCUMULATING"
            if c7d < 0 and c14d < 0:
                return "DISTRIBUTING"

        # Flat: less than 2% change over 7 days
        if c7d_pct is not None and abs(c7d_pct) < 2.0:
            return "HOLDING"

        # Single-direction from 7d
        if c7d is not None:
            if c7d > 0:
                return "ACCUMULATING"
            if c7d < 0:
                return "DISTRIBUTING"

        return "HOLDING"

    # ── Query: address history ────────────────────────────────────────────

    async def get_address_history(
        self,
        chain: str,
        contract: str,
        address: str,
        days: int = 14,
    ) -> List[Dict[str, Any]]:
        """Get balance time series for one wallet on one token.

        Returns list of {timestamp, balance, pct_supply} ordered chronologically.
        """
        db = self._ensure_db()
        contract_key = contract.lower() if chain != "solana" else contract
        addr_key = address.lower() if chain != "solana" else address
        cutoff = int(time.time()) - (days * 86400)

        cursor = await db.execute(
            """SELECT snapshot_ts, balance, pct_supply
               FROM holder_snapshots
               WHERE chain = ? AND contract = ? AND address = ?
                 AND snapshot_ts >= ?
               ORDER BY snapshot_ts ASC""",
            (chain, contract_key, addr_key, cutoff),
        )
        rows = await cursor.fetchall()
        return [
            {
                "timestamp": r[0],
                "balance": r[1],
                "pct_supply": r[2],
            }
            for r in rows
        ]

    # ── Query: last snapshot timestamp per token ──────────────────────────

    async def get_last_snapshot_ts(
        self, chain: str, contract: str
    ) -> Optional[int]:
        """Get the timestamp of the most recent snapshot for a token."""
        db = self._ensure_db()
        contract_key = contract.lower() if chain != "solana" else contract
        cursor = await db.execute(
            """SELECT MAX(snapshot_ts) FROM holder_snapshots
               WHERE chain = ? AND contract = ?""",
            (chain, contract_key),
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None

    # ── Cleanup ───────────────────────────────────────────────────────────

    async def cleanup_old(self, days: Optional[int] = None) -> int:
        """Delete snapshots older than retention period.

        Returns number of rows deleted.
        """
        db = self._ensure_db()
        retention = days if days is not None else SNAPSHOT_RETENTION_DAYS
        cutoff = int(time.time()) - (retention * 86400)

        cursor = await db.execute(
            "DELETE FROM holder_snapshots WHERE snapshot_ts < ?",
            (cutoff,),
        )
        await db.commit()
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info("Cleaned up %d old snapshots (older than %dd)", deleted, retention)
        return deleted
