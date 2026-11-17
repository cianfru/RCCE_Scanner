"""The POC rule on swing profiles: the chart's structure as it stood each day, the orders, their fills and the trade."""
import unittest

import numpy as np

from engines import auction_engine as ae
from research import fib_zone as F
from research import poc_rule as P
from research import value_area_rule as V

DAY, BAR = V.DAY_MS, V.BAR_MS
T0 = 1_788_739_200_000 - 60 * DAY       # a Monday, 60 days before 2026-09-07


def market(days, heavy=(118.0, 124.0)):
    """5-minute candles walking through one price a day (from each day's price to the next), half a point either
    side. Candles between the ``heavy`` prices trade 40 times the volume of the rest."""
    rows = []
    for k, (p0, p1) in enumerate(zip(days, days[1:])):
        for i in range(288):
            p = p0 + (p1 - p0) * i / 288
            rows.append((T0 + k * DAY + i * BAR, p, p + 0.5, p - 0.5, p, 400.0 if heavy[0] <= p < heavy[1] else 10.0))
    a = np.array(rows)
    return {"ts": a[:, 0].astype(np.int64), "open": a[:, 1], "high": a[:, 2], "low": a[:, 3], "close": a[:, 4], "volume": a[:, 5]}


# Flat at 100, a low at 95, a rise to 150, a fall to 110, a bounce to 123, a fall to 105, then flat.
PATH = ([100.0] * 20 + [95.0] + list(np.linspace(100, 150, 12)) + list(np.linspace(146, 110, 8)) + list(np.linspace(113, 123, 4))
        + list(np.linspace(120, 105, 5)) + [105.0] * 45)
FIRST, LAST = V.iso(T0)[:10], V.iso(T0 + 200 * DAY)[:10]


class Structure(unittest.TestCase):
    def test_hourly_candles_from_the_five_minute_ones(self):
        d = market([100.0, 112.0])
        hr = P.hourly(d)
        self.assertEqual(len(hr["ts"]), 24)
        self.assertEqual(hr["ts"][1] - hr["ts"][0], V.HOUR_MS)
        self.assertAlmostEqual(hr["low"][0], 99.5)
        self.assertAlmostEqual(hr["high"][0], 100.5 + 12 * 11 / 288)
        self.assertEqual(hr["volume"][0], 120.0)

    def test_the_structure_holds_only_what_was_known_at_the_close(self):
        d = market(PATH)
        dd = F.daily(d)
        piv = ae.swings(dd["high"], dd["low"], dd["atr"])
        self.assertEqual([p[0] for p in piv[:2]], ["L", "H"])
        low, high = piv[0], piv[1]
        before = sum(p[3] <= high[3] - 1 for p in piv)
        # The day before the high is confirmed, the rise is still the running move: no finished move ends at it.
        known = P.structure(piv, dd, high[3] - 1, before)
        self.assertEqual(known[-1], low)
        # From the day it is confirmed, the rise from the low to the high is the last finished move.
        known = P.structure(piv, dd, high[3], before + 1)
        self.assertEqual(known[-2:], [low, high])
        self.assertEqual(P.structure(piv, dd, 5, 0), [])

    def test_a_moves_levels_come_from_its_own_hours(self):
        d = market(PATH)
        dd, hr = F.daily(d), P.hourly(d)
        piv = ae.swings(dd["high"], dd["low"], dd["atr"])
        poc, vah, val = P.move_levels(hr, dd, piv[0], piv[1], 150.0)
        self.assertTrue(118 <= val < poc < vah <= 124.5)                  # where the rise traded most
        self.assertIsNone(P.move_levels(hr, dd, piv[1], piv[0], 150.0))  # no candles from a later swing to an earlier one


class Orders(unittest.TestCase):
    def setUp(self):
        self.d = market(PATH)
        dd, hr = F.daily(self.d), P.hourly(self.d)
        piv = ae.swings(dd["high"], dd["low"], dd["atr"])
        self.dd, self.high = dd, piv[1]
        self.poc, self.vah, self.val = P.move_levels(hr, dd, piv[0], piv[1], float(dd["close"][piv[1][3]]))
        self.rows, self.counts = P.entries("TEST", self.d, FIRST, LAST)

    def test_a_close_over_the_value_area_buys_at_the_poc_and_a_close_under_it_sells_there(self):
        buy, sell = self.rows[:2]
        # The high is confirmed on the way down, with price still over the rise's value area: a buy rests at its POC.
        self.assertEqual((buy["side"], buy["direction"]), (1, 1))
        self.assertEqual((buy["entry"], buy["stop"], buy["target"]), (self.poc, self.val, self.vah))
        self.assertGreater(self.dd["close"][self.high[3]], self.vah)
        # The fall goes on through the value area. The first close under it places the sell, filled on the bounce.
        self.assertEqual((sell["side"], sell["direction"]), (-1, 1))
        self.assertEqual((sell["entry"], sell["stop"], sell["target"]), (self.poc, self.vah, self.val))
        self.assertGreater(sell["t"], buy["t"])
        for r in (buy, sell):
            g = r["g"]
            self.assertTrue(self.d["low"][g] <= r["entry"] <= self.d["high"][g])       # filled in a candle that holds the POC
            self.assertEqual(r["day"], int(ae.session_starts([r["t"]], "month")[0]))
            self.assertAlmostEqual(r["walk"], r["risk"] / (r["risk"] + r["reward"]))

    def test_one_order_per_move_and_side(self):
        on_the_rise = [r for r in self.rows if (r["entry"], r["direction"]) == (self.poc, 1)]
        self.assertEqual(sorted(r["side"] for r in on_the_rise), [-1, 1])
        self.assertGreaterEqual(self.counts["orders"], len(self.rows))
        self.assertGreaterEqual(self.counts["moves"], 1)

    def test_orders_are_placed_on_break_days_inside_the_period_only(self):
        early = V.iso(T0 + 10 * DAY)[:10]
        self.assertEqual(P.entries("TEST", self.d, FIRST, early)[0], [])

    def test_the_trade_ends_at_the_stop_the_exit_or_the_last_price(self):
        buy, sell = self.rows[:2]
        lost = P.score(self.d, buy)                           # price went on down through the value area's low
        self.assertTrue(lost["stopped"] and not lost["reached"])
        self.assertAlmostEqual(lost["gross"], (self.val - self.poc) / self.poc)
        self.assertAlmostEqual(lost["net"], lost["gross"] - V.COST)
        won = P.score(self.d, sell)                           # the bounce failed at the POC and price fell to the low edge
        self.assertTrue(won["reached"] and not won["stopped"])
        self.assertAlmostEqual(won["gross"], (self.poc - self.val) / self.poc)
        late = {**sell, "t": int(self.d["ts"][-1]) - 5 * DAY}
        self.assertIsNone(P.score(self.d, late))              # the candles end before the trade could

    def test_an_order_lapses_after_thirty_days(self):
        # After the high, price stays over the value area for good: the buy at the POC never fills.
        calm = market([100.0] * 20 + [95.0] + list(np.linspace(100, 150, 12)) + list(np.linspace(147, 136, 4)) + [136.0] * 60)
        rows, counts = P.entries("TEST", calm, FIRST, LAST)
        self.assertEqual((rows, counts["orders"]), ([], 1))


class Rows(unittest.TestCase):
    def test_a_row_needs_trades_months_a_positive_mean_interval_and_halves(self):
        good = {"n": 300, "days": 40, "value": 0.01, "low": 0.002, "first_half": 0.004, "second_half": 0.02}
        out = P.bars(good, {**good, "n": 150, "days": 25}, {**good, "n": 150, "days": 25, "low": -0.001})
        self.assertEqual([out[k]["met"] for k in ("R1", "R2", "R3")], [True, True, False])
        self.assertTrue(out["R3"]["confirms"])
        self.assertFalse(P.bars({**good, "n": 199}, good, good)["R1"]["met"])
        self.assertFalse(P.bars({**good, "first_half": -0.001}, good, good)["R1"]["met"])
        self.assertFalse(P.bars({"n": 0, "days": 0}, good, good)["R1"]["met"])

    def test_power_gives_a_rate_per_made_up_mean(self):
        shape = {"risk_pct": {"50": 4.0}, "reward_pct": {"50": 4.0}, "per_month": [8] * 40, "per_month_sells": [4] * 40, "per_month_buys": [4] * 40}
        out = P.power(shape, reps=200)
        self.assertEqual(out["spread"], 0.04)
        self.assertLess(out["independent"]["R1"]["0.0"], 0.1)
        self.assertGreater(out["independent"]["R1"]["0.02"], 0.9)
        self.assertLessEqual(out["one outcome a month"]["R1"]["0.02"], out["independent"]["R1"]["0.02"])


if __name__ == "__main__":
    unittest.main()
