"""
Selection window study (declared in docs/reviews/selection-window-study.md before any result was computed): which
window, 30, 60 or 90 days, picks Hyperliquid wallets whose profits carry into the next 30 days, with the profitable
traders' other rules unchanged.

    python -m backtest.selection_window_study fetch --leaderboard SNAPSHOT.json     (from backend/; resumable)
    python -m backtest.selection_window_study status
    python -m backtest.selection_window_study analyse --out results.json

Data: a saved leaderboard snapshot (addresses, today's account value and volume; its SHA-256 is recorded) and each
sampled wallet's Hyperliquid `portfolio` reply, kept whole (zlib). Every value at a time is the wallet's last point
at or before it (0 before its first point): no value after a date enters its selection. The cache (--db, default
data/selection_window_cache/study.db, gitignored) keeps every answer, so a fetch cut short continues where it stopped.
"""
from __future__ import annotations

import argparse
import bisect
import datetime
import hashlib
import itertools
import json
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

URL = "https://api.hyperliquid.xyz/info"
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "selection_window_cache" / "study.db"

DAY = 86_400
# --- declared rules (docs/reviews/selection-window-study.md) --------------------------------------
WINDOWS = (30, 60, 90)            # selection windows, days; 30 is today's
OUTCOME_D = 30                    # the next 30 days after each date
T0 = int(datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc).timestamp())
N_DATES = 12                      # T0, T0 - 30 d, ... T0 - 330 d (outcome windows do not overlap)
SHARE = 0.50                      # fixed hash sample of the leaderboard
K_FULL = 400                      # list size compared (about today's 431); in the sample, round(K_FULL * share)
CAP_FULL = 600                    # today's cap, for the "rules as they are" arms
MIN_AV, MIN_PERP, MIN_PNL, MIN_BASE, MIN_ROI = 10_000, 5_000, 10_000, 1_000, 0.30
MM_RATIO, MM_MIN_AV = 100, 10_000  # market maker: month volume over 100x today's account, for $10K+ accounts
HIT_PNL = 100                     # a hit: next-30-day PnL of +$100 or more; |PnL| under $100: did not trade
BIG_VLM = 10_000_000              # leaderboard rows listed by volume ($10M+), not only by account ($100K+)
ROI_CLIP = 1.0                    # next-30-day ROI clipped to +-100% for the magnitude check
BAR_PP, BAR_DATES, BAR_P, MIN_SIDE = 3.0, 10, 0.025, 3
SUB_VLM_SHARE = 0.9               # portfolio volume under 90% of the leaderboard's: the row adds sub-accounts
STALE_STRATA = ((0, 2), (2, 7), (7, 10_000))   # days since the last point at t (context)
WEIGHT = 20                       # portfolio request weight
MAX_RUNS = 3                      # a wallet unreadable in 3 fetch runs is left out (and counted)


def dates() -> List[int]:
    """Formation dates, newest first."""
    return [T0 - k * OUTCOME_D * DAY for k in range(N_DATES)]


def skey(addr: str) -> int:
    return int(hashlib.sha256(addr.lower().encode()).hexdigest()[:8], 16) % 10_000


def in_sample(addr: str, share: float) -> bool:
    return skey(addr) < round(share * 10_000)


# --- series ------------------------------------------------------------------------------------

class Series:
    """A wallet's points (unix s, value). The value at x is the last point at or before x; 0 before the first."""

    __slots__ = ("t", "v")

    def __init__(self, points: Sequence[Sequence]):
        pts = sorted((float(p[0]) / 1000.0, float(p[1])) for p in points)
        self.t = [p[0] for p in pts]
        self.v = [p[1] for p in pts]

    def asof(self, x: float) -> float:
        i = bisect.bisect_right(self.t, x)
        return self.v[i - 1] if i else 0.0

    def times(self, a: float, b: float) -> List[float]:
        """Point times in (a, b]."""
        return self.t[bisect.bisect_right(self.t, a):bisect.bisect_right(self.t, b)]

    def staleness(self, x: float) -> Optional[float]:
        """Seconds since the last point at or before x; None before the first."""
        i = bisect.bisect_right(self.t, x)
        return x - self.t[i - 1] if i else None


class Wallet:
    __slots__ = ("addr", "av", "pnl", "pav", "ppnl", "lb_av", "lb_month_vlm", "lb_all_vlm", "pf_all_vlm",
                 "pf_month_vlm")

    def __init__(self, addr: str, reply, lb: Optional[dict] = None):
        self.addr = addr
        d = dict(reply) if isinstance(reply, list) else (reply or {})
        at, pa = d.get("allTime") or {}, d.get("perpAllTime") or {}
        self.av = Series(at.get("accountValueHistory") or [])
        self.pnl = Series(at.get("pnlHistory") or [])
        self.pav = Series(pa.get("accountValueHistory") or [])
        self.ppnl = Series(pa.get("pnlHistory") or [])
        self.pf_all_vlm = float(at.get("vlm") or 0)
        self.pf_month_vlm = float((d.get("month") or {}).get("vlm") or 0)
        lb = lb or {}
        self.lb_av = float(lb.get("av") or 0)
        self.lb_month_vlm = float(lb.get("month_vlm") or 0)
        self.lb_all_vlm = float(lb.get("all_vlm") or 0)

    def market_maker(self) -> bool:
        return self.lb_av >= MM_MIN_AV and self.lb_month_vlm / self.lb_av > MM_RATIO

    def sub_accounts(self) -> bool:
        """The leaderboard row adds sub-accounts the portfolio does not cover."""
        return (self.pf_all_vlm < SUB_VLM_SHARE * self.lb_all_vlm
                or (self.pf_month_vlm == 0 and self.lb_month_vlm > 0))

    def big(self) -> bool:
        return self.lb_all_vlm >= BIG_VLM


def window(w: Wallet, start: float, end: float, perps: bool = False) -> Tuple[float, Optional[float], float]:
    """(PnL, ROI, base) between start and end, all as of the last points. Base = account value at start + the
    largest cumulative net deposit (change in account value - PnL since start) at any point in (start, end], when
    positive: deposits enlarge it, withdrawals never shrink it. ROI None when the base is under MIN_BASE."""
    av, pn = (w.pav, w.ppnl) if perps else (w.av, w.pnl)
    a0, p0 = av.asof(start), pn.asof(start)
    top = 0.0
    for x in sorted(set(av.times(start, end)) | set(pn.times(start, end))):
        top = max(top, (av.asof(x) - a0) - (pn.asof(x) - p0))
    pnl = pn.asof(end) - p0
    base = a0 + top
    return pnl, (pnl / base if base >= MIN_BASE else None), base


def active(w: Wallet, t: float) -> bool:
    """Perps PnL moved between the wallet's last two perps points at or before t."""
    i = bisect.bisect_right(w.ppnl.t, t)
    return i >= 2 and w.ppnl.v[i - 1] != w.ppnl.v[i - 2]


def eligible_base(w: Wallet, t: float, need_active: bool = True, drop_mm: bool = True, perps: bool = False) -> bool:
    """The floors and the activity rule, read as of c: the last point at or before t of the series the outcome is
    measured on (total, or perps for the perps arms). The other series can have points between c and t, which
    belong to the outcome's span; nothing after c is read."""
    if drop_mm and w.market_maker():
        return False
    ser = w.pav if perps else w.av
    i = bisect.bisect_right(ser.t, t)
    if not i:
        return False
    c = ser.t[i - 1]
    if w.av.asof(c) < MIN_AV or w.pav.asof(c) < MIN_PERP:
        return False
    return active(w, c) if need_active else True


def last_point(ser: Series, x: float) -> Optional[float]:
    i = bisect.bisect_right(ser.t, x)
    return ser.t[i - 1] if i else None


def effective_days(w: Wallet, a: float, b: float) -> Optional[float]:
    """Days between the points a window from a to b actually reads (from the first point if a is before it)."""
    pb = last_point(w.av, b)
    if pb is None:
        return None
    pa = last_point(w.av, a)
    return (pb - (pa if pa is not None else w.av.t[0])) / DAY


def ranked(wallets: Sequence[Wallet], t: float, days: int, min_roi: Optional[float] = None, perps: bool = False,
           need_active: bool = True, drop_mm: bool = True) -> List[Tuple[float, str]]:
    """(ROI, address) of the wallets meeting the list's rules for a ``days`` window at t, best first (ties: address)."""
    out = []
    for w in wallets:
        if not eligible_base(w, t, need_active, drop_mm, perps):
            continue
        pnl, roi, _ = window(w, t - days * DAY, t, perps)
        alltime = (w.ppnl if perps else w.pnl).asof(t)
        if roi is None or pnl < MIN_PNL or alltime < pnl:
            continue
        if min_roi is not None and roi < min_roi:
            continue
        out.append((roi, w.addr))
    out.sort(key=lambda r: (-r[0], r[1]))
    return out


def median(xs: Sequence[float]) -> Optional[float]:
    s = sorted(xs)
    n = len(s)
    if not n:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def metrics(outs: Sequence[dict]) -> dict:
    n = len(outs)
    if not n:
        return {"n": 0, "hit": None, "hit_active": None, "median_roi": None, "mean_roi_clipped": None,
                "capital_return": None, "inactive": None, "under_10m": None, "sub_accounts": None}
    act = [o for o in outs if abs(o["pnl"]) >= HIT_PNL]
    rois = [o["roi"] for o in outs if o["roi"] is not None]
    base = sum(o["base"] for o in outs)
    med = median(rois)
    return {
        "n": n,
        "hit": 100.0 * sum(1 for o in outs if o["pnl"] >= HIT_PNL) / n,
        "hit_active": 100.0 * sum(1 for o in act if o["pnl"] >= HIT_PNL) / len(act) if act else None,
        "median_roi": None if med is None else 100.0 * med,
        "mean_roi_clipped": 100.0 * sum(max(-ROI_CLIP, min(ROI_CLIP, r)) for r in rois) / len(rois) if rois else None,
        "capital_return": 100.0 * sum(o["pnl"] for o in outs) / base if base > 0 else None,
        "inactive": 100.0 * (n - len(act)) / n,
        "under_10m": 100.0 * sum(1 for o in outs if not o["big"]) / n,
        "sub_accounts": 100.0 * sum(1 for o in outs if o["sub"]) / n,
    }


def sign_flip_p(diffs: Sequence[float]) -> float:
    """Exact one-sided p of the mean: the share of the 2^n sign patterns on |d| whose mean is at least the observed."""
    n = len(diffs)
    obs = sum(diffs)
    mags = [abs(d) for d in diffs]
    hits = sum(1 for signs in itertools.product((1, -1), repeat=n)
               if sum(s * m for s, m in zip(signs, mags)) >= obs - 1e-9)
    return hits / 2 ** n


def core(diffs: Sequence[float]) -> dict:
    """Conditions 1-3 of the bar on per-date differences (points)."""
    n = len(diffs)
    mean = sum(diffs) / n
    positive = sum(1 for d in diffs if d > 0)
    p = sign_flip_p(diffs)
    return {"mean_pp": mean, "dates_positive": positive, "dates": n, "p": p,
            "met": mean >= BAR_PP and positive >= BAR_DATES and p <= BAR_P}


def side_means(diffs: Sequence[float], up: Sequence[bool]) -> dict:
    ups = [d for d, u in zip(diffs, up) if u]
    downs = [d for d, u in zip(diffs, up) if not u]
    out = {"up_dates": len(ups), "down_dates": len(downs),
           "up_mean": sum(ups) / len(ups) if ups else None, "down_mean": sum(downs) / len(downs) if downs else None}
    out["required"] = len(ups) >= MIN_SIDE and len(downs) >= MIN_SIDE
    out["met"] = (not out["required"]) or (out["up_mean"] > 0 and out["down_mean"] > 0)
    return out


def lag1(xs: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs)
    return None if var == 0 else sum((xs[i] - m) * (xs[i + 1] - m) for i in range(n - 1)) / var


def _outcome(w: Wallet, t: float, perps: bool = False) -> dict:
    pnl, roi, base = window(w, t, t + OUTCOME_D * DAY, perps)
    return {"pnl": pnl, "roi": roi, "base": base, "big": w.big(), "sub": w.sub_accounts()}


def equal_arms(pools: Dict[int, List[Tuple[float, str]]], k: int) -> Tuple[Dict[int, List[str]], int]:
    """The top k of each window's pool; when a pool is short, every window takes the shortest pool's size."""
    size = min([k] + [len(p) for p in pools.values()])
    return {d: [a for _, a in p[:size]] for d, p in pools.items()}, size


def analyse(wallets: Sequence[Wallet], share: float, btc_up: Optional[Sequence[bool]] = None) -> dict:
    """``btc_up``: per date (newest first), whether BTC closed higher 30 days after it."""
    k = max(1, round(K_FULL * share))
    cap = max(1, round(CAP_FULL * share))
    by = {w.addr: w for w in wallets}
    big = {w.addr for w in wallets if w.big()}
    no_sub = {w.addr for w in wallets if not w.sub_accounts()}
    keys = ("primary", "perps", "big", "rules", "k_half", "k_double", "with_mm", "no_active_rule", "no_sub")
    res: Dict[str, list] = {key: [] for key in keys}
    res.update({"dates": [], "baseline": [], "sizes": [], "pools": [], "strata": [], "staleness_days": []})
    lists: Dict[int, List[set]] = {d: [] for d in WINDOWS}
    for t in dates():
        oc: Dict[Tuple[str, bool], dict] = {}

        def out(addrs, perps=False):
            for a in addrs:
                if (a, perps) not in oc:
                    oc[(a, perps)] = _outcome(by[a], t, perps)
            return [oc[(a, perps)] for a in addrs]

        res["dates"].append(time.strftime("%Y-%m-%d", time.gmtime(t)))
        pools = {d: ranked(wallets, t, d) for d in WINDOWS}
        arms, size = equal_arms(pools, k)
        res["sizes"].append(size)
        res["pools"].append({d: len(p) for d, p in pools.items()})
        res["primary"].append({d: metrics(out(arms[d])) for d in WINDOWS})
        for d in WINDOWS:
            lists[d].append(set(arms[d]))
        res["staleness_days"].append({d: median([by[a].av.staleness(t) / DAY for a in arms[d]]) for d in WINDOWS})
        for key, kk in (("k_half", max(1, k // 2)), ("k_double", 2 * k)):
            a2, _ = equal_arms(pools, kk)
            res[key].append({d: metrics(out(a2[d])) for d in WINDOWS})
        def within(members):
            """The primary ranking restricted to a set of wallets (each wallet's rank key is its own)."""
            return {d: [r for r in pools[d] if r[1] in members] for d in WINDOWS}

        pa, _ = equal_arms({d: ranked(wallets, t, d, perps=True) for d in WINDOWS}, k)
        res["perps"].append({d: metrics(out(pa[d], perps=True)) for d in WINDOWS})
        ba, _ = equal_arms(within(big), k)
        res["big"].append({d: metrics(out(ba[d])) for d in WINDOWS})
        ma, _ = equal_arms({d: ranked(wallets, t, d, drop_mm=False) for d in WINDOWS}, k)
        res["with_mm"].append({d: metrics(out(ma[d])) for d in WINDOWS})
        na, _ = equal_arms({d: ranked(wallets, t, d, need_active=False) for d in WINDOWS}, k)
        res["no_active_rule"].append({d: metrics(out(na[d])) for d in WINDOWS})
        sa, _ = equal_arms(within(no_sub), k)
        res["no_sub"].append({d: metrics(out(sa[d])) for d in WINDOWS})
        res["rules"].append({d: metrics(out([a for _, a in ranked(wallets, t, d, MIN_ROI)[:cap]])) for d in WINDOWS})
        base_w = [w for w in wallets if eligible_base(w, t)]
        res["baseline"].append(metrics(out([w.addr for w in base_w])))
        strata = {}
        for lo, hi in STALE_STRATA:
            members = {w.addr for w in base_w if lo * DAY <= w.av.staleness(t) < hi * DAY}
            ks = max(1, round(k * len(members) / max(1, len(base_w))))
            sarms, _ = equal_arms(within(members), ks)
            lengths = {d: {"window_days": median([x for a in sarms[d] if (x := effective_days(by[a], t - d * DAY, t)) is not None]),
                           "outcome_days": median([x for a in sarms[d] if (x := effective_days(by[a], t, t + OUTCOME_D * DAY)) is not None])}
                       for d in WINDOWS}
            strata[f"{lo}-{hi}d"] = {"k": ks, "eligible": len(members), "lengths": lengths,
                                     **{d: metrics(out(sarms[d])) for d in WINDOWS}}
        res["strata"].append(strata)

    def diffs(key, d, ref=WINDOWS[0], field="hit"):
        return [p[d][field] - p[ref][field] if p[d][field] is not None and p[ref][field] is not None else None
                for p in res[key]]

    verdict = {}
    for d in WINDOWS[1:]:
        hd = diffs("primary", d)
        if any(x is None for x in hd):
            verdict[d] = {"met": False, "missing_dates": sum(1 for x in hd if x is None)}
            continue
        v = core(hd)
        checks = {}
        checks["btc"] = side_means(hd, btc_up) if btc_up is not None else {"met": False, "missing": "btc"}
        for key in ("big", "perps"):
            xs = [x for x in diffs(key, d) if x is not None]
            checks[key] = {"mean_pp": sum(xs) / len(xs) if xs else None, "dates": len(xs),
                           "met": bool(xs) and sum(xs) / len(xs) > 0}
        rd = [x for x in diffs("primary", d, field="mean_roi_clipped") if x is not None]
        checks["roi"] = {"mean_pp": sum(rd) / len(rd) if rd else None, "met": bool(rd) and sum(rd) / len(rd) >= 0}
        v["checks"] = checks
        v["lag1"] = lag1(hd)
        v["met"] = v["met"] and all(c["met"] for c in checks.values())
        verdict[d] = v
    passing = [d for d in WINDOWS[1:] if verdict[d]["met"]]
    per_date_90_60 = diffs("primary", 90, ref=60)                   # context, always
    between = None
    if len(passing) == 2:
        between = core([x for x in diffs("primary", 90, ref=60)])
        chosen = 90 if between["met"] else 60
    else:
        chosen = passing[0] if passing else WINDOWS[0]
    turnover = {d: [{"from": res["dates"][i + 1], "to": res["dates"][i],
                     "replaced": 100.0 * (1 - len(lists[d][i] & lists[d][i + 1]) / len(lists[d][i + 1]))
                     if lists[d][i + 1] else None} for i in range(len(lists[d]) - 1)] for d in WINDOWS}
    return {"k": k, "cap": cap, "share": share, "wallets": len(wallets), **res, "turnover": turnover,
            "verdict": verdict, "ninety_vs_sixty": between, "ninety_vs_sixty_per_date": per_date_90_60,
            "chosen_window": chosen, "signal": bool(passing)}


# --- fetching ----------------------------------------------------------------------------------

def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS leaderboard (addr TEXT PRIMARY KEY, skey INTEGER, av REAL, month_vlm REAL,
        all_vlm REAL, all_pnl REAL);
    CREATE TABLE IF NOT EXISTS portfolio (addr TEXT PRIMARY KEY, raw BLOB, fetched REAL);
    CREATE TABLE IF NOT EXISTS failures (addr TEXT PRIMARY KEY, runs INTEGER, last_error TEXT);
    """)
    return conn


def _post(body: dict, timeout: int = 30):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def valid(reply) -> bool:
    """A portfolio reply: a list of [name, dict] pairs with a non-empty all-time history."""
    if not isinstance(reply, list) or not reply:
        return False
    if not all(isinstance(p, list) and len(p) == 2 and isinstance(p[1], dict) for p in reply):
        return False
    at = dict(reply).get("allTime") or {}
    return bool(at.get("accountValueHistory")) and bool(at.get("pnlHistory"))


def load_leaderboard(conn: sqlite3.Connection, path: Optional[Path]) -> int:
    if conn.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0]:
        return 0
    if path:
        raw = path.read_bytes()
    else:
        with urllib.request.urlopen(LEADERBOARD, timeout=120) as r:
            raw = r.read()
    rows = json.loads(raw)["leaderboardRows"]
    out = []
    for e in rows:
        a = (e.get("ethAddress") or "").lower()
        if not a:
            continue
        perf = {n: m for n, m in e.get("windowPerformances") or []}
        out.append((a, skey(a), float(e.get("accountValue") or 0), float((perf.get("month") or {}).get("vlm") or 0),
                    float((perf.get("allTime") or {}).get("vlm") or 0), float((perf.get("allTime") or {}).get("pnl") or 0)))
    conn.executemany("INSERT OR REPLACE INTO leaderboard VALUES (?,?,?,?,?,?)", out)
    for k, v in (("leaderboard_sha256", hashlib.sha256(raw).hexdigest()), ("leaderboard_rows", str(len(rows))),
                 ("leaderboard_loaded_at", str(time.time()))):
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (k, v))
    conn.commit()
    return len(out)


def sample(conn: sqlite3.Connection, share: float) -> List[str]:
    return [a for (a,) in conn.execute(
        "SELECT addr FROM leaderboard WHERE skey < ? ORDER BY skey, addr", (round(share * 10_000),))]


def load_btc(conn: sqlite3.Connection) -> None:
    """BTC's price at each date and 30 days later (the open of the daily candle starting then)."""
    if conn.execute("SELECT 1 FROM meta WHERE k = 'btc_open'").fetchone():
        return
    start = (dates()[-1] - DAY) * 1000
    end = (T0 + OUTCOME_D * DAY + DAY) * 1000
    candles = _post({"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "1d", "startTime": start, "endTime": end}})
    opens = {int(c["t"]) // 1000: float(c["o"]) for c in candles}
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('btc_open', ?)", (json.dumps(opens),))
    conn.commit()


def btc_up(conn: sqlite3.Connection) -> Optional[List[bool]]:
    row = conn.execute("SELECT v FROM meta WHERE k = 'btc_open'").fetchone()
    if not row:
        return None
    opens = {int(k): v for k, v in json.loads(row[0]).items()}
    try:
        return [opens[t + OUTCOME_D * DAY] > opens[t] for t in dates()]
    except KeyError:
        return None


def fetch(conn: sqlite3.Connection, share: float, rate: int, leaderboard: Optional[Path], workers: int = 4) -> None:
    n = load_leaderboard(conn, leaderboard)
    if n:
        print(f"leaderboard: {n} rows", flush=True)
    load_btc(conn)
    done = {a for (a,) in conn.execute("SELECT addr FROM portfolio")}
    gone = {a for (a,) in conn.execute("SELECT addr FROM failures WHERE runs >= ?", (MAX_RUNS,))}
    todo = [a for a in sample(conn, share) if a not in done and a not in gone]
    print(f"sample {len(sample(conn, share))}, read {len(done)}, given up {len(gone)}, to read {len(todo)}", flush=True)
    lock = threading.Lock()
    state = {"next": time.time(), "gap": 60.0 * WEIGHT / rate, "done": 0, "limited": 0, "failed": 0,
             "since_commit": time.time()}

    def wait():
        with lock:
            at = max(time.time(), state["next"])
            state["next"] = at + state["gap"]
        time.sleep(max(0.0, at - time.time()))

    def one(a):
        err = ""
        for attempt in range(6):
            wait()
            try:
                reply = _post({"type": "portfolio", "user": a})
                if not valid(reply):
                    err = "invalid reply: " + json.dumps(reply)[:120]
                    time.sleep(2 * (attempt + 1))
                    continue
            except urllib.error.HTTPError as exc:
                err = f"HTTP {exc.code}"
                if exc.code == 429:
                    with lock:
                        state["limited"] += 1
                        state["next"] = max(state["next"], time.time() + 20 * (attempt + 1))
                else:
                    time.sleep(2 * (attempt + 1))
                continue
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"[:200]
                time.sleep(2 * (attempt + 1))
                continue
            with lock:
                conn.execute("INSERT OR REPLACE INTO portfolio VALUES (?,?,?)",
                             (a, zlib.compress(json.dumps(reply, separators=(",", ":")).encode()), time.time()))
                conn.execute("DELETE FROM failures WHERE addr = ?", (a,))
                state["done"] += 1
                if state["done"] % 50 == 0 or time.time() - state["since_commit"] > 60:
                    conn.commit()
                    state["since_commit"] = time.time()
                if state["done"] % 500 == 0:
                    print(f"{state['done']}/{len(todo)} read, {state['limited']} rate-limited, "
                          f"{state['failed']} failed", flush=True)
            return
        with lock:
            state["failed"] += 1
            conn.execute("INSERT INTO failures VALUES (?, 1, ?) ON CONFLICT(addr) DO UPDATE SET runs = runs + 1, "
                         "last_error = excluded.last_error", (a, err))

    try:
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(one, todo))
    finally:
        with lock:
            conn.commit()
    print(f"done: {state['done']} read, {state['limited']} rate-limited, {state['failed']} failed", flush=True)


def wallets_from(conn: sqlite3.Connection, share: float) -> Tuple[List[Wallet], dict]:
    keep = set(sample(conn, share))
    lb = {a: {"av": av, "month_vlm": mv, "all_vlm": tv} for a, av, mv, tv in
          conn.execute("SELECT addr, av, month_vlm, all_vlm FROM leaderboard")}
    ws = [Wallet(a, json.loads(zlib.decompress(raw)), lb.get(a)) for a, raw in
          conn.execute("SELECT addr, raw FROM portfolio") if a in keep]
    gone = {a for (a,) in conn.execute("SELECT addr FROM failures WHERE runs >= ?", (MAX_RUNS,))} & keep
    read = {w.addr for w in ws}
    info = {"sampled": len(keep), "read": len(read), "left_out_unreadable": len(gone),
            "missing": len(keep - read - gone)}
    return ws, info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("fetch", "status", "analyse"))
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--share", type=float, default=SHARE)
    ap.add_argument("--rate", type=int, default=1100, help="weight per minute (Hyperliquid allows 1,200 per IP)")
    ap.add_argument("--leaderboard", type=Path, help="a saved leaderboard snapshot (default: download one)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    conn = connect(args.db)
    meta = dict(conn.execute("SELECT k, v FROM meta"))
    if args.cmd == "fetch":
        fetch(conn, args.share, args.rate, args.leaderboard)
    elif args.cmd == "status":
        _, info = wallets_from(conn, args.share)
        print(json.dumps({**info, "leaderboard_sha256": meta.get("leaderboard_sha256"),
                          "leaderboard_rows": meta.get("leaderboard_rows"), "btc": bool(btc_up(conn))}))
    else:
        ws, info = wallets_from(conn, args.share)
        if not ws or info["missing"]:
            print(f"not ready: {json.dumps(info)}", file=sys.stderr)
            return 1
        res = analyse(ws, args.share, btc_up(conn))
        res["data"] = {**info, "leaderboard_sha256": meta.get("leaderboard_sha256"),
                       "leaderboard_rows": meta.get("leaderboard_rows")}
        text = json.dumps(res, indent=1, default=str)
        if args.out:
            args.out.write_text(text)
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
