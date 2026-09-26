"""
Entry quality study (docs/reviews/entry-quality-study.md).

    python -m backtest.entry_quality <primary.pkl> <secondary.pkl> --out <name>   (from backend/)

Stage A describes forward returns after each fresh long entry (raw and excess over the
set's equal-weight average) by several splits; Stage B picks a signal x regime blacklist on
the primary set by the declared rule and scores E0 / E1 / E2 on both sets.
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

import backtest.position_manager as pm_mod
from backtest.larsson_study import (
    HOLDOUT, RUNS_DIR, _compute_bmsb_filter, _costed_pm_class, _is_bmsb_blocked, _weekly_completed, windows,
)
from backtest.sizing_study import score

LONGS = ("STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED")
HORIZONS = {"1d": 6, "3d": 18, "7d": 42}
MIN_CELL = 30
EXEC_ACCUMULATE = {"STRONG": 0.25, "MODERATE": 0.25, "WEAK": 0.15, "CONFLICTING": 0.15, "UNKNOWN": 0.15}


def in_windows(t):
    return any(w["start_ms"] <= t < w["end_ms"] for w in windows() if w["index"] < HOLDOUT)


def entry_events(rows, bmsb):
    by_sym = collections.defaultdict(list)
    for r in rows:
        by_sym[r["symbol"]].append(r)
    price = {}
    for s, rs in by_sym.items():
        rs.sort(key=lambda r: r["timestamp"])
        price[s] = {r["timestamp"]: r["price"] for r in rs}
    stamps = sorted({r["timestamp"] for r in rows})
    idx = {t: i for i, t in enumerate(stamps)}
    # Set average forward return per (timestamp, horizon), over coins priced at both ends.
    avg = {}
    for h, n in HORIZONS.items():
        for i, t in enumerate(stamps[:-n] if n else stamps):
            t2 = stamps[i + n]
            rets = [p[t2] / p[t] - 1 for p in price.values() if t in p and t2 in p and p[t] > 0]
            if rets:
                avg[(t, h)] = sum(rets) / len(rets)
    events = []
    for s, rs in by_sym.items():
        prev = None
        for r in rs:
            sig = r["signal"]
            if sig in LONGS and sig != prev and in_windows(r["timestamp"]):
                t = r["timestamp"]
                e = {"symbol": s, "t": t, "signal": sig, "regime": r.get("regime"), "confluence": r.get("confluence_label"),
                     "checks": (r["conditions_met"] / r["conditions_total"]) if r.get("conditions_total") else None,
                     "heat": r.get("heat"), "z": r.get("zscore"), "band_block": _is_bmsb_blocked(bmsb[0], bmsb[1], t)}
                for h, n in HORIZONS.items():
                    i = idx[t]
                    if i + n < len(stamps) and stamps[i + n] in price[s] and (t, h) in avg:
                        raw = price[s][stamps[i + n]] / price[s][t] - 1
                        e[f"raw_{h}"], e[f"ex_{h}"] = raw, raw - avg[(t, h)]
                events.append(e)
            prev = sig
    return events


def bucket(e, key):
    v = e.get(key)
    if key == "checks":
        return None if v is None else ("<60%" if v < 0.6 else "60-80%" if v < 0.8 else ">=80%")
    if key == "heat":
        return None if v is None else ("<30" if v < 30 else "30-60" if v < 60 else ">=60")
    if key == "z":
        return None if v is None else ("<0" if v < 0 else "0-1" if v < 1 else "1-2" if v < 2 else ">=2")
    return v


def summarize(events, split):
    groups = collections.defaultdict(list)
    for e in events:
        k = split(e)
        if k is not None:
            groups[k].append(e)
    out = {}
    for k, es in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        row = {"n": len(es)}
        for h in HORIZONS:
            for kind in ("raw", "ex"):
                v = [e[f"{kind}_{h}"] for e in es if f"{kind}_{h}" in e]
                if v:
                    row[f"{kind}_{h}_mean"] = round(100 * sum(v) / len(v), 2)
                    row[f"{kind}_{h}_median"] = round(100 * statistics.median(v), 2)
                    row[f"{kind}_{h}_pos"] = round(100 * sum(x > 0 for x in v) / len(v), 1)
        out[" x ".join(k) if isinstance(k, tuple) else str(k)] = row
    return out


def stage_a(events):
    return {
        "signal": summarize(events, lambda e: e["signal"]),
        "signal_x_regime": summarize(events, lambda e: (e["signal"], str(e["regime"]))),
        "entry_checks": summarize(events, lambda e: bucket(e, "checks")),
        "confluence": summarize(events, lambda e: e["confluence"]),
        "heat": summarize(events, lambda e: bucket(e, "heat")),
        "zscore": summarize(events, lambda e: bucket(e, "z")),
        "btc_band_block": summarize(events, lambda e: "blocked" if e["band_block"] else "open"),
    }


def blacklist(events):
    cells = collections.defaultdict(list)
    for e in events:
        if "ex_7d" in e:
            cells[(e["signal"], str(e["regime"]))].append(e["ex_7d"])
    return sorted(k for k, v in cells.items()
                  if len(v) >= MIN_CELL and sum(v) / len(v) < 0 and statistics.median(v) < 0)


def make_pm(variant, black):
    Base = _costed_pm_class()

    class EntryPM(Base):
        def _open_position(self, sym, bar, confluence):
            if variant == "E1" and (bar.signal, str(bar.regime)) in black:
                return None
            return super()._open_position(sym, bar, confluence)

        def _add_to_position(self, sym, bar, confluence):
            if variant == "E1" and (bar.signal, str(bar.regime)) in black:
                return None
            return super()._add_to_position(sym, bar, confluence)

    return EntryPM


def run_variants(rows, bmsb, black):
    table = {}
    for v in ("E0", "E1", "E2"):
        sizing, signals = pm_mod._ENTRY_SIZING, pm_mod._ENTRY_SIGNALS
        if v == "E2":
            pm_mod._ENTRY_SIZING = {**sizing, "ACCUMULATE": EXEC_ACCUMULATE}
            pm_mod._ENTRY_SIGNALS = set(pm_mod._ENTRY_SIZING)
        try:
            res, trades, exp = score(rows, bmsb, make_pm(v, set(black)))
        finally:
            pm_mod._ENTRY_SIZING, pm_mod._ENTRY_SIGNALS = sizing, signals
        table[v] = {
            "compounded_pct": (math.prod(1 + r["total_return_pct"] / 100 for r in res) - 1) * 100,
            "per_window_pct": [round(r["total_return_pct"], 2) for r in res],
            "worst_dd_pct": min(r["max_dd_pct"] for r in res),
            "median_sharpe": statistics.median(r["sharpe"] for r in res),
            "avg_exposure_pct": round(100 * float(np.mean(exp)), 1),
            "trades": len(trades),
            "win_rate_pct": 100 * sum(t["pnl"] > 0 for t in trades) / max(1, len(trades)),
        }
    return table


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("primary")
    ap.add_argument("secondary")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    wk = _weekly_completed("BTC", windows()[HOLDOUT - 2]["end"])
    m = _compute_bmsb_filter(wk)
    bmsb = (m, sorted(m))
    out = {}
    black = None
    for name, path in (("primary", args.primary), ("secondary", args.secondary)):
        rows = pickle.loads(Path(path).read_bytes())
        ev = entry_events(rows, bmsb)
        if black is None:
            black = blacklist(ev)                  # chosen on the primary set only
        out[name] = {"entry_events": len(ev), "stage_a": stage_a(ev), "variants": run_variants(rows, bmsb, black)}
        print(name, len(ev), {k: (round(v["compounded_pct"], 1), round(v["worst_dd_pct"], 1), round(v["median_sharpe"], 2),
                                  v["trades"]) for k, v in out[name]["variants"].items()}, flush=True)
    out["blacklist"] = [" x ".join(k) for k in black]
    print("blacklist", out["blacklist"])
    (RUNS_DIR / f"{args.out}.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
