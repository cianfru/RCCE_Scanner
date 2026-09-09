import unittest
from scan_schedule import ScanSchedule, refresh_interval


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
        self.assertIsNone(due(299))
        self.assertEqual(due(300), 'BTC')
        self.assertIsNone(due(301, False))
        self.assertEqual(due(3600, False), 'BTC')

    def test_unavailable_backoff_and_recovery(self):
        schedule = ScanSchedule()
        schedule.record('NEW', 0, False)
        due = lambda now: schedule.next_due(['NEW'], now, lambda s: 'hot', lambda s: 'spot', True)
        self.assertIsNone(due(3599))
        self.assertEqual(due(3600), 'NEW')
        schedule.record('NEW', 3600, True)
        self.assertEqual(due(3900), 'NEW')

    def test_oldest_due_is_not_starved_and_delisting_prunes(self):
        schedule = ScanSchedule()
        schedule.record('HOT', 4000, True)
        schedule.record('COLD', 0, True)
        self.assertEqual(schedule.next_due(['HOT', 'COLD'], 5000,
                         lambda s: 'hot' if s == 'HOT' else 'cold', lambda s: 'spot', True), 'COLD')
        schedule.prune(['HOT'])
        self.assertNotIn('COLD', schedule.attempts)

    def test_spot_and_cold_intervals(self):
        self.assertEqual(refresh_interval(tier='active', kind='spot', active=True), 1800)
        self.assertEqual(refresh_interval(tier='active', kind='perpetual', active=True), 900)
        self.assertEqual(refresh_interval(tier='deep_cold', kind='spot', active=True), 14400)
