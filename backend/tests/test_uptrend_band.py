"""The Uptrend share against its own weekly band (research/uptrend_band.py): the band, the crossings, the comparisons
and the timing against the 55% rule, as declared in docs/reviews/uptrend-band-study.md."""
import unittest

from backtest.risk_on_cycles import SUNDAY, expand_weekly, weekly_rows
from market_history import DAY_MS
from research import late_uptrends as L
from research import uptrend_band as U


def rows_of(shares, start=1000, btc=None):
    return [{"day": start + i, "n": 100, "uptrend": s, "btc": 100.0 if btc is None else btc[i]}
            for i, s in enumerate(shares)]


class FakeValues:
    """Values with fixed outcomes per day and key."""

    def __init__(self, table, share=None):
        self.table, self.share = table, share or {}

    def get(self, d, key):
        return self.table.get(d, {}).get(key)


class BandTests(unittest.TestCase):
    def test_the_band_is_btcs_band_code_on_the_share(self):
        shares = [0.2 + 0.6 * ((i // 9) % 5) / 4 for i in range(400)]
        rows = rows_of(shares, start=18748)
        share = {r["day"]: r["uptrend"] for r in rows}
        self.assertEqual(U.share_band(rows), expand_weekly(weekly_rows(share, SUNDAY), share))

    def test_sunday_values_completed_weeks_used_from_the_next_day(self):
        rows = rows_of([0.5] * 300, start=18748)              # 18748 is a Saturday; 18749 a Sunday (day % 7 == 3)
        band = U.share_band(rows)
        sundays = [d for d in range(18748, 19048) if d % 7 == SUNDAY]
        self.assertEqual(sundays[0], 18749)
        first = sundays[20]                                   # the 21st Sunday completes the band
        self.assertNotIn(first, band, "a Sunday's band is used from the next day")
        self.assertEqual(min(band), first + 1)
        self.assertEqual(band[first + 1], (0.5, 0.5))

    def test_a_sunday_uses_the_previous_weeks_band(self):
        shares = [0.3] * 200 + [0.9] * 100
        rows = rows_of(shares, start=18748)
        band = U.share_band(rows)
        wk = dict(weekly_rows({r["day"]: r["uptrend"] for r in rows}, SUNDAY))
        sun = next(d for d in range(18948, 19048) if d % 7 == SUNDAY and d - 7 in wk and wk[d - 7])
        self.assertEqual(band[sun], wk[sun - 7])
        self.assertEqual(band[sun + 1], wk[sun])

    def test_edges_are_inside(self):
        self.assertEqual(U.side(0.40, (0.40, 0.50)), "inside")
        self.assertEqual(U.side(0.50, (0.40, 0.50)), "inside")
        self.assertEqual(U.side(0.3999, (0.40, 0.50)), "under")
        self.assertEqual(U.side(0.5001, (0.40, 0.50)), "over")


class CrossingTests(unittest.TestCase):
    def test_gaps_of_up_to_five_days_join(self):
        days = list(range(100))
        self.assertEqual(U.stretches(days, {10, 16}), [[10, 16]], "5 days between: one stretch")
        self.assertEqual(U.stretches(days, {10, 17}), [[10, 10], [17, 17]], "6 days between: two")

    def test_a_crossing_needs_the_band_on_the_six_days_before(self):
        rows = rows_of([0.5] * 40)
        band = {d: (0.4, 0.45) for d in range(1000, 1040)}
        rows[3]["uptrend"] = 0.3                             # under on the band's 4th day: start unknown
        rows[30]["uptrend"] = 0.3                            # under on day 30: a crossing
        cx = U.crossings(rows, band)
        self.assertEqual([(s["first"], s["known"]) for s in cx["under"]], [(1003, False), (1030, True)])
        self.assertEqual(U.crossing_days(cx, "under"), [1030])
        self.assertEqual(U.crossing_days(cx, "over"), [], "one long stretch over from the band's first day: unknown")
        rows[6]["uptrend"] = 0.3
        cx = U.crossings(rows, band)
        self.assertEqual([s["first"] for s in cx["under"]], [1003, 1030], "day 6 joins the stretch from day 3")

    def test_the_cooldown_looks_at_every_crossing_of_the_kind(self):
        self.assertEqual(U.counted([0, 20, 40, 75]), [0, 75], "20 and 40 each follow a crossing within 30 days")
        self.assertEqual(U.counted([0, 30, 61]), [0, 61], "30 days after is still inside")
        self.assertEqual(U.counted([0, 31]), [0, 31])


class ComparisonTests(unittest.TestCase):
    def test_comparison_days(self):
        share = {d: 0.5 for d in range(0, 200)}
        share[100] = 0.60
        share[101] = 0.6001
        vals = FakeValues({d: {"alt60": 1.0} for d in range(0, 190)}, share)
        pool = U.comparison_days(list(range(0, 200)), vals, 50, [50, 120], "alt60")
        self.assertIn(100, pool, "within 10 points, inclusive")
        self.assertNotIn(101, pool)
        for d in (50, 80, 120, 150):
            self.assertNotIn(d, pool, "a crossing and the 30 days after it are left out")
        self.assertIn(81, pool)
        self.assertIn(151, pool)
        self.assertNotIn(195, pool, "no outcome")

    def _block(self, ev_vals, sign=-1, edge=10.0, pool_vals=None):
        n = len(ev_vals)
        events = list(range(n))
        pool_vals = pool_vals or [0.0, 2.0, -2.0, 1.0, -1.0] * 4
        table = {e: {"alt60": v} for e, v in zip(events, ev_vals)}
        pool = list(range(1000, 1000 + len(pool_vals)))
        for d, v in zip(pool, pool_vals):
            table[d] = {"alt60": v}
        return U.price_block(events, [pool] * n, FakeValues(table), "alt60", sign, edge)

    def test_the_bar_needs_every_check(self):
        good = [-30.0, -25.0, -20.0, -35.0, -28.0, 5.0, -22.0, -31.0, -26.0, -24.0]
        b = self._block(good)
        self.assertEqual(b["verdict"], "met")
        self.assertEqual(b["same_way"], 9)
        self.assertEqual(b["draws_beyond"], 0.0)
        self.assertEqual(self._block(good[:7])["verdict"], "not met", "seven events are too few")
        mixed = [-30.0, -25.0, -20.0, 5.0, 4.0, 3.0, -22.0, -31.0, -26.0, -24.0]
        self.assertFalse(self._block(mixed)["consistent"], "7 of 10 is under 75%")
        small = [-9.0] * 10
        self.assertFalse(self._block(small)["edge"], "a 9-point gap is under the 10-point bar")
        late = [-30.0, -25.0, -20.0, -35.0, -28.0, 30.0, 25.0, -31.0, 26.0, 24.0]
        self.assertFalse(self._block(late)["halves_agree"])

    def test_draws_are_compared_the_declared_way(self):
        up = [30.0, 25.0, 20.0, 35.0, 28.0, -5.0, 22.0, 31.0, 26.0, 24.0]
        self.assertEqual(self._block(up, sign=+1)["verdict"], "met")
        self.assertEqual(self._block(up, sign=-1)["verdict"], "not met")
        self.assertEqual(self._block(up, sign=-1)["draws_beyond"], 1.0, "every draw's median is at or below +25")

    def test_random_draws_see_a_wide_pool(self):
        wide = [float(x) for x in range(-60, 61, 3)]
        b = self._block([-12.0] * 10, pool_vals=wide)
        self.assertTrue(b["edge"] and b["consistent"])
        self.assertFalse(b["beyond_random"], "a 12-point gap is common among medians of 10 draws from this pool")


class TimingTests(unittest.TestCase):
    def s(self, first, last, known=True):
        return {"first": first, "last": last, "known": known}

    def test_end_cases(self):
        run = {"start": 100, "end": 200}
        self.assertEqual(U.end_case(run, [self.s(180, 230)], 1000), {"case": "band first", "cross": 180, "lead": 20})
        self.assertEqual(U.end_case(run, [self.s(200, 230)], 1000)["case"], "same day")
        self.assertEqual(U.end_case(run, [self.s(90, 230)], 1000)["case"], "under since before the run")
        self.assertEqual(U.end_case(run, [self.s(150, 160), self.s(210, 230)], 1000),
                         {"case": "band later", "cross": 210, "lead": -10}, "a stretch that ended before E is not it")
        self.assertEqual(U.end_case(run, [self.s(261, 270)], 1000)["case"], "none within 60 days")
        self.assertEqual(U.end_case(run, [], 250)["case"], "not known yet")
        self.assertEqual(U.end_case(run, [self.s(180, 230, known=False)], 1000)["case"], "start unknown")

    def test_start_cases(self):
        run = {"start": 300}
        self.assertEqual(U.start_case(run, 200, [self.s(280, 400)], 1000), {"case": "band first", "cross": 280, "lead": 20})
        self.assertEqual(U.start_case(run, 200, [self.s(300, 400)], 1000)["case"], "same day")
        self.assertEqual(U.start_case(run, 200, [self.s(150, 400)], 1000)["case"], "over since before the dip")
        self.assertEqual(U.start_case(run, 200, [self.s(320, 400)], 1000)["lead"], -20)
        self.assertEqual(U.start_case(run, 200, [self.s(361, 400)], 1000)["case"], "none within 60 days")
        self.assertEqual(U.start_case(run, 200, [], 330)["case"], "not known yet")

    def test_lead_needs_eight_runs_three_of_four_first_and_ten_days(self):
        cases = [{"case": "band first", "lead": 15}] * 6 + [{"case": "band later", "lead": -3}] * 2
        v = U.lead_verdict(cases)
        self.assertTrue(v["enough"] and v["mostly_first"] and v["long_enough"])
        self.assertEqual(v["median_lead"], 15)
        v = U.lead_verdict(cases[:7])
        self.assertFalse(v["enough"])
        v = U.lead_verdict(cases[:5] + [{"case": "same day", "lead": 0}] + cases[6:])
        self.assertFalse(v["mostly_first"], "the same day is not first: 5 of 8")
        v = U.lead_verdict([{"case": "under since before the run"}] * 3 + cases)
        self.assertEqual(v["runs_with_both"], 8, "runs without a crossing of their own are left out")
        self.assertFalse(U.lead_verdict([{"case": "band first", "lead": 9}] * 8)["long_enough"])

    def test_false_alarms(self):
        # One run from day 10, end day 100 (its 5th day under 55% is 104); then off.
        shares = [0.3] * 10 + [0.7] * 90 + [0.4] * 100 + [0.7] * 20 + [0.4] * 30
        rows = rows_of(shares, start=0)
        state, runs = L.runs(rows)
        self.assertEqual((runs[0]["start"], runs[0]["end"]), (10, 100))
        fa = U.false_alarms([20, 50, 102], state, runs, True, rows[-1]["day"], ends=True)
        self.assertEqual([r["followed"] for r in fa["rows"]], [False, True, True],
                         "day 20: the end is 80 days on; day 102 is a dip day after the end day")
        self.assertFalse(fa["few_false_alarms"], "2 of 3 is under 75%")
        fa = U.false_alarms([110, 150, 205, 230], state, runs, False, rows[-1]["day"], ends=False)
        self.assertEqual([r["followed"] for r in fa["rows"]], [False, True, None],
                         "day 110: the start (200) is 90 days on; 205 is inside a run; day 230's 60 days are not over")
        self.assertEqual(fa["known"], 2)

    def test_part_b_on_a_ramp(self):
        up = [0.2 + 0.035 * i for i in range(20)]
        down = [0.9 - 0.035 * i for i in range(20)]
        shares = [0.2] * 220 + up + [0.9] * 160 + down + [0.2] * 120
        rows = rows_of(shares, start=18748)
        band = U.share_band(rows)
        cx = U.crossings(rows, band)
        state, runs = L.runs(rows)
        vals = U.Values(rows, lambda a, b: None)
        res = U.part_b(rows, band, cx, vals, state, runs)
        self.assertEqual(len(res["runs"]), 1)
        r = res["runs"][0]
        self.assertEqual(r["start_case"], "band first")
        self.assertEqual(r["end_case"], "band first")
        self.assertGreater(r["start_lead"], 0)
        self.assertGreater(r["end_lead"], 0)
        self.assertEqual(r["end_lead_vs_known"], r["end_lead"] + 4)
        self.assertEqual(r["end_prices"]["between"]["earlier"], "band")
        self.assertEqual(res["ends"]["verdict"], "not met", "one run is too few")


class DataTests(unittest.TestCase):
    def test_rows_add_overheated_to_uptrend(self):
        snap = {"columns": ["day", "n", "uptrend", "overheated", "downtrend", "basing", "median_z", "btc"],
                "days": [[18748, 40, 0.5, 0.05, 0.1, 0.35, 0.0, 50000.0]]}
        r = U.load_rows(snap)[0]
        self.assertAlmostEqual(r["uptrend"], 0.55)
        self.assertEqual((r["day"], r["n"], r["btc"]), (18748, 40, 50000.0))

    def test_closes_need_two_hundred_candles_and_closed_days(self):
        fetched = {"pairs": {"OLDUSDT": [[d, float(d)] for d in range(100, 400)],
                             "NEWUSDT": [[d, 1.0] for d in range(250, 401)]}}
        c = U.closes_by_day(fetched, [298, 299, 300, 399, 400], last_day=399)
        self.assertNotIn("OLDUSDT", c.get(298, {}), "the 199th candle")
        self.assertEqual(c[299]["OLDUSDT"], 299.0, "the 200th candle")
        self.assertNotIn("NEWUSDT", c[399], "150 candles")
        self.assertNotIn(400, c, "after the last closed day")

    def test_alt_change_needs_twenty_alts_and_leaves_btc_out(self):
        a = {f"C{i}": 1.0 for i in range(20)}
        b = {f"C{i}": 1.1 for i in range(20)}
        a["BTCUSDT"], b["BTCUSDT"] = 1.0, 5.0
        self.assertEqual(U.alt_change({0: a, 30: b}, 0, 30), 10.0)
        del b["C0"]
        self.assertIsNone(U.alt_change({0: a, 30: b}, 0, 30))

    def test_shape_reads_no_outcome(self):
        shares = [0.2 + 0.6 * ((i // 40) % 2) for i in range(500)]
        snap = {"columns": ["day", "n", "uptrend", "overheated", "downtrend", "basing", "median_z", "btc"],
                "days": [[18748 + i, 100, s, 0.0, 0.0, 0.0, 0.0, 1.0] for i, s in enumerate(shares)]}
        text = str(U.shape(snap))
        for word in ("alt30", "alt60", "btc30", "btc60", "median"):
            self.assertNotIn(word, text)

    def test_the_bar_on_simulated_data(self):
        p = U.power(10, 28.0, shifts=(0, 40), reps=2000)
        self.assertLess(p[0], 0.05)
        self.assertGreater(p[40], 0.8)

    def test_day_ms(self):
        self.assertEqual(DAY_MS, 86_400_000)


if __name__ == "__main__":
    unittest.main()
