import unittest

import numpy as np

from engines.levels_engine import (
    LevelConfig, body_pivots, classify, compute_levels, levels_at, nearest_resistance, nearest_support,
)


def bars(closes, wick=0.002):
    c = np.asarray(closes, dtype=float)
    o = np.concatenate(([c[0]], c[:-1]))
    return {"open": o, "close": c, "high": np.maximum(o, c) * (1 + wick), "low": np.minimum(o, c) * (1 - wick),
            "timestamp": np.arange(len(c)) * 86_400_000.0, "volume": np.ones(len(c))}


def box(lo=100.0, hi=120.0, cycles=5, leg=12):
    """Price oscillating between lo and hi with sharp turns (clean body pivots)."""
    out = []
    for _ in range(cycles):
        out += list(np.linspace(lo, hi, leg)) + list(np.linspace(hi, lo, leg))
    return out


class EventRuleTests(unittest.TestCase):
    L = 100.0

    def test_breakout_needs_prior_close_at_or_below_buffer(self):
        self.assertEqual(classify(self.L, 2, 0, 102.0, 100.5, 102.5, 100.2, 0.01), ["breakout"])
        self.assertEqual(classify(self.L, 2, 0, 102.0, 101.5, 102.5, 101.0, 0.01), [])   # already above
        self.assertEqual(classify(self.L, 1, 0, 102.0, 100.5, 102.5, 100.2, 0.01), [])   # one high touch

    def test_breakdown(self):
        self.assertEqual(classify(self.L, 0, 2, 98.0, 99.5, 99.8, 97.5, 0.01), ["breakdown"])

    def test_bounce_and_rejection(self):
        self.assertEqual(classify(self.L, 0, 2, 101.5, 102.0, 102.2, 100.3, 0.01), ["bounce"])
        self.assertEqual(classify(self.L, 2, 0, 99.0, 98.0, 103.0, 98.5, 0.01), ["rejection"])


class LevelTests(unittest.TestCase):
    def test_pivots_are_confirmed_only_n_bars_later(self):
        c = [1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1, 1, 1]
        d = bars(c)
        piv = body_pivots(d["open"], d["close"], 3)
        high_j = [j for j, _, k in piv if k == "H"]
        self.assertIn(5, high_j)
        cfg = LevelConfig(n=3, min_touches=1, max_last=100)
        self.assertEqual(levels_at(8, piv, cfg), [])        # j+n = 8 is not < 8
        self.assertTrue(levels_at(9, piv, cfg))

    def test_box_produces_support_and_resistance(self):
        d = bars(box())
        out = compute_levels(d, LevelConfig(max_last=60))
        last = out[-1]
        prices = sorted(lv.price for lv in last.levels)
        self.assertTrue(any(abs(p / 100 - 1) < 0.02 for p in prices), prices)
        self.assertTrue(any(abs(p / 120 - 1) < 0.02 for p in prices), prices)
        self.assertAlmostEqual(nearest_support(last.sr_levels, 110), min(prices, key=lambda p: abs(p - 100)), delta=2)
        self.assertAlmostEqual(nearest_resistance(last.sr_levels, 110), min(prices, key=lambda p: abs(p - 120)), delta=2)

    def test_range_regime_starts_in_box_and_ends_on_breakout(self):
        # Fast legs keep the 20-point band within 8 x ATR(14), as the rule requires.
        closes = box(cycles=6, leg=6) + list(np.linspace(100, 119, 10)) + [126, 130, 134]
        out = compute_levels(bars(closes), LevelConfig(max_last=60))
        in_box = len(box(cycles=6, leg=6)) + 8
        self.assertTrue(out[in_box].range_state)
        self.assertFalse(out[-1].range_state)
        breakout_bar = next(i for i in range(in_box, len(closes)) if any(e["event"] == "breakout" for e in out[i].events))
        self.assertEqual(closes[breakout_bar], 126)

    def test_fakeout_counter_ignores_level_after_three_attempts(self):
        cfg = LevelConfig(max_last=60, cooldown=30)
        base = box(cycles=6)
        # Repeated pokes above 120 that close back inside: each is a breakout attempt.
        poke = [118, 118, 123, 118, 118]
        closes = base + poke * 5 + [118] * 3
        out = compute_levels(bars(closes), cfg)
        start = len(base)
        breakouts = [(i, e) for i in range(start, len(closes)) for e in out[i].events if e["event"] == "breakout"]
        self.assertEqual([e["attempt"] for _, e in breakouts], [1, 2, 3])

    def test_scale_invariance_for_btc_pair_prices(self):
        # The same shape at ALT/BTC prices (1e-6) must give the same events.
        closes = box(cycles=6) + list(np.linspace(100, 119, 10)) + [126, 130]
        usd = compute_levels(bars(closes), LevelConfig(max_last=60))
        btc = compute_levels(bars(np.array(closes) * 1e-6), LevelConfig(max_last=60))
        ev = lambda out: [[e["event"] for e in b.events] for b in out]
        self.assertEqual(ev(usd), ev(btc))
        self.assertEqual([b.range_state for b in usd], [b.range_state for b in btc])

    def test_wide_box_relative_to_atr_is_not_a_range(self):
        closes = box(cycles=6, leg=12)       # 20-point band, ATR ~2: band > 8 x ATR
        out = compute_levels(bars(closes), LevelConfig(max_last=60))
        self.assertFalse(any(b.range_state for b in out))

    def test_output_does_not_depend_on_start(self):
        closes = box(cycles=8) + [126, 130, 118, 104, 96]
        full = compute_levels(bars(closes), LevelConfig(max_last=60))
        late = compute_levels(bars(closes), LevelConfig(max_last=60), start=150)
        self.assertEqual([len(b.levels) for b in full[150:]], [len(b.levels) for b in late[150:]])


if __name__ == "__main__":
    unittest.main()
