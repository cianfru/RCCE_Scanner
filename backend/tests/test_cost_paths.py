import json
import tempfile
import unittest
from pathlib import Path

from opportunity_journal import OpportunityJournal


class JournalTests(unittest.TestCase):
    def test_unchanged_rows_are_not_rewritten_and_changes_are(self):
        with tempfile.TemporaryDirectory() as d:
            j = OpportunityJournal(path=Path(d) / "o.db")
            row = {"symbol": "BTC/USDT", "timeframe": "4h", "signal_bar_close_time": 100.0, "decision_version": "v1"}
            opp = {"id": "a", "status": "confirmed", "signal": "LIGHT_LONG"}
            j.record(row, opp, as_of=100.0)
            count = lambda t: j.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            snaps, states = count("snapshots"), count("states")
            self.assertFalse(j.record(row, dict(opp), as_of=160.0))       # same candle, same state
            self.assertEqual((count("snapshots"), count("states")), (snaps, states))
            j.record(dict(row, signal_bar_close_time=14500.0), dict(opp, status="blocked"), as_of=14500.0)
            self.assertEqual(count("snapshots"), snaps + 1)
            self.assertEqual(json.loads(j.db.execute("SELECT payload FROM states").fetchone()[0])["status"], "blocked")
            # A fresh journal on the same file starts from the stored state.
            j2 = OpportunityJournal(path=Path(d) / "o.db")
            self.assertEqual(j2.previous("BTC/USDT", "4h")["status"], "blocked")


class ScanResponseTests(unittest.TestCase):
    def test_cached_body_keeps_live_fields_and_shape(self):
        from fastapi.testclient import TestClient
        import main
        main.cache.results["4h"] = []
        c = TestClient(main.app)
        a = c.get("/api/scan?timeframe=4h").json()
        b = c.get("/api/scan?timeframe=4h").json()
        for body in (a, b):
            self.assertEqual(set(body) >= {"results", "scan_running", "cache_age_seconds", "consensus"}, True)
            self.assertIsInstance(body["results"], list)


if __name__ == "__main__":
    unittest.main()


class SectorTests(unittest.TestCase):
    def test_sectors_ecosystems_and_tiers(self):
        from sectors import classify, size_tier
        self.assertEqual(classify("SKR/USDT", "SKR"), ("Infrastructure", "Solana"))
        self.assertEqual(classify("WIF/USDT", "WIF"), ("Memes", "Solana"))
        self.assertEqual(classify("UBTC/USDC", "@142"), ("Majors", "Bitcoin"))
        self.assertEqual(classify("XMR1/USDC", "@9"), ("Privacy", None))
        self.assertEqual(classify("NEWCOIN/USDT", "NEWCOIN"), ("Other", None))
        self.assertEqual(size_tier({"oi_value": 5e8}), "Large")
        self.assertEqual(size_tier({"oi_value": 2e7}), "Mid")
        self.assertEqual(size_tier({"oi_value": 0, "volume_24h": 8e6}), "Small")
        self.assertIsNone(size_tier(None))
