"""The 0.618 to 0.66 retracement zone study: swings, touches of a depth, the race after a touch, the trade."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research import fib_zone as F
from research import value_area_rule as V

DAY = V.DAY_MS
T0 = 1_788_739_200_000            # Monday 2026-09-07 00:00 UTC


def candles(prices, start=T0):
    """5-minute candles that walk through ``prices`` (each candle spans from the previous price to its own)."""
    p = np.asarray(prices, dtype=float)
    prev = np.concatenate(([p[0]], p[:-1]))
    return {"ts": start + np.arange(len(p)) * V.BAR_MS, "open": prev, "high": np.maximum(prev, p), "low": np.minimum(prev, p),
            "close": p, "volume": np.ones(len(p)), "taker": np.full(len(p), 0.5)}


class SwingTests(unittest.TestCase):
    def test_a_swing_is_confirmed_when_price_comes_back_k_atrs(self):
        # ATR of 1 throughout. Up to 120 on day 5, back to 115.5 on day 7 (4.5 under): the high is confirmed there.
        high = np.array([101, 102, 103, 110, 115, 120, 119, 117, 112, 108, 113, 118.0])
        low = high - 1.0
        low[7] = 115.5
        atr = np.ones(len(high))
        piv = F.swings(high, low, atr, k=4.0)
        self.assertEqual(piv[0], ("H", 120.0, 5, 7))
        # The low after it: 107 on day 9; day 11's high of 118 is 11 above: confirmed on the first day 4 above (day 10: 113 >= 111).
        self.assertEqual(piv[1], ("L", 107.0, 9, 10))

    def test_no_swing_without_a_reversal(self):
        high = np.arange(100, 120, dtype=float)
        self.assertEqual(F.swings(high, high - 1, np.ones(20), k=4.0), [])


class TouchTests(unittest.TestCase):
    def test_first_touch_of_each_depth_after_each_new_top(self):
        # Base 100, top 160 (set by the second candle). Then down to 130 (depth 0.5), up to 140, down to 122 (0.618+).
        d = candles([150, 160, 150, 140, 130, 140, 122, 150, 170, 160, 140])
        got = F.leg_touches(d["high"], d["low"], 100.0, 150.0, np.ones(len(d["ts"]), dtype=bool))
        first = {(dep, top): off for dep, off, top in got}
        self.assertEqual(first[(0.30, 160.0)], 3)             # 160 - 0.30 x 60 = 142, first traded on the way to 140
        self.assertEqual(first[(0.382, 160.0)], 4)            # 137.08, on the way to 130
        self.assertEqual(first[(0.5, 160.0)], 4)
        self.assertEqual(first[(0.618, 160.0)], 6)            # 122.92, on the way to 122; the dip to 130 did not reach it
        self.assertNotIn((0.7, 160.0), first)                 # 118 was never traded
        self.assertEqual(first[(0.382, 170.0)], 10)           # after the new top at 170: 143.26, on the way to 140
        self.assertEqual(sum(1 for dep, _, top in got if dep == 0.5 and top == 160.0), 1)   # once per top

    def test_a_candle_that_sets_a_new_top_is_not_a_touch_and_the_leg_ends_under_its_base(self):
        d = candles([150, 160, 99, 160, 120])
        got = F.leg_touches(d["high"], d["low"], 100.0, 150.0, np.ones(5, dtype=bool))
        self.assertEqual(got, [])                             # the candle to 99 ends the leg before any touch counts
        d = candles([150, 120, 170])                          # the first candle to 120 is a touch of the old top...
        got = F.leg_touches(d["high"], d["low"], 100.0, 150.0, np.ones(3, dtype=bool))
        self.assertTrue(all(top == 150.0 for _, _, top in got))
        short = F.leg_touches(d["high"], d["low"], 100.0, 150.0, np.zeros(3, dtype=bool))
        self.assertEqual(short, [])                           # a leg that is not tall enough gives nothing


class OutcomeTests(unittest.TestCase):
    def row(self, d, direction=1, g=0):
        extreme, base = (160.0, 100.0) if direction > 0 else (100.0, 160.0)
        height = 60.0
        return {"direction": direction, "g": g, "t": int(d["ts"][g]), "height": height, "extreme": extreme, "base": base,
                "level": extreme - direction * F.ZONE_TOP * height, "depth": F.ZONE_TOP}

    def long_path(self, prices):
        return candles(list(prices) + [prices[-1]] * (288 * (F.TRADE_DAYS + 1)))

    def test_the_race_after_a_touch(self):
        level, w = 160 - 0.618 * 60, 0.08 * 60                 # 122.92, 4.8
        d = self.long_path([level, level + 2, level + 5])
        self.assertEqual(F.race(d, self.row(d)), "turn")
        d = self.long_path([level, level - 2, level - 5, level + 20])
        self.assertEqual(F.race(d, self.row(d)), "deeper")
        d = self.long_path([level, level + 1, level - 1])
        self.assertEqual(F.race(d, self.row(d)), "none")
        d = self.long_path([level, level - 5, level + 5])     # one candle from -5 to +5 holds both: the first decides
        self.assertEqual(F.race(d, self.row(d)), "deeper")
        self.assertIsNone(F.race(candles([level, level + 5]), self.row(candles([level, level + 5]))))   # candles run out

    def test_the_race_mirrors_for_a_down_leg(self):
        level = 100 + 0.618 * 60                               # a rally back up to 137.08
        d = self.long_path([level, level - 5])
        self.assertEqual(F.race(d, self.row(d, direction=-1)), "turn")
        d = self.long_path([level, level + 5])
        self.assertEqual(F.race(d, self.row(d, direction=-1)), "deeper")

    def test_the_trade_is_in_at_the_level_with_the_stop_at_0786_and_out_at_the_extreme(self):
        level = 160 - 0.618 * 60
        d = self.long_path([level, 130, 161])
        t = F.zone_trade(d, self.row(d))
        self.assertTrue(t["reached"])
        self.assertAlmostEqual(t["gross"], (160 - level) / level)
        self.assertAlmostEqual(t["r"], (160 - level) / (level - (160 - 0.786 * 60)))
        d = self.long_path([level, 112, 161])                  # 112.84 is the stop
        t = F.zone_trade(d, self.row(d))
        self.assertTrue(t["stopped"])
        self.assertAlmostEqual(t["r"], -1.0)
        d = self.long_path([level, 125])                       # neither: out at the last price after 90 days
        self.assertAlmostEqual(F.zone_trade(d, self.row(d))["gross"], (125 - level) / level)


class PocTests(unittest.TestCase):
    def test_a_poc_counts_inside_the_zone_or_within_a_quarter_percent_of_it(self):
        row = {"direction": 1, "extreme": 160.0, "height": 60.0}      # the zone: 122.92 down to 120.40
        self.assertTrue(F.poc_in_zone(row, [121.0]))
        self.assertTrue(F.poc_in_zone(row, [50.0, 123.2]))            # 0.23% above the top edge
        self.assertFalse(F.poc_in_zone(row, [124.0, 119.0]))
        down = {"direction": -1, "extreme": 100.0, "height": 60.0}    # the zone: 137.08 up to 139.60
        self.assertTrue(F.poc_in_zone(down, [138.0]))
        self.assertFalse(F.poc_in_zone(down, [121.0]))

    def test_only_finished_weeks_and_months_before_the_touch_are_read(self):
        week = int(F.ae.session_starts([T0], "week")[0])
        weeks = {week: {"poc": 1.0}, week - 7 * DAY: {"poc": 2.0}, week - 13 * 7 * DAY: {"poc": 3.0}}
        aug, sep = V._ms("2026-08-01"), V._ms("2026-09-01")
        got = F.pocs_before(T0 + 3 * DAY, weeks, {sep: 9.0, aug: 8.0})
        self.assertEqual(sorted(got), [2.0, 8.0])                    # not this week's or this month's; not 13 weeks back


class BarTests(unittest.TestCase):
    def test_each_row_needs_its_size_its_interval_and_both_halves(self):
        zone = {"n": 400, "days": 50, "value": 0.58, "low": 0.53, "first_half": 0.57, "second_half": 0.6}
        gap = {"value": 0.06, "low": 0.01, "first_half": 0.05, "second_half": 0.07}
        grp = {"n": 150, "days": 40}
        net = {"n": 400, "days": 50, "value": 0.01, "low": 0.002, "first_half": 0.01, "second_half": 0.01}
        b = F.bars(zone, gap, grp, grp, gap, net)
        self.assertTrue(all(b[r]["met"] for r in ("R1", "R2", "R3", "R4")))
        self.assertFalse(F.bars({**zone, "value": 0.54}, gap, grp, grp, gap, net)["R1"]["met"])
        self.assertFalse(F.bars(zone, {**gap, "low": -0.01}, grp, grp, gap, net)["R2"]["met"])
        self.assertFalse(F.bars(zone, gap, {"n": 50, "days": 40}, grp, gap, net)["R3"]["met"])
        self.assertFalse(F.bars(zone, gap, grp, grp, gap, {**net, "second_half": -0.01})["R4"]["met"])


class EndToEndTests(unittest.TestCase):
    def test_counts_and_run_agree_on_a_made_up_cache(self):
        rng = np.random.default_rng(5)
        syms = ("BTCUSDT", "AAAUSDT", "BBBUSDT")
        first, last = "2021-03-01", "2021-12-31"
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            n = 288 * 480
            for sym in syms:
                close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
                open_ = np.concatenate(([100.0], close[:-1]))
                spread = np.abs(rng.normal(0, 0.001, n)) * close
                np.savez_compressed(cache / f"{sym}-5m.npz", ts=V._ms("2020-12-01") + np.arange(n) * V.BAR_MS, open=open_,
                                    high=np.maximum(open_, close) + spread, low=np.minimum(open_, close) - spread, close=close,
                                    volume=rng.random(n) + 0.1, taker=np.zeros(n))
            sh = F.shape(first, last, cache, syms)
            res = F.run_study(first, last, cache, syms, draws=300)
            self.assertGreater(sh["zone"]["touches"], 0)
            raced = sum(res["reported"]["outcomes"][str(F.ZONE_TOP)].values())
            self.assertEqual(raced, sh["zone"]["touches"])                 # the run scores the touches shape counted
            self.assertEqual(sh["zone"]["poc_in_zone"] + sh["zone"]["no_poc"], sh["zone"]["touches"])
            self.assertGreater(sh["touches"]["0.3"], sh["touches"]["0.85"])  # shallow depths are touched more often
            self.assertFalse(res["R1"]["met"] and res["R4"]["met"])
            self.assertIn("by_depth", res["reported"])
            self.assertIn("R3", F.power(sh, reps=10)["independent"])


if __name__ == "__main__":
    unittest.main()
