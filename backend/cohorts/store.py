"""SQLite storage for wallet cohorts (portable: the file can move to another host as is).

wallets              registry from the leaderboard: all-time PnL, polling schedule (next_poll_at,
                     streak = readings in a row without a position change, pinned = HyperLens roster)
wallet_state_latest  one row per wallet, overwritten each poll (no per-wallet history)
cohort_snapshots     aggregated rows per sweep: the time series
sweep_runs           audit: duration, weight used, errors; an unfinished run is resumed
coin_positioning     per coin, once per 4h candle: three merged groups (assign.COIN_GROUPS),
                     wallets and USD per side; every coin held, plus '' for all markets
coin_recent          the same groups plus profitable traders, once per 30 minutes, kept 3 days
                     (the coin page's last-24-hours strip)
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from cohorts.assign import COIN_GROUPS, Position, WalletState, coin_groups_from_rows
from hl_cadence import SETTLED_STREAK

RETENTION_DAYS = 180
RECENT_SLOT_S = 30 * 60        # coin_recent: one reading per 30-minute slot
RECENT_RETENTION_DAYS = 3
RECENT_GROUPS = ("profitable",) + COIN_GROUPS
COIN_RETENTION_DAYS = 400      # coin_positioning: small (about 65 KB a day), kept as long as trader_lean
RUNS_RETENTION_DAYS = 14       # sweep_runs rows (one per tick with work since the adaptive cadence)
PIN_ROSTER, PIN_ELITE = 1, 2   # wallets.pinned: HyperLens roster wallet; elite (read at least every 15 min)

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
    next_poll_at REAL NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 4
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
CREATE TABLE IF NOT EXISTS coin_positioning (
    coin TEXT NOT NULL,
    ts INTEGER NOT NULL,
    full INTEGER NOT NULL DEFAULT 1,
    winners_ln INTEGER NOT NULL DEFAULT 0, winners_sn INTEGER NOT NULL DEFAULT 0,
    winners_lu INTEGER NOT NULL DEFAULT 0, winners_su INTEGER NOT NULL DEFAULT 0,
    losers_ln INTEGER NOT NULL DEFAULT 0, losers_sn INTEGER NOT NULL DEFAULT 0,
    losers_lu INTEGER NOT NULL DEFAULT 0, losers_su INTEGER NOT NULL DEFAULT 0,
    whales_ln INTEGER NOT NULL DEFAULT 0, whales_sn INTEGER NOT NULL DEFAULT 0,
    whales_lu INTEGER NOT NULL DEFAULT 0, whales_su INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (coin, ts)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS coin_recent (
    coin TEXT NOT NULL,
    ts INTEGER NOT NULL,
    profitable_ln INTEGER, profitable_sn INTEGER, profitable_lu INTEGER, profitable_su INTEGER,
    winners_ln INTEGER NOT NULL DEFAULT 0, winners_sn INTEGER NOT NULL DEFAULT 0,
    winners_lu INTEGER NOT NULL DEFAULT 0, winners_su INTEGER NOT NULL DEFAULT 0,
    losers_ln INTEGER NOT NULL DEFAULT 0, losers_sn INTEGER NOT NULL DEFAULT 0,
    losers_lu INTEGER NOT NULL DEFAULT 0, losers_su INTEGER NOT NULL DEFAULT 0,
    whales_ln INTEGER NOT NULL DEFAULT 0, whales_sn INTEGER NOT NULL DEFAULT 0,
    whales_lu INTEGER NOT NULL DEFAULT 0, whales_su INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (coin, ts)
) WITHOUT ROWID;
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
        if "streak" not in cols:              # before the adaptive cadence: start everyone settled (60 min)
            self.db.execute(f"ALTER TABLE wallets ADD COLUMN streak INTEGER NOT NULL DEFAULT {SETTLED_STREAK}")
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

    def due(self, now: float, polled_since: Optional[float] = None) -> List[Tuple[str, Optional[float], int, int]]:
        """(address, all-time PnL, pinned, streak) of the wallets whose next reading is due.
        polled_since: skip wallets already polled since then (resuming an interrupted run)."""
        return self.db.execute(
            "SELECT w.address, w.all_time_pnl, w.pinned, w.streak FROM wallets w "
            "LEFT JOIN wallet_state_latest s ON s.address = w.address "
            "WHERE w.active = 1 AND w.next_poll_at <= ? AND (s.ts IS NULL OR s.ts < ?) "
            "ORDER BY w.pinned DESC, w.lb_value DESC",
            (now, polled_since if polled_since is not None else float("inf"))).fetchall()

    def registry_size(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM wallets WHERE active = 1").fetchone()[0]

    def set_pinned(self, addresses: Iterable[str], elite: Iterable[str] = ()) -> int:
        """The HyperLens roster: read on the adaptive cadence whatever their size (elite at least
        every 15 min). A wallet newly pinned is due at once."""
        el = {a.lower() for a in elite}
        addrs = {a.lower() for a in addresses} | el
        before = {r[0] for r in self.db.execute("SELECT address FROM wallets WHERE pinned > 0")}
        self.db.execute("UPDATE wallets SET pinned = 0 WHERE pinned > 0")
        self.db.executemany("UPDATE wallets SET pinned = ? WHERE address = ?",
                            [(PIN_ELITE if a in el else PIN_ROSTER, a) for a in addrs])
        self.db.executemany("UPDATE wallets SET next_poll_at = 0 WHERE address = ?", [(a,) for a in addrs - before])
        self.db.commit()
        return self.db.execute("SELECT COUNT(*) FROM wallets WHERE pinned > 0").fetchone()[0]

    def focus_size(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM wallets WHERE active = 1 AND focus = 1").fetchone()[0]

    # --- wallet state -------------------------------------------------------------
    def previous(self, address: str):
        """The wallet's last stored reading: ({(coin, long): first_seen}, book or None).
        book: {coin: (signed size, usd)}; None when there is no reading or it was stored before
        sizes were kept (then only the coin sides compare, see hl_cadence.changed_sides)."""
        row = self.db.execute("SELECT positions FROM wallet_state_latest WHERE address = ?", (address,)).fetchone()
        if not row:
            return {}, None
        ps = json.loads(row[0])
        first = {(p[0], bool(p[2])): p[3] for p in ps}
        if any(len(p) < 5 for p in ps):
            return first, None
        return first, {p[0]: (p[4] if p[2] else -p[4], p[1]) for p in ps}

    def previous_first_seen(self, address: str) -> Dict[Tuple[str, bool], float]:
        return self.previous(address)[0]

    def save_states(self, items: List[tuple]) -> None:
        """items: (address, ts, equity, [Position], focus, next_poll_at[, streak])"""
        self.db.executemany(
            "INSERT INTO wallet_state_latest (address, ts, equity, positions) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(address) DO UPDATE SET ts = excluded.ts, equity = excluded.equity, positions = excluded.positions",
            [(it[0], it[1], it[2], json.dumps([[p.coin, round(p.usd, 2), int(p.long), p.first_seen, float(f"{p.size:.6g}")]
                                               for p in it[3]], separators=(",", ":")))
             for it in items])
        self.db.executemany("UPDATE wallets SET focus = ?, next_poll_at = ?, streak = ? WHERE address = ?",
                            [(int(it[4]), it[5], it[6] if len(it) > 6 else SETTLED_STREAK, it[0]) for it in items])
        self.db.commit()

    def equities(self, since: float) -> Dict[str, float]:
        """address -> perp equity at the latest reading, for readings taken since ``since``."""
        return {a: eq for a, eq in self.db.execute(
            "SELECT address, equity FROM wallet_state_latest WHERE ts >= ?", (since,))}

    def load_states(self, now: float, max_age_s: float) -> List[WalletState]:
        out = []
        for a, eq, ps, pnl in self.db.execute(
                "SELECT s.address, s.equity, s.positions, w.all_time_pnl FROM wallet_state_latest s "
                "JOIN wallets w ON w.address = s.address WHERE w.active = 1 AND w.focus = 1 AND s.ts >= ?", (now - max_age_s,)):
            out.append(WalletState(a, eq, pnl, [Position(p[0], p[1], bool(p[2]), p[3], p[4] if len(p) > 4 else 0.0)
                                                for p in json.loads(ps)]))
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

    def history_all(self, dimension: str, symbol: Optional[str], since: float) -> Dict[str, List[dict]]:
        """Every cohort's rows for one dimension and market, oldest first."""
        out: Dict[str, List[dict]] = {}
        for ts, c, data in self.db.execute(
                "SELECT ts, cohort, data FROM cohort_snapshots WHERE dimension = ? AND symbol = ? AND ts >= ? ORDER BY ts",
                (dimension, symbol or "", int(since))):
            out.setdefault(c, []).append({"ts": ts, **json.loads(data)})
        return out

    def coverage(self) -> dict:
        """When collection started and how many all-market and per-symbol readings exist."""
        first, n_all = self.db.execute("SELECT MIN(ts), COUNT(DISTINCT ts) FROM cohort_snapshots WHERE symbol = ''").fetchone()
        n_sym = self.db.execute("SELECT COUNT(DISTINCT ts) FROM cohort_snapshots WHERE symbol != ''").fetchone()[0]
        return {"since": first, "readings": n_all or 0, "symbol_readings": n_sym or 0}

    def symbols_at(self, ts: int) -> List[str]:
        return [r[0] for r in self.db.execute(
            "SELECT DISTINCT symbol FROM cohort_snapshots WHERE ts = ? AND symbol != '' ORDER BY symbol", (ts,))]

    def bias_history(self, since: float) -> Dict[tuple, List[tuple]]:
        out: Dict[tuple, List[tuple]] = {}
        for ts, d, c, s, data in self.db.execute(
                "SELECT ts, dimension, cohort, symbol, data FROM cohort_snapshots WHERE ts >= ?", (int(since),)):
            out.setdefault((d, c, s or None), []).append((ts, json.loads(data).get("bias")))
        return out

    # --- per-coin record (coin page) -----------------------------------------------
    # On the '' row, full = 1 when every coin held was written at that time; 0 for times filled
    # from the 40-coin cohort rows, where a missing coin means "not recorded", not "nobody holds it".
    _COIN_COLS = tuple(f"{g}_{k}" for g in COIN_GROUPS for k in ("ln", "sn", "lu", "su"))

    def write_coin_groups(self, ts: int, groups: Dict[str, Dict[str, list]], full: bool = True,
                          commit: bool = True) -> int:
        rows = []
        for coin, by in groups.items():
            vals = []
            for g in COIN_GROUPS:
                c = by.get(g) or (0, 0, 0, 0)
                vals += [int(c[0]), int(c[1]), int(round(c[2])), int(round(c[3]))]
            rows.append((coin, int(ts), int(full), *vals))
        if "" not in groups:              # the time marker: this time was recorded
            rows.append(("", int(ts), int(full), *([0] * len(self._COIN_COLS))))
        cols = ", ".join(self._COIN_COLS)
        self.db.executemany(
            f"INSERT OR REPLACE INTO coin_positioning (coin, ts, full, {cols}) "
            f"VALUES ({', '.join('?' * (3 + len(self._COIN_COLS)))})", rows)
        if commit:
            # The key is (coin, ts), so deleting by time scans the table: at most once a day.
            cutoff = int(ts) - COIN_RETENTION_DAYS * 86400
            oldest = self.db.execute("SELECT MIN(ts) FROM coin_positioning WHERE coin = ''").fetchone()[0]
            if oldest is not None and oldest < cutoff - 86400:
                self.db.execute("DELETE FROM coin_positioning WHERE ts < ?", (cutoff,))
            self.db.commit()
        return len(rows)

    def latest_coin_ts(self) -> Optional[int]:
        row = self.db.execute("SELECT MAX(ts) FROM coin_positioning WHERE coin = ''").fetchone()
        return row[0] if row and row[0] else None

    def coin_history(self, coin: str, since: float) -> Tuple[List[Tuple[int, int]], Dict[int, tuple]]:
        """([(ts, full)] of every recorded time, {ts: (12 values in _COIN_COLS order)} for the coin)."""
        times = self.db.execute("SELECT ts, full FROM coin_positioning WHERE coin = '' AND ts >= ? ORDER BY ts",
                                (int(since),)).fetchall()
        cols = ", ".join(self._COIN_COLS)
        vals = {r[0]: tuple(r[1:]) for r in self.db.execute(
            f"SELECT ts, {cols} FROM coin_positioning WHERE coin = ? AND ts >= ?", (coin, int(since)))}
        return times, vals

    def backfill_coin_groups(self) -> int:
        """Once, while coin_positioning is empty: fill it from the per-symbol cohort rows already
        stored (the 40 largest coins at each 4h candle), so those coins start with their history."""
        if self.db.execute("SELECT 1 FROM coin_positioning LIMIT 1").fetchone():
            return 0
        times = [r[0] for r in self.db.execute(
            "SELECT DISTINCT ts FROM cohort_snapshots WHERE symbol != '' ORDER BY ts")]
        n = 0
        try:
            for ts in times:
                rows = [{"dimension": d, "cohort": c, "symbol": sym or None, **json.loads(data)}
                        for d, c, sym, data in self.db.execute(
                            "SELECT dimension, cohort, symbol, data FROM cohort_snapshots WHERE ts = ?", (ts,))]
                n += self.write_coin_groups(ts, coin_groups_from_rows(rows), full=False, commit=False)
        except Exception:
            self.db.rollback()
            raise
        self.db.commit()
        return n

    # --- the last few days every 30 minutes (coin page strip) ----------------------
    # profitable_* NULL on the '' row: profitable traders were not available at that time (a gap);
    # otherwise a coin missing at a recorded time means nobody in the group held it.
    _RECENT_COLS = tuple(f"{g}_{k}" for g in RECENT_GROUPS for k in ("ln", "sn", "lu", "su"))

    def write_recent(self, ts: int, groups: Dict[str, Dict[str, list]], profitable: Optional[Dict[str, dict]]) -> int:
        coins = set(groups) | set(profitable or {}) | {""}
        rows = []
        for coin in coins:
            if profitable is None:
                vals = [None] * 4
            else:
                p = profitable.get(coin) or {}
                vals = [int(p.get("long") or 0), int(p.get("short") or 0),
                        int(round(p.get("long_usd") or 0)), int(round(p.get("short_usd") or 0))]
            by = groups.get(coin, {})
            for g in COIN_GROUPS:
                c = by.get(g) or (0, 0, 0, 0)
                vals += [int(c[0]), int(c[1]), int(round(c[2])), int(round(c[3]))]
            rows.append((coin, int(ts), *vals))
        cols = ", ".join(self._RECENT_COLS)
        self.db.executemany(f"INSERT OR REPLACE INTO coin_recent (coin, ts, {cols}) "
                            f"VALUES ({', '.join('?' * (2 + len(self._RECENT_COLS)))})", rows)
        cutoff = int(ts) - RECENT_RETENTION_DAYS * 86400
        oldest = self.db.execute("SELECT MIN(ts) FROM coin_recent WHERE coin = ''").fetchone()[0]
        if oldest is not None and oldest < cutoff - 3600:       # at most hourly: the delete scans the table
            self.db.execute("DELETE FROM coin_recent WHERE ts < ?", (cutoff,))
        self.db.commit()
        return len(rows)

    def latest_recent_ts(self) -> Optional[int]:
        row = self.db.execute("SELECT MAX(ts) FROM coin_recent WHERE coin = ''").fetchone()
        return row[0] if row and row[0] else None

    def recent_history(self, coin: str, since: float) -> Tuple[List[Tuple[int, bool]], Dict[int, tuple]]:
        """([(ts, profitable recorded)] of every recorded time, {ts: 16 values in _RECENT_COLS order})."""
        times = [(ts, p is not None) for ts, p in self.db.execute(
            "SELECT ts, profitable_ln FROM coin_recent WHERE coin = '' AND ts >= ? ORDER BY ts", (int(since),))]
        cols = ", ".join(self._RECENT_COLS)
        vals = {r[0]: tuple(r[1:]) for r in self.db.execute(
            f"SELECT ts, {cols} FROM coin_recent WHERE coin = ? AND ts >= ?", (coin, int(since)))}
        return times, vals

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
        self.db.execute("DELETE FROM sweep_runs WHERE started < ? AND status = 'done'", (now - RUNS_RETENTION_DAYS * 86400,))
        self.db.commit()

    def cadence_counts(self) -> Dict[str, int]:
        """Followed-set wallets (focus or pinned) by how many readings in a row showed no change."""
        return {f"streak_{k}": n for k, n in self.db.execute(
            "SELECT streak, COUNT(*) FROM wallets WHERE active = 1 AND (focus = 1 OR pinned > 0) GROUP BY streak")}

    def runs(self, limit: int = 10) -> List[dict]:
        cols = ("id", "started", "finished", "status", "due", "polled", "errors", "rate_limited", "weight", "duration_s")
        return [dict(zip(cols, r)) for r in self.db.execute(
            f"SELECT {', '.join(cols)} FROM sweep_runs ORDER BY id DESC LIMIT ?", (limit,))]
