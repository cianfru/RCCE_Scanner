import unittest

from backtest.sector_tilt_study import ranks, tilt


class TiltTests(unittest.TestCase):
    def setUp(self):
        day = 20_000
        self.day = day
        self.strength = {s: {day: v} for s, v in
                         [("AI", 0.3), ("DeFi", 0.2), ("Memes", 0.1), ("L1", 0.0), ("L2", -0.1), ("Payments", -0.2)]}
        self.ts = (day + 1) * 86_400_000 + 4 * 3_600_000      # a 4h bar the day after the ranked close

    def test_thirds(self):
        top, bottom = ranks(self.strength, self.day)
        self.assertEqual((top, bottom), ({"AI", "DeFi"}, {"L2", "Payments"}))

    def test_only_new_entries_are_filtered(self):
        sector_of = {"FET/USDT": "AI", "XLM/USDT": "Payments", "BTC/USDT": "Majors", "SOL/USDT": "L1"}
        rows = [{"symbol": s, "signal": sig, "timestamp": self.ts} for s, sig in
                [("FET/USDT", "STRONG_LONG"), ("XLM/USDT", "LIGHT_LONG"), ("XLM/USDT", "TRIM"),
                 ("BTC/USDT", "LIGHT_LONG"), ("SOL/USDT", "LIGHT_LONG")]]
        t1 = [r["signal"] for r in tilt(rows, sector_of, self.strength, "T1")]
        t2 = [r["signal"] for r in tilt(rows, sector_of, self.strength, "T2")]
        self.assertEqual(t1, ["STRONG_LONG", "SECTOR_SKIP", "TRIM", "LIGHT_LONG", "LIGHT_LONG"])
        self.assertEqual(t2, ["STRONG_LONG", "SECTOR_SKIP", "TRIM", "LIGHT_LONG", "SECTOR_SKIP"])
        self.assertEqual([r["signal"] for r in tilt(rows, sector_of, self.strength, "B")],
                         [r["signal"] for r in rows])


if __name__ == "__main__":
    unittest.main()
