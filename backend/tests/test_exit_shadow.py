import tempfile
import unittest
from pathlib import Path

from exit_shadow import ExitShadow


def rows(**signals_prices):
    return [{"symbol": s, "signal": sig, "price": p} for s, (sig, p) in signals_prices.items()]


class ExitShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "exit_shadow.json"
        self.sh = ExitShadow(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def day(self, n):
        return f"2026-10-{n:02d}"

    def test_same_entries_different_exits(self):
        self.sh.process_day(self.day(1), rows(X=("STRONG_LONG", 100)))
        self.sh.process_day(self.day(2), rows(X=("TRIM", 110)))
        cur = self.sh.state["books"]["current"]
        hold = self.sh.state["books"]["hold60"]
        self.assertEqual(cur["closed"][0]["reason"], "TRIM")
        self.assertAlmostEqual(cur["closed"][0]["return_pct"], (110 * 0.999 / (100 * 1.001) - 1) * 100, places=2)
        self.assertIn("X", hold["open"])                 # hold60 ignores TRIM

    def test_stops_8_and_12(self):
        self.sh.process_day(self.day(1), rows(X=("LIGHT_LONG", 100)))
        self.sh.process_day(self.day(2), rows(X=("WAIT", 91)))
        self.assertEqual(self.sh.state["books"]["current"]["closed"][0]["reason"], "STOP_8")
        self.assertIn("X", self.sh.state["books"]["hold60"]["open"])
        self.sh.process_day(self.day(3), rows(X=("WAIT", 87)))
        self.assertEqual(self.sh.state["books"]["hold60"]["closed"][0]["reason"], "STOP_12")

    def test_risk_off_closes_everything_in_current_only(self):
        self.sh.process_day(self.day(1), rows(X=("STRONG_LONG", 100), Y=("LIGHT_LONG", 50)))
        self.sh.process_day(self.day(2), rows(X=("WAIT", 101), Y=("RISK_OFF", 50)))
        self.assertEqual(self.sh.state["books"]["current"]["open"], {})
        self.assertEqual(set(self.sh.state["books"]["hold60"]["open"]), {"X", "Y"})

    def test_hold60_time_exit_and_decay(self):
        self.sh.process_day(self.day(1), rows(X=("STRONG_LONG", 100)))
        for d in range(2, 30):
            self.sh.process_day(f"2026-10-{d:02d}", rows(X=("WAIT", 100)))
        self.assertEqual(self.sh.state["books"]["current"]["closed"][0]["reason"], "DECAY")
        for d in range(1, 34):
            self.sh.process_day(f"2026-11-{d:02d}" if d <= 30 else f"2026-12-{d - 30:02d}", rows(X=("WAIT", 100)))
        closed = self.sh.state["books"]["hold60"]["closed"]
        self.assertEqual(closed[0]["reason"], "HOLD_60")
        self.assertEqual(closed[0]["days"], 60)

    def test_idempotent_per_day_and_persisted(self):
        self.assertTrue(self.sh.process_day(self.day(1), rows(X=("STRONG_LONG", 100))))
        self.assertFalse(self.sh.process_day(self.day(1), rows(X=("TRIM", 50))))
        again = ExitShadow(self.path)
        self.assertEqual(again.state["last_date"], self.day(1))
        self.assertIn("X", again.state["books"]["current"]["open"])

    def test_summary(self):
        self.sh.process_day(self.day(1), rows(X=("STRONG_LONG", 100)))
        self.sh.process_day(self.day(2), rows(X=("NO_LONG", 90)))
        s = self.sh.summary()
        self.assertEqual(s["policies"]["current"]["closed"], 1)
        self.assertEqual(s["policies"]["hold60"]["open"], 1)
        self.assertLess(s["policies"]["current"]["mean_return_pct"], 0)


if __name__ == "__main__":
    unittest.main()
