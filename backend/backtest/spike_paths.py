"""
Where past spikes bottomed, for the coin chart (docs/reviews/after-the-spike-study.md).

    python -m backtest.spike_paths export [--4h primary.pkl secondary.pkl ...]   (from backend/)

Spike and anchor follow the engine's cool-off definition (engines/spike_zone.py). Per
timeframe it writes the depth and bar of the lowest close within 60 bars of the anchor
(10/25/50/75/90th percentiles), how often price never fell 5%, and the median per-bar path.
Windows 1-9 only (bars after 2026-03-29 are dropped). Output: seeds/spike_paths.json.
"""
from __future__ import annotations

import argparse
import json
import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np

from backtest.larsson_study import RUNS_DIR
from engines.rcce_engine import Z_BLOWOFF
from engines.spike_zone import HORIZON, RUN_Z, SEED

END_DAY = 20541
END_MS = (END_DAY + 1) * 86_400_000


def paths(series):
    """series: list of (close, z). Anchored 60-bar paths, one per spike."""
    p = np.array([c for c, _ in series], dtype=np.float64)
    z = np.array([np.nan if v is None else v for _, v in series], dtype=np.float64)
    out, i, n = [], 0, len(series)
    while i < n:
        if z[i] >= Z_BLOWOFF:
            b = i
            while b + 1 < n and z[b + 1] >= RUN_Z:
                b += 1
            anc = b + 1
            if anc + HORIZON < n:
                out.append(p[anc:anc + HORIZON + 1] / p[anc])
            i = b + 1
        else:
            i += 1
    return out


def summarize(all_paths):
    P = np.array(all_paths)
    low = P.min(axis=1) - 1
    bar = P.argmin(axis=1)
    pct = lambda v, qs: {f"p{q}": round(float(np.percentile(v, q)), 4) for q in qs}
    return {"n": len(P), "horizon": HORIZON, "low_depth": pct(low, (10, 25, 50, 75, 90)),
            "low_bar": {k: int(round(v)) for k, v in pct(bar, (25, 50, 75)).items()},
            "never_fell_5pct": round(float(np.mean(low > -0.05)), 3),
            "median_path": [round(float(v), 4) for v in np.median(P, axis=0)]}


def daily():
    reg = json.loads((RUNS_DIR / "breadth_history_regimes.json").read_text())
    closes = json.loads((RUNS_DIR / "breadth_history.json").read_text())["closes"]
    out = []
    for pair, rows in reg.items():
        c = closes.get(pair, {})
        out += paths([(c[str(d)], z) for d, _, z in rows if d <= END_DAY and str(d) in c])
    return out


def four_hour(pickles):
    out = []
    for path in pickles:
        by = defaultdict(list)
        for r in sorted(pickle.loads(Path(path).read_bytes()), key=lambda r: r["timestamp"]):
            if r["timestamp"] < END_MS and r.get("price"):
                by[r["symbol"]].append((r["price"], r.get("zscore")))
        for s in by.values():
            out += paths(s)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=("export",))
    ap.add_argument("--4h", dest="four", nargs="*", default=[])
    args = ap.parse_args(argv)
    seed = {"1d": summarize(daily())}
    if args.four:
        seed["4h"] = summarize(four_hour(args.four))
    SEED.write_text(json.dumps(seed, separators=(",", ":")))
    for tf, s in seed.items():
        print(tf, s["n"], "spikes; low", s["low_depth"], "bar", s["low_bar"], "never fell 5%:", s["never_fell_5pct"])


if __name__ == "__main__":
    main()
