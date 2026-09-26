"""SQLite storage for wallet cohorts (portable: the file can move to another host as is).

wallets              registry from the leaderboard: all-time PnL, polling schedule
wallet_state_latest  one row per wallet, overwritten each poll (no per-wallet history)
cohort_snapshots     aggregated rows per sweep: the time series
sweep_runs           audit: duration, weight used, errors; an unfinished run is resumed
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from cohorts.assign import Position, WalletState

RETENTION_DAYS = 180

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    address TEXT PRIMARY KEY,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    lb_value REAL,
    all_time_pnl REAL,
    active INTEGER NOT NULL DEFAULT 1,
    focus INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    next_poll_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_wallets_due ON wallets(active, next_poll_at);
CREATE TABLE IF NOT EXISTS wallet_state_latest (
    address TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    equity REAL NOT NULL,
    positions TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cohort_snapshots (
    ts INTEGER NOT NULL,
    dimension TEXT NOT NULL,
    cohort TEXT NOT NULL,
    symbol TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (ts, dimension, cohort, symbol)
);
CREATE INDEX IF NOT EXISTS idx_cs_series ON cohort_snapshots(dimension, cohort, symbol, ts);
CREATE TABLE IF NOT EXISTS sweep_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started REAL NOT NULL,
    finished REAL,
    status TEXT NOT NULL,
    due INTEGER NOT NULL DEFAULT 0,
    polled INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    rate_limited INTEGER NOT NULL DEFAULT 0,
    weight INTEGER NOT NULL DEFAULT 0,
    duration_s REAL
);
"""


def default_path() -> str:
    env = os.environ.get("COHORTS_DB_PATH")
    if env:
        return env
    hl = os.environ.get("HYPERLENS_DB_PATH")
    base = os.path.dirname(hl) if hl else str(Path(__file__).resolve().parent.parent)
    return os.path.join(base, "cohorts.db")


class Store:
    def __init__(self, path: Optional[str] = None):
        self.path = path or default_path()
        if os.path.dirname(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(_SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(wallets)")}
        if "pinned" not in cols:              # databases created before HyperLens was fed by the sweep
            self.db.execute("ALTER TABLE wallets ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
        self.db.commit()

    # --- registry -----------------------------------------------------------------
    def update_registry(self, rows: Iterable[Tuple[str, float, Optional[float]]], now: float) -> int:
        """rows: (address, leaderboard account value, all-time PnL). Wallets missing from
        today's list stop being polled but keep their row."""
        rows = list(rows)
        self.db.execute("UPDATE wallets SET active = 0")
        self.db.executemany(
            "INSERT INTO wallets (address, first_seen, last_seen, lb_value, all_time_pnl, active) VALUES (?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(address) DO UPDATE SET last_seen = excluded.last_seen, lb_value = excluded.lb_value, "
            "all_time_pnl = excluded.all_time_pnl, active = 1",
            [(a, now, now, v, p) for a, v, p in rows],
        )
        self.db.commit()
        return len(rows)

    def due(self, now: float, polled_since: Optional[float] = None) -> List[Tuple[str, Optional[float]]]:
        """(address, all-time PnL) to poll. polled_since: skip wallets already polled since then (resuming a sweep)."""
        return self.db.execute(
            "SELECT w.address, w.all_time_pnl FROM wallets w LEFT JOIN wallet_state_latest s ON s.address = w.address "
            "WHERE w.active = 1 AND (w.next_poll_at <= ? OR w.pinned = 1) AND (s.ts IS NULL OR s.ts < ?) "
            "ORDER BY w.pinned DESC, w.lb_value DESC",
            (now, polled_since if polled_since is not None else float("inf"))).fetchall()

    def registry_size(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM wallets WHERE active = 1").fetchone()[0]

    def set_pinned(self, addresses: Iterable[str]) -> int:
        """Wallets polled every sweep whatever their size (the HyperLens roster)."""
        addrs = [(a.lower(),) for a in addresses]
        self.db.execute("UPDATE wallets SET pinned = 0 WHERE pinned = 1")
        self.db.executemany("UPDATE wallets SET pinned = 1 WHERE address = ?", addrs)
        self.db.commit()
        return self.db.execute("SELECT COUNT(*) FROM wallets WHERE pinned = 1").fetchone()[0]

    def focus_size(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM wallets WHERE active = 1 AND focus = 1").fetchone()[0]

    # --- wallet state -------------------------------------------------------------
    def previous_first_seen(self, address: str) -> Dict[Tuple[str, bool], float]:
        row = self.db.execute("SELECT positions FROM wallet_state_latest WHERE address = ?", (address,)).fetchone()
        return {(c, bool(lg)): fs for c, _, lg, fs in json.loads(row[0])} if row else {}

    def save_states(self, items: List[tuple]) -> None:
        """items: (address, ts, equity, [Position], focus, next_poll_at)"""
        self.db.executemany(
            "INSERT INTO wallet_state_latest (address, ts, equity, positions) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(address) DO UPDATE SET ts = excluded.ts, equity = excluded.equity, positions = excluded.positions",
            [(a, ts, eq, json.dumps([[p.coin, round(p.usd, 2), int(p.long), p.first_seen] for p in ps], separators=(",", ":")))
             for a, ts, eq, ps, _, _ in items])
        self.db.executemany("UPDATE wallets SET focus = ?, next_poll_at = ? WHERE address = ?",
                            [(int(f), nxt, a) for a, _, _, _, f, nxt in items])
        self.db.commit()

    def load_states(self, now: float, max_age_s: float) -> List[WalletState]:
        out = []
        for a, eq, ps, pnl in self.db.execute(
                "SELECT s.address, s.equity, s.positions, w.all_time_pnl FROM wallet_state_latest s "
                "JOIN wallets w ON w.address = s.address WHERE w.active = 1 AND w.focus = 1 AND s.ts >= ?", (now - max_age_s,)):
            out.append(WalletState(a, eq, pnl, [Position(c, u, bool(lg), fs) for c, u, lg, fs in json.loads(ps)]))
        return out

    # --- cohort time series -------------------------------------------------------
    def write_snapshot(self, ts: int, rows: List[dict]) -> None:
        self.db.executemany(
            "INSERT OR REPLACE INTO cohort_snapshots (ts, dimension, cohort, symbol, data) VALUES (?, ?, ?, ?, ?)",
            [(ts, r["dimension"], r["cohort"], r["symbol"] or "",
              json.dumps({k: v for k, v in r.items() if k not in ("dimension", "cohort", "symbol")}, separators=(",", ":")))
             for r in rows])
        self.db.execute("DELETE FROM cohort_snapshots WHERE ts < ?", (ts - RETENTION_DAYS * 86400,))
        self.db.commit()

    def latest_ts(self) -> Optional[int]:
        row = self.db.execute("SELECT MAX(ts) FROM cohort_snapshots").fetchone()
        return row[0] if row and row[0] else None

    def latest_symbol_ts(self) -> Optional[int]:
        row = self.db.execute("SELECT MAX(ts) FROM cohort_snapshots WHERE symbol != ''").fetchone()
        return row[0] if row and row[0] else None

    def latest_symbol_snapshot_ts(self, symbol: str) -> Optional[int]:
        row = self.db.execute("SELECT MAX(ts) FROM cohort_snapshots WHERE symbol = ?", (symbol,)).fetchone()
        return row[0] if row and row[0] else None

    def snapshot(self, ts: int, dimension: Optional[str] = None, symbol: Optional[str] = None) -> List[dict]:
        q, args = "SELECT dimension, cohort, symbol, data FROM cohort_snapshots WHERE ts = ?", [ts]
        if dimension:
            q, args = q + " AND dimension = ?", args + [dimension]
        if symbol is not None:
            q, args = q + " AND symbol = ?", args + [symbol]
        return [{"dimension": d, "cohort": c, "symbol": s or None, **json.loads(data)}
                for d, c, s, data in self.db.execute(q, args)]

    def history(self, dimension: str, cohort: str, symbol: Optional[str], since: float) -> List[dict]:
        return [{"ts": ts, **json.loads(data)} for ts, data in self.db.execute(
            "SELECT ts, data FROM cohort_snapshots WHERE dimension = ? AND cohort = ? AND symbol = ? AND ts >= ? ORDER BY ts",
            (dimension, cohort, symbol or "", int(since)))]

    def bias_history(self, since: float) -> Dict[tuple, List[tuple]]:
        out: Dict[tuple, List[tuple]] = {}
        for ts, d, c, s, data in self.db.execute(
                "SELECT ts, dimension, cohort, symbol, data FROM cohort_snapshots WHERE ts >= ?", (int(since),)):
            out.setdefault((d, c, s or None), []).append((ts, json.loads(data).get("bias")))
        return out

    # --- sweep audit ---------------------------------------------------------------
    def open_run(self, now: float) -> Tuple[int, float, bool]:
        """Resume the last unfinished sweep, or start one. Returns (id, started, resumed).
        A resumed sweep skips wallets already polled since it started."""
        row = self.db.execute("SELECT id, started FROM sweep_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return row[0], row[1], True
        cur = self.db.execute("INSERT INTO sweep_runs (started, status) VALUES (?, 'running')", (now,))
        self.db.commit()
        return cur.lastrowid, now, False

    def progress(self, run_id: int, due: int, polled: int, errors: int, rate_limited: int, weight: int) -> None:
        self.db.execute("UPDATE sweep_runs SET due = MAX(due, ?), polled = polled + ?, errors = errors + ?, "
                        "rate_limited = rate_limited + ?, weight = weight + ? WHERE id = ?",
                        (due, polled, errors, rate_limited, weight, run_id))
        self.db.commit()

    def close_run(self, run_id: int, now: float) -> None:
        self.db.execute("UPDATE sweep_runs SET status = 'done', finished = ?, duration_s = ? - started WHERE id = ?",
                        (now, now, run_id))
        self.db.commit()

    def runs(self, limit: int = 10) -> List[dict]:
        cols = ("id", "started", "finished", "status", "due", "polled", "errors", "rate_limited", "weight", "duration_s")
        return [dict(zip(cols, r)) for r in self.db.execute(
            f"SELECT {', '.join(cols)} FROM sweep_runs ORDER BY id DESC LIMIT ?", (limit,))]
