import unittest

from public_preview import landing, preview_row, preview_rows


def row(symbol, **extra):
    base = {
        "symbol": symbol, "regime": "MARKUP", "signal": "LIGHT_LONG", "priority_score": 60.5,
        "decision_input": {"large": "payload"}, "trading_setups": [{"x": 1}] * 5,
        "positioning": {"oi_trend": "RISING", "funding_rate": 0.0001, "oi_value": 1e9},
        "conditions_detail": [{"name": "funding_ok", "label": "Funding", "group": "core", "available": False, "met": False, "desc": "long text"}],
    }
    base.update(extra)
    return base


class PublicPreviewTests(unittest.TestCase):
    def test_keeps_only_the_landing_fields(self):
        slim = preview_row(row("BTC/USDT"))
        self.assertEqual(slim["regime"], "MARKUP")
        self.assertNotIn("decision_input", slim)
        self.assertNotIn("trading_setups", slim)
        self.assertEqual(slim["positioning"], {"oi_trend": "RISING"})
        self.assertEqual(slim["conditions_detail"], [{"name": "funding_ok", "label": "Funding", "group": "core", "available": False, "met": False}])

    def test_one_row_per_coin_usdt_first_in_coin_order(self):
        rows = preview_rows([row("HYPE/USDC", regime="A"), row("DOGE/USDT"), row("HYPE/USDT", regime="B"), row("BTC/USDT"), row("ETH/BTC")])
        self.assertEqual([r["symbol"] for r in rows], ["BTC/USDT", "HYPE/USDT"])
        self.assertEqual(rows[1]["regime"], "B")
        self.assertEqual(preview_rows([row("HYPE/USDC")])[0]["symbol"], "HYPE/USDC")
        self.assertEqual(preview_rows(None), [])

    def test_endpoint_is_slim_and_keeps_its_etag(self):
        from unittest import mock
        from fastapi.testclient import TestClient
        import main
        rows = [row("BTC/USDT"), row("SOL/USDT")]
        with mock.patch.dict(main.cache.results, {"1d": rows}), mock.patch.object(main.cache, "symbols", ["BTC/USDT", "SOL/USDT"]):
            self._check_endpoint(TestClient(main.app))

    def _check_endpoint(self, c):
        first = c.get("/api/public/preview?timeframe=1d")
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual([r["symbol"] for r in body["results"]], ["BTC/USDT", "SOL/USDT"])
        self.assertNotIn("decision_input", body["results"][0])
        etag = first.headers.get("etag")
        self.assertTrue(etag)
        again = c.get("/api/public/preview?timeframe=1d", headers={"If-None-Match": etag})
        self.assertEqual(again.status_code, 304)


T = [100, 200, 300]


def coin(name, z=0.5, pl=3, ps=0, stage="running", gross=1000, t=T):
    return {"coin": name, "symbol": f"{name}/USDT", "price": 10.0, "regime": "MARKUP", "zscore": z, "priority": 50.0,
            "stage": stage, "zone": "watch", "crowd": "early", "checks": [9, 11], "sparkline": [1, 2, 3],
            "traders": {"pl": pl, "ps": ps, "ple": 9.1, "n24l": 1}, "money": {"gross_usd": gross, "long_usd": gross, "short_usd": 0},
            "entry": {"dist_pct": 4.21, "in_zone": False, "avg_long_entry": 9.6},
            "band": {"lo": 8.0, "hi": 9.0, "week_close": 9.5, "sma20": 9.0}, "trail": {"t": list(t), "z": [0.1, 0.2, 0.3], "n": [1, 2, 3]}}


class LandingPayloadTests(unittest.TestCase):
    def test_follows_hype_and_keeps_what_the_map_draws(self):
        smap = {"updated_at": 400, "box": {"z": [-0.5, 1.5], "n": [1, 8]}, "coins": [
            coin("BTC", gross=9e9), coin("HYPE"), coin("IDLE", pl=0, stage="waiting"), coin("NOZ", z=None),
            coin("OLD", t=[1, 2, 3])]}
        out = landing(smap, [row("HYPE/USDT")], {"columns": ["day", "n", "uptrend"], "days": [[d, 10, d / 100] for d in range(10)],
                                                   "today": {"day": 9, "uptrend": 0.09}, "cycle": {"type": "on", "day": 3}},
                      {"declared": "2026-09-29", "days_logged": 1, "next_report_day": 30, "verdict": "x"})
        self.assertEqual(out["focus"], "HYPE")
        self.assertEqual([c["coin"] for c in out["coins"]], ["BTC", "HYPE", "OLD"])
        self.assertEqual(out["t"], T)
        self.assertNotIn("t", out["coins"][0]["trail"])                # the shared closes, sent once
        self.assertEqual(out["coins"][2]["trail"]["t"], [1, 2, 3])
        self.assertNotIn("sparkline", out["coins"][0])
        self.assertNotIn("ple", out["coins"][0]["traders"])
        self.assertEqual(out["read"]["symbol"], "HYPE/USDT")
        self.assertNotIn("decision_input", out["read"])
        self.assertEqual(out["history"]["weekly"], [[0, 0.0], [7, 0.07], [9, 0.09]])
        self.assertNotIn("verdict", out["forward"])

    def test_without_hype_the_most_money(self):
        smap = {"coins": [coin("BTC", gross=5), coin("ETH", gross=9)]}
        self.assertEqual(landing(smap, [])["focus"], "ETH")
        self.assertIsNone(landing(None, [])["focus"])

    def test_endpoint_is_public_and_cdn_cacheable(self):
        from unittest import mock
        from fastapi.testclient import TestClient
        import main

        async def fake_map(tf):
            return {"updated_at": 400, "box": {"z": [-0.5, 1.5], "n": [1, 8]}, "coins": [coin("HYPE")]}
        main._LANDING_CACHE.clear()
        with mock.patch.object(main, "_setup_map_cached", fake_map), mock.patch.dict(main.cache.results, {"1d": []}):
            c = TestClient(main.app)
            first = c.get("/api/public/landing")
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["focus"], "HYPE")
            self.assertIn("max-age=", first.headers.get("cdn-cache-control", ""))
            self.assertEqual(c.get("/api/public/landing", headers={"If-None-Match": first.headers["etag"]}).status_code, 304)
        main._LANDING_CACHE.clear()


if __name__ == "__main__":
    unittest.main()
