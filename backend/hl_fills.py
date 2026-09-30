"""
Stored fills of the tracked wallets (the HyperLens roster), so trader profiles, their fills and
history, the coin page's trader entries and the leaderboard's win rates are read from our
database instead of a Hyperliquid ``userFills`` request per page view.

Store (fills.db, next to hyperlens.db): one row per perpetual fill, the fields the fill
classification needs (time, coin, side, price, size, position before, direction, closed PnL,
fee, timed-order flag). Keyed by (wallet, time, trade id, side, timed-order flag), so a fill
read twice is stored once, and a wallet's fills are one range of the key in time order.
Spot and builder-dex fills are not kept. Kept RETENTION_DAYS (180) and at most
MAX_FILLS_PER_WALLET (the newest 10,000) per wallet; a wallet off the roster for OFF_ROSTER_DAYS
is dropped.

Fetching, one wallet at a time on this module's own share of Hyperliquid's per-IP budget:

    backfill      once per wallet: ``userFillsByTime`` from RETENTION_DAYS ago, 2,000 a page
                  (Hyperliquid keeps a wallet's 10,000 latest), and its timed-order slices
    on a change   the position poller saw the wallet's positions change: only the fills since
                  the last stored one (``userFillsByTime`` and ``userTwapSliceFillsByTime``)
    on a view     a profile whose live positions differ from the stored fills, at most once per
                  wallet every VIEW_REFRESH_S
    sweep         every wallet every SWEEP_S (12 h, +-10%), for trades opened and closed between
                  two position readings

Weight: 20 per request plus 1 per 20 fills returned. The store has WEIGHT_PER_MIN (300) of the
1,200 a minute; the backfill may use at most BACKFILL_WEIGHT_PER_MIN (240) of it, so the
incremental reads always have room, and pauses during the quiet window after each 4-hour close.

Wallets not on the roster (a pasted address) are read live in trader_profile, shared between
viewers for a few minutes, and at most LIVE_LOADS_PER_MIN such reads a minute across all users;
past that the request is answered "busy" (``Busy``).
"""
from __future__ import annotations

import asyncio
import collections
import logging
import os
import sqlite3
import threading
import time
import zlib
from pathlib import Path
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

import aiohttp

import hl_calls

logger = logging.getLogger(__name__)

INFO_URL = "https://api.hyperliquid.xyz/info"
RETENTION_DAYS = int(os.environ.get("FILLS_RETENTION_DAYS", "180"))
MAX_FILLS_PER_WALLET = int(os.environ.get("FILLS_MAX_PER_WALLET", "10000"))
WEIGHT_PER_MIN = float(os.environ.get("FILLS_WEIGHT_PER_MIN", "300"))
BACKFILL_WEIGHT_PER_MIN = min(WEIGHT_PER_MIN, float(os.environ.get("FILLS_BACKFILL_WEIGHT_PER_MIN", "240")))
LIVE_LOADS_PER_MIN = int(os.environ.get("TRADER_LIVE_LOADS_PER_MIN", "6"))
SWEEP_S = 12 * 3600
VIEW_REFRESH_S = 10 * 60        # a view asks for a wallet's new fills at most this often
MIN_RESYNC_S = 60               # a change or view read is skipped when the wallet was read this recently
OFF_ROSTER_DAYS = 7
MAINTAIN_EVERY_S = 6 * 3600
START_DELAY_S = 60
PAGE = 2000                     # fills per answer (Hyperliquid's cap)
HL_RECENT_CAP = 10_000          # Hyperliquid serves a wallet's latest 10,000 fills by time
MAX_PAGES = 8                   # per request type per read; the rest continues at the next read
OVERLAP_MS = 5_000              # re-read the last seconds before the cursor (duplicates are ignored)
CALL_WEIGHT = 20
MAX_VIEW_REQUESTS = 20
LOAD_CACHE_WALLETS = 8

_FIELDS = ("coin", "time", "px", "sz", "side", "dir", "startPosition", "twap", "tid", "closedPnl", "fee")


def enabled() -> bool:
    return os.environ.get("FILLS_STORE_ENABLED", "1") not in ("0", "false", "no")


def default_path() -> str:
    env = os.environ.get("FILLS_DB_PATH")
    if env:
        return env
    hl = os.environ.get("HYPERLENS_DB_PATH")
    base = os.path.dirname(hl) if hl else str(Path(__file__).resolve().parent)
    return os.path.join(base, "fills.db")


def is_perp_fill(f: dict) -> bool:
    """Same rule as trader_profile.is_perp_fill (native perpetuals only)."""
    coin = str(f.get("coin") or "")
    d = str(f.get("dir") or "")
    return bool(coin) and not coin.startswith("@") and "/" not in coin and ":" not in coin \
        and ("Long" in d or "Short" in d)


class Busy(Exception):
    """Too many live reads of untracked wallets this minute."""

    def __init__(self, retry_after: float):
        super().__init__("Busy, try again shortly")
        self.retry_after = max(1, int(retry_after + 0.999))


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY,
    address TEXT NOT NULL UNIQUE,
    backfilled_at REAL,          -- first complete read (NULL: backfill pending)
    covered_from REAL,           -- fills may be missing before this time (s)
    cursor_ms INTEGER,           -- regular fills read up to here
    twap_cursor_ms INTEGER,      -- timed-order slices read up to here
    synced_at REAL,
    n INTEGER NOT NULL DEFAULT 0,
    twap_seen INTEGER NOT NULL DEFAULT 0,
    off_roster_at REAL
);
CREATE TABLE IF NOT EXISTS fills (
    wallet INTEGER NOT NULL,
    time INTEGER NOT NULL,       -- ms
    tid INTEGER NOT NULL,
    side TEXT NOT NULL,          -- B / A
    twap INTEGER NOT NULL,
    coin TEXT NOT NULL,
    px TEXT NOT NULL,
    sz TEXT NOT NULL,
    start_pos TEXT,
    dir TEXT,
    closed_pnl TEXT,
    fee TEXT,
    PRIMARY KEY (wallet, time, tid, side, twap)
) WITHOUT ROWID;
"""


def row_of(f: dict, twap: bool) -> tuple:
    """Hyperliquid fill -> stored columns after the wallet id (strings kept as sent)."""
    return (int(f["time"]), int(f.get("tid") or 0), str(f.get("side") or ""), int(bool(twap)), str(f["coin"]),
            str(f["px"]), str(f["sz"]), _s(f.get("startPosition")), _s(f.get("dir")),
            _s(f.get("closedPnl")), _s(f.get("fee")))


def _s(x) -> Optional[str]:
    return None if x is None else str(x)


def fill_of(r: tuple) -> dict:
    """Stored row (time, tid, side, twap, coin, px, sz, start, dir, pnl, fee) -> the fill shape
    trader_entries and trader_profile read (the live path's fields)."""
    t, tid, side, twap, coin, px, sz, start, d, pnl, fee = r
    return {"coin": coin, "time": t, "px": px, "sz": sz, "side": side, "dir": d, "startPosition": start,
            "twap": bool(twap), "tid": tid, "closedPnl": pnl, "fee": fee}


class Store:
    def __init__(self, path: Optional[str] = None):
        self.path = path or default_path()
        if os.path.dirname(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        new = not os.path.exists(self.path)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        if new:
            self.db.execute("PRAGMA auto_vacuum=INCREMENTAL")    # pruned pages go back to the disk
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def wallets(self) -> Dict[str, dict]:
        cols = ("id", "address", "backfilled_at", "covered_from", "cursor_ms", "twap_cursor_ms", "synced_at", "n",
                "twap_seen", "off_roster_at")
        with self.lock:
            rows = self.db.execute(f"SELECT {', '.join(cols)} FROM wallets").fetchall()
        return {r[1]: dict(zip(cols, r)) for r in rows}

    def wallet(self, address: str) -> dict:
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO wallets (address) VALUES (?)", (address,))
            self.db.commit()
        return self.wallets_by("address = ?", (address,))[0]

    def wallets_by(self, where: str, args: tuple) -> List[dict]:
        cols = ("id", "address", "backfilled_at", "covered_from", "cursor_ms", "twap_cursor_ms", "synced_at", "n",
                "twap_seen", "off_roster_at")
        with self.lock:
            rows = self.db.execute(f"SELECT {', '.join(cols)} FROM wallets WHERE {where}", args).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def update(self, wid: int, **fields) -> None:
        if not fields:
            return
        with self.lock:
            self.db.execute(f"UPDATE wallets SET {', '.join(k + ' = ?' for k in fields)} WHERE id = ?",
                            (*fields.values(), wid))
            self.db.commit()

    def insert(self, wid: int, rows: Iterable[tuple]) -> int:
        """Fills not already stored; returns how many were new."""
        rows = [(wid, *r) for r in rows]
        if not rows:
            return 0
        with self.lock:
            before = self.db.total_changes
            self.db.executemany("INSERT OR IGNORE INTO fills VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self.db.commit()
            return self.db.total_changes - before

    def load(self, wid: int) -> List[tuple]:
        with self.lock:
            return self.db.execute(
                "SELECT time, tid, side, twap, coin, px, sz, start_pos, dir, closed_pnl, fee FROM fills "
                "WHERE wallet = ? ORDER BY time, tid, side, twap", (wid,)).fetchall()

    def count(self, wid: Optional[int] = None) -> int:
        with self.lock:
            if wid is None:
                return self.db.execute("SELECT COALESCE(SUM(n), 0) FROM wallets").fetchone()[0]
            return self.db.execute("SELECT COUNT(*) FROM fills WHERE wallet = ?", (wid,)).fetchone()[0]

    def trim(self, wid: int, keep: int) -> Tuple[int, Optional[int]]:
        """Keep the newest ``keep`` fills (and any sharing the oldest kept millisecond).
        Returns (deleted, time of the oldest kept fill) or (0, None) when under the cap."""
        with self.lock:
            row = self.db.execute("SELECT time FROM fills WHERE wallet = ? ORDER BY time DESC LIMIT 1 OFFSET ?",
                                  (wid, keep - 1)).fetchone()
            if row is None:
                return 0, None
            cur = self.db.execute("DELETE FROM fills WHERE wallet = ? AND time < ?", (wid, row[0]))
            self.db.commit()
            return cur.rowcount, row[0]

    def prune(self, wid: int, cutoff_ms: int) -> int:
        with self.lock:
            cur = self.db.execute("DELETE FROM fills WHERE wallet = ? AND time < ?", (wid, cutoff_ms))
            self.db.commit()
            return cur.rowcount

    def drop(self, wid: int) -> int:
        with self.lock:
            cur = self.db.execute("DELETE FROM fills WHERE wallet = ?", (wid,))
            self.db.execute("DELETE FROM wallets WHERE id = ?", (wid,))
            self.db.commit()
            return cur.rowcount

    def compact(self) -> None:
        with self.lock:
            self.db.execute("PRAGMA incremental_vacuum")
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def size_bytes(self) -> int:
        return sum(os.path.getsize(p) for p in (self.path, self.path + "-wal") if os.path.exists(p))


_store: Optional[Store] = None
_meta: Dict[str, dict] = {}          # address -> wallets row (kept in step with the table)


def store() -> Store:
    global _store, _meta
    if _store is None:
        _store = Store()
        _meta = _store.wallets()
    return _store


def use_store(s: Optional[Store]) -> None:
    """Tests: point the module at another store (None: reopen the default one on next use)."""
    global _store, _meta
    _store = s
    _meta = s.wallets() if s is not None else {}
    _load_cache.clear()
    _rev.clear()


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

class LiveLimiter:
    """At most ``per_min`` live reads in any 60 seconds, across all users."""

    def __init__(self, per_min: int, clock: Callable[[], float] = time.monotonic):
        self.per_min, self.clock = per_min, clock
        self.hits: Deque[float] = collections.deque()
        self.refused = 0

    def try_acquire(self) -> Tuple[bool, float]:
        now = self.clock()
        while self.hits and now - self.hits[0] >= 60:
            self.hits.popleft()
        if len(self.hits) >= self.per_min:
            self.refused += 1
            return False, 60 - (now - self.hits[0]) if self.hits else 60.0
        self.hits.append(now)
        return True, 0.0

    def used(self) -> int:
        now = self.clock()
        return sum(1 for t in self.hits if now - t < 60)


def _buckets():
    from cohorts.sweeper import TokenBucket
    return (TokenBucket(WEIGHT_PER_MIN, capacity=WEIGHT_PER_MIN),
            TokenBucket(BACKFILL_WEIGHT_PER_MIN, capacity=BACKFILL_WEIGHT_PER_MIN))


_bucket, _backfill_bucket = _buckets()
live_limiter = LiveLimiter(LIVE_LOADS_PER_MIN)
_weight_log: Deque[Tuple[float, int, bool]] = collections.deque()    # (t, weight, backfill), last hour
_stats = {"syncs": collections.Counter(), "errors": 0, "last_error": None, "new_fills": 0,
          "backfill_weight": 0, "backfilled_now": 0}


def _spent(weight: int, backfill: bool) -> None:
    now = time.time()
    _weight_log.append((now, weight, backfill))
    while _weight_log and now - _weight_log[0][0] > 3600:
        _weight_log.popleft()
    if backfill:
        _stats["backfill_weight"] += weight


async def _http(session: aiohttp.ClientSession, body: dict):
    async with session.post(INFO_URL, json=body) as resp:
        if resp.status == 429:
            raise RateLimited()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return await resp.json(content_type=None)


class RateLimited(RuntimeError):
    pass


async def _post(session, body: dict, backfill: bool) -> list:
    buckets = (_bucket, _backfill_bucket) if backfill else (_bucket,)
    for b in buckets:
        await b.take(CALL_WEIGHT)
    hl_calls.record(body["type"])
    try:
        data = await _http(session, body)
    except RateLimited:
        for b in buckets:
            b.penalize()
        _spent(CALL_WEIGHT, backfill)
        raise
    data = data if isinstance(data, list) else []
    extra = len(data) // 20
    if extra:
        for b in buckets:
            await b.take(extra)
        hl_calls.record_weight(body["type"], extra)
    _spent(CALL_WEIGHT + extra, backfill)
    return data


# ---------------------------------------------------------------------------
# Reading a wallet
# ---------------------------------------------------------------------------

_rev: Dict[str, int] = {}             # address -> bumped whenever its stored fills change


def _bump(address: str) -> None:
    _rev[address] = _rev.get(address, 0) + 1
    _load_cache.pop(address, None)


async def _pages(session, body: dict, start_ms: int, backfill: bool, unwrap: bool,
                 on_page: Callable[[list], "asyncio.Future"]) -> Tuple[int, Optional[int], Optional[int], bool]:
    """Read forward from ``start_ms`` page by page. Returns (fills read, earliest time, latest time,
    finished: False when MAX_PAGES ran out before a short page)."""
    total, first, last = 0, None, None
    for _ in range(MAX_PAGES):
        page = await _post(session, {**body, "startTime": int(start_ms)}, backfill)
        fs = [x.get("fill", x) for x in page] if unwrap else page
        fs = [f for f in fs if isinstance(f, dict) and "time" in f]
        await on_page(fs)
        total += len(fs)
        if fs:
            lo, hi = min(f["time"] for f in fs), max(f["time"] for f in fs)
            first = lo if first is None else min(first, lo)
            last = hi if last is None else max(last, hi)
        if len(page) < PAGE or not fs:
            return total, first, last, True
        start_ms = hi if hi > start_ms else start_ms + 1
    return total, first, last, False


async def sync(session, address: str, reason: str) -> int:
    """Read the wallet's new fills (all of the retention window on its first read). Returns the
    number of new fills stored."""
    st = store()
    address = address.lower()
    w = _meta.get(address) or await asyncio.to_thread(st.wallet, address)
    wid = w["id"]
    backfill = w["backfilled_at"] is None
    now = time.time()
    now_ms = int(now * 1000)
    since_ms = int((now - RETENTION_DAYS * 86400) * 1000)
    added = 0
    covered = w["covered_from"]

    async def store_page(fs, twap):
        nonlocal added
        rows = [row_of(f, twap) for f in fs if is_perp_fill(f)]
        if rows:
            added += await asyncio.to_thread(st.insert, wid, rows)

    # Regular fills
    start = max(since_ms, (w["cursor_ms"] or since_ms) - OVERLAP_MS)
    n, first, last, done = await _pages(session, {"type": "userFillsByTime", "user": address, "aggregateByTime": True},
                                        start, backfill, False, lambda fs: store_page(fs, False))
    cursor = max(w["cursor_ms"] or 0, last or 0) if not done else max(w["cursor_ms"] or 0, last or 0, now_ms - 60_000)
    if backfill:
        covered = since_ms / 1000
        if n >= HL_RECENT_CAP * 0.95 and first:        # older fills than the latest 10,000 are not served
            covered = first / 1000
    # Timed-order slices: on the first read, on a change or view, or when the wallet has used them
    twap_cursor, twap_seen = w["twap_cursor_ms"], w["twap_seen"]
    if backfill or reason != "sweep" or twap_seen:
        tstart = twap_cursor
        if tstart is None:
            latest = await _post(session, {"type": "userTwapSliceFills", "user": address}, backfill)
            fs = [x.get("fill", x) for x in latest if isinstance(x, dict)]
            fs = [f for f in fs if isinstance(f, dict) and "time" in f and f["time"] >= since_ms]
            if len(latest) < PAGE:
                await store_page(fs, True)
                twap_seen = twap_seen or bool(fs)
                twap_cursor = max([f["time"] for f in fs] + [now_ms - 60_000])
            else:
                # A heavy timed-order user: read forward from where the newest MAX_FILLS_PER_WALLET begin.
                ts = [f["time"] for f in fs] or [now_ms]
                span = max(ts) - min(ts)
                tstart = max(since_ms, max(ts) - span * max(1, MAX_FILLS_PER_WALLET // PAGE))
                covered = max(covered or 0, tstart / 1000)
                twap_seen = True
        if tstart is not None:
            tn, _, tlast, tdone = await _pages(session, {"type": "userTwapSliceFillsByTime", "user": address},
                                               max(since_ms, tstart - OVERLAP_MS), backfill, True,
                                               lambda fs: store_page(fs, True))
            twap_seen = twap_seen or tn > 0
            twap_cursor = max(tstart, tlast or 0, (now_ms - 60_000) if tdone else 0)
    trimmed, oldest = await asyncio.to_thread(st.trim, wid, MAX_FILLS_PER_WALLET)
    if oldest is not None and trimmed:
        covered = max(covered or 0, oldest / 1000)
    count = await asyncio.to_thread(st.count, wid)
    fields = {"cursor_ms": cursor, "twap_cursor_ms": twap_cursor, "synced_at": now, "n": count,
              "twap_seen": int(bool(twap_seen)), "covered_from": covered, "off_roster_at": None}
    if backfill and done:
        fields["backfilled_at"] = now
        _stats["backfilled_now"] += 1
    await asyncio.to_thread(st.update, wid, **fields)
    w = dict(w, **fields)
    _meta[address] = w
    if added or trimmed or backfill:
        _bump(address)
    _stats["syncs"][reason] += 1
    _stats["new_fills"] += added
    return added


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

_dirty: Dict[str, float] = {}                 # address -> when the poller saw its positions change
_view_requests: "collections.OrderedDict[str, float]" = collections.OrderedDict()
_priority: "collections.OrderedDict[str, float]" = collections.OrderedDict()   # backfill these first
_retry_at: Dict[str, Tuple[float, int]] = {}  # address -> (not before, failures in a row)
_waiters: Dict[str, List[asyncio.Future]] = {}
_wake: Optional[asyncio.Event] = None
_task: Optional[asyncio.Task] = None


def _roster() -> List[str]:
    try:
        import hl_intelligence as hl
        return [w.address for w in hl._roster]
    except Exception:
        return []


def _on_roster(address: str) -> bool:
    try:
        import hl_intelligence as hl
        idx = getattr(hl, "_roster_index", None)
        if idx and getattr(hl, "_roster_index_of", None) == id(hl._roster):
            return address in idx
        return any(w.address == address for w in hl._roster)
    except Exception:
        return False


def _kick() -> None:
    if _wake is not None:
        _wake.set()


def mark_changed(address: str) -> None:
    """The position poller saw this tracked wallet's positions change: read its new fills soon."""
    if enabled():
        _dirty[address.lower()] = time.time()
        _kick()


def prioritise(addresses: Iterable[str]) -> None:
    """Backfill these wallets before the others (the leaderboard page on screen, a profile view)."""
    for a in addresses:
        a = a.lower()
        if a not in _priority and not ready(a):
            _priority[a] = time.time()
    while len(_priority) > 700:
        _priority.popitem(last=False)
    _kick()


def _sweep_due(w: dict) -> float:
    jitter = (zlib.crc32(w["address"].encode()) % 2001 - 1000) / 10000       # +-10%, fixed per wallet
    return (w["synced_at"] or 0) + SWEEP_S * (1 + jitter)


def _quiet(now: float) -> bool:
    try:
        from cohorts.sweeper import quiet_until
        return quiet_until(now) is not None
    except Exception:
        return False


def next_job(now: float, roster: List[str]) -> Optional[Tuple[str, str]]:
    """(address, reason) of the next read, or None. Order: views, position changes, the sweep, then
    the backfill (prioritised wallets first, then roster order; not in the post-close quiet window)."""
    on = set(roster)

    def ok(a):
        r = _retry_at.get(a)
        return a in on and (r is None or r[0] <= now)

    def recent(a, s):
        w = _meta.get(a)
        return bool(w and w["synced_at"] and now - w["synced_at"] < s)

    for a in list(_view_requests):
        if not ok(a) or recent(a, MIN_RESYNC_S):
            _view_requests.pop(a, None)
            _resolve(a)
            continue
        return a, "view" if ready(a) else "backfill"
    for a, t in sorted(_dirty.items(), key=lambda kv: kv[1]):
        if a not in on:
            _dirty.pop(a, None)
            continue
        w = _meta.get(a)
        if w and w["backfilled_at"] and ok(a):
            if w["synced_at"] and w["synced_at"] >= t:
                _dirty.pop(a, None)
                continue
            return a, "change"
    due = [(_sweep_due(_meta[a]), a) for a in roster if a in _meta and _meta[a]["backfilled_at"] and ok(a)]
    due = [x for x in due if x[0] <= now]
    if due:
        return min(due)[1], "sweep"
    if _quiet(now):
        return None
    pending = [a for a in _priority if ok(a) and not ready(a)] + \
              [a for a in roster if ok(a) and not (_meta.get(a) or {}).get("backfilled_at")]
    return (pending[0], "backfill") if pending else None


def _resolve(address: str) -> None:
    for f in _waiters.pop(address, []):
        if not f.done():
            f.set_result(None)


async def refresh(address: str, wait: float = 0.0) -> None:
    """A view found the stored fills behind the wallet's live positions: read its new fills
    (at most once per VIEW_REFRESH_S per wallet), waiting up to ``wait`` seconds."""
    address = address.lower()
    w = _meta.get(address)
    if not enabled() or not _on_roster(address) or (w and w["synced_at"] and time.time() - w["synced_at"] < VIEW_REFRESH_S):
        return
    _view_requests[address] = time.time()
    _view_requests.move_to_end(address)
    while len(_view_requests) > MAX_VIEW_REQUESTS:
        old, _ = _view_requests.popitem(last=False)
        _resolve(old)
    _kick()
    if wait > 0 and _task is not None and not _task.done():
        fut = asyncio.get_running_loop().create_future()
        _waiters.setdefault(address, []).append(fut)
        try:
            await asyncio.wait_for(asyncio.shield(fut), wait)
        except asyncio.TimeoutError:
            pass


async def _run_one(session, address: str, reason: str) -> None:
    try:
        await sync(session, address, reason)
        _retry_at.pop(address, None)
        if reason in ("change", "view", "backfill"):
            _dirty.pop(address, None)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        fails = _retry_at.get(address, (0, 0))[1] + 1
        _retry_at[address] = (time.time() + min(3600, 60 * 2 ** min(fails, 6)), fails)
        _stats["errors"] += 1
        _stats["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
        logger.warning("Fills store: read of %s failed (%s): %s", address[:10], reason, exc)
    finally:
        _view_requests.pop(address, None)
        _priority.pop(address, None)
        _resolve(address)


def maintain(roster: List[str], now: Optional[float] = None) -> dict:
    """Retention (RETENTION_DAYS), wallets off the roster for OFF_ROSTER_DAYS, then give freed
    pages back to the disk."""
    out, changed, fresh = _maintain_db(roster, now)
    _apply_maintenance(changed, fresh)
    return out


def _apply_maintenance(changed: List[str], fresh: Dict[str, dict]) -> None:
    """On the event loop: the in-memory view follows the table."""
    for a in changed:
        _bump(a)
    _meta.clear()
    _meta.update(fresh)


def _maintain_db(roster: List[str], now: Optional[float] = None) -> Tuple[dict, List[str], Dict[str, dict]]:
    """The database part of maintain (blocking: run in a thread). Returns (summary, wallets whose
    fills changed, the wallets table)."""
    now = time.time() if now is None else now
    st = store()
    on = set(roster)
    cutoff_ms = int((now - RETENTION_DAYS * 86400) * 1000)
    out = {"pruned": 0, "dropped_wallets": 0}
    changed: List[str] = []
    for address, w in list(st.wallets().items()):
        if address not in on and roster:
            if w["off_roster_at"] is None:
                st.update(w["id"], off_roster_at=now)
            elif now - w["off_roster_at"] > OFF_ROSTER_DAYS * 86400:
                st.drop(w["id"])
                out["dropped_wallets"] += 1
                changed.append(address)
                continue
        elif w["off_roster_at"] is not None:
            st.update(w["id"], off_roster_at=None)
        gone = st.prune(w["id"], cutoff_ms)
        if gone:
            out["pruned"] += gone
            st.update(w["id"], n=st.count(w["id"]), covered_from=max(w["covered_from"] or 0, cutoff_ms / 1000))
            changed.append(address)
    st.compact()
    out["db_mb"] = round(st.size_bytes() / 1e6, 1)
    logger.info("Fills store maintenance: %s", out)
    return out, changed, st.wallets()


async def run_forever() -> None:
    """Background reader (started from main at startup when FILLS_STORE_ENABLED is not 0)."""
    global _wake, _task, _meta
    _task = asyncio.current_task()
    _wake = asyncio.Event()
    await asyncio.sleep(START_DELAY_S)
    st = await asyncio.to_thread(store)
    _meta = await asyncio.to_thread(st.wallets)
    last_maint = time.time() - MAINTAIN_EVERY_S + 1800          # first maintenance ~30 min after start
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                from feature_flags import get_flag
                if not get_flag("hyperlens_enabled"):
                    await asyncio.sleep(60)
                    continue
                roster = _roster()
                now = time.time()
                if roster and now - last_maint > MAINTAIN_EVERY_S:
                    last_maint = now
                    _apply_maintenance(*(await asyncio.to_thread(_maintain_db, roster, now))[1:])
                job = next_job(now, roster) if roster else None
                if job is None:
                    _wake.clear()
                    try:
                        await asyncio.wait_for(_wake.wait(), 30)
                    except asyncio.TimeoutError:
                        pass
                    continue
                await _run_one(session, *job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Fills store loop error: %s", exc)
                await asyncio.sleep(10)


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------

_load_cache: "collections.OrderedDict[str, tuple]" = collections.OrderedDict()   # address -> (rev, result)


def ready(address: str) -> bool:
    """Served from the store: enabled, on the roster, and its backfill is complete."""
    if not enabled() or _store is None:
        return False
    w = _meta.get(address.lower())
    return bool(w and w["backfilled_at"]) and _on_roster(address.lower())


def stored_fills(address: str) -> Optional[dict]:
    """The wallet's stored fills, oldest first, in the live path's shape ({fills, covered_from}),
    or None when the wallet is not served from the store."""
    address = address.lower()
    if not ready(address):
        return None
    rev = _rev.get(address, 0)
    hit = _load_cache.get(address)
    if hit and hit[0] == rev:
        _load_cache.move_to_end(address)
        return hit[1]
    w = _meta[address]
    fills = [fill_of(r) for r in store().load(w["id"])]
    res = {"fills": fills, "covered_from": w["covered_from"], "synced_at": w["synced_at"], "stored": True}
    _load_cache[address] = (rev, res)
    while len(_load_cache) > LOAD_CACHE_WALLETS:
        _load_cache.popitem(last=False)
    return res


async def load(address: str) -> Optional[dict]:
    """stored_fills off the event loop."""
    if not ready(address):
        return None
    hit = _load_cache.get(address.lower())
    if hit and hit[0] == _rev.get(address.lower(), 0):
        return hit[1]
    return await asyncio.to_thread(stored_fills, address)


def status() -> dict:
    """For /api/hyperlens/status: backfill progress, the store's size and its Hyperliquid weight."""
    roster = _roster()
    on = set(roster)
    done = sum(1 for a in roster if (_meta.get(a) or {}).get("backfilled_at"))
    pending = len(roster) - done
    now = time.time()
    w5 = sum(w for t, w, _ in _weight_log if now - t <= 300) / 5
    w60 = sum(w for t, w, _ in _weight_log if now - t <= 3600) / 60
    per_wallet = (_stats["backfill_weight"] / _stats["backfilled_now"]) if _stats["backfilled_now"] else None
    eta = round(pending * per_wallet / BACKFILL_WEIGHT_PER_MIN * 60) if per_wallet and pending else (0 if not pending else None)
    size = None
    if _store is not None:
        try:
            size = round(_store.size_bytes() / 1e6, 1)
        except OSError:
            pass
    return {
        "enabled": enabled(),
        "wallets": len(roster), "backfilled": done, "backfill_pending": pending, "backfill_eta_s": eta,
        "stored_wallets": len(_meta), "stored_on_roster": sum(1 for a in _meta if a in on),
        "fills": sum((w.get("n") or 0) for w in _meta.values()), "db_mb": size,
        "retention_days": RETENTION_DAYS, "max_fills_per_wallet": MAX_FILLS_PER_WALLET,
        "weight_budget_per_min": WEIGHT_PER_MIN, "backfill_budget_per_min": BACKFILL_WEIGHT_PER_MIN,
        "weight_per_min_5m": round(w5, 1), "weight_per_min_60m": round(w60, 1),
        "backfill_weight_per_wallet": round(per_wallet) if per_wallet else None,
        "queued": {"changes": len(_dirty), "views": len(_view_requests), "priority": len(_priority)},
        "reads_since_start": dict(_stats["syncs"]), "new_fills_since_start": _stats["new_fills"],
        "errors": _stats["errors"], "last_error": _stats["last_error"],
        "live_loads": {"per_min_limit": LIVE_LOADS_PER_MIN, "last_min": live_limiter.used(),
                       "refused_since_start": live_limiter.refused},
    }
