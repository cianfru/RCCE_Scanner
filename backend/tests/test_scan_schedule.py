import unittest
from scan_schedule import ScanSchedule, refresh_interval, last_bar_close, BAR_SECONDS, SETTLE_SECONDS


class ScheduleTests(unittest.TestCase):
    def test_full_universe_initial_pass_without_duplicates(self):
        schedule = ScanSchedule()
        symbols = [f'T{i}/USDC' for i in range(482)] + ['BTC/USDT']
        visited = []
        for now in range(len(symbols)):
            symbol = schedule.next_due(symbols, now, lambda s: 'active', lambda s: 'spot', True)
            visited.append(symbol)
            schedule.record(symbol, now, True)
        self.assertEqual(visited[0], 'BTC/USDT')
        self.assertEqual(set(visited), set(symbols))
        self.assertIsNone(schedule.next_due(symbols, 500, lambda s: 'active', lambda s: 'spot', True))

    def test_wall_clock_and_activity_changes(self):
        schedule = ScanSchedule()
        schedule.record('BTC', 0, True)
        def due(now, active=True):
            return schedule.next_due(['BTC'], now, lambda s: 'hot', lambda s: 'perpetual', active)
        self.assertIsNone(due(899))
        self.assertEqual(due(900), 'BTC')
        self.assertIsNone(due(901, False))
        self.assertEqual(due(3600, False), 'BTC')

    def test_unavailable_backoff_and_recovery(self):
        schedule = ScanSchedule()
        schedule.record('NEW', 0, False)
        due = lambda now: schedule.next_due(['NEW'], now, lambda s: 'hot', lambda s: 'spot', True)
        self.assertIsNone(due(3599))
        self.assertEqual(due(3600), 'NEW')
        schedule.record('NEW', 3600, True)
        self.assertEqual(due(4500), 'NEW')

    def test_oldest_due_is_not_starved_and_delisting_prunes(self):
        schedule = ScanSchedule()
        schedule.record('HOT', 4000, True)
        schedule.record('COLD', 0, True)
        self.assertEqual(schedule.next_due(['HOT', 'COLD'], 5000,
                         lambda s: 'hot' if s == 'HOT' else 'cold', lambda s: 'spot', True), 'COLD')
        schedule.prune(['HOT'])
        self.assertNotIn('COLD', schedule.attempts)

    def test_spot_and_cold_intervals(self):
        self.assertEqual(refresh_interval(tier='active', kind='spot', active=True), 3600)
        self.assertEqual(refresh_interval(tier='active', kind='perpetual', active=True), 3600)
        self.assertEqual(refresh_interval(tier='deep_cold', kind='spot', active=True), 14400)


class CandleCloseTests(unittest.TestCase):
    CLOSE = 1_790_352_000  # 2026-09-25 16:00 UTC, a 4h close

    def test_every_market_is_refreshed_once_after_a_close_btc_first(self):
        schedule = ScanSchedule()
        symbols = ['COLD/USDT', 'ETH/USDT', 'BTC/USDT']
        before = self.CLOSE - 600
        for i, s in enumerate(symbols):
            schedule.record(s, i, True, wall=before)
        tier = lambda s: 'deep_cold'
        # Before the close nothing is due (deep_cold interval is 4h).
        self.assertIsNone(schedule.next_due(symbols, 10, tier, lambda s: 'perp', False, wall=self.CLOSE - 1))
        after = self.CLOSE + SETTLE_SECONDS + 1
        order = []
        for k in range(3):
            s = schedule.next_due(symbols, 20 + k, tier, lambda s: 'perp', False, wall=after + k)
            order.append(s)
            schedule.record(s, 20 + k, True, wall=after + k)
        self.assertEqual(order[:2], ['BTC/USDT', 'ETH/USDT'])
        self.assertEqual(set(order), set(symbols))
        self.assertIsNone(schedule.next_due(symbols, 30, tier, lambda s: 'perp', False, wall=after + 60))

    def test_unavailable_markets_are_not_forced(self):
        schedule = ScanSchedule()
        schedule.record('DEAD', 0, False, wall=self.CLOSE - 60)
        self.assertIsNone(schedule.next_due(['DEAD'], 10, lambda s: 'hot', lambda s: 'perp', True, wall=self.CLOSE + 60))

    def test_last_bar_close_waits_for_settle(self):
        self.assertEqual(last_bar_close(self.CLOSE + SETTLE_SECONDS), self.CLOSE + SETTLE_SECONDS)
        self.assertEqual(last_bar_close(self.CLOSE + SETTLE_SECONDS - 1), self.CLOSE - BAR_SECONDS + SETTLE_SECONDS)


class FetchCacheCloseTests(unittest.TestCase):
    def test_entry_expires_at_candle_close_inside_its_ttl(self):
        import time as _time
        from unittest import mock
        import data_fetcher as df
        cache = df.DataCache()
        close = CandleCloseTests.CLOSE
        with mock.patch.object(df, "_ohlcv_store") as store:
            store.get.return_value = {"close": [1]}
            with mock.patch.object(_time, "time", return_value=close - 60):
                cache.put("X", "4h", {})
                self.assertIsNotNone(cache.get("X", "4h"))
            with mock.patch.object(_time, "time", return_value=close + 30):
                self.assertIsNone(cache.get("X", "4h"))
            with mock.patch.object(_time, "time", return_value=close - 60):
                cache.put("X", "1d", {})
            with mock.patch.object(_time, "time", return_value=close + 30):
                self.assertIsNotNone(cache.get("X", "1d"))   # 16:00 is not a daily close
