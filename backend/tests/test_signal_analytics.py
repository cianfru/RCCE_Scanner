import asyncio
import json
import unittest

from signal_analytics import SignalAnalytics, _is_win


def row(signal, outcome, met, conditions_met=9, regime="MARKUP", conditions_total=11):
    ctx = {"synthesis": {"conditions_detail": [
        {"name": name, "met": value} for name, value in met.items()]}}
    return {"signal": signal, "regime": regime, "conditions_met": conditions_met,
            "conditions_total": conditions_total,
            "outcome_7d_pct": outcome, "context": json.dumps(ctx)}


def analytics(rows):
    a = SignalAnalytics(signal_log=None)

    async def fetch(timeframe, extra_where="", extra_params=()):
        return rows

    a._fetch_rows_with_outcomes = fetch
    return a


class IsWinTests(unittest.TestCase):
    def test_short_signals_win_when_price_falls(self):
        for sig in ("LIGHT_SHORT", "STRONG_SHORT"):
            with self.subTest(sig=sig):
                self.assertTrue(_is_win(sig, -4.0))
                self.assertFalse(_is_win(sig, 3.0))

    def test_long_and_exit_directions_unchanged(self):
        self.assertTrue(_is_win("LIGHT_LONG", 2.0))
        self.assertFalse(_is_win("LIGHT_LONG", -2.0))
        self.assertTrue(_is_win("TRIM", -2.0))
        self.assertFalse(_is_win("WAIT", 5.0))

    def test_regime_scorecard_scores_shorts(self):
        rows = [row("LIGHT_SHORT", -5.0, {})] * 4 + [row("LIGHT_SHORT", -1.0, {})] * 4 \
            + [row("LIGHT_SHORT", 2.0, {})] * 4
        out = asyncio.run(analytics(rows).regime_stratified_scorecard())
        self.assertAlmostEqual(out["LIGHT_SHORT"][0]["win_rate"], 66.7)

    def test_regime_scorecard_drops_tiny_cells(self):
        rows = [row("TRIM", -5.0, {}, regime="ACCUM")] * 3
        out = asyncio.run(analytics(rows).regime_stratified_scorecard())
        self.assertNotIn("TRIM", out)


class LongOnlyAverageTests(unittest.TestCase):
    # A falling price after an exit or short is a good outcome for that signal;
    # averaging it with long returns would drag the long numbers down.
    ROWS = [
        row("LIGHT_LONG", 6.0, {"heat_ok": True}, conditions_met=11),
        row("STRONG_LONG", 4.0, {"heat_ok": True}, conditions_met=9, conditions_total=9),
        row("LIGHT_LONG", -2.0, {"heat_ok": False}, conditions_met=5),
        row("NO_LONG", -10.0, {"heat_ok": True}, conditions_met=5),
        row("LIGHT_SHORT", -8.0, {"heat_ok": False}, conditions_met=5),
    ]

    def test_condition_edge_uses_long_entries_only(self):
        out = asyncio.run(analytics(self.ROWS).condition_predictive_value())
        heat = next(c for c in out if c["name"] == "heat_ok")
        self.assertEqual((heat["true_count"], heat["false_count"]), (2, 1))
        self.assertEqual(heat["avg_7d_true"], 5.0)
        self.assertEqual(heat["avg_7d_false"], -2.0)
        self.assertEqual(heat["edge"], 7.0)
        self.assertEqual(heat["win_rate_true"], 100.0)

    def test_confluence_buckets_use_long_entries_only(self):
        out = asyncio.run(analytics(self.ROWS).confluence_stratified_scorecard())
        by_bucket = {b["bucket"]: b for b in out}
        # 11/11 and 9/9 both mean every check was met.
        self.assertEqual(by_bucket["100%"]["count"], 2)
        self.assertEqual(by_bucket["100%"]["avg_7d"], 5.0)
        low = by_bucket["<60%"]
        self.assertEqual(low["count"], 1)
        self.assertEqual(low["avg_7d"], -2.0)
        self.assertEqual(low["win_rate"], 0.0)
        self.assertEqual(set(low["signals"]), {"LIGHT_LONG"})

    def test_conviction_buckets_skip_rows_without_a_total(self):
        rows = [row("LIGHT_LONG", 3.0, {}, conditions_total=None)]
        out = asyncio.run(analytics(rows).confluence_stratified_scorecard())
        self.assertTrue(all(b["count"] == 0 for b in out))


if __name__ == "__main__":
    unittest.main()
