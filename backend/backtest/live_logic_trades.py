"""
The trades behind a scored replay (a report beside backtest/live_logic_check.py; it changes no score).

    python -m backtest.live_logic_trades A=<a.pkl> B=<b.pkl> [...] --out <name>   (from backend/)

Per variant, over windows 1-9, through the same manager and BTC weekly block as the scorer:
- by entry signal: trades, wins, the summed P&L as % of a window's starting capital, and the median trade;
- by coin: the summed P&L as % of a window's starting capital;
- exits by signal: how many trades each exit closed.
Each window starts from the same capital, so summed % adds up across windows (it is not compounded).
"""
from __future__ import annotations

import argparse
import collections
import json
import pickle
import statistics
from pathlib import Path

from backtest.larsson_study import HOLDOUT, INITIAL_CAPITAL, RUNS_DIR, _compute_bmsb_filter, _weekly_completed, windows
from backtest.live_logic_check import score


def summarize(trades):
    """trades: [(window, Trade)] -> the three tables."""
    def pct(x):
        return round(100.0 * x / INITIAL_CAPITAL, 2)
    by_entry = collections.defaultdict(list)
    by_coin = collections.defaultdict(float)
    exits = collections.Counter()
    for _, t in trades:
        by_entry[t.entry_signal].append(t)
        by_coin[t.symbol] += t.pnl_usd or 0.0
        exits[t.exit_signal or "END"] += 1
    entry = {k: {"trades": len(v), "wins": sum(1 for t in v if (t.pnl_usd or 0) > 0),
                 "pnl_pct": pct(sum(t.pnl_usd or 0 for t in v)),
                 "median_trade_pct": round(statistics.median(t.pnl_pct or 0 for t in v), 2)}
             for k, v in sorted(by_entry.items())}
    return {"by_entry": entry, "by_coin_pnl_pct": {k: pct(v) for k, v in sorted(by_coin.items())},
            "exits": dict(exits.most_common())}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("variants", nargs="+", help="NAME=path.pkl")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    w = _weekly_completed("BTC", windows()[HOLDOUT - 2]["end"])
    m = _compute_bmsb_filter(w)
    bmsb = (m, sorted(m))
    table = {}
    for spec in args.variants:
        name, path = spec.split("=", 1)
        sink = []
        score(pickle.loads(Path(path).read_bytes()), bmsb, sink)
        table[name] = summarize(sink)
    out = RUNS_DIR / f"{args.out}_trades.json"
    out.write_text(json.dumps(table, indent=1, default=float))
    print(json.dumps(table, indent=1, default=float))


if __name__ == "__main__":
    main()
