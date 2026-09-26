import asyncio
import time
import unittest
from unittest import mock

import numpy as np

import hl_intelligence as hl
import sector_view
from sectors import groups


class ProfitableTraderTests(unittest.TestCase):
    def test_one_lucky_month_is_not_enough(self):
        def row(addr, roi, pnl, all_time):
            return {"ethAddress": addr, "accountValue": "200000", "windowPerformances": [
                ["month", {"pnl": str(pnl), "roi": str(roi), "vlm": "1000"}],
                ["allTime", {"pnl": str(all_time), "roi": "1", "vlm": "1000"}]]}
        rows = [row("0xproven", 0.8, 50_000, 400_000), row("0xlucky", 2.0, 60_000, 20_000)]

        class Resp:
            status = 200
            async def json(self, content_type=None): return {"leaderboardRows": rows}
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        class Session:
            def __init__(self, *a, **k): pass
            def get(self, url): return Resp()
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        with mock.patch.object(hl.aiohttp, "ClientSession", Session):
            asyncio.run(hl.refresh_leaderboard())
        self.assertEqual([w.address for w in hl._roster_money_printers], ["0xproven"])

    def test_each_wallet_counts_once_per_group(self):
        with mock.patch.object(hl, "_mp_book", {
            "a": {"WIF": 1000.0, "BOME": 500.0, "BTC": -200.0},   # long memes twice: one Memes long
            "b": {"WIF": -300.0},
            "c": {"RNDR": 100.0, "WIF": 50.0},
        }):
            lean = hl.profitable_lean(groups)
        self.assertEqual((lean["sector:Memes"]["long"], lean["sector:Memes"]["short"]), (2, 1))
        self.assertAlmostEqual(lean["sector:Memes"]["lean"], 1 / 3, places=3)
        self.assertEqual(lean["ecosystem:Solana"]["long"], 2)      # a (WIF+BOME) and c (RNDR+WIF)
        self.assertEqual(lean["pocket:AI|Solana"]["long"], 1)
        self.assertEqual(lean["sector:Majors"]["short"], 1)


class SeriesTests(unittest.TestCase):
    def test_median_index_against_btc_skips_forming_candle(self):
        day = 86_400
        base = 20_600 * day
        now = base + 20 * day + 3600
        ts = np.array([(base + i * day) * 1000 for i in range(21)], dtype=float)   # last candle still forming

        class Store:
            data = {
                "BTC/USDT": np.linspace(100, 120, 21),
                "WIF/USDT": np.linspace(1, 2, 21),
                "BOME/USDT": np.linspace(1, 1.5, 21),
                "POPCAT/USDT": np.linspace(1, 1.2, 21),
            }
            def get(self, sym, tf):
                return {"timestamp": ts, "close": self.data[sym]} if sym in self.data else None

        rows = [{"symbol": s, "sector": sec, "ecosystem": eco} for s, sec, eco in [
            ("BTC/USDT", "Majors", "Bitcoin"), ("WIF/USDT", "Memes", "Solana"),
            ("BOME/USDT", "Memes", "Solana"), ("POPCAT/USDT", "Memes", "Solana")]]
        out = sector_view.series(rows, Store(), days=30, now=now)
        self.assertEqual(len(out["dates"]), 20)                      # 21 candles, the forming one dropped
        memes = out["groups"]["sector:Memes"]
        self.assertEqual(memes["n"], 3)
        expect = 100 * Store.data["BOME/USDT"][19] / Store.data["BOME/USDT"][0]   # the median member
        self.assertAlmostEqual(memes["index"][-1], expect, delta=1.0)
        self.assertNotIn("sector:Majors", out["groups"])            # one member is not a group
        self.assertAlmostEqual(out["btc"][-1], 100 * Store.data["BTC/USDT"][19] / 100, places=2)


if __name__ == "__main__":
    unittest.main()
