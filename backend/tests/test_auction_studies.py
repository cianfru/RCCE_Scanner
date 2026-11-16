"""The other auction-level studies: races to a POC, acceptance outside value, sweeps, confluence, New York hours."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research import auction_studies as A
from research import value_area_rule as V

DAY = V.DAY_MS
T0 = 1_788_739_200_000            # Monday 2026-09-07 00:00 UTC


def coin(days, taker_share=0.5):
    """Candles from a list of days; each day is 48 half-hour (low, high, close) triples or plain prices.
    Every candle of a half hour repeats its triple, opens at its close, and has volume 1."""
    lo, hi, cl = [], [], []
    for day in days:
        for x in day:
            a, b, c = x if isinstance(x, tuple) else (x, x, x)
            lo += [a] * 6; hi += [b] * 6; cl += [c] * 6
    n = len(cl)
    return {"ts": T0 + np.arange(n) * V.BAR_MS, "open": np.array(cl, float), "high": np.array(hi, float),
            "low": np.array(lo, float), "close": np.array(cl, float), "volume": np.ones(n), "taker": np.full(n, taker_share)}


def profile_day(poc, low, high, close):
    """A day whose volume sits at ``poc`` (narrow bars there) with one wide bar to its extremes, ending at close."""
    return [(poc - 0.05, poc + 0.05, poc)] * 46 + [(low, high, poc)] + [(min(close, poc), max(close, poc), close)]


class TradeTests(unittest.TestCase):
    def test_stop_target_and_end(self):
        d = coin([[100, 101, 103, 99, 104]])
        long = lambda **k: A.trade(d, 6, 30, 1, 100.0, **k)
        self.assertTrue(long(stop=98.0, target=103.0)["reached"])
        self.assertAlmostEqual(long(stop=98.0, target=103.0)["gross"], 0.03)
        self.assertAlmostEqual(long(stop=98.0, target=103.0)["net"], 0.03 - V.COST)
        self.assertTrue(long(stop=99.5, target=104.0)["stopped"])            # 99 comes before 104
        self.assertAlmostEqual(long(stop=99.5, target=104.0)["r"], -1.0)
        self.assertAlmostEqual(long(stop=90.0)["gross"], 0.04)              # no target: out at the last price
        short = A.trade(d, 6, 30, -1, 100.0, stop=102.0, target=99.0)
        self.assertTrue(short["stopped"])                                    # 103 comes before 99


class RaceTests(unittest.TestCase):
    def test_which_price_is_traded_first(self):
        days = [[100] * 48, [100] * 10 + [101] * 10 + [99] * 28, [100] * 48, [100] * 48]
        d = coin(days)
        self.assertEqual(A.race(d, 288, T0 + DAY, 3, 101.0, 99.0), "poc")
        self.assertEqual(A.race(d, 288, T0 + DAY, 3, 99.0, 101.0), "mirror")
        self.assertEqual(A.race(d, 288, T0 + DAY, 3, 105.0, 95.0), "none")
        self.assertIsNone(A.race(d, 288, T0 + DAY, 5, 101.0, 99.0))           # the window runs past the candles

    def test_a_fresh_race_needs_distance_and_a_mirror_inside_the_days_range(self):
        quiet = [(99.9, 100.1, 100)] * 48
        # Day 1: volume at 100, range 98..103, close 101 -> POC 1% below the close, mirror 102 inside the range.
        d = coin([quiet, profile_day(100, 98, 103, 101)] + [quiet] * 4)
        rows = A.poc_races("X", d, V.iso(T0), V.iso(T0 + 5 * DAY), outcomes=True)
        fresh = [r for r in rows if r["kind"] == "fresh"]
        self.assertEqual(len(fresh), 1)
        self.assertEqual((fresh[0]["t0"], fresh[0]["outcome"]), (T0 + 2 * DAY, "poc"))   # the next days sit at 100
        self.assertAlmostEqual(fresh[0]["dist"], 1 / 101, places=3)
        # Close at the day's high: the mirror is above the range, so no fresh race.
        d = coin([quiet, profile_day(100, 98, 101, 101)] + [quiet] * 4)
        self.assertEqual([r for r in A.poc_races("X", d, V.iso(T0), V.iso(T0 + 5 * DAY), True) if r["kind"] == "fresh"], [])

    def test_an_old_race_starts_only_for_a_poc_not_traded_the_next_day(self):
        up = [(109.9, 110.1, 110)] * 48
        d = coin([profile_day(100, 98, 103, 101), up] + [[(109.9, 110.1, 110)] * 20 + [(110, 121, 121)] * 28] + [up] * 12)
        old = [r for r in A.poc_races("X", d, V.iso(T0), V.iso(T0 + 14 * DAY), True) if r["kind"] == "old"]
        self.assertEqual(old[0]["t0"], T0 + 2 * DAY)                           # raced from the end of the day after
        self.assertEqual(old[0]["outcome"], "mirror")                          # 2 x 110 - 100 = 120 traded, 100 never
        counted = A.poc_races("X", d, V.iso(T0), V.iso(T0 + 14 * DAY), outcomes=False)
        self.assertNotIn("outcome", counted[0])


class OutsideTests(unittest.TestCase):
    def rows(self, today):
        d = coin([profile_day(100, 95, 105, 100), today])
        return d, A.outside_events("X", d, V.iso(T0 + DAY), V.iso(T0 + DAY), outcomes=True)

    def test_two_closes_outside_are_acceptance_and_the_trade_follows_the_break(self):
        d, rows = self.rows([100] * 4 + [101] * 2 + [102] * 42)
        r = rows[0]
        self.assertEqual((r["state"], r["side"], r["entry"]), ("accepted", 1, 101.0))
        self.assertAlmostEqual(r["gross"], 0.01 / 1.01, places=6)             # out at the day's last price, 102
        self.assertAlmostEqual(r["net"], r["gross"] - V.COST)
        self.assertTrue(r["closed_outside"])
        self.assertFalse(r["back_inside"])

    def test_back_inside_on_the_next_bar_is_a_rejection_and_back_inside_later_is_the_stop(self):
        _, rows = self.rows([100] * 4 + [101] + [100] * 43)
        self.assertEqual(rows[0]["state"], "rejected")
        # Accepted at 101, then a dip inside within a bar that still closes outside (held), then a close inside (out).
        _, rows = self.rows([100] * 4 + [101] * 2 + [(99.9, 101, 100.8)] + [100] + [103] * 40)
        r = rows[0]
        self.assertTrue(r["back_inside"])
        self.assertAlmostEqual(r["gross"], (100 - 101) / 101)                 # out at the close back inside, not at 103
        self.assertLess(r["tight_net"], 0)                                    # the price stop was hit on the dip
        _, rows = self.rows([100] * 48)
        self.assertEqual(rows[0]["state"], "stayed_inside")


class SweepTests(unittest.TestCase):
    def day0(self):
        return profile_day(100, 95, 105, 100)             # PDH 105, PDL 95, POC 100

    def test_a_sweep_is_a_first_breach_that_closes_back_inside_the_same_bar(self):
        today = [100] * 3 + [(100, 106, 104)] + [103] * 4 + [100] * 40
        d = coin([self.day0(), today])
        rows = A.sweep_events("X", d, None, V.iso(T0 + DAY), V.iso(T0 + DAY), outcomes=True)
        r = rows[0]
        self.assertEqual((len(rows), r["side"], r["entry"], r["target"]), (1, 1, 104.0, r["target"]))
        self.assertAlmostEqual(r["target"], 100.0, delta=0.1)                 # the previous day's POC
        self.assertGreater(r["stop"], 106.0)
        self.assertTrue(r["reached"])                                         # the fade (short) got to the POC
        self.assertIsNone(r["flush"])                                         # no open-interest file

    def test_a_bar_that_closes_beyond_the_level_is_a_break_not_a_sweep(self):
        d = coin([self.day0(), [100] * 3 + [(100, 106, 105.5)] + [104] * 44])
        self.assertEqual(A.sweep_events("X", d, None, V.iso(T0 + DAY), V.iso(T0 + DAY), True), [])

    def test_open_interest_falling_over_the_bar_is_a_flush_and_delta_with_the_sweep_is_absorption(self):
        today = [100] * 3 + [(94, 100, 96)] + [97] * 44                        # a sweep of the low at 01:30-02:00
        d = coin([self.day0(), today], taker_share=0.4)                       # sellers aggressive
        t_open = T0 + DAY + 3 * A.HALF
        oi = {"ts": np.array([t_open, t_open + A.HALF]), "oi": np.array([1000.0, 990.0])}
        r = A.sweep_events("X", d, oi, V.iso(T0 + DAY), V.iso(T0 + DAY), True)[0]
        self.assertEqual((r["side"], r["flush"], r["absorbed"]), (-1, True, True))
        oi["oi"] = np.array([1000.0, 1010.0])
        self.assertFalse(A.sweep_events("X", d, oi, V.iso(T0 + DAY), V.iso(T0 + DAY), True)[0]["flush"])
        d2 = coin([self.day0(), today], taker_share=0.6)                      # buyers aggressive into a low sweep
        self.assertFalse(A.sweep_events("X", d2, oi, V.iso(T0 + DAY), V.iso(T0 + DAY), True)[0]["absorbed"])
        self.assertIsNone(A.reading(oi, t_open + 20 * 60_000))                # a reading more than 10 minutes old

    def test_other_levels_near_the_swept_level_are_counted(self):
        # The day opens at 104.9, within 0.25% of the previous high (105): one plain level near.
        today = [104.9] * 3 + [(104.9, 106, 104)] + [103] * 44
        d = coin([self.day0(), today])
        r = A.sweep_events("X", d, None, V.iso(T0 + DAY), V.iso(T0 + DAY), True)[0]
        self.assertGreaterEqual(r["k_plain"], 1)
        self.assertEqual(r["k"], r["k_plain"] + r["k_profile"])


class SessionTests(unittest.TestCase):
    def test_new_york_hours_follow_daylight_saving(self):
        summer = A.ny_sessions(V._ms("2026-07-06"), V._ms("2026-07-07"))
        self.assertIn((V._ms("2026-07-06") + int(13.5 * 3_600_000), V._ms("2026-07-06") + int(20.25 * 3_600_000)), summer)
        winter = A.ny_sessions(V._ms("2026-01-12"), V._ms("2026-01-13"))
        self.assertIn((V._ms("2026-01-12") + int(14.5 * 3_600_000), V._ms("2026-01-12") + int(21.25 * 3_600_000)), winter)
        week = A.ny_sessions(V._ms("2026-07-06"), V._ms("2026-07-12"))
        days = {V.iso(a) for a, _ in week if a >= V._ms("2026-07-06")}
        self.assertEqual(days, {"2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"})   # no weekend


class EndToEndTests(unittest.TestCase):
    def test_counts_run_and_power_on_a_made_up_cache(self):
        rng = np.random.default_rng(11)
        syms = ("BTCUSDT", "AAAUSDT")
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            n = 288 * 120
            for sym in syms:
                close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
                open_ = np.concatenate(([100.0], close[:-1]))
                spread = np.abs(rng.normal(0, 0.001, n)) * close
                vol = rng.random(n) + 0.1
                ts = T0 + np.arange(n) * V.BAR_MS
                np.savez_compressed(cache / f"{sym}-5m.npz", ts=ts, open=open_, high=np.maximum(open_, close) + spread,
                                    low=np.minimum(open_, close) - spread, close=close, volume=vol, taker=vol * rng.random(n))
                np.savez_compressed(cache / f"{sym}-oi.npz", ts=ts, oi=1000 + np.cumsum(rng.normal(0, 1, n)))
            first, last = V.iso(T0 + DAY), V.iso(T0 + 119 * DAY)
            sh = A.shape(first, last, cache, syms)
            res = A.run_study(first, last, cache, syms, draws=300)
            # The run scores what shape counted.
            for kind in ("fresh", "old"):
                self.assertEqual(res["S2"][kind]["races"], sh["S2"][kind]["races"])
            self.assertEqual(res["S3"]["net"]["n"], sh["S3"]["states"].get("accepted", 0))
            self.assertEqual(res["S4"]["R1"]["net"]["n"], sh["S4"]["sweeps"])
            self.assertEqual(res["S4"]["R2"]["with"]["n"] + res["S4"]["R2"]["without"]["n"], sh["S4"]["sweeps"] - sh["S4"]["flush"]["None"])
            self.assertEqual(res["S5"]["near"]["n"] + res["S5"]["alone"]["n"], sh["S4"]["sweeps"])
            self.assertEqual(res["S6"]["two_closes"]["R1"]["rule"]["n"], sh["S6"]["two_closes"]["rule"]["events"])
            self.assertGreater(sh["S6"]["two_closes"]["coin_sessions"], 100)
            self.assertFalse(res["S3"]["met"] and res["S4"]["R1"]["met"] and res["S5"]["met"])
            self.assertIn("within_7d", res["S2"]["revisits"])
            pw = A.power(sh, reps=10)
            self.assertIn("S4_R2", pw)


if __name__ == "__main__":
    unittest.main()
