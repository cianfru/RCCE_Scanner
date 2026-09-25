"""
Early entry on a pending regime change: does entering at square k of 5 pay?

    python -m backtest.transition_study --tf 1d --out transitions_1d      (from backend/)

At every closed candle the live engine (compute_rcce) runs on the trailing 600-bar
window, exactly as the scanner does, and reports the regime and any pending change
(the squares in the grid). Studied: pending changes *into* MARKUP (Uptrend) from
ACCUM or REACC. For each episode and each square k = 1..4, and for the
confirmation bar itself, entry is at the next candle's open; the return is measured
to the close H candles later, with 10 bps per side. Also reported: how often an
episode reaches confirmation, and the price move between square k and confirmation
(the cost of waiting). Windows 1-9 only (data ends 2026-03-29); holdout untouched.
"""
from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from backtest import binance_history as bh
from backtest.larsson_scenarios import universe
from backtest.larsson_study import RUNS_DIR

WINDOW = 600
END = "2026-03-29"
COST = 2 * 0.0010
HORIZONS = {"1d": (10, 20), "4h": (30, 60)}   # ~2 and ~4 weeks on 1d; 5 and 10 days on 4h


def _series(sym: str, tf: str):
    d = bh.load(f"{sym}USDT", tf, "2020-01-01" if tf == "1d" else "2021-01-01", END)
    if d is None or len(d["close"]) < WINDOW + 50:
        return None
    from engines.rcce_engine import compute_rcce
    out = []
    for i in range(WINDOW, len(d["close"])):
        w = {k: v[i - WINDOW:i] for k, v in d.items()}   # candles [i-600, i): bar i-1 is the last closed
        r = compute_rcce(w)
        t = r.get("regime_transition") or {}
        out.append((i - 1, r.get("regime"), t.get("candidate"), t.get("observed_bars", 0)))
    return {"open": d["open"], "close": d["close"], "rows": out}


def _episodes(s):
    """Episodes of a pending MARKUP from ACCUM/REACC: the bar index of each square
    k and of the confirmation bar (None if the change was abandoned)."""
    eps, cur = [], None
    rows = s["rows"]
    for j, (i, regime, cand, k) in enumerate(rows):
        pending = cand == "MARKUP" and regime in ("ACCUM", "REACC") and k >= 1
        if pending:
            if cur is not None and k <= max(cur["squares"]):    # count restarted: a new episode
                eps.append(cur)
                cur = None
            if cur is None:
                cur = {"squares": {}, "confirm": None, "from": regime}
            cur["squares"].setdefault(k, i)
            continue
        if cur is not None:
            if regime == "MARKUP":
                cur["confirm"] = i
            eps.append(cur)
            cur = None
    if cur is not None:
        eps.append(cur)
    return eps


def _ret(s, i, h):
    """Enter at the open after bar i, exit at the close h bars later, net of costs."""
    o, c = s["open"], s["close"]
    if i + 1 + h >= len(c):
        return None
    return c[i + 1 + h] / o[i + 1] - 1 - COST


def _worker(args):
    sym, tf = args
    s = _series(sym, tf)
    if s is None:
        return sym, None
    eps = _episodes(s)
    h1, h2 = HORIZONS[tf]
    rows = []
    for e in eps:
        for k, i in e["squares"].items():
            rows.append(dict(sym=sym, point=f"square {k}", confirmed=e["confirm"] is not None,
                             r1=_ret(s, i, h1), r2=_ret(s, i, h2),
                             wait=(s["close"][e["confirm"]] / s["close"][i] - 1) if e["confirm"] is not None else None))
        if e["confirm"] is not None:
            rows.append(dict(sym=sym, point="confirmed", confirmed=True,
                             r1=_ret(s, e["confirm"], h1), r2=_ret(s, e["confirm"], h2), wait=0.0))
    # Baseline: every bar in ACCUM/REACC, and every bar in MARKUP.
    base = {"ACCUM/REACC any bar": [], "MARKUP any bar": []}
    for i, regime, _, _ in s["rows"]:
        key = "MARKUP any bar" if regime == "MARKUP" else "ACCUM/REACC any bar" if regime in ("ACCUM", "REACC") else None
        if key:
            base[key].append(_ret(s, i, h2))
    return sym, {"rows": rows, "base": base, "episodes": len(eps),
                 "confirmed": sum(e["confirm"] is not None for e in eps)}


def summarise(results, tf):
    h1, h2 = HORIZONS[tf]
    rows = [r for res in results.values() if res for r in res["rows"]]
    table = {}
    for point in [f"square {k}" for k in range(1, 5)] + ["confirmed"]:
        rs = [r for r in rows if r["point"] == point]
        r1 = [r["r1"] for r in rs if r["r1"] is not None]
        r2 = [r["r2"] for r in rs if r["r2"] is not None]
        waits = [r["wait"] for r in rs if r["wait"] is not None and point != "confirmed"]
        table[point] = {
            "n": len(rs),
            "reaches_confirmation_pct": 100 * sum(r["confirmed"] for r in rs) / len(rs) if rs else None,
            f"mean_{h1}": 100 * statistics.mean(r1) if r1 else None,
            f"mean_{h2}": 100 * statistics.mean(r2) if r2 else None,
            f"median_{h2}": 100 * statistics.median(r2) if r2 else None,
            f"win_{h2}": 100 * sum(x > 0 for x in r2) / len(r2) if r2 else None,
            "move_until_confirmation_median": 100 * statistics.median(waits) if waits else None,
        }
    for key in ("ACCUM/REACC any bar", "MARKUP any bar"):
        b = [x for res in results.values() if res for x in res["base"][key] if x is not None]
        table[key] = {"n": len(b), f"mean_{h2}": 100 * statistics.mean(b), f"median_{h2}": 100 * statistics.median(b),
                      f"win_{h2}": 100 * sum(x > 0 for x in b) / len(b)}
    return table


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", choices=("1d", "4h"), default="1d")
    ap.add_argument("--universe", default="both", choices=("primary", "secondary", "both"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    syms = universe("primary") + (universe("secondary") if args.universe == "both" else []) \
        if args.universe != "secondary" else universe("secondary")
    with ProcessPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(_worker, [(s, args.tf) for s in syms]))
    table = summarise(results, args.tf)
    out = {"tf": args.tf, "coins": sum(1 for v in results.values() if v), "table": table,
           "episodes": sum(v["episodes"] for v in results.values() if v),
           "confirmed": sum(v["confirmed"] for v in results.values() if v)}
    (RUNS_DIR / f"{args.out}.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
