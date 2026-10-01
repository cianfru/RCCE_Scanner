import unittest

import ratelimit
from ratelimit import SlidingWindowLimiter


class RateLimitTests(unittest.TestCase):
    def test_allows_up_to_max_then_blocks(self):
        lim = SlidingWindowLimiter(max_requests=3, window_seconds=60)
        allowed = [lim.check("ip")[0] for _ in range(5)]
        self.assertEqual(allowed, [True, True, True, False, False])

    def test_retry_after_is_positive_when_blocked(self):
        lim = SlidingWindowLimiter(max_requests=1, window_seconds=60)
        self.assertTrue(lim.check("ip")[0])
        allowed, retry_after = lim.check("ip")
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_keys_are_isolated(self):
        lim = SlidingWindowLimiter(max_requests=1, window_seconds=60)
        self.assertTrue(lim.check("a")[0])
        self.assertFalse(lim.check("a")[0])
        # A different key is unaffected.
        self.assertTrue(lim.check("b")[0])

    def test_window_expiry_frees_budget(self):
        from unittest import mock
        clock = [1000.0]           # a fixed clock: the real one made this depend on the machine's speed
        with mock.patch.object(ratelimit.time, "monotonic", lambda: clock[0]):
            lim = SlidingWindowLimiter(max_requests=1, window_seconds=0.05)
            self.assertTrue(lim.check("ip")[0])
            clock[0] += 0.04
            self.assertFalse(lim.check("ip")[0])
            clock[0] += 0.02
            self.assertTrue(lim.check("ip")[0])

    def test_key_cap_is_bounded_under_unique_flood(self):
        # Regression for the unbounded-map bug: a flood of fresh identities
        # must not grow the tracked-key map past the cap.
        orig = ratelimit._MAX_KEYS
        ratelimit._MAX_KEYS = 5
        try:
            lim = SlidingWindowLimiter(max_requests=1, window_seconds=60)
            results = [lim.check(f"ip-{i}")[0] for i in range(50)]
            self.assertLessEqual(len(lim._hits), 5)
            # First 5 fresh keys admitted; the rest rejected while saturated.
            self.assertEqual(results[:5], [True] * 5)
            self.assertTrue(all(r is False for r in results[5:]))
        finally:
            ratelimit._MAX_KEYS = orig


class TokenBucketTests(unittest.TestCase):
    def test_burst_then_refill(self):
        b = ratelimit.TokenBucket(burst=3, per_minute=60)       # one a second
        self.assertEqual([b.take("ip", now=0.0)[0] for _ in range(4)], [True, True, True, False])
        ok, wait = b.take("ip", now=0.0)
        self.assertFalse(ok)
        self.assertAlmostEqual(wait, 1.0, places=3)
        self.assertTrue(b.take("ip", now=1.0)[0])
        self.assertFalse(b.take("ip", now=1.0)[0])
        # Refills to the burst, not beyond.
        self.assertEqual([b.take("ip", now=100.0)[0] for _ in range(4)], [True, True, True, False])

    def test_keys_are_separate_and_the_map_is_bounded(self):
        b = ratelimit.TokenBucket(burst=1, per_minute=1, max_keys=3)
        self.assertTrue(b.take("a", now=0)[0])
        self.assertFalse(b.take("a", now=0)[0])
        self.assertTrue(b.take("b", now=0)[0])
        self.assertTrue(b.take("c", now=0)[0])
        self.assertFalse(b.take("d", now=0)[0])        # full of active clients
        self.assertTrue(b.take("d", now=1000)[0])      # idle ones pruned
        self.assertLessEqual(len(b._b), 3)


class ClientIpTests(unittest.TestCase):
    H = {"x-forwarded-for": "1.1.1.1, 2.2.2.2", "x-real-ip": "3.3.3.3"}

    def test_modes(self):
        self.assertEqual(ratelimit.client_ip(self.H, "9.9.9.9", "xff-first"), "1.1.1.1")
        self.assertEqual(ratelimit.client_ip(self.H, "9.9.9.9", "xff-last"), "2.2.2.2")
        self.assertEqual(ratelimit.client_ip(self.H, "9.9.9.9", "real-ip"), "3.3.3.3")
        self.assertEqual(ratelimit.client_ip(self.H, "9.9.9.9", "peer"), "9.9.9.9")
        self.assertEqual(ratelimit.client_ip({}, "9.9.9.9", "xff-first"), "9.9.9.9")
        self.assertEqual(ratelimit.client_ip({}, None, "real-ip"), "unknown")

    def test_env_picks_the_mode(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"RATE_LIMIT_CLIENT_IP": "xff-last"}):
            self.assertEqual(ratelimit.client_ip(self.H, None), "2.2.2.2")


class ClassifyTests(unittest.TestCase):
    def test_classes(self):
        c = ratelimit.classify
        addr = "0x" + "a" * 40
        self.assertEqual(c("GET", f"/api/traders/{addr}", {}), "trader")
        self.assertEqual(c("GET", f"/api/traders/{addr}/fills", {}), "trader")
        self.assertEqual(c("GET", f"/api/traders/{addr}/history", {}), "trader")
        self.assertIsNone(c("GET", "/api/traders/leaderboard", {}))
        self.assertEqual(c("GET", "/api/setup-map/ladder", {"coin": "BTC"}), "exchange")
        self.assertEqual(c("GET", "/api/setup-map/mine", {}), "exchange")
        self.assertEqual(c("GET", "/api/chart/BTC/USDT", {}), "exchange")
        self.assertEqual(c("GET", "/api/trade/fills", {}), "exchange")
        self.assertEqual(c("GET", "/api/notifications/position-warnings", {"address": addr}), "exchange")
        self.assertIsNone(c("GET", "/api/notifications/market-setups", {}))
        for cheap in ("/api/scan", "/api/setup-map", "/api/hyperlens/consensus", "/api/net-stats"):
            self.assertIsNone(c("GET", cheap, {}), cheap)
        self.assertEqual(c("POST", "/api/favorites/BTC", {}), "write")
        self.assertEqual(c("DELETE", "/api/setup-map/watch/BTC", {}), "write")
        self.assertIsNone(c("POST", "/api/auth/login", {}))
        self.assertIsNone(c("POST", "/api/chat", {}))
        self.assertIsNone(c("OPTIONS", "/api/favorites/BTC", {}))

    def test_limits_from_env(self):
        lim = ratelimit.Limits({"RATE_LIMIT_TRADER": "2/60", "RATE_LIMIT_TRADER_GLOBAL": "off",
                                "RATE_LIMIT_WRITE": "off"})
        self.assertNotIn("trader", lim.everyone)
        self.assertNotIn("write", lim.per_client)
        self.assertEqual(lim.per_client["trader"].burst, 2)
        self.assertIn("exchange", lim.everyone)       # default kept

    def test_all_clients_together_are_capped(self):
        lim = ratelimit.Limits({"RATE_LIMIT_EXCHANGE": "100/100", "RATE_LIMIT_EXCHANGE_GLOBAL": "3/1"})
        results = [lim.check("exchange", f"ip{i}", now=0.0)[0] for i in range(5)]
        self.assertEqual(results, [True, True, True, False, False])


class MiddlewareTests(unittest.TestCase):
    def _app(self, limits):
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def ok(request):
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/api/traders/{a}", ok), Route("/api/scan", ok),
                                Route("/api/favorites/{s}", ok, methods=["POST"])])
        app.add_middleware(ratelimit.RateLimitMiddleware, limits=limits)
        from starlette.testclient import TestClient
        return TestClient(app)

    def test_429_with_retry_after_per_client(self):
        c = self._app(ratelimit.Limits({"RATE_LIMIT_TRADER": "2/6", "RATE_LIMIT_TRADER_GLOBAL": "off"}))
        path = "/api/traders/0x" + "b" * 40
        a = {"x-forwarded-for": "1.1.1.1"}
        self.assertEqual([c.get(path, headers=a).status_code for _ in range(3)], [200, 200, 429])
        r = c.get(path, headers=a)
        self.assertEqual(r.status_code, 429)
        self.assertGreaterEqual(int(r.headers["retry-after"]), 1)
        self.assertEqual(r.headers["access-control-allow-origin"], "*")
        # Another client is unaffected; cheap feeds are never limited.
        self.assertEqual(c.get(path, headers={"x-forwarded-for": "2.2.2.2"}).status_code, 200)
        self.assertEqual([c.get("/api/scan", headers=a).status_code for _ in range(10)], [200] * 10)
        self.assertGreaterEqual(ratelimit.LIMITED.get("trader", 0), 2)

    def test_writes_are_limited_and_switch_off(self):
        import os
        from unittest import mock
        c = self._app(ratelimit.Limits({"RATE_LIMIT_WRITE": "1/1"}))
        self.assertEqual(c.post("/api/favorites/BTC").status_code, 200)
        self.assertEqual(c.post("/api/favorites/BTC").status_code, 429)
        with mock.patch.dict(os.environ, {"RATE_LIMIT": "0"}):
            self.assertEqual(c.post("/api/favorites/BTC").status_code, 200)


if __name__ == "__main__":
    unittest.main()
