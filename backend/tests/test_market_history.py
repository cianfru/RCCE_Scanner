"""Market history drawer: seed + daily rows, episodes scored after the study's end day, the risk-on run."""
import asyncio
import json
import unittest
from unittest.mock import patch

import market_history as mh


class MarketHistoryTests(unittest.TestCase):
    def setUp(self):
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None
        mh._closes.clear()
        self.tmp = patch.object(mh, "_live_path", return_value="/tmp/mh_test_live.json")
        self.tmp.start()
        import os
        if os.path.exists("/tmp/mh_test_live.json"):
            os.remove("/tmp/mh_test_live.json")

    def tearDown(self):
        self.tmp.stop()
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None
        mh._closes.clear()

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
        # The study's episodes start by its end day; the counts say which period they cover.
        for b in v["bands"]:
            for e in b["episodes"]:
                self.assertLessEqual(e[0], v["end_day"])
            self.assertTrue(all(len(e) == 9 for e in b["episodes"] + b["later"]))
        self.assertEqual(v["base_period"], [v["days"][0][0], v["end_day"]])
        self.assertEqual(v["scored_through"], v["today"]["day"])

    def test_later_episodes_merge_short_gaps(self):
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

    def test_update_fills_closes_from_60_days_before_the_end_day(self):
        seed = mh._load()
        last = seed["days"][-1][0]
        first = seed["end_day"] - 59
        kl = [[d * mh.DAY_MS, "0", "0", "0", str(d), "0"] for d in range(first - 300, last + 1)]

        async def fetch(session, url):
            if "alternative" in url:
                return None
            return None if "BTCUSDT" in url else kl       # one pair missing: under 10% of the coins

        with patch.object(mh, "_fetch_json", fetch):
            asyncio.run(mh.update(now=(last + 1) * 86_400 + 100))
        self.assertEqual(min(mh._closes), first)
        self.assertEqual(max(mh._closes), last)
        self.assertEqual(mh._closes[first]["ETHUSDT"], float(first))
        self.assertNotIn("BTCUSDT", mh._closes[first])

        # A fetch that returns under 90% of a day's coins is not kept: the next update retries it.
        mh._closes.clear()

        async def few(session, url):
            return kl if url.endswith("ETHUSDT&interval=1d&limit=1000") else None

        with patch.object(mh, "_fetch_json", few):
            asyncio.run(mh.update(now=(last + 1) * 86_400 + 100))
        self.assertEqual(mh._closes, {})

    def test_day_closes_needs_min_bars(self):
        kl = [[d * mh.DAY_MS, "0", "0", "0", str(d), "0"] for d in range(100, 110)]
        self.assertEqual(mh.day_closes(kl, [104, 105, 120], 6), {105: 105.0})
        self.assertEqual(mh.day_closes([["k"]], [105], 1), {})


class ScoringTests(unittest.TestCase):
    """Episodes are scored once 30 or 60 days have closed, also after the study's end day."""

    def setUp(self):
        mh._closes.clear()

    def tearDown(self):
        mh._closes.clear()

    def test_scored_once_the_horizon_closes(self):
        bands_def = [[0, .5, "low"], [.5, 1.01, "high"]]
        # BTC closes at 100 + (day - 1000); every alt closes at 100 until day 1030 and at 50 after it.
        days = [[d, 50, .6 if d < 1040 or d >= 1050 else .4, 0.0, 0.0, 0.0, 0.0, 100.0 + (d - 1000)] for d in range(1000, 1101)]
        for d, *_ in days:
            mh._closes[d] = {"BTCUSDT": 1.0, **{f"C{j}": 100.0 if d <= 1030 else 50.0 for j in range(25)}}
        seed = {"end_day": 1030, "bands_def": bands_def, "bands": {
            "low": {"episodes": []},
            # The study's row: 60 days would pass its end day, so it has no 60-day outcome.
            "high": {"episodes": [[1000, 1030, .6, 9.9, 0.1, 29.9, 0.1, None, None]]}}}
        btc = {d[0]: d[7] for d in days}
        out = mh.scored_bands(seed, days, btc)
        # The episode running on the end day continues to 1039 (same band): not a new one on 1031.
        ep = out["high"]["episodes"][0]
        self.assertEqual(ep, [1000, 1039, .6, 9.9, 0.1, 29.9, 0.1, 60.0, -50.0])   # the study's outcomes stay
        self.assertEqual(out["low"]["later"], [[1040, 1049, .4, 7.1, 0.0, 21.4, 0.0, 42.9, 0.0]])
        # Started 1050: 30 days closed by 1100, 60 not yet.
        self.assertEqual(out["high"]["later"], [[1050, 1100, .6, 6.7, 0.0, 20.0, 0.0, None, None]])

    def test_too_few_alts_or_missing_closes_leave_the_alt_empty(self):
        mh._closes[1] = {f"C{j}": 1.0 for j in range(19)}
        mh._closes[31] = {f"C{j}": 2.0 for j in range(19)}
        self.assertEqual(mh._change({1: 10.0, 31: 5.0}, 1, 31), (-50.0, None))
        self.assertEqual(mh._change({1: 10.0}, 1, 31), (None, None))


class CycleTests(unittest.TestCase):
    """The drawer's risk-on line uses the risk-on cycles study's rules and reproduces its numbers."""

    def setUp(self):
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None
        self.tmp = patch.object(mh, "_live_path", return_value="/tmp/mh_test_live_none.json")
        self.tmp.start()

    def tearDown(self):
        self.tmp.stop()
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None

    def test_seed_reproduces_the_study(self):
        from backtest.risk_on_cycles import detect_runs
        seed = mh._load()
        days = [d for d in seed["days"] if d[1] >= seed["min_coins"]]
        runs = detect_runs([d[0] for d in days], {d[0]: round(d[2] + d[3], 4) for d in days})
        lengths = sorted(r["length"] for r in runs if r["type"] == "on" and not r["first"] and r["end"] is not None)
        self.assertEqual(lengths, [6, 8, 11, 19, 30, 41, 53, 96, 101, 119, 143, 148])
        c = mh.cycle(days)
        # docs/reviews/risk-on-cycles-study.md: run began 2026-08-20; 12 ended runs, median 47 days; of the 7
        # that lasted as long as today's, 5 lasted 30 more.
        self.assertEqual({k: c[k] for k in ("type", "start", "day", "past", "median", "reached", "lasted_more")},
                         {"type": "on", "start": 20685, "day": 37, "past": 12, "median": 47, "reached": 7, "lasted_more": 5})
        # With the API's two days after the seed (2026-09-27 = the study's day 38): day 39 counted from 1.
        mh._live = [[20722, 145, 0.8207, 0.0, 0.0, 0.1793, 1.554, 84433.1], [20723, 145, 0.8207, 0.0, 0.0, 0.1793, 1.525, 84472.0]]
        c = mh.view()["cycle"]
        self.assertEqual((c["day"], c["reached"], c["lasted_more"], c["below_days"]), (39, 7, 5, 0))

    def test_dip_inside_a_run_and_a_risk_off_stretch(self):
        mk = lambda xs: [[i, 50, x, 0.0, 0.0, 0.0, 0.0, 1.0] for i, x in enumerate(xs)]
        # off 5, on 10 (ended by 5 below), off 5, on 3, then 2 days below: still the same run.
        xs = [.4] * 5 + [.6] * 10 + [.4] * 5 + [.6] * 3 + [.4] * 2
        c = mh.cycle(mk(xs))
        self.assertEqual((c["type"], c["start"], c["day"], c["below_days"], c["past"], c["median"]), ("on", 20, 5, 2, 1, 10))
        self.assertEqual((c["reached"], c["lasted_more"]), (1, 0))
        c = mh.cycle(mk(xs + [.4] * 3))                  # the fifth day below ends it: risk-off since day 23
        self.assertEqual((c["type"], c["start"], c["day"], c["past"], c["median"]), ("off", 23, 5, 1, 5))
        self.assertIsNone(mh.cycle(mk([.6] * 10)))        # the first run's start is unknown


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
