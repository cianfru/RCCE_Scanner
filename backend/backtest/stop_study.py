"""
Stop rules study (docs/reviews/stop-rules-study.md): the same replayed signals and costed
PositionManager, with only the stop rules changed.

    python -m backtest.stop_study <replay.pkl> --set primary|secondary --out <name>   (from backend/)

Stops are checked on 4H closes from the average entry, before the signal logic (as the
PositionManager's own 8% stop). Breakeven, once the peak close is BE_ARM above entry,
closes on the first close at or below entry. ATR14 is taken from completed 4H candles
at the entry bar and fixed for the trade. Windows 1-9 only.
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

BAR_MS = 4 * 3600 * 1000

# name: (stop kind, value, breakeven arm) ; stop kind "pct" | "atr" | None
VARIANTS = {
    "S0": ("pct", 0.08, None),
    "S1": ("pct", 0.08, 0.05),
    "S2": ("pct", 0.08, 0.10),
    "S3": ("pct", 0.12, None),
    "S4": ("pct", 0.16, None),
    "S5": (None, None, None),
    "S6": ("atr", 3.0, None),
    "S7": ("atr", 3.0, 0.10),
}
ATR_BOUNDS = (0.06, 0.25)


def atr_pct_series(symbol: str):
    """(close_times_ms, ATR14 % of close) from 4H Binance candles; value i is known at close_times[i]."""
    from backtest import binance_history as bh
    from backtest.live_logic_replay import DATA_END, DATA_START
    d = bh.load(symbol.replace("/", ""), "4h", DATA_START, DATA_END)
    h, l, c = (np.asarray(d[k], dtype=float) for k in ("high", "low", "close"))
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    atr = np.convolve(tr, np.ones(14) / 14, mode="full")[:len(tr)]
    atr[:13] = np.nan
    return np.asarray(d["timestamp"], dtype=float) + BAR_MS, atr / c


def make_pm(kind, value, be_arm, atr):
    Base = _costed_pm_class()

    class VariantPM(Base):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.stop_dist, self.peak = {}, {}

        def _open_position(self, sym, bar, confluence):
            t = super()._open_position(sym, bar, confluence)
            if sym in self.positions and sym not in self.stop_dist:
                if kind == "pct":
                    self.stop_dist[sym] = value
                elif kind == "atr":
                    ts, a = atr[sym]
                    i = np.searchsorted(ts, bar.timestamp, side="right") - 1
                    v = a[i] if i >= 0 and np.isfinite(a[i]) else ATR_BOUNDS[0] / value
                    self.stop_dist[sym] = min(ATR_BOUNDS[1], max(ATR_BOUNDS[0], value * v))
                else:
                    self.stop_dist[sym] = None
                self.peak[sym] = bar.price
            return t

        def _close_position(self, sym, timestamp, price, exit_signal, close_pct=1.0):
            t = super()._close_position(sym, timestamp, price, exit_signal, close_pct)
            if sym not in self.positions:
                self.stop_dist.pop(sym, None)
                self.peak.pop(sym, None)
            return t

        def process_bar(self, bar):
            sym, price = bar.symbol, bar.price
            pos = self.positions.get(sym)
            if pos is not None and pos.entry_price > 0:
                self.peak[sym] = max(self.peak.get(sym, price), price)
                move = price / pos.entry_price - 1
                dist = self.stop_dist.get(sym)
                if dist is not None and move <= -dist:
                    self._latest_prices[sym] = price
                    self._wait_counts[sym] = 0
                    return self._close_position(sym, bar.timestamp, price, "STOP_LOSS")
                if be_arm is not None and self.peak[sym] / pos.entry_price - 1 >= be_arm and move <= 0:
                    self._latest_prices[sym] = price
                    self._wait_counts[sym] = 0
                    return self._close_position(sym, bar.timestamp, price, "BE_STOP")
            return super().process_bar(bar)

    return VariantPM


def score(rows, bmsb, pm_class):
    by_ts = collections.defaultdict(list)
    for r in rows:
        by_ts[r["timestamp"]].append(r)
    stamps = sorted(by_ts)
    syms = sorted({r["symbol"] for r in rows})
    out, trades_all = [], []
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
        m = metrics(_daily(pm.equity_curve), exposure, trades, (w["end_ms"] - w["start_ms"]) / 86_400_000)
        out.append(dict(window=w["index"], **m))
    return out, trades_all


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("replay")
    ap.add_argument("--set", required=True, choices=("primary", "secondary"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    pm_mod._STOP_LOSS_PCT = -1e9          # the variants apply their own stops
    rows = pickle.loads(Path(args.replay).read_bytes())
    syms = sorted({r["symbol"] for r in rows})
    atr = {s: atr_pct_series(s) for s in syms}
    # Volatility thirds by median ATR% over the study windows.
    w = [x for x in windows() if x["index"] < HOLDOUT]
    lo_ms, hi_ms = w[0]["start_ms"], w[-1]["end_ms"]
    med = {s: float(np.nanmedian(a[(ts >= lo_ms) & (ts < hi_ms)])) for s, (ts, a) in atr.items()}
    order = sorted(syms, key=med.get)
    k = len(order)
    bracket = {s: ("low", "middle", "high")[min(2, i * 3 // k)] for i, s in enumerate(order)}
    wk = _weekly_completed("BTC", windows()[HOLDOUT - 2]["end"])
    m = _compute_bmsb_filter(wk)
    bmsb = (m, sorted(m))
    table = {}
    for name, (kind, value, be) in VARIANTS.items():
        res, trades = score(rows, bmsb, make_pm(kind, value, be, atr))
        per_bracket = collections.Counter()
        for t in trades:
            per_bracket[bracket[t["symbol"]]] += t["pnl"]
        worst = sorted(t["pnl"] for t in trades)[:3]
        table[name] = {
            "rule": {"stop": kind, "value": value, "breakeven": be},
            "compounded_pct": (math.prod(1 + r["total_return_pct"] / 100 for r in res) - 1) * 100,
            "per_window_pct": [round(r["total_return_pct"], 2) for r in res],
            "worst_dd_pct": min(r["max_dd_pct"] for r in res),
            "median_sharpe": statistics.median(r["sharpe"] for r in res),
            "trades": len(trades),
            "win_rate_pct": 100 * sum(t["pnl"] > 0 for t in trades) / max(1, len(trades)),
            "exits": dict(collections.Counter(t["exit"] for t in trades).most_common()),
            "worst_trades_usd": [round(x) for x in worst],
            "pnl_by_volatility_usd": {b: round(per_bracket[b]) for b in ("low", "middle", "high")},
        }
        print(name, round(table[name]["compounded_pct"], 1), round(table[name]["worst_dd_pct"], 1),
              table[name]["per_window_pct"], table[name]["pnl_by_volatility_usd"], flush=True)
    out = {"set": args.set, "brackets": {b: [s for s in order if bracket[s] == b] for b in ("low", "middle", "high")},
           "median_atr_pct": {s: round(100 * med[s], 2) for s in order}, "variants": table}
    (RUNS_DIR / f"{args.out}.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
