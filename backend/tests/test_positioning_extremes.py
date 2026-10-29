"""Profitable traders at extremes (research/positioning_extremes.py): episodes, outcomes and comparisons as declared in
docs/reviews/positioning-extremes-study.md."""
import unittest

from research import positioning_extremes as P

short = lambda v: v <= P.SHORT_LINE      # noqa: E731
long_ = lambda v: v >= P.LONG_LINE       # noqa: E731


class EpisodeTests(unittest.TestCase):
    def test_a_return_inside_for_up_to_14_days_is_the_same_episode(self):
        r = [(d, 0.5) for d in range(100)]
        for d in (10, 11, 12, 20, 40):                     # 10-20: one episode (8 days inside); 40: a new one
            r[d] = (d, 0.25 if d != 11 else 0.2)
        eps = P.episodes(r, short, low=True)
        self.assertEqual([(e["start"], e["end"], e["days"]) for e in eps], [(10, 20, 4), (40, 40, 1)])
        self.assertEqual(eps[0]["extreme"], 11)
        self.assertEqual(eps[0]["back"], 21, "the first day back inside the line after the episode")
        self.assertEqual(eps[0]["reading"], 0.25)

    def test_the_long_side_takes_the_highest_reading(self):
        r = [(0, 0.5), (1, 0.87), (2, 0.9), (3, 0.88), (4, 0.5)]
        e = P.episodes(r, long_, low=False)[0]
        self.assertEqual((e["start"], e["extreme"], e["back"]), (1, 2, 4))


class OutcomeTests(unittest.TestCase):
    def setUp(self):
        self.btc = {d: 100.0 + d for d in range(200)}

    def test_changes_are_censored_past_the_newest_close(self):
        self.assertEqual(P.change(self.btc, 100, 30), round(100 * (230 / 200 - 1), 1))
        self.assertIsNone(P.change(self.btc, 180, 30))
        self.assertAlmostEqual(P.past_change(self.btc, 100), 100 * (200 / 170 - 1))
        self.assertIsNone(P.past_change(self.btc, 10))

    def test_the_path_names_the_largest_fall_and_rise_and_their_days(self):
        btc = {0: 100.0, 1: 90.0, 2: 120.0, 3: 110.0}
        p = P.path(btc, 0, n=3)
        self.assertEqual((p["fall"], p["fall_day"], p["rise"], p["rise_day"], p["complete"]), (-10.0, 1, 20.0, 2, True))
        self.assertFalse(P.path(btc, 0, n=5)["complete"])

    def test_fifths(self):
        cuts = P.fifths(list(range(100)))
        self.assertEqual(cuts, [20, 40, 60, 80])
        self.assertEqual([P.fifth(v, cuts) for v in (0, 20, 59, 99)], [0, 1, 2, 4])


class ComparisonTests(unittest.TestCase):
    def test_seven_years_counts_runs_after_a_month_at_least_as_bad(self):
        # Two drops of 20% over 30 days, 100 days apart, and a later one at the day studied.
        btc = {}
        for d in range(400):
            btc[d] = 100.0
        for start in (100, 200, 330):
            for k in range(30):
                btc[start + k] = 100.0 * (1 - 0.2 * (k + 1) / 30)
            for k in range(30, 60):
                btc[start + k] = 80.0 + (k - 29)
        out = P.seven_years(btc, 359, "short")
        self.assertEqual([c["start"] for c in out["cases"]], [P.iso(129), P.iso(229)])
        self.assertEqual(out["d7"]["n"], 2)

    def test_the_permutation_draws_from_the_same_past_month_fifths(self):
        btc = {d: 100.0 * (1.01 ** (d % 50)) for d in range(300)}
        days = list(range(40, 250))
        every = {0: days}
        share = P.permutation(btc, [45, 60], every, [10 ** 9] * 4, 30, draws=500)
        self.assertIsNotNone(share)
        self.assertEqual(share, P.permutation(btc, [45, 60], every, [10 ** 9] * 4, 30, draws=500), "seeded")
        self.assertIsNone(P.permutation(btc, [290], every, [10 ** 9] * 4, 30), "a censored start")


class RunTests(unittest.TestCase):
    def test_a_short_history_reads_not_met(self):
        days = list(range(20000, 20120))
        seed = {"rows": [[d, 20 if 20030 <= d < 20036 else 60, 80 if 20030 <= d < 20036 else 40] for d in days]}
        market = {"days": [[d, 100, 0.5, 0, 0, 0.5, 0.0, 50_000.0 + 10 * (d - 19800)] for d in range(19800, 20120)]}
        res = P.run(seed, market, None)
        s = res["short"]
        self.assertEqual([e["start"] for e in s["episodes"]], [P.iso(20030)])
        self.assertEqual(s["checks"]["episodes"], 1)
        self.assertFalse(s["checks"]["enough"])
        self.assertEqual(s["checks"]["verdict"], "not met")
        self.assertEqual(res["long"]["episodes"], [])

    def test_the_out_of_sample_part_reads_the_pages_recorded_days_with_the_shift(self):
        feed = {"crowd": {"columns": ["day", "long", "short", "long_share", "rebuilt"],
                          "rows": [[20755, None, None, 0.2, 1], [20756, 10, 90, 0.1, 0], [20757, 50, 50, 0.5, 0]],
                          "overlap": {"offset_pts": -9.5}}}
        rows, shift = P.readings_from_feed(feed)
        self.assertEqual(rows, [(20756, 0.1), (20757, 0.5)])
        self.assertAlmostEqual(shift, -0.095)


if __name__ == "__main__":
    unittest.main()
