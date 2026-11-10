"""
The gaps between the live executor and the backtest position manager, one at a time
(docs/reviews/executor-gap-study.md).

The executor (executor.py) and the backtest manager (backtest/position_manager.py) share entries, sizing, the
8% stop and the signal exits. They differ in four management rules:

                                   executor            backtest manager
    decay exit (bars of Wait)      none                20
    BTC weekly-band entry block    none                yes
    breakeven stop after +5%       yes                 none
    Risk-off closes                that coin           every position

`manager(...)` builds a costed position manager with each rule set either way. Scoring is backtest/rule_lab.score
on the rows of the live rules, so nothing here touches the executor.

    python -m backtest.executor_gap --rows <rows.pkl> [<rows.pkl> ...] --out <result.json>      (from backend/)
"""
from __future__ import annotations

from typing import Dict, Optional

STOP_PCT = -0.08                 # both sides
BE_ARM = 0.05                    # executor: armed once the position has been +5%
EXIT_SIGNALS = ("TRIM_HARD", "NO_LONG", "TRIM")

EXECUTOR = dict(decay=None, band=False, breakeven=True, risk_off_all=False)
BACKTEST = dict(decay=20, band=True, breakeven=False, risk_off_all=True)

# The declared variants: the executor's rules with one backtest rule added (X5: two).
VARIANTS: Dict[str, dict] = {
    "X0": EXECUTOR,
    "X1_decay20": {**EXECUTOR, "decay": 20},
    "X1_decay42": {**EXECUTOR, "decay": 42},
    "X2_band": {**EXECUTOR, "band": True},
    "X3_riskoff_all": {**EXECUTOR, "risk_off_all": True},
    "X4_no_breakeven": {**EXECUTOR, "breakeven": False},
    "X5_decay20_band": {**EXECUTOR, "decay": 20, "band": True},
    "B": BACKTEST,
}


def manager(decay: Optional[int], band: bool, breakeven: bool, risk_off_all: bool):
    """A costed position manager class with the four rules set as given."""
    from backtest.larsson_study import _costed_pm_class

    class GapPM(_costed_pm_class()):
        def process_bar(self, bar):
            sym, price, signal = bar.symbol, bar.price, bar.signal
            self._latest_prices[sym] = price
            pos = self.positions.get(sym)
            if pos is not None:
                pos.bars_held += 1
                pos.peak_price = max(pos.peak_price, price)
                gain = (price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0.0
                if gain <= STOP_PCT:
                    self._wait_counts[sym] = 0
                    return self._close_position(sym, bar.timestamp, price, "STOP_LOSS")
                if breakeven and gain <= 0 and pos.peak_price >= pos.entry_price * (1 + BE_ARM):
                    self._wait_counts[sym] = 0
                    return self._close_position(sym, bar.timestamp, price, "BE_STOP")
            if signal == "RISK_OFF":
                self._wait_counts[sym] = 0
                if risk_off_all:
                    trades = self._close_all(bar.timestamp, price_override=None, exit_signal=signal)
                    return trades[-1] if trades else None
                return self._close_position(sym, bar.timestamp, price, signal)
            if signal in EXIT_SIGNALS:
                self._wait_counts[sym] = 0
                return self._close_position(sym, bar.timestamp, price, signal)
            if signal == "WAIT":
                self._wait_counts[sym] = self._wait_counts.get(sym, 0) + 1
                if decay is not None and self._wait_counts[sym] >= decay and sym in self.positions:
                    self._wait_counts[sym] = 0
                    return self._close_position(sym, bar.timestamp, price, "DECAY_EXIT")
                return None
            self._wait_counts[sym] = 0
            if signal in ("STRONG_LONG", "LIGHT_LONG", "REVIVAL_SEED"):
                if band and self.macro_blocked:
                    return None
                if sym not in self.positions:
                    return self._open_position(sym, bar, bar.confluence_label)
            return None

    return GapPM


def compounded(windows) -> float:
    t = 1.0
    for w in windows:
        t *= 1 + w["total_return_pct"] / 100
    return 100 * (t - 1)


def main(argv=None):
    import argparse
    import collections
    import json
    import pickle
    from pathlib import Path
    from backtest import rule_lab
    from backtest.larsson_study import HOLDOUT, windows
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", nargs="+", required=True, help="<name>.rows.pkl from backtest/rule_capture.py (4H)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    wins = [w for w in windows() if w["index"] < HOLDOUT]
    bmsb = rule_lab.bmsb_filter(windows()[HOLDOUT - 2]["end"])
    res = {}
    for path in args.rows:
        name = Path(path).name.replace(".rows.pkl", "")
        rows = pickle.loads(Path(path).read_bytes())
        res[name] = {"reference": rule_lab.score(rows, bmsb, wins)}        # the unchanged backtest manager
        for v, flags in VARIANTS.items():
            res[name][v] = rule_lab.score(rows, bmsb, wins, pm_class=manager(**flags))
        for v, ws in res[name].items():
            exits = collections.Counter()
            for w in ws:
                exits.update(w["exits"])
            print(f"{name:<14}{v:<18}W1-6 {compounded(ws[:6]):+7.1f}  W7-9 {compounded(ws[6:]):+7.1f}  "
                  f"W1-9 {compounded(ws):+7.1f}  worst {min(w['total_return_pct'] for w in ws):+6.1f}  {dict(exits)}")
    Path(args.out).write_text(json.dumps({"variants": VARIANTS, "results": res}, indent=1, default=float))


if __name__ == "__main__":
    main()
