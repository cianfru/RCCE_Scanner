"""After-the-spike picture on the coin chart: mean lines and the spike anchor."""
import unittest

import numpy as np

from engines.rcce_engine import LEN_LONG, LEN_REGRESSION, Z_SCALE, Z_SMOOTH, _calc_zscore_hybrid
from engines.spike_zone import last_spike, mean_levels, zone


def series(n=700, seed=3):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))


class SpikeZoneTests(unittest.TestCase):
    def test_mean_levels_invert_the_z_score(self):
        c = series()
        z = _calc_zscore_hybrid(c, LEN_LONG, LEN_REGRESSION, Z_SMOOTH, Z_SCALE)
        lv = mean_levels(c, ks=(float(z[-1]),))
        self.assertAlmostEqual(lv[float(z[-1])][-1], c[-1], delta=c[-1] * 1e-6)

    def test_spike_anchor_and_superseded(self):
        z = np.array([0.5] * 10 + [2.2, 2.7, 3.0, 2.1] + [1.0] * 6)
        c = np.array([10.0] * 10 + [11, 13, 14, 12] + [11] * 6)
        s = last_spike(z, c)
        self.assertEqual((s["run_start"], s["run_end"], s["anchor_index"]), (10, 13, 14))
        self.assertEqual((s["peak"], s["superseded"]), (14.0, False))
        c2 = c.copy()
        c2[-1] = 15.0
        self.assertTrue(last_spike(z, c2)["superseded"])
        self.assertIsNone(last_spike(np.zeros(20), c))
        running = last_spike(np.array([0.5] * 10 + [2.2, 2.7]), np.array([10.0] * 10 + [11, 13]))
        self.assertIsNone(running["anchor_index"])

    def test_zone_from_seed(self):
        zn = zone("1d", 100.0)
        self.assertIsNotNone(zn)
        self.assertLess(zn["bottom"], zn["median_price"])
        self.assertLess(zn["median_price"], zn["top"])
        self.assertLess(zn["from_bar"], zn["median_bar"])
        self.assertIsNone(zone("15m", 100.0))


if __name__ == "__main__":
    unittest.main()
