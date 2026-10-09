import unittest
from types import SimpleNamespace

import numpy as np

from backtest import breakdown_exit_study as r2
from backtest import riskoff_breakdown_study as ro
from backtest.larsson_scenarios import scenario_pm_class
from backtest.larsson_study import DAY_MS, _compute_bmsb_filter, _costed_pm_class, _is_bmsb_blocked
from scanner import compute_consensus


def breakdown(level):
    return {"event": "breakdown", "level": float(level), "n_low": 2}


def sd(opens, closes, events=None):
    n = len(closes)
    events = events or {}
    return SimpleNamespace(usd={"open": np.array(opens, float), "close": np.array(closes, float)},
                           ll={"state": ["grey"] * n, "e32": np.full(n, np.nan)}, atr=np.full(n, np.nan),
                           levels=[SimpleNamespace(events=events.get(i, [])) for i in range(n)], pattern_bars={})


def bar(i, price, signal="WAIT"):
    return SimpleNamespace(symbol="X/USDT", timestamp=float(i), price=price, signal=signal,
                           confluence_label="STRONG", date="")


def run(cls, data, signals=None):
    pm = cls(10_000, ["X/USDT"])
    for i, p in enumerate(data.usd["close"]):
        if hasattr(pm, "set_context"):                 # as run_b1 does
            pm.set_context("X", i, data)
        pm.process_bar(bar(i, float(p), (signals or {}).get(i, "WAIT")))
    return pm, [(int(t.exit_time), t.exit_signal, round(t.exit_price, 4), round(t.size_pct, 3)) for t in pm.trades]


B1 = _costed_pm_class()
H60 = scenario_pm_class(r2.H60)
ON, OFF = (lambda ts: True), (lambda ts: False)


class GateTests(unittest.TestCase):
    def test_gate_blocks_a_breakdown_exit_outside_risk_off(self):
        data = sd(opens=[100, 100, 99, 98, 95, 97], closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(98)]})
        cls = r2.breakdown_exit_class(B1, gate=OFF)
        pm, trades = run(cls, data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [])
        self.assertIn("X/USDT", pm.positions)
        self.assertEqual(cls.skipped, [{"symbol": "X", "entry": 0.0, "bd_bar": 3, "ts": 3.0}])

    def test_gate_allows_the_exit_inside_risk_off(self):
        data = sd(opens=[100, 100, 99, 98, 95, 97], closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(98)]})
        cls = r2.breakdown_exit_class(B1, gate=ON)
        pm, trades = run(cls, data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(4, "BREAKDOWN", 95.0, 1.0)])
        self.assertEqual(pm.trades[0].tags, {"bd_bar": 3, "fill_bar": 4})
        self.assertEqual(cls.skipped, [])

    def test_gate_is_read_on_the_breakdown_close_not_at_the_fill(self):
        data = sd(opens=[100, 100, 99, 98, 95, 97], closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(98)]})
        _, trades = run(r2.breakdown_exit_class(B1, gate=lambda ts: ts == 3.0), data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(4, "BREAKDOWN", 95.0, 1.0)])

    def test_a_later_breakdown_inside_risk_off_still_exits(self):
        data = sd(opens=[100, 100, 99, 98, 97, 96, 96], closes=[100, 99, 98, 97, 97, 96, 96],
                  events={2: [breakdown(99)], 4: [breakdown(98)]})
        cls = r2.breakdown_exit_class(B1, gate=lambda ts: ts >= 4)
        _, trades = run(cls, data, signals={0: "STRONG_LONG"})
        self.assertEqual(trades, [(5, "BREAKDOWN", 96.0, 1.0)])
        self.assertEqual([s["bd_bar"] for s in cls.skipped], [2])

    def test_each_class_keeps_its_own_skip_log(self):
        data = sd(opens=[100] * 6, closes=[100, 99, 98, 96, 97, 97], events={3: [breakdown(98)]})
        a, b = r2.breakdown_exit_class(B1, gate=OFF), r2.breakdown_exit_class(B1, gate=OFF)
        run(a, data, signals={0: "STRONG_LONG"})
        self.assertEqual((len(a.skipped), len(b.skipped)), (1, 0))

    def test_parents_reproduce_with_the_gate_off_and_r2_with_it_on(self):
        data = sd(opens=[100] * 70, closes=[100] * 5 + [95] * 30 + [93] * 35,
                  events={5: [breakdown(97)], 40: [breakdown(94)]})
        signals = {0: "STRONG_LONG", 7: "TRIM", 9: "STRONG_LONG"}
        for parent in (B1, H60):
            _, p = run(parent, data, signals=signals)
            _, off = run(r2.breakdown_exit_class(parent, gate=OFF), data, signals=signals)
            _, on = run(r2.breakdown_exit_class(parent, gate=ON), data, signals=signals)
            _, ungated = run(r2.breakdown_exit_class(parent), data, signals=signals)
            self.assertEqual(off, p)
            self.assertEqual(on, ungated)
            self.assertNotEqual(on, p)                  # the rule does fire on this path


def weekly(closes, start_ms=1_600_000_000_000 - 1_600_000_000_000 % DAY_MS):
    """Weekly bars keyed to their final day's open, as the replay cache stores BTC."""
    n = len(closes)
    ts = np.array([start_ms + (7 * k + 6) * DAY_MS for k in range(n)], float)
    c = np.array(closes, float)
    return {"timestamp": ts, "open": c, "high": c, "low": c, "close": c, "volume": np.ones(n)}


class RoBmsbTests(unittest.TestCase):
    def setUp(self):
        self.w = weekly([100.0] * 30 + [60.0, 100.0, 60.0, 60.0, 100.0])
        self.gate = ro.ro_bmsb_gate(self.w)
        self.key = [float(t) for t in self.w["timestamp"]]

    def test_one_completed_week_below_is_enough(self):
        self.assertFalse(self.gate(self.key[29]))
        self.assertTrue(self.gate(self.key[30]))        # first week below, on its final day's close
        self.assertFalse(self.gate(self.key[31]))
        b1 = _compute_bmsb_filter(self.w)                # B1's entry gate needs two weeks
        self.assertFalse(_is_bmsb_blocked(b1, sorted(b1), self.key[30]))
        self.assertTrue(_is_bmsb_blocked(b1, sorted(b1), self.key[33]))

    def test_a_week_counts_only_once_it_is_complete(self):
        for d in range(1, 7):                            # Monday .. Saturday of the drop week
            self.assertFalse(self.gate(self.key[30] - d * DAY_MS))
        self.assertTrue(self.gate(self.key[30] + 3 * DAY_MS))    # mid-week: last completed week

    def test_no_look_ahead(self):
        days = np.arange(self.key[20], self.key[-1] + 7 * DAY_MS, DAY_MS)
        for ts in days:
            k = int(np.sum(self.w["timestamp"] <= ts))
            past = {f: v[:k] for f, v in self.w.items()}
            self.assertEqual(self.gate(ts), ro.ro_bmsb_gate(past)(ts), ts)
        changed = weekly([100.0] * 30 + [60.0, 100.0, 60.0, 10.0, 1000.0])   # different future weeks
        self.assertEqual([self.gate(t) for t in self.key[:32]], [ro.ro_bmsb_gate(changed)(t) for t in self.key[:32]])

    def test_missing_series_is_never_risk_off(self):
        self.assertFalse(ro.ro_bmsb_gate(None)(self.key[30]))


def result(reason, regime="FLAT"):
    return SimpleNamespace(signal_reason=reason, regime=regime)


class RoConsTests(unittest.TestCase):
    def test_reads_the_replays_recorded_consensus(self):
        bars = {("A", 1.0): result("MARKUP + z=0.1 + conf=40% + consensus=RISK-OFF + heat=10", "MARKUP"),
                ("B", 1.0): result("MARKDOWN + consensus RISK-OFF", "MARKDOWN"),
                ("A", 2.0): result("MARKDOWN regime (consensus=MIXED)", "MARKDOWN"),
                ("B", 2.0): result("MARKDOWN regime (consensus=MIXED)", "MARKDOWN")}
        self.assertEqual(ro.replay_consensus(bars), {1.0: "RISK-OFF", 2.0: "MIXED"})
        g = ro.ro_cons_gate(bars)
        self.assertTrue(g(1.0))
        self.assertFalse(g(2.0))                         # recorded MIXED wins over a recount of the stored regimes
        self.assertFalse(g(3.0))                         # no replay results that day

    def test_recounts_with_the_live_function_when_nothing_is_recorded(self):
        regimes = ["MARKDOWN", "MARKDOWN", "MARKDOWN", "ACCUM"]
        bars = {(s, 5.0): result("Exhaustion climax detected", r) for s, r in zip("ABCD", regimes)}
        self.assertEqual(ro.replay_consensus(bars)[5.0], compute_consensus([{"regime": r} for r in regimes])["consensus"])
        self.assertTrue(ro.ro_cons_gate(bars)(5.0))
        bars[("C", 5.0)] = result("Exhaustion climax detected", "MARKUP")
        self.assertFalse(ro.ro_cons_gate(bars)(5.0))     # 2 of 4 in MARKDOWN: MIXED

    def test_conflicting_records_are_an_error(self):
        bars = {("A", 1.0): result("x + consensus=RISK-OFF"), ("B", 1.0): result("x + consensus=MIXED")}
        with self.assertRaises(ValueError):
            ro.replay_consensus(bars)

    def test_no_look_ahead(self):
        bars = {("A", 1.0): result("consensus=RISK-OFF"), ("A", 2.0): result("consensus=MIXED"),
                ("A", 3.0): result("none", "MARKDOWN")}
        full = ro.replay_consensus(bars)
        for ts in (1.0, 2.0, 3.0):
            past = {k: v for k, v in bars.items() if k[1] <= ts}
            self.assertEqual(ro.replay_consensus(past)[ts], full[ts])
        bars[("A", 4.0)] = result("consensus=RISK-ON")
        bars[("B", 4.0)] = result("consensus=RISK-ON")
        self.assertEqual({t: ro.replay_consensus(bars)[t] for t in (1.0, 2.0, 3.0)}, full)


class DeclarationTests(unittest.TestCase):
    def test_declared_variants_gates_and_parents(self):
        self.assertEqual(ro.VARIANTS, ("RO1-B1", "RO2-B1", "RO1-H60", "RO2-H60"))
        self.assertEqual(ro.GATE_OF, {"RO1-B1": "RO-BMSB", "RO2-B1": "RO-CONS", "RO1-H60": "RO-BMSB", "RO2-H60": "RO-CONS"})
        self.assertEqual(ro.PARENTS["RO1-B1"], "B1")
        self.assertEqual(ro.PARENTS["RO2-H60"], "F0-t60-s12-nosig")

    def test_classes_parents_and_context_rows(self):
        replay = {"bars": {("A", 1.0): result("consensus=RISK-OFF")}, "weekly_btc": weekly([100.0] * 30)}
        classes = ro.pm_classes(replay)
        self.assertEqual(set(classes), set(ro.ROWS))
        self.assertIsNone(classes["B1"])                 # run_b1's own costed PositionManager
        data = sd(opens=[100] * 70, closes=[100] * 5 + [95] * 65, events={5: [breakdown(97)]})
        signals = {0: "STRONG_LONG", 10: "TRIM"}
        self.assertEqual(run(classes["F0-t60-s12-nosig"], data, signals)[1], run(H60, data, signals)[1])
        self.assertEqual(run(classes["R2-H60"], data, signals)[1], run(r2.breakdown_exit_class(H60), data, signals)[1])
        fresh = ro.pm_classes(replay)
        self.assertIsNot(fresh["RO1-B1"].skipped, classes["RO1-B1"].skipped)

    def test_skipped_stats_use_the_first_skipped_close_per_position(self):
        n = 40
        data = {"X": sd(opens=[100.0] * n, closes=[100.0] * 23 + [90.0] * 17)}
        data["X"].usd["open"][4] = 80.0
        skipped = [{"symbol": "X", "entry": 1.0, "bd_bar": 5, "ts": 5.0},
                   {"symbol": "X", "entry": 1.0, "bd_bar": 3, "ts": 3.0},
                   {"symbol": "X", "entry": 9.0, "bd_bar": 30, "ts": 30.0}]
        s = ro.skipped_stats(skipped, data)
        self.assertEqual((s["closes"], s["positions"]), (3, 2))
        self.assertEqual((s["fwd20"]["n"], s["fwd20"]["excluded"]), (1, 1))      # bar 50 is past the data
        self.assertAlmostEqual(s["fwd20"]["mean_pct"], (90 / 80 - 1) * 100)       # open of bar 4, close of bar 23

    def test_holdout_is_never_studied_or_loaded(self):
        from backtest.larsson_scenarios import _data_end
        from backtest.larsson_study import HOLDOUT, windows
        self.assertEqual([w["index"] for w in ro.study_windows()], list(range(1, 10)))
        self.assertEqual(_data_end(), windows()[HOLDOUT - 2]["end"])            # data stops at the end of W9
        self.assertLessEqual(_data_end(), windows()[HOLDOUT - 1]["start"])


if __name__ == "__main__":
    unittest.main()
