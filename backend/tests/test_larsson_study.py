import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backtest import larsson_study as ls

DAY = 86_400_000.0


class WindowTests(unittest.TestCase):
    def test_ten_frozen_180_day_windows_with_last_as_holdout(self):
        w = ls.windows()
        self.assertEqual(len(w), 10)
        self.assertTrue(all(x["end_ms"] - x["start_ms"] == 180 * DAY for x in w))
        self.assertTrue(all(a["end_ms"] == b["start_ms"] for a, b in zip(w, w[1:])))
        self.assertEqual(w[-1]["end"], ls.FREEZE_END)
        self.assertEqual([x["index"] for x in w if x["holdout"]], [10])


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [mock.patch.object(ls, "RUNS_DIR", root),
                        mock.patch.object(ls, "HOLDOUT_MARKER", root / ".marker"),
                        mock.patch.object(ls, "study")]
        for p in self.patches:
            p.start()
        self.root = root

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_walk_forward_refuses_the_holdout_window(self):
        with self.assertRaises(SystemExit):
            ls.main(["--out", "x", "--windows", "1-10"])
        ls.study.assert_not_called()

    def test_holdout_runs_once_only(self):
        frozen = self.root / "frozen.json"
        frozen.write_text('{"risk_pct": 0.01, "tol": 0.015, "max_last": 30, "b": 0.01}')
        ls.main(["--out", "h1", "--holdout", "--frozen", str(frozen)])
        self.assertEqual(ls.study.call_count, 1)
        self.assertTrue((self.root / ".marker").exists())
        with self.assertRaises(SystemExit):
            ls.main(["--out", "h2", "--holdout", "--frozen", str(frozen)])
        self.assertEqual(ls.study.call_count, 1)

    def test_holdout_needs_frozen_parameters(self):
        with self.assertRaises(SystemExit):
            ls.main(["--out", "h", "--holdout"])
        self.assertFalse((self.root / ".marker").exists())

    def test_outputs_are_never_overwritten(self):
        (self.root / "taken").mkdir()
        with self.assertRaises(SystemExit):
            ls.main(["--out", "taken"])


class MetricTests(unittest.TestCase):
    def test_metrics_on_a_known_curve(self):
        curve = [(i * DAY, 10_000 * (1.001 ** (i + 1))) for i in range(180)]
        m = ls.metrics(curve, [0.5] * 180, [{"pnl": 10.0, "r": 0.5, "bars": 5}, {"pnl": -5.0, "r": -0.25, "bars": 3}], 180)
        self.assertAlmostEqual(m["total_return_pct"], (1.001 ** 180 - 1) * 100, places=6)
        self.assertEqual(m["max_dd_pct"], 0.0)
        self.assertEqual(m["win_rate_pct"], 50.0)
        self.assertAlmostEqual(m["payoff"], 2.0)
        self.assertAlmostEqual(m["expectancy_r"], 0.125)
        self.assertAlmostEqual(m["exposure_adj_return_pct"], m["total_return_pct"] / 0.5)

    def test_drawdown(self):
        curve = [(0, 10_000.0), (DAY, 12_000.0), (2 * DAY, 9_000.0), (3 * DAY, 11_000.0)]
        m = ls.metrics(curve, [1] * 4, [], 4)
        self.assertAlmostEqual(m["max_dd_pct"], -25.0)
        self.assertTrue(math.isfinite(m["sharpe"]))


if __name__ == "__main__":
    unittest.main()
