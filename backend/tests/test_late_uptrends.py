"""Late broad uptrends (research/late_uptrends.py): runs, roll-overs, heat turns, matching and cells as declared in
docs/reviews/late-uptrends-study.md."""
import unittest

from research import late_uptrends as L


def rows_of(shares, fg=None, traders=None, start=1000):
    return [{"day": start + i, "n": 100, "uptrend": s, "downtrend": 0.0, "basing": None if s is None else 1 - s,
             "fg": None if fg is None else fg[i], "traders": None if traders is None else traders[i], "btc": 100.0}
            for i, s in enumerate(shares)]


class RunTests(unittest.TestCase):
    def test_a_run_ends_on_the_first_day_of_five_below_and_short_dips_stay_inside(self):
        shares = [0.5] * 3 + [0.6] * 5 + [0.5] * 4 + [0.6] * 3 + [0.5] * 6 + [0.6]
        state, rs = L.runs(rows_of(shares))
        self.assertEqual([(r["start"], r["end"]) for r in rs], [(1003, 1015), (1021, None)])
        self.assertEqual(state[1010]["age"], 7, "a dip day of 4 stays in the run, its age counted from the start")
        self.assertFalse(state[1019]["on"], "the 5th day below turns it off")
        self.assertTrue(state[1018]["on"])
        self.assertFalse(rs[0]["first"])

    def test_a_run_on_the_first_day_has_no_known_start(self):
        _, rs = L.runs(rows_of([0.7, 0.7, 0.4, 0.4, 0.4, 0.4, 0.4]))
        self.assertTrue(rs[0]["first"])

    def test_roll_over_is_20_points_under_the_high_so_far(self):
        shares = [0.6, 0.8, 0.95, 0.85, 0.76, 0.74, 0.9]
        _, rs = L.runs(rows_of(shares))
        share = {1000 + i: s for i, s in enumerate(shares)}
        self.assertEqual(L.roll_over(rs[0], share), 1005, "95 -> 76 is 19 points; 74 is 21")
        self.assertEqual(L.roll_over(rs[0], {**share, 1004: 0.75}), 1004, "exactly 20 points counts")


class HeatTests(unittest.TestCase):
    def test_heat_is_the_page_average_and_turns_follow_the_page_rule(self):
        rows = rows_of([0.9, 0.9, 0.5], fg=[80, 80, 50], traders=[0.85, None, None])
        self.assertEqual([round(h, 2) for _, h in L.heat_series(rows)], [85.0, 85.0, 50.0])
        series = [(1, 60), (2, 78), (3, 82), (4, 80), (5, 74), (6, 71), (7, 65), (8, 76), (9, 79)]
        self.assertEqual(L.heat_turns(series), [(6, "cooling", 3, 82)], "as frontend/src/utils/marketHeat.test.js")
        cold = [(1, 30), (2, 22), (3, 18), (4, 24), (5, 29)]
        self.assertEqual(L.heat_turns(cold), [(5, "lifting", 3, 18)])


class CellTests(unittest.TestCase):
    def test_cells_need_a_broad_uptrend_and_split_by_age_and_greed(self):
        r = {"uptrend": 0.7, "fg": 72}
        self.assertEqual(L.cell_of({"on": True, "age": 59}, r), "early_greedy")
        self.assertEqual(L.cell_of({"on": True, "age": 60}, r), "late_greedy")
        self.assertEqual(L.cell_of({"on": True, "age": 60}, {"uptrend": 0.7, "fg": 69}), "late")
        self.assertIsNone(L.cell_of({"on": True, "age": 80}, {"uptrend": 0.5, "fg": 80}), "a dip day under 55% is no cell")
        self.assertIsNone(L.cell_of({"on": False}, r))


class MatchTests(unittest.TestCase):
    def test_matched_days_are_near_the_share_and_away_from_turns_of_the_kind(self):
        shares = [0.5 + 0.001 * (i % 7) for i in range(120)]
        rows = rows_of(shares)
        out = L.Outcomes(rows, lambda a, b: 0.0, rows[-1]["day"])
        pool = L.matched_days(rows, out, 1010, [1010, 1050])
        self.assertTrue(all(not (1010 <= d <= 1040) and not (1050 <= d <= 1080) for d in pool))
        self.assertTrue(all(d + 30 <= rows[-1]["day"] for d in pool), "only days with a complete 30 days")
        self.assertIn(1000, pool)

    def test_windows_past_the_last_day_are_censored(self):
        rows = rows_of([0.5] * 40)
        out = L.Outcomes(rows, lambda a, b: 1.0, rows[-1]["day"])
        self.assertEqual(out.breadth(1000, 30), 0.0)
        self.assertIsNone(out.breadth(1020, 30))
        self.assertIsNone(out.alt_change(1020, 30))
        self.assertIsNone(out.alt_low(1000), "the 60-day path needs every 5-day step")


if __name__ == "__main__":
    unittest.main()
