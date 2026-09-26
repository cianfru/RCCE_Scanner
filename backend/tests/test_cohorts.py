import asyncio
import os
import tempfile
import unittest

from cohorts.assign import Position, WalletState, aggregate, divergence, equity_cohort, pnl_cohort, zscore
from cohorts.source import RateLimited, parse
from cohorts.store import Store
from cohorts.sweeper import SLEEPY_EVERY_S, Sweeper, TokenBucket, next_schedule, quiet_until


class AssignTests(unittest.TestCase):
    def test_equity_boundaries(self):
        cases = [(0, "Shrimp"), (249.99, "Shrimp"), (250, "Fish"), (9_999, "Fish"), (10_000, "Dolphin"),
                 (50_000, "Apex Predator"), (100_000, "Small Whale"), (500_000, "Whale"), (1e6, "Tidal Whale"),
                 (5e6, "Leviathan"), (3e9, "Leviathan"), (-5, "Shrimp")]
        for v, name in cases:
            self.assertEqual(equity_cohort(v), name, v)
        self.assertIsNone(equity_cohort(None))

    def test_pnl_boundaries(self):
        cases = [(-5e6, "Giga-Rekt"), (-1e6, "Full Rekt"), (-100e3, "Semi-Rekt"), (-10e3, "Exit Liquidity"),
                 (-0.01, "Exit Liquidity"), (0, "Humble Earner"), (10e3, "Grinder"), (100e3, "Smart Money"),
                 (1e6, "Money Printer"), (-1_000_000.01, "Giga-Rekt")]
        for v, name in cases:
            self.assertEqual(pnl_cohort(v), name, v)

    def test_aggregation_math(self):
        now = 1_000_000.0
        old, young = now - 3 * 86400, now - 3600
        states = [
            WalletState("a", 200_000, 150_000, [Position("BTC", 300_000, True, old), Position("ETH", 100_000, False, young)]),
            WalletState("b", 300_000, 500_000, [Position("BTC", 100_000, False, young)]),
            WalletState("c", 150_000, 120_000, []),                                   # no positions
            WalletState("mm", 200_000, 150_000, [Position(f"C{i}", 1_000, True, old) for i in range(30)]),  # market maker
        ]
        rows = {(r["dimension"], r["cohort"], r["symbol"]): r for r in aggregate(states, now)}
        g = rows[("equity", "Small Whale", None)]
        self.assertEqual((g["wallets"], g["positioned"], g["long_wallets"], g["short_wallets"]), (3, 2, 1, 1))
        self.assertEqual((g["long_usd"], g["short_usd"], g["net_usd"]), (300_000, 200_000, 100_000))
        self.assertAlmostEqual(g["bias"], 0.2)
        self.assertAlmostEqual(g["bias_24h"], -1.0)                               # only the young shorts
        self.assertAlmostEqual(g["lev_wavg"], 500_000 / 500_000)
        self.assertAlmostEqual(g["lev_median"], (2.0 + 1 / 3) / 2, places=2)       # a 400K/200K, b 100K/300K
        btc = rows[("pnl", "Smart Money", "BTC")]
        self.assertEqual((btc["long_usd"], btc["short_usd"], btc["wallets"]), (300_000, 100_000, 2))
        self.assertAlmostEqual(btc["bias"], 0.5)
        self.assertNotIn(("equity", "Small Whale", "C1"), rows)                   # market maker excluded
        self.assertTrue(all(not r["partial"] for r in rows.values()))

    def test_divergence_and_z(self):
        rows = [{"dimension": "pnl", "cohort": c, "symbol": None, "long_usd": lo, "short_usd": sh, "positioned": 1}
                for c, lo, sh in [("Smart Money", 80, 20), ("Money Printer", 20, 80), ("Exit Liquidity", 90, 10)]]
        d = divergence(rows)
        self.assertEqual(d["winners"]["bias"], 0.0)
        self.assertEqual(d["losers"]["bias"], 0.8)
        self.assertEqual(d["divergence"], -0.8)
        self.assertIsNone(zscore([0.1] * 5, 0.2))                                 # too little history
        self.assertEqual(zscore([0.0, 1.0] * 20, 1.0), 1.0)

    def test_parse(self):
        eq, ps = parse({"marginSummary": {"accountValue": "1234.5"}, "assetPositions": [
            {"position": {"coin": "kPEPE", "szi": "-100", "positionValue": "50.5", "entryPx": "0.4"}},
            {"position": {"coin": "BTC", "szi": "0.0"}}]})
        self.assertEqual(eq, 1234.5)
        self.assertEqual(ps, [("PEPE", 50.5, False)])


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += max(0.0, s)


class BucketTests(unittest.TestCase):
    def test_rate_and_penalty(self):
        c = Clock()
        b = TokenBucket(600, capacity=10, clock=c, sleep=c.sleep)            # 10 weight per second

        async def spend(n):
            for _ in range(n):
                await b.take(2)
        asyncio.run(spend(5))                                                 # capacity covers the first 10
        self.assertEqual(c.t, 0)
        asyncio.run(spend(50))                                                # 100 weight at 10/s
        self.assertAlmostEqual(c.t, 10.0, places=6)
        b.penalize(300)
        t0 = c.t
        asyncio.run(spend(5))                                                 # half rate: 10 weight in 2s
        self.assertAlmostEqual(c.t - t0, 2.0, places=6)
        c.t += 400
        b._refill()
        b.tokens = 0
        t0 = c.t
        asyncio.run(spend(5))                                                 # penalty over: full rate again
        self.assertAlmostEqual(c.t - t0, 1.0, places=6)


class ScheduleTests(unittest.TestCase):
    def test_sleepy_and_wake(self):
        streak, nxt = 0, 0.0
        for i in range(3):
            streak, nxt = next_schedule(0.0, [], streak, 1000.0)
        self.assertEqual((streak, nxt), (3, 1000.0 + SLEEPY_EVERY_S))            # demoted after 3 empty sweeps
        streak, nxt = next_schedule(20_000.0, [], streak, 2000.0)
        self.assertEqual((streak, nxt), (0, 0.0))                                # equity back: every sweep again

    def test_quiet_window(self):
        self.assertEqual(quiet_until(14400 * 10 + 60), 14400 * 10 + 1200)
        self.assertIsNone(quiet_until(14400 * 10 + 1500))


class Crash(Exception):
    pass


class FakeSource:
    weight = 2

    def __init__(self, fail_after=None, rate_limit_once=None):
        self.calls, self.fail_after, self.rate_limit_once = [], fail_after, rate_limit_once

    async def fetch(self, address):
        if self.rate_limit_once == address:
            self.rate_limit_once = None
            raise RateLimited()
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise Crash()
        self.calls.append(address)
        return (20_000.0, [("BTC", 10_000.0, True)]) if address.endswith("1") else (0.0, [])


class SweepTests(unittest.TestCase):
    def test_sweep_resume_and_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(os.path.join(d, "c.db"))
            addrs = [f"0x{i:03d}{i % 2}" for i in range(10)]
            st.update_registry([(a, 50_000.0, 200_000.0) for a in addrs], now=0)
            c = Clock(100.0)
            src = FakeSource(fail_after=6, rate_limit_once=addrs[2])
            sw = Sweeper(st, src, TokenBucket(6000, clock=c, sleep=c.sleep), clock=c, sleep=c.sleep, respect_quiet=False)
            import cohorts.sweeper as mod
            old_batch, mod.BATCH = mod.BATCH, 3
            try:
                with self.assertRaises(Crash):
                    asyncio.run(sw.run_once())
                saved = st.db.execute("SELECT COUNT(*) FROM wallet_state_latest").fetchone()[0]
                self.assertGreaterEqual(saved, 3)
                src2 = FakeSource()
                sw2 = Sweeper(st, src2, TokenBucket(6000, clock=c, sleep=c.sleep), clock=c, sleep=c.sleep, respect_quiet=False)
                info = asyncio.run(sw2.run_once())
            finally:
                mod.BATCH = old_batch
            self.assertTrue(info["resumed"])
            self.assertEqual(len(src2.calls) + saved, 10)                         # nothing polled twice
            self.assertEqual(st.db.execute("SELECT COUNT(*) FROM wallet_state_latest").fetchone()[0], 10)
            snap = st.snapshot(st.latest_ts(), dimension="pnl", symbol="")
            sm = next(r for r in snap if r["cohort"] == "Smart Money")
            self.assertEqual((sm["wallets"], sm["positioned"], sm["long_usd"]), (10, 5, 50_000))
            self.assertEqual(st.runs(1)[0]["status"], "done")
            self.assertGreaterEqual(sum(r["rate_limited"] for r in st.runs(5)), 1)


if __name__ == "__main__":
    unittest.main()


class EndpointTests(unittest.TestCase):
    def test_endpoints_before_and_after_a_sweep(self):
        from fastapi.testclient import TestClient
        import cohorts.sweeper as mod
        import main
        with tempfile.TemporaryDirectory() as d:
            old = mod._store
            mod._store = Store(os.path.join(d, "c.db"))
            try:
                c = TestClient(main.app)
                self.assertIsNone(c.get("/api/cohorts").json()["ts"])
                mod._store.update_registry([("0xa1", 50_000.0, 2e6)], now=0)
                clk = Clock(1_000_000.0)
                sw = Sweeper(mod._store, FakeSource(), TokenBucket(6000, clock=clk, sleep=clk.sleep),
                             clock=clk, sleep=clk.sleep, respect_quiet=False)
                asyncio.run(sw.run_once())
                body = c.get("/api/cohorts?dimension=pnl").json()
                self.assertEqual([r["cohort"] for r in body["rows"]], ["Money Printer"])
                self.assertEqual(c.get("/api/cohorts?symbol=BTC").json()["symbol"], "BTC")
                self.assertEqual(c.get("/api/cohorts/divergence").json()["winners"]["bias"], 1.0)
                self.assertEqual(len(c.get("/api/cohorts/history?dimension=pnl&cohort=Money%20Printer&days=180").json()["points"]), 0)
                self.assertEqual(c.get("/api/cohorts/status").json()["registry"], 1)
                self.assertIn("cohorts", c.get("/api/hyperlens/consensus?symbol=BTC&cohorts=true").json())
            finally:
                mod._store = old
