import unittest
from types import SimpleNamespace

import numpy as np

from backtest.larsson_scenarios import H1, Scenario, family, scenario_pm_class
from backtest import larsson_scenarios as sc_mod


def sd(states, e32=None, atr=None):
    n = len(states)
    return SimpleNamespace(ll={"state": states, "e32": np.array(e32 if e32 is not None else [np.nan] * n)},
                           atr=np.array(atr if atr is not None else [np.nan] * n))


def bar(i, price, signal="WAIT"):
    return SimpleNamespace(symbol="X/USDT", timestamp=float(i), price=price, signal=signal,
                           confluence_label="STRONG", date="")


def run(scenario, prices, states, signals=None, **kw):
    pm = scenario_pm_class(scenario)(10_000, ["X/USDT"])
    data = sd(states, **kw)
    exits = []
    for i, p in enumerate(prices):
        pm.set_context("X", i, data)
        t = pm.process_bar(bar(i, p, (signals or {}).get(i, "WAIT")))
        if t is not None:
            exits.append((i, t.exit_signal))
    return pm, exits


class ExitRuleTests(unittest.TestCase):
    def test_flip_waits_for_gold_before_blue_when_opened_in_blue(self):
        states = ["blue", "blue", "grey", "gold", "gold", "grey", "blue", "blue"]
        _, exits = run(Scenario(False, "flip", None, False), [100] * 8, states, signals={0: "STRONG_LONG"})
        self.assertEqual(exits, [(6, "LL_FLIP")])

    def test_grey_exit_after_gold(self):
        states = ["gold", "gold", "grey", "blue"]
        _, exits = run(Scenario(False, "grey", None, False), [100] * 4, states, signals={0: "STRONG_LONG"})
        self.assertEqual(exits, [(2, "LL_GREY")])

    def test_e32_needs_a_close_above_first(self):
        states = ["grey"] * 5
        e32 = [105, 105, 99, 99, 101]
        prices = [100, 100, 100, 100, 100]
        _, exits = run(Scenario(False, "e32", None, False), prices, states, signals={0: "STRONG_LONG"}, e32=e32)
        self.assertEqual(exits, [(4, "E32")])

    def test_atr_chandelier(self):
        prices = [100, 110, 120, 106, 104]
        _, exits = run(Scenario(False, "atr3", None, False), prices, ["grey"] * 5, signals={0: "STRONG_LONG"}, atr=[5] * 5)
        self.assertEqual(exits, [(4, "ATR3")])          # 104 < 120 - 15

    def test_time_exit_and_stop(self):
        _, exits = run(Scenario(False, "t30", None, False), [100] * 40, ["grey"] * 40, signals={0: "STRONG_LONG"})
        self.assertEqual(exits, [(30, "T30")])
        _, exits = run(Scenario(False, "t60", 0.12, False), [100, 95, 87], ["grey"] * 3, signals={0: "STRONG_LONG"})
        self.assertEqual(exits, [(2, "STOP_12")])

    def test_rcce_exit_signals_only_when_enabled(self):
        sig = {0: "STRONG_LONG", 2: "TRIM"}
        _, off = run(Scenario(False, "t60", None, False), [100] * 4, ["grey"] * 4, signals=sig)
        _, on = run(Scenario(False, "t60", None, True), [100] * 4, ["grey"] * 4, signals=sig)
        self.assertEqual(off, [])
        self.assertEqual(on, [(2, "TRIM")])

    def test_decay_exit_is_off(self):
        # 25 WAIT bars would trigger B1's decay exit; scenarios never decay out.
        _, exits = run(Scenario(False, "t60", None, False), [100] * 26, ["grey"] * 26, signals={0: "STRONG_LONG"})
        self.assertEqual(exits, [])


class FamilyTests(unittest.TestCase):
    def test_family_size_and_named_hypothesis(self):
        fam = family()
        self.assertEqual(len(fam), 78)
        self.assertEqual(len({s.name for s in fam}), 78)
        self.assertIn(H1, fam)
        self.assertFalse(any(s.exit == "blue" and not s.veto for s in fam))

    def test_reality_check_finds_no_edge_in_noise(self):
        rng = np.random.default_rng(1)
        n = 600
        base = rng.normal(0, 0.01, n)
        results = {"B1": {"daily": base}}
        names = [f"s{k}" for k in range(20)]
        for nm in names:
            results[nm] = {"daily": base + rng.normal(0, 0.002, n)}
        rc = sc_mod.reality_check(results, names, reps=400)
        self.assertGreater(rc["family_p"], 0.1)

    def test_reality_check_detects_a_real_edge(self):
        rng = np.random.default_rng(2)
        n = 600
        base = rng.normal(0, 0.01, n)
        results = {"B1": {"daily": base}, "edge": {"daily": base + 0.002 + rng.normal(0, 0.002, n)}}
        rc = sc_mod.reality_check(results, ["edge"], reps=400)
        self.assertLess(rc["family_p"], 0.05)


if __name__ == "__main__":
    unittest.main()
