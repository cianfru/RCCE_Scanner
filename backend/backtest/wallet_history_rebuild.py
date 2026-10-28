"""
Rebuild daily long/short counts of Hyperliquid smart money and whales from public data, for the market history page
(wallet_history.py; method in docs/reviews/wallet-history.md). Context, not a signal.

    python -m backtest.wallet_history_rebuild census --share 0.10 --whale-share 0.35     (from backend/)
    python -m backtest.wallet_history_rebuild fills  --share 0.10 --whale-share 0.35
    python -m backtest.wallet_history_rebuild candles
    python -m backtest.wallet_history_rebuild export --share 0.10 --whale-share 0.35     (writes seeds/wallet_history_seed.json)
    python -m backtest.wallet_history_rebuild status

Groups, as the live cohort sweep (cohorts.assign) defines them, but as each wallet stood on each day:
smart = $100K+ all-time PnL and $10K+ perp equity; whales = $1M+ perp equity. Steps:

1. Candidates: today's leaderboard without market makers (monthly volume over 100x the account value, as the live
   registry), with $100K+ all-time PnL, a $1M+ account or $100M+ all-time volume (wallets that were large once).
2. Sample: a fixed hash of the address picks `share` of them, and `whale_share` of the likely whales (a $1M+
   account or $1B+ all-time volume). Every count is weighted by 1/(the wallet's chance of being picked).
3. Census: Hyperliquid's `portfolio` gives each wallet's perp equity (weekly, finer lately) and all-time PnL
   (weekly); interpolated at each 00:00 UTC close they say which group it was in that day.
4. Fills: for wallets in a group on some day, the current positions, fills and timed-order slices since START.
   Each fill carries Hyperliquid's own record of the position just before it (startPosition), so a position at a
   close is the one right after the last fill before it or right before the next (the current position when none
   follows); where a fill was not read and the two differ, the nearer in time. Very active wallets are read for
   their newest pages only; days before their first fill read count them as uncovered (left out, the others
   scaled up).
5. Daily closes per coin (candleSnapshot 1d) value each position; a wallet is long or short by the sign of its
   net dollar position, wallets with more than 25 positions are left out (cohorts.assign.MAX_POSITIONS).

Rate: Hyperliquid allows 1,200 weight a minute per IP; this uses --rate (default 1,050). A sample of 10% / 35%
took about six hours. The cache (--db) keeps every answer, so a run cut short continues where it stopped.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import datetime
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DAY = 86_400_000
START = int(datetime.datetime(2025, 9, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
URL = "https://api.hyperliquid.xyz/info"
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "wallet_history_cache" / "rebuild.db"
SEED = Path(__file__).resolve().parent.parent / "seeds" / "wallet_history_seed.json"

MM_VLM_RATIO = 100
SMART_PNL, SMART_EQ, WHALE_EQ = 100_000, 10_000, 1_000_000
CAND_PNL, CAND_AV, CAND_VLM = 100_000, 1_000_000, 100_000_000
WHALE_LIKELY_AV, WHALE_LIKELY_VLM = 1_000_000, 1_000_000_000
MAX_REG_PAGES, MAX_TWAP_PAGES = 3, 2
MAX_POSITIONS = 25
FLAT_BELOW = 1e-6           # float leftovers of a full close (the API's sizes carry noise), as research/traders_turn.py
PAGE = 2000
COLUMNS = ["day", "wallets", "positioned", "long", "short", "long_usd", "short_usd", "sampled"]


# ---------------------------------------------------------------------------
# Hyperliquid client: a weight bucket under the per-IP limit, retries on 429 and 5xx
# ---------------------------------------------------------------------------

WEIGHT = {"clearinghouseState": 2}
ITEM_EXTRA = {"userFills", "userFillsByTime", "candleSnapshot", "userTwapSliceFills", "userTwapSliceFillsByTime"}


class Bucket:
    def __init__(self, per_min: float):
        self.rate, self.cap = per_min / 60.0, per_min / 4
        self.tokens, self.last, self.used = self.cap, time.monotonic(), 0
        self.lock = threading.Lock()

    def take(self, n: float) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.cap, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= n:
                    self.tokens -= n
                    self.used += n
                    return
                wait = (n - self.tokens) / self.rate
            time.sleep(min(wait, 5))

    def penalize(self, seconds: float) -> None:
        with self.lock:
            self.tokens = -self.rate * seconds


BUCKET = Bucket(1050)


def info(body: dict, retries: int = 6):
    kind = body["type"]
    BUCKET.take(WEIGHT.get(kind, 20))
    data = json.dumps(body).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
            out = json.loads(urllib.request.urlopen(req, timeout=90).read())
            if kind in ITEM_EXTRA and isinstance(out, list) and len(out) >= 20:     # +1 weight per 20 items
                BUCKET.take(len(out) // (60 if kind == "candleSnapshot" else 20))
            return out
        except urllib.error.HTTPError as e:
            if e.code == 429:
                BUCKET.penalize(20 * (attempt + 1))
                time.sleep(5 * (attempt + 1))
            elif e.code >= 500:
                time.sleep(3 * (attempt + 1))
            else:
                raise
        except Exception:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{kind} failed after {retries} tries")


def fills_since(user: str, start_ms: int, end_ms: int, kind: str = "userFillsByTime", max_pages: int = 50):
    """Fills from start_ms, oldest first, 2,000 a page. Each page after the first starts at the previous page's
    latest millisecond (duplicates dropped), so fills sharing a millisecond at a page edge are all kept."""
    out, cur, pages, seen = [], start_ms, 0, set()
    while True:
        body = {"type": kind, "user": user, "startTime": cur, "endTime": end_ms}
        if kind == "userFillsByTime":
            body["aggregateByTime"] = True
        page = info(body) or []
        pages += 1
        fs = [x.get("fill", x) for x in page if isinstance(x, dict)]         # timed-order slices come wrapped
        fs = [f for f in fs if "time" in f]
        for f in fs:
            k = (f["time"], f.get("tid"), f.get("oid"), f["coin"], f["side"], f["sz"], f.get("startPosition"))
            if k not in seen:
                seen.add(k)
                out.append(f)
        if len(page) < PAGE or not fs or pages >= max_pages:
            break
        hi = max(f["time"] for f in fs)
        cur = hi if hi > cur else cur + 1
    out.sort(key=lambda f: (f["time"], f.get("tid") or 0))
    return out


def merge(*lists):
    seen, out = set(), []
    for fs in lists:
        for f in fs:
            k = (f["time"], f.get("tid"), f.get("oid"), f["coin"], f["side"], f["sz"], f.get("startPosition"))
            if k not in seen:
                seen.add(k)
                out.append(f)
    out.sort(key=lambda f: (f["time"], f.get("tid") or 0))
    return out


def read_kind(addr: str, kind: str, latest_kind: str, now: int):
    """(fills since START, coverage start or None when complete, capped). One page from START when it is not
    full; else the latest 2,000 too, and when the gap between them takes more than the cap in pages, only the
    newest window (coverage then starts at its first fill)."""
    first = fills_since(addr, START, now, kind, max_pages=1)
    if len(first) < PAGE:
        return first, None, 0
    body = {"type": latest_kind, "user": addr}
    if kind == "userFillsByTime":
        body["aggregateByTime"] = True
    latest = [x.get("fill", x) for x in (info(body) or []) if isinstance(x, dict)]
    latest = [f for f in latest if "time" in f]
    if not latest:
        return first, None, 0
    lo, hi = min(f["time"] for f in latest), max(f["time"] for f in latest)
    first_end = max(f["time"] for f in first)
    if first_end >= lo:
        return merge(first, latest), None, 0
    span = max(1, hi - lo)
    cap = MAX_REG_PAGES if kind == "userFillsByTime" else MAX_TWAP_PAGES
    if (lo - first_end) / span <= cap:
        return merge(first, fills_since(addr, first_end, lo, kind, cap + 1), latest), None, 0
    got = merge(fills_since(addr, max(first_end, int(lo - span * cap)), lo, kind, cap + 1), latest)
    return got, (got[0]["time"] if got else lo), 1


def is_perp(f: dict) -> bool:
    """Native perpetuals (not spot, HIP-3 dexes or outcome tokens), settlements included."""
    c, d = str(f.get("coin") or ""), str(f.get("dir") or "")
    return bool(c) and c[0] not in "@#" and "/" not in c and ":" not in c and ("Long" in d or "Short" in d or d == "Settlement")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_lock = threading.Lock()


def db(path) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
    c = sqlite3.connect(str(path), timeout=60, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=OFF")          # a cache: speed over durability
    c.executescript("""
    CREATE TABLE IF NOT EXISTS wallets (addr TEXT PRIMARY KEY, skey INTEGER, lb_av REAL, lb_pnl REAL, lb_vlm REAL,
        census TEXT, ever_smart INTEGER, ever_whale INTEGER, fills_done INTEGER DEFAULT 0, err TEXT);
    CREATE TABLE IF NOT EXISTS fills (addr TEXT PRIMARY KEY, current TEXT, data TEXT, coverage_start INTEGER,
        n_reg INTEGER, n_twap INTEGER, reg_capped INTEGER, twap_capped INTEGER, weight INTEGER);
    CREATE TABLE IF NOT EXISTS candles (coin TEXT PRIMARY KEY, data TEXT);
    """)
    return c


def skey(addr: str) -> int:
    return int(hashlib.sha256(addr.lower().encode()).hexdigest()[:8], 16) % 10_000


def whale_likely(av: float, vlm: float) -> bool:
    return av >= WHALE_LIKELY_AV or vlm >= WHALE_LIKELY_VLM


def chance(av: float, vlm: float, share: float, whale_share: float) -> float:
    """A wallet's chance of being in the sample."""
    return max(share, whale_share) if whale_likely(av, vlm) else share


def in_sample(key: int, av: float, vlm: float, share: float, whale_share: float) -> bool:
    return key < int(chance(av, vlm, share, whale_share) * 10_000)


def sample_order(key: int, av: float, vlm: float, share: float, whale_share: float) -> float:
    """Work order: both strata advance together, so any prefix of the work is a proportional sample."""
    return key / max(1.0, chance(av, vlm, share, whale_share) * 10_000)


def load_candidates(conn, leaderboard_path=None) -> int:
    raw = json.load(open(leaderboard_path)) if leaderboard_path else json.loads(urllib.request.urlopen(LEADERBOARD, timeout=120).read())
    out = []
    for r in raw["leaderboardRows"]:
        w = {k: v for k, v in r["windowPerformances"]}
        av = float(r["accountValue"] or 0)
        if av > 0 and float(w["month"]["vlm"] or 0) / av > MM_VLM_RATIO:
            continue
        pnl, vlm = float(w["allTime"]["pnl"] or 0), float(w["allTime"]["vlm"] or 0)
        if pnl >= CAND_PNL or av >= CAND_AV or vlm >= CAND_VLM:
            a = r["ethAddress"].lower()
            out.append((a, skey(a), av, pnl, vlm))
    with _lock:
        conn.executemany("INSERT OR IGNORE INTO wallets (addr, skey, lb_av, lb_pnl, lb_vlm) VALUES (?,?,?,?,?)", out)
        conn.commit()
    return len(out)


def sampled(conn, share, whale_share, where="1=1"):
    rows = conn.execute(f"SELECT addr, skey, lb_av, lb_vlm FROM wallets WHERE {where}").fetchall()
    rows = [r for r in rows if in_sample(r[1], r[2], r[3], share, whale_share)]
    rows.sort(key=lambda r: sample_order(r[1], r[2], r[3], share, whale_share))
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

def interp(pts, t):
    """Linear between points, flat beyond the ends; None without points."""
    if not pts:
        return None
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    i = bisect.bisect_right([p[0] for p in pts], t)
    (t0, v0), (t1, v1) = pts[i - 1], pts[i]
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v1


def day_ends(end_ms=None):
    """(day, close time) for every closed day from START: day d closes at 00:00 UTC of d + 1."""
    end_ms = end_ms or int(time.time() * 1000)
    return [(d, (d + 1) * DAY) for d in range(START // DAY, end_ms // DAY) if (d + 1) * DAY <= end_ms]


def membership(rec: dict, t: int):
    """(smart, whale) at time t from the wallet's own history; before its first point it is in neither."""
    eq_pts, pnl_pts = rec["eq"], rec["pnl"]
    if not eq_pts or t < eq_pts[0][0] - 7 * DAY:
        return False, False
    eq = interp(eq_pts, t) or 0.0
    pnl = interp(pnl_pts, t)
    return (pnl is not None and pnl >= SMART_PNL and eq >= SMART_EQ), eq >= WHALE_EQ


def classify_any(rec: dict):
    smart = whale = False
    for _, t in day_ends():
        s, w = membership(rec, t)
        smart, whale = smart or s, whale or w
        if smart and whale:
            break
    return smart, whale


def series(pf: dict, keys, field):
    pts = {}
    for k in keys:
        for t, v in (pf.get(k) or {}).get(field, []) or []:
            pts[int(t)] = float(v)
    return sorted(pts.items())


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def census_one(conn, addr):
    try:
        pf = dict(info({"type": "portfolio", "user": addr}))
        eq = series(pf, ("perpAllTime", "perpMonth", "perpWeek", "perpDay"), "accountValueHistory")
        pnl = series(pf, ("allTime",), "pnlHistory")
        keep = START - 21 * DAY
        eq = [p for p in eq if p[0] >= keep] or eq[-1:]
        pnl = [p for p in pnl if p[0] < keep][-1:] + [p for p in pnl if p[0] >= keep]
        rec = {"eq": [[t, round(v, 2)] for t, v in eq], "pnl": [[t, round(v, 2)] for t, v in pnl]}
        smart, whale = classify_any(rec)
        with _lock:
            conn.execute("UPDATE wallets SET census=?, ever_smart=?, ever_whale=?, err=NULL WHERE addr=?",
                         (json.dumps(rec, separators=(",", ":")), int(smart), int(whale), addr))
            conn.commit()
    except Exception as e:
        with _lock:
            conn.execute("UPDATE wallets SET err=? WHERE addr=?", (f"census: {e}", addr))
            conn.commit()


def fills_one(conn, addr):
    w0 = BUCKET.used
    try:
        st = info({"type": "clearinghouseState", "user": addr})
        current = {}
        for ap in st.get("assetPositions", []) or []:
            p = ap.get("position", {}) or {}
            szi = float(p.get("szi", 0) or 0)
            if szi:
                current[p["coin"]] = szi
        now = int(time.time() * 1000)
        reg, cov_r, reg_capped = read_kind(addr, "userFillsByTime", "userFills", now)
        tw, cov_t, twap_capped = read_kind(addr, "userTwapSliceFillsByTime", "userTwapSliceFills", now)
        coverage = max([START] + [c for c in (cov_r, cov_t) if c])
        data = {}
        for f, twap in [(x, 0) for x in reg] + [(x, 1) for x in tw]:
            if is_perp(f):
                sz = float(f["sz"]) * (1 if f["side"] == "B" else -1)
                data.setdefault(f["coin"], []).append([int(f["time"]), int(f.get("tid") or 0), float(f["startPosition"]),
                                                       sz, float(f["px"]), twap])
        for c in data:
            data[c].sort(key=lambda r: (r[0], r[1]))
        with _lock:
            conn.execute("INSERT OR REPLACE INTO fills VALUES (?,?,?,?,?,?,?,?,?)",
                         (addr, json.dumps(current), json.dumps(data, separators=(",", ":")), coverage,
                          len(reg), len(tw), reg_capped, twap_capped, BUCKET.used - w0))
            conn.execute("UPDATE wallets SET fills_done=1, err=NULL WHERE addr=?", (addr,))
            conn.commit()
    except Exception as e:
        with _lock:
            conn.execute("UPDATE wallets SET err=? WHERE addr=?", (f"fills: {e}", addr))
            conn.commit()


def run_pool(conn, todo, fn, workers, stop_at):
    with ThreadPoolExecutor(workers) as ex:
        futs = []
        for a in todo:
            if time.time() > stop_at:
                break
            futs.append(ex.submit(fn, conn, a))
            while sum(1 for f in futs if not f.done()) > workers * 2:
                time.sleep(0.1)
            futs = [f for f in futs if not f.done()]


def candles(conn):
    coins = set()
    for data, cur in conn.execute("SELECT data, current FROM fills"):
        coins.update(json.loads(data))
        coins.update(json.loads(cur))
    have = {c for (c,) in conn.execute("SELECT coin FROM candles")}
    now = int(time.time() * 1000)
    for c in sorted(coins - have):
        try:
            rows = info({"type": "candleSnapshot", "req": {"coin": c, "interval": "1d", "startTime": START - 2 * DAY, "endTime": now}})
            data = [[int(r["t"]) // DAY, float(r["c"])] for r in rows or []]
        except Exception as e:
            print("candles failed", c, e, flush=True)
            data = []
        conn.execute("INSERT OR REPLACE INTO candles VALUES (?,?)", (c, json.dumps(data)))
        conn.commit()
    return len(coins)


# ---------------------------------------------------------------------------
# Aggregate and export
# ---------------------------------------------------------------------------

def positions_at(cur: dict, data: dict, ends, now_ms=None):
    """{day: {coin: size}} at each close. Two records of Hyperliquid's frame each close: the position right after
    the last fill before it (startPosition + size) and right before the next one (its startPosition; the current
    position, read at now_ms, when no fill follows). They agree unless a fill in between was not read; then the
    one nearer in time is taken."""
    now_ms = now_ms or int(time.time() * 1000)
    out = {d: {} for d, _ in ends}
    for c in set(cur) | set(data):
        rows = data.get(c, [])
        times = [r[0] for r in rows]
        for d, t in ends:
            i = bisect.bisect_right(times, t)
            after, t_after = (rows[i][2], rows[i][0]) if i < len(rows) else (cur.get(c, 0.0), now_ms)
            sz = after
            if i > 0:
                before, t_before = rows[i - 1][2] + rows[i - 1][3], rows[i - 1][0]
                if abs(before - after) > 1e-9 * max(1.0, abs(after)) and t - t_before < t_after - t:
                    sz = before
            if abs(sz) >= FLAT_BELOW:
                out[d][c] = sz
    return out


def price(closes: dict, data: dict, coin: str, d: int, t: int):
    p = closes.get(coin, {}).get(d)
    if p:
        return p
    rows = data.get(coin, [])
    if not rows:
        return None
    i = min(bisect.bisect_right([r[0] for r in rows], t), len(rows) - 1)
    return rows[i][4]                    # a coin without candles (delisted): the nearest fill's price


def aggregate(conn, share, whale_share, end_ms=None):
    """Weighted daily rows per group, plus the raw counts behind them."""
    ends = day_ends(end_ms)
    meta = {a: (k, av, vlm) for a, k, av, vlm in conn.execute("SELECT addr, skey, lb_av, lb_vlm FROM wallets")}
    census = {a: json.loads(c) for a, c in conn.execute("SELECT addr, census FROM wallets WHERE census IS NOT NULL")
              if in_sample(meta[a][0], meta[a][1], meta[a][2], share, whale_share)}
    fills = {a: (json.loads(cur), json.loads(data), cov) for a, cur, data, cov in
             conn.execute("SELECT addr, current, data, coverage_start FROM fills") if a in census}
    closes = {c: {int(d): float(v) for d, v in json.loads(data)} for c, data in conn.execute("SELECT coin, data FROM candles")}
    acc = {g: {d: collections.defaultdict(float) for d, _ in ends} for g in ("smart", "whales")}
    for addr, rec in census.items():
        member = {}
        for d, t in ends:
            s, w = membership(rec, t)
            if s or w:
                member[d] = [g for g, on in (("smart", s), ("whales", w)) if on]
        if not member:
            continue
        weight = 1.0 / chance(meta[addr][1], meta[addr][2], share, whale_share)
        f = fills.get(addr)
        if f is None:                                    # not read yet: counts as uncovered
            for d, gs in member.items():
                for g in gs:
                    acc[g][d]["uncovered_w"] += weight
            continue
        cur, data, cov = f
        pos = positions_at(cur, data, [(d, t) for d, t in ends if d in member and t >= cov], end_ms)
        for d, t in ends:
            gs = member.get(d)
            if not gs:
                continue
            if t < cov:
                for g in gs:
                    acc[g][d]["uncovered_w"] += weight
                continue
            book = pos[d]
            if len(book) > MAX_POSITIONS:
                continue
            long_usd = short_usd = 0.0
            for c, sz in book.items():
                px = price(closes, data, c, d, t)
                if px:
                    long_usd += max(0.0, sz * px)
                    short_usd += max(0.0, -sz * px)
            net = long_usd - short_usd
            for g in gs:
                a = acc[g][d]
                a["n"] += 1
                a["wallets"] += weight
                if book:
                    a["positioned"] += weight
                    a["long"] += weight * (net > 0)
                    a["short"] += weight * (net < 0)
                a["long_usd"] += weight * long_usd
                a["short_usd"] += weight * short_usd
    out = {}
    for g, by_day in acc.items():
        rows = []
        for d, a in sorted(by_day.items()):
            if not a["n"]:
                continue
            scale = (a["wallets"] + a["uncovered_w"]) / a["wallets"]      # uncovered members take the covered shares
            rows.append([d, round(a["wallets"] * scale), round(a["positioned"] * scale), round(a["long"] * scale),
                         round(a["short"] * scale), round(a["long_usd"] * scale), round(a["short_usd"] * scale), int(a["n"])])
        out[g] = rows
    return out, {"censused": len(census), "read": len(fills)}


def export(conn, share, whale_share, path=SEED, end_ms=None):
    groups, counts = aggregate(conn, share, whale_share, end_ms)
    days = [r[0] for rows in groups.values() for r in rows]
    seed = {"version": 1, "built": datetime.date.today().isoformat(), "start_day": min(days), "end_day": max(days),
            "columns": COLUMNS, "sample": {"share": share, "whale_share": whale_share, **counts}, "groups": groups}
    Path(path).write_text(json.dumps(seed, separators=(",", ":")))
    return seed


def status(conn):
    q = lambda s: conn.execute(s).fetchone()[0]
    print("wallets", q("SELECT COUNT(*) FROM wallets"), "| census", q("SELECT COUNT(*) FROM wallets WHERE census IS NOT NULL"),
          "| ever smart", q("SELECT COUNT(*) FROM wallets WHERE ever_smart=1"), "| ever whale", q("SELECT COUNT(*) FROM wallets WHERE ever_whale=1"),
          "| fills", q("SELECT COUNT(*) FROM wallets WHERE fills_done=1"), "| errors", q("SELECT COUNT(*) FROM wallets WHERE err IS NOT NULL"),
          "| fill weight", q("SELECT COALESCE(SUM(weight), 0) FROM fills"), "| capped", q("SELECT COALESCE(SUM(reg_capped), 0) FROM fills"))


def main(argv=None):
    global BUCKET
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["census", "fills", "candles", "export", "status"])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--leaderboard", help="a saved leaderboard JSON instead of downloading it")
    ap.add_argument("--share", type=float, default=0.10)
    ap.add_argument("--whale-share", type=float, default=0.35)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--rate", type=float, default=1050)
    ap.add_argument("--limit-s", type=float, default=7000, help="stop taking new wallets after this many seconds")
    ap.add_argument("--out", default=str(SEED))
    a = ap.parse_args(argv)
    BUCKET = Bucket(a.rate)
    conn = db(a.db)
    stop_at = time.time() + a.limit_s
    if a.step == "census":
        print("candidates", load_candidates(conn, a.leaderboard), flush=True)
        run_pool(conn, sampled(conn, a.share, a.whale_share, "census IS NULL"), census_one, a.workers, stop_at)
    elif a.step == "fills":
        todo = sampled(conn, a.share, a.whale_share, "census IS NOT NULL AND (ever_smart=1 OR ever_whale=1) AND fills_done=0")
        print("to read", len(todo), flush=True)
        run_pool(conn, todo, fills_one, a.workers, stop_at)
    elif a.step == "candles":
        print("coins", candles(conn), flush=True)
    elif a.step == "export":
        seed = export(conn, a.share, a.whale_share, a.out)
        print("seed", a.out, seed["sample"], "days", seed["start_day"], "-", seed["end_day"],
              {g: len(r) for g, r in seed["groups"].items()})
    status(conn)


if __name__ == "__main__":
    sys.exit(main())
