"""Funding history for the Chart view (funding_history.py): daily sums, the seed then live closes, the update."""
import asyncio
import json
import tempfile
import unittest
from unittest import mock

import funding_history as F

DAY_MS = F.DAY_MS


def rec(day, hour, rate):
    return {"coin": "BTC", "fundingRate": str(rate), "time": day * DAY_MS + hour * 3_600_000}


class DailyTests(unittest.TestCase):
    def test_a_day_sums_its_payments_as_a_yearly_percent_and_open_days_are_left_out(self):
        recs = [rec(100, h, 0.0000125) for h in range(24)] + [rec(101, 0, 0.001), {"time": "x"}]
        self.assertEqual(F.daily(recs, before_day=101), {100: 10.95})
        self.assertEqual(F.daily(recs, before_day=102)[101], 36.5)

    def test_merged_appends_live_days_after_the_seed(self):
        out = F.merged({"rows": [[1, 5.0, 6.0], [2, 7.0, 8.0]]}, {2: [2, 0, 0], 3: [3, 9.0, 9.5]})
        self.assertEqual(out["rows"], [[1, 5.0, 6.0], [2, 7.0, 8.0], [3, 9.0, 9.5]])
        self.assertEqual(out["through"], 3)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict("os.environ", {"HYPERLENS_DB_PATH": f"{self.dir.name}/hyperlens.db"})
        self.env.start()
        F._seed, F._live, F._view = {"rows": [[100, 10.0, 11.0]]}, {}, None

    def tearDown(self):
        self.env.stop()
        self.dir.cleanup()
        F._seed, F._live, F._view = None, {}, None

    def test_update_reads_closed_days_after_the_seed_and_saves_them(self):
        calls = []

        async def fetch(coin, start_ms):
            calls.append((coin, start_ms))
            return [rec(d, h, 0.00001) for d in (101, 102, 103) for h in range(24)]
        n = asyncio.run(F.update(fetch, now_ms=103 * DAY_MS + 5))
        self.assertEqual(n, 2, "101 and 102 are closed; 103 is today")
        self.assertEqual([c[1] for c in calls], [101 * DAY_MS, 101 * DAY_MS])
        self.assertEqual(F.view()["rows"][-1][0], 102)
        saved = json.loads(open(f"{self.dir.name}/funding_live.json").read())
        self.assertEqual([r[0] for r in saved["rows"]], [101, 102])
        self.assertEqual(asyncio.run(F.update(fetch, now_ms=103 * DAY_MS + 5)), 0, "nothing new to read")

    def test_a_failed_read_adds_nothing(self):
        async def fetch(coin, start_ms):
            return []
        self.assertEqual(asyncio.run(F.update(fetch, now_ms=105 * DAY_MS)), 0)
        self.assertEqual(F.view()["rows"], [[100, 10.0, 11.0]])


if __name__ == "__main__":
    unittest.main()
