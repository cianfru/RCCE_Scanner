"""
signal_log.py
~~~~~~~~~~~~~
SQLite-based signal persistence for tracking signal transitions and
measuring historical accuracy.

Logs every signal *change* (not every scan tick) with full context,
then back-fills outcome columns (price_1d, price_3d, price_7d) as
time passes.  Supports:
  - Paginated signal history
  - Per-signal-type win-rate scorecard
  - Recent signal changes feed

Uses aiosqlite for async SQLite access.  DB file lives in backend/data/.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence directory
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).resolve().parent / "data"
_DB_PATH = _PERSIST_DIR / "signal_events.db"

# Time constants
_1D = 86_400
_3D = 3 * 86_400
_7D = 7 * 86_400
_OUTCOME_TOLERANCE = 2 * 3600  # ±2h window for outcome lookup


class SignalLog:
    """Async SQLite manager for signal event persistence."""

    _instance: Optional["SignalLog"] = None

    def __init__(self) -> None:
        self._db: Optional[aiosqlite.Connection] = None
        # In-memory cache of last-seen signals per (symbol, timeframe)
        self._prev_signals: Dict[str, Dict[str, str]] = {}

    @classmethod
    def get(cls) -> "SignalLog":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def init(self) -> None:
        """Open database and create tables if needed."""
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(_DB_PATH))
        self._db.row_factory = aiosqlite.Row

        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS signal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                signal TEXT NOT NULL,
                prev_signal TEXT,
                regime TEXT NOT NULL,
                price REAL NOT NULL,
                zscore REAL,
                heat INTEGER,
                confidence REAL,
                momentum REAL,
                conditions_met INTEGER,
                effective_conditions INTEGER,
                conditions_total INTEGER,
                exhaustion_state TEXT,
                floor_confirmed INTEGER DEFAULT 0,
                consensus TEXT,
                vol_scale REAL DEFAULT 1.0,
                signal_reason TEXT,
                timestamp INTEGER NOT NULL,
                -- Outcomes (filled by background updater)
                price_1d REAL,
                price_3d REAL,
                price_7d REAL,
                outcome_1d_pct REAL,
                outcome_3d_pct REAL,
                outcome_7d_pct REAL
            );
            CREATE INDEX IF NOT EXISTS idx_sig_sym_tf_ts
                ON signal_events(symbol, timeframe, timestamp);
            CREATE INDEX IF NOT EXISTS idx_sig_signal_tf
                ON signal_events(signal, timeframe);
            CREATE INDEX IF NOT EXISTS idx_sig_ts
                ON signal_events(timestamp);
        """)
        await self._db.commit()

        # Seed _prev_signals from the most recent event per symbol+tf
        cursor = await self._db.execute("""
            SELECT symbol, timeframe, signal
            FROM signal_events
            WHERE id IN (
                SELECT MAX(id) FROM signal_events
                GROUP BY symbol, timeframe
            )
        """)
        rows = await cursor.fetchall()
        for r in rows:
            tf = r["timeframe"]
            sym = r["symbol"]
            if tf not in self._prev_signals:
                self._prev_signals[tf] = {}
            self._prev_signals[tf][sym] = r["signal"]

        logger.info(
            "Signal log initialized at %s (%d previous states loaded)",
            _DB_PATH, len(rows),
        )

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SignalLog not initialized — call init() first")
        return self._db

    # ── Log signals (called after each scan) ───────────────────────────────

    async def log_signals(
        self,
        results: List[dict],
        timeframe: str,
        consensus: str,
    ) -> int:
        """Batch-insert signal events for all symbols that changed signal.

        Only logs when the signal differs from the previous scan for that
        symbol+timeframe combination.  On first run, everything is "NEW".

        Returns number of events logged.
        """
        db = self._ensure_db()
        now = int(time.time())
        tf_prev = self._prev_signals.setdefault(timeframe, {})
        rows = []

        for r in results:
            symbol = r.get("symbol", "")
            signal = r.get("signal", "WAIT")
            prev = tf_prev.get(symbol)

            # Only log transitions (or first-ever observation)
            if signal == prev:
                continue

            rows.append((
                symbol,
                timeframe,
                signal,
                prev,  # None on first observation
                r.get("regime", ""),
                r.get("price", 0.0),
                r.get("zscore"),
                r.get("heat"),
                r.get("confidence"),
                r.get("momentum"),
                r.get("conditions_met"),
                r.get("effective_conditions"),
                r.get("conditions_total"),
                r.get("exhaustion_state"),
                1 if r.get("floor_confirmed") else 0,
                consensus,
                r.get("vol_scale", 1.0),
                r.get("signal_reason", ""),
                now,
            ))
            # Update in-memory state
            tf_prev[symbol] = signal

        if not rows:
            return 0

        await db.executemany(
            """INSERT INTO signal_events (
                symbol, timeframe, signal, prev_signal, regime, price,
                zscore, heat, confidence, momentum,
                conditions_met, effective_conditions, conditions_total,
                exhaustion_state, floor_confirmed, consensus,
                vol_scale, signal_reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await db.commit()
        logger.info(
            "Logged %d signal changes for %s (e.g. %s)",
            len(rows), timeframe,
            ", ".join(f"{r[0]}:{r[2]}" for r in rows[:3]),
        )
        return len(rows)

    # ── Update outcomes (called periodically) ──────────────────────────────

    async def update_outcomes(self, current_prices: Dict[str, float]) -> int:
        """Back-fill outcome columns for signals old enough.

        Called after each scan with {symbol: current_price}.
        Fills price_1d when signal is >1d old, price_3d when >3d old, etc.

        Returns number of rows updated.
        """
        db = self._ensure_db()
        now = int(time.time())
        updated = 0

        # Find signals needing 1d outcome (>24h old, price_1d is NULL)
        cursor = await db.execute(
            """SELECT id, symbol, price FROM signal_events
               WHERE price_1d IS NULL AND timestamp <= ?""",
            (now - _1D,),
        )
        rows_1d = await cursor.fetchall()
        for r in rows_1d:
            cp = current_prices.get(r["symbol"])
            if cp and r["price"] and r["price"] > 0:
                pct = (cp - r["price"]) / r["price"] * 100
                await db.execute(
                    "UPDATE signal_events SET price_1d = ?, outcome_1d_pct = ? WHERE id = ?",
                    (cp, round(pct, 2), r["id"]),
                )
                updated += 1

        # 3d outcomes
        cursor = await db.execute(
            """SELECT id, symbol, price FROM signal_events
               WHERE price_3d IS NULL AND timestamp <= ?""",
            (now - _3D,),
        )
        rows_3d = await cursor.fetchall()
        for r in rows_3d:
            cp = current_prices.get(r["symbol"])
            if cp and r["price"] and r["price"] > 0:
                pct = (cp - r["price"]) / r["price"] * 100
                await db.execute(
                    "UPDATE signal_events SET price_3d = ?, outcome_3d_pct = ? WHERE id = ?",
                    (cp, round(pct, 2), r["id"]),
                )
                updated += 1

        # 7d outcomes
        cursor = await db.execute(
            """SELECT id, symbol, price FROM signal_events
               WHERE price_7d IS NULL AND timestamp <= ?""",
            (now - _7D,),
        )
        rows_7d = await cursor.fetchall()
        for r in rows_7d:
            cp = current_prices.get(r["symbol"])
            if cp and r["price"] and r["price"] > 0:
                pct = (cp - r["price"]) / r["price"] * 100
                await db.execute(
                    "UPDATE signal_events SET price_7d = ?, outcome_7d_pct = ? WHERE id = ?",
                    (cp, round(pct, 2), r["id"]),
                )
                updated += 1

        if updated > 0:
            await db.commit()
            logger.info("Updated %d signal outcomes", updated)
        return updated

    # ── Query: signal history ──────────────────────────────────────────────

    async def get_history(
        self,
        timeframe: str = "4h",
        symbol: Optional[str] = None,
        signal_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Paginated signal event history, newest first."""
        db = self._ensure_db()

        where_parts = ["timeframe = ?"]
        params: list = [timeframe]

        if symbol:
            where_parts.append("symbol = ?")
            params.append(symbol)
        if signal_type:
            where_parts.append("signal = ?")
            params.append(signal_type)

        where_clause = " AND ".join(where_parts)
        params.extend([limit, offset])

        cursor = await db.execute(
            f"""SELECT * FROM signal_events
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?""",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_history_count(
        self,
        timeframe: str = "4h",
        symbol: Optional[str] = None,
        signal_type: Optional[str] = None,
    ) -> int:
        """Total count for pagination."""
        db = self._ensure_db()

        where_parts = ["timeframe = ?"]
        params: list = [timeframe]

        if symbol:
            where_parts.append("symbol = ?")
            params.append(symbol)
        if signal_type:
            where_parts.append("signal = ?")
            params.append(signal_type)

        where_clause = " AND ".join(where_parts)
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM signal_events WHERE {where_clause}",
            params,
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    # ── Query: scorecard ───────────────────────────────────────────────────

    async def get_scorecard(
        self,
        timeframe: str = "4h",
    ) -> List[Dict[str, Any]]:
        """Per-signal-type win-rate scorecard.

        "Win" definition depends on signal direction:
        - LONG signals (STRONG_LONG, LIGHT_LONG, ACCUMULATE, REVIVAL_SEED*):
          win = price went UP after signal
        - EXIT signals (TRIM, TRIM_HARD, RISK_OFF, NO_LONG):
          win = price went DOWN after signal (validating the exit)
        """
        db = self._ensure_db()

        _LONG_SIGNALS = {
            "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE",
            "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
        }
        _EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}

        cursor = await db.execute(
            """SELECT signal,
                      COUNT(*) as total,
                      AVG(outcome_1d_pct) as avg_1d,
                      AVG(outcome_3d_pct) as avg_3d,
                      AVG(outcome_7d_pct) as avg_7d,
                      COUNT(outcome_1d_pct) as has_1d,
                      COUNT(outcome_3d_pct) as has_3d,
                      COUNT(outcome_7d_pct) as has_7d
               FROM signal_events
               WHERE timeframe = ?
               GROUP BY signal
               ORDER BY total DESC""",
            (timeframe,),
        )
        rows = await cursor.fetchall()
        cards: List[Dict[str, Any]] = []

        for r in rows:
            sig = r["signal"]
            total = r["total"]

            # Skip WAIT — it's the default state, not actionable
            if sig == "WAIT":
                continue

            # Calculate win rate based on signal direction
            is_long = sig in _LONG_SIGNALS
            is_exit = sig in _EXIT_SIGNALS

            # Count wins from 7d outcomes (most meaningful timeframe)
            wins_cursor = await db.execute(
                """SELECT COUNT(*) FROM signal_events
                   WHERE timeframe = ? AND signal = ?
                     AND outcome_7d_pct IS NOT NULL
                     AND outcome_7d_pct {} 0""".format(">" if is_long else "<"),
                (timeframe, sig),
            )
            wins_row = await wins_cursor.fetchone()
            wins = wins_row[0] if wins_row else 0

            has_outcomes = r["has_7d"]
            win_rate = round(wins / has_outcomes * 100, 1) if has_outcomes > 0 else None

            cards.append({
                "signal": sig,
                "count": total,
                "direction": "LONG" if is_long else ("EXIT" if is_exit else "NEUTRAL"),
                "wins": wins,
                "has_outcomes": has_outcomes,
                "win_rate": win_rate,
                "avg_1d": round(r["avg_1d"], 2) if r["avg_1d"] is not None else None,
                "avg_3d": round(r["avg_3d"], 2) if r["avg_3d"] is not None else None,
                "avg_7d": round(r["avg_7d"], 2) if r["avg_7d"] is not None else None,
            })

        return cards

    # ── Query: recent changes ──────────────────────────────────────────────

    async def get_recent_changes(
        self,
        timeframe: str = "4h",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Latest signal transitions only."""
        db = self._ensure_db()
        cursor = await db.execute(
            """SELECT symbol, signal, prev_signal, regime, price,
                      zscore, heat, confidence, timestamp, signal_reason
               FROM signal_events
               WHERE timeframe = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (timeframe, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
