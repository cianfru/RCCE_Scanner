"""
The Radar's forward record: one reading per coin per daily close (00:00 UTC), for the declared
test in docs/reviews/radar-forward-test.md. Scored by research/radar_forward.py.

After each 1D close is processed (from 30 minutes after it, once 90% of the map's coins have that
day's candle in the store, or at 2 hours regardless; never later than 6 hours), the 1D Radar
(setup_map.build, as /api/setup-map?tf=1d) is written to ``radar_readings`` in the HyperLens
SQLite store, next to trader_lean. One row per coin per close (INSERT OR IGNORE); rows are kept
indefinitely (about 180 a day: about 130 bytes a row, 23 KB a day, 8.5 MB a year).

Nothing here calls an outside API: the map is built from data in memory.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from typing import Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

DAY = 86400
SCHEMA_VERSION = 1
READ_FROM = 30 * 60          # first check after the close
READ_BY = 2 * 3600           # read regardless of the candles from here
READ_UNTIL = 6 * 3600        # later than this the close is missing (never back-filled)
READY_SHARE = 0.9            # share of coins with the day's candle in the store

_SCHEMA = """
CREATE TABLE IF NOT EXISTS radar_readings (
    day INTEGER NOT NULL,            -- the daily close, epoch seconds at 00:00 UTC
    coin TEXT NOT NULL,
    taken_at REAL NOT NULL,
    zone TEXT, stage TEXT, crowd TEXT,
    long INTEGER NOT NULL, short INTEGER NOT NULL,
    net_24h INTEGER,                 -- (long - short) now minus 24h before; NULL without a record
    gross_usd REAL NOT NULL,
    band_state TEXT, band_fill REAL,
    z REAL, price REAL,
    close REAL,                      -- the stored daily candle close for this day
    avg_long_entry REAL, entry_dist REAL, in_zone INTEGER NOT NULL,
    shown INTEGER NOT NULL,          -- on the Radar's default view
    roster_version INTEGER,
    schema_version INTEGER NOT NULL,
    PRIMARY KEY (day, coin)
) WITHOUT ROWID;
"""
COLUMNS = ("day", "coin", "taken_at", "zone", "stage", "crowd", "long", "short", "net_24h", "gross_usd",
           "band_state", "band_fill", "z", "price", "close", "avg_long_entry", "entry_dist", "in_zone", "shown",
           "roster_version", "schema_version")


def conn() -> sqlite3.Connection:
    from hl_persistence import _get_conn
    c = _get_conn()
    ensure(c)
    return c


def ensure(c: sqlite3.Connection) -> None:
    c.executescript(_SCHEMA)


def day_of(now: float) -> int:
    """The latest daily close at or before ``now``."""
    return int(now // DAY * DAY)


def shown(c: dict) -> bool:
    """The Radar's default view (frontend utils/setupMap.js visible): a z-score, not waiting, and
    at least one profitable trader in it or forming or just fired."""
    t = c.get("traders") or {}
    return c.get("zscore") is not None and c.get("stage") != "waiting" and (
        (t.get("pl") or 0) + (t.get("ps") or 0) > 0 or c.get("stage") in ("forming", "fresh"))


def day_close(ohlcv: Optional[dict], day: int) -> Optional[float]:
    """The close of the daily candle that ends at ``day`` (00:00 UTC), from the store."""
    import setup_map
    ts, cs = setup_map.closes(ohlcv, "1d", day + 1)
    return cs[-1] if ts and ts[-1] == day else None


def readings(smap: dict, day: int, before: Dict[str, dict], close_of: Callable[[str], Optional[float]],
             roster_version: Optional[int], now: float) -> List[tuple]:
    """Rows for one close: every coin on the 1D map with a z-score."""
    rows = []
    for c in smap.get("coins") or []:
        if c.get("zscore") is None:
            continue
        t = c.get("traders") or {}
        lo, sh = t.get("pl") or 0, t.get("ps") or 0
        b = before.get(c["coin"])
        band = c.get("band") or {}
        e = c.get("entry") or {}
        rows.append((day, c["coin"], now, c.get("zone"), c.get("stage"), c.get("crowd"), lo, sh,
                     (lo - sh) - (b["long"] - b["short"]) if b else None,
                     float((c.get("money") or {}).get("gross_usd") or 0), band.get("state"), band.get("fill"),
                     c.get("zscore"), c.get("price"), close_of(c["symbol"]),
                     e.get("avg_long_entry"), None if e.get("dist_pct") is None else e["dist_pct"] / 100,
                     int(bool(e.get("in_zone"))), int(shown(c)), roster_version, SCHEMA_VERSION))
    return rows


def write(c: sqlite3.Connection, rows: Iterable[tuple]) -> int:
    """Insert rows; a coin already read at that close keeps its first reading."""
    cur = c.executemany(f"INSERT OR IGNORE INTO radar_readings ({', '.join(COLUMNS)}) "
                        f"VALUES ({', '.join('?' * len(COLUMNS))})", list(rows))
    c.commit()
    return cur.rowcount


def logged(c: sqlite3.Connection, day: int) -> bool:
    return c.execute("SELECT 1 FROM radar_readings WHERE day = ? LIMIT 1", (day,)).fetchone() is not None


def load(c: sqlite3.Connection) -> List[dict]:
    cur = c.execute(f"SELECT {', '.join(COLUMNS)} FROM radar_readings ORDER BY day, coin")
    return [dict(zip(COLUMNS, r)) for r in cur.fetchall()]


def ready(smap: dict, day: int, has_candle: Callable[[str], bool]) -> bool:
    coins = [c for c in smap.get("coins") or [] if c.get("zscore") is not None]
    return bool(coins) and sum(1 for c in coins if has_candle(c["symbol"])) >= READY_SHARE * len(coins)


def take(c: sqlite3.Connection, now: float, build_map: Callable[[], dict], load_before: Callable[[dict, float], Dict[str, dict]],
         candles: Callable[[str], Optional[dict]], roster_version: Optional[int]) -> int:
    """One attempt: returns rows written (0 when outside the window, not ready or already logged)."""
    day = day_of(now)
    age = now - day
    if age < READ_FROM or age > READ_UNTIL or logged(c, day):
        return 0
    smap = build_map()
    close_of = lambda sym: day_close(candles(sym), day)
    if age < READ_BY and not ready(smap, day, lambda sym: close_of(sym) is not None):
        return 0
    rows = readings(smap, day, load_before(smap, now), close_of, roster_version, now)
    return write(c, rows) if rows else 0


async def run(build_map: Callable[[], dict], load_before: Callable[[dict, float], Dict[str, dict]],
              candles: Callable[[str], Optional[dict]], poll_seconds: int = 300) -> None:
    """Background loop in the server: one attempt every five minutes (a DB check outside the window)."""
    if os.environ.get("RADAR_LOG_ENABLED", "1") == "0":
        logger.info("Radar log disabled")
        return
    await asyncio.sleep(90)
    while True:
        try:
            import hl_intelligence
            now = time.time()
            if READ_FROM <= now - day_of(now) <= READ_UNTIL:
                n = await asyncio.to_thread(take, conn(), now, build_map, load_before, candles, hl_intelligence.record_version())
                if n:
                    logger.info("Radar log: %d readings for the close of %s", n, time.strftime("%Y-%m-%d", time.gmtime(day_of(now))))
        except Exception:
            logger.exception("Radar log failed (non-fatal)")
        await asyncio.sleep(poll_seconds)
