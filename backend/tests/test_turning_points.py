"""Turning points (research/turning_points.py): downturns, z-turns, leads and comparisons as declared in
docs/reviews/turning-points-study.md."""
import unittest

from research import late_uptrends as L
from research import turning_points as T


def rows_of(shares, zs=None, start=1000):
    return [{"day": start + i, "n": 100, "uptrend": s, "downtrend": 0.0, "basing": 0.0, "fg": 50, "traders": None,
             "btc": 100.0, "median_z": None if zs is None else zs[i], "band_lo": None} for i, s in enumerate(shares)]


class MoveTests(unittest.TestCase):
    def test_first_move_measures_from_the_extreme_so_far(self):
        days = list(range(6))
        z = dict(zip(days, [0.2, 1.5, 1.2, 0.8, 0.74, 1.6]))
        self.assertEqual(T.first_move(days, z, 0.75, up=False), 4, "1.5 -> 0.8 is 0.7; 0.74 is 0.76 under the high")
        low = dict(zip(days, [-1.0, -1.5, -1.0, -0.76, 0.0, 0.0]))
        self.assertEqual(T.first_move(days, low, 0.75, up=True), 4, "-1.5 -> -0.76 is 0.74 over the low; 0.0 is 1.5")
        self.assertIsNone(T.first_move(days, {d: 0.0 for d in days}, 0.75, up=True))


class DownturnTests(unittest.TestCase):
    def test_a_downturn_runs_from_a_run_end_to_the_next_start(self):
        shares = [0.6] * 5 + [0.3] * 10 + [0.6] * 3
        rows = rows_of(shares)
        state, rs = L.runs(rows)
        dts = T.downturns(rows, rs, state)
        self.assertEqual(len(dts), 1)
        self.assertEqual((dts[0]["start"], dts[0]["end"]), (1005, 1015))
        self.assertEqual(dts[0]["all_days"][0], 1005)
        self.assertEqual(dts[0]["days"][0], 1009, "known on the 5th day under 55%")

    def test_an_ongoing_downturn_has_no_end(self):
        rows = rows_of([0.6] * 3 + [0.3] * 8)
        state, rs = L.runs(rows)
        dts = T.downturns(rows, rs, state)
        self.assertIsNone(dts[0]["end"])
        self.assertEqual(dts[0]["all_days"][-1], 1010)


class BlockTests(unittest.TestCase):
    def test_lead_needs_eight_runs_three_of_four_first_and_ten_days(self):
        pairs = [(0, 15)] * 7 + [(0, -2)]
        self.assertEqual(T.lead_block(pairs)["verdict"], "met")
        self.assertEqual(T.lead_block(pairs[:7])["verdict"], "not met", "seven runs are too few")
        self.assertEqual(T.lead_block([(0, 5)] * 8)["verdict"], "not met", "a 5-day lead is under the bar")
        self.assertEqual(T.lead_block([(0, 15), (None, 3)])["runs"], 1, "runs without both are left out")

    def test_verdict_block_compares_with_each_events_pool(self):
        rows = rows_of([0.5] * 200)
        alt = {d: (-30.0 if d % 20 == 0 else 0.0) for d in range(1000, 1200)}
        out = L.Outcomes(rows, lambda a, b: alt.get(a) if b - a in L.STEPS else None, rows[-1]["day"])
        events = [1000 + 20 * k for k in range(8)]
        pool = [d for d in range(1001, 1130) if d % 20]
        v = T.verdict_block(out, events, [pool] * 8, "alt30", T.PRICE_EDGE, -1)
        self.assertEqual(v["verdict"], "met")
        self.assertEqual(v["median_excess"], -30.0)
        self.assertEqual(T.verdict_block(out, events[:7], [pool] * 7, "alt30", T.PRICE_EDGE, -1)["verdict"], "not met")


if __name__ == "__main__":
    unittest.main()
