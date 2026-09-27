"""
Market timing and bearish signals as trades (docs/reviews/timing-and-exits-study.md).

    python -m backtest.timing_exits <primary.pkl> <secondary.pkl> --out <name>   (from backend/)

Part M holds a basket (or BTC) while the engine reads risk-on, cash otherwise. Part X
describes returns after Trim / Light short and runs short strategies on them. Windows 1-9,
fresh capital per window, 5 + 5 bps per side.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pickle
import statistics
from pathlib import Path

import numpy as np

from backtest.larsson_study import (
    HOLDOUT, INITIAL_CAPITAL, RUNS_DIR, _compute_bmsb_filter, _is_bmsb_blocked, _weekly_completed, metrics, windows,
)
from backtest.live_logic_check import _daily
from backtest.sizing_study import score as pm_score
from backtest.larsson_study import _costed_pm_class

COST = 0.001
ON_REGIMES_BTC = {"MARKUP", "REACC", "BLOWOFF"}
BREADTH_REGIMES = {"MARKUP", "REACC"}
LONG_ENTRIES = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED"}
SHORT_SIZE = {"STRONG": 0.30, "MODERATE": 0.25, "WEAK": 0.15, "CONFLICTING": 0.15, "UNKNOWN": 0.15}
HOLD_BARS, STOP = 42, 0.08
HORIZONS = {"1d": 6, "3d": 18, "7d": 42}


def wins():
    return [w for w in windows() if w["index"] < HOLDOUT]


def prepare(rows):
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["symbol"]][r["timestamp"]] = r
    stamps = sorted({r["timestamp"] for r in rows})
    return by, stamps


def summarize_window(curve, exposure, trades, w):
    return metrics(_daily(curve), exposure, trades, (w["end_ms"] - w["start_ms"]) / 86_400_000)


def pack(res, exposure_all=None, trades=None):
    return {"compounded_pct": (math.prod(1 + r["total_return_pct"] / 100 for r in res) - 1) * 100,
            "per_window_pct": [round(r["total_return_pct"], 2) for r in res],
            "worst_dd_pct": min(r["max_dd_pct"] for r in res),
            "median_sharpe": statistics.median(r["sharpe"] for r in res),
            **({"avg_exposure_pct": round(100 * float(np.mean(exposure_all)), 1)} if exposure_all else {}),
            **({"trades": trades} if trades is not None else {})}


# ------------------------------------------------------------------------------ Part M
def timing(by, stamps, btc, bmsb, rule, hold):
    """rule: 'T1' | 'T2' | 'BH'; hold: 'H1' (basket) | 'H2' (BTC)."""
    res, exp_all = [], []
    for w in wins():
        span = [t for t in stamps if w["start_ms"] <= t < w["end_ms"]]
        eq, inv, prev, curve, exposure = INITIAL_CAPITAL, False, None, [], []
        for t in span:
            if inv and prev is not None:
                if hold == "H1":
                    rets = [by[s][t]["price"] / by[s][prev]["price"] - 1 for s in by
                            if t in by[s] and prev in by[s] and by[s][prev]["price"] > 0]
                    r = sum(rets) / len(rets) if rets else 0.0
                else:
                    r = btc[t]["price"] / btc[prev]["price"] - 1 if t in btc and prev in btc else 0.0
                eq *= 1 + r
            if rule == "BH":
                on = True
            else:
                band = not _is_bmsb_blocked(bmsb[0], bmsb[1], t)
                if rule == "T1":
                    on = band and t in btc and btc[t].get("regime") in ON_REGIMES_BTC
                else:
                    regs = [by[s][t].get("regime") for s in by if t in by[s]]
                    on = band and bool(regs) and sum(g in BREADTH_REGIMES for g in regs) / len(regs) >= 0.5
            if on != inv:
                eq *= 1 - COST
                inv = on
            curve.append((t, eq))
            exposure.append(1.0 if inv else 0.0)
            prev = t
        if inv:
            eq *= 1 - COST
            curve[-1] = (curve[-1][0], eq)
        res.append(summarize_window(curve, exposure, [], w))
        exp_all += exposure
    return pack(res, exp_all)


# ------------------------------------------------------------------------------ Part X
def bearish_events(by, stamps, signal):
    idx = {t: i for i, t in enumerate(stamps)}
    avg = {}
    for h, n in HORIZONS.items():
        for i, t in enumerate(stamps[:-n]):
            t2 = stamps[i + n]
            rets = [by[s][t2]["price"] / by[s][t]["price"] - 1 for s in by if t in by[s] and t2 in by[s]]
            if rets:
                avg[(t, h)] = sum(rets) / len(rets)
    in_w = lambda t: any(w["start_ms"] <= t < w["end_ms"] for w in wins())
    out = collections.defaultdict(list)
    for s, bars in by.items():
        prev = None
        for t in sorted(bars):
            sig = bars[t]["signal"]
            if sig == signal and prev != signal and in_w(t):
                for h, n in HORIZONS.items():
                    i = idx[t]
                    if i + n < len(stamps) and stamps[i + n] in bars and (t, h) in avg:
                        raw = bars[stamps[i + n]]["price"] / bars[t]["price"] - 1
                        out[f"raw_{h}"].append(raw)
                        out[f"ex_{h}"].append(raw - avg[(t, h)])
            prev = sig
    summ = {"n": len(out.get("raw_7d", []))}
    for k, v in out.items():
        summ[k] = {"mean": round(100 * sum(v) / len(v), 2), "median": round(100 * statistics.median(v), 2),
                   "pos": round(100 * sum(x > 0 for x in v) / len(v), 1)}
    return summ


def shorts(by, stamps, signal):
    res, exp_all, n_trades, wins_n = [], [], 0, 0
    syms = sorted(by)
    for w in wins():
        slot = INITIAL_CAPITAL / len(syms)
        cash, pos, curve, exposure = INITIAL_CAPITAL, {}, [], []
        prev_sig = {}
        span = [t for t in stamps if w["start_ms"] <= t < w["end_ms"]]
        for t in span:
            for s in syms:
                b = by[s].get(t)
                if b is None:
                    continue
                p, sig = b["price"], b["signal"]
                if s in pos:
                    q = pos[s]
                    q["bars"] += 1
                    if p / q["entry"] - 1 >= STOP or sig in LONG_ENTRIES or q["bars"] >= HOLD_BARS:
                        pnl = q["alloc"] * (1 - p / q["entry"])
                        cash += q["alloc"] + pnl - q["alloc"] * COST
                        n_trades += 1
                        wins_n += pnl > 0
                        del pos[s]
                if sig == signal and prev_sig.get(s) != signal and s not in pos:
                    alloc = min(slot * SHORT_SIZE.get(b.get("confluence_label"), 0.15), cash)
                    if alloc > 0:
                        cash -= alloc + alloc * COST
                        pos[s] = {"entry": p, "alloc": alloc, "bars": 0}
                prev_sig[s] = sig
            open_val = sum(q["alloc"] * (2 - by[s][t]["price"] / q["entry"]) for s, q in pos.items() if t in by[s])
            eq = cash + open_val
            curve.append((t, eq))
            exposure.append(sum(q["alloc"] for q in pos.values()) / eq if eq > 0 else 0.0)
        for s, q in list(pos.items()):
            last = max(tt for tt in by[s] if tt <= span[-1])
            p = by[s][last]["price"]
            pnl = q["alloc"] * (1 - p / q["entry"])
            cash += q["alloc"] + pnl - q["alloc"] * COST
            n_trades += 1
            wins_n += pnl > 0
        curve[-1] = (curve[-1][0], cash)
        res.append(summarize_window(curve, exposure, [], w))
        exp_all += exposure
    out = pack(res, exp_all, n_trades)
    out["win_rate_pct"] = round(100 * wins_n / max(1, n_trades), 1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("primary")
    ap.add_argument("secondary")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    wk = _weekly_completed("BTC", windows()[HOLDOUT - 2]["end"])
    m = _compute_bmsb_filter(wk)
    bmsb = (m, sorted(m))
    prim_rows = pickle.loads(Path(args.primary).read_bytes())
    btc = {r["timestamp"]: r for r in prim_rows if r["symbol"] == "BTC/USDT"}
    out = {}
    for name, rows in (("primary", prim_rows), ("secondary", pickle.loads(Path(args.secondary).read_bytes()))):
        by, stamps = prepare(rows)
        res, _, exp = pm_score(rows, bmsb, _costed_pm_class())
        part_m = {"M0": pack(res, exp)}
        for rule in ("T1", "T2", "BH"):
            for hold in ("H1", "H2"):
                part_m[f"{'BH' if rule == 'BH' else 'M-' + rule}-{hold}"] = timing(by, stamps, btc, bmsb, rule, hold)
        part_x = {"trim_after": bearish_events(by, stamps, "TRIM"), "light_short_after": bearish_events(by, stamps, "LIGHT_SHORT"),
                  "X1_short_light_short": shorts(by, stamps, "LIGHT_SHORT"), "X2_short_trim": shorts(by, stamps, "TRIM")}
        out[name] = {"M": part_m, "X": part_x}
        for k, v in part_m.items():
            print(name, k, round(v["compounded_pct"], 1), round(v["worst_dd_pct"], 1), round(v["median_sharpe"], 2),
                  v.get("avg_exposure_pct"), flush=True)
        for k in ("X1_short_light_short", "X2_short_trim"):
            v = part_x[k]
            print(name, k, round(v["compounded_pct"], 1), round(v["worst_dd_pct"], 1), round(v["median_sharpe"], 2),
                  v["trades"], v["win_rate_pct"], flush=True)
        for k in ("trim_after", "light_short_after"):
            v = part_x[k]
            print(name, k, v["n"], "raw7d", v.get("raw_7d"), "ex7d", v.get("ex_7d"), "ex3d", v.get("ex_3d"), flush=True)
    (RUNS_DIR / f"{args.out}.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
