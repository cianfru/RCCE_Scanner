"""A corrupt weekly series must not turn into a bearish BMSB (PURR/USDT spot, audit COIN-02)."""
import unittest
from unittest.mock import patch

import numpy as np

from candle_snapshot import TF_MS, consistent_weekly
from engines.exhaustion_engine import compute_exhaustion
from engines.heatmap_engine import compute_heatmap
from signal_synthesizer import synthesize_signal

MONDAY = 4 * TF_MS["1d"]  # 1970-01-05, where weekly bars open


def daily(days=210, start=MONDAY + 10 * TF_MS["1w"]):
    """Flat market around 0.10, like PURR while its band jumped."""
    rng = np.random.default_rng(7)
    close = 0.10 + rng.normal(0, 0.002, days)
    return {"timestamp": start + np.arange(days) * TF_MS["1d"],
            "open": close, "high": close * 1.03, "low": close * 0.97,
            "close": close, "volume": np.full(days, 1000.0)}


def weekly_from(d, weeks=40, corrupt=(), factor=40.0):
    """Weekly bars from MONDAY; weeks covered by *d* are resampled from it, older ones stay flat."""
    ts = MONDAY + np.arange(weeks) * TF_MS["1w"]
    close = np.full(weeks, 0.10)
    for i, t in enumerate(ts):
        inside = (d["timestamp"] >= t) & (d["timestamp"] < t + TF_MS["1w"])
        if inside.any():
            close[i] = d["close"][inside][-1]
    close[list(corrupt)] *= factor
    return {"timestamp": ts, "open": close, "high": close * 1.05, "low": close * 0.95,
            "close": close, "volume": np.full(weeks, 7000.0)}


class BmsbSanityTests(unittest.TestCase):
    def setUp(self):
        self.daily = daily()
        # The last closed weeks carry a close far outside what the market traded that week.
        self.bad = weekly_from(self.daily, corrupt=(35, 36, 37, 38))

    def test_weekly_bars_outside_the_week_range_are_dropped(self):
        clean = consistent_weekly(self.bad, self.daily, "1d")
        self.assertEqual(len(clean["close"]), len(self.bad["close"]) - 4)
        self.assertLess(clean["close"].max(), 0.2)
        good = weekly_from(self.daily)
        self.assertIs(consistent_weekly(good, self.daily, "1d"), good)

    def test_weeks_without_shorter_candles_are_kept(self):
        # The first ten weeks precede the daily history and cannot be checked.
        old = weekly_from(self.daily, corrupt=(2,))
        self.assertEqual(len(consistent_weekly(old, self.daily, "1d")["close"]), len(old["close"]))

    def test_band_far_from_price_is_unavailable_not_bearish(self):
        heat = compute_heatmap(self.daily, self.bad)
        self.assertEqual(heat["bmsb_mid"], 0.0)
        self.assertEqual(heat["direction"], 0)
        self.assertEqual(compute_exhaustion(self.daily, self.bad)["state"], "NEUTRAL")
        row = dict(regime="MARKUP", confidence=70, zscore=.5, heat=heat["heat"], heat_phase="Neutral",
                   raw_signal="LIGHT_LONG", bmsb_valid=bool(heat["bmsb_mid"]), heat_direction=heat["direction"])
        out = synthesize_signal(row, {"consensus": "RISK-ON"})
        self.assertEqual(out.signal, "WAIT")
        self.assertTrue(out.reason.startswith("BMSB data unavailable"))
        self.assertNotIn("BMSB bearish", out.reason)

    def test_plausible_band_still_reads(self):
        heat = compute_heatmap(self.daily, weekly_from(self.daily))
        self.assertAlmostEqual(heat["bmsb_mid"], 0.10, delta=0.01)

    def test_genuine_pump_or_crash_keeps_the_band(self):
        # Price triples (or falls to a third) over the last 20 days: the band lags but is real.
        for mult in (3.5, 0.28):
            d = daily()
            d = {k: v.copy() for k, v in d.items()}
            for k in ("open", "high", "low", "close"):
                d[k][-20:] *= mult
            heat = compute_heatmap(d, weekly_from(d))
            self.assertGreater(heat["bmsb_mid"], 0.0, mult)

    def test_sub_cent_coin_keeps_its_band(self):
        scale = lambda x: {k: (v * 1e-5 if k in ("open", "high", "low", "close") else v) for k, v in x.items()}
        heat = compute_heatmap(scale(self.daily), scale(weekly_from(self.daily)))
        self.assertAlmostEqual(heat["bmsb_mid"], 1e-6, delta=1e-7)

    def test_scanner_uses_the_cleaned_weekly_series(self):
        from scanner import _process_symbol
        as_of = float(self.daily["timestamp"][-1] + TF_MS["1d"])
        with patch("scanner.compute_rcce", return_value={}):
            result = _process_symbol("PURR/USDT", "1d", self.daily, self.bad, None, None, as_of_ms=as_of)
        self.assertTrue(result["bmsb_valid"])
        self.assertAlmostEqual(result["bmsb_mid"], 0.10, delta=0.01)


if __name__ == "__main__":
    unittest.main()
