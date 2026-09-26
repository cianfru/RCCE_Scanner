"""
Rebuild daily market breadth with the live engine (declared in docs/reviews/market-breadth-study.md).

    python -m backtest.breadth_history rebuild --out breadth_history      (from backend/)

At every closed daily candle compute_rcce runs on each coin's trailing window (up to 600
candles, as the scanner does; coins with fewer than 200 candles are skipped that day).
Output: per coin per day regime and z-score, plus per-day aggregates, written to
data/larsson_runs/<out>.json (gitignored). Recent days are kept for display; the study
itself only measures outcomes up to 2026-03-29.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

from backtest import binance_history as bh
from backtest.larsson_study import RUNS_DIR
from backtest.sector_momentum_study import _pair
from sectors import _S

START = "2019-01-01"
WINDOW = 600
MIN_BARS = 200
DAY_MS = 86_400_000


def coins():
    seen, out = set(), []
    for coin in ["BTC", *_S.keys()]:
        pair = _pair(coin)
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out


def _worker(pair):
    try:
        d = bh.load(pair, "1d", START, None)
    except Exception:
        return pair, None
    if d is None or len(d["close"]) < MIN_BARS + 1:
        return pair, None
    from engines.rcce_engine import compute_rcce
    rows = []
    for i in range(MIN_BARS, len(d["close"]) + 1):
        w = {k: v[max(0, i - WINDOW):i] for k, v in d.items()}     # candles up to and including bar i-1
        r = compute_rcce(w)
        day = int(d["timestamp"][i - 1]) // DAY_MS
        rows.append((day, r.get("regime"), round(float(r.get("z_score") or 0.0), 3), float(d["close"][i - 1])))
    return pair, rows


def rebuild(out_name):
    pairs = coins()
    with ProcessPoolExecutor(max_workers=4) as pool:
        per_coin = {p: rows for p, rows in pool.map(_worker, pairs, chunksize=2) if rows}
    days = defaultdict(list)
    for pair, rows in per_coin.items():
        for day, regime, z, close in rows:
            days[day].append((pair, regime, z))
    agg = []
    for day in sorted(days):
        rs = days[day]
        c = Counter(r for _, r, _ in rs)
        n = len(rs)
        agg.append({"day": day, "n": n, "counts": dict(c),
                    "uptrend": round(c.get("MARKUP", 0) / n, 4), "overheated": round(c.get("BLOWOFF", 0) / n, 4),
                    "downtrend": round(c.get("MARKDOWN", 0) / n, 4),
                    "basing": round((c.get("ACCUM", 0) + c.get("REACC", 0) + c.get("CAP", 0)) / n, 4),
                    "median_z": round(statistics.median(z for _, _, z in rs), 3)})
    closes = {p: {day: close for day, _, _, close in rows} for p, rows in per_coin.items()}
    (RUNS_DIR / f"{out_name}.json").write_text(json.dumps({"coins": len(per_coin), "days": agg, "closes": closes}))
    (RUNS_DIR / f"{out_name}_regimes.json").write_text(json.dumps({p: [(d, r, z) for d, r, z, _ in rows] for p, rows in per_coin.items()}))
    print(f"{len(per_coin)} coins, {len(agg)} days -> {out_name}.json")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rebuild")
    r.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "rebuild":
        rebuild(args.out)


if __name__ == "__main__":
    main()
