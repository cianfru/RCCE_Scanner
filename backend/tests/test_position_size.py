import unittest
import warnings

import numpy as np

from research.position_size import (DAY, W72, Size, block_boot_rho, change_series, event_stats, spearman,
                                    verdict_a, verdict_b, verdict_c)
from research.traders_turn import BAR, H, Study, positions


def fill(coin, t, sz, side, start, twap=0):
    return [coin, t, "1", str(sz), side, "", str(start), twap]


def wallet(fills, cover=0, cohort="money_printer"):
    return {"cohorts": {cohort}, "cover": cover, "pos": positions(sorted(fills, key=lambda f: -f[1]))}


def make(wallets, prices=None, n_hours=24 * 45, fng=None, panel_start=0):
    """A study over n_hours with flat prices (BTC 100, ETH 50) unless `prices` gives hourly closes."""
    prices = prices or {}
    candles = {c: [[t * H, float(prices[c][t]) if c in prices else p] for t in range(n_hours)]
               for c, p in (("BTC", 100.0), ("ETH", 50.0))}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        s = Study(wallets, candles, n_hours * H)
        return Size(s, fng or {}, panel_start=panel_start, analysis_start=panel_start)


def bar(z, t):
    return int(np.where(z.grid == t)[0][0])


class SizeRebuildTests(unittest.TestCase):
    def setUp(self):
        # buy 2 BTC at 10h, buy 1 at 16h exactly, sell 0.5 at 30h; short 1 ETH from 5h
        self.w = {"0xaaaa000000000000000000000000000000000001": wallet([
            fill("BTC", 10 * H, 2, "B", 0), fill("BTC", 16 * H, 1, "B", 2), fill("BTC", 30 * H, 0.5, "A", 3),
            fill("ETH", 5 * H, 1, "A", 0)])}
        self.z = make(self.w)
        self.m = self.z.measures("BTC", self.z.panel("money_printer"))

    def test_coins_notional_and_share(self):
        z, m = self.z, self.m
        self.assertEqual(m["long_coins"][bar(z, 12 * H)], 2.0)
        self.assertEqual(m["long_usd"][bar(z, 12 * H)], 200.0)
        # gross = 2 BTC x 100 + 1 ETH short x 50
        self.assertAlmostEqual(m["share"][bar(z, 12 * H)], 200 / 250)
        self.assertEqual(m["long_coins"][bar(z, 20 * H)], 3.0)
        self.assertEqual(m["long_coins"][bar(z, 32 * H)], 2.5)
        self.assertEqual(m["short_usd"][bar(z, 32 * H)], 0.0)

    def test_fill_at_the_close_is_not_counted(self):
        self.assertEqual(self.m["long_coins"][bar(self.z, 16 * H)], 2.0)

    def test_median_per_wallet_needs_five_long_wallets(self):
        ws = {f"0x{i:040x}": wallet([fill("BTC", 2 * H, i, "B", 0)]) for i in range(1, 6)}
        z = make(ws)
        m = z.measures("BTC", z.panel("money_printer"))
        self.assertEqual(m["median_wallet_usd"][bar(z, 4 * H)], 300.0)
        ws.pop(f"0x{5:040x}")
        z = make(ws)
        self.assertTrue(np.isnan(z.measures("BTC", z.panel("money_printer"))["median_wallet_usd"][bar(z, 4 * H)]))


class FixedCohortTests(unittest.TestCase):
    def test_wallet_entering_coverage_later_never_counts(self):
        ws = {"0x" + "1" * 40: wallet([fill("BTC", 2 * H, 1, "B", 0)]),
              # capped history: coverage starts at 200h, after the panel start; holds 5 BTC throughout
              "0x" + "2" * 40: wallet([fill("BTC", 250 * H, 1, "B", 5)], cover=200 * H)}
        z = make(ws, panel_start=0)
        m = z.measures("BTC", z.panel("money_printer"))
        self.assertTrue((m["long_coins"][z.grid > 2 * H] == 1.0).all())      # no growth at 200h or 250h
        self.assertEqual(int(z.panel("money_printer").sum()), 1)

    def test_other_group_and_largest_wallet_removal(self):
        ws = {"0x" + "1" * 40: wallet([fill("BTC", 2 * H, 1, "B", 0)]),
              "0x" + "3" * 40: wallet([fill("BTC", 2 * H, 3, "B", 0)]),
              "0x" + "4" * 40: wallet([fill("BTC", 2 * H, 9, "B", 0)], cohort="smart_money")}
        z = make(ws)
        pm = z.panel("money_printer")
        self.assertEqual(z.measures("BTC", pm)["long_coins"][-1], 4.0)
        wo, tag, top1, top3 = z.largest("BTC", pm)
        self.assertEqual(z.measures("BTC", wo)["long_coins"][-1], 1.0)
        self.assertEqual(tag, "0x3333...3333")
        self.assertAlmostEqual(top1, 75.0, places=3)
        self.assertAlmostEqual(top3, 100.0, places=3)
        self.assertEqual(int(z.without_top("BTC", pm, k=1).sum()), 1)
        self.assertEqual(z.measures("BTC", z.without_top("BTC", pm, k=1))["long_coins"][-1], 1.0)
        self.assertEqual(int(z.without_top("BTC", pm, k=3).sum()), 0)


class LookaheadTests(unittest.TestCase):
    def test_before_window_ignores_fills_after_the_event(self):
        base = [fill("BTC", 2 * H, 1, "B", 0), fill("BTC", 300 * H, 1, "B", 1)]
        later = base + [fill("BTC", 420 * H + 1, 5, "B", 2)]              # after the event bar at 420h
        za, zb = make({"0x" + "1" * 40: wallet(base)}), make({"0x" + "1" * 40: wallet(later)})
        b = bar(za, 420 * H)
        ra = za.event_rows("BTC", za.measures("BTC", za.panel("money_printer")), [b], len(za.grid) - 1)[0]
        rb = zb.event_rows("BTC", zb.measures("BTC", zb.panel("money_printer")), [b], len(zb.grid) - 1)[0]
        for w in ("before_72h", "before_7d"):
            self.assertEqual(ra[f"long_coins_{w}"], rb[f"long_coins_{w}"])
        self.assertEqual(ra["long_coins_before_7d"], 100.0)                  # 1 -> 2 coins
        self.assertNotEqual(ra["long_coins_after_72h"], rb["long_coins_after_72h"])

    def test_after_window_past_the_limit_is_undefined(self):
        z = make({"0x" + "1" * 40: wallet([fill("BTC", 2 * H, 1, "B", 0)])})
        m = z.measures("BTC", z.panel("money_printer"))
        b = 100
        r = z.event_rows("BTC", m, [b], b + W72 - 1)[0]
        self.assertTrue(np.isnan(r["long_coins_after_72h"]))
        self.assertFalse(np.isnan(r["long_coins_before_72h"]))

    def test_matched_baseline_skips_bars_within_72h(self):
        z = make({})
        n = len(z.grid)
        b = 100
        coins = np.where(np.arange(n) >= b, 2.0, 1.0)            # one jump, at the event bar
        m = {"long_coins": coins, "long_usd": coins * 100, "share": coins / 10, "median_wallet_usd": coins,
             "wallets_long": coins}
        r = z.event_rows("BTC", m, [b], n - 1)[0]
        self.assertEqual(r["long_coins_before_72h"], 100.0)
        self.assertEqual(r["long_coins_before_72h_matched"], 0.0)          # every window holding the jump is excluded
        self.assertEqual(r["long_coins_before_72h_excess"], 100.0)
        self.assertAlmostEqual(r["share_before_72h"], 10.0)                # points

    def test_fear_greed_is_used_from_the_next_day(self):
        z = make({}, fng={2: 80, 3: 20})
        self.assertTrue(np.isnan(z.fg[bar(z, 2 * DAY + 4 * H)]))
        self.assertEqual(z.fg[bar(z, 3 * DAY)], 80.0)
        self.assertEqual(z.fg[bar(z, 3 * DAY + 20 * H)], 80.0)
        self.assertEqual(z.fg[bar(z, 4 * DAY)], 20.0)


class EventTests(unittest.TestCase):
    def test_hindsight_top_needs_holders_72h_before(self):
        n = 24 * 45
        peak = 400
        px = [100 - 0.001 * t + 50 * np.exp(-((t - peak) / 30.0) ** 2) for t in range(n)]
        ws = {f"0x{i:040x}": wallet([fill("BTC", 2 * H, 1, "B", 0)]) for i in range(1, 6)}
        z = make(ws, prices={"BTC": px})
        m = z.measures("BTC", z.panel("money_printer"))
        ev = z.events("BTC", m, "top_any_z", len(z.grid) - 1)
        self.assertEqual([int(z.grid[b]) for b in ev], [peak * H])      # its close is the peak hour's neighbour
        m4 = dict(m, holders=np.minimum(m["holders"], 4))
        self.assertEqual(z.events("BTC", m4, "top_any_z", len(z.grid) - 1), [])

    def test_greed_start_is_first_known_day_at_or_above_70(self):
        ws = {f"0x{i:040x}": wallet([fill("BTC", 2 * H, 1, "B", 0)]) for i in range(1, 6)}
        z = make(ws, fng={d: v for d, v in enumerate([50] * 10 + [72, 75, 60, 71] + [50] * 16)})
        m = z.measures("BTC", z.panel("money_printer"))
        ev = z.events("BTC", m, "greed_start", len(z.grid) - 1)
        # value of day 10 is known from day 11 00:00; day 13's from day 14, 72h after the first
        self.assertEqual([int(z.grid[b] // DAY) for b in ev], [11, 14])


class StatsTests(unittest.TestCase):
    def test_spearman_with_ties(self):
        self.assertAlmostEqual(spearman([1, 2, 2, 3], [10, 20, 20, 30]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_block_bootstrap_keeps_days_together(self):
        day = np.repeat(np.arange(40), 3)
        x = np.arange(120, dtype=float)
        out = block_boot_rho(x, x, day)
        self.assertEqual((out["n"], out["days"]), (120, 40))
        self.assertAlmostEqual(out["ci90"][0], 1.0)

    def test_change_series_percent_and_points(self):
        a = np.array([0.0, 1.0, 2.0, 4.0])
        self.assertTrue(np.isnan(change_series(a, -1, 0, "pct")[1]))       # from 0: undefined
        self.assertEqual(change_series(a, -1, 0, "pct")[3], 100.0)
        self.assertAlmostEqual(change_series(np.array([0.2, 0.5]), -1, 0, "share")[1], 30.0)


class VerdictTests(unittest.TestCase):
    @staticmethod
    def st(days, med, lo, hi):
        e = {"n": days, "median": med, "ci90_median": [lo, hi]}
        return {"distinct_days": days, **{w: {"long_coins": {"excess": e}} for w in
                                         ("before_72h", "before_7d", "after_72h", "after_7d")}}

    def test_a_needs_30_days_and_interval_above_0(self):
        self.assertEqual(verdict_a(self.st(30, 1, 0.1, 2), self.st(30, 1, 0.1, 2))["size_rises_into_event"]["verdict"], "passes")
        self.assertEqual(verdict_a(self.st(29, 1, 0.1, 2), self.st(29, 1, 0.1, 2))["size_rises_into_event"]["verdict"],
                         "not informative")
        self.assertEqual(verdict_a(self.st(30, 1, 0.1, 2), self.st(30, 1, -0.1, 2))["size_rises_into_event"]["verdict"],
                         "not shown")
        self.assertEqual(verdict_a(self.st(30, -1, -2, -0.1), self.st(30, -1, -2, -0.1))["size_cut_after_event"]["verdict"],
                         "passes")

    def test_b_and_c(self):
        g = {"days": 120, "rho": 0.2, "ci90": [0.01, 0.4]}
        self.assertEqual(verdict_b(g, g)["verdict"], "relationship")
        self.assertEqual(verdict_b({**g, "days": 119}, g)["verdict"], "not informative")
        self.assertEqual(verdict_b(g, {**g, "ci90": [-0.01, 0.4]})["verdict"], "no clear relationship")
        f = {"7d": {"days": 120, "rho": -0.25, "ci90": [-0.4, -0.05]}, "14d": {"days": 120, "rho": -0.3, "ci90": [-0.5, -0.1]}}
        self.assertEqual(verdict_c(f, f)["verdict"], "signal bar met")
        f2 = {**f, "14d": {"days": 120, "rho": 0.3, "ci90": [0.1, 0.5]}}
        self.assertEqual(verdict_c(f2, f2)["verdict"], "no predictive relationship shown")

    def test_event_stats_shapes(self):
        self.assertEqual(event_stats([])["events"], 0)
        self.assertEqual(BAR, 4 * H)


if __name__ == "__main__":
    unittest.main()
