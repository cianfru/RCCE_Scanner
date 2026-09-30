"""Shared CDN cache for the heavy feeds (edge.py): keys, access and cache headers."""

import os
import unittest
from unittest import mock

import access
import edge


def _row(sym="BTC/USDT"):
    return dict(symbol=sym, timeframe="4h", price=100.0, regime="ACCUM", confidence=50, signal="WAIT",
                zscore=0, energy=0, vol_state="NORMAL", momentum=0, asset_class="crypto")


class KeyTests(unittest.TestCase):
    def test_open_api_uses_a_fixed_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(edge.issue()["key"], "open")
            self.assertTrue(edge.key_valid("anything"))
            self.assertFalse(edge.key_valid(""))
            self.assertFalse(edge.key_valid(None))

    def test_enforced_keys_rotate_and_the_previous_one_still_works(self):
        env = {"REFLEX_ACCESS_CODE": "c0de", "EDGE_KEY_WINDOW_S": "3600"}
        with mock.patch.dict(os.environ, env, clear=True):
            k0 = edge.issue(now=10_000)["key"]
            self.assertNotEqual(k0, "open")
            self.assertTrue(edge.key_valid(k0, now=10_000))
            self.assertTrue(edge.key_valid(k0, now=10_000 + 3600))      # next window
            self.assertFalse(edge.key_valid(k0, now=10_000 + 7200))     # two windows on
            self.assertFalse(edge.key_valid("open", now=10_000))
            self.assertFalse(edge.key_valid("x" * 32, now=10_000))
            self.assertEqual(edge.issue(now=10_000)["expires_at"], 10_800)
        with mock.patch.dict(os.environ, {"REFLEX_ACCESS_CODE": "other", "EDGE_KEY_WINDOW_S": "3600"}, clear=True):
            self.assertFalse(edge.key_valid(k0, now=10_000))              # a new secret signs everyone out

    def test_levels_get_different_keys(self):
        with mock.patch.dict(os.environ, {"REFLEX_ACCESS_CODE": "c0de"}, clear=True):
            a = edge.issue("member", now=1)["key"]
            b = edge.issue("free", now=1)["key"]
            self.assertNotEqual(a, b)
            self.assertFalse(edge.key_valid(b, "member", now=1))

    def test_edge_request_rules(self):
        with mock.patch.dict(os.environ, {"REFLEX_ACCESS_CODE": "c0de", "EDGE_CACHE": "1"}, clear=True):
            k = edge.issue()["key"]
            self.assertTrue(edge.is_edge_request("GET", "/api/scan", {}, {"k": k}))
            self.assertFalse(edge.is_edge_request("GET", "/api/scan", {}, {}))
            self.assertFalse(edge.is_edge_request("GET", "/api/scan", {"authorization": "Bearer t"}, {"k": k}))
            self.assertFalse(edge.is_edge_request("POST", "/api/scan", {}, {"k": k}))
            self.assertFalse(edge.is_edge_request("GET", "/api/traders/0xabc", {}, {"k": k}))
            self.assertFalse(edge.is_edge_request("GET", "/api/executor/status", {}, {"k": k}))
        with mock.patch.dict(os.environ, {"REFLEX_ACCESS_CODE": "c0de"}, clear=True):
            self.assertFalse(edge.is_edge_request("GET", "/api/scan", {}, {"k": edge.issue()["key"]}))


class EdgeHttpTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import main
        main.cache.symbols = ["BTC/USDT"]
        main.cache.results["4h"] = [_row()]
        main._SCAN_BODY_CACHE.clear()
        self.c = TestClient(main.app)

    def test_key_endpoint_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = self.c.get("/api/edge/key")
            self.assertEqual(r.json(), {"enabled": False})
            self.assertIn("no-store", r.headers["cache-control"])

    def test_cache_headers_only_on_keyed_credential_free_requests(self):
        with mock.patch.dict(os.environ, {"EDGE_CACHE": "1", "EDGE_TTL_S": "30"}, clear=True):
            info = self.c.get("/api/edge/key").json()
            self.assertTrue(info["enabled"])
            self.assertEqual(info["prefix"], "/edge")
            r = self.c.get(f"/api/scan?timeframe=4h&view=list&k={info['key']}")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.headers["cdn-cache-control"].startswith("max-age=30"))
            self.assertIn("stale-while-revalidate", r.headers["cdn-cache-control"])
            self.assertEqual(r.headers["cache-control"], "max-age=0, must-revalidate")
            self.assertIn("etag", r.headers)
            # The ETag still answers with an empty 304.
            r304 = self.c.get(f"/api/scan?timeframe=4h&view=list&k={info['key']}",
                              headers={"If-None-Match": r.headers["etag"]})
            self.assertEqual(r304.status_code, 304)
            # Direct requests (no key) and requests with credentials are never marked cacheable.
            self.assertNotIn("cdn-cache-control", self.c.get("/api/scan?timeframe=4h").headers)
            r2 = self.c.get(f"/api/scan?timeframe=4h&k={info['key']}", headers={"Authorization": "Bearer x"})
            self.assertNotIn("cdn-cache-control", r2.headers)
            # Other endpoints are not edge feeds.
            self.assertNotIn("cdn-cache-control", self.c.get(f"/api/status?k={info['key']}").headers)

    def test_enforced_access_needs_a_valid_key_or_token(self):
        env = {"EDGE_CACHE": "1", "REFLEX_ACCESS_CODE": "c0de"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.c.get("/api/edge/key").status_code, 401)
            token = access.issue_token()
            info = self.c.get("/api/edge/key", headers={"Authorization": f"Bearer {token}"}).json()
            self.assertEqual(self.c.get("/api/scan?timeframe=4h").status_code, 401)
            self.assertEqual(self.c.get("/api/scan?timeframe=4h&k=wrong").status_code, 401)
            ok = self.c.get(f"/api/scan?timeframe=4h&k={info['key']}")
            self.assertEqual(ok.status_code, 200)
            self.assertIn("cdn-cache-control", ok.headers)
            # The key opens only the edge feeds.
            self.assertEqual(self.c.get(f"/api/executor/status?k={info['key']}").status_code, 401)
        with mock.patch.dict(os.environ, {"REFLEX_ACCESS_CODE": "c0de"}, clear=True):
            # Switched off: keys open nothing.
            self.assertEqual(self.c.get(f"/api/scan?timeframe=4h&k={info['key']}").status_code, 401)


if __name__ == "__main__":
    unittest.main()
