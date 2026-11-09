"""The entry-rule switches of the rule-lab study (docs/reviews/rule-lab-study.md): each default leaves the
signal as it was, and each other value changes only the entry it names."""
import unittest
from unittest.mock import patch

import signal_synthesizer as ss
from signal_synthesizer import synthesize_signal

CONTEXT = dict(positioning={"funding_regime": "NEUTRAL", "oi_trend": "BUILDING"},
               sentiment={"fear_greed_value": 40}, stablecoin={"trend": "STABLE"})


def row(**over):
    base = dict(regime="MARKUP", confidence=70, zscore=.5, heat=30, heat_phase="Neutral",
                raw_signal="LIGHT_LONG", bmsb_valid=True, heat_direction=1)
    base.update(over)
    return base


def signal(r, consensus="RISK-ON", **ctx):
    return synthesize_signal(r, {"consensus": consensus}, **(ctx or CONTEXT)).signal


class RuleSwitchTests(unittest.TestCase):
    def test_defaults_are_the_rules_as_they_ran(self):
        self.assertEqual((ss.LIGHT_LONG_MIN, ss.MARKUP_ENTRY_Z_MAX, ss.MODERATE_MIXED_OK, ss.MARKUP_FADE_BLOCK,
                          ss.MARKUP_STRONG_OK, ss.CROWDED_BLOWOFF_OK), (0.40, None, True, False, True, True))

    def test_light_long_minimum(self):
        thin = dict(sentiment={"fear_greed_value": 80}, stablecoin={"trend": "CONTRACTING"})
        self.assertEqual(signal(row(), "MIXED", **thin), "LIGHT_LONG")
        with patch.object(ss, "LIGHT_LONG_MIN", 0.99):
            self.assertEqual(signal(row(), "MIXED", **thin), "WAIT")

    def test_late_entry_cap_covers_every_uptrend_path(self):
        late = row(zscore=1.4)
        self.assertEqual(signal(late), "LIGHT_LONG")                       # strong score: the downgrade path
        thin = dict(sentiment={"fear_greed_value": 80}, stablecoin={"trend": "CONTRACTING"})
        self.assertEqual(signal(late, "MIXED", **thin), "LIGHT_LONG")      # thin score: the plain path
        with patch.object(ss, "MARKUP_ENTRY_Z_MAX", 1.0):
            self.assertEqual(signal(late), "WAIT")
            self.assertEqual(signal(late, "MIXED", **thin), "WAIT")
            self.assertEqual(signal(row(zscore=.5), "MIXED", **thin), "LIGHT_LONG")   # below the cap: unchanged

    def test_plain_entry_can_require_risk_on(self):
        thin = dict(sentiment={"fear_greed_value": 80}, stablecoin={"trend": "CONTRACTING"})
        with patch.object(ss, "MODERATE_MIXED_OK", False):
            self.assertEqual(signal(row(), "MIXED", **thin), "WAIT")
            self.assertEqual(signal(row(), "RISK-ON", **thin), "LIGHT_LONG")

    def test_fading_heat_can_block_uptrend_entries_only(self):
        fading = row(heat_phase="Fading")
        self.assertEqual(signal(fading), "LIGHT_LONG")
        with patch.object(ss, "MARKUP_FADE_BLOCK", True):
            self.assertEqual(signal(fading), "WAIT")
            self.assertEqual(signal(row()), "LIGHT_LONG")

    def test_uptrend_strong_long_can_be_light_while_other_regimes_keep_it(self):
        with patch.object(ss, "STRONG_LONG_CAP", False):
            self.assertEqual(signal(row()), "STRONG_LONG")
            with patch.object(ss, "MARKUP_STRONG_OK", False):
                self.assertEqual(signal(row()), "LIGHT_LONG")
                self.assertEqual(signal(row(regime="ACCUM", zscore=-.5)), "STRONG_LONG")

    def test_crowded_funding_entry_above_blowoff_changes_only_with_a_switch(self):
        crowded = dict(CONTEXT, positioning={"funding_regime": "CROWDED_LONG", "oi_trend": "BUILDING"})
        high = row(zscore=2.6)
        self.assertEqual(signal(high), "WAIT")                             # neutral funding: stopped at the blow-off z
        self.assertEqual(signal(high, **crowded), "LIGHT_LONG")            # crowded funding: as it has always run
        with patch.object(ss, "CROWDED_BLOWOFF_OK", False):
            self.assertEqual(signal(high, **crowded), "WAIT")
            self.assertEqual(signal(row(zscore=1.4), **crowded), "LIGHT_LONG")
        with patch.object(ss, "MARKUP_ENTRY_Z_MAX", 1.0):
            self.assertEqual(signal(row(zscore=1.4), **crowded), "WAIT")


if __name__ == "__main__":
    unittest.main()
