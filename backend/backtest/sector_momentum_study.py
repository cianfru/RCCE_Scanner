"""
Sector momentum: does a group that beat BTC recently keep beating it?

    python -m backtest.sector_momentum_study --out sector_momentum      (from backend/)

Declared in docs/reviews/sector-momentum-study.md before running. Daily Binance
closes 2021-01-01 to 2026-03-29 (windows 1-9); the holdout is not touched.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np

from backtest import binance_history as bh
from backtest.larsson_study import HOLDOUT, RUNS_DIR, windows
from sectors import _S

START, END = "2021-01-01", "2026-03-29"
H = 10
LOOKBACKS = (7, 30)
MIN_MEMBERS = 3


def _pair(coin: str) -> str:
    base = coin[1:] if coin.startswith("k") and coin[1:].isupper() else coin
    return f"{base.upper()}USDT"


def _load(coin):
    try:
        d = bh.load(_pair(coin), "1d", START, END)
    except Exception:
        d = None
    if d is None or len(d["close"]) < 60:
        return coin, None
    return coin, {int(t) // 86_400_000: float(c) for t, c in zip(d["timestamp"], d["close"]) if c > 0}


def _spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _pct_mean(xs):
    xs = [x for x in xs if x is not None]
    return round(100 * statistics.mean(xs), 2) if xs else None


def _pct_median(xs):
    xs = [x for x in xs if x is not None]
    return round(100 * statistics.median(xs), 2) if xs else None


def _pos(xs):
    xs = [x for x in xs if x is not None]
    return round(100 * sum(x > 0 for x in xs) / len(xs)) if xs else None


def _tstat(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 3 or statistics.pstdev(xs) == 0:
        return None
    return statistics.mean(xs) / (statistics.stdev(xs) / math.sqrt(len(xs)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    # Aliases (FART, VIRT, PEPE, RNDR...) point at the same coins; keep one ticker each.
    coins, seen = [], set()
    for coin, (sector, eco) in _S.items():
        pair = _pair(coin)
        if coin != "BTC" and pair not in seen:
            seen.add(pair)
            coins.append((coin, sector, eco))
    with ThreadPoolExecutor(max_workers=8) as pool:
        prices = dict(pool.map(_load, [c for c, _, _ in coins]))
    btc = _load("BTC")[1]
    days = sorted(d for d in btc)
    loaded = [(c, s, e) for c, s, e in coins if prices.get(c)]

    def logret(series, d):
        a, b = series.get(d - 1), series.get(d)
        return math.log(b / a) if a and b else None

    groups = {}
    for c, s, e in loaded:
        groups.setdefault(("sector", s), []).append(c)
        if e:
            groups.setdefault(("ecosystem", e), []).append(c)

    # Daily relative (to BTC) median log return per group; None when < MIN_MEMBERS.
    btc_r = {d: logret(btc, d) for d in days}
    rel = {}
    for g, members in groups.items():
        series = {}
        for d in days:
            xs = [x for x in (logret(prices[c], d) for c in members) if x is not None]
            series[d] = (statistics.median(xs) - btc_r[d]) if len(xs) >= MIN_MEMBERS and btc_r[d] is not None else None
        rel[g] = series

    def basket_vs_btc(members, t):
        """Equal-weight basket simple return over (t, t+H] minus BTC's: what a trade would earn."""
        rs = [prices[c][t + H] / prices[c][t] - 1 for c in members if prices[c].get(t) and prices[c].get(t + H)]
        if len(rs) < MIN_MEMBERS or not (btc.get(t) and btc.get(t + H)):
            return None
        return statistics.mean(rs) - (btc[t + H] / btc[t] - 1)

    def window_sum(series, d0, d1):
        xs = [series.get(d) for d in range(d0, d1 + 1)]
        return sum(xs) if all(x is not None for x in xs) else None

    wins = [w for w in windows() if w["index"] < HOLDOUT]
    to_day = lambda s: int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()) // 86_400

    out = {"coins_loaded": len(loaded), "coins_listed": len(coins),
           "groups": {f"{k}:{n}": len(m) for (k, n), m in groups.items()}, "results": {}}
    for kind in ("sector", "ecosystem"):
        keys = [g for g in rel if g[0] == kind]
        for L in LOOKBACKS:
            steps = []
            for t in range(days[0] + L, days[-1] - H, H):   # non-overlapping 10-day outcomes
                past, fut, basket = [], [], []
                for g in keys:
                    p, f = window_sum(rel[g], t - L + 1, t), window_sum(rel[g], t + 1, t + H)
                    if p is not None and f is not None:
                        past.append(p)
                        fut.append(f)
                        basket.append(basket_vs_btc(groups[g], t))
                if len(past) < 4:
                    continue
                i_hi, i_lo = int(np.argmax(past)), int(np.argmin(past))
                steps.append({"day": t, "n": len(past), "ic": _spearman(past, fut),
                              "spread": fut[i_hi] - fut[i_lo], "leader": fut[i_hi],
                              "all_mean": statistics.mean(fut),
                              "b_leader": basket[i_hi], "b_spread": (basket[i_hi] - basket[i_lo]) if None not in (basket[i_hi], basket[i_lo]) else None,
                              "b_all": statistics.mean([b for b in basket if b is not None]) if any(b is not None for b in basket) else None})
            ics = [s["ic"] for s in steps if s["ic"] is not None]
            spreads = [s["spread"] for s in steps]
            leaders = [s["leader"] for s in steps]
            per_window = {}
            for w in wins:
                a, b = to_day(w["start"]), to_day(w["end"])
                sp = [s["spread"] for s in steps if a <= s["day"] < b]
                per_window[w["index"]] = round(100 * statistics.mean(sp), 2) if sp else None
            pos_windows = sum(1 for v in per_window.values() if v is not None and v > 0)
            res = {
                "steps": len(steps), "groups_per_step": round(statistics.mean(s["n"] for s in steps), 1) if steps else 0,
                "mean_ic": round(statistics.mean(ics), 3) if ics else None, "ic_t": round(_tstat(ics) or 0, 2),
                "spread_mean_pct": round(100 * statistics.mean(spreads), 2) if spreads else None,
                "spread_pos_pct": round(100 * sum(x > 0 for x in spreads) / len(spreads)) if spreads else None,
                "spread_t": round(_tstat(spreads) or 0, 2),
                "leader_vs_btc_mean_pct": round(100 * statistics.mean(leaders), 2) if leaders else None,
                "leader_vs_btc_pos_pct": round(100 * sum(x > 0 for x in leaders) / len(leaders)) if leaders else None,
                "avg_group_vs_btc_pct": round(100 * statistics.mean(s["all_mean"] for s in steps), 2) if steps else None,
                "spread_by_window_pct": per_window, "windows_positive": pos_windows,
                # Robustness: equal-weight baskets, simple returns (what a trade would earn, before costs).
                "basket_leader_vs_btc_mean_pct": _pct_mean([s["b_leader"] for s in steps]),
                "basket_leader_vs_btc_median_pct": _pct_median([s["b_leader"] for s in steps]),
                "basket_leader_vs_btc_pos_pct": _pos([s["b_leader"] for s in steps]),
                "basket_spread_mean_pct": _pct_mean([s["b_spread"] for s in steps]),
                "basket_spread_pos_pct": _pos([s["b_spread"] for s in steps]),
                "basket_avg_group_vs_btc_pct": _pct_mean([s["b_all"] for s in steps]),
            }
            res["passes"] = bool(res["mean_ic"] and res["mean_ic"] > 0 and res["ic_t"] >= 2
                                 and res["spread_mean_pct"] and res["spread_mean_pct"] > 0 and res["spread_t"] >= 2
                                 and pos_windows >= 6)
            out["results"][f"{kind}_L{L}"] = res
    (RUNS_DIR / f"{args.out}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["results"], indent=1))
    print("coins", out["coins_loaded"], "of", out["coins_listed"])


if __name__ == "__main__":
    main()
