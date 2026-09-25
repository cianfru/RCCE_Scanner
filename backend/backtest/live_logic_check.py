"""
Score replayed signal logic with one position manager (step 2 of 2).

    python -m backtest.live_logic_check A=<a.pkl> B=<b.pkl> [C=<c.pkl> ...] --out <name>   (from backend/)

Each argument is a replay from backtest/live_logic_replay.py (4h bars, windows 1-9).
Every variant runs through the same costed PositionManager as the study's B1 baseline
(5+5 bps fees, 5+5 bps slippage, the manager's own stops, exits and sizing) and the
same BTC weekly-BMSB block on completed weeks. Only the signals differ, so any gap in
returns comes from the signal logic itself.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pickle
import statistics
from pathlib import Path
from types import SimpleNamespace

from backtest.larsson_study import (
    HOLDOUT, INITIAL_CAPITAL, RUNS_DIR, _compute_bmsb_filter, _costed_pm_class, _date, _is_bmsb_blocked,
    _weekly_completed, metrics, windows,
)


def _daily(curve):
    by_day = {}
    for ts, eq in curve:
        by_day[_date(ts)] = (ts, eq)
    return [by_day[d] for d in sorted(by_day)]


def score(rows, bmsb):
    by_ts = collections.defaultdict(list)
    for r in rows:
        by_ts[r["timestamp"]].append(r)
    stamps = sorted(by_ts)
    syms = sorted({r["symbol"] for r in rows})
    out = []
    for w in [w for w in windows() if w["index"] < HOLDOUT]:
        pm = _costed_pm_class()(INITIAL_CAPITAL, syms)
        span = [t for t in stamps if w["start_ms"] <= t < w["end_ms"]]
        exposure = []
        for ts in span:
            pm.macro_blocked = _is_bmsb_blocked(bmsb[0], bmsb[1], ts)
            bars = [SimpleNamespace(**r) for r in by_ts[ts]]
            for bar in bars:
                pm.process_bar(bar)
            pm.mark_to_market(ts, {b.symbol: b.price for b in bars})
            eq = pm.equity_curve[-1][1]
            value = sum(pm.per_symbol_alloc * p.size_pct * pm._latest_prices.get(s, p.entry_price) / p.entry_price
                        for s, p in pm.positions.items() if p.entry_price > 0)
            exposure.append(value / eq if eq > 0 else 0.0)
        pm.close_all_at_end(span[-1])
        pm.equity_curve[-1] = (span[-1], pm.get_equity())
        trades = [dict(pnl=t.pnl_usd, r=None, bars=t.bars_held, exit=t.exit_signal) for t in pm.trades]
        m = metrics(_daily(pm.equity_curve), exposure, trades, (w["end_ms"] - w["start_ms"]) / 86_400_000)
        out.append(dict(window=w["index"], **m))
    return out


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
        rows = pickle.loads(Path(path).read_bytes())
        res = score(rows, bmsb)
        sig = collections.Counter(r["signal"] for r in rows)
        table[name] = {
            "compounded_pct": (math.prod(1 + r["total_return_pct"] / 100 for r in res) - 1) * 100,
            "per_window_pct": [round(r["total_return_pct"], 2) for r in res],
            "worst_dd_pct": min(r["max_dd_pct"] for r in res),
            "median_sharpe": statistics.median(r["sharpe"] for r in res),
            "trades": sum(r["trades"] for r in res),
            "win_rate_pct": statistics.mean(r["win_rate_pct"] for r in res),
            "signal_bars": dict(sig.most_common()),
            "regime_bars": dict(collections.Counter(r["regime"] for r in rows).most_common()),
        }
    out = RUNS_DIR / f"{args.out}.json"
    out.write_text(json.dumps(table, indent=1, default=float))
    print(json.dumps(table, indent=1, default=float))


if __name__ == "__main__":
    main()
