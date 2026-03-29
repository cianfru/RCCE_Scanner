"""
signal_outcomes.py
~~~~~~~~~~~~~~~~~~
Tracks price action AFTER unified cross-TF signals fire.

When a unified signal fires (WAIT → LIGHT_LONG, etc.), records the entry
price and tracks subsequent price movement to measure:
- MFE (Max Favorable Excursion): how far price moved in your favor
- MAE (Max Adverse Excursion): how far price moved against you
- Hit rates at various R:R levels (did price hit +1% before -1%?)

Only tracks UNIFIED signals (both 4H + 1D must agree). Per-TF signals
are ignored — they're not tradeable.

Persisted to SQLite alongside signal_log.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).resolve().parent / "data"

_DB_PATH = _PERSIST_DIR / "signal_outcomes.db"

# R:R levels to track (% thresholds)
_RR_LEVELS = [1.0, 2.0, 3.0, 5.0]

# Signals that count as "entry" for tracking
_ENTRY_SIGNALS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}
_EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}

# Max age to keep tracking an open outcome (7 days)
_MAX_TRACK_AGE_S = 7 * 24 * 3600

# ---------------------------------------------------------------------------
# In-memory active tracking
# ---------------------------------------------------------------------------

@dataclass
class ActiveOutcome:
    """An in-progress outcome being tracked."""
    symbol: str
    signal: str
    entry_price: float
    entry_time: float
    mfe_pct: float = 0.0        # max favorable excursion %
    mae_pct: float = 0.0        # max adverse excursion %
    current_pct: float = 0.0    # current % change from entry
    # Which R:R levels were hit favorably first
    hit_levels: Dict[float, bool] = field(default_factory=dict)  # {1.0: True, 2.0: False, ...}
    resolved: bool = False
    resolve_reason: str = ""    # "signal_change" | "max_age" | "exit_signal"
    resolve_time: float = 0.0
    resolve_price: float = 0.0


# Active outcomes: symbol → ActiveOutcome
_active: Dict[str, ActiveOutcome] = {}

# SQLite connection
_db = None


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def _ensure_db():
    global _db
    if _db is not None:
        return _db
    try:
        import sqlite3
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(_DB_PATH))
        _db.row_factory = sqlite3.Row
        _db.execute("""
            CREATE TABLE IF NOT EXISTS signal_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_time REAL NOT NULL,
                mfe_pct REAL DEFAULT 0,
                mae_pct REAL DEFAULT 0,
                exit_pct REAL DEFAULT 0,
                exit_price REAL DEFAULT 0,
                exit_time REAL DEFAULT 0,
                resolve_reason TEXT DEFAULT '',
                duration_hours REAL DEFAULT 0,
                hit_1pct INTEGER DEFAULT 0,
                hit_2pct INTEGER DEFAULT 0,
                hit_3pct INTEGER DEFAULT 0,
                hit_5pct INTEGER DEFAULT 0
            )
        """)
        _db.execute("CREATE INDEX IF NOT EXISTS idx_so_signal ON signal_outcomes(signal)")
        _db.execute("CREATE INDEX IF NOT EXISTS idx_so_time ON signal_outcomes(entry_time)")
        _db.commit()
        logger.info("Signal outcomes DB ready at %s", _DB_PATH)
    except Exception as e:
        logger.warning("Signal outcomes DB init failed: %s", e)
        _db = None
    return _db


# ---------------------------------------------------------------------------
# Public API — called from scanner.py after unified signal computation
# ---------------------------------------------------------------------------

def update_outcomes(results: List[dict]) -> None:
    """Process scan results to track unified signal outcomes.

    Called after every synthesis pass. For each symbol:
    1. If unified signal just fired (WAIT → entry): start tracking
    2. If tracking and price moved: update MFE/MAE + hit levels
    3. If unified signal changed or expired: resolve and persist
    """
    now = time.time()

    for r in results:
        sym = r.get("symbol", "")
        unified = r.get("unified_signal")
        price = r.get("price", 0)
        if not sym or not price or not unified:
            continue

        active = _active.get(sym)

        # Case 1: No active tracking, unified is an entry signal → start
        if not active and unified in _ENTRY_SIGNALS:
            _active[sym] = ActiveOutcome(
                symbol=sym,
                signal=unified,
                entry_price=price,
                entry_time=now,
                hit_levels={lvl: False for lvl in _RR_LEVELS},
            )
            logger.debug("Outcome tracking started: %s %s @ %.4f", sym, unified, price)
            continue

        # Case 2: Active tracking exists
        if active and not active.resolved:
            pct = ((price - active.entry_price) / active.entry_price) * 100

            # For LONG signals, favorable = positive
            active.current_pct = pct
            if pct > active.mfe_pct:
                active.mfe_pct = pct
            if pct < active.mae_pct:
                active.mae_pct = pct

            # Check R:R hit levels (did price hit +X% before -X%?)
            for lvl in _RR_LEVELS:
                if not active.hit_levels.get(lvl, False):
                    if pct >= lvl:
                        active.hit_levels[lvl] = True
                    elif pct <= -lvl:
                        active.hit_levels[lvl] = False  # hit adverse first

            # Check resolve conditions
            should_resolve = False
            reason = ""

            if unified in _EXIT_SIGNALS:
                should_resolve = True
                reason = "exit_signal"
            elif unified == "WAIT" and active.signal in _ENTRY_SIGNALS:
                should_resolve = True
                reason = "signal_change"
            elif unified in _ENTRY_SIGNALS and unified != active.signal:
                # Signal changed type (e.g., LIGHT → STRONG) — keep tracking, update signal
                active.signal = unified
            elif now - active.entry_time > _MAX_TRACK_AGE_S:
                should_resolve = True
                reason = "max_age"

            if should_resolve:
                active.resolved = True
                active.resolve_reason = reason
                active.resolve_time = now
                active.resolve_price = price
                _persist_outcome(active)
                del _active[sym]
                logger.debug(
                    "Outcome resolved: %s %s entry=%.4f exit=%.4f MFE=+%.2f%% MAE=%.2f%% reason=%s",
                    sym, active.signal, active.entry_price, price,
                    active.mfe_pct, active.mae_pct, reason,
                )

    # Clean up stale entries
    stale = [s for s, a in _active.items() if now - a.entry_time > _MAX_TRACK_AGE_S]
    for s in stale:
        a = _active.pop(s)
        a.resolved = True
        a.resolve_reason = "max_age"
        a.resolve_time = now
        _persist_outcome(a)


def _persist_outcome(outcome: ActiveOutcome) -> None:
    """Save a resolved outcome to SQLite."""
    db = _ensure_db()
    if not db:
        return
    try:
        duration_h = (outcome.resolve_time - outcome.entry_time) / 3600
        exit_pct = ((outcome.resolve_price - outcome.entry_price) / outcome.entry_price) * 100 if outcome.entry_price > 0 else 0

        db.execute(
            """INSERT INTO signal_outcomes
               (symbol, signal, entry_price, entry_time, mfe_pct, mae_pct,
                exit_pct, exit_price, exit_time, resolve_reason, duration_hours,
                hit_1pct, hit_2pct, hit_3pct, hit_5pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                outcome.symbol, outcome.signal, outcome.entry_price, outcome.entry_time,
                round(outcome.mfe_pct, 3), round(outcome.mae_pct, 3),
                round(exit_pct, 3), outcome.resolve_price, outcome.resolve_time,
                outcome.resolve_reason, round(duration_h, 2),
                int(outcome.hit_levels.get(1.0, False)),
                int(outcome.hit_levels.get(2.0, False)),
                int(outcome.hit_levels.get(3.0, False)),
                int(outcome.hit_levels.get(5.0, False)),
            ),
        )
        db.commit()
    except Exception as e:
        logger.warning("Failed to persist outcome for %s: %s", outcome.symbol, e)


# ---------------------------------------------------------------------------
# Query API — used by endpoints
# ---------------------------------------------------------------------------

def get_outcome_stats(days: int = 30) -> Dict[str, Any]:
    """Aggregate outcome stats across all signals for the last N days."""
    db = _ensure_db()
    if not db:
        return {"signals": [], "active_count": len(_active)}

    cutoff = time.time() - days * 86400
    cursor = db.execute(
        """SELECT signal,
                  COUNT(*) as total,
                  AVG(mfe_pct) as avg_mfe,
                  AVG(mae_pct) as avg_mae,
                  AVG(exit_pct) as avg_exit,
                  AVG(duration_hours) as avg_duration_h,
                  SUM(hit_1pct) as hit_1,
                  SUM(hit_2pct) as hit_2,
                  SUM(hit_3pct) as hit_3,
                  SUM(hit_5pct) as hit_5
           FROM signal_outcomes
           WHERE entry_time > ?
           GROUP BY signal
           ORDER BY total DESC""",
        (cutoff,),
    )
    rows = cursor.fetchall()

    signals = []
    for r in rows:
        total = r["total"]
        signals.append({
            "signal": r["signal"],
            "total": total,
            "avg_mfe_pct": round(r["avg_mfe"] or 0, 2),
            "avg_mae_pct": round(r["avg_mae"] or 0, 2),
            "avg_exit_pct": round(r["avg_exit"] or 0, 2),
            "avg_duration_hours": round(r["avg_duration_h"] or 0, 1),
            "hit_1pct": round(r["hit_1"] / total * 100, 1) if total > 0 else 0,
            "hit_2pct": round(r["hit_2"] / total * 100, 1) if total > 0 else 0,
            "hit_3pct": round(r["hit_3"] / total * 100, 1) if total > 0 else 0,
            "hit_5pct": round(r["hit_5"] / total * 100, 1) if total > 0 else 0,
        })

    return {
        "days": days,
        "signals": signals,
        "active_count": len(_active),
        "active": [
            {
                "symbol": a.symbol,
                "signal": a.signal,
                "entry_price": a.entry_price,
                "current_pct": round(a.current_pct, 2),
                "mfe_pct": round(a.mfe_pct, 2),
                "mae_pct": round(a.mae_pct, 2),
                "duration_hours": round((time.time() - a.entry_time) / 3600, 1),
                "hit_levels": {str(k): v for k, v in a.hit_levels.items()},
            }
            for a in _active.values()
        ],
    }


def get_recent_outcomes(limit: int = 50) -> List[dict]:
    """Get most recent resolved outcomes."""
    db = _ensure_db()
    if not db:
        return []

    cursor = db.execute(
        """SELECT * FROM signal_outcomes
           ORDER BY exit_time DESC LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in cursor.fetchall()]
