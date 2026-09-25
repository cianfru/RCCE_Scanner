"""
Follow-up: RCCE entries with Larsson Line exits (declared in docs/reviews/larsson-study.md
before it was run). Windows 1-9 only; the holdout stays untouched.

    python -m backtest.larsson_exit_study --out exits_w1-9      (from backend/)

Entries, sizing, BMSB gate, costs and the fill convention are exactly B1's
(replay_engine + PositionManager). Entries are skipped while the ribbon is
blue, so B3 is the exact control. Only the exit rule changes:

  X1  first daily close with the ribbon blue; no price stop, no RCCE exit
      signals, no decay exit
  X2  X1 + a 12% catastrophe stop checked on the close
  X3  X1 + RCCE's own exit signals (TRIM, TRIM_HARD, NO_LONG, RISK_OFF);
      no 8% stop, no decay exit
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import statistics
from collections import Counter

from backtest.larsson_study import (
    HOLDOUT, PRIMARY, RUNS_DIR, _bmsb, _costed_pm_class, _days, load_universe, metrics,
    rcce_replay, run_b1, windows,
)

MODES = ("X1", "X2", "X3")
CATASTROPHE_STOP = 0.12


def ll_exit_pm_class(mode: str):
    from backtest.position_manager import _ENTRY_SIGNALS, _EXIT_100_SIGNALS, _EXIT_ALL_SIGNAL
    base = _costed_pm_class()

    class LLExitPM(base):
        ll_state = None

        def process_bar(self, bar):
            sym, price, signal = bar.symbol, bar.price, bar.signal
            self._latest_prices[sym] = price
            if sym in self.positions:
                self.positions[sym].bars_held += 1
                pos = self.positions[sym]
                if self.ll_state == "blue":
                    return self._close_position(sym, bar.timestamp, price, "LL_BLUE", close_pct=1.0)
                if mode == "X2" and price <= pos.entry_price * (1 - CATASTROPHE_STOP):
                    return self._close_position(sym, bar.timestamp, price, "STOP_12", close_pct=1.0)
                if mode == "X3":
                    if signal == _EXIT_ALL_SIGNAL:
                        trades = self._close_all(bar.timestamp, price_override=None, exit_signal=signal)
                        return trades[-1] if trades else None
                    if signal in _EXIT_100_SIGNALS:
                        return self._close_position(sym, bar.timestamp, price, signal, close_pct=1.0)
            elif mode == "X3" and signal == _EXIT_ALL_SIGNAL:
                trades = self._close_all(bar.timestamp, price_override=None, exit_signal=signal)
                return trades[-1] if trades else None
            # Entries: identical to PositionManager.process_bar
            if signal in _ENTRY_SIGNALS and not self.macro_blocked:
                if signal == "ACCUMULATE" and sym in self.positions:
                    return self._add_to_position(sym, bar, bar.confluence_label)
                if sym not in self.positions:
                    return self._open_position(sym, bar, bar.confluence_label)
            return None

    return LLExitPM


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    out = RUNS_DIR / args.out
    if out.exists():
        ap.error(f"{out} exists; results are never overwritten")
    wins = [w for w in windows() if w["index"] < HOLDOUT]
    data = load_universe(PRIMARY, windows()[HOLDOUT - 2]["end"])
    replay = rcce_replay(data, windows()[HOLDOUT - 2]["end"], RUNS_DIR / "cache")
    bmsb = _bmsb(replay)
    rows, exits = [], {}
    for w in wins:
        days = len(_days(w, data))
        runs = {"B1": run_b1(w, data, replay, bmsb), "B3": run_b1(w, data, replay, bmsb, veto_blue=True)}
        for mode in MODES:
            runs[mode] = run_b1(w, data, replay, bmsb, veto_blue=True, pm_class=ll_exit_pm_class(mode))
        for name, (curve, exp, tr) in runs.items():
            rows.append(dict(window=w["index"], strategy=name, **metrics(curve, exp, tr, days)))
            exits.setdefault(name, []).extend(tr)
    out.mkdir(parents=True)
    with (out / "results.csv").open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    summary = {}
    for name in ("B1", "B3") + MODES:
        r = [x for x in rows if x["strategy"] == name]
        tr = exits[name]
        summary[name] = {
            "compounded_pct": (math.prod(1 + x["total_return_pct"] / 100 for x in r) - 1) * 100,
            "median_sharpe": statistics.median(x["sharpe"] for x in r),
            "median_dd_pct": statistics.median(x["max_dd_pct"] for x in r),
            "worst_dd_pct": min(x["max_dd_pct"] for x in r),
            "positive_windows": sum(x["total_return_pct"] > 0 for x in r),
            "trades": len(tr),
            "win_rate_pct": sum(t["pnl"] > 0 for t in tr) / len(tr) * 100 if tr else 0.0,
            "avg_hold_bars": statistics.mean(t["bars"] for t in tr) if tr else 0.0,
            "median_exposure_pct": statistics.median(x["avg_exposure_pct"] for x in r),
            "exits": dict(Counter(t["exit"] for t in tr)),
            "per_window": {x["window"]: {"ret": x["total_return_pct"], "sharpe": x["sharpe"], "dd": x["max_dd_pct"]} for x in r},
        }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
