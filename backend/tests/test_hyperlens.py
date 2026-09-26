import time
import unittest
from collections import deque
from unittest import mock

import hl_intelligence as hl


def _state(av, *positions):
    return {"marginSummary": {"accountValue": str(av)}, "assetPositions": [{"position": p} for p in positions]}


class HyperLensTests(unittest.TestCase):
    def test_liq_distance_is_from_the_mark_and_empty_without_a_liq_price(self):
        cross = {"coin": "ETH", "szi": "10", "entryPx": "2000", "positionValue": "25000", "leverage": {"type": "cross", "value": 3}}
        near = dict(cross, liquidationPx="2250")                        # mark 2500, liq 10% below it
        a, b = hl._parse_positions(_state(1e6, cross, near))
        self.assertIsNone(a.liq_distance_pct)
        self.assertEqual(b.liq_distance_pct, 10.0)

    def test_roi_is_dropped_when_the_month_started_near_empty(self):
        self.assertIsNone(hl._meaningful_roi(50_000, 50_000))           # ROI = PnL/100: began with ~$100
        self.assertEqual(hl._meaningful_roi(50_000, 100.0), 100.0)       # began with $50K

    def test_symbol_positions_use_the_consensus_account_filter(self):
        pos = {"coin": "ETH", "szi": "1", "entryPx": "2000", "leverage": {"type": "cross", "value": 2}}
        roster = [hl.TrackedWallet(address="0xbig", account_value=1e6), hl.TrackedWallet(address="0xsmall", account_value=20_000)]
        now = time.time()
        snaps = {w.address: deque([hl._snapshot_from_state(_state(w.account_value, pos), ts=now)]) for w in roster}
        with mock.patch.object(hl, "_roster", roster), mock.patch.object(hl, "_snapshots", snaps), \
                mock.patch.object(hl, "_roster_money_printers", []), mock.patch.object(hl, "_roster_smart_money", []), \
                mock.patch.object(hl, "_consensus", {}), mock.patch.object(hl, "_mp_book", {}):
            hl._recompute_consensus()
            self.assertEqual(hl._consensus["ETH"].long_count, 1)
            self.assertEqual([p["address"] for p in hl.get_symbol_positions("ETH")], ["0xbig"])
            self.assertEqual((hl._fresh_wallets, hl._consensus_wallets), (2, 1))


if __name__ == "__main__":
    unittest.main()
