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

    def test_four_candidates_pending_fifth_confirms(self):
        p = self.probabilities([3, 2, 2, 2, 2])
        regimes, _, pending = _resolve_regime_with_persistence(p, True)
        self.assertEqual(regimes[-1], 3)
        self.assertEqual(pending['candidate'], 'REACC')
        self.assertEqual(pending['observed_bars'], 4)
        regimes, _, pending = _resolve_regime_with_persistence(self.probabilities([3, 2, 2, 2, 2, 2]), True)
        self.assertEqual(regimes[-1], 2)
        self.assertIsNone(pending)
        self.assertEqual(len(_resolve_regime_with_persistence(p)), 2)

    def test_interrupted_candidate_resets_and_hysteresis_is_respected(self):
        _, _, pending = _resolve_regime_with_persistence(self.probabilities([3, 2, 2, 3, 2]), True)
        self.assertEqual(pending['observed_bars'], 1)
        p = self.probabilities([0, 0]); p[0, 1] = .45; p[2, 1] = .5
        _, _, pending = _resolve_regime_with_persistence(p, True)
        self.assertIsNone(pending)
