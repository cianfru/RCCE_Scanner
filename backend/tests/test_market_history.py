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

    def test_band_uses_sunday_closes(self):
        # BTC at 100 every day except Sundays (day % 7 == 3), which close at 200: only a Sunday band reads 200.
        days = [[d, 50, 0.5, 0.0, 0.0, 0.5, 0.0, 200.0 if d % 7 == 3 else 100.0] for d in range(0, 300)]
        band = mh.btc_band(days)
        sunday21 = 3 + 7 * 20                                        # the 21st Sunday close
        self.assertNotIn(sunday21, band)                             # its week is completed only after the close
        self.assertNotIn(sunday21 - 1, band)
        self.assertEqual(band[sunday21 + 1], (200.0, 200.0))
        self.assertEqual(band[sunday21 + 7], (200.0, 200.0))         # the next Sunday still uses the week before
        self.assertEqual(band[sunday21 + 8], (200.0, 200.0))
        from backtest.risk_on_cycles import WEDNESDAY, weekly_band
        wed = weekly_band({d[0]: d[7] for d in days}, WEDNESDAY)
        self.assertEqual(wed[sunday21 + 7], (100.0, 100.0))          # the old Wednesday filter would read 100

    def test_band_rows_expand_to_the_daily_band(self):
        from backtest.risk_on_cycles import expand_weekly
        days = [[d, 50, 0.5, 0.0, 0.0, 0.5, 0.0, 100 + (d * 37 % 23)] for d in range(18000, 18400)]
        rows = mh.btc_band_rows(days)
        self.assertTrue(all(w % 7 == 3 for w, _ in rows))            # Sundays
        self.assertEqual(expand_weekly(rows, [d[0] for d in days]), mh.btc_band(days))

    def test_ft_history_is_the_sunday_recomputation(self):
        from backtest.risk_on_cycles import RUNS_DIR
        if not (RUNS_DIR / "breadth_history.json").exists():
            self.skipTest("the local rebuild cache is not here (gitignored)")
        from backtest import breadth_history as bh
        self.assertEqual(bh.ft_history(), mh.FT_HISTORY)

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


# ---------------------------------------------------------------------------
# Past paths (docs/reviews/market-paths-method.md)
# ---------------------------------------------------------------------------

def mk(segments, first=1000, btc=None):
    """Days rows from (share, length) segments; BTC from `btc(day)` (default 100), 50 coins."""
    shares = [s for s, n in segments for _ in range(n)]
    return [[first + i, 50, x, 0.0, 0.0, 1 - x, 0.0, (btc or (lambda d: 100.0))(first + i)]
            for i, x in enumerate(shares)]


def holding(days, lo=50.0):
    return {d[0]: (lo, lo + 5) for d in days}


NO_ALT = lambda t, e: None


def runs_of(n_runs, on=0.80, on_len=20, off_len=10, tail_on=15):
    """n_runs past risk-on runs (share `on`) between risk-off stretches, then today's run of tail_on days, with 70
    days of risk-off before it so every past run's 60 days close by today."""
    seg = []
    for _ in range(n_runs):
        seg += [(0.30, off_len), (on, on_len)]
    return seg + [(0.30, 70), (on, tail_on)]


class RunStateTests(unittest.TestCase):
    def test_dip_days_stay_on_and_the_fifth_flips(self):
        days = mk([(.4, 3), (.6, 4), (.4, 4), (.6, 2), (.4, 5)])
        st = mh.run_state_at_close(days)
        self.assertEqual(st[1000], ("off", 0))
        self.assertEqual(st[1003], ("on", 1))
        self.assertEqual(st[1010], ("on", 1))                 # 4th dip day
        self.assertEqual(st[1012], ("on", 1))
        self.assertEqual(st[1016], ("on", 1))                 # 4th day below
        self.assertEqual(st[1017], ("off", 2))                # 5th day below: flips at that close
        # Point in time: a state never depends on later days.
        self.assertEqual(mh.run_state_at_close(days[:12]), {k: v for k, v in st.items() if k < 1012})


class HazenTests(unittest.TestCase):
    def test_small_arrays(self):
        self.assertEqual([mh.hazen([7.0], q) for q in (.1, .5, .9)], [7.0, 7.0, 7.0])
        self.assertEqual([mh.hazen([4.0, 2.0], q) for q in (.1, .25, .5, .75, .9)], [2.0, 2.0, 3.0, 4.0, 4.0])
        v = [5.0, 1.0, 3.0, 2.0, 4.0]
        self.assertEqual(mh.hazen(v, .1), 1.0)                # position 0: clamped
        self.assertAlmostEqual(mh.hazen(v, .25), 1.75)       # position 0.75
        self.assertEqual(mh.hazen(v, .5), 3.0)
        self.assertAlmostEqual(mh.hazen(v, .75), 4.25)
        self.assertEqual(mh.hazen(v, .9), 5.0)                # position 4: clamped


class AnalogTests(unittest.TestCase):
    def test_episodes_split_at_run_changes_and_long_gaps(self):
        # Two runs at 80%; inside the first, 60% days break the matches for 6 and then 2 days.
        seg = [(0.3, 10), (0.8, 5), (0.6, 6), (0.8, 3), (0.6, 2), (0.8, 3), (0.3, 10), (0.8, 5), (0.3, 80), (0.8, 3)]
        days = mk(seg)
        eps, rule = mh.analogs(days, holding(days), days[-1][0])
        self.assertEqual([[e[0], len(e)] for e in eps], [[1010, 5], [1021, 6], [1039, 5]])
        self.assertEqual(rule["step"], 3)                     # 2 runs: no step reaches 6

    def test_todays_run_and_open_windows_are_left_out(self):
        days = mk(runs_of(6, tail_on=15))
        T = days[-1][0]
        eps, _ = mh.analogs(days, holding(days), T)
        st = mh.run_state_at_close(days)
        self.assertTrue(all(st[d][1] != st[T][1] for e in eps for d in e))
        self.assertTrue(all(d + 60 <= T for e in eps for d in e))
        # Cut off 20 days earlier: the last past run's days no longer have 60 closed days.
        eps2, _ = mh.analogs(days, holding(days), T, cutoff=T - 50)
        self.assertLess(len(eps2), len(eps))

    def test_ladder_takes_the_first_step_with_six_runs(self):
        # Runs at 80% (x3), 88% (x2), 93% (x1) and today at 80%: step 0 (5 pts) has 3 runs, step 1 (10 pts) 5,
        # step 3 (15 pts) 6.
        seg = []
        for on in (.80, .80, .80, .88, .88, .93):
            seg += [(.3, 10), (on, 20)]
        days = mk(seg + [(.3, 70), (.80, 10)])
        _, rule = mh.analogs(days, holding(days), days[-1][0])
        self.assertEqual(rule, {"width": 0.15, "btc_side": "either", "step": 3})
        seg = []
        for on in (.80, .80, .80, .80, .80, .88):
            seg += [(.3, 10), (on, 20)]
        days = mk(seg + [(.3, 70), (.80, 10)])
        _, rule = mh.analogs(days, holding(days), days[-1][0])
        self.assertEqual(rule, {"width": 0.10, "btc_side": "holding", "step": 1})

    def test_btc_side_must_match_at_steps_0_and_1(self):
        days = mk(runs_of(8))
        T = days[-1][0]
        band = holding(days)
        first_on = [d[0] for d in days if d[2] > .5][:20]         # the first run's days
        for d in first_on:
            band[d] = (200.0, 210.0)                              # BTC 100: below the band
        for d in [d[0] for d in days if d[2] > .5][20:40]:
            del band[d]                                           # the second run: no band
        eps, rule = mh.analogs(days, band, T)
        self.assertEqual(rule["step"], 0)
        starts = {e[0] for e in eps}
        self.assertFalse(starts & set(first_on))
        self.assertEqual(len(eps), 6)


class FanTests(unittest.TestCase):
    def test_one_path_per_episode_so_a_long_episode_does_not_dominate(self):
        # Run 1 matches for 20 days and then collapses; runs 2-6 match for one day each and rise.
        seg = [(.3, 10), (.8, 20), (.1, 60)]
        for _ in range(5):
            seg += [(.3, 10), (.8, 1), (.95, 60)]
        days = mk(seg + [(.3, 70), (.8, 5)])
        f = mh.fan(days, holding(days), NO_ALT, days[-1][0])
        self.assertEqual((f["runs"], len(f["episodes"]), len(f["paths"]["uptrend"])), (6, 6, 6))
        i = mh.FAN_K.index(60)
        # Median of 6 endpoints: five at 0.95 (0.8 + 0.95 - 0.8), one at 0.1.
        self.assertAlmostEqual(f["bands"]["uptrend"][i][2], 0.95)
        self.assertAlmostEqual(min(p[i] for p in f["paths"]["uptrend"]), 0.1)

    def test_minimum_runs(self):
        for n, expect in ((2, None), (3, True), (5, True), (6, False)):
            days = mk(runs_of(n))
            f = mh.fan(days, holding(days), NO_ALT, days[-1][0])
            if expect is None:
                self.assertIsNone(f)
                continue
            self.assertEqual(f["too_few"], expect)
            self.assertEqual(f["runs"], n)
            if expect:
                self.assertEqual(f["bands"], {"uptrend": None, "btc": None, "alt": None})
                self.assertEqual(mh.fan_show({"untested": False, "series": {s: {"pass": True} for s in mh.FAN_SERIES}},
                                             True), {s: "paths" for s in mh.FAN_SERIES})
            else:
                self.assertIsNotNone(f["bands"]["uptrend"][6])

    def test_anchoring_clip_rebase_and_missing_alt(self):
        # Past runs at 60% jump to 99% afterwards; today at 60% as well but 1.0 would overflow when anchored at .62.
        seg = []
        for _ in range(6):
            seg += [(.3, 10), (.60, 1), (.99, 70)]
        days = mk(seg + [(.3, 70), (.62, 5)], btc=lambda d: 100.0 + (d - 1000))
        T = days[-1][0]
        alt = lambda t, e: None if (e - t) == 60 else -(e - t) / 10    # no alt at +60 (under 20 alts there)
        f = mh.fan(days, holding(days), alt, T)
        up = f["paths"]["uptrend"][0]
        self.assertAlmostEqual(up[0], 0.62)
        self.assertEqual(up[6], 1.0)                            # .62 + .99 - .60 clipped to 1
        t0 = f["episodes"][0][0]
        btc_T = days[-1][7]
        self.assertAlmostEqual(f["paths"]["btc"][0][6], btc_T * (100.0 + t0 + 30 - 1000) / (100.0 + t0 - 1000))
        self.assertEqual(f["paths"]["alt"][0][:2], [0.0, -0.5])
        self.assertIsNone(f["paths"]["alt"][0][12])
        self.assertIsNone(f["bands"]["alt"][12])              # dropped at that knot only
        self.assertIsNotNone(f["bands"]["alt"][6])

    def test_payload_rounding_and_ordinary(self):
        days = mk(runs_of(6), btc=lambda d: 1000.0 + d / 7)
        base = {"k": list(mh.FAN_K), "btc": [0.0] + [1.0] * 12, "alt": [0.0] + [-2.0] * 12}
        f = mh.fan_payload(mh.fan(days, holding(days), lambda t, e: (e - t) / 3, days[-1][0], base_path=base))
        self.assertTrue(all(isinstance(x, int) for p in f["paths"]["btc"] for x in p))
        self.assertEqual(f["ordinary"]["btc"][1], int(round(days[-1][7] * 1.01)))
        self.assertEqual(f["ordinary"]["alt"][1], -2.0)
        self.assertEqual(f["paths"]["alt"][0][1], 1.7)
        self.assertEqual(len(f["k"]), 13)


class AltPathTests(unittest.TestCase):
    def closes(self, n_days=200, n_alts=25):
        c = {"BTCUSDT": {str(d): 100.0 + d for d in range(n_days)}}
        for j in range(n_alts):
            c[f"C{j}USDT"] = {str(d): 10.0 + ((d * (j + 3)) % 17) + j for d in range(n_days)}
        return c

    def test_recent_days_from_closes_match_the_seed_builder(self):
        from backtest import market_paths as mp
        c = self.closes()
        built = mp.alt_paths(c, first=0, last=100)
        live = mh.make_alt_ret(None, mp.recent_closes(c, -1))           # every origin from per-day closes
        for t in range(0, 101):
            for i, k in enumerate(mh.ALT_PATHS_K):
                self.assertLessEqual(abs(built["rows"][t][i] - live(t, t + k)), 0.5)

    def test_switch_from_seed_paths_to_closes_without_a_gap(self):
        from backtest import market_paths as mp
        c = self.closes()
        built = mp.alt_paths(c, first=0, last=100)
        alt = mh.make_alt_ret(built, mp.recent_closes(c, 100))
        self.assertEqual(alt(100, 130), built["rows"][100][5])              # last seed origin
        self.assertIsNotNone(alt(101, 131))                                 # first origin from closes
        self.assertIsInstance(alt(101, 131), float)
        self.assertEqual(alt(50, 50), 0.0)
        c19 = self.closes(n_alts=19)                                        # under 20 alts: missing
        self.assertIsNone(mh.make_alt_ret(None, mp.recent_closes(c19, -1))(10, 40))
        self.assertIsNone(mp.alt_paths(c19, first=0, last=0)["rows"][0][0])

    def test_seed_paths_reproduce_the_episodes_and_the_base(self):
        seed = json.loads(mh.SEED_PATH.read_text())
        ap, bp = seed["alt_paths"], seed["base_path"]
        self.assertEqual((ap["from"], len(ap["rows"])), (18748, seed["end_day"] - 60 - 18748 + 1))
        for h in (10, 30, 60):
            i = bp["k"].index(h)
            self.assertEqual(bp["btc"][i], seed["base"][str(h)]["btc"]["median"])
            self.assertEqual(bp["alt"][i], seed["base"][str(h)]["alt"]["median"])
        n = 0
        for b in seed["bands"].values():
            for e in b["episodes"]:
                if ap["from"] <= e[0] < ap["from"] + len(ap["rows"]):
                    for h, col in ((30, 6), (60, 8)):
                        if e[col] is not None:
                            self.assertLessEqual(abs(ap["rows"][e[0] - ap["from"]][ap["k"].index(h)] - e[col]), 0.5)
                            n += 1
        self.assertGreater(n, 100)


def noisy(n=1500, seed=7):
    """A deterministic series with several risk-on runs, a wandering BTC and per-coin-free alt index."""
    import math
    x, out, btc, alt = seed, [], 100.0, 100.0
    alt_ix = {}
    for i in range(n):
        x = (x * 1103515245 + 12345) % 2 ** 31
        r = x / 2 ** 31
        share = min(0.99, max(0.01, 0.5 + 0.4 * math.sin(i / 11) + 0.2 * (r - 0.5)))
        btc *= 1 + 0.03 * (r - 0.5)
        alt *= 1 + 0.05 * (r - 0.48)
        out.append([1000 + i, 50, round(share, 4), 0.0, 0.0, 0.0, 0.0, btc])
        alt_ix[1000 + i] = alt
    return out, alt_ix


class CheckTests(unittest.TestCase):
    BANDS = [[0, .25, "a"], [.25, .40, "b"], [.40, .55, "c"], [.55, .70, "d"], [.70, .85, "e"], [.85, 1.01, "f"]]

    def run_check(self, days, ix):
        band = {d[0]: (d[7] * 0.97, d[7] * 1.02) if d[0] % 3 else (d[7] * 1.01, d[7] * 1.03) for d in days}
        alt = lambda t, e: 100 * (ix[e] / ix[t] - 1) if t in ix and e in ix else None
        return mh.fan_check(days, band, alt, days[-1][0], self.BANDS, detail=True)

    def test_no_lookahead(self):
        days, ix = noisy()
        base = self.run_check(days, ix)
        tested = [r for r in base["per_t"] if r["fan"] and r["series"]]
        self.assertGreater(len(tested), 5)
        T = tested[len(tested) // 2]["T"]
        # Change everything after T + 60: shares, BTC and the alts. T's result and every earlier one stay.
        days2 = [d if d[0] <= T + 60 else [d[0], d[1], round(1 - d[2], 4), 0, 0, 0, 0, d[7] * 3] for d in days]
        ix2 = {d: (v if d <= T + 60 else v * 0.2) for d, v in ix.items()}
        again = self.run_check(days2, ix2)
        before = [r for r in base["per_t"] if r["T"] <= T]
        self.assertEqual(before, [r for r in again["per_t"] if r["T"] <= T])
        # The fan at a test day never reaches past it.
        band = {d[0]: (d[7] * 0.97, d[7] * 1.02) for d in days}
        for r in tested:
            eps, _ = mh.analogs(days, band, r["T"], cutoff=r["T"])
            self.assertTrue(all(d + 60 <= r["T"] for e in eps for d in e))

    def test_counts_and_untested(self):
        days, ix = noisy()
        c = self.run_check(days, ix)
        self.assertEqual(set(c["series"]), set(mh.FAN_SERIES))
        for s, v in c["series"].items():
            for h in ("30", "60"):
                mid, out, n = v[h]
                self.assertLessEqual(mid, out)                 # the middle half sits inside the 10-90 band
                self.assertLessEqual(out, n)
        # The bar counts scored test days (with quantiles), not every day that had a fan.
        self.assertLessEqual(c["scored"], c["tested"])
        self.assertEqual(c["untested"], c["scored"] < 30 or c["scored_runs"] < 8)
        if c["untested"]:
            self.assertEqual(mh.fan_show(c, False), {s: "paths" for s in mh.FAN_SERIES})

    def test_wilson_pass_rule(self):
        self.assertFalse(mh.wilson_contains(19, 52, 0.50))
        self.assertTrue(mh.wilson_contains(24, 52, 0.50))
        self.assertFalse(mh.wilson_contains(31, 52, 0.80))
        self.assertTrue(mh.wilson_contains(39, 52, 0.80))

    def test_show_follows_pass(self):
        check = {"untested": False, "series": {"uptrend": {"pass": False}, "btc": {"pass": True}, "alt": {"pass": True}}}
        self.assertEqual(mh.fan_show(check, False), {"uptrend": "paths", "btc": "bands", "alt": "bands"})
        self.assertEqual(mh.fan_show({**check, "untested": True}, False), {s: "paths" for s in mh.FAN_SERIES})
        self.assertEqual(mh.fan_show(None, False), {s: "paths" for s in mh.FAN_SERIES})


class FanPayloadTests(unittest.TestCase):
    def setUp(self):
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None
        mh._closes.clear()
        self.tmp = patch.object(mh, "_live_path", return_value="/tmp/mh_test_live_fan.json")
        self.tmp.start()
        import os
        if os.path.exists("/tmp/mh_test_live_fan.json"):
            os.remove("/tmp/mh_test_live_fan.json")

    def tearDown(self):
        self.tmp.stop()
        mh._seed, mh._live, mh._fng, mh._view = None, [], {}, None
        mh._closes.clear()
        mh._fan_log.clear()

    def test_view_payload(self):
        v = mh.view()
        self.assertNotIn("btc_band", v)
        w = v["btc_band_weekly"]
        self.assertTrue(all(r[0] % 7 == 3 and r[1] <= r[2] for r in w))
        self.assertLessEqual(w[0][0], v["days"][0][0])
        self.assertLess(len(json.dumps(v, separators=(",", ":"))), 170_000)
        f = v["fan"]
        self.assertIsNotNone(f)
        self.assertLess(len(json.dumps(f, separators=(",", ":"))), 6_000)
        self.assertEqual(set(f) >= {"day", "state", "rule", "runs", "min_runs", "too_few", "k", "q", "episodes",
                                    "paths", "bands", "ordinary", "show", "check", "live_check"}, True)
        self.assertEqual(f["day"], v["today"]["day"])
        self.assertEqual(len(f["k"]), 13)
        self.assertTrue(all(len(p) == 13 for s in mh.FAN_SERIES for p in f["paths"][s]))
        self.assertEqual(len(f["episodes"]), len(f["paths"]["btc"]))
        self.assertTrue(all(len(e) == 4 and e[3] in (0, 1) for e in f["episodes"]))
        self.assertEqual(len(f["ordinary"]["btc"]), 13)
        self.assertEqual(f["ordinary"]["alt"][6], v["base"]["30"]["alt"]["median"])
        self.assertEqual(set(f["show"].values()) <= {"bands", "paths"}, True)
        self.assertEqual(f["check"], mh._load().get("fan_check"))
        self.assertIsNone(f["live_check"])
        runs = v["cycle"]["runs"]
        self.assertEqual(len(runs), v["cycle"]["past"])
        self.assertTrue(all(len(r) == 3 and 0 < r[2] <= 1 for r in runs))
        self.assertGreater(runs[0][0], v["days"][0][0])       # the first run (start unknown) is left out
        self.assertEqual(v["alt_recent"], [])                 # no per-coin closes loaded

    def test_fan_failure_does_not_take_the_view_down(self):
        with patch.object(mh, "fan_view", side_effect=ValueError("bad seed field")), \
                patch.object(mh, "alt_recent", side_effect=KeyError("x")):
            mh._view = None
            v = mh.view()
        self.assertIsNone(v["fan"])
        self.assertEqual(v["alt_recent"], [])
        self.assertIn("bands", v)
        mh._view = None

    def test_alt_recent(self):
        days = [[d, 50, .5, 0, 0, .5, 0, 1.0] for d in range(100, 250)]
        for d in range(100, 250):
            mh._closes[d] = {"BTCUSDT": 1.0, **{f"C{j}": 100.0 + (249 - d) for j in range(20)}}
        out = mh.alt_recent(days)
        self.assertEqual(out[-1], [249, 0.0])
        self.assertLessEqual(len(out), 91)
        self.assertEqual(out[0], [159, 90.0])

    def test_fan_log_once_per_new_episode_and_scored_after_the_window(self):
        seg = runs_of(6, tail_on=1)
        days = mk(seg, first=5000)
        T = days[-1][0]
        mh._seed = {"days": days[:-1], "min_coins": 40, "bands_def": CheckTests.BANDS, "end_day": 0, "pairs": []}
        mh._live = [days[-1]]
        with patch.object(mh, "FAN_LOG_FROM", T), patch.object(mh, "btc_band", lambda rows: holding(rows)):
            mh.log_fans([T])
            mh.log_fans([T])
            self.assertEqual(len(mh._fan_log), 1)
            self.assertEqual(mh._fan_log[0][0], T)
            self.assertEqual(set(mh._fan_log[0][1]), set(mh.FAN_SERIES))
            q = mh._fan_log[0][1]["uptrend"]["30"]
            self.assertEqual(len(q), 5)
            # A day inside the same drawer episode is not logged.
            mh._live.append([T + 1, 50, .8, 0, 0, .2, 0, 100.0])
            mh.log_fans([T + 1])
            self.assertEqual(len(mh._fan_log), 1)
        all_d = days + [[T + i, 50, .8, 0, 0, .2, 0, 100.0] for i in range(1, 61)]
        lc = mh.live_check(mh._fan_log, all_d[:-31], NO_ALT)          # 29 days after T: nothing closed
        self.assertEqual((lc["logged"], lc["scored"], lc["mid"]["uptrend"][1]), (1, 0, 0))
        lc = mh.live_check(mh._fan_log, all_d[:-30], NO_ALT)          # +30 closed, +60 not: still not scored
        self.assertEqual((lc["scored"], lc["out"]["uptrend"][1], lc["mid"]["uptrend"][1]), (0, 0, 0))
        lc = mh.live_check(mh._fan_log, all_d, NO_ALT)                # +60 closed: both horizons count
        self.assertEqual((lc["scored"], lc["out"]["uptrend"][1]), (1, 2))


class SparkTests(unittest.TestCase):
    """The scanner card's sparkline: last 90 days of Uptrend share, and the min-max stub of the fan's past paths."""
    def setUp(self):
        mh._seed, mh._live, mh._fng, mh._view, mh._spark = None, [], {}, None, None
        mh._closes.clear()
        self.tmp = patch.object(mh, "_live_path", return_value="/tmp/mh_test_live_spark.json")
        self.tmp.start()

    def tearDown(self):
        self.tmp.stop()
        mh._seed, mh._live, mh._fng, mh._view, mh._spark = None, [], {}, None, None
        mh._closes.clear()

    @staticmethod
    def fake_view(fan):
        days = [[d, 50, .4 + (d % 7) / 100, .1, 0, .5, 0, 1.0] for d in range(1000, 1200)]
        return {"days": days, "today": {"day": 1199}, "fan": fan}

    def test_endpoint_shape_and_size(self):
        from fastapi.testclient import TestClient
        import main
        r = TestClient(main.app).get("/api/market-history/spark")
        self.assertEqual(r.status_code, 200)
        s = r.json()
        self.assertEqual(set(s), {"days", "today", "stub"})
        self.assertLess(len(r.content), 3_000)
        v = mh.view()
        self.assertEqual(s["today"], v["today"]["day"])
        self.assertEqual(len(s["days"]), 90)
        self.assertEqual(s["days"][-1][0], s["today"])
        last = v["days"][-1]
        self.assertEqual(s["days"][-1][1], round(last[2] + last[3], 3))
        self.assertTrue(all(len(d) == 2 and 0 <= d[1] <= 1 for d in s["days"]))
        if s["stub"] is not None:
            self.assertEqual(s["stub"]["k"][0], 0)
            self.assertLessEqual(s["stub"]["k"][-1], 30)
        self.assertIs(mh.spark(), mh.spark())                # cached with the view
        mh._view = None
        self.assertIsNot(mh.spark(), s)                      # rebuilt when the view is

    def test_stub_is_the_min_max_of_past_paths_anchored_at_today(self):
        k = list(range(0, 61, 5))
        now = .52                                            # day 1199: .40 + .02 Uptrend, .10 Overheated
        paths = [[now + .01 * i * j if i < 9 else None for i in range(13)] for j in (-3, 1, 2)]
        paths.append([now] + [None] * 12)                    # a path with no later knots does not cut the stub
        v = self.fake_view({"too_few": False, "k": k, "paths": {"uptrend": paths}})
        s = mh.spark_payload(v)
        st = s["stub"]
        self.assertEqual(st["k"], [0, 5, 10, 15, 20, 25, 30])
        self.assertEqual(st["lo"][0], st["hi"][0])
        self.assertEqual(st["lo"][0], now)
        self.assertEqual(s["days"][-1], [1199, now])
        self.assertTrue(all(lo <= hi for lo, hi in zip(st["lo"], st["hi"])))
        self.assertEqual(st["lo"][6], round(now - .18, 3))
        self.assertEqual(st["hi"][6], round(now + .12, 3))
        self.assertNotIn("median", st)
        self.assertEqual(len(s["days"]), 90)
        self.assertEqual(s["days"][0][0], 1110)

    def test_no_stub_when_the_fan_is_missing_or_has_too_few_runs(self):
        self.assertIsNone(mh.spark_payload(self.fake_view(None))["stub"])
        paths = [[.44] * 13 for _ in range(4)]
        self.assertIsNone(mh.spark_payload(self.fake_view({"too_few": True, "k": list(range(0, 61, 5)),
                                                           "paths": {"uptrend": paths}}))["stub"])

    def test_stub_stops_at_the_first_knot_without_values(self):
        paths = [[.44, .5, None] + [None] * 10, [.44, .4, None] + [None] * 10]
        st = mh.spark_payload(self.fake_view({"too_few": False, "k": list(range(0, 61, 5)),
                                              "paths": {"uptrend": paths}}))["stub"]
        self.assertEqual(st, {"k": [0, 5], "lo": [.44, .4], "hi": [.44, .5]})
