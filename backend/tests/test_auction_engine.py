"""The coin chart's Value layer: profiles, value areas, swings and their profiles, reference levels."""
import asyncio
import unittest

import numpy as np

import auction
from engines import auction_engine as ae

DAY = ae.DAY_MS
T0 = 1_788_739_200_000            # Monday 2026-09-07 00:00 UTC


def candles(rows):
    """rows: (ts_ms, open, high, low, close, volume)."""
    a = np.array(rows, dtype=np.float64)
    return {"timestamp": a[:, 0], "open": a[:, 1], "high": a[:, 2], "low": a[:, 3], "close": a[:, 4], "volume": a[:, 5]}


def flat_day(start, price, bars=24, volume=10.0):
    """A day of hourly candles inside one half-point row: [price, price + 0.5)."""
    return [(start + i * 3_600_000, price + 0.2, price + 0.4, price + 0.1, price + 0.3, volume) for i in range(bars)]


class ProfileTests(unittest.TestCase):
    def test_volume_is_split_evenly_over_the_rows_a_candle_touches(self):
        base, rows = ae.profile([104.0], [100.0], [50.0], 1.0)
        self.assertEqual(base, 100.0)
        np.testing.assert_allclose(rows, [10, 10, 10, 10, 10])

    def test_the_profile_keeps_all_the_volume_and_no_dust(self):
        rng = np.random.default_rng(1)
        low = 100 + rng.random(500) * 20
        high = low + rng.random(500) * 3
        vol = rng.random(500) * 100
        _, rows = ae.profile(high, low, vol, 0.25, base=90.0, rows=400)
        self.assertAlmostEqual(rows.sum(), vol.sum(), places=6)
        self.assertTrue((rows[:40] == 0).all() and (rows[140:] == 0).all())

    def test_value_area_grows_two_rows_at_a_time_towards_more_volume(self):
        vol = np.array([1, 1, 5, 9, 20, 9, 8, 8, 1, 1], dtype=float)     # total 63, 70% = 44.1
        poc, lo, hi = ae.value_area(vol)
        self.assertEqual(poc, 4)
        # 20, then up (9 + 8 = 17 > 9 + 5 = 14) = 37, then down (14 > 8 + 1) = 51 >= 44.1.
        self.assertEqual((lo, hi), (2, 6))
        self.assertGreaterEqual(vol[lo:hi + 1].sum() / vol.sum(), ae.VALUE_SHARE)

    def test_a_tied_point_of_control_is_the_row_nearest_the_middle(self):
        self.assertEqual(ae.value_area(np.array([7, 1, 1, 7, 1, 1, 1], dtype=float))[0], 3)

    def test_step_is_a_round_number_at_or_below_the_fraction_of_price(self):
        self.assertEqual(ae.nice_step(65_000 * 2e-4), 10.0)       # 13 -> 10
        self.assertEqual(ae.nice_step(1_900 * 2e-4), 0.25)        # 0.38 -> 0.25
        self.assertAlmostEqual(ae.nice_step(0.000012 * 2e-4), 2e-9)
        with self.assertRaises(ValueError):
            ae.nice_step(0)


class SessionTests(unittest.TestCase):
    def test_sessions_start_at_utc_midnight_monday_and_the_first_of_the_month(self):
        ts = [T0 + 5 * 3_600_000, T0 + 3 * DAY, T0 + 30 * DAY]        # Mon 7 Sep, Thu 10 Sep, Wed 7 Oct
        np.testing.assert_array_equal(ae.session_starts(ts, "day"), [T0, T0 + 3 * DAY, T0 + 30 * DAY])
        np.testing.assert_array_equal(ae.session_starts(ts, "week"), [T0, T0, T0 + 28 * DAY])
        sep1, oct1 = T0 - 6 * DAY, T0 + 24 * DAY
        np.testing.assert_array_equal(ae.session_starts(ts, "month"), [sep1, sep1, oct1])
        self.assertEqual(ae.session_end(sep1, "month"), oct1)
        self.assertEqual(ae.session_end(T0, "week"), T0 + 7 * DAY)

    def test_value_area_and_point_of_control_of_a_session(self):
        # Most of the day's volume at 100, a thin excursion to 110.
        rows = flat_day(T0, 100.0, bars=20, volume=100.0) + [(T0 + (20 + i) * 3_600_000, 105, 110, 104, 108, 1.0) for i in range(4)]
        s = ae.sessions(candles(rows), "day", 0.5, T0 + DAY + 1)[0]
        self.assertEqual(s["poc"], 100.25)                # the centre of the row holding the volume
        self.assertEqual((s["vah"], s["val"]), (100.5, 100.1))   # that row alone holds over 70%; VAL stops at the low
        self.assertEqual((s["high"], s["low"], s["live"]), (110.0, 100.1, False))

    def test_a_point_of_control_is_naked_until_a_later_candle_trades_through_it(self):
        rows = flat_day(T0, 100.0) + flat_day(T0 + DAY, 120.0) + flat_day(T0 + 2 * DAY, 121.0)
        # Day 4 comes back down through 100 in its third hour.
        day4 = flat_day(T0 + 3 * DAY, 119.0, bars=2) + [(T0 + 3 * DAY + 2 * 3_600_000, 119, 119.4, 99, 100, 10.0)]
        out = ae.sessions(candles(rows + day4), "day", 0.5, T0 + 3 * DAY + 4 * 3_600_000)
        self.assertEqual([s["poc"] for s in out[:3]], [100.25, 120.25, 121.25])
        self.assertEqual(out[0]["touched"], (T0 + 3 * DAY + 2 * 3_600_000) // 1000)
        self.assertIsNone(out[1]["touched"])            # day 4 never traded up to 120.25
        self.assertIsNone(out[2]["touched"])
        self.assertTrue(out[3]["live"])
        self.assertIsNone(out[3]["touched"])            # a session still running has no finished POC

    def test_a_session_the_candles_start_inside_is_left_out(self):
        rows = flat_day(T0 + 6 * 3_600_000, 100.0, bars=18) + flat_day(T0 + DAY, 101.0)
        out = ae.sessions(candles(rows), "day", 0.5, T0 + 3 * DAY)
        self.assertEqual([s["start"] for s in out], [(T0 + DAY) // 1000])

    def test_reference_levels_come_from_the_daily_candles(self):
        # Daily candles from Mon 31 Aug to Wed 9 Sep (live): open = 100 + day number.
        first = T0 - 7 * DAY
        daily = candles([(first + i * DAY, 100 + i, 110 + i, 90 + i, 100 + i, 1.0) for i in range(10)])
        now = T0 + 2 * DAY + 3_600_000
        day = ae.reference_levels(daily, "day", now)
        self.assertEqual(day, {"w_open": 107.0, "m_open": 101.0, "d_open": 109.0, "pd_high": 118.0, "pd_low": 98.0})
        week = ae.reference_levels(daily, "week", now)
        self.assertEqual(week, {"w_open": 107.0, "m_open": 101.0, "pw_high": 116.0, "pw_low": 90.0})
        self.assertEqual(ae.reference_levels(None, "day", now), {})

    def test_the_retracement_band_of_a_live_major_leg(self):
        # Flat near 100 (ATR about 1), a swing low at 95, a leg up to 150, then a pullback to 140.
        prices = [100] * 20 + [95] + list(np.linspace(100, 150, 12)) + [146, 142, 140]
        day0 = T0 - 40 * DAY
        daily = candles([(day0 + i * DAY, p, p + 0.5, p - 0.5, p, 1.0) for i, p in enumerate(prices)])
        zones = ae.fib_zones(daily)
        up = [z for z in zones if z["direction"] == 1]
        self.assertEqual(len(up), 1)
        z = up[0]
        self.assertEqual((z["base"], z["extreme"]), (94.5, 150.5))            # the swing low and the highest price since
        self.assertAlmostEqual(z["from"], 150.5 - 0.618 * 56, places=6)
        self.assertAlmostEqual(z["to"], 150.5 - 0.66 * 56, places=6)
        self.assertFalse(z["touched"])                                        # the pullback stopped at 139.5
        self.assertEqual(z["base_time"], (day0 + 20 * DAY) // 1000)
        # Deeper, into the band: touched. Under the swing low: the leg is gone.
        deeper = candles([(day0 + i * DAY, p, p + 0.5, p - 0.5, p, 1.0) for i, p in enumerate(prices + [116])])
        self.assertTrue([z for z in ae.fib_zones(deeper) if z["direction"] == 1][0]["touched"])
        gone = candles([(day0 + i * DAY, p, p + 0.5, p - 0.5, p, 1.0) for i, p in enumerate(prices + [116, 94])])
        self.assertEqual([z for z in ae.fib_zones(gone) if z["direction"] == 1], [])
        self.assertEqual(ae.fib_zones(None), [])


def swing_market(heavy=(120.0, 122.0)):
    """Hourly candles for 44 days and the daily candles they add up to: flat at 100 for 20 days, a low at 95 on
    day 20, a rise to 150 by day 32, a fall to 118 by day 40, then 4 quiet days. Hours between `heavy` prices
    trade 50 times the volume of the rest."""
    days = [100.0] * 20 + [95.0] + list(np.linspace(100, 150, 12)) + list(np.linspace(146, 118, 8)) + [119.0, 120.0, 119.0]
    start = T0 - 40 * DAY
    hours = []
    for d, (p0, p1) in enumerate(zip(days, days[1:])):
        for i in range(24):
            p = p0 + (p1 - p0) * i / 24
            hours.append((start + d * DAY + i * 3_600_000, p, p + 0.5, p - 0.5, p, 500.0 if heavy[0] <= p < heavy[1] else 10.0))
    a = np.array(hours)
    daily = [(start + d * DAY, a[d * 24, 1], a[d * 24:(d + 1) * 24, 2].max(), a[d * 24:(d + 1) * 24, 3].min(), a[(d + 1) * 24 - 1, 4],
              a[d * 24:(d + 1) * 24, 5].sum()) for d in range(len(days) - 1)]
    return candles(hours), candles(daily), start


class SwingRangeTests(unittest.TestCase):
    def test_each_swing_gets_its_own_profile(self):
        hourly, daily, start = swing_market()
        now = start + 43 * DAY - 1
        up, down = ae.swing_ranges(hourly, daily, 0.5, now)
        # The rise: from the hour of the low on day 20 to the hour of the high on day 32.
        self.assertEqual((up["direction"], up["live"]), (1, False))
        self.assertEqual((up["low"], up["high"]), (94.5, 150.5))
        self.assertEqual(up["start"], (start + 20 * DAY) // 1000)                     # day 20 opens at its low
        self.assertEqual(up["end"], (start + 32 * DAY + 3_600_000) // 1000)           # day 32 opens at its high; the candle's close
        self.assertTrue(120 <= up["poc"] < 122)                                       # where the volume was
        self.assertTrue(up["low"] <= up["val"] <= up["poc"] <= up["vah"] <= up["high"])
        bins = up["bins"]
        self.assertEqual((len(bins["v"]), max(bins["v"]), bins["low"]), (ae.RANGE_ROWS, 1000, 94.5))
        self.assertAlmostEqual(bins["step"], 56 / ae.RANGE_ROWS)
        fullest = bins["low"] + (int(np.argmax(bins["v"])) + 0.5) * bins["step"]
        self.assertTrue(119.5 <= fullest <= 122.5)
        # The fall still running: from that high to the last candle.
        self.assertEqual((down["direction"], down["live"]), (-1, True))
        self.assertEqual(down["start"], (start + 32 * DAY) // 1000)
        self.assertEqual(down["end"], (start + 43 * DAY) // 1000)
        self.assertEqual((down["high"], down["low"]), (150.5, 117.5))

    def test_a_pullback_of_less_than_half_a_move_does_not_end_it_when_the_move_goes_on(self):
        L, H = (lambda p: ("L", p)), (lambda p: ("H", p))
        # A rise of 20, a dip of 7 (35%), then a higher high: one rise from 62 to 87.
        self.assertEqual(ae.merge_moves([L(62), H(82), L(75), H(87)]), [L(62), H(87)])
        # A dip of 51% ends the rise. So does a dip of 35% that is not followed by a higher high.
        self.assertEqual(ae.merge_moves([L(58), H(67), L(62.4), H(82)]), [L(58), H(67), L(62.4), H(82)])
        self.assertEqual(ae.merge_moves([L(62), H(82), L(75), H(80)]), [L(62), H(82), L(75), H(80)])
        # Falls mirror: a bounce of 43% of the fall, then a lower low.
        self.assertEqual(ae.merge_moves([H(2810), L(2173), H(2450), L(1710)]), [H(2810), L(1710)])
        # The merged rise is measured against the next dip too, and the points before it stay.
        self.assertEqual(ae.merge_moves([H(70), L(62), H(82), L(75), H(87), L(80), H(95)]), [H(70), L(62), H(95)])
        # A move that grows by a merge can take in the pullback before it: 100 to 110, back to 106, up to 109 (not
        # beyond 110), back to 108, then 120: first 106 to 120 becomes one rise, then 100 to 120.
        self.assertEqual(ae.merge_moves([L(100), H(110), L(106), H(109), L(108), H(120)]), [L(100), H(120)])
        self.assertEqual(ae.merge_moves([L(1), H(2)]), [L(1), H(2)])

    def test_the_running_moves_reach_can_merge_it_with_the_move_before(self):
        # The rise to 150, a dip to 136 (a quarter of the rise from 95) that turns into a swing, then 160 without
        # a new swing: one rise from the low, still running.
        days = [100.0] * 20 + [95.0] + list(np.linspace(100, 150, 12)) + list(np.linspace(147, 136, 4)) + list(np.linspace(140, 160, 6))
        start = T0 - 40 * DAY
        hours = [(start + d * DAY + i * 3_600_000, p0 + (p1 - p0) * i / 24, p0 + (p1 - p0) * i / 24 + 0.5, p0 + (p1 - p0) * i / 24 - 0.5,
                  p0 + (p1 - p0) * i / 24, 10.0) for d, (p0, p1) in enumerate(zip(days, days[1:])) for i in range(24)]
        a = np.array(hours)
        n = len(days) - 1
        daily = candles([(start + d * DAY, a[d * 24, 1], a[d * 24:(d + 1) * 24, 2].max(), a[d * 24:(d + 1) * 24, 3].min(), a[(d + 1) * 24 - 1, 4], 240.0)
                         for d in range(n)])
        kinds = [p[0] for p in ae.swings(daily["high"], daily["low"], __import__("engines.levels_engine", fromlist=["wilder_atr"]).wilder_atr(daily["high"], daily["low"], daily["close"]))]
        self.assertEqual(kinds, ["L", "H", "L"])                                     # the dip was a swing of its own
        ranges = ae.swing_ranges(candles(hours), daily, 0.5, start + n * DAY - 1)
        self.assertEqual([(r["direction"], r["live"], r["low"]) for r in ranges], [(1, True, 94.5)])
        self.assertEqual(ranges[0]["start"], (start + 20 * DAY) // 1000)

    def test_a_swing_the_candles_start_inside_is_left_out(self):
        hourly, daily, start = swing_market()
        late = {k: v[25 * 24:] for k, v in hourly.items()}                            # hourly candles from day 25, inside the rise
        ranges = ae.swing_ranges(late, daily, 0.5, start + 43 * DAY - 1)
        self.assertEqual([(r["direction"], r["live"]) for r in ranges], [(-1, True)])

    def test_no_swings_without_daily_candles(self):
        hourly, daily, start = swing_market()
        self.assertEqual(ae.swing_ranges(hourly, None, 0.5, start + 43 * DAY), [])
        short = {k: v[:20] for k, v in daily.items()}
        self.assertEqual(ae.swing_ranges(hourly, short, 0.5, start + 43 * DAY), [])

    def test_build_gives_a_coins_charts_their_swings_levels_and_zone(self):
        hourly, daily, start = swing_market()
        now = start + 43 * DAY - 1
        body = ae.build(hourly, daily, now)
        self.assertEqual((body["version"], body["interval"], body["from"]), ("auction-2", "1h", start // 1000))
        self.assertEqual([r["direction"] for r in body["ranges"]], [1, -1])
        # The day's and the week's levels together; each chart shows its own.
        self.assertEqual(set(body["levels"]), {"d_open", "pd_high", "pd_low", "w_open", "pw_high", "pw_low", "m_open", "ib_high", "ib_low"})
        self.assertEqual(body["levels"]["ib_high"], 120.5)                            # the running day's first hourly candle (120 to 120.5)
        self.assertNotIn("sessions", body)
        down = [z for z in body["fib"] if z["direction"] == -1]
        self.assertEqual((down[0]["base"], down[0]["extreme"]), (150.5, 117.5))
        bare = ae.build(hourly, None, now)
        self.assertEqual((bare["ranges"], bare["fib"], set(bare["levels"])), ([], [], {"ib_high", "ib_low"}))


class LayerCacheTests(unittest.TestCase):
    def test_views_of_one_chart_share_a_build_and_its_answer(self):
        calls = []

        async def fake_build(symbol):
            calls.append(symbol)
            await asyncio.sleep(0.01)
            return {"symbol": symbol, "ranges": [1]}

        async def run():
            real, auction._build = auction._build, fake_build
            auction._cache.clear()
            try:
                a, b = await asyncio.gather(auction.levels("BTC/USDT", "4h"), auction.levels("BTC/USDT", "4h"))
                c = await auction.levels("BTC/USDT", "4h")
                await auction.levels("ETH/USDT", "4h")
                return a, b, c
            finally:
                auction._build = real
                auction._cache.clear()

        a, b, c = asyncio.run(run())
        self.assertEqual((a, b), (c, c))
        self.assertEqual(calls, ["BTC/USDT", "ETH/USDT"])

    def test_a_coins_three_charts_share_one_build(self):
        calls = []

        async def fake_build(symbol):
            calls.append(symbol)
            return {"symbol": symbol, "ranges": [1]}

        async def run():
            real, auction._build = auction._build, fake_build
            auction._cache.clear()
            try:
                return await auction.levels("BTC/USDT", "4h"), await auction.levels("BTC/USDT", "1h"), await auction.levels("BTC/USDT", "1d")
            finally:
                auction._build = real
                auction._cache.clear()

        four, one, day = asyncio.run(run())
        self.assertEqual(calls, ["BTC/USDT"])                # all three read the same hourly candles
        self.assertEqual((four["timeframe"], one["timeframe"], day["timeframe"], day["ranges"]), ("4h", "1h", "1d", [1]))

    def test_a_failed_build_is_not_kept(self):
        async def failing(symbol):
            raise auction.NoData("No intraday candles for this market")

        async def run():
            real, auction._build = auction._build, failing
            auction._cache.clear()
            try:
                with self.assertRaises(auction.NoData):
                    await auction.levels("NOPE/USDT", "4h")
                return dict(auction._cache), dict(auction._building)
            finally:
                auction._build = real

        cache, building = asyncio.run(run())
        self.assertEqual((cache, building), ({}, {}))


class EndpointTests(unittest.TestCase):
    def get(self, path, answer):
        from unittest import mock
        from fastapi.testclient import TestClient
        import main

        async def fake(symbol, timeframe):
            self.asked = (symbol, timeframe)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with mock.patch.object(auction, "levels", fake):
            return TestClient(main.app).get(path)

    def test_the_layer_is_served_per_chart(self):
        r = self.get("/api/auction/BTC-USDT?timeframe=1d", {"sessions": []})
        self.assertEqual((r.status_code, r.json(), self.asked), (200, {"sessions": []}, ("BTC/USDT", "1d")))

    def test_busy_no_data_ratios_and_other_timeframes_are_refused(self):
        r = self.get("/api/auction/BTC/USDT", auction.Busy("budget"))
        self.assertEqual((r.status_code, r.headers.get("retry-after")), (503, "30"))
        self.assertEqual(self.get("/api/auction/BTC/USDT", auction.NoData("No intraday candles for this market")).status_code, 404)
        self.assertEqual(self.get("/api/auction/ETH/BTC", {}).status_code, 422)
        self.assertEqual(self.get("/api/auction/BTC/USDT?timeframe=1w", {}).status_code, 422)

    def test_the_hourly_chart_is_candles_read_on_demand(self):
        from unittest import mock
        from fastapi.testclient import TestClient
        import main
        n = 120
        ts = (T0 + np.arange(n) * 3_600_000).astype(np.float64)
        price = 100 + np.arange(n) * 0.1
        candles_1h = {"timestamp": ts, "open": price, "high": price + 1, "low": price - 1, "close": price + 0.5, "volume": np.full(n, 7.0)}

        async def hourly(symbol):
            self.asked = symbol
            return candles_1h

        async def stored(symbol, timeframe, **_):
            return None                                   # no weekly band without stored candles

        with mock.patch.object(auction, "hour_candles", hourly), mock.patch("data_fetcher.fetch_ohlcv", stored):
            r = TestClient(main.app).get("/api/chart/BTC-USDT?timeframe=1h&limit=100")
        body = r.json()
        self.assertEqual((r.status_code, self.asked, body["timeframe"], len(body["candles"])), (200, "BTC/USDT", "1h", 100))
        self.assertEqual(body["candles"][-1], {"time": int(ts[-1] // 1000), "open": price[-1], "high": price[-1] + 1,
                                               "low": price[-1] - 1, "close": price[-1] + 0.5})
        self.assertEqual((body["volume"][-1]["value"], body["trend"], body["cto_ribbon"], body["patterns"], body["bmsb_mid"]),
                         (7.0, None, None, [], []))

        async def busy(symbol):
            raise auction.Busy("budget")
        with mock.patch.object(auction, "hour_candles", busy):
            self.assertEqual(TestClient(main.app).get("/api/chart/BTC/USDT?timeframe=1h").status_code, 503)


if __name__ == "__main__":
    unittest.main()
