import unittest

import hl_calls


class CallCounterTests(unittest.TestCase):
    def setUp(self):
        hl_calls.reset()

    def test_per_minute_rates_by_type(self):
        t0 = hl_calls._started + 600                       # ten minutes after start
        for m in range(5):                                 # five finished minutes
            for _ in range(10):
                hl_calls.record("testStateA", now=t0 + m * 60)
            hl_calls.record("testFillsB", now=t0 + m * 60)
        hl_calls.record("testStateA", n=99, now=t0 + 5 * 60)   # the current minute is not counted yet
        st = hl_calls.stats(now=t0 + 5 * 60 + 10)
        mine = lambda d: {k: v for k, v in d.items() if k.startswith("test")}      # background callers may record too
        self.assertEqual(mine(st["per_min_5m"]), {"testStateA": 10.0, "testFillsB": 1.0})
        self.assertEqual(mine(st["total_since_start"]), {"testStateA": 149, "testFillsB": 5})
        self.assertAlmostEqual(st["per_min_60m"]["testStateA"], 50 / 15, places=2)   # 15 minutes of uptime

    def test_old_minutes_fall_out_of_the_ring(self):
        t0 = hl_calls._started + 7200
        hl_calls.record("testMetaC", now=t0)
        st = hl_calls.stats(now=t0 + 3 * 3600)
        self.assertEqual(st["per_min_60m"]["testMetaC"], 0.0)
        hl_calls.record("testMetaC", now=t0 + 3600 * 3)         # reuses the same slot, old count dropped
        self.assertEqual(hl_calls._rings["testMetaC"][int((t0 + 3600 * 3) // 60) % 60], 1)

    def test_status_exposes_the_counter(self):
        from unittest import mock
        import hl_intelligence as hl
        hl_calls.record("testStatusD")
        with mock.patch.object(hl, "_db_stats", return_value={}):
            st = hl.get_status()
        self.assertIn("api_calls", st)
        self.assertEqual(st["api_calls"]["total_since_start"]["testStatusD"], 1)


if __name__ == "__main__":
    unittest.main()
