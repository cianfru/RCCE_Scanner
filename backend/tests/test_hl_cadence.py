"""Adaptive reading cadence (hl_cadence) and its use in the cohort sweep and HyperLens."""
import asyncio
import os
import tempfile
import time
import unittest
from collections import deque
from unittest import mock

import hl_cadence as cad
from cohorts.store import PIN_ELITE, PIN_ROSTER, Store
from cohorts.sweeper import SNAPSHOT_EVERY_S, Sweeper, TokenBucket

MIN = 60


class TierTests(unittest.TestCase):
    def test_back_off_while_unchanged(self):
        streak, seen = 0, []
        for _ in range(7):
            seen.append(cad.interval(streak, flat=False))
            streak = cad.next_streak(streak, False)
        self.assertEqual(seen, [10 * MIN, 15 * MIN, 30 * MIN, 45 * MIN, 60 * MIN, 60 * MIN, 60 * MIN])
        self.assertEqual(cad.next_streak(4, True), 0)                         # a change resets to 10 min
        self.assertEqual(cad.interval(0, flat=False), 10 * MIN)

    def test_flat_followed_elite(self):
        self.assertEqual(cad.interval(3, flat=True), 2 * 3600)                # flat and unchanged: 2 h
        self.assertEqual(cad.interval(0, flat=True), 10 * MIN)                # just closed everything: changed
        self.assertEqual(cad.interval(4, flat=True, followed=True), 5 * MIN)  # followed wins over everything
        self.assertEqual(cad.interval(4, flat=False, followed=True), 5 * MIN)
        self.assertEqual(cad.interval(4, flat=False, elite=True), 15 * MIN)   # elite floor
        self.assertEqual(cad.interval(3, flat=True, elite=True), 15 * MIN)
        self.assertEqual(cad.interval(0, flat=False, elite=True), 10 * MIN)   # faster tiers stay faster

    def test_jitter_only_on_long_intervals(self):
        self.assertEqual(cad.next_at(0, 0, False, rng=lambda: 1.0), 10 * MIN)
        self.assertAlmostEqual(cad.next_at(0, 4, False, rng=lambda: 1.0), 3600 * 1.1)
        self.assertAlmostEqual(cad.next_at(0, 4, False, rng=lambda: 0.0), 3600 * 0.9)

    def test_reading_age_covers_the_slowest_tier(self):
        self.assertGreaterEqual(cad.MAX_READING_AGE_S, cad.FLAT_S * (1 + cad.JITTER) + cad.TICK_S)


class ChangeTests(unittest.TestCase):
    base = {"BTC": (10.0, 1_000_000.0), "ETH": (-50.0, 150_000.0)}

    def test_same_book_is_unchanged(self):
        self.assertFalse(cad.changed(self.base, dict(self.base)))
        moved_price = {"BTC": (10.0, 1_100_000.0), "ETH": (-50.0, 140_000.0)}
        self.assertFalse(cad.changed(self.base, moved_price))                 # value moves with price only

    def test_dust_is_ignored(self):
        tiny = dict(self.base, BTC=(10.004, 1_000_400.0))                     # 0.04%: dust
        self.assertFalse(cad.changed(self.base, tiny))
        dust_coin = dict(self.base, PEPE=(1000.0, 30.0))                      # a $30 position appears
        self.assertFalse(cad.changed(self.base, dust_coin))
        small_frac_but_big = {"BTC": (10.0, 1_000_000.0), "ETH": (-50.4, 151_200.0)}   # 0.8%: under 1%
        self.assertFalse(cad.changed(self.base, small_frac_but_big))

    def test_real_changes(self):
        self.assertTrue(cad.changed(self.base, dict(self.base, BTC=(12.0, 1_200_000.0))))     # add 20%
        self.assertTrue(cad.changed(self.base, {"BTC": (10.0, 1_000_000.0)}))                 # ETH closed
        self.assertTrue(cad.changed(self.base, dict(self.base, SOL=(100.0, 15_000.0))))       # new coin
        self.assertTrue(cad.changed(self.base, dict(self.base, ETH=(50.0, 150_000.0))))       # flipped
        self.assertTrue(cad.changed(None, self.base))                                         # no earlier reading
        self.assertTrue(cad.changed(self.base, {}))                                           # closed everything
        self.assertFalse(cad.changed({}, {}))

    def test_legacy_readings_compare_sides(self):
        self.assertFalse(cad.changed_sides({("BTC", True), ("ETH", False)}, self.base))
        self.assertTrue(cad.changed_sides({("BTC", True)}, self.base))

    def test_book_from_state(self):
        data = {"assetPositions": [{"position": {"coin": "BTC", "szi": "-2", "positionValue": "200000"}},
                                   {"position": {"coin": "ETH", "szi": "0"}}]}
        self.assertEqual(cad.book_from_state(data), {"BTC": (-2.0, 200000.0)})


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += max(0.0, s)


class ScriptedSource:
    """clearinghouseState stand-in: each address returns its current scripted book."""
    weight = 2

    def __init__(self, books):
        self.books, self.calls = books, []

    async def fetch(self, address):
        self.calls.append(address)
        eq, ps = self.books[address]
        return eq, list(ps)


class SweepCadenceTests(unittest.TestCase):
    def _sweeper(self, st, src, clk):
        return Sweeper(st, src, TokenBucket(60_000, clock=clk, sleep=clk.sleep), clock=clk, sleep=clk.sleep,
                       respect_quiet=False)

    def test_changed_wallets_come_back_fast_and_quiet_ones_back_off(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(os.path.join(d, "c.db"))
            addrs = ["0xquiet", "0xbusy", "0xflat", "0xelite"]
            st.update_registry([(a, 500_000.0, 1e6) for a in addrs], now=0)
            st.set_pinned(["0xelite"], elite=["0xelite"])
            books = {"0xquiet": (500_000.0, [("BTC", 100_000.0, True, 1.0)]),
                     "0xbusy": (500_000.0, [("ETH", 50_000.0, True, 20.0)]),
                     "0xflat": (500_000.0, []),
                     "0xelite": (500_000.0, [("SOL", 80_000.0, False, 500.0)])}
            src = ScriptedSource(books)
            clk = Clock(1_000_000.0)
            sw = self._sweeper(st, src, clk)
            reads = {a: [] for a in addrs}
            import cohorts.sweeper as mod
            with mock.patch.object(mod.random, "random", return_value=0.5):   # no jitter
                end = clk.t + 6 * 3600
                n = 0
                while clk.t < end:
                    before = len(src.calls)
                    asyncio.run(sw.run_once())
                    for a in src.calls[before:]:
                        reads[a].append(clk.t)
                    n += 1
                    if n % 2 == 0:                                            # 0xbusy trades every 10 minutes
                        eq, ps = books["0xbusy"]
                        books["0xbusy"] = (eq, [("ETH", ps[0][1] * 1.1, True, ps[0][3] * 1.1)])
                    clk.t += cad.TICK_S
            gaps = lambda a: [round((b - x) / 60) for x, b in zip(reads[a], reads[a][1:])]
            # quiet: first reading (no history) -> 10, then 15, 30, 45, 60, 60 ... (each rounded up to a tick)
            self.assertEqual(gaps("0xquiet")[:6], [10, 15, 30, 45, 60, 60])
            self.assertTrue(all(g <= 15 for g in gaps("0xbusy")))              # keeps changing: 10-15 min
            self.assertEqual(gaps("0xflat")[:3], [10, 120, 120])               # flat: 2 h once settled
            self.assertTrue(all(g <= 15 for g in gaps("0xelite")))             # elite floor
            self.assertLess(len(reads["0xquiet"]), 6 * 60 / 30)                # fewer reads than every 30 min

    def test_snapshot_every_30_minutes_not_every_tick(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(os.path.join(d, "c.db"))
            st.update_registry([("0xa1", 500_000.0, 1e6)], now=0)
            clk = Clock(14400 * 100 + 3600.0)
            sw = self._sweeper(st, ScriptedSource({"0xa1": (500_000.0, [("BTC", 100_000.0, True, 1.0)])}), clk)
            stamps = set()
            for _ in range(12):                                               # one hour of 5-min ticks
                asyncio.run(sw.run_once())
                stamps.add(st.latest_ts())
                clk.t += cad.TICK_S
            self.assertEqual(len(stamps), 2)
            a, b = sorted(stamps)
            self.assertEqual(b - a, SNAPSHOT_EVERY_S)
            rows = st.snapshot(b, symbol="")
            self.assertTrue(rows and all(r["roster_version"] == cad.ROSTER_VERSION for r in rows))
            self.assertEqual(rows[0]["wallets"], 1)                           # reading from up to an hour ago counts

    def test_old_database_starts_settled(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "old.db")
            old = sqlite3.connect(path)
            old.execute("CREATE TABLE wallets (address TEXT PRIMARY KEY, first_seen REAL NOT NULL, last_seen REAL NOT NULL, "
                        "lb_value REAL, all_time_pnl REAL, active INTEGER NOT NULL DEFAULT 1, focus INTEGER NOT NULL DEFAULT 0, "
                        "pinned INTEGER NOT NULL DEFAULT 0, next_poll_at REAL NOT NULL DEFAULT 0)")
            old.execute("INSERT INTO wallets VALUES ('0xa', 0, 0, 1e6, 1e6, 1, 1, 1, 0)")
            old.execute("CREATE TABLE wallet_state_latest (address TEXT PRIMARY KEY, ts REAL NOT NULL, equity REAL NOT NULL, "
                        "positions TEXT NOT NULL)")
            old.execute("""INSERT INTO wallet_state_latest VALUES ('0xa', 10, 1e6, '[["BTC",100000,1,5]]')""")
            old.commit()
            old.close()
            st = Store(path)
            self.assertEqual(st.due(100.0), [("0xa", 1e6, 1, cad.SETTLED_STREAK)])
            clk = Clock(100.0)
            src = ScriptedSource({"0xa": (1e6, [("BTC", 101_000.0, True, 1.0)])})    # same side: unchanged
            with mock.patch("cohorts.sweeper.random.random", return_value=0.5):
                asyncio.run(self._sweeper(st, src, clk).run_once())
            nxt, streak = st.db.execute("SELECT next_poll_at, streak FROM wallets").fetchone()
            self.assertEqual((round(nxt - clk.t), streak), (3600, cad.SETTLED_STREAK + 1))
            self.assertEqual(st.previous("0xa")[1], {"BTC": (1.0, 101_000.0)})   # sizes kept from now on


def _state(av, *positions):
    return {"marginSummary": {"accountValue": str(av)}, "assetPositions": [{"position": p} for p in positions]}


class HyperLensOwnPollTests(unittest.TestCase):
    def test_followed_always_roster_only_when_due_without_the_sweep(self):
        import hl_intelligence as hl
        roster = [hl.TrackedWallet(address=f"0x{i}", account_value=1e6) for i in range(4)]
        pos = {"coin": "ETH", "szi": "1", "entryPx": "2000", "positionValue": "2000", "leverage": {"type": "cross", "value": 2}}
        snap = hl._snapshot_from_state(_state(1e6, pos))
        fetch = mock.AsyncMock(return_value=snap)
        now = time.time()
        plan = {"0x0": (now - 1, 4), "0x1": (now + 600, 4), "0x2": (now + 600, 4)}   # 0x3: never read -> due
        with mock.patch.object(hl, "_roster", roster), mock.patch.object(hl, "_asset_index_map", {"x": "y"}), \
                mock.patch.object(hl, "_poll_plan", plan), mock.patch.object(hl, "_snapshots", {}), \
                mock.patch.object(hl, "_fetch_wallet_positions", fetch), mock.patch.object(hl, "_consensus", {}), \
                mock.patch.object(hl, "_wallet_cohorts", {}), mock.patch.object(hl, "_last_db_save_at", 1e18), \
                mock.patch.object(hl, "_get_watchlist_addresses", return_value={"0x2"}), \
                mock.patch.object(hl, "roster_via_cohorts", return_value=False):
            asyncio.run(hl.poll_positions())
            polled = sorted(c.args[2].address for c in fetch.call_args_list)
            self.assertEqual(polled, ["0x0", "0x2", "0x3"])                    # 0x1 not due yet
            due2, streak2 = hl._poll_plan["0x2"]
            self.assertAlmostEqual(due2 - now, cad.FOLLOWED_S, delta=5)         # followed: 5 min
            self.assertEqual(hl._poll_plan["0x3"][1], 0)                         # first reading counts as a change
            self.assertAlmostEqual(hl._poll_plan["0x3"][0] - now, 10 * MIN, delta=5)
            fetch.reset_mock()
            asyncio.run(hl.poll_positions(force=True))
            self.assertEqual(len(fetch.call_args_list), 4)                     # the 4-hour record reads everyone


if __name__ == "__main__":
    unittest.main()
