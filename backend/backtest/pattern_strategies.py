"""
Pattern strategy variants (declared in docs/reviews/larsson-study.md before they were run).

    python -m backtest.pattern_strategies --out pattern_strats_w1-9      (from backend/)

Windows 1-9, primary universe, declared parameters. Each variant is compared with
its parent and with B1; White's Reality Check runs over the five against B1.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics

import numpy as np

from backtest.larsson_scenarios import Scenario, prepare, reality_check, scenario_pm_class
from backtest.larsson_study import (
    DECLARED, HOLDOUT, INITIAL_CAPITAL, RUNS_DIR, _costed_pm_class, _days, metrics, run_b1, run_larsson, windows,
)

DECLARED_VARIANTS = ("L2P", "L3X50", "L3X100", "RCCE-PX", "H60-PX")
PARENTS = {"L2P": "L2", "L3X50": "L3", "L3X100": "L3", "RCCE-PX": "B1", "H60-PX": "F0-t60-s12-nosig"}


def rcce_px_class():
    """B1's PositionManager, unchanged, plus a full exit when a bear pattern confirms."""
    base = _costed_pm_class()

    class RccePatternExitPM(base):
        ctx = None

        def set_context(self, sym, i, sd):
            self.ctx = (sym, i, sd)

        def process_bar(self, bar):
            _, i, sd = self.ctx
            if bar.symbol in self.positions and i is not None and {20, 21, 23} & set(sd.pattern_bars.get(i, [])):
                self._latest_prices[bar.symbol] = bar.price
                self.positions[bar.symbol].bars_held += 1
                return self._close_position(bar.symbol, bar.timestamp, bar.price, "BEAR_PATTERN", close_pct=1.0)
            return super().process_bar(bar)

    return RccePatternExitPM


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = RUNS_DIR / args.out
    if out.exists():
        ap.error("results are never overwritten")
    data, replay, bmsb = prepare("primary")
    wins = [w for w in windows() if w["index"] < HOLDOUT]
    runners = {
        "B1": lambda w: run_b1(w, data, replay, bmsb),
        "RCCE-PX": lambda w: run_b1(w, data, replay, bmsb, pm_class=rcce_px_class()),
        "F0-t60-s12-nosig": lambda w: run_b1(w, data, replay, bmsb, pm_class=scenario_pm_class(Scenario(False, "t60", 0.12, False))),
        "H60-PX": lambda w: run_b1(w, data, replay, bmsb, pm_class=scenario_pm_class(Scenario(False, "t60", 0.12, False, pattern_exit=True))),
    }
    for v in ("L2", "L2P", "L3", "L3X50", "L3X100"):
        runners[v] = (lambda name: (lambda w: run_larsson(name, DECLARED, w, data, replay, bmsb)))(v)
    results = {}
    for name, fn in runners.items():
        rows, daily, trades = [], [], []
        for w in wins:
            curve, exp, tr = fn(w)
            rows.append(dict(window=w["index"], **metrics(curve, exp, tr, len(_days(w, data)))))
            eq = np.array([INITIAL_CAPITAL] + [e for _, e in curve])
            daily.extend(eq[1:] / eq[:-1] - 1)
            trades.extend(tr)
        results[name] = {"rows": rows, "daily": np.array(daily), "trades": trades}
    rc = reality_check(results, list(DECLARED_VARIANTS))
    table = {}
    for name, res in results.items():
        rows = res["rows"]
        table[name] = {
            "compounded_pct": (math.prod(1 + r["total_return_pct"] / 100 for r in rows) - 1) * 100,
            "worst_dd_pct": min(r["max_dd_pct"] for r in rows),
            "median_sharpe": statistics.median(r["sharpe"] for r in rows),
            "trades": len(res["trades"]),
            "pattern_exits": sum(1 for t in res["trades"] if t["exit"] in ("bear_pattern", "BEAR_PATTERN")),
            "per_window_return": [round(r["total_return_pct"], 2) for r in rows],
            "parent": PARENTS.get(name),
            "naive_p_vs_b1": rc["naive_p"].get(name),
        }
    out.mkdir(parents=True)
    (out / "summary.json").write_text(json.dumps({"reality_check": rc, "table": table}, indent=1, default=float))
    print(json.dumps({"reality_check": {k: rc[k] for k in ("best", "family_p")}, "table": table}, indent=1, default=float))


if __name__ == "__main__":
    main()
