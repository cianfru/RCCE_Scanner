"""Wallet history rebuild: positions at each close from fills, membership as of each day, weighted counts."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from backtest import wallet_history_rebuild as wr

DAY = wr.DAY


class PositionsTests(unittest.TestCase):
    def test_a_position_is_the_start_of_the_next_fill_or_the_current_one(self):
        # BTC: long 2 until a fill at t=5 days (start 2, buy 1), then 3 until a sell to 0 at day 8; ETH untouched.
        data = {"BTC": [[5 * DAY + 10, 1, 2.0, 1.0, 60000.0, 0], [8 * DAY + 10, 2, 3.0, -3.0, 61000.0, 0]]}
        cur = {"ETH": -10.0}
        ends = [(d, (d + 1) * DAY) for d in range(3, 9)]
        pos = wr.positions_at(cur, data, ends)
        self.assertEqual(pos[3], {"BTC": 2.0, "ETH": -10.0})
        self.assertEqual(pos[5], {"BTC": 3.0, "ETH": -10.0})            # day 5 closes after the buy
        self.assertEqual(pos[7], {"BTC": 3.0, "ETH": -10.0})
        self.assertEqual(pos[8], {"ETH": -10.0})                         # sold to zero, no current BTC

    def test_a_fill_not_read_takes_the_nearer_of_the_two_records(self):
        # After the fill just past day 2's start the position was 1; just before the one past day 8's it was 4: a
        # fill between them was not read. Closes nearer the first read 1, closes nearer the second read 4.
        data = {"SOL": [[2 * DAY + 10, 1, 0.0, 1.0, 100.0, 0], [8 * DAY + 10, 2, 4.0, -4.0, 100.0, 0]]}
        pos = wr.positions_at({}, data, [(d, (d + 1) * DAY) for d in range(0, 9)], now_ms=20 * DAY)
        self.assertEqual([pos[d].get("SOL", 0.0) for d in range(0, 9)], [0.0, 0.0, 1.0, 1.0, 1.0, 4.0, 4.0, 4.0, 0.0])
        # No fill after the close: the current position, or the last fill's when that is nearer and they differ.
        pos = wr.positions_at({"SOL": 2.0}, {"SOL": [[2 * DAY, 1, 0.0, 1.0, 100.0, 0]]}, [(2, 3 * DAY), (15, 16 * DAY)],
                              now_ms=20 * DAY)
        self.assertEqual((pos[2]["SOL"], pos[15]["SOL"]), (1.0, 2.0))
        # A full close that leaves float noise is flat.
        noisy = {"PEPE": [[2 * DAY, 1, 727061.7999999999, -727061.8, 0.01, 0]]}
        self.assertEqual(wr.positions_at({}, noisy, [(3, 4 * DAY)], now_ms=20 * DAY)[3], {})

    def test_membership_follows_the_wallet_history(self):
        rec = {"eq": [[10 * DAY, 5_000.0], [20 * DAY, 2_000_000.0]], "pnl": [[0, 50_000.0], [20 * DAY, 150_000.0]]}
        self.assertEqual(wr.membership(rec, 2 * DAY), (False, False), "before its first point, less a week")
        self.assertEqual(wr.membership(rec, 5 * DAY), (False, False))     # $5K equity, $75K PnL
        self.assertEqual(wr.membership(rec, 12 * DAY), (True, False))     # $404K equity, $110K PnL
        self.assertEqual(wr.membership(rec, 15 * DAY), (True, True))      # $1M equity
        self.assertEqual(wr.membership({"eq": [], "pnl": []}, 20 * DAY), (False, False))

    def test_perp_filter(self):
        self.assertTrue(wr.is_perp({"coin": "BTC", "dir": "Open Long"}))
        self.assertTrue(wr.is_perp({"coin": "kPEPE", "dir": "Close Short"}))
        self.assertTrue(wr.is_perp({"coin": "FOO", "dir": "Settlement"}))
        self.assertTrue(wr.is_perp({"coin": "ETH", "dir": "Liquidated Cross Long"}))
        for f in ({"coin": "@107", "dir": "Buy"}, {"coin": "PURR/USDC", "dir": "Sell"}, {"coin": "xyz:TSLA", "dir": "Open Long"},
                  {"coin": "#18751", "dir": "Buy"}):
            self.assertFalse(wr.is_perp(f), f)


class ReadTests(unittest.TestCase):
    """read_kind: one page for a quiet wallet, the newest window for a busy one, coverage cut near the API's cap."""

    def run_read(self, total, start=100 * DAY, now=200 * DAY):
        times = [start + int(i * (now - start) / total) for i in range(total)]
        fill = lambda t: {"time": t, "tid": t, "oid": t, "coin": "BTC", "side": "B", "sz": "1", "startPosition": "0"}

        def fills_since(addr, s0, end, kind, max_pages=50):
            out = [fill(t) for t in times if s0 <= t <= end]
            return out[:2000 * max_pages]

        def info(body):
            return [fill(t) for t in times[-2000:]]
        with patch.object(wr, "START", start), patch.object(wr, "fills_since", fills_since), patch.object(wr, "info", info):
            return wr.read_kind("0xabc", "userFillsByTime", "userFills", now), times

    def test_a_quiet_wallet_is_one_page_and_complete(self):
        (got, cov, capped), times = self.run_read(1500)
        self.assertEqual((len(got), cov, capped), (1500, None, 0))

    def test_a_busy_wallet_is_read_in_full_when_the_gap_is_short(self):
        (got, cov, capped), _ = self.run_read(7000)
        self.assertEqual((len(got), cov, capped), (7000, None, 0))

    def test_near_the_api_cap_coverage_starts_at_the_first_fill_read(self):
        (got, cov, capped), times = self.run_read(9800)
        self.assertEqual((len(got), capped), (9800, 0))
        self.assertEqual(cov, times[0])

    def test_a_very_busy_wallet_keeps_its_newest_window(self):
        (got, cov, capped), times = self.run_read(40_000)
        self.assertEqual(capped, 1)
        self.assertGreater(cov, times[0])
        self.assertEqual(got[-1]["time"], times[-1])
        self.assertLessEqual(len(got), 2000 * (wr.MAX_REG_PAGES + 2))


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="whr_test_")
        self.conn = wr.db(os.path.join(self.dir, "c.db"))
        self.start = patch.object(wr, "START", 100 * DAY)
        self.start.start()

    def tearDown(self):
        self.start.stop()
        self.conn.close()

    def add(self, addr, key, av, vlm, eq, pnl, current, data=None, coverage=None):
        self.conn.execute("INSERT INTO wallets (addr, skey, lb_av, lb_pnl, lb_vlm, census, ever_smart, ever_whale, fills_done) "
                          "VALUES (?,?,?,?,?,?,1,1,?)", (addr, key, av, pnl, vlm,
                                                         json.dumps({"eq": [[0, eq]], "pnl": [[0, pnl]]}), int(current is not None)))
        if current is not None:
            self.conn.execute("INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?)",
                              (addr, json.dumps(current), json.dumps(data or {}), coverage or 100 * DAY, 0, 0, 0, 0, 0))
        self.conn.commit()

    def test_counts_are_weighted_by_the_chance_of_being_sampled(self):
        self.conn.execute("INSERT INTO candles VALUES (?, ?)", ("BTC", json.dumps([[d, 100.0] for d in range(98, 110)])))
        # Two ordinary smart wallets sampled at 10% (weight 10 each), one whale-likely at 50% (weight 2).
        self.add("a", 5, 50_000, 1e6, 50_000, 200_000, {"BTC": 1.0})
        self.add("b", 6, 50_000, 1e6, 50_000, 200_000, {"BTC": -1.0})
        self.add("w", 4000, 5e6, 1e6, 3e6, 500_000, {"BTC": 2.0})
        self.add("out", 9000, 50_000, 1e6, 50_000, 200_000, {"BTC": 1.0})       # not in the sample
        groups, counts = wr.aggregate(self.conn, 0.10, 0.50, end_ms=103 * DAY)
        self.assertEqual(counts, {"censused": 3, "read": 3})
        smart = {r[0]: r for r in groups["smart"]}
        # day, wallets, positioned, long, short, long_usd, short_usd, sampled
        self.assertEqual(smart[100], [100, 22, 22, 12, 10, 1400, 1000, 3])
        self.assertEqual([r[1] for r in groups["whales"]], [2, 2, 2])

    def test_uncovered_members_take_the_covered_shares(self):
        self.conn.execute("INSERT INTO candles VALUES (?, ?)", ("BTC", json.dumps([[d, 100.0] for d in range(98, 110)])))
        self.add("a", 1, 50_000, 1e6, 50_000, 200_000, {"BTC": 1.0})
        self.add("b", 2, 50_000, 1e6, 50_000, 200_000, {"BTC": -1.0}, coverage=102 * DAY)   # read from day 101's close on
        self.add("c", 3, 50_000, 1e6, 50_000, 200_000, None)                                # not read yet
        groups, _ = wr.aggregate(self.conn, 0.10, 0.10, end_ms=103 * DAY)
        smart = {r[0]: r for r in groups["smart"]}
        self.assertEqual(smart[100][:5], [100, 30, 30, 30, 0])      # only a read: its side, scaled to 3 wallets
        self.assertEqual(smart[101][:5], [101, 30, 30, 15, 15])
        self.assertEqual([smart[100][7], smart[101][7]], [1, 2])


if __name__ == "__main__":
    unittest.main()
