"""The scan list view (scan_view.py), the sparkline feed and the full row for one coin."""

import gzip
import json
import unittest

import scan_view


def _row(sym="BTC/USDT", price=100.0, spark=None):
    return dict(
        symbol=sym, timeframe="4h", price=price, regime="ACCUM", confidence=50, signal="WAIT",
        zscore=0.5, energy=0.2, vol_state="NORMAL", momentum=0.1, asset_class="crypto",
        sparkline=spark if spark is not None else [1.0, 2.0, 3.0],
        cto={"big": "x" * 500}, cto_shadow={"big": "y" * 500}, trading_setups=[{"a": 1}],
        conditions_detail=[
            {"name": "bullish_regime", "label": "Regime", "group": "core", "available": True, "met": False,
             "desc": "Uptrend", "source": "market_candles", "observed_at": 1.0},
            {"name": "sentiment", "label": "Fear & Greed", "group": "core", "available": False, "met": False,
             "desc": "Sentiment", "source": "fear_greed", "observed_at": None},
        ],
        input_quality={"coinglass": {"status": "ready", "age_seconds": 3.2, "source": "x"},
                       "funding": {"status": "ready", "age_seconds": 1.0}},
        opportunity={"status": "confirmed", "direction": "long", "setup_type": "reversal", "reason": "z" * 200},
        positioning={"funding_rate": 1e-5, "oi_trend": "STABLE", "oi_value": 1e9, "mark_price": 100.1,
                     "source": "binance", "source_map": {"liq": "coinglass"}, "liquidation_1h_usd": 5.0},
        smart_money={"trend": "NEUTRAL", "confidence": 0.050367669876729276, "long_notional": 346298267.6764,
                     "profitable": {"long": 3, "short": 1, "long_usd": 2079.62, "short_usd": 450.46}},
        signal_age_seconds=12, signal_first_seen_at=1000.0, evaluated_at=2000.0,
    )


class ListRowTests(unittest.TestCase):
    def test_drops_unused_and_detail_fields(self):
        out = scan_view.list_row(_row())
        for k in ("cto", "cto_shadow", "trading_setups", "sparkline", "signal_age_seconds", "vol_state"):
            self.assertNotIn(k, out, k)
        for k in ("symbol", "price", "signal", "regime", "zscore", "energy", "momentum", "confidence",
                  "signal_first_seen_at", "evaluated_at"):
            self.assertEqual(out[k], _row()[k], k)

    def test_slims_nested_blocks_to_what_the_list_reads(self):
        out = scan_view.list_row(_row())
        # Only unavailable conditions, with name/label/group/available (signalContext, marketWideMissing).
        self.assertEqual(out["conditions_detail"],
                         [{"name": "sentiment", "label": "Fear & Greed", "group": "core", "available": False}])
        self.assertEqual(out["input_quality"], {"coinglass": {"status": "ready"}})
        self.assertEqual(out["opportunity"], {"status": "confirmed", "direction": "long", "setup_type": "reversal"})
        self.assertEqual(set(out["positioning"]), {"funding_rate", "oi_trend", "oi_value", "source", "source_map"})
        sm = out["smart_money"]
        self.assertEqual(sm["confidence"], 0.0504)
        self.assertEqual(sm["long_notional"], 346298268)
        self.assertEqual(sm["profitable"], {"long": 3, "short": 1, "long_usd": 2080, "short_usd": 450})

    def test_missing_and_odd_values_pass_through(self):
        out = scan_view.list_row({"symbol": "X", "conditions_detail": None, "positioning": None, "smart_money": None})
        self.assertEqual(out, {"symbol": "X", "conditions_detail": None, "positioning": None, "smart_money": None})

    def test_sparklines_by_symbol(self):
        rows = [_row("A/USDT", spark=[1.0]), _row("B/USDT", spark=[])]
        self.assertEqual(scan_view.sparklines(rows), {"A/USDT": [1.0], "B/USDT": []})

    def test_find_row(self):
        rows = [dict(_row("BTC/USDT"), market_kind="perpetual"), dict(_row("UBTC/USDC"), market_kind="spot")]
        self.assertEqual(scan_view.find_row(rows, "BTC/USDT")["symbol"], "BTC/USDT")
        self.assertEqual(scan_view.find_row(rows, "btc")["symbol"], "BTC/USDT")
        self.assertEqual(scan_view.find_row(rows, "BTCUSDT")["symbol"], "BTC/USDT")
        self.assertEqual(scan_view.find_row(rows, "UBTC", "spot")["symbol"], "UBTC/USDC")
        self.assertIsNone(scan_view.find_row(rows, "UBTC", "perpetual"))
        self.assertIsNone(scan_view.find_row(rows, ""))

    def test_list_is_much_smaller(self):
        rows = [_row(f"C{i}/USDT", price=float(i), spark=[float(i + j) for j in range(24)]) for i in range(50)]
        full = gzip.compress(json.dumps(rows).encode())
        slim = gzip.compress(json.dumps(scan_view.list_rows(rows)).encode())
        self.assertLess(len(slim), len(full) * 0.6)


class ScanEndpointTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import main
        self.main = main
        main.cache.symbols = ["BTC/USDT", "ETH/USDT"]
        main.cache.results["4h"] = [_row("BTC/USDT"), _row("ETH/USDT", price=10.0, spark=[9.0, 10.0])]
        main.cache.last_scan_time = 1_000_000.0
        main._SCAN_BODY_CACHE.clear()
        self.c = TestClient(main.app)

    def test_default_view_is_unchanged(self):
        body = self.c.get("/api/scan?timeframe=4h").json()
        self.assertIn("sparkline", body["results"][0])
        self.assertIn("cto_shadow", body["results"][0])
        self.assertEqual(body["as_of"], 1_000_000.0)
        self.assertIn("stale", body)

    def test_list_view(self):
        body = self.c.get("/api/scan?timeframe=4h&view=list").json()
        self.assertEqual([r["symbol"] for r in body["results"]], ["BTC/USDT", "ETH/USDT"])
        self.assertNotIn("sparkline", body["results"][0])
        self.assertNotIn("cto_shadow", body["results"][0])
        for k in ("scan_running", "cache_age_seconds", "consensus", "as_of", "stale"):
            self.assertIn(k, body)
        self.assertEqual(self.c.get("/api/scan?timeframe=4h&view=bogus").status_code, 422)

    def test_views_have_their_own_etags(self):
        a = self.c.get("/api/scan?timeframe=4h").headers["etag"]
        b = self.c.get("/api/scan?timeframe=4h&view=list").headers["etag"]
        self.assertNotEqual(a, b)
        r = self.c.get("/api/scan?timeframe=4h&view=list", headers={"If-None-Match": b})
        self.assertEqual(r.status_code, 304)

    def test_sparklines_etag_holds_until_a_candle_closes(self):
        r = self.c.get("/api/scan/sparklines?timeframe=4h")
        self.assertEqual(r.json()["sparklines"], {"BTC/USDT": [1.0, 2.0, 3.0], "ETH/USDT": [9.0, 10.0]})
        tag = r.headers["etag"]
        # A new pass with new prices and the same closes: same ETag, empty 304.
        self.main.cache.results["4h"] = [_row("BTC/USDT", price=101.0), _row("ETH/USDT", price=11.0, spark=[9.0, 10.0])]
        r2 = self.c.get("/api/scan/sparklines?timeframe=4h", headers={"If-None-Match": tag})
        self.assertEqual(r2.status_code, 304)
        # A closed candle changes it.
        self.main.cache.results["4h"] = [_row("BTC/USDT", spark=[2.0, 3.0, 4.0]), _row("ETH/USDT", spark=[9.0, 10.0])]
        r3 = self.c.get("/api/scan/sparklines?timeframe=4h", headers={"If-None-Match": tag})
        self.assertEqual(r3.status_code, 200)

    def test_full_row_for_one_coin(self):
        r = self.c.get("/api/scan/row?symbol=ETH&timeframe=4h")
        self.assertEqual(r.status_code, 200)
        row = r.json()["row"]
        self.assertEqual(row["symbol"], "ETH/USDT")
        self.assertEqual(len(row["conditions_detail"]), 2)
        self.assertIn("sparkline", row)
        self.assertEqual(r.json()["as_of"], 1_000_000.0)
        self.assertEqual(self.c.get("/api/scan/row?symbol=NOPE&timeframe=4h").status_code, 404)


if __name__ == "__main__":
    unittest.main()
