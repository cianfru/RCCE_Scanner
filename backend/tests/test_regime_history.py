import tempfile
import unittest
from pathlib import Path
import numpy as np
from data_fetcher import OHLCVStore
from engines.rcce_engine import _resolve_regime_with_persistence


def candles(start, end, value=1):
    ts = np.arange(start, end, dtype=float)
    return {k: ts.copy() if k == 'timestamp' else np.full(len(ts), value, dtype=float)
            for k in ('timestamp', 'open', 'high', 'low', 'close', 'volume')}


class HistoryTests(unittest.TestCase):
    def test_backfill_same_latest_retains_older_and_revises_overlap(self):
        store = OHLCVStore()
        store.update('VVV/USDT', '1d', candles(300, 600))
        self.assertTrue(store.needs_full_fetch('VVV/USDT', '1d'))
        data = store.update('VVV/USDT', '1d', candles(0, 600, 2), full_fetch_target=600)
        self.assertEqual(len(data['close']), 600)
        np.testing.assert_array_equal(data['timestamp'], np.arange(600))
        self.assertTrue(np.all(data['close'] == 2))
        self.assertFalse(store.needs_full_fetch('VVV/USDT', '1d'))
        data = store.update('VVV/USDT', '1d', candles(599, 601, 3))
        self.assertEqual(len(data['close']), 600)
        self.assertEqual(data['timestamp'][0], 1)
        self.assertEqual(data['close'][-2], 3)

    def test_short_listing_full_request_is_remembered_across_restart(self):
        store = OHLCVStore()
        store.update('SHORT/USDC', '1d', candles(0, 80, 20), full_fetch_target=600)
        self.assertFalse(store.needs_full_fetch('SHORT/USDC', '1d'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cache.pkl'
            self.assertTrue(store.save_to_disk(path, force=True))
            restored = OHLCVStore()
            self.assertTrue(restored.load_from_disk(path))
            self.assertFalse(restored.needs_full_fetch('SHORT/USDC', '1d'))
        store.invalidate('SHORT/USDC', '1d')
        self.assertTrue(store.needs_full_fetch('SHORT/USDC', '1d'))

    def test_empty_backfill_does_not_mark_success(self):
        store = OHLCVStore()
        store.update('VVV/USDT', '1d', candles(0, 300))
        store.update('VVV/USDT', '1d', candles(0, 0), full_fetch_target=600)
        self.assertTrue(store.needs_full_fetch('VVV/USDT', '1d'))


class TransitionTests(unittest.TestCase):
    def probabilities(self, candidates):
        result = np.full((6, len(candidates)), .01)
        for i, regime in enumerate(candidates): result[regime, i] = .95
        return result

    def bearish_then_bullish(self, bull_regimes, bull_p=0.45, bear_p=0.20):
        """MARKDOWN bar 0, then bullish-family bars below the dominance
        thresholds so the family-exit persistence path (not the override) is
        exercised."""
        n = len(bull_regimes) + 1
        p = np.full((6, n), 0.01)
        p[3, 0] = 0.95
        for i, reg in enumerate(bull_regimes, start=1):
            p[reg, i] = bull_p
            p[3, i] = bear_p
        return p

    def test_dominant_bullish_releases_bearish_latch_after_two_bars(self):
        # The model gives the held MARKDOWN 0.01 while REACC dominates (0.95).
        # A single dominant bar must NOT release (that fires on dead-cat
        # bounces); two consecutive dominant bars release without waiting the
        # full MIN_REGIME_BARS.
        regimes, _, pending = _resolve_regime_with_persistence(self.probabilities([3, 2]), True)
        self.assertEqual(regimes[-1], 3)
        self.assertEqual(pending['candidate'], 'REACC')
        regimes, _, pending = _resolve_regime_with_persistence(self.probabilities([3, 2, 2]), True)
        self.assertEqual(regimes[-1], 2)
        self.assertIsNone(pending)

    def test_interrupted_dominance_streak_resets(self):
        # Dominant, then a bearish bar, then dominant again: the streak must
        # restart, so the label is still held after the second dominant bar.
        regimes, _, _ = _resolve_regime_with_persistence(self.probabilities([3, 2, 3, 2]), True)
        self.assertEqual(regimes[-1], 3)

    def test_family_persistence_when_not_dominant(self):
        # Rotating bullish family (MARKUP<->REACC), each below the dominance
        # threshold, must still persist MIN_REGIME_BARS before the bearish label
        # is released -- but the count now spans the family, not one sub-regime.
        p = self.bearish_then_bullish([0, 2, 0, 2, 0])   # 5 bullish bars after MARKDOWN
        # 4 bullish bars: not yet released (was previously stuck forever here
        # because MARKUP/REACC never repeated 5x in a row).
        regimes4, _, pending4 = _resolve_regime_with_persistence(p[:, :5], True)
        self.assertEqual(regimes4[-1], 3)
        self.assertEqual(pending4['observed_bars'], 4)
        # 5th bullish-family bar confirms the exit.
        regimes5, _, pending5 = _resolve_regime_with_persistence(p, True)
        self.assertIn(regimes5[-1], (0, 2))
        self.assertNotEqual(regimes5[-1], 3)

    def test_bearish_entry_still_requires_persistence(self):
        # Guard the safety intent: a bullish regime does not flip to MARKDOWN on
        # a brief bearish blip (needs MIN_REGIME_BARS).
        regimes, _, _ = _resolve_regime_with_persistence(self.probabilities([0, 3, 3, 0, 0]), True)
        self.assertEqual(regimes[-1], 0)

    def test_bullish_family_hysteresis_respected(self):
        # Within the bullish family, a marginally-higher candidate does not win
        # without clearing the hysteresis ratio.
        p = self.probabilities([0, 0]); p[0, 1] = .45; p[2, 1] = .5
        _, _, pending = _resolve_regime_with_persistence(p, True)
        self.assertIsNone(pending)
