import json
import os
import tempfile
import time
import unittest
from unittest import mock

import hl_persistence as hp


class CompactTests(unittest.TestCase):
    def test_old_positions_pruned_equity_kept_file_shrinks(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "hl.db")
            with mock.patch.object(hp, "_DB_PATH", path), mock.patch.object(hp, "_conn", None), \
                    mock.patch.object(hp, "_PRUNE_CHUNK", 700), mock.patch.object(hp, "_VACUUM_MIN_FREE_MB", 1):
                conn = hp._get_conn()
                now = time.time()
                blob = json.dumps([{"coin": f"C{i}", "side": "LONG", "size_usd": 1000.0, "pad": "x" * 300} for i in range(10)])
                rows = [(f"0x{w}", now - h * 3600, 1000.0 + h, blob) for w in range(20) for h in range(0, 200)]
                conn.executemany("INSERT INTO snapshots (address, timestamp, account_value, positions_json) VALUES (?, ?, ?, ?)", rows)
                conn.commit()
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                before = os.path.getsize(path)
                out = hp.cleanup_old_data()
                after = os.path.getsize(path)
                self.assertEqual(out["positions_pruned"], 20 * (200 - 24))          # the last 24h (0..23h) keep positions
                self.assertTrue(out["compact"]["vacuumed"], out["compact"])
                self.assertLess(after, before / 5)
                eq = hp.load_equity_history("0x3", days=30)
                self.assertEqual(len(eq), 200)                                      # equity curve intact
                recent = conn.execute("SELECT positions_json FROM snapshots WHERE address = '0x3' ORDER BY timestamp DESC LIMIT 1").fetchone()[0]
                self.assertEqual(len(json.loads(recent)), 10)                       # recent positions kept
                self.assertFalse(hp.compact()["vacuumed"])                          # nothing left to reclaim
                conn.close()
