"""Last good data with its time when a feed cannot be rebuilt (degrade.py)."""

import asyncio
import unittest
from unittest import mock

import degrade


class LastGoodTests(unittest.TestCase):
    def setUp(self):
        self.lg = degrade.LastGood()

    def test_fresh_body_is_kept_and_served(self):
        body = self.lg.serve_sync("k", lambda: {"rows": [1]})
        self.assertEqual(body, {"rows": [1]})
        self.assertEqual(self.lg.get("k")[1], {"rows": [1]})

    def test_failed_build_serves_last_good_marked_stale(self):
        self.lg.remember("k", {"rows": [1]}, now=500.0)

        def boom():
            raise RuntimeError("429 from upstream")
        body = self.lg.serve_sync("k", boom)
        self.assertEqual(body["rows"], [1])
        self.assertTrue(body["stale"])
        self.assertEqual(body["as_of"], 500.0)
        self.assertEqual(self.lg.fallbacks, 1)
        # The stored copy is untouched.
        self.assertNotIn("stale", self.lg.get("k")[1])

    def test_empty_build_serves_last_good(self):
        self.lg.remember("k", {"consensus": [{"symbol": "BTC"}], "as_of": 400.0})
        body = self.lg.serve_sync("k", lambda: {"consensus": []})
        self.assertEqual(body["consensus"], [{"symbol": "BTC"}])
        self.assertTrue(body["stale"])
        self.assertEqual(body["as_of"], 400.0)

    def test_without_last_good_errors_and_empties_pass_through(self):
        with self.assertRaises(RuntimeError):
            self.lg.serve_sync("x", lambda: (_ for _ in ()).throw(RuntimeError("down")))
        self.assertEqual(self.lg.serve_sync("y", lambda: {"rows": []}), {"rows": []})

    def test_async_serve(self):
        async def ok():
            return {"coins": [1]}

        async def fail():
            raise TimeoutError()
        self.assertEqual(asyncio.run(self.lg.serve("a", ok)), {"coins": [1]})
        self.assertTrue(asyncio.run(self.lg.serve("a", fail))["stale"])

    def test_bounded(self):
        lg = degrade.LastGood(max_keys=2)
        for k in "abc":
            lg.remember(k, {"rows": [k]})
        self.assertIsNone(lg.get("a"))
        self.assertIsNotNone(lg.get("c"))


class StampTests(unittest.TestCase):
    def test_as_of_is_the_oldest_source_and_stale_any_past_limit(self):
        out = degrade.stamp({"rows": []}, (1000.0, 900), (1500.0, 1200), now=1600.0)
        self.assertEqual(out["as_of"], 1000.0)
        self.assertFalse(out["stale"])
        out = degrade.stamp({"rows": []}, (1000.0, 900), (1500.0, 1200), now=2000.0)
        self.assertTrue(out["stale"])

    def test_nothing_read_yet_is_not_stale(self):
        out = degrade.stamp({"rows": []}, (None, 900))
        self.assertIsNone(out["as_of"])
        self.assertFalse(out["stale"])

    def test_a_fallback_keeps_its_own_time(self):
        out = degrade.stamp({"rows": [1], "stale": True, "as_of": 10.0}, (5000.0, 900), now=5001.0)
        self.assertEqual(out["as_of"], 10.0)
        self.assertTrue(out["stale"])

    def test_positions_time_is_whole_minutes(self):
        import hl_intelligence as hl
        from collections import deque
        snap = hl.PositionSnapshot(timestamp=1234.5, positions=[])
        with mock.patch.object(hl, "_snapshots", {"0xa": deque([snap])}):
            self.assertEqual(degrade.positions_as_of(), 1200.0)
        with mock.patch.object(hl, "_snapshots", {}):
            self.assertIsNone(degrade.positions_as_of())


class EndpointFallbackTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import main
        self.main = main
        degrade.LAST_GOOD._d.clear()
        self.c = TestClient(main.app)

    def test_consensus_serves_last_good_when_the_rebuild_fails(self):
        import hl_intelligence as hl
        c = hl.SymbolConsensus(symbol="BTC", long_count=3, short_count=1)
        with mock.patch.object(hl, "get_all_consensus", return_value={"BTC": c}):
            first = self.c.get("/api/hyperlens/consensus").json()
        self.assertEqual(first["count"], 1)
        self.assertIn("as_of", first)
        self.assertFalse(first["stale"])
        with mock.patch.object(hl, "get_all_consensus", side_effect=RuntimeError("rate limited")):
            r = self.c.get("/api/hyperlens/consensus")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["consensus"][0]["symbol"], "BTC")
        self.assertTrue(r.json()["stale"])
        self.assertTrue(r.json()["as_of"])
        with mock.patch.object(hl, "get_all_consensus", return_value={}):
            self.assertEqual(self.c.get("/api/hyperlens/consensus").json()["count"], 1)

    def test_leaderboard_serves_last_good_page(self):
        import trader_profile as tp
        page = {"window": "30d", "cohort": "profitable", "rows": [{"address": "0x1"}], "as_of": 123.0}
        with mock.patch.object(tp, "leaderboard", return_value=page):
            self.assertEqual(self.c.get("/api/traders/leaderboard").json()["rows"], [{"address": "0x1"}])
        with mock.patch.object(tp, "leaderboard", side_effect=RuntimeError("down")):
            body = self.c.get("/api/traders/leaderboard").json()
        self.assertEqual(body["rows"], [{"address": "0x1"}])
        self.assertTrue(body["stale"])

    def test_setup_map_serves_last_good_map(self):
        good = {"tf": "1d", "coins": [{"coin": "BTC"}]}
        self.main._SETUP_MAP_CACHE.clear()
        with mock.patch.object(self.main, "_setup_map_build", return_value=good):
            first = self.c.get("/api/setup-map?tf=1d").json()
        self.assertEqual(first["coins"], [{"coin": "BTC"}])
        self.main._SETUP_MAP_CACHE.clear()
        with mock.patch.object(self.main, "_setup_map_build", side_effect=RuntimeError("down")):
            body = self.c.get("/api/setup-map?tf=1d").json()
        self.assertEqual(body["coins"], [{"coin": "BTC"}])
        self.assertTrue(body["stale"])
        self.main._SETUP_MAP_CACHE.clear()


if __name__ == "__main__":
    unittest.main()
