"""
Cohort selection study (declared in docs/reviews/cohort-selection-study.md before any result was computed): does a
rule built on longer, steadier or risk-adjusted profit pick Hyperliquid wallets that keep making money over the next
30 days more often than every wallet meeting the list's base rules?

Built on the half of the 31 October 2026 leaderboard snapshot read for the selection window study ("read" half,
`skey` under 5,000) and confirmed on the other half ("unread" half), read for this study. A rule passes only if it
meets the bar on both halves.

    python -m backtest.cohort_selection_study fetch          (from backend/; resumable; reads the unread half)
    python -m backtest.cohort_selection_study stability      (re-reads 200 wallets of the read half, compares points)
    python -m backtest.cohort_selection_study status
    python -m backtest.cohort_selection_study counts         (pool sizes per date and half; no outcome is read)
    python -m backtest.cohort_selection_study analyse --out results.json

Data, measures and the base rules are the selection window study's (backtest/selection_window_study.py), imported
unchanged: every value at a time is the wallet's last point at or before it, never interpolated.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
import sys
import time
import zlib
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from backtest import selection_window_study as sw

DAY = sw.DAY
# --- declared rules (docs/reviews/cohort-selection-study.md) --------------------------------------
LONG_D = 180                      # the candidates' window, days; a wallet's first point must be at least this old
BLOCK_D = 30                      # a month block
RECENT_BLOCKS, MIN_PROFIT_BLOCKS = 6, 5   # steady: profitable in at least 5 of the last 6 blocks
RANK_BLOCKS = 12                  # steady: ranked by profitable blocks among the last 12
MIN_PNL_LONG = 10_000             # PnL over the 180 days, all candidates
DD_FLOOR = 0.05                   # risk: the drop is floored at 5% of the base
K = 200                           # list size in each half (400 for the whole leaderboard, as before)
SPLIT = 5_000                     # skey under SPLIT: the read half; at or over: the unread half
HALVES = ("read", "unread")
CANDIDATES = ("dollars", "steady", "risk")
BAR_PP, BAR_DATES, BAR_P = 5.0, 9, 0.01
CORR_FLAT = 0.2                   # context: |correlation| of PnL changes with BTC's moves under this: little exposure
MIN_PAIRS = 8                     # context: point pairs needed for that correlation
STABILITY_N = 200
STABILITY_END = int(sw.T0 + sw.OUTCOME_D * DAY)   # 31 October 2026 00:00 UTC: the last outcome's end
BTC_FROM = sw.T0 - (sw.N_DATES - 1) * sw.OUTCOME_D * DAY - LONG_D * DAY - 5 * DAY


def half_of(addr: str) -> str:
    return "read" if sw.skey(addr) < SPLIT else "unread"


# --- measures ----------------------------------------------------------------------------------

def old_enough(w: sw.Wallet, t: float) -> bool:
    """The wallet's first account point is at least LONG_D days before t."""
    return bool(w.av.t) and w.av.t[0] <= t - LONG_D * DAY


def block_pnls(w: sw.Wallet, t: float, n: int) -> List[Optional[float]]:
    """PnL of the n month blocks before t, newest first: block i runs from t - (i+1)*30 d to t - i*30 d. None for a
    block that starts before the wallet's first point."""
    first = w.pnl.t[0] if w.pnl.t else None
    out = []
    for i in range(n):
        a, b = t - (i + 1) * BLOCK_D * DAY, t - i * BLOCK_D * DAY
        out.append(None if first is None or a < first else w.pnl.asof(b) - w.pnl.asof(a))
    return out


def profit_blocks(w: sw.Wallet, t: float, n: int) -> int:
    return sum(1 for p in block_pnls(w, t, n) if p is not None and p >= sw.HIT_PNL)


def drawdown(w: sw.Wallet, a: float, b: float) -> float:
    """The largest fall of cumulative PnL from a running peak, over the value at a and every point in (a, b]."""
    vals = [w.pnl.asof(a)] + [w.pnl.asof(x) for x in w.pnl.times(a, b)]
    peak, worst = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        worst = max(worst, peak - v)
    return worst


def long_rules(w: sw.Wallet, t: float) -> Optional[Tuple[float, Optional[float], float]]:
    """The candidates' shared rules at t: the base rules, a first point 180+ days old, PnL of $10K+ over the 180
    days, and all-time PnL at least that (not down before it). Returns the 180-day (PnL, ROI, base) or None."""
    if not sw.eligible_base(w, t) or not old_enough(w, t):
        return None
    pnl, roi, base = sw.window(w, t - LONG_D * DAY, t)
    if pnl < MIN_PNL_LONG or w.pnl.asof(t) < pnl:
        return None
    return pnl, roi, base


def score(rule: str, w: sw.Wallet, t: float) -> Optional[tuple]:
    """The wallet's rank key under a candidate rule (higher is better), or None when it does not qualify."""
    lr = long_rules(w, t)
    if lr is None:
        return None
    pnl, roi, base = lr
    if rule == "dollars":
        return (pnl,)
    if rule == "steady":
        if profit_blocks(w, t, RECENT_BLOCKS) < MIN_PROFIT_BLOCKS:
            return None
        return (profit_blocks(w, t, RANK_BLOCKS), pnl)
    if rule == "risk":
        if roi is None:
            return None
        return (roi / max(drawdown(w, t - LONG_D * DAY, t) / base, DD_FLOOR),)
    raise ValueError(rule)


def pick(wallets: Sequence[sw.Wallet], t: float, rule: str, k: int = K) -> Tuple[List[str], int]:
    """The top k wallets under a rule (ties: address) and the size of its pool."""
    pool = [(s, w.addr) for w in wallets if (s := score(rule, w, t)) is not None]
    pool.sort(key=lambda r: (tuple(-x for x in r[0]), r[1]))
    return [a for _, a in pool[:k]], len(pool)


# --- context: exposure to BTC --------------------------------------------------------------------

class Btc:
    """BTC daily closes {day open (s): close}; the price at x is the close of the last day ended at or before x."""

    def __init__(self, closes: Dict[int, float]):
        self.days = sorted(closes)
        self.c = closes

    def at(self, x: float) -> Optional[float]:
        import bisect
        i = bisect.bisect_right(self.days, x - DAY)
        return self.c[self.days[i - 1]] if i else None


def btc_corr(w: sw.Wallet, t: float, btc: Btc) -> Optional[float]:
    """Correlation, over the 180 days before t, of the wallet's PnL change between consecutive points with BTC's
    return over the same span. None with fewer than MIN_PAIRS pairs or no variation."""
    pts = [t - LONG_D * DAY] + w.pnl.times(t - LONG_D * DAY, t)
    xs, ys = [], []
    for a, b in zip(pts, pts[1:]):
        pa, pb = btc.at(a), btc.at(b)
        if not pa or not pb:
            continue
        xs.append(pb / pa - 1)
        ys.append(w.pnl.asof(b) - w.pnl.asof(a))
    n = len(xs)
    if n < MIN_PAIRS:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (vx * vy) ** 0.5


def exposure(ws: Sequence[sw.Wallet], t: float, btc: Optional[Btc]) -> Optional[dict]:
    if btc is None or not ws:
        return None
    cs = [btc_corr(w, t, btc) for w in ws]
    n = len(cs)
    return {"with_btc": 100.0 * sum(1 for c in cs if c is not None and c > CORR_FLAT) / n,
            "against_btc": 100.0 * sum(1 for c in cs if c is not None and c < -CORR_FLAT) / n,
            "little": 100.0 * sum(1 for c in cs if c is not None and abs(c) <= CORR_FLAT) / n,
            "unknown": 100.0 * sum(1 for c in cs if c is None) / n}


# --- the bar -------------------------------------------------------------------------------------

def core(diffs: Sequence[float]) -> dict:
    """Conditions 1-3 on per-date differences (points)."""
    n = len(diffs)
    mean = sum(diffs) / n
    positive = sum(1 for d in diffs if d > 0)
    p = sw.sign_flip_p(diffs)
    return {"mean_pp": mean, "dates_positive": positive, "dates": n, "p": p,
            "met": mean >= BAR_PP and positive >= BAR_DATES and p <= BAR_P}


def judge(per_date: List[dict], rule: str, btc_up: Optional[Sequence[Optional[bool]]]) -> dict:
    """The bar for one rule on one half. ``per_date``: each date's metrics per arm, newest first."""
    hd = [p[rule]["hit"] - p["baseline"]["hit"] if p[rule]["hit"] is not None else None for p in per_date]
    if any(x is None for x in hd):
        return {"met": False, "missing_dates": sum(1 for x in hd if x is None)}
    v = core(hd)
    rd = [p[rule]["mean_roi_clipped"] - p["baseline"]["mean_roi_clipped"] for p in per_date
          if p[rule]["mean_roi_clipped"] is not None and p["baseline"]["mean_roi_clipped"] is not None]
    roi = {"mean_pp": sum(rd) / len(rd) if rd else None, "dates": len(rd)}
    roi["met"] = len(rd) == len(per_date) and roi["mean_pp"] > 0
    side = sw.side_means(hd, btc_up) if btc_up is not None else {"met": False, "missing": "btc"}
    if btc_up is not None:
        side["met"] = bool(side["up_mean"] is not None and side["down_mean"] is not None
                           and side["up_mean"] > 0 and side["down_mean"] > 0)
    v.update(per_date_pp=hd, roi=roi, btc=side, lag1=sw.lag1(hd))
    v["met"] = v["met"] and roi["met"] and side["met"]
    return v


# --- analysis --------------------------------------------------------------------------------------

def analyse_half(ws: Sequence[sw.Wallet], btc_up, btc: Optional[Btc] = None) -> dict:
    by = {w.addr: w for w in ws}
    per_date, sizes, context = [], [], []
    lists: Dict[str, List[set]] = {r: [] for r in CANDIDATES + ("today",)}
    for t in sw.dates():
        oc: Dict[str, dict] = {}

        def out(addrs):
            for a in addrs:
                if a not in oc:
                    oc[a] = sw._outcome(by[a], t)
            return [oc[a] for a in addrs]

        base = [w.addr for w in ws if sw.eligible_base(w, t)]
        seasoned = [a for a in base if old_enough(by[a], t)]
        arms = {r: pick(ws, t, r) for r in CANDIDATES}
        today = [a for _, a in sw.ranked(ws, t, 30)[:K]]
        row = {"baseline": sw.metrics(out(base)), "seasoned": sw.metrics(out(seasoned)), "today": sw.metrics(out(today))}
        row.update({r: sw.metrics(out(arms[r][0])) for r in CANDIDATES})
        per_date.append(row)
        sizes.append({"baseline": len(base), "seasoned": len(seasoned), "today": len(today),
                      **{r: {"pool": arms[r][1], "list": len(arms[r][0])} for r in CANDIDATES}})
        tset = set(today)
        context.append({
            "overlap_with_today": {r: 100.0 * len(set(arms[r][0]) & tset) / len(arms[r][0]) if arms[r][0] else None
                                   for r in CANDIDATES},
            "exposure": {**{r: exposure([by[a] for a in arms[r][0]], t, btc) for r in CANDIDATES},
                         "today": exposure([by[a] for a in today], t, btc),
                         "baseline": exposure([by[a] for a in base], t, btc)},
        })
        for r in CANDIDATES:
            lists[r].append(set(arms[r][0]))
        lists["today"].append(tset)
    verdict = {r: judge(per_date, r, btc_up) for r in CANDIDATES}
    turnover = {r: [100.0 * (1 - len(lists[r][i] & lists[r][i + 1]) / len(lists[r][i + 1])) if lists[r][i + 1] else None
                    for i in range(len(lists[r]) - 1)] for r in lists}
    return {"wallets": len(ws), "dates": [time.strftime("%Y-%m-%d", time.gmtime(t)) for t in sw.dates()],
            "per_date": per_date, "sizes": sizes, "context": context, "turnover": turnover, "verdict": verdict}


def analyse(wallets: Sequence[sw.Wallet], btc_up, btc: Optional[Btc] = None) -> dict:
    halves = {h: analyse_half([w for w in wallets if half_of(w.addr) == h], btc_up, btc) for h in HALVES}
    passing = [r for r in CANDIDATES if all(halves[h]["verdict"][r]["met"] for h in HALVES)]
    chosen = max(passing, key=lambda r: (halves["unread"]["verdict"][r]["mean_pp"], -CANDIDATES.index(r))) if passing else None
    return {"halves": halves, "passing": passing, "chosen": chosen, "signal": bool(passing)}


def counts(wallets: Sequence[sw.Wallet]) -> dict:
    """Pool sizes per date and half: no outcome is read."""
    out = {}
    for h in HALVES:
        ws = [w for w in wallets if half_of(w.addr) == h]
        rows = []
        for t in sw.dates():
            base = [w for w in ws if sw.eligible_base(w, t)]
            rows.append({"date": time.strftime("%Y-%m-%d", time.gmtime(t)), "baseline": len(base),
                         "seasoned": sum(1 for w in base if old_enough(w, t)),
                         **{r: pick(ws, t, r)[1] for r in CANDIDATES}})
        out[h] = {"wallets": len(ws), "dates": rows}
    return out


# --- data -----------------------------------------------------------------------------------------

def wallets_all(conn: sqlite3.Connection) -> Tuple[List[sw.Wallet], dict]:
    lb = {a: {"av": av, "month_vlm": mv, "all_vlm": tv} for a, av, mv, tv in
          conn.execute("SELECT addr, av, month_vlm, all_vlm FROM leaderboard")}
    ws = [sw.Wallet(a, json.loads(zlib.decompress(raw)), lb.get(a)) for a, raw in conn.execute("SELECT addr, raw FROM portfolio")
          if a in lb]
    gone = {a for (a,) in conn.execute("SELECT addr FROM failures WHERE runs >= ?", (sw.MAX_RUNS,))}
    read = {w.addr for w in ws}
    info = {}
    for h in HALVES:
        listed = {a for a in lb if half_of(a) == h}
        info[h] = {"listed": len(listed), "read": len(read & listed), "left_out_unreadable": len(gone & listed),
                   "missing": len(listed - read - gone)}
    return ws, info


def load_btc_daily(conn: sqlite3.Connection) -> Optional[Btc]:
    row = conn.execute("SELECT v FROM meta WHERE k = 'btc_daily_close'").fetchone()
    if not row:
        candles = sw._post({"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "1d",
                                                              "startTime": int(BTC_FROM) * 1000,
                                                              "endTime": (STABILITY_END + DAY) * 1000}})
        closes = {int(c["t"]) // 1000: float(c["c"]) for c in candles if int(c["T"]) // 1000 <= STABILITY_END + DAY}
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('btc_daily_close', ?)", (json.dumps(closes),))
        conn.commit()
        row = (json.dumps(closes),)
    closes = {int(k): v for k, v in json.loads(row[0]).items()}
    return Btc(closes) if closes else None


def compare_points(old_reply, new_reply, end: float = STABILITY_END) -> dict:
    """Points before ``end`` (s) in the all-time account value and PnL series: are they the same in both replies?"""
    def pts(reply, key):
        d = dict(reply) if isinstance(reply, list) else {}
        return [(int(p[0]), str(p[1])) for p in ((d.get("allTime") or {}).get(key) or []) if int(p[0]) < end * 1000]
    out = {"same": True, "old_points": 0, "new_points": 0, "differing": 0}
    for key in ("accountValueHistory", "pnlHistory"):
        a, b = pts(old_reply, key), pts(new_reply, key)
        out["old_points"] += len(a)
        out["new_points"] += len(b)
        out["differing"] += len(set(a) ^ set(b))
    out["same"] = out["differing"] == 0
    return out


def stability(conn: sqlite3.Connection, n: int = STABILITY_N) -> dict:
    """Re-read n wallets of the read half (lowest skey, then address) and compare their points before 31 October."""
    conn.execute("CREATE TABLE IF NOT EXISTS stability (addr TEXT PRIMARY KEY, raw BLOB, fetched REAL)")
    rows = sorted((sw.skey(a), a, raw) for a, raw in conn.execute("SELECT addr, raw FROM portfolio") if half_of(a) == "read")[:n]
    res = []
    for _, a, raw in rows:
        got = conn.execute("SELECT raw FROM stability WHERE addr = ?", (a,)).fetchone()
        if got:
            new = json.loads(zlib.decompress(got[0]))
        else:
            time.sleep(60.0 * sw.WEIGHT / 1000)
            new = sw._post({"type": "portfolio", "user": a})
            conn.execute("INSERT OR REPLACE INTO stability VALUES (?,?,?)",
                         (a, zlib.compress(json.dumps(new, separators=(",", ":")).encode()), time.time()))
            conn.commit()
        res.append(compare_points(json.loads(zlib.decompress(raw)), new))
    return {"compared": len(res), "identical": sum(1 for r in res if r["same"]),
            "points_compared": sum(r["old_points"] for r in res), "points_differing": sum(r["differing"] for r in res)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("fetch", "stability", "status", "counts", "analyse"))
    ap.add_argument("--db", type=Path, default=sw.DEFAULT_DB)
    ap.add_argument("--rate", type=int, default=1100, help="weight per minute (Hyperliquid allows 1,200 per IP)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    conn = sw.connect(args.db)
    meta = dict(conn.execute("SELECT k, v FROM meta"))
    if args.cmd == "fetch":
        sw.fetch(conn, 1.0, args.rate, None)          # the whole snapshot: the read half is already stored
        load_btc_daily(conn)
    elif args.cmd == "stability":
        print(json.dumps(stability(conn)))
    elif args.cmd == "status":
        _, info = wallets_all(conn)
        print(json.dumps({**info, "leaderboard_sha256": meta.get("leaderboard_sha256")}))
    elif args.cmd == "counts":
        ws, _ = wallets_all(conn)
        print(json.dumps(counts(ws), indent=1))
    else:
        ws, info = wallets_all(conn)
        if any(info[h]["missing"] for h in HALVES):
            print(f"not ready: {json.dumps(info)}", file=sys.stderr)
            return 1
        res = analyse(ws, sw.btc_up(conn), load_btc_daily(conn))
        res["data"] = {**info, "leaderboard_sha256": meta.get("leaderboard_sha256")}
        text = json.dumps(res, indent=1, default=str)
        if args.out:
            args.out.write_text(text)
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
