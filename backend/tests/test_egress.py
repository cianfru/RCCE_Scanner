"""Egress: ETag / 304, price-tick batching, WebSocket audiences and the byte counter."""

import asyncio
import gzip
import json
import unittest

import egress
from price_ticker import PriceTicker, select_moves
from ws_hub import WebSocketHub


def _row(sym="BTC/USDT", price=100.0):
    return dict(symbol=sym, timeframe="4h", price=price, regime="ACCUM", confidence=50,
                signal="WAIT", zscore=0, energy=0, vol_state="NORMAL", momentum=0,
                asset_class="crypto")


class _Client:
    def __init__(self):
        from fastapi.testclient import TestClient
        import main
        self.main = main
        self.c = TestClient(main.app)


class ConditionalGetTests(unittest.TestCase):
    def setUp(self):
        self.t = _Client()
        self.main = self.t.main
        self.c = self.t.c
        self.main.cache.symbols = ["BTC/USDT", "ETH/USDT"]
        self.main.cache.results["4h"] = [_row()]
        self.main._SCAN_BODY_CACHE.clear()

    def test_scan_match_returns_empty_304(self):
        a = self.c.get("/api/scan?timeframe=4h")
        self.assertEqual(a.status_code, 200)
        etag = a.headers["etag"]
        self.assertTrue(etag.startswith('"') and etag.endswith('"'))
        self.assertEqual(a.headers["cache-control"], "no-cache")
        b = self.c.get("/api/scan?timeframe=4h", headers={"If-None-Match": etag})
        self.assertEqual(b.status_code, 304)
        self.assertEqual(b.content, b"")
        self.assertEqual(b.headers["etag"], etag)

    def test_scan_mismatch_returns_body(self):
        a = self.c.get("/api/scan?timeframe=4h")
        b = self.c.get("/api/scan?timeframe=4h", headers={"If-None-Match": '"stale"'})
        self.assertEqual(b.status_code, 200)
        self.assertEqual(b.json()["results"], a.json()["results"])
        self.assertEqual(b.headers["etag"], a.headers["etag"])

    def test_scan_new_version_changes_etag(self):
        etag = self.c.get("/api/scan?timeframe=4h").headers["etag"]
        self.main.cache.results["4h"] = [_row(price=101.0)]      # a synthesis pass replaces the list
        b = self.c.get("/api/scan?timeframe=4h", headers={"If-None-Match": etag})
        self.assertEqual(b.status_code, 200)
        self.assertNotEqual(b.headers["etag"], etag)
        self.assertEqual(b.json()["results"][0]["price"], 101.0)
        # Same content in a new list object: same ETag, so still a 304.
        self.main.cache.results["4h"] = [_row(price=101.0)]
        c = self.c.get("/api/scan?timeframe=4h", headers={"If-None-Match": b.headers["etag"]})
        self.assertEqual(c.status_code, 304)

    def test_timeframes_and_filters_have_their_own_etags(self):
        self.main.cache.results["1d"] = [_row(price=5.0)]
        e4 = self.c.get("/api/scan?timeframe=4h").headers["etag"]
        e1 = self.c.get("/api/scan?timeframe=1d").headers["etag"]
        self.assertNotEqual(e4, e1)
        self.assertEqual(self.c.get("/api/scan?timeframe=1d", headers={"If-None-Match": e4}).status_code, 200)

    def test_generic_endpoint_ignores_cache_age(self):
        self.main.cache.tradfi_results["4h"] = [{"symbol": "XYZ", "regime": "ACCUM", "signal": "WAIT"}]
        import time
        self.main.cache.last_scan_time = time.time() - 5
        a = self.c.get("/api/tradfi?timeframe=4h")
        self.assertIn("etag", a.headers)
        self.main.cache.last_scan_time = time.time() - 50       # cache age differs, data does not
        b = self.c.get("/api/tradfi?timeframe=4h", headers={"If-None-Match": a.headers["etag"]})
        self.assertEqual(b.status_code, 304)
        self.main.cache.tradfi_results["4h"] = [{"symbol": "XYZ", "regime": "MARKUP", "signal": "WAIT"}]
        c = self.c.get("/api/tradfi?timeframe=4h", headers={"If-None-Match": a.headers["etag"]})
        self.assertEqual(c.status_code, 200)

    def test_weak_and_list_if_none_match(self):
        etag = self.c.get("/api/scan?timeframe=4h").headers["etag"]
        r = self.c.get("/api/scan?timeframe=4h", headers={"If-None-Match": f'"x", W/{etag}'})
        self.assertEqual(r.status_code, 304)

    def test_gzip_still_applies_and_304_has_cors(self):
        self.main.cache.results["4h"] = [_row(sym=f"C{i}/USDT") for i in range(40)]
        self.main.cache.symbols = [f"C{i}/USDT" for i in range(40)]
        a = self.c.get("/api/scan?timeframe=4h", headers={"Accept-Encoding": "gzip", "Origin": "https://x.app"})
        self.assertEqual(a.headers.get("content-encoding"), "gzip")
        self.assertIn("etag", a.headers.get("access-control-expose-headers", "").lower())
        b = self.c.get("/api/scan?timeframe=4h", headers={"Accept-Encoding": "gzip", "Origin": "https://x.app",
                                                          "If-None-Match": a.headers["etag"]})
        self.assertEqual(b.status_code, 304)
        self.assertEqual(b.headers.get("access-control-allow-origin"), "*")

    def test_preflight_allows_if_none_match_and_is_cached_long(self):
        r = self.c.options("/api/scan", headers={"Origin": "https://x.app", "Access-Control-Request-Method": "GET",
                                                 "Access-Control-Request-Headers": "if-none-match"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("if-none-match", r.headers["access-control-allow-headers"].lower())
        self.assertEqual(r.headers["access-control-max-age"], "7200")

    def test_non_get_errors_and_admin_are_untouched(self):
        r = self.c.get("/api/net-stats")
        self.assertNotIn("etag", r.headers)
        r = self.c.get("/api/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("etag", r.headers)


class EtagHelperTests(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(egress.etag_matches('"a"', '"a"'))
        self.assertTrue(egress.etag_matches('W/"a"', '"a"'))
        self.assertTrue(egress.etag_matches('"b", "a"', '"a"'))
        self.assertTrue(egress.etag_matches("*", '"a"'))
        self.assertFalse(egress.etag_matches('"b"', '"a"'))
        self.assertFalse(egress.etag_matches(None, '"a"'))
        self.assertFalse(egress.etag_matches("", '"a"'))

    def test_etag_ignores_only_cache_age(self):
        a = egress.etag_for(b'{"results":[1],"cache_age_seconds":12.5}')
        b = egress.etag_for(b'{"results":[1],"cache_age_seconds":99}')
        c = egress.etag_for(b'{"results":[2],"cache_age_seconds":12.5}')
        d = egress.etag_for(b'{"results":[1],"cache_age_seconds":null}')
        self.assertEqual(a, b)
        self.assertEqual(a, d)
        self.assertNotEqual(a, c)


class TickBatchingTests(unittest.TestCase):
    def test_threshold(self):
        last = {"BTC/USDT": 100_000.0, "ETH/USDT": 4000.0}
        dirty = {"BTC/USDT": 100_005.0,      # 0.005%: below 0.01%, held back
                 "ETH/USDT": 4000.4,         # exactly 0.01%: sent
                 "NEW/USDT": 1.0}            # never sent: sent
        self.assertEqual(select_moves(dirty, last), {"ETH/USDT": 4000.4, "NEW/USDT": 1.0})
        self.assertEqual(select_moves({"BTC/USDT": 99_989.0}, last), {"BTC/USDT": 99_989.0})

    def test_drift_accumulates_against_last_sent(self):
        t = PriceTicker()
        t._dirty = {"BTC/USDT": 100.0}
        self.assertEqual(t.take_batch(), {"BTC/USDT": 100.0})
        for p in (100.004, 100.008):                       # each step under the threshold
            t._dirty = {"BTC/USDT": p}
            self.assertEqual(t.take_batch(), {})
        t._dirty = {"BTC/USDT": 100.011}                  # 0.011% from the last sent
        self.assertEqual(t.take_batch(), {"BTC/USDT": 100.011})
        self.assertEqual(t._dirty, {})

    def test_batch_interval_is_five_seconds(self):
        import price_ticker
        self.assertEqual(price_ticker._BATCH_INTERVAL, 5.0)

    def test_snapshot_event_has_all_prices(self):
        t = PriceTicker()
        t._prices = {"A/USDT": 1.0, "B/USDT": 2.0}
        ev = t.snapshot_event()
        self.assertEqual(ev["type"], "price-snapshot")
        self.assertEqual(ev["data"], {"A/USDT": 1.0, "B/USDT": 2.0})


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_text(self, payload):
        self.sent.append(json.loads(payload))


class HubAudienceTests(unittest.TestCase):
    def setUp(self):
        egress.reset()
        self.hub = WebSocketHub()
        self.v1, self.v2, self.hidden = _FakeWS(), _FakeWS(), _FakeWS()

        async def go():
            await self.hub.connect(self.v1, 1)
            await self.hub.connect(self.v2, 2)
            await self.hub.connect(self.hidden, 2)
        asyncio.run(go())
        self.hub.set_paused(self.hidden, True)

    def types(self, ws):
        return [m["type"] for m in ws.sent]

    def test_counts(self):
        self.assertEqual(self.hub.counts(), {"total": 3, "active": 2, "v2": 2, "legacy": 1})

    def test_scan_updated_goes_to_visible_v2_only(self):
        asyncio.run(self.hub.push_scan_updated(123.0))
        self.assertEqual(self.types(self.v2), ["scan-updated"])
        self.assertEqual(self.v2.sent[0]["data"]["timestamp"], 123.0)
        self.assertEqual(self.v1.sent, [])
        self.assertEqual(self.hidden.sent, [])

    def test_push_synthesis_no_longer_sends_full_state(self):
        asyncio.run(self.hub.push_synthesis([_row()] * 50, [_row()] * 50, {}, {}, {"timestamp": 5.0}))
        self.assertEqual(self.types(self.v2), ["scan-updated"])
        self.assertEqual(self.v1.sent, [])

    def test_symbol_update_is_legacy_only(self):
        asyncio.run(self.hub.push_symbol_update("BTC/USDT", _row(), None))
        self.assertEqual(self.types(self.v1), ["symbol-update"])
        self.assertEqual(self.v2.sent + self.hidden.sent, [])

    def test_ticks_skip_hidden_tabs_and_resume(self):
        asyncio.run(self.hub.broadcast({"type": "price-tick", "data": {"A": 1}}, audience="active"))
        self.assertEqual(self.types(self.v1), ["price-tick"])
        self.assertEqual(self.types(self.v2), ["price-tick"])
        self.assertEqual(self.hidden.sent, [])
        self.hub.set_paused(self.hidden, False)
        asyncio.run(self.hub.broadcast({"type": "price-tick", "data": {"A": 2}}, audience="active"))
        self.assertEqual(self.types(self.hidden), ["price-tick"])

    def test_alerts_still_reach_hidden_tabs(self):
        asyncio.run(self.hub.push_signal_transition([{"symbol": "BTC/USDT"}]))
        self.assertEqual(self.types(self.hidden), ["signal-transition"])

    def test_ws_bytes_are_counted(self):
        asyncio.run(self.hub.broadcast({"type": "price-tick", "data": {"A": 1}}, audience="active"))
        snap = egress.snapshot()
        row = snap["ws"]["by_type"]["price-tick"]
        self.assertEqual(row["messages"], 2)
        payload = json.dumps({"type": "price-tick", "data": {"A": 1}})
        self.assertEqual(row["raw_bytes"], 2 * len(payload))
        self.assertGreater(row["est_wire_bytes"], 0)

    def test_dead_connection_is_dropped(self):
        class Dead(_FakeWS):
            async def send_text(self, payload):
                raise RuntimeError("gone")
        dead = Dead()
        asyncio.run(self.hub.connect(dead, 2))
        asyncio.run(self.hub.broadcast({"type": "heartbeat"}))
        self.assertEqual(self.hub.client_count, 3)


class WebSocketEndpointTests(unittest.TestCase):
    def setUp(self):
        self.t = _Client()
        WebSocketHub._instance = None
        PriceTicker.get()._prices = {"BTC/USDT": 100.0}

    def test_v2_gets_price_snapshot_not_scan_state_and_can_pause(self):
        with self.t.c.websocket_connect("/ws/scan?v=2") as ws:
            first = ws.receive_json()
            self.assertEqual(first["type"], "price-snapshot")
            self.assertEqual(first["data"], {"BTC/USDT": 100.0})
            ws.send_json({"type": "pause"})
            ws.send_json({"type": "resume"})
            again = ws.receive_json()
            self.assertEqual(again["type"], "price-snapshot")
            self.assertEqual(WebSocketHub.get().counts()["v2"], 1)

    def test_v1_keeps_full_state_on_connect(self):
        with self.t.c.websocket_connect("/ws/scan") as ws:
            self.assertEqual(ws.receive_json()["type"], "synthesis-complete")


class EgressCounterTests(unittest.TestCase):
    def setUp(self):
        self.t = _Client()
        self.c = self.t.c
        self.t.main.cache.symbols = [f"C{i}/USDT" for i in range(40)]
        self.t.main.cache.results["4h"] = [_row(sym=f"C{i}/USDT") for i in range(40)]
        self.t.main._SCAN_BODY_CACHE.clear()
        egress.reset()

    def _endpoint(self, name):
        rows = self.c.get("/api/net-stats").json()["http"]["by_endpoint"]
        return next(r for r in rows if r["endpoint"] == name)

    def test_counts_bytes_after_gzip_and_304s(self):
        a = self.c.get("/api/scan?timeframe=4h", headers={"Accept-Encoding": "gzip"})
        raw = len(gzip.decompress(a.content)) if a.content[:2] == b"\x1f\x8b" else len(a.content)
        self.c.get("/api/scan?timeframe=4h", headers={"Accept-Encoding": "gzip", "If-None-Match": a.headers["etag"]})
        row = self._endpoint("/api/scan")
        self.assertEqual(row["requests"], 2)
        self.assertEqual(row["not_modified"], 1)
        wire = int(a.headers["content-length"])
        self.assertLess(wire, raw)                       # gzip applied before counting
        self.assertGreater(row["bytes"], wire)           # plus headers
        self.assertLess(row["bytes"], wire + 1500)       # the 304 is headers only

    def test_route_template_not_raw_path(self):
        self.c.get("/api/positioning/BTC-USDT")
        names = [r["endpoint"] for r in self.c.get("/api/net-stats").json()["http"]["by_endpoint"]]
        self.assertIn("/api/positioning/{symbol}", names)
        self.assertNotIn("/api/positioning/BTC-USDT", names)

    def test_snapshot_shape(self):
        snap = self.c.get("/api/net-stats").json()
        for key in ("http", "ws", "total_est_bytes_per_hour", "note", "elapsed_s"):
            self.assertIn(key, snap)
        self.assertIn("clients", snap["ws"])


if __name__ == "__main__":
    unittest.main()
