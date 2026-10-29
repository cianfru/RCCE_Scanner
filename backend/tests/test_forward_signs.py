"""Forward test of funding and whales (forward_signs.py), as declared in docs/reviews/funding-whales-forward-test.md."""
import unittest

import numpy as np

import forward_signs as F


def wallets_with(net_by_day):
    cols = ["day", "wallets", "positioned", "long", "short", "long_usd", "short_usd", "sampled", "rebuilt"]
    rows = [[d, 100, 80, 50 + round(50 * v), 50 - round(50 * v), 0, 0, 10, 0] for d, v in net_by_day.items()]
    return {"columns": cols, "groups": {"whales": rows}, "coin_columns": ["day", "long", "short", "rebuilt"], "coins": {}}


class ReadingTests(unittest.TestCase):
    def test_funding_is_the_7_day_mean_of_the_two_coins(self):
        rows = [[d, 10.0, 20.0] for d in range(1, 5)] + [[5, 30.0, 40.0]]
        r = F.funding_reading(rows)
        self.assertNotIn(4, r)
        self.assertEqual(r[5], (15 * 4 + 35) / 5)

    def test_whales_net_is_long_minus_short_over_the_group(self):
        r = F.whales_reading(wallets_with({1: 0.2}))
        self.assertAlmostEqual(r[1], 0.2)
        self.assertEqual(F.whales_reading({"coin_columns": ["day", "long", "short", "rebuilt"],
                                           "coins": {"BTC": {"whales": [[1, 3, 1, 0]]}}}, "BTC"), {1: 0.5})


class TestTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.days = list(range(F.FROM_DAY - 400, F.FROM_DAY + 500))
        self.x = {d: float(rng.normal()) for d in self.days}
        self.noise = {d: float(rng.normal()) for d in self.days}

    def run_test(self, link, last_day, sign=-1):
        out = lambda d: None if d + F.H > last_day else link * 10 * self.x[d] + self.noise[d]   # noqa: E731
        past = lambda d: self.noise[d - 1]                                                      # noqa: E731
        return F.test(self.x, out, past, sign, last_day)

    def test_only_forward_days_with_closed_outcomes_count_and_the_status_follows_their_number(self):
        r = self.run_test(-1, F.FROM_DAY + 30 + 99)
        self.assertEqual((r["days"], r["status"]), (100, "collecting"))
        self.assertEqual(self.run_test(-1, F.FROM_DAY + 30 + 199)["status"], "interim")
        self.assertNotIn("verdict", self.run_test(-1, F.FROM_DAY + 30 + 199))

    def test_the_verdict_takes_the_first_365_days_and_the_declared_side(self):
        r = self.run_test(-1, F.FROM_DAY + 30 + 450)
        self.assertEqual(r["status"], "verdict")
        self.assertEqual(r["verdict"], "met")
        self.assertLess(r["partial"], -0.15)
        self.assertEqual(self.run_test(+1, F.FROM_DAY + 30 + 450)["verdict"], "not met", "the wrong side never passes")
        self.assertEqual(self.run_test(0, F.FROM_DAY + 30 + 450)["verdict"], "not met", "no link, no pass")

    def test_record_puts_the_pieces_together(self):
        days = [[d, 100, 0.5, 0, 0, 0, 0, 100.0 + d] for d in self.days]
        rec = F.record(days, lambda a, b: float(b - a), [[d, 10.0, 12.0] for d in self.days], wallets_with({d: 0.1 for d in self.days}))
        self.assertEqual(rec["through"], self.days[-1])
        self.assertIn(rec["funding"]["status"], ("collecting", "interim", "verdict"))
        self.assertIsNotNone(rec["funding"]["reported"]["tails"])


if __name__ == "__main__":
    unittest.main()
