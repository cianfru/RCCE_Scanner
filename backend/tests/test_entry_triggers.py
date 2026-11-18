"""The entry-trigger study: the 5-minute structure change, the 3rd touch, the readings on the retest, and the trades."""
import unittest

import numpy as np

from engines import auction_engine as ae
from research import entry_triggers as E
from research import value_area_rule as V

DAY, HOUR, BAR = V.DAY_MS, V.HOUR_MS, V.BAR_MS
T0 = 1_788_739_200_000 - 80 * DAY       # a Monday, 80 days before 2026-09-07
FIRST, LAST = V.iso(T0)[:10], V.iso(T0 + 200 * DAY)[:10]


def arrays(rows):
    a = np.array(rows, dtype=float)
    return a[:, 0], a[:, 1], a[:, 2]


def market(days, tail, after, heavy=(118.0, 124.0)):
    """5-minute candles: one price a day walked through (half a point either side), then the ``tail`` candles
    (open, high, low, close) from the next midnight, their day filled up at the last close, then the ``after``
    days walked through. Candles between the ``heavy`` prices trade 40 times the volume. Taker buys are half of
    each candle's volume."""
    rows = []
    walk = lambda k, p0, p1: [(T0 + k * DAY + i * BAR, p, p + 0.5, p - 0.5, p) for i in range(288) for p in [p0 + (p1 - p0) * i / 288]]
    for k, (p0, p1) in enumerate(zip(days, days[1:])):
        rows += walk(k, p0, p1)
    k = len(days) - 1
    last = tail[-1][3]
    tail = list(tail) + [(last, last + 0.2, last - 0.2, last)] * (288 - len(tail))
    rows += [(T0 + k * DAY + i * BAR, o, h, l, c) for i, (o, h, l, c) in enumerate(tail)]
    for j, (p0, p1) in enumerate(zip([last] + list(after), after)):
        rows += walk(k + 1 + j, p0, p1)
    a = np.array(rows)
    vol = np.where((a[:, 4] >= heavy[0]) & (a[:, 4] < heavy[1]), 400.0, 10.0)
    return {"ts": a[:, 0].astype(np.int64), "open": a[:, 1], "high": a[:, 2], "low": a[:, 3], "close": a[:, 4], "volume": vol, "taker": vol / 2}


def mirrored(d, around=250.0):
    """The same market upside down: every price p becomes ``around`` - p."""
    return {**d, "open": around - d["open"], "high": around - d["low"], "low": around - d["high"], "close": around - d["close"]}


# Flat at 100, a low at 95, a rise to 150 (the swing high, 150.5), a fall to 110, a rise back to 149.
PATH = [100.0] * 20 + [95.0] + list(np.linspace(100, 150, 12)) + list(np.linspace(146, 110, 8)) + list(np.linspace(114, 149, 7))
# Day 47: price takes the high, pulls back, makes a lower high and closes under the pullback low; the hour closes
# back under the high; the next hour price moves away and comes back to the high; then it falls.
TAKE = [(149.5, 151.5, 149.4, 151.0),        # 0: trades above 150.5, to 151.5
        (151.0, 151.1, 148.0, 148.2),        # 1: the pullback low, 148.0
        (148.2, 151.2, 148.1, 151.0),        # 2: a bounce of 3 units: the lower high, 151.2
        (151.0, 151.1, 148.1, 148.3),        # 3: back 3 units from it
        (148.3, 148.4, 147.0, 147.5)]        # 4: closes under 148.0 and under 150.5
QUIET = [(147.5, 147.7, 147.3, 147.5)] * 7   # 5 to 11: the hour closes at 147.5
RETEST = [(147.5, 147.6, 146.0, 146.5),      # 12: 3 units away from the high
          (146.5, 150.8, 146.4, 150.6)]      # 13: back at 150.5
FALL = [(p, p + 0.5, p - 0.5, p) for p in np.linspace(150, 115, 274)]
DAY47 = TAKE + QUIET + RETEST + FALL
START = 47 * 288                             # the first candle of day 47


def full():
    return market(PATH, DAY47, [115.0] * 16)


def by_row(rows):
    return {r["row"]: r for r in rows}


class Hourly(unittest.TestCase):
    def test_hourly_candles_as_the_chart_reads_them(self):
        d = market([100.0, 112.0], [(112.0, 112.5, 111.5, 112.0)], [])
        hr = E.hourly(d)
        self.assertEqual(len(hr["timestamp"]), 48)
        self.assertEqual((hr["open"][0], hr["low"][0]), (100.0, 99.5))
        self.assertAlmostEqual(hr["close"][0], 100 + 12 * 11 / 288)
        self.assertAlmostEqual(hr["high"][0], 100.5 + 12 * 11 / 288)
        self.assertEqual(hr["volume"][0], 120.0)


class StructureChange(unittest.TestCase):
    def run_on(self, candles, level=150.5, unit=1.0):
        hi, lo, cl = arrays([(h, l, c) for _, h, l, c in candles])
        return E.structure_change(hi, lo, cl, 0, len(candles), level, unit)

    def test_a_pullback_a_lower_high_and_a_close_under_the_pullback_low(self):
        self.assertEqual(self.run_on(TAKE), {"entry": 4, "top": 0, "low": 1, "retest": 2, "extreme": 151.5})

    def test_no_lower_high_no_entry(self):
        straight_down = [TAKE[0], (151.0, 151.1, 148.0, 148.2), (148.2, 148.3, 145.0, 145.2), (145.2, 145.3, 142.0, 142.1)]
        self.assertIsNone(self.run_on(straight_down))              # it only fell: no bounce of 3 units, so no pullback low

    def test_a_bounce_of_under_three_units_is_not_a_swing(self):
        small = [TAKE[0], TAKE[1], (148.2, 150.9, 148.1, 150.5), (150.5, 150.6, 147.0, 147.2)]
        self.assertIsNone(self.run_on(small))                      # 148.0 to 150.9: 2.9 units

    def test_the_low_and_the_bounce_in_one_candle_do_not_count(self):
        one = [TAKE[0], (151.0, 151.3, 148.0, 150.0), (150.0, 150.1, 147.0, 147.2), (147.2, 147.3, 146.0, 146.1)]
        self.assertIsNone(self.run_on(one))                        # which came first inside the candle is not known

    def test_a_higher_high_starts_it_again(self):
        again = TAKE[:4] + [(148.3, 152.0, 148.2, 151.8)] + TAKE[1:]
        self.assertEqual(self.run_on(again), {"entry": 8, "top": 4, "low": 5, "retest": 6, "extreme": 152.0})

    def test_the_close_must_be_back_inside_the_level_too(self):
        far = [(o + 6, h + 6, l + 6, c + 6) for o, h, l, c in TAKE]        # the same shape 6 points higher: all above 150.5
        self.assertIsNone(self.run_on(far))
        then = far + [(153.5, 153.6, 150.0, 150.2)]                 # and then a close under the level
        self.assertEqual(self.run_on(then)["entry"], 5)

    def test_the_window_ends(self):
        hi, lo, cl = arrays([(h, l, c) for _, h, l, c in TAKE])
        self.assertIsNone(E.structure_change(hi, lo, cl, 0, 4, 150.5, 1.0))


class ThirdTouch(unittest.TestCase):
    def run_on(self, candles, extreme=151.5):
        hi, lo, _ = arrays([(h, l, c) for _, h, l, c in candles])
        return E.third_touch(hi, lo, 0, len(candles), 150.5, extreme, 1.0)

    def test_price_leaves_the_level_and_comes_back(self):
        self.assertEqual(self.run_on(QUIET[:2] + RETEST), {"fill": 3, "low": 2})

    def test_it_must_move_three_units_away_first(self):
        near = [(149.0, 149.2, 147.6, 148.0), (148.0, 150.9, 147.9, 150.7)]
        self.assertIsNone(self.run_on(near))                       # 147.6 is 2.9 units under 150.5

    def test_away_and_back_in_one_candle_is_not_a_retest(self):
        self.assertIsNone(self.run_on([(149.0, 150.9, 147.0, 150.7)]))
        self.assertEqual(self.run_on([(149.0, 150.9, 147.0, 150.7), (150.7, 150.8, 150.0, 150.2)])["fill"], 1)

    def test_beyond_the_sweeps_extreme_before_moving_away_undoes_it(self):
        self.assertIsNone(self.run_on([(149.0, 151.6, 148.9, 151.0)] + RETEST))
        self.assertEqual(self.run_on(RETEST[:1] + [(146.5, 152.0, 146.4, 151.8)])["fill"], 1)    # after moving away it is a fill (and a stop)


class Trades(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = full()
        cls.rows, cls.counts = E.events("TEST", cls.d, None, FIRST, LAST)

    def test_one_trade_of_each_row_at_the_swept_high(self):
        self.assertEqual(sorted(r["row"] for r in self.rows), ["B", "R1", "R2"])
        self.assertEqual({k: self.counts[k] for k in ("taken", "swept", "quick", "broken")}, {"taken": 1, "swept": 1, "quick": 1, "broken": 0})
        r = by_row(self.rows)
        self.assertEqual([(x["side"], x["swept"], x["quick"], x["hours"]) for x in self.rows], [(-1, True, True, 1)] * 3)
        # R1: in at the close under the pullback low. R2: in at the level. B: in at the close of the hour that closed back.
        self.assertEqual((r["R1"]["g"], r["R1"]["entry"], r["R1"]["fill"]), (START + 4, 147.5, False))
        self.assertEqual((r["R2"]["g"], r["R2"]["entry"], r["R2"]["fill"]), (START + 13, 150.5, True))
        self.assertEqual((r["B"]["g"], r["B"]["entry"], r["B"]["fill"]), (START + 11, 147.5, False))
        for x in self.rows:
            self.assertAlmostEqual(x["stop"], 151.55)             # one row (0.05) beyond the high made, 151.5
            self.assertTrue(118 <= x["target"] <= 124.5)          # the POC of the range since the swing high
        self.assertEqual(len({x["target"] for x in self.rows}), 1)
        self.assertAlmostEqual(r["R2"]["risk"], 1.05 / 150.5)
        self.assertAlmostEqual(r["R1"]["wait"], 4 * 5 / 60)

    def test_the_trades_are_scored_from_the_candle_after_the_entry(self):
        for x in self.rows:
            t = E.score(self.d, x)
            self.assertTrue(t["reached"] and not t["stopped"], x["row"])
            self.assertAlmostEqual(t["gross"], (x["entry"] - x["target"]) / x["entry"])
            self.assertAlmostEqual(t["net"], t["gross"] - 0.002)

    def test_an_order_filled_by_a_candle_that_also_reaches_the_stop_is_stopped(self):
        day = TAKE + QUIET + [RETEST[0], (146.5, 151.6, 146.4, 151.0)] + FALL       # the retest candle runs to 151.6
        d = market(PATH, day, [115.0] * 16)
        r2 = by_row(E.events("TEST", d, None, FIRST, LAST)[0])["R2"]
        t = E.score(d, r2)
        self.assertTrue(t["stopped"])
        self.assertAlmostEqual(t["gross"], -1.05 / 150.5)
        self.assertEqual(t["r"], -1.0)

    def test_a_trade_the_candles_end_before_is_not_scored(self):
        d = market(PATH, DAY47, [115.0] * 5)
        rows, _ = E.events("TEST", d, None, FIRST, LAST)
        self.assertEqual([E.score(d, x) for x in rows], [None] * 3)

    def test_nothing_after_the_entry_changes_it(self):
        cut = {k: v[:START + 288] for k, v in self.d.items()}                       # the candles end with day 47
        early = {r["row"]: (r["g"], r["entry"], r["stop"], r["target"]) for r in E.events("TEST", cut, None, FIRST, LAST)[0]}
        self.assertEqual(early, {r["row"]: (r["g"], r["entry"], r["stop"], r["target"]) for r in self.rows})

    def test_only_levels_taken_in_the_period_count(self):
        take_day = V.iso(T0 + 47 * DAY)[:10]
        self.assertEqual(len(E.events("TEST", self.d, None, take_day, take_day)[0]), 3)
        self.assertEqual(E.events("TEST", self.d, None, FIRST, V.iso(T0 + 46 * DAY)[:10])[0], [])

    def test_a_poc_too_near_the_entry_is_no_trade(self):
        keep = E.MIN_ROOM
        try:
            E.MIN_ROOM = 0.5
            rows, counts = E.events("TEST", self.d, None, FIRST, LAST)
        finally:
            E.MIN_ROOM = keep
        self.assertEqual((rows, [counts[f"no_room_{r}"] for r in E.ROWS]), ([], [1, 1, 1]))

    def test_a_swept_low_is_the_same_trade_upside_down(self):
        d = mirrored(self.d)
        rows, counts = E.events("TEST", d, None, FIRST, LAST)
        r = by_row(rows)
        self.assertEqual(sorted(r), ["B", "R1", "R2"])
        self.assertEqual([x["side"] for x in rows], [1, 1, 1])
        self.assertEqual((r["R1"]["g"], r["R1"]["entry"]), (START + 4, 102.5))
        self.assertEqual((r["R2"]["g"], r["R2"]["entry"]), (START + 13, 99.5))
        self.assertAlmostEqual(r["R1"]["stop"], 98.5 - 0.025)                       # one row (0.025 at this price) under the low made
        self.assertTrue(125.5 <= r["R1"]["target"] <= 132)
        self.assertTrue(E.score(d, r["R1"])["reached"])

    def test_a_break_has_no_sweep_trades(self):
        up = [(149.5, 151.5, 149.4, 151.0)] + [(p, p + 0.5, p - 0.5, p) for p in np.linspace(151.5, 170, 287)]
        d = market(PATH, up, [170.0] * 16)
        rows, counts = E.events("TEST", d, None, FIRST, LAST)
        self.assertEqual((rows, counts["taken"], counts["broken"], counts["swept"]), ([], 1, 1, 0))


class Readings(unittest.TestCase):
    def test_a_cvd_divergence_is_more_net_buying_at_the_lower_high_than_at_the_high(self):
        d = full()
        self.assertEqual([r["div"] for r in E.events("TEST", d, None, FIRST, LAST)[0]], [False] * 3)     # buys are half of every candle
        d["taker"] = d["taker"].copy()
        d["taker"][START + 2] = d["volume"][START + 2]                              # the bounce to the lower high was all buying
        r = by_row(E.events("TEST", d, None, FIRST, LAST)[0])
        self.assertEqual((r["R1"]["div"], r["R2"]["div"], r["B"]["div"]), (True, True, True))
        low = mirrored(d)                                                           # upside down, the same buying is no divergence
        self.assertEqual(by_row(E.events("TEST", low, None, FIRST, LAST)[0])["R1"]["div"], False)
        low["taker"] = low["taker"].copy()
        low["taker"][START + 2] = 0.0                                               # the drop to the higher low was all selling
        self.assertEqual(by_row(E.events("TEST", low, None, FIRST, LAST)[0])["R1"]["div"], True)

    def test_open_interest_on_the_retest(self):
        d = full()
        oi = {"ts": d["ts"] + BAR, "oi": np.full(len(d["ts"]), 1000.0)}             # a reading at each candle's close
        oi["oi"][START + 1] = 900.0                                                 # down at the pullback low
        oi["oi"][START + 2] = 950.0                                                 # up again at the lower high
        r = by_row(E.events("TEST", d, oi, FIRST, LAST)[0])
        self.assertEqual((r["R1"]["oi_rose"], r["R1"]["oi_fell_then_rose"]), (True, True))
        self.assertEqual(r["R2"]["oi_rose"], False)                                 # its retest: candle 12 to candle 12
        oi["oi"][START + 2] = 880.0
        self.assertEqual(by_row(E.events("TEST", d, oi, FIRST, LAST)[0])["R1"]["oi_rose"], False)
        self.assertEqual([r["oi_rose"] for r in E.events("TEST", d, None, FIRST, LAST)[0]], [None] * 3)      # no readings: left out
        old = {"ts": oi["ts"][:START - 12], "oi": oi["oi"][:START - 12]}            # the readings stop an hour before: too old to use
        self.assertEqual(by_row(E.events("TEST", d, old, FIRST, LAST)[0])["R1"]["oi_rose"], None)


class RowsAndBars(unittest.TestCase):
    def test_a_trade_row_needs_enough_trades_a_positive_mean_an_interval_above_zero_and_both_halves(self):
        good = {"n": 250, "days": 40, "value": 0.004, "low": 0.001, "high": 0.007, "first_half": 0.003, "second_half": 0.005}
        self.assertTrue(E.trade_bar(good)["met"])
        for change in ({"n": 150}, {"days": 20}, {"low": -0.001}, {"second_half": -0.001}, {"value": -0.002}):
            self.assertFalse(E.trade_bar({**good, **change})["met"], change)
        self.assertTrue(E.trade_bar({**good, "low": -0.001})["confirms"])            # held out: the mean above 0 is enough
        self.assertFalse(E.trade_bar({"n": 0, "days": 0})["met"])

    def test_a_gap_row_needs_both_groups_a_gap_of_a_tenth_of_a_percent_and_both_halves(self):
        a, b = {"n": 150, "days": 30}, {"n": 120, "days": 25}
        diff = {"value": 0.002, "low": 0.0005, "high": 0.004, "first_half": 0.001, "second_half": 0.003}
        self.assertTrue(E.gap_bar(a, b, diff)["met"])
        self.assertFalse(E.gap_bar(a, {"n": 80, "days": 25}, diff)["met"])
        self.assertFalse(E.gap_bar(a, b, {**diff, "value": 0.0005})["met"])
        self.assertFalse(E.gap_bar(a, b, {**diff, "low": -0.001})["met"])
        self.assertFalse(E.gap_bar(a, b, {**diff, "first_half": -0.001})["met"])
        self.assertFalse(E.gap_bar({}, {}, {})["met"])

    def test_groups_by_a_reading_leave_out_trades_without_one(self):
        rows = [{"x": True}, {"x": False}, {"x": None}, {"x": True}]
        yes, no = E.split(rows, "x")
        self.assertEqual((len(yes), len(no)), (2, 1))

    def test_trades_a_month_for_two_groups(self):
        a, b = [{"day": 1}, {"day": 1}, {"day": 3}], [{"day": 2}, {"day": 3}]
        self.assertEqual(E.pair_per_month(a, b), [[2, 0], [0, 1], [1, 1]])


class ShapeAndPower(unittest.TestCase):
    def test_power_gives_a_rate_for_each_truth(self):
        months = [8] * 50
        shape = {"rows": {"R1": {"per_month": months, "risk_pct": {"50": 1.0}, "reward_pct": {"50": 4.0}},
                          "R2": {"per_month": [2] * 10, "risk_pct": {"50": 1.0}, "reward_pct": {"50": 4.0}}},
                 "oi_rose": {"first": 200, "second": 200, "months_first": 50, "months_second": 50, "per_month": [[4, 4]] * 50},
                 "div": {"first": 30, "second": 370, "months_first": 20, "months_second": 50, "per_month": [[1, 7]] * 50}}
        out = E.power(shape, reps=200)
        free = out["independent"]
        self.assertEqual(set(free["R1"]) - {"spread"}, {"0.0", "0.002", "0.005", "0.01"})
        self.assertEqual(free["R1"]["spread"], 0.02)
        self.assertLessEqual(free["R1"]["0.0"], 0.1)
        self.assertGreaterEqual(free["R1"]["0.01"], 0.95)                           # 400 trades, 2% wide: 1% a trade always shows
        self.assertEqual(set(free["R2"].values()) - {0.02}, {0.0})                  # 20 trades: under the minimum, never met
        self.assertGreaterEqual(free["R3"]["0.01"], 0.9)
        self.assertLessEqual(free["R3"]["0.0"], 0.1)
        self.assertEqual(set(free["R4"].values()), {0.0})                           # a group of 30: under the minimum
        self.assertLessEqual(out["one outcome a month"]["R1"]["0.01"], free["R1"]["0.01"])


if __name__ == "__main__":
    unittest.main()
