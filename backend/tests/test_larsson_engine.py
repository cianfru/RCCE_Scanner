"""Larsson Line parity against the official v2.51 script's flips on Binance daily bars.

Fixtures are Binance spot daily closes (public market data), committed so the
tests run offline. Dates are bar opens, UTC.
"""
import gzip
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from engines.larsson_engine import (
    BLUE, GOLD, GREY, LARSSON_VERSION, READY_BARS, compute_larsson_series,
    compute_larsson_snapshot, ema,
)

FIXTURES = Path(__file__).parent / "fixtures" / "larsson"
DAY_MS = 86_400_000


def load(pair):
    with gzip.open(FIXTURES / f"{pair}_1d_close.csv.gz", "rt") as fh:
        rows = [line.strip().split(",") for line in fh if line[0].isdigit()]
    ts = np.array([datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000 for d, _ in rows])
    return ts, np.array([float(c) for _, c in rows])


def by_date(series):
    day = lambda t: datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return {day(t): i for i, t in enumerate(series["timestamps"])}


PARITY = {
    "BTCUSDT": [(BLUE, "2018-02-05"), (BLUE, "2020-03-13"), (GOLD, "2020-05-04"), (GOLD, "2022-04-02"),
                (BLUE, "2022-04-17"), (GOLD, "2026-05-01"), (BLUE, "2026-06-03"), (GOLD, "2026-08-23")],
    "ETHUSDT": [(BLUE, "2018-03-13"), (BLUE, "2020-03-18"), (GOLD, "2020-04-30"), (GOLD, "2022-04-04"),
                (BLUE, "2022-04-28"), (GOLD, "2026-05-11"), (BLUE, "2026-05-20"), (GOLD, "2026-08-19")],
    "LTCBTC": [(GOLD, "2026-09-24")],
}


class ParityTests(unittest.TestCase):
    def test_expected_flips_on_expected_dates(self):
        for pair, expected in PARITY.items():
            ts, close = load(pair)
            s = compute_larsson_series(close, ts)
            idx = by_date(s)
            for kind, date in expected:
                with self.subTest(pair=pair, date=date):
                    self.assertEqual(s["flip"][idx[date]], kind)

    def test_luna_grey_warning_precedes_blue_flip(self):
        ts, close = load("LUNAUSDT")
        s = compute_larsson_series(close, ts)
        idx = by_date(s)
        self.assertEqual(s["flip"][idx["2022-03-01"]], GOLD)
        grey = idx["2022-05-01"]
        self.assertEqual(s["state"][grey], GREY)
        self.assertTrue(s["grey_after_gold"][grey])
        self.assertIsNone(s["flip"][grey])
        self.assertAlmostEqual(close[grey], 82, delta=1)
        blue = idx["2022-05-09"]
        self.assertEqual(s["flip"][blue], BLUE)
        self.assertAlmostEqual(close[blue], 30, delta=1)
        # Grey is a warning only: no flip anywhere between the two.
        self.assertTrue(all(f is None for f in s["flip"][grey:blue]))


class PropertyTests(unittest.TestCase):
    def setUp(self):
        self.series = [compute_larsson_series(close, ts) for ts, close in map(load, ("BTCUSDT", "ETHUSDT", "LTCBTC", "LUNAUSDT"))]

    def test_grey_never_emits_a_flip(self):
        for s in self.series:
            self.assertTrue(all(f is None for st, f in zip(s["state"], s["flip"]) if st == GREY))

    def test_flips_alternate_strictly(self):
        for s in self.series:
            flips = [f for f in s["flip"] if f]
            self.assertTrue(all(a != b for a, b in zip(flips, flips[1:])))

    def test_return_to_same_colour_through_grey_is_silent(self):
        # Uptrend, a 10% pullback that breaks the ribbon order (grey) but never
        # reaches full blue order, then the uptrend resumes: gold, grey, gold.
        close = np.concatenate([np.linspace(100, 200, 200), np.linspace(200, 180, 15), np.linspace(180, 300, 150)])
        s = compute_larsson_series(close, np.arange(len(close)) * DAY_MS)
        self.assertIn(GREY, s["state"])
        self.assertNotIn(BLUE, s["state"])
        self.assertEqual([f for f in s["flip"] if f], [])
        self.assertEqual(sum(s["grey_after_gold"]), 1)

    def test_ema_seeds_with_sma(self):
        x = np.arange(1, 11, dtype=float)
        e = ema(x, 4)
        self.assertTrue(np.isnan(e[2]))
        self.assertAlmostEqual(e[3], 2.5)
        self.assertAlmostEqual(e[4], 5 * 0.4 + 2.5 * 0.6)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_ignores_bar_in_progress(self):
        ts, close = load("BTCUSDT")
        ohlcv = {"timestamp": ts, "close": close}
        last_open = ts[-1]
        mid_bar = compute_larsson_snapshot(ohlcv, "1d", last_open + DAY_MS / 2)
        at_close = compute_larsson_snapshot(ohlcv, "1d", last_open + DAY_MS)
        self.assertEqual(mid_bar["candle_close_time"], last_open / 1000)
        self.assertEqual(at_close["candle_close_time"], (last_open + DAY_MS) / 1000)
        self.assertEqual(at_close["version"], LARSSON_VERSION)
        self.assertEqual(at_close["data_quality"], "ready")

    def test_short_history_is_not_ready(self):
        ts, close = load("BTCUSDT")
        n = READY_BARS - 1
        snap = compute_larsson_snapshot({"timestamp": ts[:n], "close": close[:n]}, "1d", ts[n - 1] + DAY_MS)
        self.assertEqual(snap["data_quality"], "warmup")
        tiny = compute_larsson_snapshot({"timestamp": ts[:20], "close": close[:20]}, "1d", ts[19] + DAY_MS)
        self.assertEqual(tiny["data_quality"], "unavailable")


if __name__ == "__main__":
    unittest.main()
