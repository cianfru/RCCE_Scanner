import unittest

from scanner import compute_consensus


class ConsensusTests(unittest.TestCase):
    def test_markets_without_history_are_not_counted(self):
        # 17 in Uptrend, 6 measured Flat, 10 with no candles: 17/23 = 74%, not 17/33 = 52%.
        rows = ([{"regime": "MARKUP", "history_bars": 500}] * 17
                + [{"regime": "FLAT", "history_bars": 500}] * 6
                + [{"regime": "FLAT", "history_bars": 0}] * 10)
        c = compute_consensus(rows)
        self.assertEqual(c["consensus"], "RISK-ON")
        self.assertEqual(c["counts"]["total"], 23)
        self.assertEqual(c["strength"], round(17 / 23 * 100, 1))

    def test_rows_without_the_field_still_count(self):
        c = compute_consensus([{"regime": "MARKDOWN"}] * 3 + [{"regime": "MARKUP"}])
        self.assertEqual(c["consensus"], "RISK-OFF")
        self.assertEqual(c["counts"]["total"], 4)

    def test_no_measured_market_reads_mixed(self):
        c = compute_consensus([{"regime": "FLAT", "history_bars": 0}] * 5)
        self.assertEqual(c, {"consensus": "MIXED", "strength": 0.0, "counts": {}})


if __name__ == "__main__":
    unittest.main()
