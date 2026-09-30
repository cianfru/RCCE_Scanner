import unittest

from public_preview import preview_row, preview_rows


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


if __name__ == "__main__":
    unittest.main()
