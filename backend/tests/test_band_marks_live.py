"""band_marks_live.py: the band model's marks live, the window the engine reads, and their record."""
import asyncio
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import band_marks_live as L
import hl_persistence as hp
from research import band_marks as M

DAY_MS = 86_400_000


def _walk(n, seed=11):
    """A walk with fast legs both ways, so hot and cold states and top divergences occur."""
    rng = np.random.default_rng(seed)
    drift = np.zeros(n)
    i = 0
    while i < n:
        k = int(rng.integers(30, 160))
        drift[i: i + k] = rng.choice([0.012, -0.012, 0.0005, -0.0005, 0.02, -0.02])
        i += k
    close = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.035, n)))
    high = close * np.exp(np.abs(rng.normal(0, 0.02, n)))
    low = close * np.exp(-np.abs(rng.normal(0, 0.02, n)))
    return high, low, close


def _klines(first_day, high, low, close):
    return [[(first_day + i) * DAY_MS, str(close[i]), str(high[i]), str(low[i]), str(close[i]), "0"]
            for i in range(len(close))]


class PairTests(unittest.TestCase):
    def test_scanner_symbols_map_to_binance_pairs(self):
        self.assertEqual(L.pair_of("BTC/USDT"), "BTCUSDT")
        self.assertEqual(L.pair_of("KPEPE/USDT"), "PEPEUSDT")      # per-1,000 market: the token's pair
        self.assertEqual(L.pair_of("KAITO/USDT"), "KAITOUSDT")     # a K ticker that is not a k market
        self.assertIsNone(L.pair_of("xyz:GOLD/USDT"))
        self.assertIsNone(L.pair_of(""))


class MarkTests(unittest.TestCase):
    def test_grid_keeps_completed_days_and_fills_gaps(self):
        kl = [[10 * DAY_MS, "1", "2", "1", "1.5", "0"], [12 * DAY_MS, "1", "3", "1", "2.5", "0"],
              [13 * DAY_MS, "1", "4", "1", "3.5", "0"]]
        days, hi, lo, cl = L.grid(kl, 12)                 # day 13 is under way: left out
        self.assertEqual(list(days), [10, 11, 12])
        self.assertEqual(list(cl), [1.5, 1.5, 2.5])
        self.assertEqual(list(hi), [2.0, 1.5, 3.0])
        self.assertIsNone(L.grid([["k"]], 12))
        self.assertIsNone(L.grid([], 12))

    def test_marks_are_the_models_on_the_recent_days(self):
        high, low, close = _walk(2600)
        first = 17000
        last = first + len(close) - 1
        out = M.model(np.arange(first, last + 1), high, low, close)
        got = L.marks(_klines(first, high, low, close), last)
        for k in L.KINDS:
            want = [first + i for i in np.flatnonzero(out[k]) if first + i >= last - L.RECORD_DAYS + 1]
            self.assertEqual(got[k], want)

    def test_two_thousand_days_give_the_full_historys_recent_marks(self):
        high, low, close = _walk(4200, seed=3)
        first = 15000
        seen = 0
        for end in range(2500, len(close), 50):
            full = M.model(np.arange(first, first + end + 1), high[:end + 1], low[:end + 1], close[:end + 1])
            s = end - 1999
            got = L.marks(_klines(first + s, high[s:end + 1], low[s:end + 1], close[s:end + 1]), first + end)
            for k in L.KINDS:
                want = [first + i for i in np.flatnonzero(full[k]) if i >= end - L.RECORD_DAYS + 1]
                self.assertEqual(got[k], want, (end, k))
                seen += len(want)
        self.assertGreater(seen, 0)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._db = (hp._DB_PATH, hp._conn)
        hp._DB_PATH, hp._conn = os.path.join(self.dir, "marks.db"), None
        L.reset_view()

    def tearDown(self):
        if hp._conn is not None:
            hp._conn.close()
        hp._DB_PATH, hp._conn = self._db
        shutil.rmtree(self.dir, ignore_errors=True)
        L.reset_view()

    def test_the_window_runs_90_completed_days_from_the_mark(self):
        d = 20000
        self.assertIsNone(hp.last_band_marks_day())
        hp.save_band_marks(d + 5, {"PEPEUSDT": {"top_div": [d], "cap_turn": []}, "ETHUSDT": {"top_div": [], "cap_turn": [d]}})
        self.assertEqual(hp.last_band_marks_day(), d + 5)

        def at(last_day, symbol="KPEPE/USDT"):
            L.reset_view()
            return L.in_window(symbol, now=(last_day + 1) * 86_400 + 60)
        self.assertTrue(at(d))                     # the mark's own day, once it has closed
        self.assertTrue(at(d + 89))                # the 90th completed day
        self.assertFalse(at(d + 90))
        self.assertFalse(at(d - 1))
        self.assertFalse(at(d, "ETH/USDT"))        # covered, no top divergence (a capitulation turn is not one)
        self.assertIsNone(at(d, "SOL/USDT"))       # not covered
        L.reset_view()
        self.assertEqual(L.holding_out(now=(d + 10) * 86_400), {"PEPEUSDT": d})

    def test_coverage_is_the_latest_run_and_saving_twice_adds_nothing(self):
        d = 20000
        self.assertEqual(hp.save_band_marks(d, {"BTCUSDT": {"top_div": [d - 3], "cap_turn": []}}), 1)
        self.assertEqual(hp.save_band_marks(d, {"BTCUSDT": {"top_div": [d - 3], "cap_turn": []}}), 0)
        hp.save_band_marks(d + 1, {"ETHUSDT": {"top_div": [], "cap_turn": []}})
        L.reset_view()
        self.assertIsNone(L.in_window("BTC/USDT", now=(d + 2) * 86_400))     # left out of the latest run
        self.assertFalse(L.in_window("ETH/USDT", now=(d + 2) * 86_400))


class DailyJobTests(unittest.TestCase):
    def setUp(self):
        import market_history as mh
        self.mh = mh
        self.dir = tempfile.mkdtemp()
        self.tmp = patch.object(mh, "_live_path", return_value=os.path.join(self.dir, "live.json"))
        self.tmp.start()
        self._state = (list(mh._live), dict(mh._stretch), dict(mh._closes), mh._stretch_seed)
        self._db = (hp._DB_PATH, hp._conn)
        hp._DB_PATH, hp._conn = os.path.join(self.dir, "job.db"), None
        L.reset_view()

    def tearDown(self):
        mh = self.mh
        self.tmp.stop()
        mh._live[:], (mh._stretch, mh._closes, mh._stretch_seed) = self._state[0], self._state[1:]
        if hp._conn is not None:
            hp._conn.close()
        hp._DB_PATH, hp._conn = self._db
        shutil.rmtree(self.dir, ignore_errors=True)
        L.reset_view()

    def test_the_daily_update_records_the_marks_once_a_day_from_two_pages(self):
        mh = self.mh
        seed = mh._load()
        last = seed["days"][-1][0]
        mh._stretch_seed = {"rows": [[last + 1, 50, 5, 0.1]]}       # nothing missing but the marks
        high, low, close = _walk(2600)
        first = last + 2 - len(close) + 1                          # the last candle is the day under way
        allk = _klines(first, high, low, close)
        pairs = seed["pairs"][:45]
        urls = []

        async def fake_fetch(session, url):
            urls.append(url)
            if "alternative" in url:
                return {"data": []}
            if "endTime=" in url:
                end = int(url.split("endTime=")[1])
                older = [r for r in allk if r[0] <= end]
                return older[-1000:]
            return allk[-1000:]

        rows = lambda kl, days, w, m: {d: ("MARKUP", 1.0, 100.0) for d in days}
        now = (last + 2) * 86_400 + 100
        with patch.object(mh, "_fetch_json", fake_fetch), patch.object(mh, "day_rows", rows), \
                patch.object(mh, "all_days", lambda: [[last + 1]]), \
                patch.object(mh, "_load", lambda: dict(seed, pairs=pairs)):
            asyncio.run(mh.update(now=now))
            first_run = len(urls)
            asyncio.run(mh.update(now=now))                        # marks already computed for yesterday
        self.assertEqual(hp.last_band_marks_day(), last + 1)
        self.assertEqual(sum("endTime=" in u for u in urls[:first_run]), 45)
        self.assertEqual(sum("endTime=" in u for u in urls[first_run:]), 0)
        want = L.marks(allk, last + 1)
        events, coverage = hp.load_band_marks(0)
        self.assertEqual(len(coverage), 45)
        for kind in L.KINDS:
            self.assertEqual(sorted(d for p, d, k in events if p == pairs[0] and k == kind), want[kind])


if __name__ == "__main__":
    unittest.main()
