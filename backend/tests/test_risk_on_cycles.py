"""Risk-on cycles study (docs/reviews/risk-on-cycles-study.md): run detection, censoring, survival, band."""
import unittest

import market_history as mh
from backtest.risk_on_cycles import (SUNDAY, WEDNESDAY, Market, Sample, age_bucket, band_breaks, breadth_bucket,
                                     detect_runs, how_ended, survival_row, verdict_median, verdict_share,
                                     weekly_band, wilson)


def series(pattern, first=100):
    """'H' = 60% Uptrend share, 'L' = 40%."""
    days = list(range(first, first + len(pattern)))
    return days, {d: (0.60 if c == "H" else 0.40) for d, c in zip(days, pattern)}


class RunDetectionTests(unittest.TestCase):
    def test_dips_of_four_days_stay_inside_and_five_end_the_run(self):
        days, share = series("LLLLL" "HHH" "LLLL" "HH" "LLLLL" "H")
        runs = detect_runs(days, share)
        on = [r for r in runs if r["type"] == "on"]
        self.assertEqual(on[0]["start"], 105)
        self.assertEqual(on[0]["end"], 114)               # first day of the 5-day stretch
        self.assertEqual(on[0]["length"], 9)              # 105..113, the 4-day dip included
        off = [r for r in runs if r["type"] == "off" and not r["first"]]
        self.assertEqual((off[0]["start"], off[0]["end"], off[0]["length"]), (114, 119, 5))

    def test_first_run_takes_the_first_days_type(self):
        days, share = series("HHLLLLLH")
        runs = detect_runs(days, share)
        self.assertEqual([(r["type"], r["first"]) for r in runs], [("on", True), ("off", False), ("on", False)])
        days, share = series("LLHH")
        runs = detect_runs(days, share)
        self.assertEqual([(r["type"], r["start"]) for r in runs], [("off", 100), ("on", 102)])   # no 5-day wait

    def test_one_day_risk_on_run(self):
        days, share = series("LLLLLHLLLLLL")
        on = [r for r in detect_runs(days, share) if r["type"] == "on"]
        self.assertEqual((on[0]["start"], on[0]["end"], on[0]["length"]), (105, 106, 1))

    def test_unconfirmed_end_is_censored_at_last_day_above(self):
        # Four days below at the end: the end needs a fifth.
        days, share = series("LLLLL" "HHHHHH" "LLLL")
        last = detect_runs(days, share)[-1]
        self.assertEqual((last["type"], last["end"]), ("on", None))
        self.assertEqual(last["min_length"], 6)          # last day at 55%+ minus start plus 1
        # A fifth day confirms it; the risk-off run after it is the censored one.
        days, share = series("LLLLL" "HHHHHH" "LLLLL")
        runs = detect_runs(days, share)
        self.assertEqual(runs[-2]["end"], 111)
        self.assertEqual((runs[-1]["type"], runs[-1]["end"], runs[-1]["min_length"]), ("off", None, 5))

    def test_cutting_the_sample_never_moves_a_start(self):
        days, share = series("LLLLLHHHLLHHHHLLLLLLHHLLLLLLLH")
        full = detect_runs(days, share)
        for cut in range(5, len(days)):
            part = detect_runs(days[:cut], share)
            starts = {(r["type"], r["start"]) for r in full}
            self.assertTrue({(r["type"], r["start"]) for r in part} <= starts)


class SurvivalTests(unittest.TestCase):
    def run_(self, n, censored=False, first=False):
        r = {"type": "on", "first": first, "censored": censored}
        r["min_length" if censored else "length"] = n
        return r

    def test_counts_with_censoring(self):
        rows = [self.run_(5), self.run_(12), self.run_(45), self.run_(80), self.run_(200, first=True),
                self.run_(25, censored=True), self.run_(70, censored=True)]
        r10 = survival_row(rows, 10)
        # At risk: 12, 45, 80, censored 25, censored 70 (the first run never counts).
        self.assertEqual(r10["at_risk"], 5)
        self.assertEqual(r10["left_out"], 1)               # censored at 25 < 40: outcome unknown
        self.assertEqual((r10["lasted"], r10["n"]), (3, 4))  # 45, 80, censored 70 lasted 40; 12 did not
        r45 = survival_row(rows, 45)
        self.assertEqual((r45["at_risk"], r45["lasted"], r45["n"], r45["left_out"]), (3, 1, 2, 1))
        self.assertTrue(r45["few"])
        r60 = survival_row(rows, 60, more=60)
        self.assertEqual((r60["at_risk"], r60["lasted"], r60["n"], r60["left_out"]), (2, 0, 1, 1))

    def test_ignores_risk_off_runs(self):
        rows = [{"type": "off", "first": False, "censored": False, "length": 90}]
        self.assertEqual(survival_row(rows, 10)["at_risk"], 0)


class BandTests(unittest.TestCase):
    def test_wednesday_band_equals_market_history(self):
        btc = {d: 100 + (d * 37 % 23) for d in range(18000, 18400)}
        rows = [[d, 50, .5, 0, 0, .5, 0, c] for d, c in btc.items()]
        self.assertEqual(weekly_band(btc, WEDNESDAY), mh.btc_band(rows))
        self.assertNotEqual(weekly_band(btc, SUNDAY), mh.btc_band(rows))

    def test_sunday_band_uses_completed_weeks(self):
        btc = {d: 100.0 for d in range(3, 3 + 7 * 30)}
        band = weekly_band(btc, SUNDAY)
        sunday21 = 3 + 7 * 20                        # the 21st Sunday close
        self.assertNotIn(sunday21, band)               # its own week is not completed until after the close
        self.assertAlmostEqual(band[sunday21 + 1][0], 100.0)

    def test_breaks_merge_gaps_of_five_days(self):
        btc = {d: 100.0 for d in range(0, 40)}
        band = {d: (90.0, 95.0) for d in btc}
        for d in (5, 11, 18, 19, 30):                  # 5->11: gap of 5 merges; 11->18: gap of 6 does not
            btc[d] = 80.0
        self.assertEqual(band_breaks(btc, band), [5, 18, 30])


class HowEndedTests(unittest.TestCase):
    def sample(self, below_days, last=200):
        share = {d: 0.6 for d in range(0, last + 1)}
        btc = {d: 100.0 for d in share}
        for d in below_days:
            btc[d] = 50.0
        m = Market(share, btc, {})
        m.band = {d: (80.0, 90.0) for d in share}
        return Sample(m, last)

    def test_cases(self):
        run = {"start": 50, "end": 80}
        self.assertEqual(how_ended(run, self.sample([70, 71])), {"case": "btc_first", "lead": 10})
        self.assertEqual(how_ended(run, self.sample([80])), {"case": "btc_first", "lead": 0})
        self.assertEqual(how_ended(run, self.sample(range(40, 81))), {"case": "already_below"})
        self.assertEqual(how_ended(run, self.sample([95])), {"case": "breadth_first", "lag": 15})
        self.assertEqual(how_ended(run, self.sample([150])), {"case": "no_break_60d"})
        self.assertEqual(how_ended(run, self.sample([], last=120)), {"case": "not_known_yet"})
        self.assertEqual(how_ended(run, self.sample([95], last=120)), {"case": "breadth_first", "lag": 15})


class SmallTests(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(breadth_bucket(0.8207), 8)
        self.assertEqual(breadth_bucket(0.8), 8)
        self.assertEqual(breadth_bucket(0.7999), 7)
        self.assertEqual(breadth_bucket(1.0), 9)
        self.assertEqual([age_bucket(a) for a in (0, 14, 15, 29, 30, 59, 60, 119, 120, 400)],
                         [0, 0, 1, 1, 2, 2, 3, 3, 4, 4])

    def test_wilson_and_verdicts(self):
        lo, hi = wilson(7, 12)
        self.assertAlmostEqual(lo, 0.354, places=2)
        self.assertAlmostEqual(hi, 0.782, places=2)
        ref = {"lo": 0.35, "hi": 0.78}
        self.assertEqual(verdict_share(4, 6, ref)["verdict"], "consistent")
        self.assertEqual(verdict_share(6, 6, ref)["verdict"], "did not hold out of sample")
        self.assertEqual(verdict_share(1, 2, ref)["verdict"], "consistent (n = 2, too few to read)")
        self.assertEqual(verdict_share(0, 0, ref)["verdict"], "no out-of-sample case")
        self.assertEqual(verdict_median([5.0], {"n": 9, "q25": -3, "q75": 8})["verdict"],
                         "consistent (n = 1, too few to read)")


if __name__ == "__main__":
    unittest.main()
