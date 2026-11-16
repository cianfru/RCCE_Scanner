"""The coin chart's Value layer: profiles, value areas, naked points of control, reference levels."""
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

    def test_build_gives_the_chart_sessions_bins_and_levels(self):
        rows = []
        for d in range(10):
            rows += [(T0 - 7 * DAY + d * DAY + i * 900_000, 100 + d, 101 + d, 99 + d, 100 + d, 5.0) for i in range(96)]
        now = T0 + 3 * DAY - 1
        body = ae.build(candles(rows), None, "4h", now)
        self.assertEqual((body["period"], body["outer_period"], body["interval"]), ("day", "week", "15m"))
        # The first hour of the running day (the Initial Balance): its four 15-minute candles.
        self.assertEqual((body["levels"]["ib_high"], body["levels"]["ib_low"]), (110.0, 108.0))
        self.assertEqual(len(body["sessions"]), 10)
        self.assertTrue(body["sessions"][-1]["live"])
        self.assertEqual([s["live"] for s in body["outer"]], [False, True])      # last week, this week
        # Bins are whole parts per million of the window's volume on one shared grid.
        total = sum(sum(s["bins"]["v"]) for s in body["sessions"])
        self.assertAlmostEqual(total, 1_000_000, delta=200)
        last = body["sessions"][-1]["bins"]
        self.assertLessEqual(last["from"] + len(last["v"]), body["grid"]["rows"])
        self.assertGreater(last["from"], body["sessions"][0]["bins"]["from"])   # later days sit higher


class LayerCacheTests(unittest.TestCase):
    def test_views_of_one_chart_share_a_build_and_its_answer(self):
        calls = []

        async def fake_build(symbol, timeframe):
            calls.append((symbol, timeframe))
            await asyncio.sleep(0.01)
            return {"symbol": symbol, "timeframe": timeframe}

        async def run():
            real, auction._build = auction._build, fake_build
            auction._cache.clear()
            try:
                a, b = await asyncio.gather(auction.levels("BTC/USDT", "4h"), auction.levels("BTC/USDT", "4h"))
                c = await auction.levels("BTC/USDT", "4h")
                await auction.levels("BTC/USDT", "1d")
                return a, b, c
            finally:
                auction._build = real
                auction._cache.clear()

        a, b, c = asyncio.run(run())
        self.assertIs(a, b)
        self.assertIs(a, c)
        self.assertEqual(calls, [("BTC/USDT", "4h"), ("BTC/USDT", "1d")])

    def test_the_hourly_and_four_hour_charts_share_one_build(self):
        calls = []

        async def fake_build(symbol, timeframe):
            calls.append(timeframe)
            return {"symbol": symbol, "timeframe": timeframe, "sessions": [1]}

        async def run():
            real, auction._build = auction._build, fake_build
            auction._cache.clear()
            try:
                return await auction.levels("BTC/USDT", "4h"), await auction.levels("BTC/USDT", "1h")
            finally:
                auction._build = real
                auction._cache.clear()

        four, one = asyncio.run(run())
        self.assertEqual(calls, ["4h"])                      # both read 15-minute candles
        self.assertEqual((four["timeframe"], one["timeframe"], one["sessions"]), ("4h", "1h", [1]))

    def test_a_failed_build_is_not_kept(self):
        async def failing(symbol, timeframe):
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
