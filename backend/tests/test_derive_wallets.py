"""The Derive drawer's feed: the shipped seed reads as one row a day, and the seed step maps the series as declared."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import derive_wallets as dw
from backtest import derive_smart_series as ds


class DeriveWalletsTests(unittest.TestCase):
    def setUp(self):
        dw._view = None

    def tearDown(self):
        dw._view = None

    def test_the_shipped_seed_is_one_row_a_day_with_counts_and_prices(self):
        v = dw.view()
        cols, rows = v["columns"], v["rows"]
        self.assertEqual(cols[:3], ["day", "btc", "eth"])
        self.assertEqual(len(cols), 3 + len(v["coins"]) * len(v["fields"]))
        self.assertTrue(all(len(r) == len(cols) for r in rows))
        days = [r[0] for r in rows]
        self.assertEqual(days, list(range(days[0], days[0] + len(days))), "no missing days")
        self.assertEqual((v["first"], v["through"]), (days[0], days[-1]))
        counts = [i for i, c in enumerate(cols) if c.endswith(("_long", "_short"))]
        self.assertTrue(all(isinstance(r[i], int) and r[i] >= 0 for r in rows for i in counts))
        self.assertTrue(all(r[1] and r[1] > 0 for r in rows[100:]), "BTC has a close on every later day")
        self.assertIn(19795, v["tops"]["BTC"], "13 March 2024, the first top of the series")
        self.assertTrue(set(v["tops"]["BTC"]) <= set(days))

    def test_without_a_seed_the_feed_is_empty(self):
        with patch.object(dw, "SEED_PATH", dw.Path(os.path.join(tempfile.mkdtemp(), "none.json"))):
            self.assertEqual(dw.view(), {})

    def test_seed_maps_the_series_columns(self):
        cols = ["day", "BTC.price", "ETH.price"] + [f"{g}.{c}.{k}" for g in ("smart", "smart_pit") for c in ds.SEED_COINS
                                                     for k in ("o_wl", "o_ws", "put_buy_open")]
        ix = {c: i for i, c in enumerate(cols)}
        row = [None] * len(cols)
        row[0], row[ix["BTC.price"]], row[ix["ETH.price"]] = "2024-03-13", 73000.5, 4000.0
        for c in ds.SEED_COINS:
            row[ix[f"smart_pit.{c}.o_wl"]], row[ix[f"smart_pit.{c}.o_ws"]] = 5, 2
            row[ix[f"smart.{c}.o_wl"]], row[ix[f"smart.{c}.o_ws"]] = 1, 7
            row[ix[f"smart_pit.{c}.put_buy_open"]], row[ix[f"smart.{c}.put_buy_open"]] = 100, 900
        doc = ds.seed({"meta": {"columns": cols, "wallets_as_of": "2024-03-14", "group_sizes_today": {"smart": 9}},
                       "rows": [row]})
        self.assertEqual(doc["rows"], [[19795, 73000.5, 4000.0] + [5, 2, 1, 7, 100, 900] * 3])
        self.assertEqual(doc["columns"][3:9], ["BTC.pit_long", "BTC.pit_short", "BTC.now_long", "BTC.now_short",
                                               "BTC.pit_puts", "BTC.now_puts"])
        self.assertEqual((doc["first"], doc["through"], doc["smart_today"]), (19795, 19795, 9))

    def test_tops_are_highs_followed_by_a_fall(self):
        up = [(d, 100 + d) for d in range(40)]                         # a climb to 139 on day 39
        down = [(40 + d, 139 - 2 * d) for d in range(60)]              # then a fall past 15%
        self.assertEqual(ds.tops(up + down), [39, 40])                 # 139 on days 39 and 40 (the fall starts after)
        self.assertEqual(ds.tops(up), [], "no fall, no top")
        shallow = up + [(40 + d, 139 - 0.3 * d) for d in range(60)]
        self.assertEqual(ds.tops(shallow), [], "a fall under 15% is not a top")


if __name__ == "__main__":
    unittest.main()
