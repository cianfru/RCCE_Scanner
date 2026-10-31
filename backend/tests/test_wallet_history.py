"""Wallet positioning history: live rows from the cohort sweep's snapshots, merged after the rebuilt seed; the
profitable traders' share of positions long from HyperLens's record, after Outrider's rebuilt days."""
import asyncio
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import wallet_history as ph

DAY = ph.DAY_S


def snap(ts, cohort, wallets, long, short, positioned=None, long_usd=0.0, short_usd=0.0):
    return (ts, cohort, {"wallets": wallets, "positioned": positioned if positioned is not None else long + short,
                         "long_wallets": long, "short_wallets": short, "long_usd": long_usd, "short_usd": short_usd})


class PositioningHistoryTests(unittest.TestCase):
    def setUp(self):
        ph._seed, ph._crowd_seed, ph._live, ph._checked, ph._view = None, None, {}, None, None
        self.dir = tempfile.mkdtemp(prefix="wh_test_")
        self.live = patch.object(ph, "_live_path", return_value=os.path.join(self.dir, "wallet_history_live.json"))
        self.live.start()
        self.seed_path = os.path.join(self.dir, "seed.json")
        self.seed = patch.object(ph, "SEED_PATH", ph.Path(self.seed_path))
        self.seed.start()
        self.crowd_path = os.path.join(self.dir, "crowd.json")
        self.crowd = patch.object(ph, "CROWD_SEED_PATH", ph.Path(self.crowd_path))
        self.crowd.start()

    def tearDown(self):
        self.live.stop()
        self.seed.stop()
        self.crowd.stop()
        shutil.rmtree(self.dir, ignore_errors=True)
        ph._seed, ph._crowd_seed, ph._live, ph._checked, ph._view = None, None, {}, None, None

    def write_seed(self, rows_by_group, start, end):
        with open(self.seed_path, "w") as fh:
            json.dump({"version": 1, "built": "2026-10-28", "start_day": start, "end_day": end, "columns": ph.COLUMNS,
                       "sample": {"share": 0.1}, "groups": rows_by_group}, fh)

    def test_day_row_takes_the_snapshot_nearest_the_close_and_sums_its_cohorts(self):
        close = 101 * DAY
        snaps = [snap(close - 1800, "Smart Money", 90, 40, 20), snap(close - 1800, "Money Printer", 10, 5, 2),
                 snap(close + 600, "Smart Money", 100, 50, 30, long_usd=1e6, short_usd=4e5),
                 snap(close + 600, "Money Printer", 12, 6, 4, long_usd=2e6, short_usd=1e5)]
        self.assertEqual(ph.day_row(100, snaps), [100, 112, 90, 56, 34, 3_000_000, 500_000, 112])
        self.assertIsNone(ph.day_row(100, []))

    def test_update_reads_each_closed_day_once_and_keeps_it_in_the_file(self):
        calls = []

        first = 100 * DAY + 60                               # the sweep's first snapshot: just after day 99's close

        def fetch(dim, cohorts, lo, hi, symbol=""):
            calls.append((dim, lo, symbol))
            close = lo + ph.SNAP_WINDOW_S
            day = close // DAY - 1
            if day == 102 or close + 300 < first:            # the sweep was down, or not started yet
                return []
            if symbol:                                       # coin rows: only BTC has holders here
                return [snap(close + 900, cohorts[0], 50, 7, 3)] if symbol == "BTC" else []
            return [snap(close + 300, cohorts[0], 100 + day, 40, 30)]

        now = 105 * DAY + 2 * 3600                          # day 104's close was two hours ago
        added = asyncio.run(ph.update(now=now, fetch=fetch, fetch_first=lambda: first, fetch_lean=lambda lo, hi: []))
        self.assertEqual(added, 2 * 5 * 2)                   # days 99, 100, 101, 103, 104; both groups; all and BTC
        self.assertEqual(sorted(ph._live["smart"]), [99, 100, 101, 103, 104])
        self.assertEqual(ph._live["whales:BTC"][100], [100, 7, 3])
        self.assertNotIn("smart:ETH", ph._live)
        saved = json.load(open(os.path.join(self.dir, "wallet_history_live.json")))
        self.assertEqual(saved["checked_through"], 104)
        self.assertEqual(saved["days"]["whales"][0][:5], [99, 199, 70, 40, 30])
        n = len(calls)
        self.assertEqual(asyncio.run(ph.update(now=now + 600, fetch=fetch, fetch_first=lambda: first,
                                               fetch_lean=lambda lo, hi: [])), 0)
        self.assertEqual(len(calls), n)                      # nothing looked up again, not even the empty day
        # A reload reads the file back.
        ph._seed, ph._crowd_seed, ph._live, ph._checked, ph._view = None, None, {}, None, None
        ph._load()
        self.assertEqual(ph._checked, 104)
        self.assertEqual(ph._live["smart"][103][1], 203)

    def test_view_prefers_recorded_days_and_moves_the_rebuilt_ones_to_their_level(self):
        seed_rows = [[d, 1000, 600, 400, 200, 1e8, 5e7, 100] for d in range(90, 101)]
        self.write_seed({"smart": seed_rows, "whales": seed_rows}, 90, 100)
        ph._load()
        # Recorded days 92-103 (none on day 95): 3 points more long, 1 less short, 2 more positioned than the rebuild.
        ph._live = {g: {d: [d, 1000, 620, 430, 190, 1, 1, 1000] for d in range(92, 104) if d != 95} for g in ph.GROUPS}
        v = ph.view()
        rows = {r[0]: r for r in v["groups"]["smart"]}
        self.assertEqual(sorted(rows), list(range(90, 104)))
        self.assertEqual(v["columns"][-1], "rebuilt")
        self.assertEqual(rows[90], [90, 1000, 620, 430, 190, 1e8, 5e7, 100, 1])     # rebuilt, moved to the recorded level
        self.assertEqual(rows[95][-1], 1)                                             # a gap in the recording: rebuilt
        self.assertEqual(rows[96], [96, 1000, 620, 430, 190, 1, 1, 1000, 0])        # recorded
        self.assertEqual(rows[103][-1], 0)
        self.assertEqual(v["rebuilt"]["to"], 100)
        self.assertEqual(v["recorded_from"], 92)
        o = v["overlap"]["smart"]
        self.assertEqual((o["days"], o["from"], o["to"], o["long_pts"], o["short_pts"]), (8, 92, 100, 3.0, 1.0))
        self.assertEqual(o["offset"], {"positioned": 2.0, "long": 3.0, "short": -1.0})

    def test_coin_rows_follow_the_same_rule(self):
        rebuilt = {d: [d, 300, 100] for d in range(10, 20)}               # 30% long, 10% short of 1,000 wallets
        live = {d: [d, 360, 80] for d in range(13, 22)}                   # 36% and 8% of 1,000; 7 days overlap
        rows = ph.coin_rows(rebuilt, live, {d: 1000 for d in range(10, 20)}, {d: 1000 for d in range(13, 22)})
        by_day = {r[0]: r for r in rows}
        self.assertEqual(sorted(by_day), list(range(10, 22)))
        self.assertEqual(by_day[10], [10, 360, 80, 1])                    # rebuilt, moved by +6 and -2 points
        self.assertEqual(by_day[15], [15, 360, 80, 0])                    # recorded
        short = ph.coin_rows(rebuilt, {14: [14, 360, 80]}, {d: 1000 for d in range(10, 20)}, {14: 1000})
        self.assertEqual(short[0], [10, 300, 100, 1], "a single overlap day moves nothing")

    def test_aligned_keeps_the_counts_possible(self):
        row = [1, 100, 50, 45, 5, 0, 0, 10]
        out = ph.aligned(row, {"positioned": -0.4, "long": 0.6, "short": 0.5})
        self.assertEqual(out[:5], [1, 100, 100, 100, 0])                # long capped at all wallets, short fits the rest
        self.assertEqual(ph.aligned([1, 0, 0, 0, 0, 0, 0, 0], {"positioned": 0, "long": 0.1, "short": 0}), [1, 0, 0, 0, 0, 0, 0, 0])

    def test_update_reads_the_cohort_store_itself(self):
        from cohorts.store import Store
        import cohorts.sweeper as sweeper
        st = Store(os.path.join(self.dir, "cohorts.db"))
        base = 20750 * DAY
        for k in range(4 * 48):                              # four days of 30-minute snapshots
            st.write_snapshot(base + 600 + k * 1800, [
                {"dimension": "pnl", "cohort": "Smart Money", "symbol": None, "wallets": 1000, "positioned": 700,
                 "long_wallets": 400, "short_wallets": 250, "long_usd": 1e8, "short_usd": 6e7},
                {"dimension": "pnl", "cohort": "Money Printer", "symbol": None, "wallets": 200, "positioned": 150,
                 "long_wallets": 90, "short_wallets": 50, "long_usd": 5e7, "short_usd": 3e7},
                {"dimension": "equity", "cohort": "Leviathan", "symbol": None, "wallets": 60, "positioned": 55,
                 "long_wallets": 25, "short_wallets": 28, "long_usd": 3e8, "short_usd": 3.2e8},
                {"dimension": "pnl", "cohort": "Smart Money", "symbol": "BTC", "wallets": 300, "positioned": 300,
                 "long_wallets": 1, "short_wallets": 1, "long_usd": 0, "short_usd": 0},
            ])
        with patch.object(sweeper, "_store", st):
            added = asyncio.run(ph.update(now=base + 4 * DAY + 2 * 3600, fetch_lean=lambda lo, hi: []))
        self.assertEqual(added, 15)                          # days 20749-20753: both groups, and smart's BTC row
        self.assertEqual(ph._live["smart:BTC"][20750], [20750, 1, 1])
        self.assertEqual(ph._live["smart"][20749], [20749, 1200, 850, 490, 300, 150_000_000, 90_000_000, 1200])
        self.assertEqual(ph._live["whales"][20753][:5], [20753, 60, 55, 25, 28])
        st.db.close()

    def test_overlap_needs_a_week(self):
        rows = [[d, 10, 5, 3, 2, 0, 0, 10] for d in range(1, 7)]
        self.assertIsNone(ph.overlap(rows, {r[0]: r for r in rows}))

    def test_without_a_seed_the_view_is_live_only(self):
        ph._load()
        ph._live = {"smart": {5: [5, 10, 6, 4, 2, 0, 0, 10]}, "whales": {}}
        v = ph.view()
        self.assertIsNone(v["rebuilt"])
        self.assertEqual(v["groups"]["smart"], [[5, 10, 6, 4, 2, 0, 0, 10, 0]])
        self.assertEqual(v["recorded_from"], 5)
        self.assertIsNone(v["overlap"]["smart"])


    # ------------------------------------------------------------------ profitable traders

    def test_crowd_rows_sum_the_coins_at_the_bar_closing_the_day(self):
        close = 101 * DAY

        def fetch(lo, hi):
            self.assertEqual((lo, hi), (close - ph.BAR_S, close + ph.BAR_S))
            return [(close - ph.BAR_S, "coin:BTC", 99, 99),
                    (close, "coin:BTC", 30, 10), (close, "coin:ETH", 20, 5), (close, "coin:DOGE", 4, 6),
                    (close + ph.BAR_S, "coin:BTC", 1, 1)]
        out = ph.crowd_rows([100], fetch)
        self.assertEqual(out["crowd"][100], [100, 54, 21])            # positions over every coin, one bar only
        self.assertEqual(out["crowd:BTC"][100], [100, 30, 10])
        self.assertEqual(out["crowd:ETH"][100], [100, 20, 5])
        self.assertNotIn("crowd:SOL", out)
        # The 00:00 bar missing: the nearest one within four hours, the earlier on a tie.
        out = ph.crowd_rows([100], lambda lo, hi: [(close - ph.BAR_S, "coin:BTC", 3, 1), (close + ph.BAR_S, "coin:BTC", 9, 9)])
        self.assertEqual(out["crowd"][100], [100, 3, 1])
        self.assertEqual(ph.crowd_rows([100], lambda lo, hi: []), {})

    def test_fetch_lean_reads_roster_two_coin_rows_from_hyperlens(self):
        import hl_persistence as hp
        with patch.object(hp, "_DB_PATH", os.path.join(self.dir, "hyperlens.db")), patch.object(hp, "_conn", None):
            close = 20750 * DAY
            row = lambda lo, sh: {"long": lo, "short": sh, "long_usd": 1.0, "short_usd": 1.0}
            hp.save_trader_lean(close, {"coin:BTC": row(30, 10), "sector:AI": row(5, 5)}, 2)
            hp.save_trader_lean(close - ph.BAR_S, {"coin:BTC": row(8, 8)})            # before roster version 2
            self.assertEqual(ph._fetch_lean(close - ph.BAR_S, close + ph.BAR_S), [(close, "coin:BTC", 30, 10)])
            hp._conn.close()

    def write_crowd(self, rows, picked=200):
        with open(self.crowd_path, "w") as fh:
            json.dump({"version": 1, "picked": picked, "columns": ["day", "long_share"], "rows": rows}, fh)

    def test_crowd_view_puts_the_rebuilt_days_at_the_recorded_level(self):
        self.write_crowd([[d, 0.6] for d in range(90, 101)])
        ph._load()
        # Recorded days 94-103: 65% of positions long (13 of 20), and BTC on two of them.
        ph._live = {"crowd": {d: [d, 13, 7] for d in range(94, 104)}, "crowd:BTC": {100: [100, 3, 1], 101: [101, 0, 0]}}
        c = ph.view()["crowd"]
        rows = {r[0]: r for r in c["rows"]}
        self.assertEqual(c["columns"], ["day", "long", "short", "long_share", "rebuilt"])
        self.assertEqual(rows[90], [90, None, None, 0.65, 1])          # rebuilt, moved up 5 points
        self.assertEqual(rows[94], [94, 13, 7, 0.65, 0])               # recorded where both exist
        self.assertEqual(rows[103][-1], 0)
        self.assertEqual(c["overlap"], {"days": 7, "from": 94, "to": 100, "offset_pts": 5.0, "gap_pts": 5.0})
        self.assertEqual(c["rebuilt"], {"from": 90, "to": 100, "method": "fixed", "picked": 200})
        self.assertEqual(c["recorded_from"], 94)
        self.assertEqual(c["coins"]["BTC"], [[100, 3, 1, 0.75, 0]])    # a day with no positions is left out
        self.assertEqual(c["coins"]["ETH"], [])

    def test_crowd_view_without_overlap_or_data(self):
        self.write_crowd([[d, 0.7] for d in range(90, 95)])
        ph._load()
        ph._live = {"crowd": {94: [94, 1, 1]}}
        c = ph.view()["crowd"]
        self.assertIsNone(c["overlap"])
        self.assertEqual({r[0]: r[3] for r in c["rows"]}, {90: 0.7, 91: 0.7, 92: 0.7, 93: 0.7, 94: 0.5})
        ph._crowd_seed, ph._live, ph._view = {}, {}, None
        self.assertIsNone(ph.view()["crowd"])

    def test_update_keeps_the_crowd_rows_and_a_failing_record_keeps_the_rest(self):
        first = 100 * DAY + 60
        fetch = lambda dim, cohorts, lo, hi, symbol="": [] if symbol else [snap(lo + ph.SNAP_WINDOW_S, cohorts[0], 10, 4, 3)]
        lean = lambda lo, hi: [(lo + ph.BAR_S, "coin:HYPE", 6, 2)]
        added = asyncio.run(ph.update(now=102 * DAY + 2 * 3600, fetch=fetch, fetch_first=lambda: first, fetch_lean=lean))
        self.assertEqual(added, 4 * 4)                                 # days 98-101: both groups, crowd and crowd:HYPE
        self.assertEqual(ph._live["crowd:HYPE"][100], [100, 6, 2])
        saved = json.load(open(os.path.join(self.dir, "wallet_history_live.json")))
        self.assertEqual(saved["days"]["crowd"], [[d, 6, 2] for d in range(98, 102)])

        def broken(lo, hi):
            raise RuntimeError("no hyperlens db")
        added = asyncio.run(ph.update(now=103 * DAY + 2 * 3600, fetch=fetch, fetch_first=lambda: first, fetch_lean=broken))
        self.assertEqual(added, 2)                                     # day 102: the groups still recorded
        self.assertNotIn(102, ph._live["crowd"])

    def test_a_daily_rule_seed_joins_per_coin_too(self):
        with open(self.crowd_path, "w") as fh:
            json.dump({"version": 2, "columns": ["day", "long", "short"], "rows": [[d, 90, 10] for d in range(90, 101)],
                       "coin_columns": ["day", "long", "short"], "coins": {"BTC": [[d, 8, 2] for d in range(90, 101)]}}, fh)
        ph._load()
        # Recorded days 94-103 at 70% long overall and 50% long on BTC: the rebuilt days move down 20 and 30 points.
        ph._live = {"crowd": {d: [d, 7, 3] for d in range(94, 104)}, "crowd:BTC": {d: [d, 1, 1] for d in range(94, 104)}}
        c = ph.view()["crowd"]
        rows = {r[0]: r for r in c["rows"]}
        self.assertEqual(rows[90], [90, None, None, 0.7, 1])
        self.assertEqual(rows[95], [95, 7, 3, 0.7, 0])
        self.assertEqual(c["rebuilt"]["method"], "daily")
        btc = {r[0]: r for r in c["coins"]["BTC"]}
        self.assertEqual(btc[90], [90, None, None, 0.5, 1])
        self.assertEqual(btc[100], [100, 1, 1, 0.5, 0])
        self.assertEqual(c["coins"]["ETH"], [])

    def test_the_shipped_crowd_seed_is_one_row_a_day(self):
        seed = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seeds",
                                           "crowd_share_seed.json")))
        days = [r[0] for r in seed["rows"]]
        self.assertEqual(seed["columns"], ["day", "long", "short"])
        self.assertEqual(days, list(range(days[0], days[0] + len(days))), "one row a day, no gaps")
        self.assertTrue(all(r[1] >= 0 and r[2] >= 0 and r[1] + r[2] > 0 for r in seed["rows"]))
        self.assertEqual(set(seed["coins"]), set(ph.COINS))


if __name__ == "__main__":
    unittest.main()
