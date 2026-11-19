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
COMPARE = "seasoned"              # the comparison: everyone eligible whose first point is 180+ days old
STABILITY_N = 200
STABILITY_END = int(sw.T0 + sw.OUTCOME_D * DAY)   # 31 October 2026 00:00 UTC: the last outcome's end
STABLE_BEFORE = int(sw.T0 - 2 * DAY)              # 29 September 2026: before it, stored points are the weekly grid
STABILITY_MAX_DIFF = 0.05         # more than 5% of the re-read wallets differing before STABLE_BEFORE stops the run
SNAPSHOT_SHA256 = "31abadebc58cb61e7956e6be694b9425faac2ac612dc370c1bacd5d594871b1e"
BTC_STEP = 4 * 3600               # BTC 4h candles for the exposure context
# The selection window study's published hit rates on the read half (its 30-day arm and everyone eligible), newest
# date first: the code check that must match before the analysis runs.
PUBLISHED_TODAY = (18.0, 72.5, 43.5, 38.0, 58.0, 66.0, 51.5, 61.5, 25.5, 37.5, 58.0, 46.0)
PUBLISHED_BASELINE = (32.8, 63.2, 67.4, 38.3, 49.6, 60.5, 53.1, 51.3, 33.6, 55.2, 28.2, 26.3)
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
    """BTC closes {candle open (s): close} of candles ``step`` seconds long; the price at x is the close of the last
    candle ended at or before x."""

    def __init__(self, closes: Dict[int, float], step: int = DAY):
        self.days = sorted(closes)
        self.c = closes
        self.step = step

    def at(self, x: float) -> Optional[float]:
        import bisect
        i = bisect.bisect_right(self.days, x - self.step)
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


def _mean_diff(per_date: List[dict], rule: str, field: str) -> dict:
    d = [p[rule][field] - p[COMPARE][field] for p in per_date
         if p[rule][field] is not None and p[COMPARE][field] is not None]
    out = {"mean_pp": sum(d) / len(d) if d else None, "dates": len(d)}
    out["met"] = len(d) == len(per_date) and out["mean_pp"] > 0
    return out


def judge(per_date: List[dict], rule: str, btc_up: Optional[Sequence[Optional[bool]]]) -> dict:
    """The bar for one rule on one half, against COMPARE. ``per_date``: each date's metrics per arm, newest first.
    No verdict (not met) when the rule's list is empty on a date or the BTC record is missing."""
    hd = [p[rule]["hit"] - p[COMPARE]["hit"] if p[rule]["hit"] is not None and p[COMPARE]["hit"] is not None
          else None for p in per_date]
    if any(x is None for x in hd):
        return {"met": False, "missing_dates": sum(1 for x in hd if x is None)}
    v = core(hd)
    roi = _mean_diff(per_date, rule, "mean_roi_clipped")
    traded = _mean_diff(per_date, rule, "hit_active")
    if btc_up is None:
        side = {"met": False, "missing": "btc"}
    else:
        side = {k: x for k, x in sw.side_means(hd, btc_up).items() if k != "required"}
        side["met"] = bool(side["up_mean"] is not None and side["down_mean"] is not None
                           and side["up_mean"] > 0 and side["down_mean"] > 0)
    v.update(per_date_pp=hd, roi=roi, traded=traded, btc=side, lag1=sw.lag1(hd))
    v["met"] = v["met"] and roi["met"] and traded["met"] and side["met"]
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

REREAD = "reread"                # the read half read again, the same days as the unread half (Changes, 15 November)


def wallets_all(conn: sqlite3.Connection, fresh: bool = True) -> Tuple[List[sw.Wallet], dict]:
    """Every wallet of both halves. ``fresh``: the read half from its re-read (REREAD), so both halves come from
    replies of the same days; otherwise from the replies stored for the selection window study (the code check)."""
    conn.execute(f"CREATE TABLE IF NOT EXISTS {REREAD} (addr TEXT PRIMARY KEY, raw BLOB, fetched REAL)")
    lb = {a: {"av": av, "month_vlm": mv, "all_vlm": tv} for a, av, mv, tv in
          conn.execute("SELECT addr, av, month_vlm, all_vlm FROM leaderboard")}
    raws = {a: raw for a, raw in conn.execute("SELECT addr, raw FROM portfolio") if a in lb}
    if fresh:
        raws = {a: r for a, r in raws.items() if half_of(a) == "unread"}
        raws.update({a: r for a, r in conn.execute(f"SELECT addr, raw FROM {REREAD}") if a in lb and half_of(a) == "read"})
    ws = [sw.Wallet(a, json.loads(zlib.decompress(raw)), lb.get(a)) for a, raw in raws.items()]
    gone = {a for (a,) in conn.execute("SELECT addr FROM failures WHERE runs >= ?", (sw.MAX_RUNS,))}
    read = {w.addr for w in ws}
    info = {}
    for h in HALVES:
        listed = {a for a in lb if half_of(a) == h}
        info[h] = {"listed": len(listed), "read": len(read & listed), "left_out_unreadable": len(gone & listed),
                   "missing": len(listed - read - gone)}
    return ws, info


def reread(conn: sqlite3.Connection, rate: int = 1100, workers: int = 4) -> None:
    """Read the read half again into REREAD (resumable), at the same pace as the fetch."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    wallets_all(conn)
    done = {a for (a,) in conn.execute(f"SELECT addr FROM {REREAD}")}
    gone = {a for (a,) in conn.execute("SELECT addr FROM failures WHERE runs >= ?", (sw.MAX_RUNS,))}
    todo = [a for (a,) in conn.execute("SELECT addr FROM leaderboard ORDER BY skey, addr")
            if half_of(a) == "read" and a not in done and a not in gone]
    print(f"re-read: {len(done)} done, {len(todo)} to read", flush=True)
    lock = threading.Lock()
    state = {"next": time.time(), "gap": 60.0 * sw.WEIGHT / rate, "n": 0}

    def one(a):
        for attempt in range(8):
            with lock:
                at = max(time.time(), state["next"])
                state["next"] = at + state["gap"]
            time.sleep(max(0.0, at - time.time()))
            try:
                reply = sw._post({"type": "portfolio", "user": a})
            except Exception as exc:
                with lock:
                    if "429" in str(exc):
                        state["next"] = max(state["next"], time.time() + 20 * (attempt + 1))
                time.sleep(2 * (attempt + 1))
                continue
            if not sw.valid(reply):
                time.sleep(2 * (attempt + 1))
                continue
            with lock:
                conn.execute(f"INSERT OR REPLACE INTO {REREAD} VALUES (?,?,?)",
                             (a, zlib.compress(json.dumps(reply, separators=(",", ":")).encode()), time.time()))
                state["n"] += 1
                if state["n"] % 50 == 0:
                    conn.commit()
                if state["n"] % 1000 == 0:
                    print(f"re-read {state['n']}/{len(todo)}", flush=True)
            return
        print(f"re-read: {a} unreadable this run", flush=True)

    try:
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(one, todo))
    finally:
        with lock:
            conn.commit()
    print(f"re-read done: {state['n']} read", flush=True)


def load_btc_4h(conn: sqlite3.Connection) -> Optional[Btc]:
    """BTC 4h closes from May 2025 to 31 October 2026 (Hyperliquid), stored once; for the exposure context."""
    row = conn.execute("SELECT v FROM meta WHERE k = 'btc_4h_close'").fetchone()
    if not row:
        candles = sw._post({"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "4h",
                                                              "startTime": int(BTC_FROM) * 1000,
                                                              "endTime": (STABILITY_END + DAY) * 1000}})
        closes = {int(c["t"]) // 1000: float(c["c"]) for c in candles if int(c["t"]) // 1000 + BTC_STEP <= STABILITY_END + DAY}
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('btc_4h_close', ?)", (json.dumps(closes),))
        conn.commit()
        row = (json.dumps(closes),)
    closes = {int(k): v for k, v in json.loads(row[0]).items()}
    return Btc(closes, BTC_STEP) if closes else None


SERIES = (("allTime", "accountValueHistory"), ("allTime", "pnlHistory"),
          ("perpAllTime", "accountValueHistory"), ("perpAllTime", "pnlHistory"))


def compare_points(old_reply, new_reply, start: float = 0, end: float = STABLE_BEFORE) -> dict:
    """Points with start <= time < end (s) in the all-time and perps-only account value and PnL series: the same in
    both replies?"""
    def pts(reply, part, key):
        d = dict(reply) if isinstance(reply, list) else {}
        return {(int(p[0]), str(p[1])) for p in ((d.get(part) or {}).get(key) or [])
                if start * 1000 <= int(p[0]) < end * 1000}
    out = {"old_points": 0, "new_points": 0, "differing": 0}
    for part, key in SERIES:
        a, b = pts(old_reply, part, key), pts(new_reply, part, key)
        out["old_points"] += len(a)
        out["new_points"] += len(b)
        out["differing"] += len(a ^ b)
    out["same"] = out["differing"] == 0
    return out


def readings(w: sw.Wallet) -> list:
    """What the study reads of a wallet at each date, outcomes excepted: the base rules, the comparison group and
    each rule's rank key."""
    return [(sw.eligible_base(w, t), old_enough(w, t), *[score(r, w, t) for r in CANDIDATES]) for t in sw.dates()]


def stability(conn: sqlite3.Connection, n: int = STABILITY_N) -> dict:
    """Re-read n wallets of the read half (lowest skey, then address). Points before STABLE_BEFORE must be identical;
    later points up to 31 October are counted, and so are wallets whose readings (no outcome) change."""
    conn.execute("CREATE TABLE IF NOT EXISTS stability (addr TEXT PRIMARY KEY, raw BLOB, fetched REAL)")
    lb = {a: {"av": av, "month_vlm": mv, "all_vlm": tv} for a, av, mv, tv in
          conn.execute("SELECT addr, av, month_vlm, all_vlm FROM leaderboard")}
    rows = sorted((sw.skey(a), a, raw) for a, raw in conn.execute("SELECT addr, raw FROM portfolio")
                  if half_of(a) == "read")[:n]
    res = []
    for _, a, raw in rows:
        got = conn.execute("SELECT raw FROM stability WHERE addr = ?", (a,)).fetchone()
        if got:
            new = json.loads(zlib.decompress(got[0]))
        else:
            new = None
            for attempt in range(8):
                time.sleep(60.0 * sw.WEIGHT / 1000)
                try:
                    reply = sw._post({"type": "portfolio", "user": a})
                except Exception:
                    time.sleep(10 * (attempt + 1))
                    continue
                if sw.valid(reply):
                    new = reply
                    break
            if new is None:
                raise RuntimeError(f"stability: {a} unreadable; run again")
            conn.execute("INSERT OR REPLACE INTO stability VALUES (?,?,?)",
                         (a, zlib.compress(json.dumps(new, separators=(",", ":")).encode()), time.time()))
            conn.commit()
        old = json.loads(zlib.decompress(raw))
        before = compare_points(old, new)
        after = compare_points(old, new, STABLE_BEFORE, STABILITY_END)
        wo, wn = sw.Wallet(a, old, lb.get(a)), sw.Wallet(a, new, lb.get(a))
        ro = readings(wo)
        res.append({"before": before["same"], "after": after["same"], "readings": ro == readings(wn),
                    "eligible": any(r[0] for r in ro)})
    elig = [r for r in res if r["eligible"]]
    out = {"compared": len(res), "same_before": sum(r["before"] for r in res),
           "same_after": sum(r["after"] for r in res), "same_readings": sum(r["readings"] for r in res),
           "eligible_on_a_date": len(elig), "eligible_same_before": sum(r["before"] for r in elig),
           "eligible_same_readings": sum(r["readings"] for r in elig)}
    out["ok"] = len(res) == n and (len(res) - out["same_before"]) <= STABILITY_MAX_DIFF * n
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('cohort_stability', ?)", (json.dumps(out),))
    conn.commit()
    return out


def reproduce(conn: sqlite3.Connection) -> dict:
    """Today's list and everyone eligible on the read half, against the selection window study's published hit rates
    (nothing new is computed: both were published). Recorded in meta; the analysis needs it to match."""
    ws, _ = wallets_all(conn, fresh=False)
    ws = [w for w in ws if half_of(w.addr) == "read"]
    by = {w.addr: w for w in ws}
    today, base = [], []
    for t in sw.dates():
        tl = [a for _, a in sw.ranked(ws, t, 30)[:K]]
        bl = [w.addr for w in ws if sw.eligible_base(w, t)]
        today.append(round(sw.metrics([sw._outcome(by[a], t) for a in tl])["hit"], 1))
        base.append(round(sw.metrics([sw._outcome(by[a], t) for a in bl])["hit"], 1))
    out = {"today": today, "baseline": base,
           "ok": tuple(today) == PUBLISHED_TODAY and tuple(base) == PUBLISHED_BASELINE}
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('cohort_reproduce', ?)", (json.dumps(out),))
    conn.commit()
    return out


def ready(conn: sqlite3.Connection) -> List[str]:
    """What still stops the analysis: the snapshot, the stability check, the code check, unread wallets."""
    meta = dict(conn.execute("SELECT k, v FROM meta"))
    why = []
    if meta.get("leaderboard_sha256") != SNAPSHOT_SHA256:
        why.append("leaderboard snapshot is not the declared one")
    if "compared" not in json.loads(meta.get("cohort_stability") or "{}"):
        why.append("stability check missing")
    if not json.loads(meta.get("cohort_reproduce") or "{}").get("ok"):
        why.append("today's list does not reproduce the published hit rates")
    _, info = wallets_all(conn)
    if any(info[h]["missing"] for h in HALVES):
        why.append(f"wallets still to read: {info}")
    return why


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("fetch", "reread", "stability", "reproduce", "status", "counts", "analyse"))
    ap.add_argument("--db", type=Path, default=sw.DEFAULT_DB)
    ap.add_argument("--rate", type=int, default=1100, help="weight per minute (Hyperliquid allows 1,200 per IP)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    conn = sw.connect(args.db)
    meta = dict(conn.execute("SELECT k, v FROM meta"))
    if args.cmd in ("fetch", "reread", "stability", "reproduce") and meta.get("leaderboard_sha256") != SNAPSHOT_SHA256:
        print("the database does not hold the declared leaderboard snapshot", file=sys.stderr)
        return 1
    if args.cmd == "fetch":
        sw.fetch(conn, 1.0, args.rate, None)          # the whole snapshot: the read half is already stored
        load_btc_4h(conn)
    elif args.cmd == "reread":
        reread(conn, args.rate)
    elif args.cmd == "stability":
        print(json.dumps(stability(conn)))
    elif args.cmd == "reproduce":
        print(json.dumps(reproduce(conn)))
    elif args.cmd == "status":
        _, info = wallets_all(conn)
        print(json.dumps({**info, "leaderboard_sha256": meta.get("leaderboard_sha256")}))
    elif args.cmd == "counts":
        ws, _ = wallets_all(conn)
        print(json.dumps(counts(ws), indent=1))
    else:
        why = ready(conn)
        if why:
            print("not ready: " + "; ".join(why), file=sys.stderr)
            return 1
        ws, info = wallets_all(conn)
        res = analyse(ws, sw.btc_up(conn), load_btc_4h(conn))
        res["data"] = {**info, "leaderboard_sha256": meta.get("leaderboard_sha256")}
        text = json.dumps(res, indent=1, default=str)
        if args.out:
            args.out.write_text(text)
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
