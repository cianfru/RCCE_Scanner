"""Backtest routes: fixed sub-paths must not be swallowed by /api/backtest/{bt_id}."""

import unittest


class BacktestSymbolsRouteTests(unittest.TestCase):
    def test_symbols_returns_list_not_backtest_404(self):
        from fastapi.testclient import TestClient
        import main
        r = TestClient(main.app).get("/api/backtest/symbols")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json()["symbols"], list)

    def test_unknown_backtest_id_still_404s(self):
        from fastapi.testclient import TestClient
        import main
        r = TestClient(main.app).get("/api/backtest/no-such-id")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
