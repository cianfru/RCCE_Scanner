"""
signal_log.py
~~~~~~~~~~~~~
SQLite-based signal persistence for tracking signal transitions, regime
changes, and measuring historical accuracy.

Logs every signal *change* and regime *transition* with full engine context
snapshots.  Back-fills outcome columns (price_1d, price_3d, price_7d) as
time passes.  Supports:
  - Paginated signal history
  - Regime transition tracking with duration
  - Upgrade / downgrade / entry / exit classification
  - Per-signal-type win-rate scorecard
  - Unified timeline (signal + regime events interleaved)
  - Recent signal changes feed

Uses aiosqlite for async SQLite access.  DB file lives in backend/data/.
"""

from __future__ import annotations

import json
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
_OUTCOME_TOLERANCE = 2 * 3600  # +/-2h window for outcome lookup

# ---------------------------------------------------------------------------
# Signal ranking for upgrade / downgrade classification
# ---------------------------------------------------------------------------

SIGNAL_RANK = {
    "NO_LONG": -2,
    "RISK_OFF": -1,
    "TRIM_HARD": 0,
    "TRIM": 1,
    "WAIT": 2,
    "REVIVAL_SEED": 3,
    "REVIVAL_SEED_CONFIRMED": 3,
    "ACCUMULATE": 4,
    "LIGHT_LONG": 5,
    "STRONG_LONG": 6,
}

_LONG_SIGNALS = {
    "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE",
    "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
}
_EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}


def _classify_transition(prev_signal: Optional[str], new_signal: str) -> str:
    """Classify a signal transition as UPGRADE/DOWNGRADE/ENTRY/EXIT/LATERAL/INITIAL."""
    if prev_signal is None:
        return "INITIAL"

    old_rank = SIGNAL_RANK.get(prev_signal, 2)
    new_rank = SIGNAL_RANK.get(new_signal, 2)
    old_is_long = prev_signal in _LONG_SIGNALS
    new_is_long = new_signal in _LONG_SIGNALS
    new_is_exit = new_signal in _EXIT_SIGNALS

    # ENTRY: moving from non-long to long
    if not old_is_long and new_is_long:
        return "ENTRY"
    # EXIT: moving from long to exit/wait
    if old_is_long and (new_is_exit or new_signal == "WAIT"):
        return "EXIT"
    # UPGRADE/DOWNGRADE within same family
    if new_rank > old_rank:
        return "UPGRADE"
    if new_rank < old_rank:
        return "DOWNGRADE"
    return "LATERAL"


def _build_context(r: dict, consensus: str) -> str:
    """Build compact JSON context blob from full scanner result dict."""
    ctx = {
        "rcce": {
            "energy": r.get("energy"),
            "vol_state": r.get("vol_state"),
            "raw_signal": r.get("raw_signal"),
            "beta_btc": r.get("beta_btc"),
            "beta_eth": r.get("beta_eth"),
            "atr_ratio": r.get("atr_ratio"),
            "regime_probabilities": r.get("regime_probabilities"),
        },
        "heatmap": {
            "heat_direction": r.get("heat_direction"),
            "heat_phase": r.get("heat_phase"),
            "atr_regime": r.get("atr_regime"),
            "deviation_pct": r.get("deviation_pct"),
            "deviation_abs": r.get("deviation_abs"),
            "bmsb_mid": r.get("bmsb_mid"),
            "r3": r.get("r3"),
        },
        "exhaustion": {
            "effort": r.get("effort"),
            "rel_vol": r.get("rel_vol"),
            "dist_pct": r.get("dist_pct"),
            "is_absorption": r.get("is_absorption"),
            "is_climax": r.get("is_climax"),
            "w_bmsb": r.get("w_bmsb"),
        },
        "synthesis": {
            "signal_warnings": r.get("signal_warnings", []),
            "conditions_detail": r.get("conditions_detail", []),
            "signal_confidence": r.get("signal_confidence"),
            "positioning": r.get("positioning"),
            "confluence": r.get("confluence"),
            "priority_score": r.get("priority_score"),
        },
        "market": {
            "consensus": consensus,
            "divergence": r.get("divergence"),
            "asset_class": r.get("asset_class"),
        },
    }
    return json.dumps(ctx, separators=(",", ":"), default=str)


class SignalLog:
    """Async SQLite manager for signal event persistence."""

    _instance: Optional["SignalLog"] = None

    def __init__(self) -> None:
        self._db: Optional[aiosqlite.Connection] = None
        # In-memory caches of last-seen signals and regimes per (symbol, tf)
        self._prev_signals: Dict[str, Dict[str, str]] = {}
        self._prev_regimes: Dict[str, Dict[str, str]] = {}

    @classmethod
    def get(cls) -> "SignalLog":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # == Lifecycle =============================================================

    async def init(self) -> None:
        """Open database and create tables if needed."""
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(_DB_PATH))
        self._db.row_factory = aiosqlite.Row

        # -- Original signal_events table ------------------------------------
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

        # -- Migration: add new columns if missing ---------------------------
        cols = set()
        cursor = await self._db.execute("PRAGMA table_info(signal_events)")
        for row in await cursor.fetchall():
            cols.add(row[1])  # column name is index 1

        if "transition_type" not in cols:
            await self._db.execute(
                "ALTER TABLE signal_events ADD COLUMN transition_type TEXT DEFAULT NULL"
            )
            logger.info("Migrated signal_events: added transition_type column")
        if "context" not in cols:
            await self._db.execute(
                "ALTER TABLE signal_events ADD COLUMN context TEXT DEFAULT NULL"
            )
            logger.info("Migrated signal_events: added context column")
        await self._db.commit()

        # -- Regime events table (new) ---------------------------------------
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS regime_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                regime TEXT NOT NULL,
                prev_regime TEXT,
                price REAL NOT NULL,
                zscore REAL,
                confidence REAL,
                energy REAL,
                context TEXT,
                timestamp INTEGER NOT NULL,
                duration_seconds INTEGER,
                ended_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_regime_sym_tf_ts
                ON regime_events(symbol, timeframe, timestamp);
            CREATE INDEX IF NOT EXISTS idx_regime_regime_tf
                ON regime_events(regime, timeframe);
            CREATE INDEX IF NOT EXISTS idx_regime_ts
                ON regime_events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_sig_transition_tf
                ON signal_events(transition_type, timeframe);
        """)
        await self._db.commit()

        # -- Seed _prev_signals from most recent event per symbol+tf ---------
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
            tf, sym = r["timeframe"], r["symbol"]
            self._prev_signals.setdefault(tf, {})[sym] = r["signal"]

        # -- Seed _prev_regimes from most recent regime event ----------------
        cursor = await self._db.execute("""
            SELECT symbol, timeframe, regime
            FROM regime_events
            WHERE id IN (
                SELECT MAX(id) FROM regime_events
                GROUP BY symbol, timeframe
            )
        """)
        regime_rows = await cursor.fetchall()
        for r in regime_rows:
            tf, sym = r["timeframe"], r["symbol"]
            self._prev_regimes.setdefault(tf, {})[sym] = r["regime"]

        # If regime_events is empty, seed from signal_events regimes
        if not regime_rows:
            cursor = await self._db.execute("""
                SELECT symbol, timeframe, regime
                FROM signal_events
                WHERE id IN (
                    SELECT MAX(id) FROM signal_events
                    GROUP BY symbol, timeframe
                )
            """)
            fallback_rows = await cursor.fetchall()
            for r in fallback_rows:
                tf, sym = r["timeframe"], r["symbol"]
                self._prev_regimes.setdefault(tf, {})[sym] = r["regime"]

        total_loaded = len(rows) + len(regime_rows)
        logger.info(
            "Signal log initialized at %s (%d signal + %d regime states loaded)",
            _DB_PATH, len(rows), len(regime_rows),
        )

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SignalLog not initialized -- call init() first")
        return self._db

    # == Log signals + regimes (called after each scan) ========================

    async def log_signals(
        self,
        results: List[dict],
        timeframe: str,
        consensus: str,
    ) -> int:
        """Batch-insert signal and regime events for symbols that changed.

        Logs signal transitions with transition_type classification and full
        engine context.  Also separately tracks regime changes with duration
        back-filling on the previous regime.

        Returns number of signal events logged.
        """
        db = self._ensure_db()
        now = int(time.time())
        tf_prev_sig = self._prev_signals.setdefault(timeframe, {})
        tf_prev_reg = self._prev_regimes.setdefault(timeframe, {})

        signal_rows = []
        regime_rows = []
        regime_backfills = []

        for r in results:
            symbol = r.get("symbol", "")
            signal = r.get("signal", "WAIT")
            regime = r.get("regime", "FLAT")
            prev_signal = tf_prev_sig.get(symbol)
            prev_regime = tf_prev_reg.get(symbol)

            signal_changed = signal != prev_signal
            regime_changed = regime != prev_regime

            if not signal_changed and not regime_changed:
                continue

            # Build context JSON once (shared by both inserts)
            context_json = _build_context(r, consensus)

            # -- Signal transition --
            if signal_changed:
                transition_type = _classify_transition(prev_signal, signal)
                signal_rows.append((
                    symbol, timeframe, signal, prev_signal,
                    regime, r.get("price", 0.0),
                    r.get("zscore"), r.get("heat"),
                    r.get("confidence"), r.get("momentum"),
                    r.get("conditions_met"), r.get("effective_conditions"),
                    r.get("conditions_total"), r.get("exhaustion_state"),
                    1 if r.get("floor_confirmed") else 0,
                    consensus, r.get("vol_scale", 1.0),
                    r.get("signal_reason", ""),
                    now, transition_type, context_json,
                ))
                tf_prev_sig[symbol] = signal

            # -- Regime transition --
            if regime_changed:
                regime_rows.append((
                    symbol, timeframe, regime, prev_regime,
                    r.get("price", 0.0), r.get("zscore"),
                    r.get("confidence"), r.get("energy"),
                    context_json, now,
                ))
                # Back-fill duration on previous regime event
                if prev_regime is not None:
                    regime_backfills.append((now, now, symbol, timeframe))
                tf_prev_reg[symbol] = regime

        # -- Batch insert signal events --
        if signal_rows:
            await db.executemany(
                """INSERT INTO signal_events (
                    symbol, timeframe, signal, prev_signal, regime, price,
                    zscore, heat, confidence, momentum,
                    conditions_met, effective_conditions, conditions_total,
                    exhaustion_state, floor_confirmed, consensus,
                    vol_scale, signal_reason, timestamp,
                    transition_type, context
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                signal_rows,
            )

        # -- Batch insert regime events --
        if regime_rows:
            await db.executemany(
                """INSERT INTO regime_events (
                    symbol, timeframe, regime, prev_regime,
                    price, zscore, confidence, energy,
                    context, timestamp
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                regime_rows,
            )

        # -- Back-fill duration on previous regime rows --
        for ended_at, ts, symbol, tf in regime_backfills:
            await db.execute(
                """UPDATE regime_events
                   SET duration_seconds = ? - timestamp,
                       ended_at = ?
                   WHERE symbol = ? AND timeframe = ?
                     AND ended_at IS NULL
                     AND id = (
                         SELECT MAX(id) FROM regime_events
                         WHERE symbol = ? AND timeframe = ?
                           AND ended_at IS NULL
                     )""",
                (ended_at, ended_at, symbol, tf, symbol, tf),
            )

        if signal_rows or regime_rows:
            await db.commit()

        if signal_rows:
            logger.info(
                "Logged %d signal changes for %s (e.g. %s)",
                len(signal_rows), timeframe,
                ", ".join(f"{r[0]}:{r[2]}" for r in signal_rows[:3]),
            )
        if regime_rows:
            logger.info(
                "Logged %d regime changes for %s (e.g. %s)",
                len(regime_rows), timeframe,
                ", ".join(f"{r[0]}:{r[2]}" for r in regime_rows[:3]),
            )

        return len(signal_rows)

    # == Update outcomes (called periodically) =================================

    async def update_outcomes(self, current_prices: Dict[str, float]) -> int:
        """Back-fill outcome columns for signals old enough.

        Called after each scan with {symbol: current_price}.
        Fills price_1d when signal is >1d old, price_3d when >3d old, etc.

        Returns number of rows updated.
        """
        db = self._ensure_db()
        now = int(time.time())
        updated = 0

        for delta, col_price, col_pct in [
            (_1D, "price_1d", "outcome_1d_pct"),
            (_3D, "price_3d", "outcome_3d_pct"),
            (_7D, "price_7d", "outcome_7d_pct"),
        ]:
            # Only back-fill signals within a 2-delta window of the target time.
            # Signals older than 2x the horizon get stale — current price is no
            # longer representative of what happened at signal+delta.
            cursor = await db.execute(
                f"""SELECT id, symbol, price FROM signal_events
                    WHERE {col_price} IS NULL
                      AND timestamp <= ?
                      AND timestamp >= ?""",
                (now - delta, now - delta * 2),
            )
            rows = await cursor.fetchall()
            for r in rows:
                cp = current_prices.get(r["symbol"])
                if cp and r["price"] and r["price"] > 0:
                    pct = (cp - r["price"]) / r["price"] * 100
                    await db.execute(
                        f"UPDATE signal_events SET {col_price} = ?, {col_pct} = ? WHERE id = ?",
                        (cp, round(pct, 2), r["id"]),
                    )
                    updated += 1

        if updated > 0:
            await db.commit()
            logger.info("Updated %d signal outcomes", updated)
        return updated

    # == Query: signal history =================================================

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

    # == Query: scorecard ======================================================

    async def get_scorecard(
        self,
        timeframe: str = "4h",
    ) -> List[Dict[str, Any]]:
        """Per-signal-type win-rate scorecard.

        "Win" definition depends on signal direction:
        - LONG signals: win = price went UP after signal
        - EXIT signals: win = price went DOWN after signal
        """
        db = self._ensure_db()

        # Outlier caps: exclude extreme returns from averages
        # (corrupted back-fills from micro-cap coins or timing issues)
        cursor = await db.execute(
            """SELECT signal,
                      COUNT(*) as total,
                      AVG(CASE WHEN abs(outcome_1d_pct) <= 30 THEN outcome_1d_pct END) as avg_1d,
                      AVG(CASE WHEN abs(outcome_3d_pct) <= 50 THEN outcome_3d_pct END) as avg_3d,
                      AVG(CASE WHEN abs(outcome_7d_pct) <= 80 THEN outcome_7d_pct END) as avg_7d,
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
            if sig == "WAIT":
                continue

            is_long = sig in _LONG_SIGNALS
            is_exit = sig in _EXIT_SIGNALS

            wins_cursor = await db.execute(
                """SELECT COUNT(*) FROM signal_events
                   WHERE timeframe = ? AND signal = ?
                     AND outcome_7d_pct IS NOT NULL
                     AND abs(outcome_7d_pct) <= 80
                     AND outcome_7d_pct {} 0""".format(">" if is_long else "<"),
                (timeframe, sig),
            )
            wins_row = await wins_cursor.fetchone()
            wins = wins_row[0] if wins_row else 0

            # Count outcomes excluding outliers (match wins query filter)
            outcomes_cursor = await db.execute(
                """SELECT COUNT(*) FROM signal_events
                   WHERE timeframe = ? AND signal = ?
                     AND outcome_7d_pct IS NOT NULL
                     AND abs(outcome_7d_pct) <= 80""",
                (timeframe, sig),
            )
            outcomes_row = await outcomes_cursor.fetchone()
            has_outcomes = outcomes_row[0] if outcomes_row else 0
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

    # == Query: recent changes =================================================

    async def get_recent_changes(
        self,
        timeframe: str = "4h",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Latest signal transitions only."""
        db = self._ensure_db()
        cursor = await db.execute(
            """SELECT symbol, signal, prev_signal, regime, price,
                      zscore, heat, confidence, timestamp, signal_reason,
                      transition_type
               FROM signal_events
               WHERE timeframe = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (timeframe, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # == Query: regime history =================================================

    async def get_regime_history(
        self,
        timeframe: str = "4h",
        symbol: Optional[str] = None,
        regime: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Paginated regime transition history, newest first."""
        db = self._ensure_db()
        where_parts = ["timeframe = ?"]
        params: list = [timeframe]

        if symbol:
            where_parts.append("symbol = ?")
            params.append(symbol)
        if regime:
            where_parts.append("regime = ?")
            params.append(regime)

        where_clause = " AND ".join(where_parts)
        params.extend([limit, offset])

        cursor = await db.execute(
            f"""SELECT * FROM regime_events
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?""",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_regime_history_count(
        self,
        timeframe: str = "4h",
        symbol: Optional[str] = None,
        regime: Optional[str] = None,
    ) -> int:
        """Total regime events count for pagination."""
        db = self._ensure_db()
        where_parts = ["timeframe = ?"]
        params: list = [timeframe]

        if symbol:
            where_parts.append("symbol = ?")
            params.append(symbol)
        if regime:
            where_parts.append("regime = ?")
            params.append(regime)

        where_clause = " AND ".join(where_parts)
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM regime_events WHERE {where_clause}",
            params,
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    # == Query: signal heatmap (14-day grid) ====================================

    async def get_signal_heatmap(
        self,
        timeframe: str = "4h",
        days: int = 14,
        symbols: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Reconstruct signal state per symbol per day over the last N days.

        For each day boundary (end-of-day UTC), finds the last signal event
        before that point for each symbol.  Returns a grid suitable for a
        heatmap visualisation.

        Parameters
        ----------
        timeframe : str
            "4h" or "1d"
        days : int
            Lookback window (default 14, max 30)
        symbols : list[str] | None
            If provided, restrict to these symbols.  Otherwise returns all
            symbols that have at least one event in the window.
        """
        import datetime as _dt

        db = self._ensure_db()
        days = min(days, 30)

        now = _dt.datetime.utcnow()
        today_end = _dt.datetime(now.year, now.month, now.day, 23, 59, 59)
        day_boundaries = []
        day_labels = []
        for i in range(days - 1, -1, -1):  # oldest first
            d = today_end - _dt.timedelta(days=i)
            day_boundaries.append(int(d.timestamp()))
            day_labels.append((d - _dt.timedelta(hours=23, minutes=59, seconds=59)).strftime("%b %d"))

        # Build per-day snapshot: last signal+conditions before each boundary
        grid: Dict[str, list] = {}   # symbol -> [{"signal":..,"cond":..}, ...]

        for boundary_ts in day_boundaries:
            params: list = [timeframe, boundary_ts]
            sym_filter = ""
            if symbols:
                placeholders = ",".join("?" for _ in symbols)
                sym_filter = f" AND symbol IN ({placeholders})"
                params.extend(symbols)

            cursor = await db.execute(
                f"""SELECT symbol, signal, conditions_met, conditions_total
                    FROM signal_events
                    WHERE timeframe = ? AND timestamp <= ?{sym_filter}
                      AND id IN (
                          SELECT MAX(id) FROM signal_events
                          WHERE timeframe = ? AND timestamp <= ?{sym_filter}
                          GROUP BY symbol
                      )""",
                params + params,  # duplicated for subquery
            )
            rows = await cursor.fetchall()
            day_data = {r["symbol"]: {
                "signal": r["signal"],
                "cond": f"{r['conditions_met'] or 0}/{r['conditions_total'] or 14}",
            } for r in rows}

            for sym, val in day_data.items():
                grid.setdefault(sym, [None] * len(day_boundaries))
                idx = day_boundaries.index(boundary_ts)
                grid[sym][idx] = val

        # Fill None gaps: if a symbol has no event before a day, carry forward
        for sym in grid:
            last_known = None
            for i in range(len(grid[sym])):
                if grid[sym][i] is not None:
                    last_known = grid[sym][i]
                elif last_known is not None:
                    grid[sym][i] = last_known

        return {
            "days": day_labels,
            "symbols": sorted(grid.keys()),
            "grid": grid,
        }

    # == Query: recent unified (for dashboard ticker) ==========================

    async def get_recent_unified(
        self,
        timeframe: str = "4h",
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """Recent signal + regime changes merged, sorted by time desc.

        Returns lightweight events for the dashboard 'What Changed' ticker.
        Each event has ``event_type`` ('signal' or 'regime'), ``symbol``,
        ``prev``/``current`` values, ``transition_type``, and ``timestamp``.
        """
        db = self._ensure_db()
        # Fetch recent signal transitions
        sig_cursor = await db.execute(
            """SELECT symbol, signal AS current, prev_signal AS prev,
                      transition_type, timestamp, 'signal' AS event_type
               FROM signal_events
               WHERE timeframe = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (timeframe, limit),
        )
        sig_rows = [dict(r) for r in await sig_cursor.fetchall()]

        # Fetch recent regime transitions
        reg_cursor = await db.execute(
            """SELECT symbol, regime AS current, prev_regime AS prev,
                      'REGIME_CHANGE' AS transition_type, timestamp,
                      'regime' AS event_type
               FROM regime_events
               WHERE timeframe = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (timeframe, limit),
        )
        reg_rows = [dict(r) for r in await reg_cursor.fetchall()]

        # Merge, sort by timestamp desc, take top N
        merged = sorted(sig_rows + reg_rows, key=lambda e: e["timestamp"], reverse=True)
        return merged[:limit]

    # == Query: unified timeline ===============================================

    async def get_timeline(
        self,
        timeframe: str = "4h",
        symbol: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Unified timeline: signal + regime events interleaved by timestamp.

        Returns events with an 'event_type' field: 'signal' or 'regime'.
        """
        db = self._ensure_db()

        sym_filter = ""
        params: list = [timeframe]
        if symbol:
            sym_filter = " AND symbol = ?"
            params.append(symbol)

        # Duplicate params for UNION ALL second SELECT
        params2: list = [timeframe]
        if symbol:
            params2.append(symbol)

        all_params = params + params2 + [limit, offset]

        cursor = await db.execute(
            f"""SELECT * FROM (
                SELECT 'signal' AS event_type, id, symbol, timeframe,
                       signal AS label, prev_signal AS prev_label,
                       regime, price, zscore, confidence,
                       transition_type, context, timestamp
                FROM signal_events
                WHERE timeframe = ?{sym_filter}

                UNION ALL

                SELECT 'regime' AS event_type, id, symbol, timeframe,
                       regime AS label, prev_regime AS prev_label,
                       regime, price, zscore, confidence,
                       NULL AS transition_type, context, timestamp
                FROM regime_events
                WHERE timeframe = ?{sym_filter}
            )
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?""",
            all_params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_timeline_count(
        self,
        timeframe: str = "4h",
        symbol: Optional[str] = None,
    ) -> int:
        """Total timeline events count."""
        db = self._ensure_db()

        sym_filter = ""
        params: list = [timeframe]
        if symbol:
            sym_filter = " AND symbol = ?"
            params.append(symbol)

        params2: list = [timeframe]
        if symbol:
            params2.append(symbol)

        all_params = params + params2

        cursor = await db.execute(
            f"""SELECT (
                    SELECT COUNT(*) FROM signal_events
                    WHERE timeframe = ?{sym_filter}
                ) + (
                    SELECT COUNT(*) FROM regime_events
                    WHERE timeframe = ?{sym_filter}
                )""",
            all_params,
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    # == Query: upgrade scorecard ==============================================

    async def get_upgrade_scorecard(
        self,
        timeframe: str = "4h",
    ) -> Dict[str, Any]:
        """Per-transition-type counts and win rates.

        Returns cards for UPGRADE, DOWNGRADE, ENTRY, EXIT with win rate
        based on 7d outcomes.
        """
        db = self._ensure_db()

        cursor = await db.execute(
            """SELECT transition_type,
                      COUNT(*) as total,
                      AVG(outcome_1d_pct) as avg_1d,
                      AVG(outcome_7d_pct) as avg_7d,
                      COUNT(outcome_7d_pct) as has_7d
               FROM signal_events
               WHERE timeframe = ? AND transition_type IS NOT NULL
               GROUP BY transition_type
               ORDER BY total DESC""",
            (timeframe,),
        )
        rows = await cursor.fetchall()
        cards = []

        for r in rows:
            tt = r["transition_type"]
            has_outcomes = r["has_7d"]

            # Win = positive 7d for UPGRADE/ENTRY, negative 7d for DOWNGRADE/EXIT
            is_bullish = tt in ("UPGRADE", "ENTRY", "INITIAL")
            wins_cursor = await db.execute(
                """SELECT COUNT(*) FROM signal_events
                   WHERE timeframe = ? AND transition_type = ?
                     AND outcome_7d_pct IS NOT NULL
                     AND outcome_7d_pct {} 0""".format(">" if is_bullish else "<"),
                (timeframe, tt),
            )
            wins_row = await wins_cursor.fetchone()
            wins = wins_row[0] if wins_row else 0

            win_rate = round(wins / has_outcomes * 100, 1) if has_outcomes > 0 else None

            cards.append({
                "transition_type": tt,
                "count": r["total"],
                "wins": wins,
                "has_outcomes": has_outcomes,
                "win_rate": win_rate,
                "avg_1d": round(r["avg_1d"], 2) if r["avg_1d"] is not None else None,
                "avg_7d": round(r["avg_7d"], 2) if r["avg_7d"] is not None else None,
            })

        return {"cards": cards, "timeframe": timeframe}

    # == Query: regime durations ===============================================

    async def get_regime_durations(
        self,
        timeframe: str = "4h",
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Average regime durations grouped by regime type."""
        db = self._ensure_db()

        sym_filter = ""
        params: list = [timeframe]
        if symbol:
            sym_filter = " AND symbol = ?"
            params.append(symbol)

        cursor = await db.execute(
            f"""SELECT regime,
                       COUNT(*) as count,
                       AVG(duration_seconds) as avg_duration,
                       MIN(duration_seconds) as min_duration,
                       MAX(duration_seconds) as max_duration
                FROM regime_events
                WHERE timeframe = ?{sym_filter}
                  AND duration_seconds IS NOT NULL
                GROUP BY regime
                ORDER BY avg_duration DESC""",
            params,
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            avg_s = r["avg_duration"]
            results.append({
                "regime": r["regime"],
                "count": r["count"],
                "avg_duration_seconds": round(avg_s) if avg_s else None,
                "avg_duration_label": _fmt_duration(avg_s) if avg_s else None,
                "min_duration_seconds": r["min_duration"],
                "max_duration_seconds": r["max_duration"],
            })
        return results

    # == Query: metric time series (for AI trend analysis) ====================

    async def get_metric_series(
        self,
        symbol: str,
        timeframe: str = "4h",
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """Extract metric time series from signal events using json_extract.

        Parses the context JSON column at query time to extract engine metrics
        without sending raw JSON blobs to the caller.  Returns events
        oldest-first for chronological trend analysis.
        """
        db = self._ensure_db()
        cursor = await db.execute(
            """SELECT
                timestamp, signal, regime, price, zscore, heat, confidence,
                json_extract(context, '$.rcce.energy') as energy,
                json_extract(context, '$.rcce.vol_state') as vol_state,
                json_extract(context, '$.heatmap.heat_phase') as heat_phase,
                json_extract(context, '$.heatmap.deviation_pct') as deviation_pct,
                json_extract(context, '$.heatmap.heat_direction') as heat_direction,
                json_extract(context, '$.exhaustion.effort') as effort,
                json_extract(context, '$.exhaustion.is_absorption') as is_absorption,
                json_extract(context, '$.synthesis.priority_score') as priority_score,
                json_extract(context, '$.market.consensus') as consensus,
                transition_type
            FROM signal_events
            WHERE symbol = ? AND timeframe = ? AND context IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?""",
            (symbol, timeframe, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in reversed(rows)]  # oldest-first


def _fmt_duration(seconds: float) -> str:
    """Format seconds as human-readable duration (e.g. '2d 5h', '14h 30m')."""
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"
    d = s // 86400
    h = (s % 86400) // 3600
    return f"{d}d {h}h" if h else f"{d}d"
