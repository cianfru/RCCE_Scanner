import unittest

import numpy as np

from research.traders_turn import (BAR, CAP, COOL, H, compare, coverage_start, four_hour_closes, position_at,
                                   positions, recent_any, run_starts, stretch, turn_test)


def fill(coin, t, sz, side, start, twap=0):
    return [coin, t, "1", str(sz), side, "", str(start), twap]


class PositionTests(unittest.TestCase):
    def test_position_after_last_fill_strictly_before_t(self):
        # API order: newest first
        s = positions([fill("BTC", 300, 1, "A", 2), fill("BTC", 200, 2, "B", 0)])["BTC"]
        self.assertEqual(position_at(s, [150]).tolist(), [0.0])      # before any fill: start of the next
        self.assertEqual(position_at(s, [200]).tolist(), [0.0])      # a fill at t does not count
        self.assertEqual(position_at(s, [201]).tolist(), [2.0])
        self.assertEqual(position_at(s, [301]).tolist(), [1.0])

    def test_before_first_fill_uses_its_start_position(self):
        s = positions([fill("ETH", 500, 3, "A", 5)])["ETH"]          # already long 5 before the history
        self.assertEqual(position_at(s, [100, 501]).tolist(), [5.0, 2.0])

    def test_never_traded_is_flat_and_excluded_markets_dropped(self):
        self.assertEqual(position_at(None, [1, 2]).tolist(), [0.0, 0.0])
        p = positions([fill("xyz:TSLA", 1, 1, "B", 0), fill("@12", 1, 1, "B", 0), fill("#5", 1, 1, "B", 0),
                       fill("PURR/USDC", 1, 1, "B", 0), fill("SOL", 1, 1, "B", 0)])
        self.assertEqual(sorted(p), ["SOL"])

    def test_same_time_fills_merge_whatever_the_list_order(self):
        # chain 0 -> 1 -> 3 at one millisecond, listed in an order that is not reverse-chronological
        s = positions([fill("BTC", 100, 1, "B", 0), fill("BTC", 100, 2, "B", 1)])["BTC"]
        self.assertEqual(len(s[0]), 1)
        self.assertEqual(position_at(s, [50, 101]).tolist(), [0.0, 3.0])

    def test_fill_older_than_coverage_yields_to_next_recorded_start(self):
        # a TWAP slice at 100 leaves +1; the capped regular list starts at 500 and its first fill
        # records +4 before it, so fills between 100 and 500 are missing
        s = positions([fill("BTC", 600, 1, "A", 4), fill("BTC", 100, 1, "B", 0, 1)])["BTC"]
        self.assertEqual(position_at(s, [550]).tolist(), [1.0])                 # rule applied literally
        self.assertEqual(position_at(s, [550], cover=500).tolist(), [4.0])
        self.assertEqual(position_at(s, [300, 700], cover=500).tolist(), [1.0, 3.0])

    def test_coverage_is_later_of_the_two_capped_lists(self):
        reg = [fill("BTC", 1000 + i, 1, "B", 0) for i in range(CAP)]
        twap = [fill("BTC", 5000 + i, 1, "B", 0, 1) for i in range(CAP)]
        self.assertEqual(coverage_start(reg + twap), 5000)
        self.assertEqual(coverage_start(reg + twap[:10]), 1000)
        self.assertEqual(coverage_start(reg[:10] + twap[:10]), 0)


class StretchAndCloseTests(unittest.TestCase):
    def test_four_hour_close_uses_hour_before_or_latest_inside(self):
        grid = np.array([4 * H, 8 * H, 12 * H])
        hourly = [[0, 1.0], [H, 2.0], [2 * H, 3.0], [3 * H, 4.0], [4 * H, 5.0], [5 * H, 6.0]]
        out = four_hour_closes(hourly, grid)
        self.assertEqual(out[0], 4.0)          # candle opening at 3h
        self.assertEqual(out[1], 6.0)          # 7h missing: latest inside the 4 hours (opens 5h)
        self.assertTrue(np.isnan(out[2]))

    def test_stretch_has_no_look_ahead_and_warms_up(self):
        rng = np.random.default_rng(1)
        c = np.exp(np.cumsum(rng.normal(0, 0.02, 700)))
        full = stretch(c)
        self.assertTrue(np.isnan(full[:199]).all())
        self.assertEqual(full[199], 0.0)                              # factor 0 at 200 bars
        for t in (250, 399, 520, 699):
            self.assertAlmostEqual(full[t], stretch(c[:t + 1])[-1], places=9)


class TurnTests(unittest.TestCase):
    def cmp(self, then, now, covered=None):
        P = np.array([then, now], dtype=float).T                    # wallets x 2 bars
        C = np.ones_like(P, bool) if covered is None else np.array([covered, covered]).T
        return compare(P, C, np.array([10.0, 10.0]), np.array([0]), np.array([1]))

    def test_one_flip_among_five_holders_is_a_20_point_drop(self):
        r = self.cmp([1, 1, 1, 1, 1], [1, 1, 1, 1, -1])
        elig, test, by_share, by_shorts = turn_test(r, np.array([True]))
        self.assertTrue(elig[0] and by_share[0] and test[0])
        self.assertFalse(by_shorts[0])
        r = self.cmp([1, 1, 1, -1, -1], [1, 1, -1, -1, -1])          # 60% -> 40%: float edge
        self.assertTrue(turn_test(r, np.array([True]))[2][0])

    def test_closing_a_long_among_all_longs_is_not_a_turn(self):
        r = self.cmp([1, 1, 1, 1, 1], [1, 1, 1, 1, 0])
        self.assertFalse(turn_test(r, np.array([True]))[1][0])

    def test_two_new_shorts_trigger_and_four_holders_are_not_eligible(self):
        r = self.cmp([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, -1, -1, 0, 0, 0])
        self.assertTrue(turn_test(r, np.array([True]))[3][0])
        r = self.cmp([1, 1, 1, 1, 0], [-1, -1, -1, -1, -1])
        self.assertFalse(turn_test(r, np.array([True]))[0][0])

    def test_nobody_holding_at_t_fails_the_share_test(self):
        r = self.cmp([1, 1, 1, 1, 1], [0, 0, 0, 0, 0])
        self.assertFalse(turn_test(r, np.array([True]))[1][0])

    def test_only_wallets_covered_at_the_start_count(self):
        r = self.cmp([1, 1, 1, 1, 1, 0], [1, 1, 1, 1, -1, -1], covered=[1, 1, 1, 1, 1, 0])
        self.assertEqual((int(r["Sn"][0]), int(r["St"][0])), (1, 0))
        self.assertEqual(float(r["VLn"][0]), 40.0)

    def test_first_bar_of_run_and_72h_cool_down(self):
        times = np.arange(40) * BAR
        test = np.zeros(40, bool)
        test[[2, 3, 4]] = True          # run: event at 2
        test[10] = True                 # 32h later: inside cool-down
        test[20] = True                 # 72h after bar 2: allowed
        test[21] = True                 # same run
        self.assertEqual(run_starts(test, times), [2, 20])
        self.assertEqual(COOL, 18 * BAR)

    def test_recent_any_covers_bar_and_six_before(self):
        t = np.zeros(12, bool)
        t[3] = True
        self.assertEqual(np.where(recent_any(t, 6))[0].tolist(), [3, 4, 5, 6, 7, 8, 9])


if __name__ == "__main__":
    unittest.main()
