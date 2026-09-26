import unittest

from confluence import compute_confluence


def tf(regime, signal, heat=30):
    return {"regime": regime, "signal": signal, "heat": heat}


class ConfluenceTests(unittest.TestCase):
    def test_both_waiting_is_neither_agreement_nor_disagreement(self):
        out = compute_confluence(tf("MARKUP", "WAIT"), tf("MARKUP", "WAIT"))
        self.assertIsNone(out.signal_aligned)

    def test_full_agreement_scores_100_and_labels_keep_raw_thresholds(self):
        out = compute_confluence(tf("MARKUP", "LIGHT_LONG"), tf("MARKUP", "STRONG_LONG"))
        self.assertEqual(out.score, 100)
        self.assertIs(out.signal_aligned, True)
        self.assertEqual(out.label, "STRONG")
        # 40 + 30 = 70 raw points: MODERATE, although it is published as 78.
        out = compute_confluence(tf("MARKUP", "LIGHT_LONG", 50), tf("REACC", "LIGHT_LONG", 75))
        self.assertEqual((out.score, out.label), (78, "MODERATE"))

    def test_entry_against_exit_differs(self):
        out = compute_confluence(tf("MARKUP", "LIGHT_LONG"), tf("MARKUP", "TRIM"))
        self.assertIs(out.signal_aligned, False)


if __name__ == "__main__":
    unittest.main()
