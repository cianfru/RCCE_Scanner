"""Versioned decision snapshots and deduplicated opportunity transitions."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from opportunities import meaningful_transition


class OpportunityJournal:
    def __init__(self, path=None):
        root = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or Path(__file__).parent / "data")
        path = Path(path or os.environ.get("OPPORTUNITY_DB_PATH", str(root / "opportunities.db")))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.retention_days = max(0, int(os.environ.get("OPPORTUNITY_RETENTION_DAYS", "90")))
        self.last_prune = 0
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS snapshots (
            symbol TEXT, timeframe TEXT, candle REAL, version TEXT, payload TEXT,
            PRIMARY KEY(symbol, timeframe, candle, version));
          CREATE TABLE IF NOT EXISTS states (symbol TEXT, timeframe TEXT, payload TEXT, PRIMARY KEY(symbol,timeframe));
          CREATE TABLE IF NOT EXISTS transitions (id INTEGER PRIMARY KEY, observed_at REAL, symbol TEXT,
            timeframe TEXT, opportunity_id TEXT, status TEXT, payload TEXT);
        """)

    def previous(self, symbol, timeframe):
        row = self.db.execute("SELECT payload FROM states WHERE symbol=? AND timeframe=?", (symbol, timeframe)).fetchone()
        return json.loads(row[0]) if row else None

    def record(self, row, opportunity, *, as_of):
        symbol, tf = row["symbol"], row["timeframe"]
        previous = self.previous(symbol, tf)
        changed = meaningful_transition(previous, opportunity)
        encode = lambda obj: json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
        payload = encode(opportunity)
        with self.db:
            # First observation of each candle is immutable: replay never sees later corrections/context.
            self.db.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?)",
                (symbol, tf, row.get("signal_bar_close_time"), row.get("decision_version"), encode(row)))
            self.db.execute("INSERT OR REPLACE INTO states VALUES (?,?,?)", (symbol, tf, payload))
            if changed:
                self.db.execute("INSERT INTO transitions(observed_at,symbol,timeframe,opportunity_id,status,payload) VALUES (?,?,?,?,?,?)",
                    (as_of, symbol, tf, opportunity["id"], opportunity["status"], payload))
        if self.retention_days and as_of - self.last_prune >= 86400:
            cutoff = as_of - self.retention_days * 86400
            with self.db:
                self.db.execute("DELETE FROM snapshots WHERE candle < ?", (cutoff,))
                self.db.execute("DELETE FROM transitions WHERE observed_at < ?", (cutoff,))
            self.last_prune = as_of
        return changed

    def recent(self, limit=100):
        return [dict(r) for r in self.db.execute("SELECT * FROM transitions ORDER BY id DESC LIMIT ?", (min(500, max(1, limit)),))]

    def close(self):
        self.db.close()
