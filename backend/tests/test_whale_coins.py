"""The whales-by-coin study: who is read, who is a whale on a day, positions from funding rows, the readings and the bars."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research import whale_coins as W

DAY = W.DAY
D0 = W.day_of("2025-03-03")


def lb_row(addr, av, vlm, pnl, month_vlm=0.0):
    return {"ethAddress": addr, "accountValue": str(av),
            "windowPerformances": [["month", {"pnl": "0", "roi": "0", "vlm": str(month_vlm)}], ["allTime", {"pnl": str(pnl), "roi": "0", "vlm": str(vlm)}]]}


def daily(d, coin, size, hours=24):
    return [d * DAY, coin, str(size), hours]


class WhoIsRead(unittest.TestCase):
    def test_volume_or_the_size_of_the_result_lets_a_wallet_in_not_todays_balance(self):
        rows = [lb_row("0xA", 5e6, 1e7, 1e5),                    # large today, traded little, made little: not read
                lb_row("0xB", 0, 2e8, -5e4),                     # traded $200M: read, though empty today
                lb_row("0xC", 100, 5e6, -8e5),                   # lost $800K: read
                lb_row("0xD", 100, 5e6, 8e5),                    # made $800K: read
                lb_row("0xE", 1e6, 5e9, 0, month_vlm=2e8)]       # a market maker: out
        self.assertEqual({a for a, *_ in W.candidates({"leaderboardRows": rows})}, {"0xb", "0xc", "0xd"})

    def test_the_order_is_fixed(self):
        rows = [lb_row(f"0x{i:040x}", 0, 2e8, 0) for i in range(30)]
        a = W.candidates({"leaderboardRows": rows})
        self.assertEqual(a, W.candidates({"leaderboardRows": rows[::-1]}))


class WhaleOnADay(unittest.TestCase):
    EQ = [[10 * DAY, 2e6], [20 * DAY, 5e5], [60 * DAY, 3e6]]

    def test_the_latest_point_at_or_before_the_close_decides(self):
        self.assertFalse(W.whale_on(self.EQ, 8))                 # day 8 closes at day 9's start: no point yet
        self.assertTrue(W.whale_on(self.EQ, 9))                  # the point at day 10's start is its close
        self.assertTrue(W.whale_on(self.EQ, 18))
        self.assertFalse(W.whale_on(self.EQ, 19))                # from the close that holds the $500K point

    def test_the_next_point_is_not_used(self):
        # Between $500K (day 20) and $3M (day 60) a line would cross $1M on day 28. The $3M is not known until day 60.
        self.assertFalse(any(W.whale_on(self.EQ, d) for d in range(19, 59)))
        self.assertTrue(W.whale_on(self.EQ, 59))

    def test_an_old_point_says_nothing(self):
        eq = [[10 * DAY, 2e6]]
        self.assertTrue(W.whale_on(eq, 9 + W.MAX_AGE))
        self.assertFalse(W.whale_on(eq, 10 + W.MAX_AGE))
        self.assertEqual(W.whale_days(eq, 0, 60), list(range(9, 10 + W.MAX_AGE)))
        self.assertFalse(W.whale_on([], 5))


class Positions(unittest.TestCase):
    def test_daily_rows_and_hourly_rows_give_the_days_mean_size(self):
        rows = [daily(D0, "BTC", 2.0), daily(D0, "ETH", -10.0, hours=6),
                [(D0 + 1) * DAY + 3_600_000, "BTC", "3.0", None], [(D0 + 1) * DAY + 7_200_000, "BTC", "1.0", None]]
        pos = W.day_positions(rows)
        self.assertEqual(pos[D0], {"BTC": (2.0, 24), "ETH": (-10.0, 6)})
        self.assertEqual(pos[D0 + 1], {"BTC": (2.0, 2)})

    def test_a_day_with_a_daily_row_and_hourly_rows_weighs_them_by_hours(self):
        rows = [daily(D0, "BTC", 1.0, hours=20), [D0 * DAY + 21 * 3_600_000, "BTC", "5.0", None]]
        size, hours = W.day_positions(rows)[D0]["BTC"]
        self.assertAlmostEqual(size, 25 / 21)
        self.assertEqual(hours, 21)

    def test_held_needs_half_the_day_and_drops_builder_dex_markets(self):
        pos = {"BTC": (2.0, 24), "ETH": (-1.0, W.MIN_HOURS - 1), "SOL": (0.0, 24), "xyz:GOLD": (4.0, 24), "HYPE": (-3.0, W.MIN_HOURS)}
        self.assertEqual(W.held(pos), {"BTC": 2.0, "HYPE": -3.0})
        self.assertEqual(W.held({}), {})

    def test_a_wallet_with_more_than_25_markets_is_left_out(self):
        many = {f"C{i}": (1.0, 24) for i in range(W.MAX_POSITIONS)}
        self.assertEqual(len(W.held(many)), W.MAX_POSITIONS)
        self.assertIsNone(W.held({**many, "xyz:GOLD": (1.0, 24)}))          # builder-dex markets count towards the 25


def cache(wallets, closes, listed=None):
    """A read cache: wallets {addr: (equity points, funding rows or None, cut at the cap)}; closes {coin: {day: close}}."""
    conn = W.db(Path(tempfile.mkdtemp()) / "read.db")
    for a, (eq, rows, cut) in wallets.items():
        conn.execute("INSERT INTO wallets VALUES (?,?,?,?)", (a, 0.0, 0.0, W.pack(eq)))
        if rows is not None:
            conn.execute("INSERT INTO funding VALUES (?,?,?,?,?,?)", (a, W.pack(rows), 1, cut, 0, 0))
    for coin, px in closes.items():
        conn.execute("INSERT INTO candles VALUES (?,?)", (coin, W.pack(sorted([d, c] for d, c in px.items()))))
    conn.execute("INSERT INTO meta VALUES ('addresses', ?)", (json.dumps(sorted(listed if listed is not None else wallets)),))
    conn.commit()
    return conn


WHALE = [[(D0 - 3) * DAY, 2e6], [(D0 + 9) * DAY, 2e6]]


class Table(unittest.TestCase):
    def test_whales_long_and_short_a_coin_in_wallets_and_dollars(self):
        wallets = {f"0x{i}": (WHALE, [daily(D0, "AAA", s)], 0) for i, s in enumerate([1, 2, 3, 4, -5, -6])}
        wallets["0x6"] = (WHALE, [daily(D0, "AAA", 9.0, hours=3)], 0)                    # held for 3 hours: not a holder
        wallets["0x7"] = ([[(D0 - 3) * DAY, 5e5]], [daily(D0, "AAA", 50.0)], 0)         # not a whale
        wallets["0x8"] = (WHALE, None, 0)                                               # positions not read
        wallets["0x9"] = (WHALE, [daily(D0, "AAA", 7.0)], 0)                            # not on the list read
        table, closes, counts = W.load(cache(wallets, {"AAA": {D0: 10.0}}, listed=[f"0x{i}" for i in range(9)]))
        self.assertEqual(table[D0]["AAA"], [4, 2, 100.0, 110.0])
        self.assertEqual(counts[D0], [8, 7, 0, 6])              # whales, read, over 25 markets, holding something
        self.assertEqual(closes["AAA"][D0], 10.0)

    def test_a_wallet_cut_at_the_page_cap_counts_up_to_the_day_before_its_last_row(self):
        rows = [daily(D0, "AAA", 1.0), daily(D0 + 1, "AAA", 1.0), daily(D0 + 2, "AAA", 1.0)]
        table, _, counts = W.load(cache({"0x1": (WHALE, rows, 1)}, {"AAA": {}}))
        self.assertEqual(sorted(table), [D0, D0 + 1])
        self.assertEqual(counts[D0 + 2][:2], [1, 0])

    def test_levels_and_changes(self):
        self.assertIsNone(W.level([3, 1, 0, 0]))                                         # 4 holders: no reading
        self.assertEqual(W.level([4, 1, 0, 0]), 0.6)
        self.assertEqual(W.level([4, 1, 100.0, 300.0], usd=True), -0.5)
        table = {D0: {"AAA": [4, 1, 0, 0], "BBB": [1, 1, 0, 0]}, D0 - W.HORIZON: {"AAA": [1, 4, 0, 0]}}
        self.assertEqual(W.reading(table, D0, "AAA", "level"), 0.6)
        self.assertAlmostEqual(W.reading(table, D0, "AAA", "change"), 1.2)
        self.assertIsNone(W.reading(table, D0, "BBB", "change"))
        self.assertIsNone(W.reading(table, D0 - W.HORIZON, "AAA", "change"))             # nothing a week before that

    def test_a_cross_section_needs_all_four_closes(self):
        table = {D0: {"AAA": [5, 0, 0, 0], "BBB": [0, 5, 0, 0], "CCC": [5, 5, 0, 0]}}
        closes = {"AAA": {D0 - 7: 100.0, D0: 110.0, D0 + 1: 121.0, D0 + 7: 99.0, D0 + 8: 133.1},
                  "BBB": {D0 - 7: 100.0, D0: 110.0}, "CCC": {D0: 1.0}}
        (coin, x, nxt, lst), = W.cross_section(table, closes, D0, "level")
        self.assertEqual((coin, x), ("AAA", 1.0))
        self.assertAlmostEqual(nxt, -0.1)
        self.assertAlmostEqual(lst, 0.1)
        self.assertAlmostEqual(W.cross_section(table, closes, D0, "level", lag=1)[0][2], 0.1)      # from the next day's close
        self.assertEqual(W.cross_section(table, closes, D0, "level", returns=False), [("AAA", 1.0, 0.0, 0.0)])


class Numbers(unittest.TestCase):
    def test_ranks_share_ties(self):
        self.assertEqual(list(W.ranks([3, 1, 3, 2])), [3.5, 1.0, 3.5, 2.0])

    def test_rank_correlations(self):
        self.assertAlmostEqual(W.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(W.spearman([1, 2, 3, 4], [9, 7, 5, 1]), -1.0)
        self.assertIsNone(W.spearman([1, 1, 1, 1], [1, 2, 3, 4]))
        x, y, z = [1, 2, 3, 4, 5, 6], [2, 1, 4, 3, 6, 5], [1, 2, 3, 4, 5, 6]
        self.assertIsNone(W.partial(x, y, z))                                            # x is z: nothing left to hold fixed
        z = [3, 1, 4, 6, 2, 5]
        xy, xz, yz = W.spearman(x, y), W.spearman(x, z), W.spearman(y, z)
        self.assertAlmostEqual(W.partial(x, y, z), (xy - xz * yz) / np.sqrt((1 - xz ** 2) * (1 - yz ** 2)))

    def test_the_block_interval_is_fixed_and_needs_two_blocks(self):
        v = list(np.sin(np.arange(120) / 5.0))
        self.assertEqual(W.block_interval(v, 28), W.block_interval(v, 28))
        lo, hi = W.block_interval(v, 28)
        self.assertLess(lo, np.mean(v))
        self.assertGreater(hi, np.mean(v))
        self.assertIsNone(W.block_interval(v[:55], 28))
        self.assertEqual(W.block_interval([0.25] * 60, 28), [0.25, 0.25])


def market(days, coins=18, seed=3, follow=1):
    """Made-up closes for `coins` coins, and a table whose level ranks the coins by their next week's return
    (follow=1), by its reverse (-1) or by nothing (0)."""
    rng = np.random.default_rng(seed)
    names = [f"C{i:02d}" for i in range(coins)]
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, (days + 3 * W.HORIZON, coins)), axis=0))
    first = D0 - W.HORIZON
    closes = {n: {first + t: float(px[t, i]) for t in range(len(px))} for i, n in enumerate(names)}
    table = {}
    for d in range(D0, D0 + days):
        nxt = np.array([closes[n][d + W.HORIZON] / closes[n][d] for n in names])
        order = np.argsort(np.argsort(nxt * follow if follow else rng.random(coins)))
        table[d] = {n: [2 + int(order[i]), coins + 1 - int(order[i]), 0.0, 0.0] for i, n in enumerate(names)}
    return table, closes


class Rows(unittest.TestCase):
    def test_a_reading_that_ranks_the_coins_as_their_next_week_meets_the_bar(self):
        table, closes = market(W.MIN_DAYS + 20)
        stats = W.day_stats(table, closes, D0, D0 + W.MIN_DAYS + 19, "level")
        self.assertEqual(len(stats), W.MIN_DAYS + 20)
        self.assertTrue(all(abs(s["ic"] - 1) < 1e-9 and abs(s["partial"] - 1) < 1e-9 and s["coins"] == 18 for s in stats))
        row = W.ic_row(stats)
        self.assertTrue(row["met"] and row["confirms"])
        self.assertEqual([round(x, 6) for x in row["interval"]], [1.0, 1.0])

    def test_too_few_days_or_the_wrong_way_or_nothing_do_not(self):
        table, closes = market(W.MIN_DAYS - 20)
        self.assertFalse(W.ic_row(W.day_stats(table, closes, D0, D0 + W.MIN_DAYS - 21, "level"))["met"])
        table, closes = market(W.MIN_DAYS + 20, follow=-1)
        row = W.ic_row(W.day_stats(table, closes, D0, D0 + W.MIN_DAYS + 19, "level"))
        self.assertFalse(row["met"] or row["confirms"])
        self.assertAlmostEqual(row["mean"], -1.0)
        table, closes = market(W.MIN_DAYS + 20, follow=0)
        row = W.ic_row(W.day_stats(table, closes, D0, D0 + W.MIN_DAYS + 19, "level"))
        self.assertFalse(row["met"])
        self.assertLess(abs(row["mean"]), 0.03)
        self.assertEqual(W.ic_row([]), {"days": 0, "met": False, "confirms": False})

    def test_a_day_with_under_15_coins_does_not_count(self):
        table, closes = market(30, coins=W.MIN_COINS - 1)
        self.assertEqual(W.day_stats(table, closes, D0, D0 + 29, "level"), [])

    def test_the_trade_is_the_top_third_less_the_bottom_third_less_costs(self):
        table, closes = market(7 * (W.MIN_WEEKS + 2))
        weeks = W.trade_weeks(table, closes, D0, D0 + 7 * (W.MIN_WEEKS + 2) - 1, "level")
        self.assertEqual(len(weeks), W.MIN_WEEKS + 2)
        self.assertEqual([w["day"] for w in weeks[:3]], [D0, D0 + 7, D0 + 14])
        names = sorted(table[D0])
        nxt = sorted(closes[n][D0 + 7] / closes[n][D0] - 1 for n in names)
        self.assertAlmostEqual(weeks[0]["top"], np.mean(nxt[-6:]))                       # 18 coins: 6 a side
        self.assertAlmostEqual(weeks[0]["bottom"], np.mean(nxt[:6]))
        self.assertAlmostEqual(weeks[0]["net"], weeks[0]["top"] - weeks[0]["bottom"] - W.COST)
        row = W.trade_row(weeks)
        self.assertTrue(row["met"] and row["top_over_median"] > 0 > row["bottom_over_median"])
        self.assertFalse(W.trade_row(weeks[:W.MIN_WEEKS - 1])["met"])
        table, closes = market(7 * (W.MIN_WEEKS + 2), follow=-1)
        self.assertFalse(W.trade_row(W.trade_weeks(table, closes, D0, D0 + 7 * (W.MIN_WEEKS + 2) - 1, "level"))["met"])


class ShapeAndPower(unittest.TestCase):
    def test_power_on_made_up_returns_gives_a_rate_for_each_truth(self):
        shape = {"readings": {"level": {"days": 330, "coins_median": 20.0, "same_a_week_later": 0.8},
                              "change": {"days": 40, "coins_median": 20.0, "same_a_week_later": 0.1}}}
        out = W.power(shape, reps=6, truths=(0.0, 0.2))
        self.assertIsNone(out["change"])                                                 # under two blocks of days
        self.assertEqual(set(out["level"]["ic_row"]), {"0.0", "0.2"})
        self.assertEqual(out["level"]["ic_row"]["0.2"], 1.0)                             # a relation that strong always shows
        self.assertLessEqual(out["level"]["ic_row"]["0.0"], 0.5)

    def test_the_shape_step_counts_without_reading_a_return(self):
        whales = {f"0x{i}": ([[(D0 - 12) * DAY, 2e6], [(D0 + 3) * DAY, 2e6], [(D0 + 20) * DAY, 2e6], [(D0 + 40) * DAY, 2e6]],
                             [daily(d, f"C{c:02d}", 1.0 if i < c % 7 else -1.0) for d in range(D0 - 8, D0 + 30) for c in range(16)], 0)     # the level differs by coin and stays
                  for i in range(6)}
        closes = {f"C{c:02d}": {d: 1.0 + c for d in range(D0 - 20, D0 + 45)} for c in range(16)}
        conn = cache(whales, closes)
        real = W.cross_section
        seen = []
        W.cross_section = lambda *a, **k: seen.append(k.get("returns", True)) or real(*a, **k)
        try:
            out = W.shape(conn, W.iso(D0), W.iso(D0 + 20))
        finally:
            W.cross_section = real
        self.assertTrue(seen and not any(seen))
        self.assertEqual(out["readings"]["level"]["days"], 21)
        self.assertEqual(out["readings"]["level"]["weeks"], 3)
        self.assertEqual(out["readings"]["level"]["coins_median"], 16.0)
        self.assertEqual(out["whales_a_day"]["median"], 6.0)
        self.assertEqual(out["positions_read_share"], 1.0)
        self.assertAlmostEqual(out["readings"]["level"]["same_a_week_later"], 1.0)


if __name__ == "__main__":
    unittest.main()
