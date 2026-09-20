import math
import unittest

from engines.range_forecast import ATR_N, WINDOW, forecast


def series(ranges, base=100.0):
    """Build OHLC arrays whose per-bar true range equals `ranges`.

    Every close is `base`, so high/low straddle it symmetrically and
    TR == high - low (the gap terms are the smaller of the three).
    """
    high, low, close = [], [], []
    for r in ranges:
        high.append(base + r / 2)
        low.append(base - r / 2)
        close.append(base)
    return high, low, close


class RangeForecastTests(unittest.TestCase):
    def test_returns_none_on_short_history(self):
        h, l, c = series([1.0] * (WINDOW + 1))
        self.assertIsNone(forecast(h, l, c, "4h"))

    def test_returns_none_on_unknown_timeframe(self):
        h, l, c = series([1.0] * (WINDOW + 50))
        self.assertIsNone(forecast(h, l, c, "1h"))

    def test_returns_none_on_zero_volatility(self):
        h, l, c = series([0.0] * (WINDOW + 50))
        self.assertIsNone(forecast(h, l, c, "4h"))

    def test_quiet_current_bar_lands_in_lowest_bucket(self):
        # 99 wide bars then one very narrow one: percentile ~1st -> VERY LOW.
        ranges = [5.0] * (WINDOW + 49) + [0.1]
        out = forecast(*series(ranges), "4h")
        self.assertEqual(out["label"], "VERY LOW")
        self.assertAlmostEqual(out["probability"], 0.111)
        self.assertLess(out["current_percentile"], 25.0)

    def test_violent_current_bar_lands_in_highest_bucket(self):
        ranges = [1.0] * (WINDOW + 49) + [50.0]
        out = forecast(*series(ranges), "4h")
        self.assertEqual(out["label"], "HIGH")
        self.assertAlmostEqual(out["probability"], 0.561)
        self.assertEqual(out["current_percentile"], 100.0)

    def test_expected_range_pct_follows_atr_and_multiplier(self):
        # Flat 2.0-wide bars on a 100 close: ATR14 == 2.0, so the expected
        # range is atr_mult * 2 / 100 * 100 == 2 * atr_mult percent.
        out = forecast(*series([2.0] * (WINDOW + 50)), "4h")
        self.assertAlmostEqual(out["expected_range_pct"], round(out["atr_mult"] * 2.0, 2))

    def test_only_trailing_window_is_used_no_lookahead(self):
        # Prepending ancient bars outside the 100-bar window must not move it.
        tail = [1.0] * (WINDOW + 20) + [4.0]
        a = forecast(*series(tail), "1d")
        b = forecast(*series([99.0] * 200 + tail), "1d")
        self.assertEqual(a, b)

    def test_timeframes_are_calibrated_separately(self):
        ranges = [1.0] * (WINDOW + 49) + [50.0]
        four_h = forecast(*series(ranges), "4h")
        daily = forecast(*series(ranges), "1d")
        self.assertEqual(four_h["label"], daily["label"])
        self.assertNotAlmostEqual(four_h["probability"], daily["probability"])

    def test_atr_uses_the_last_n_bars_only(self):
        # A calm run ending in 14 wide bars: ATR reflects the wide tail.
        ranges = [1.0] * (WINDOW + 40) + [10.0] * ATR_N
        out = forecast(*series(ranges), "4h")
        self.assertTrue(math.isclose(out["expected_range_pct"], round(out["atr_mult"] * 10.0, 2)))


if __name__ == "__main__":
    unittest.main()
