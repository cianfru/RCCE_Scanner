"""Market history drawer: seed + daily rows, episodes after the study's end day."""
import asyncio
import json
import unittest
from unittest.mock import patch

import market_history as mh


class MarketHistoryTests(unittest.TestCase):
    def setUp(self):
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None
        self.tmp = patch.object(mh, "_live_path", return_value="/tmp/mh_test_live.json")
        self.tmp.start()
        import os
        if os.path.exists("/tmp/mh_test_live.json"):
            os.remove("/tmp/mh_test_live.json")

    def tearDown(self):
        self.tmp.stop()
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None

    def test_aggregate_matches_seed_columns(self):
        row = mh.aggregate(100, {"BTCUSDT": ("MARKUP", 1.0, 50.0), "A": ("MARKUP", 2.0, 1.0),
                                 "B": ("REACC", 0.0, 1.0), "C": ("MARKDOWN", -1.0, 1.0)})
        self.assertEqual(row, [100, 4, 0.5, 0.0, 0.25, 0.25, 0.5, 50.0])

    def test_view_reads_the_seed(self):
        v = mh.view()
        self.assertEqual(v["columns"][:3], ["day", "n", "uptrend"])
        self.assertTrue(all(d[1] >= 40 for d in v["days"]))
        self.assertEqual(len(v["bands"]), 6)
        self.assertIn(v["today"]["band"], [b["label"] for b in v["bands"]])
        self.assertTrue(0 <= v["today"]["percentile"] <= 100)
        # Study outcomes never reach past the end day.
        for b in v["bands"]:
            for e in b["episodes"]:
                self.assertLessEqual(e[0], v["end_day"])

    def test_later_episodes_have_no_outcomes_and_merge_short_gaps(self):
        bands_def = [[0, .5, "low"], [.5, 1.01, "high"]]
        # Days 13-15 are missing (thin coverage): the run continues; a band change or a long gap ends it.
        days = [[8, 50, .6], [10, 50, .6], [11, 50, .6], [16, 50, .7], [17, 50, .4], [30, 50, .7]]
        out = mh.episodes_after(days, 9, bands_def)
        self.assertEqual(out["high"], [[10, 16, .6], [30, 30, .7]])
        self.assertEqual(out["low"], [[17, 17, .4]])

    def test_update_appends_missing_days(self):
        seed = mh._load()
        last = seed["days"][-1][0]

        async def fake_fetch(session, url):
            if "alternative" in url:
                return {"data": [{"timestamp": str((last + 1) * 86_400), "value": "61"}]}
            return [["k"]]

        rows = lambda kl, days, w, m: {d: ("MARKUP", 1.0, 100.0) for d in days}
        with patch.object(mh, "_fetch_json", fake_fetch), patch.object(mh, "day_rows", rows):
            added = asyncio.run(mh.update(now=(last + 3) * 86_400 + 100))
        self.assertEqual(added, 2)
        self.assertEqual([d[0] for d in mh.all_days()[-2:]], [last + 1, last + 2])
        self.assertEqual(mh.view()["fear_greed"][-1], [last + 1, 61])
        saved = json.load(open("/tmp/mh_test_live.json"))
        self.assertEqual(len(saved["days"]), 2)


if __name__ == "__main__":
    unittest.main()


class ForwardTestTests(unittest.TestCase):
    def setUp(self):
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None
        mh._closes.clear()

    def tearDown(self):
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None
        mh._closes.clear()

    def test_band_uses_completed_weeks(self):
        # Flat BTC at 100 for 30 weeks: both averages are 100 once 21 weeks exist.
        days = [[d, 50, 0.5, 0.0, 0.0, 0.5, 0.0, 100.0] for d in range(3, 3 + 7 * 30)]
        band = mh.btc_band(days)
        self.assertNotIn(3 + 7 * 10, band)
        lo, hi = band[3 + 7 * 25]
        self.assertAlmostEqual(lo, 100.0)
        self.assertAlmostEqual(hi, 100.0)

    def test_episodes_after_declaration_with_outcomes(self):
        d0 = mh.FT_DECLARED_DAY + 1
        days = [[d0 + i, 60, 0.50, 0.10, 0.0, 0.40, 1.0, 90.0] for i in range(61)]
        band = {d[0]: (100.0, 110.0) for d in days}
        for d in days:
            mh._closes[d[0]] = {"BTCUSDT": 90.0, **{f"C{j}USDT": 100.0 for j in range(25)}}
        mh._closes[d0 + 60] = {"BTCUSDT": 90.0, **{f"C{j}USDT": 80.0 for j in range(25)}}
        ft = mh.forward_test(days, band)
        self.assertEqual(len(ft["episodes"]), 1)
        e = ft["episodes"][0]
        self.assertEqual((e["start"], e["share"]), (d0, 0.6))      # Uptrend + Overheated
        self.assertEqual(e["h60"], {"btc": 0.0, "alt": -20.0})
        # Before the declaration nothing counts.
        old = [[mh.FT_DECLARED_DAY - 5, 60, 0.9, 0.0, 0.0, 0.1, 1.0, 90.0]]
        self.assertEqual(mh.forward_test(old, {old[0][0]: (100.0, 110.0)})["episodes"], [])
