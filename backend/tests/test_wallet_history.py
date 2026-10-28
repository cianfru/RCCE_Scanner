"""Wallet positioning history: live rows from the cohort sweep's snapshots, merged after the rebuilt seed."""
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
        ph._seed, ph._live, ph._checked, ph._view = None, {}, None, None
        self.dir = tempfile.mkdtemp(prefix="wh_test_")
        self.live = patch.object(ph, "_live_path", return_value=os.path.join(self.dir, "wallet_history_live.json"))
        self.live.start()
        self.seed_path = os.path.join(self.dir, "seed.json")
        self.seed = patch.object(ph, "SEED_PATH", ph.Path(self.seed_path))
        self.seed.start()

    def tearDown(self):
        self.live.stop()
        self.seed.stop()
        shutil.rmtree(self.dir, ignore_errors=True)
        ph._seed, ph._live, ph._checked, ph._view = None, {}, None, None

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

        def fetch(dim, cohorts, lo, hi):
            calls.append((dim, lo))
            close = lo + ph.SNAP_WINDOW_S
            day = close // DAY - 1
            if day == 102 or close + 300 < first:            # the sweep was down, or not started yet
                return []
            return [snap(close + 300, cohorts[0], 100 + day, 40, 30)]

        now = 105 * DAY + 2 * 3600                          # day 104's close was two hours ago
        added = asyncio.run(ph.update(now=now, fetch=fetch, fetch_first=lambda: first))
        self.assertEqual(added, 2 * 5)                       # days 99, 100, 101, 103, 104 for both groups
        self.assertEqual(sorted(ph._live["smart"]), [99, 100, 101, 103, 104])
        saved = json.load(open(os.path.join(self.dir, "wallet_history_live.json")))
        self.assertEqual(saved["checked_through"], 104)
        self.assertEqual(saved["days"]["whales"][0][:5], [99, 199, 70, 40, 30])
        n = len(calls)
        self.assertEqual(asyncio.run(ph.update(now=now + 600, fetch=fetch, fetch_first=lambda: first)), 0)
        self.assertEqual(len(calls), n)                      # nothing looked up again, not even the empty day
        # A reload reads the file back.
        ph._seed, ph._live, ph._checked, ph._view = None, {}, None, None
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
            added = asyncio.run(ph.update(now=base + 4 * DAY + 2 * 3600))
        self.assertEqual(added, 10)                          # days 20749-20753, both groups
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


if __name__ == "__main__":
    unittest.main()
