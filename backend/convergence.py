"""
Tracked wallets opening positions, and profitable traders converging on one coin
(docs/reviews/trader-convergence-forward-test.md).

Every sweep reading of a tracked wallet is compared with its previous reading: a coin
and side it did not hold before is an open, timed at the reading (so within one sweep,
about 30 minutes) at the position's entry price. The first reading of a wallet after a
start only sets its baseline, so nothing it already held counts as an open.

A convergence: at least MIN_WALLETS profitable traders open the same side of one coin
within WINDOW_S, all still holding, the latest entry within MAX_MOVE of the first, and
at most MAX_OTHERS other profitable traders already on that side. It is recorded and
alerted once, again only if more wallets join.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

WINDOW_S = 24 * 3600
MIN_WALLETS = 2
MAX_MOVE = 0.05
MAX_OTHERS = 2
MAX_GAP_S = 2 * 3600       # an open seen after a longer gap (e.g. a restart) is not timed well enough
RETENTION_DAYS = 180

_SCHEMA = """
CREATE TABLE IF NOT EXISTS position_opens (
    ts REAL NOT NULL,
    prev_ts REAL NOT NULL,
    address TEXT NOT NULL,
    cohort TEXT NOT NULL,
    coin TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_px REAL NOT NULL,
    size_usd REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opens_coin_ts ON position_opens(coin, ts);
CREATE TABLE IF NOT EXISTS convergences (
    ts REAL NOT NULL,
    coin TEXT NOT NULL,
    side TEXT NOT NULL,
    n INTEGER NOT NULL,
    first_ts REAL NOT NULL,
    first_px REAL NOT NULL,
    last_px REAL NOT NULL,
    mark_px REAL,
    others INTEGER NOT NULL,
    wallets TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_ts ON convergences(ts);
"""

Key = Tuple[str, str]  # (coin, side)


def find_convergence(opens: List[dict], holding: Dict[str, set], key: Key, now: float) -> Optional[dict]:
    """The convergence on ``key`` at ``now``, or None.

    ``opens``: profitable-trader opens (dicts with ts, prev_ts, address, coin, side, entry_px, size_usd).
    ``holding``: address -> set of (coin, side) currently held, profitable traders only.
    """
    group: Dict[str, dict] = {}
    for o in sorted(opens, key=lambda o: o["ts"]):
        if (o["coin"], o["side"]) == key and now - o["ts"] <= WINDOW_S and o["ts"] - o["prev_ts"] <= MAX_GAP_S \
                and key in holding.get(o["address"], ()):
            group.setdefault(o["address"], o)            # each wallet's first open in the window
    if len(group) < MIN_WALLETS:
        return None
    members = sorted(group.values(), key=lambda o: o["ts"])
    first, last = members[0], members[-1]
    if abs(last["entry_px"] / first["entry_px"] - 1) > MAX_MOVE:
        return None
    others = sum(1 for a, held in holding.items() if a not in group and key in held)
    if others > MAX_OTHERS:
        return None
    return {"coin": key[0], "side": key[1], "n": len(members), "first_ts": first["ts"], "first_px": first["entry_px"],
            "last_ts": last["ts"], "last_px": last["entry_px"], "others": others,
            "wallets": [{"address": o["address"], "ts": o["ts"], "entry_px": o["entry_px"], "size_usd": o["size_usd"]}
                        for o in members]}


class Tracker:
    def __init__(self, conn=None, clock=time.time):
        self.conn, self.clock = conn, clock
        self.held: Dict[str, Dict[Key, dict]] = {}    # address -> {(coin, side): position}
        self.seen_ts: Dict[str, float] = {}
        self.cohort: Dict[str, str] = {}
        self.opens: List[dict] = []                    # last WINDOW_S of opens, all cohorts
        self.fired: Dict[Key, Tuple[float, int]] = {}  # key -> (when, n) of the last alert
        self.started = clock()
        if conn is not None:
            conn.executescript(_SCHEMA)
            since = self.started - WINDOW_S
            cols = ("ts", "prev_ts", "address", "cohort", "coin", "side", "entry_px", "size_usd")
            self.opens = [dict(zip(cols, r)) for r in conn.execute(
                f"SELECT {', '.join(cols)} FROM position_opens WHERE ts >= ? ORDER BY ts", (since,))]
            for ts, coin, side, n in conn.execute(
                    "SELECT ts, coin, side, n FROM convergences WHERE ts >= ?", (since,)):
                if n >= self.fired.get((coin, side), (0, 0))[1]:
                    self.fired[(coin, side)] = (ts, n)

    def observe(self, address: str, cohort: str, ts: float, positions: Iterable[dict]) -> List[dict]:
        """One wallet reading. ``positions``: dicts with coin, side ('long'/'short'), entry_px,
        size_usd, mark_px. Returns the opens it reveals."""
        if ts <= self.seen_ts.get(address, 0):
            return []
        cur = {(p["coin"], p["side"]): p for p in positions}
        prev, prev_ts = self.held.get(address), self.seen_ts.get(address)
        self.held[address], self.seen_ts[address], self.cohort[address] = cur, ts, cohort
        if prev is None:
            return []
        new = [{"ts": ts, "prev_ts": prev_ts, "address": address, "cohort": cohort, "coin": k[0], "side": k[1],
                "entry_px": float(p["entry_px"]), "size_usd": float(p["size_usd"])}
               for k, p in cur.items() if k not in prev and p.get("entry_px")]
        self.opens += new
        return new

    def forget(self, addresses: Iterable[str]) -> None:
        for a in addresses:
            self.held.pop(a, None)
            self.seen_ts.pop(a, None)
            self.cohort.pop(a, None)

    def check(self, new_opens: List[dict]) -> List[dict]:
        """Convergences completed or grown by these opens (recorded; returned for alerts)."""
        now = self.clock()
        self.opens = [o for o in self.opens if now - o["ts"] <= WINDOW_S]
        prof_opens = [o for o in self.opens if o["cohort"] == "profitable"]
        holding = {a: set(h) for a, h in self.held.items() if self.cohort.get(a) == "profitable"}
        out = []
        for key in {(o["coin"], o["side"]) for o in new_opens if o["cohort"] == "profitable"}:
            c = find_convergence(prof_opens, holding, key, now)
            if c is None:
                continue
            when, n = self.fired.get(key, (0.0, 0))
            if now - when < WINDOW_S and c["n"] <= n:
                continue
            c["ts"] = now
            last = next((h[key] for a, h in self.held.items() if key in h and h[key].get("mark_px")), None)
            c["mark_px"] = last["mark_px"] if last else None
            self.fired[key] = (now, c["n"])
            out.append(c)
        self._save(new_opens, out)
        return out

    def _save(self, opens: List[dict], convs: List[dict]) -> None:
        if self.conn is None or not (opens or convs):
            return
        try:
            self.conn.executemany(
                "INSERT INTO position_opens (ts, prev_ts, address, cohort, coin, side, entry_px, size_usd) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(o["ts"], o["prev_ts"], o["address"], o["cohort"], o["coin"], o["side"], o["entry_px"], o["size_usd"])
                 for o in opens])
            self.conn.executemany(
                "INSERT INTO convergences (ts, coin, side, n, first_ts, first_px, last_px, mark_px, others, wallets) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(c["ts"], c["coin"], c["side"], c["n"], c["first_ts"], c["first_px"], c["last_px"], c["mark_px"],
                  c["others"], json.dumps(c["wallets"])) for c in convs])
            cutoff = self.clock() - RETENTION_DAYS * 86400
            self.conn.execute("DELETE FROM position_opens WHERE ts < ?", (cutoff,))
            self.conn.execute("DELETE FROM convergences WHERE ts < ?", (cutoff,))
            self.conn.commit()
        except Exception as exc:
            logger.warning("convergence: save failed: %s", exc)

    # ---- reads -------------------------------------------------------------------------
    def opens_for(self, coin: str, since: float) -> List[dict]:
        if self.conn is None:
            return [o for o in self.opens if o["coin"] == coin and o["ts"] >= since]
        cols = ("ts", "prev_ts", "cohort", "side", "entry_px", "size_usd")
        return [dict(zip(cols, r)) for r in self.conn.execute(
            f"SELECT {', '.join(cols)} FROM position_opens WHERE coin = ? AND ts >= ? ORDER BY ts", (coin, since))]

    def convergences_since(self, since: float, coin: Optional[str] = None) -> List[dict]:
        if self.conn is None:
            return []
        cols = ("ts", "coin", "side", "n", "first_ts", "first_px", "last_px", "mark_px", "others", "wallets")
        q = f"SELECT {', '.join(cols)} FROM convergences WHERE ts >= ?" + (" AND coin = ?" if coin else "") + " ORDER BY ts DESC"
        rows = [dict(zip(cols, r)) for r in self.conn.execute(q, (since, coin) if coin else (since,))]
        for r in rows:
            r["wallets"] = json.loads(r["wallets"])
        return rows

    def tracking_since(self) -> Optional[float]:
        if self.conn is None:
            return self.started
        row = self.conn.execute("SELECT MIN(ts) FROM position_opens").fetchone()
        return min(row[0], self.started) if row and row[0] else self.started


_tracker: Optional[Tracker] = None


def tracker() -> Tracker:
    global _tracker
    if _tracker is None:
        from hl_persistence import _get_conn
        _tracker = Tracker(_get_conn())
    return _tracker
