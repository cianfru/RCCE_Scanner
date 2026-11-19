"""
Ranking the long signals when many fire at once (docs/reviews/ranking-study.md).

On days when a quarter or more of a coin set carries a long signal, the long-signal coins are ranked by each
declared score, and the top third's return over the next 10 and 20 days is compared with the bottom third's.

Scores (closes up to the decision bar only):
    P      the scanner's priority score from the fields the replay records (signal tier, conditions met, distance
           from the weekly band, heat headroom); the parts it cannot see (floor, momentum, CVD, volume) are left out
    RS14   coin log return over 14 days minus the market's
    RS30   the same over 30 days
    RR14   coin log return over 14 days minus beta times the market's (beta of 4H log returns over the prior 90 days)
    RR30   the same over 30 days
The market is the set's median coin: each 4H bar, the median log return of the coins with a price at both closes.

    python -m backtest.ranking_study --rows <name>.rows.pkl [...] --out <result.json>      (from backend/)
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

BAR_MS = 4 * 3600 * 1000
DAY_MS = 86_400_000
LONG = {"STRONG_LONG", "LIGHT_LONG", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}
CROWDED_SHARE = 0.25           # a day is crowded when this share of the set's coins (or more) carries a long signal
MIN_LONGS = 3                  # and at least this many coins do, so each third holds a coin
HORIZONS = (10, 20)            # days
BETA_DAYS, BETA_MIN_DAYS = 90, 45
SCORES = ("P", "RS14", "RR14", "RS30", "RR30")
TIER = {"STRONG_LONG": 40, "LIGHT_LONG": 30, "REVIVAL_SEED_CONFIRMED": 20, "REVIVAL_SEED": 18}

# The bar (fixed in the declaration): every condition on every coin set, windows 1-9.
MIN_SPREAD_10D = 2.0           # median top-minus-bottom spread at 10 days, percentage points


def priority_recorded(r: dict) -> float:
    """The scanner's priority score (scanner._compute_priority) from the replay's recorded fields only."""
    s = TIER.get(r.get("signal"), 0)
    s += (r.get("conditions_met") or 0) / max(r.get("conditions_total") or 10, 1) * 20
    dev = max(-50.0, min(50.0, r.get("deviation_pct") if r.get("deviation_pct") is not None else -50.0))
    s += (dev + 50) / 100 * 10
    s += (100 - min(r.get("heat") if r.get("heat") is not None else 50, 100)) / 100 * 5
    return s


def prepare(rows: List[dict]):
    """Per-symbol price by bar time, the bar times, the market's cumulative log return by bar time (its per-bar
    return under the key ("r", t)), and the rows by bar time."""
    px: Dict[str, Dict[int, float]] = defaultdict(dict)
    by_t: Dict[int, List[dict]] = defaultdict(list)
    for r in rows:
        t = int(r["timestamp"])
        if r.get("price") and r["price"] > 0:
            px[r["symbol"]][t] = float(r["price"])
        by_t[t].append(r)
    times = sorted(by_t)
    mkt = {}
    level = 0.0
    for i, t in enumerate(times):
        if i:
            prev = times[i - 1]
            rets = [math.log(p[t] / p[prev]) for p in px.values() if t in p and prev in p]
            step = float(np.median(rets)) if rets else 0.0
            level += step
            mkt[("r", t)] = step
        mkt[t] = level
    return px, times, mkt, by_t


def coin_returns(p: Dict[int, float], times: List[int], end_idx: int, n: int) -> List[Tuple[int, float]]:
    """(bar time, 4H log return) for the last n bars ending at times[end_idx], where both closes exist."""
    out = []
    for i in range(max(1, end_idx - n + 1), end_idx + 1):
        a, b = times[i - 1], times[i]
        if a in p and b in p:
            out.append((b, math.log(p[b] / p[a])))
    return out


def beta(p: Dict[int, float], mkt: Dict[int, float], times: List[int], end_idx: int) -> Optional[float]:
    """Beta of the coin's 4H log returns to the market's over the prior BETA_DAYS (None with under BETA_MIN_DAYS)."""
    n = BETA_DAYS * 6
    rs = coin_returns(p, times, end_idx, n)
    if len(rs) < BETA_MIN_DAYS * 6:
        return None
    c = np.array([r for _, r in rs])
    m = np.array([mkt[("r", t)] for t, _ in rs])
    v = m.var(ddof=1)
    return float(np.cov(c, m)[0, 1] / v) if v > 0 else None


def score(name: str, r: dict, p: Dict[int, float], mkt: Dict[int, float], times: List[int], i: int) -> Optional[float]:
    """One declared score for one coin at bar times[i]; None when its history is too short."""
    if name == "P":
        return priority_recorded(r)
    days = 14 if name.endswith("14") else 30
    t, t0 = times[i], times[i] - days * DAY_MS
    if t not in p or t0 not in p or t0 not in mkt:
        return None
    cr, mr = math.log(p[t] / p[t0]), mkt[t] - mkt[t0]
    if name.startswith("RS"):
        return cr - mr
    b = beta(p, mkt, times, i)
    return None if b is None else cr - b * mr


def forward(p: Dict[int, float], t: int, days: int) -> Optional[float]:
    """Simple return in percent from bar t to the bar `days` later (None when the coin has no price there)."""
    t1 = t + days * DAY_MS
    return 100 * (p[t1] / p[t] - 1) if t in p and t1 in p else None


def crowded_days(by_t: Dict[int, List[dict]], times: List[int], start_ms: float, end_ms: float):
    """The daily (00:00 UTC) bars in [start, end) with at least CROWDED_SHARE of the set's coins and at least
    MIN_LONGS coins carrying a long signal: (index, bar time, long rows)."""
    out = []
    for i, t in enumerate(times):
        if t % DAY_MS or not (start_ms <= t < end_ms):
            continue
        rs = by_t[t]
        longs = [r for r in rs if r.get("signal") in LONG]
        if len(longs) >= MIN_LONGS and len(longs) >= CROWDED_SHARE * len(rs):
            out.append((i, t, longs))
    return out


def day_spread(longs: List[dict], scores: Dict[str, float], fwd: Dict[str, float]) -> Optional[float]:
    """Top third minus bottom third (by score) of the mean forward return, among the long coins with both a score
    and a forward return. None with fewer than MIN_LONGS such coins. Ties keep alphabetical order."""
    have = sorted((s for s in (r["symbol"] for r in longs) if scores.get(s) is not None and fwd.get(s) is not None))
    if len(have) < MIN_LONGS:
        return None
    ranked = sorted(have, key=lambda s: -scores[s])
    k = max(1, len(ranked) // 3)
    return float(np.mean([fwd[s] for s in ranked[:k]]) - np.mean([fwd[s] for s in ranked[-k:]]))


def run(rows: List[dict], wins: List[dict]) -> dict:
    """Per score and horizon: each crowded day's spread with its window index."""
    px, times, mkt, by_t = prepare(rows)
    out = {name: {h: [] for h in HORIZONS} for name in SCORES}
    counts = defaultdict(int)
    for w in wins:
        for i, t, longs in crowded_days(by_t, times, w["start_ms"], w["end_ms"]):
            counts[w["index"]] += 1
            fwd = {h: {r["symbol"]: forward(px[r["symbol"]], t, h) for r in longs} for h in HORIZONS}
            for name in SCORES:
                sc = {r["symbol"]: score(name, r, px[r["symbol"]], mkt, times, i) for r in longs}
                for h in HORIZONS:
                    d = day_spread(longs, sc, fwd[h])
                    if d is not None:
                        out[name][h].append((w["index"], t, d))
    return {"spreads": out, "crowded_days": dict(counts)}


def summary(spreads: List[Tuple[int, int, float]], halves=((1, 5), (6, 9))) -> dict:
    v = np.array([d for _, _, d in spreads])
    half = [np.array([d for w, _, d in spreads if a <= w <= b]) for a, b in halves]
    return {"days": int(len(v)), "median": float(np.median(v)) if len(v) else None,
            "mean": float(v.mean()) if len(v) else None, "share_positive": float((v > 0).mean()) if len(v) else None,
            "median_halves": [float(np.median(x)) if len(x) else None for x in half]}


def verdict(per_set: Dict[str, Dict[str, dict]]) -> Dict[str, dict]:
    """The declared bar for each score other than P, on every coin set:
    1. median 10-day spread at least MIN_SPREAD_10D points;
    2. median 10-day spread above 0 in both halves (windows 1-5 and 6-9);
    3. median 10-day spread above P's;
    4. median 20-day spread above 0."""
    out = {}
    for name in SCORES[1:]:
        checks = []
        for s, res in per_set.items():
            a, p, a20 = res[name]["10"], res["P"]["10"], res[name]["20"]
            ok = (a["median"] is not None and a["median"] >= MIN_SPREAD_10D
                  and all(x is not None and x > 0 for x in a["median_halves"])
                  and p["median"] is not None and a["median"] > p["median"]
                  and a20["median"] is not None and a20["median"] > 0)
            checks.append((s, ok))
        out[name] = {"passes": all(ok for _, ok in checks), "per_set": dict(checks),
                     "mean_median_10d": float(np.mean([per_set[s][name]["10"]["median"] for s in per_set]))}
    return out


def main(argv=None):
    import argparse
    import json
    import pickle
    from pathlib import Path
    from backtest.larsson_study import HOLDOUT, windows
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--window10", action="store_true", help="also read <name>.holdout.rows.pkl and report window 10")
    args = ap.parse_args(argv)
    wins = [w for w in windows() if w["index"] < HOLDOUT]
    per_set, extra = {}, {}
    for path in args.rows:
        name = Path(path).name.replace(".rows.pkl", "")
        rows = pickle.loads(Path(path).read_bytes())
        res = run(rows, wins)
        per_set[name] = {s: {str(h): summary(res["spreads"][s][h]) for h in HORIZONS} for s in SCORES}
        per_set[name]["_crowded_days"] = res["crowded_days"]
        hold_path = Path(path.replace(".rows.pkl", ".holdout.rows.pkl"))
        if args.window10 and not hold_path.exists():
            extra[name] = None                       # captured before the holdout rows were saved
        elif args.window10:
            hold = pickle.loads(hold_path.read_bytes())
            r10 = run(rows + hold, [w for w in windows() if w["index"] == HOLDOUT])
            extra[name] = {s: {str(h): summary(r10["spreads"][s][h], halves=()) for h in HORIZONS} for s in SCORES}
    clean = {s: {k: v for k, v in res.items() if not k.startswith("_")} for s, res in per_set.items()}
    v = verdict(clean)
    Path(args.out).write_text(json.dumps({"per_set": per_set, "window10": extra, "verdict": v}, indent=1))
    for s, res in per_set.items():
        print(s, "crowded days by window:", res["_crowded_days"])
        for name in SCORES:
            a, b = res[name]["10"], res[name]["20"]
            print(f"  {name:5} 10d median {a['median']:+6.2f} (halves {a['median_halves'][0]:+.2f}, {a['median_halves'][1]:+.2f}; "
                  f"positive {100 * a['share_positive']:.0f}%, {a['days']} days)   20d median {b['median']:+6.2f}")
    for name, x in v.items():
        print(name, "PASSES" if x["passes"] else "fails", x["per_set"], f"mean median 10d {x['mean_median_10d']:+.2f}")


if __name__ == "__main__":
    main()
