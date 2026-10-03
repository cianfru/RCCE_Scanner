import unittest
from types import SimpleNamespace

import numpy as np

from backtest import breakdown_exit_study as r2
from backtest.larsson_scenarios import scenario_pm_class
from backtest.larsson_study import _costed_pm_class


def breakdown(level):
    return {"event": "breakdown", "level": float(level), "n_low": 2}


def sd(opens, closes, states=None, events=None):
    n = len(closes)
    states = states or ["grey"] * n
    events = events or {}
    return SimpleNamespace(usd={"open": np.array(opens, float), "close": np.array(closes, float)},
                           ll={"state": states, "e32": np.full(n, np.nan)}, atr=np.full(n, np.nan),
                           levels=[SimpleNamespace(events=events.get(i, [])) for i in range(n)], pattern_bars={})


def bar(i, price, signal="WAIT"):
    return SimpleNamespace(symbol="X/USDT", timestamp=float(i), price=price, signal=signal,
                           confluence_label="STRONG", date="")


def run(cls, data, signals=None, between=None):
    pm = cls(10_000, ["X/USDT"])
    for i, p in enumerate(data.usd["close"]):
        if hasattr(pm, "set_context"):                 # as run_b1 does
            pm.set_context("X", i, data)
        pm.process_bar(bar(i, float(p), (signals or {}).get(i, "WAIT")))
        if between and i in between:
            between[i](pm)
    return pm, [(int(t.exit_time), t.exit_signal, round(t.exit_price, 4), round(t.size_pct, 3)) for t in pm.trades]


B1 = _costed_pm_class()


class BreakdownExitTests(unittest.TestCase):
    def test_full_exit_fills_at_the_next_open_after_the_breakdown_close(self):
        data = sd(opens=[100, 100, 99, 98, 95, 97], closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(98)]})
        pm, trades = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(4, "BREAKDOWN", 95.0, 1.0)])
        self.assertEqual(pm.trades[0].tags, {"bd_bar": 3, "fill_bar": 4})
        self.assertNotIn("X/USDT", pm.positions)

    def test_no_new_entry_on_the_exit_bar_then_entries_resume(self):
        data = sd(opens=[100, 100, 99, 98, 95, 97], closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(98)]})
        pm, trades = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG", 4: "STRONG_LONG"})
        self.assertEqual(trades, [(4, "BREAKDOWN", 95.0, 1.0)])
        self.assertNotIn("X/USDT", pm.positions)
        pm, _ = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG", 4: "STRONG_LONG", 5: "STRONG_LONG"})
        self.assertEqual(pm.positions["X/USDT"].entry_time, 5.0)

    def test_parent_unchanged_without_a_breakdown(self):
        data = sd(opens=[100] * 6, closes=[100, 99, 98, 96, 97, 97])
        _, with_rule = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG"})
        _, parent = run(B1, data, signals={0: "STRONG_LONG"})
        self.assertEqual(with_rule, parent)

    def test_half_sell_fires_once_per_trade(self):
        data = sd(opens=[100, 100, 98, 97, 97, 96, 96], closes=[100, 99, 97, 97, 96, 96, 96],
                  events={2: [breakdown(99)], 4: [breakdown(98)], 5: [breakdown(97.5)]})
        pm, trades = run(r2.breakdown_exit_class(B1, fraction=0.5, once=True), data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(3, "BREAKDOWN_50", 97.0, 0.5)])
        self.assertAlmostEqual(pm.positions["X/USDT"].size_pct, 0.5)

    def test_half_sell_rearms_for_a_new_trade(self):
        data = sd(opens=[100, 100, 98, 97, 97, 96, 96, 96], closes=[100, 99, 97, 97, 96, 96, 95, 95],
                  events={2: [breakdown(99)], 6: [breakdown(96)]})
        pm, trades = run(r2.breakdown_exit_class(B1, fraction=0.5, once=True), data,
                         signals={0: "STRONG_LONG", 4: "TRIM", 5: "STRONG_LONG"})
        self.assertEqual([t[1] for t in trades], ["BREAKDOWN_50", "TRIM", "BREAKDOWN_50"])
        self.assertEqual(trades[-1][0], 7)

    def test_levels_above_the_average_entry_are_ignored(self):
        data = sd(opens=[100] * 6, closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(101)]})
        _, trades = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [])
        data = sd(opens=[100] * 6, closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(100)]})
        _, trades = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(4, "BREAKDOWN", 100.0, 1.0)])     # at the entry price counts

    def test_other_events_and_the_entry_bar_do_not_trigger(self):
        data = sd(opens=[100] * 6, closes=[100, 99, 98, 96, 97, 97],
                  events={0: [breakdown(99)], 2: [{"event": "rejection", "level": 99.0, "n_low": 0}]})
        _, trades = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [])

    def test_not_gold_gate(self):
        events = {3: [breakdown(98)]}
        gold = sd(opens=[100] * 6, closes=[100, 99, 98, 96, 97, 97], states=["gold"] * 6, events=events)
        _, trades = run(r2.breakdown_exit_class(B1, not_gold=True), gold, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [])
        grey = sd(opens=[100] * 6, closes=[100, 99, 98, 96, 97, 97], states=["gold"] * 3 + ["grey"] * 3, events=events)
        _, trades = run(r2.breakdown_exit_class(B1, not_gold=True), grey, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(4, "BREAKDOWN", 100.0, 1.0)])
        _, trades = run(r2.breakdown_exit_class(B1), gold, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(4, "BREAKDOWN", 100.0, 1.0)])     # ungated variant ignores the ribbon

    def test_pending_exit_dropped_when_the_position_closes_first(self):
        data = sd(opens=[100] * 6, closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(98)]})
        close_all = {3: lambda pm: pm._close_all(3.0, None, "RISK_OFF")}
        _, trades = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG"}, between=close_all)
        self.assertEqual(trades, [(3, "RISK_OFF", 96.0, 1.0)])

    def test_parent_exit_on_the_breakdown_close_wins(self):
        data = sd(opens=[100] * 6, closes=[100, 99, 98, 91, 97, 97], events={3: [breakdown(98)]})
        _, trades = run(r2.breakdown_exit_class(B1), data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(3, "STOP_LOSS", 91.0, 1.0)])          # B1's 8% stop on that close

    def test_h60_parent_keeps_its_rules(self):
        h60 = scenario_pm_class(r2.H60)
        quiet = sd(opens=[100] * 62, closes=[100] * 62)
        _, trades = run(r2.breakdown_exit_class(h60), quiet, signals={0: "STRONG_LONG", 10: "TRIM"})
        self.assertEqual(trades, [(60, "T60", 100.0, 1.0)])               # RCCE exit signals still ignored
        data = sd(opens=[100] * 62, closes=[100] * 5 + [95] * 57, events={5: [breakdown(97)]})
        _, trades = run(r2.breakdown_exit_class(h60), data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(6, "BREAKDOWN", 100.0, 1.0)])


class ReportingTests(unittest.TestCase):
    def test_positions_merge_partial_sells(self):
        trades = [dict(symbol="X", entry=1.0, exit_ts=5.0, pnl=-10.0, bars=4, exit="BREAKDOWN_50"),
                  dict(symbol="X", entry=1.0, exit_ts=9.0, pnl=30.0, bars=8, exit="T60"),
                  dict(symbol="Y", entry=2.0, exit_ts=3.0, pnl=-5.0, bars=1, exit="STOP_LOSS")]
        pos = r2.positions(trades)
        self.assertEqual(len(pos), 2)
        x = next(p for p in pos if p["symbol"] == "X")
        self.assertEqual((x["pnl"], x["bars"], x["exit"]), (20.0, 8, "T60"))

    def test_forward_return_from_fill_open_to_close_20_bars_after_the_breakdown(self):
        n = 30
        data = {"X": sd(opens=[100.0] * n, closes=[100.0] * 23 + [90.0] * 7)}
        data["X"].usd["open"][4] = 80.0
        trades = [dict(symbol="X", exit="BREAKDOWN", bd_bar=3, fill_bar=4),
                  dict(symbol="X", exit="BREAKDOWN", bd_bar=12, fill_bar=13),
                  dict(symbol="X", exit="STOP_LOSS")]
        f = r2.forward_returns(trades, data)
        self.assertEqual((f["n"], f["excluded"]), (1, 1))                 # bar 32 is past the data
        self.assertAlmostEqual(f["mean_pct"], (90 / 80 - 1) * 100)        # close of bar 23 / open of bar 4

    def test_best_coin_is_the_largest_gain_over_the_parent(self):
        v = [dict(symbol="A", pnl=50.0), dict(symbol="B", pnl=100.0)]
        p = [dict(symbol="A", pnl=-40.0), dict(symbol="B", pnl=95.0)]
        self.assertEqual(r2.best_coin(v, p), "A")

    def test_beats_needs_both_return_and_drawdown(self):
        parent = {"compounded_pct": 50.0, "worst_dd_pct": -20.0}
        self.assertTrue(r2.beats({"compounded_pct": 51.0, "worst_dd_pct": -19.0}, parent))
        self.assertFalse(r2.beats({"compounded_pct": 51.0, "worst_dd_pct": -20.0}, parent))
        self.assertFalse(r2.beats({"compounded_pct": 49.0, "worst_dd_pct": -10.0}, parent))

    def test_adjusted_p_equals_family_p_for_the_best_and_is_larger_for_the_rest(self):
        from backtest.larsson_scenarios import reality_check
        rng = np.random.default_rng(3)
        base = rng.normal(0, 0.01, 500)
        results = {"B1": {"daily": base}}
        for k, edge in enumerate((0.0015, 0.0005, 0.0, -0.0005)):
            results[f"v{k}"] = {"daily": base + edge + rng.normal(0, 0.002, 500)}
        rc = reality_check(results, ["v0", "v1", "v2", "v3"], reps=300)
        self.assertEqual(rc["best"], "v0")
        self.assertEqual(rc["adjusted_p"]["v0"], rc["family_p"])
        self.assertTrue(all(rc["adjusted_p"][v] >= rc["family_p"] for v in ("v1", "v2", "v3")))

    def test_declared_variants_and_parents(self):
        self.assertEqual(r2.VARIANTS, ("R2-B1", "R2-B1-50", "R2-H60", "R2-B1-ng"))
        self.assertEqual(r2.H60_NAME, "F0-t60-s12-nosig")
        self.assertEqual(set(r2.pm_classes()), {"B1", "F0-t60-s12-nosig", *r2.VARIANTS})


if __name__ == "__main__":
    unittest.main()
