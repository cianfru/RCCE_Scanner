"""
Selection window study (declared in docs/reviews/selection-window-study.md before any result was computed): which
window, 30, 60 or 90 days, picks Hyperliquid wallets whose profits carry into the next 30 days, with the profitable
traders' other rules unchanged.

    python -m backtest.selection_window_study fetch --share 0.30        (from backend/; resumable)
    python -m backtest.selection_window_study status
    python -m backtest.selection_window_study analyse --out results.json

Data: today's leaderboard (addresses, market-maker flag) and each sampled wallet's Hyperliquid `portfolio` history
(account value and all-time PnL, total and perps only), interpolated at each date. The cache (--db, default
data/selection_window_cache/study.db, gitignored) keeps every answer, so a fetch cut short continues where it stopped.
"""
from __future__ import annotations

import argparse
import bisect
import datetime
import hashlib
import json
import random
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
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
SHARE = 0.30                      # fixed hash sample of the leaderboard (market makers left out)
K_FULL = 400                      # list size compared (about today's 431); in the sample, round(K_FULL * share)
CAP_FULL = 600                    # today's cap, for the "rules as they are" arms
MIN_AV, MIN_PERP, MIN_PNL, MIN_BASE, MIN_ROI = 10_000, 5_000, 10_000, 1_000, 0.30
MM_RATIO = 100                    # monthly volume over 100x the account value: market maker (as the live roster)
INACTIVE_PNL = 100                # |next-30-day PnL| under $100: did not trade (reported, still counted)
BAR_PP, BAR_DATES, BOOT, BOOT_SEED, BOOT_LOW = 3.0, 10, 10_000, 20261031, 0.025
FINE_SPAN_D = 2                   # robustness subset: every interpolation span at most 2 days
WEIGHT = 20                       # portfolio request weight


def dates() -> List[int]:
    """Formation dates, newest first."""
    return [T0 - k * OUTCOME_D * DAY for k in range(N_DATES)]


def skey(addr: str) -> int:
    return int(hashlib.sha256(addr.lower().encode()).hexdigest()[:8], 16) % 10_000


def in_sample(addr: str, share: float) -> bool:
    return skey(addr) < round(share * 10_000)


# --- series ------------------------------------------------------------------------------------

class Series:
    """A wallet's points (unix s, value); linear between points, 0 before the first, the last after it."""

    __slots__ = ("t", "v")

    def __init__(self, points: Sequence[Sequence]):
        pts = sorted((float(p[0]) / 1000.0, float(p[1])) for p in points)
        self.t = [p[0] for p in pts]
        self.v = [p[1] for p in pts]

    def at(self, x: float) -> float:
        t = self.t
        if not t or x < t[0]:
            return 0.0
        if x >= t[-1]:
            return self.v[-1]
        i = bisect.bisect_right(t, x)
        t0, t1, v0, v1 = t[i - 1], t[i], self.v[i - 1], self.v[i]
        return v0 if t1 == t0 else v0 + (v1 - v0) * (x - t0) / (t1 - t0)

    def span(self, x: float) -> float:
        """Length (s) of the interval x is interpolated in: 0 on a point, before the first or after the last."""
        t = self.t
        if not t or x < t[0] or x >= t[-1]:
            return 0.0
        i = bisect.bisect_right(t, x)
        return 0.0 if t[i - 1] == x else t[i] - t[i - 1]


class Wallet:
    __slots__ = ("addr", "av", "pnl", "pav")

    def __init__(self, addr: str, data: dict):
        self.addr = addr
        self.av = Series(data.get("av") or [])
        self.pnl = Series(data.get("pnl") or [])
        self.pav = Series(data.get("pav") or [])


def window(w: Wallet, start: float, end: float) -> Tuple[float, Optional[float]]:
    """(PnL, ROI) between start and end. ROI = PnL / (account value at start + net deposits, if positive);
    None when that base is under MIN_BASE (the live list drops such ROIs: a nearly empty start)."""
    pnl = w.pnl.at(end) - w.pnl.at(start)
    a0 = w.av.at(start)
    flow = (w.av.at(end) - a0) - pnl
    base = a0 + max(flow, 0.0)
    return pnl, (pnl / base if base >= MIN_BASE else None)


def outcome(w: Wallet, t: float) -> dict:
    pnl, roi = window(w, t, t + OUTCOME_D * DAY)
    a0 = w.av.at(t)
    flow = (w.av.at(t + OUTCOME_D * DAY) - a0) - pnl
    return {"pnl": pnl, "roi": roi, "base": a0 + max(flow, 0.0)}


def fine(w: Wallet, t: float) -> bool:
    xs = [t - d * DAY for d in WINDOWS] + [t, t + OUTCOME_D * DAY]
    return all(s.span(x) <= FINE_SPAN_D * DAY for x in xs for s in (w.av, w.pnl))


def eligible_base(w: Wallet, t: float) -> bool:
    return w.av.at(t) >= MIN_AV and w.pav.at(t) >= MIN_PERP


def ranked(wallets: Sequence[Wallet], t: float, days: int, min_roi: Optional[float] = None) -> List[Tuple[float, str]]:
    """(ROI, address) of the wallets meeting the list's rules for a ``days`` window at t, best first."""
    out = []
    for w in wallets:
        if not eligible_base(w, t):
            continue
        pnl, roi = window(w, t - days * DAY, t)
        if roi is None or pnl < MIN_PNL or w.pnl.at(t) < pnl:
            continue
        if min_roi is not None and roi < min_roi:
            continue
        out.append((roi, w.addr))
    out.sort(key=lambda r: (-r[0], r[1]))
    return out


def metrics(outs: Sequence[dict]) -> dict:
    n = len(outs)
    if not n:
        return {"n": 0, "hit": None, "median_roi": None, "capital_return": None, "inactive": None}
    rois = sorted(o["roi"] for o in outs if o["roi"] is not None)
    base = sum(o["base"] for o in outs)
    return {
        "n": n,
        "hit": 100.0 * sum(1 for o in outs if o["pnl"] > 0) / n,
        "median_roi": 100.0 * rois[len(rois) // 2] if len(rois) % 2 else (100.0 * (rois[len(rois) // 2 - 1] + rois[len(rois) // 2]) / 2 if rois else None),
        "capital_return": 100.0 * sum(o["pnl"] for o in outs) / base if base > 0 else None,
        "inactive": 100.0 * sum(1 for o in outs if abs(o["pnl"]) < INACTIVE_PNL) / n,
    }


def bar(diffs: Sequence[float]) -> dict:
    """The declared bar for one longer window against 30 days, on the per-date hit-rate differences (points)."""
    n = len(diffs)
    mean = sum(diffs) / n
    rng = random.Random(BOOT_SEED)
    boots = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOT))
    low = boots[int(BOOT_LOW * BOOT)]
    positive = sum(1 for d in diffs if d > 0)
    return {"mean_pp": mean, "dates_positive": positive, "dates": n, "boot_low_pp": low,
            "met": mean >= BAR_PP and positive >= BAR_DATES and low > 0}


def analyse(wallets: Sequence[Wallet], share: float) -> dict:
    k = max(1, round(K_FULL * share))
    cap = max(1, round(CAP_FULL * share))
    by = {w.addr: w for w in wallets}
    res: Dict[str, list] = {"dates": [], "primary": [], "rules": [], "baseline": [], "fine": [], "k_small": [], "k_large": []}
    lists: Dict[int, List[set]] = {d: [] for d in WINDOWS}
    for t in dates():
        oc: Dict[str, dict] = {}

        def out(addrs):
            for a in addrs:
                if a not in oc:
                    oc[a] = outcome(by[a], t)
            return [oc[a] for a in addrs]

        res["dates"].append(time.strftime("%Y-%m-%d", time.gmtime(t)))
        prim, rules, ks, kl = {}, {}, {}, {}
        for d in WINDOWS:
            r = ranked(wallets, t, d)
            top = [a for _, a in r[:k]]
            lists[d].append(set(top))
            prim[d] = metrics(out(top))
            ks[d] = metrics(out([a for _, a in r[:max(1, k // 2)]]))
            kl[d] = metrics(out([a for _, a in r[:2 * k]]))
            rules[d] = metrics(out([a for _, a in ranked(wallets, t, d, MIN_ROI)[:cap]]))
        res["primary"].append(prim)
        res["rules"].append(rules)
        res["k_small"].append(ks)
        res["k_large"].append(kl)
        res["baseline"].append(metrics(out([w.addr for w in wallets if eligible_base(w, t)])))
        fw = [w for w in wallets if fine(w, t)]
        fk = max(1, round(k * len(fw) / max(1, len(wallets))))
        res["fine"].append({d: metrics(out([a for _, a in ranked(fw, t, d)[:fk]])) for d in WINDOWS})
    verdict = {}
    for d in WINDOWS[1:]:
        diffs = [p[d]["hit"] - p[WINDOWS[0]]["hit"] for p in res["primary"]
                 if p[d]["hit"] is not None and p[WINDOWS[0]]["hit"] is not None]
        verdict[d] = bar(diffs) if len(diffs) == N_DATES else {"met": False, "missing_dates": N_DATES - len(diffs)}
    passing = [d for d in WINDOWS[1:] if verdict[d]["met"]]
    chosen = max(passing, key=lambda d: verdict[d]["mean_pp"]) if passing else WINDOWS[0]
    turnover = {d: [100.0 * (1 - len(lists[d][i] & lists[d][i + 1]) / len(lists[d][i])) if lists[d][i] else None
                    for i in range(len(lists[d]) - 1)] for d in WINDOWS}
    return {"k": k, "cap": cap, "share": share, "wallets": len(wallets), **res, "turnover": turnover,
            "verdict": verdict, "chosen_window": chosen, "signal": bool(passing)}


# --- fetching ----------------------------------------------------------------------------------

def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS leaderboard (addr TEXT PRIMARY KEY, skey INTEGER, av REAL, month_vlm REAL,
        all_vlm REAL, all_pnl REAL, mm INTEGER);
    CREATE TABLE IF NOT EXISTS portfolio (addr TEXT PRIMARY KEY, data TEXT, fetched REAL);
    """)
    return conn


def _post(body: dict, timeout: int = 30):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def load_leaderboard(conn: sqlite3.Connection) -> int:
    if conn.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0]:
        return 0
    with urllib.request.urlopen(LEADERBOARD, timeout=120) as r:
        rows = json.loads(r.read())["leaderboardRows"]
    out = []
    for e in rows:
        a = (e.get("ethAddress") or "").lower()
        if not a:
            continue
        perf = {n: m for n, m in e.get("windowPerformances") or []}
        av = float(e.get("accountValue") or 0)
        mv = float((perf.get("month") or {}).get("vlm") or 0)
        out.append((a, skey(a), av, mv, float((perf.get("allTime") or {}).get("vlm") or 0),
                    float((perf.get("allTime") or {}).get("pnl") or 0), int(av > 0 and mv / av > MM_RATIO)))
    conn.executemany("INSERT OR REPLACE INTO leaderboard VALUES (?,?,?,?,?,?,?)", out)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('leaderboard_at', ?)", (str(time.time()),))
    conn.commit()
    return len(out)


def sample(conn: sqlite3.Connection, share: float) -> List[str]:
    return [a for (a,) in conn.execute(
        "SELECT addr FROM leaderboard WHERE mm = 0 AND skey < ? ORDER BY skey, addr", (round(share * 10_000),))]


def _compact(pf: dict) -> dict:
    d = dict(pf)
    at, pa = d.get("allTime") or {}, d.get("perpAllTime") or {}
    return {"av": at.get("accountValueHistory") or [], "pnl": at.get("pnlHistory") or [],
            "pav": pa.get("accountValueHistory") or []}


def fetch(conn: sqlite3.Connection, share: float, rate: int, workers: int = 4) -> None:
    n = load_leaderboard(conn)
    if n:
        print(f"leaderboard: {n} rows", flush=True)
    done = {a for (a,) in conn.execute("SELECT addr FROM portfolio")}
    todo = [a for a in sample(conn, share) if a not in done]
    print(f"sample {len(done) + len(todo)}, to read {len(todo)}", flush=True)
    lock = threading.Lock()
    state = {"next": time.time(), "gap": 60.0 * WEIGHT / rate, "done": 0, "limited": 0}

    def wait():
        with lock:
            now = time.time()
            at = max(now, state["next"])
            state["next"] = at + state["gap"]
        time.sleep(max(0.0, at - time.time()))

    def one(a):
        for attempt in range(8):
            wait()
            try:
                pf = _post({"type": "portfolio", "user": a})
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    with lock:
                        state["limited"] += 1
                        state["next"] = max(state["next"], time.time() + 20 * (attempt + 1))
                    continue
                time.sleep(2 * (attempt + 1))
                continue
            except Exception:
                time.sleep(2 * (attempt + 1))
                continue
            with lock:
                conn.execute("INSERT OR REPLACE INTO portfolio VALUES (?,?,?)",
                             (a, json.dumps(_compact(pf), separators=(",", ":")), time.time()))
                state["done"] += 1
                if state["done"] % 200 == 0:
                    conn.commit()
                    print(f"{state['done']}/{len(todo)} read, {state['limited']} rate-limited", flush=True)
            return
        print(f"gave up on {a}", flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    conn.commit()
    print(f"done: {state['done']} read, {state['limited']} rate-limited", flush=True)


def wallets_from(conn: sqlite3.Connection, share: float) -> List[Wallet]:
    keep = set(sample(conn, share))
    return [Wallet(a, json.loads(d)) for a, d in conn.execute("SELECT addr, data FROM portfolio") if a in keep]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("fetch", "status", "analyse"))
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--share", type=float, default=SHARE)
    ap.add_argument("--rate", type=int, default=1000, help="weight per minute (Hyperliquid allows 1,200 per IP)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    conn = connect(args.db)
    if args.cmd == "fetch":
        fetch(conn, args.share, args.rate)
    elif args.cmd == "status":
        s = len(sample(conn, args.share))
        r = conn.execute("SELECT COUNT(*) FROM portfolio").fetchone()[0]
        print(f"leaderboard {conn.execute('SELECT COUNT(*) FROM leaderboard').fetchone()[0]}, sample {s}, read {r}")
    else:
        ws = wallets_from(conn, args.share)
        missing = len(sample(conn, args.share)) - len(ws)
        if missing:
            print(f"{missing} sampled wallets not read yet", file=sys.stderr)
            return 1
        res = analyse(ws, args.share)
        text = json.dumps(res, indent=1, default=str)
        if args.out:
            args.out.write_text(text)
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
