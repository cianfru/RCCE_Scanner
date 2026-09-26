"""
Position sizing study (docs/reviews/position-sizing-study.md): the same replayed signals,
costed PositionManager and exits; only how much each entry takes changes.

    python -m backtest.sizing_study <replay.pkl> --set primary|secondary --out <name>   (from backend/)
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

import numpy as np

import backtest.position_manager as pm_mod
from backtest.larsson_study import (
    HOLDOUT, INITIAL_CAPITAL, RUNS_DIR, _compute_bmsb_filter, _costed_pm_class, _is_bmsb_blocked,
    _weekly_completed, metrics, windows,
)
from backtest.live_logic_check import _daily
from backtest.stop_study import atr_pct_series

ATR_REF = 0.025
SLOTS_Z4 = 5
VARIANTS = ("Z0", "Z1", "Z2", "Z3", "Z4")


def make_pm(name, atr):
    Base = _costed_pm_class()

    class SizedPM(Base):
        def __init__(self, capital, symbols, *a, **k):
            super().__init__(capital, symbols, *a, **k)
            if name == "Z4":
                self.per_symbol_alloc = capital * self.leverage / SLOTS_Z4

        def _mult(self, sym, bar):
            if name == "Z2":
                ts, a = atr[sym]
                i = np.searchsorted(ts, bar.timestamp, side="right") - 1
                v = a[i] if i >= 0 and np.isfinite(a[i]) and a[i] > 0 else ATR_REF
                return min(2.0, max(0.5, ATR_REF / v))
            if name == "Z3":
                met, tot = getattr(bar, "conditions_met", None), getattr(bar, "conditions_total", None)
                share = met / tot if met is not None and tot else 0.8
                return min(1.5, max(0.5, share / 0.8))
            return 1.0

        def _open_position(self, sym, bar, confluence):
            m = self._mult(sym, bar)
            base = pm_mod._ENTRY_SIZING
            pm_mod._ENTRY_SIZING = {sig: {c: ((1.0 if v > 0 else 0.0) if name == "Z1" else v * m) for c, v in d.items()}
                                    for sig, d in base.items()}
            try:
                return super()._open_position(sym, bar, confluence)
            finally:
                pm_mod._ENTRY_SIZING = base

    return SizedPM


def score(rows, bmsb, pm_class):
    by_ts = collections.defaultdict(list)
    for r in rows:
        by_ts[r["timestamp"]].append(r)
    stamps = sorted(by_ts)
    syms = sorted({r["symbol"] for r in rows})
    out, trades_all, exp_all = [], [], []
    for w in [w for w in windows() if w["index"] < HOLDOUT]:
        pm = pm_class(INITIAL_CAPITAL, syms)
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
        trades = [dict(pnl=t.pnl_usd, r=None, bars=t.bars_held, exit=t.exit_signal, symbol=t.symbol) for t in pm.trades]
        trades_all += trades
        exp_all += exposure
        m = metrics(_daily(pm.equity_curve), exposure, trades, (w["end_ms"] - w["start_ms"]) / 86_400_000)
        out.append(dict(window=w["index"], **m))
    return out, trades_all, exp_all


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("replay")
    ap.add_argument("--set", required=True, choices=("primary", "secondary"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = pickle.loads(Path(args.replay).read_bytes())
    syms = sorted({r["symbol"] for r in rows})
    atr = {s: atr_pct_series(s) for s in syms}
    wk = _weekly_completed("BTC", windows()[HOLDOUT - 2]["end"])
    m = _compute_bmsb_filter(wk)
    bmsb = (m, sorted(m))
    table = {}
    for name in VARIANTS:
        res, trades, exp = score(rows, bmsb, make_pm(name, atr))
        table[name] = {
            "compounded_pct": (math.prod(1 + r["total_return_pct"] / 100 for r in res) - 1) * 100,
            "per_window_pct": [round(r["total_return_pct"], 2) for r in res],
            "worst_dd_pct": min(r["max_dd_pct"] for r in res),
            "median_sharpe": statistics.median(r["sharpe"] for r in res),
            "avg_exposure_pct": round(100 * float(np.mean(exp)), 1),
            "trades": len(trades),
            "win_rate_pct": 100 * sum(t["pnl"] > 0 for t in trades) / max(1, len(trades)),
            "worst_trades_usd": [round(x) for x in sorted(t["pnl"] for t in trades)[:3]],
        }
        t = table[name]
        print(name, round(t["compounded_pct"], 1), round(t["worst_dd_pct"], 1), round(t["median_sharpe"], 2),
              t["avg_exposure_pct"], t["trades"], t["worst_trades_usd"], flush=True)
    (RUNS_DIR / f"{args.out}.json").write_text(json.dumps({"set": args.set, "variants": table}, indent=1, default=float))


if __name__ == "__main__":
    main()
