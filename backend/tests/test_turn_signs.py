"""Which readings come before turns (research/turn_signs.py): ranks, (partial) rho, the halves and tails as declared in
docs/reviews/turn-signs-study.md."""
import unittest

import numpy as np

from research import turn_signs as S


class StatTests(unittest.TestCase):
    def test_ranks_share_ties(self):
        self.assertEqual(S.ranks(np.array([3.0, 1.0, 3.0, 2.0])).tolist(), [2.5, 0.0, 2.5, 1.0])

    def test_spearman_and_the_partial_clear_the_control(self):
        rng = np.random.default_rng(1)
        z = rng.normal(size=500)
        x = z + 0.1 * rng.normal(size=500)
        y = z + 0.1 * rng.normal(size=500)
        self.assertGreater(S.spearman(x, y), 0.9, "both follow z")
        self.assertLess(abs(S.spearman(x, y, z)), 0.15, "nothing left once z is cleared")
        self.assertAlmostEqual(S.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)

    def test_block_interval_brackets_a_clear_relation(self):
        x = np.arange(300, dtype=float)
        lo, hi = S.block_interval(x, x + np.sin(x), boot=200)
        self.assertGreater(lo, 0.8)
        self.assertTrue(np.isnan(S.block_interval(x[:40], x[:40])[0]), "too short for 30-day blocks")


class CheckTests(unittest.TestCase):
    def table(self, f):
        rng = np.random.default_rng(2)
        t = {}
        for i in range(1000):
            x = rng.normal()
            t[1000 + i] = {"feat": x, "alt30": f(x) + rng.normal(), "alt_past30": rng.normal()}
        return t

    def test_a_reading_survives_only_with_the_same_clear_sign_in_both_halves(self):
        c = S.check_feature(self.table(lambda x: -10 * x), "feat")   # tails need 5 points
        self.assertTrue(c["survives"])
        self.assertTrue(c["adds_beyond_momentum"])
        self.assertTrue(c["top_tail"] and c["bottom_tail"])
        self.assertLess(c["halves"][0]["rho"], 0)
        noise = S.check_feature(self.table(lambda x: 0.0), "feat")
        self.assertFalse(noise["survives"])
        self.assertFalse(noise["top_tail"])

    def test_short_series_are_left_out(self):
        self.assertEqual(S.check_feature({1: {"feat": 1.0, "alt30": 1.0, "alt_past30": 0.0}}, "feat")["note"], "too short")


if __name__ == "__main__":
    unittest.main()
