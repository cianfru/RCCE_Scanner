import unittest

import numpy as np

from engines.patterns_engine import (
    CODES, Pattern, PatternConfig, breaks_by_bar, chart_patterns, detect_patterns, pack,
)


def series(points, leg=8):
    """Closes through the given turning points, `leg` bars per segment; open = previous close."""
    closes = [points[0]]
    for a, b in zip(points, points[1:]):
        closes += list(np.linspace(a, b, leg + 1)[1:])
    c = np.array(closes, dtype=float)
    o = np.concatenate(([c[0]], c[:-1]))
    return {"open": o, "close": c, "high": np.maximum(o, c) * 1.001, "low": np.minimum(o, c) * 0.999,
            "timestamp": np.arange(len(c)) * 86_400_000.0, "volume": np.ones(len(c))}


def with_tail(points, tail, leg=8):
    return series(points + tail, leg)


def confirmed(d, cfg=PatternConfig()):
    return sorted({p.code for p in detect_patterns(d, cfg) if p.status == "confirmed"})


class PatternTypeTests(unittest.TestCase):
    def test_rectangle_breakout_and_breakdown(self):
        box = [100, 115, 100, 115, 100, 115, 100, 112]
        self.assertIn(CODES["rect_up"], confirmed(with_tail(box, [125])))
        self.assertIn(CODES["rect_down"], confirmed(with_tail(box, [90])))

    def test_rectangle_too_flat_is_not_a_rectangle(self):
        flat = [100, 103, 100, 103, 100, 103, 100, 102, 110]      # 3% box, spec needs 5-60%
        self.assertNotIn(CODES["rect_up"], confirmed(series(flat)))

    def test_ascending_and_descending_triangles(self):
        asc = [95, 110, 100, 110, 104, 110, 107, 118]
        self.assertIn(CODES["asc"], confirmed(series(asc)))
        desc = [115, 100, 110, 100, 106, 100, 103, 92]
        self.assertIn(CODES["desc"], confirmed(series(desc)))

    def test_flat_lows_are_not_an_ascending_triangle(self):
        not_rising = [95, 110, 95, 110, 95, 110, 100, 118]
        self.assertNotIn(CODES["asc"], confirmed(series(not_rising)))

    def test_head_and_shoulders_and_inverse(self):
        hs = [100, 110, 100, 122, 100, 110, 104, 92]
        self.assertIn(CODES["hs"], confirmed(series(hs)))
        ihs = [110, 100, 110, 88, 110, 100, 106, 118]
        self.assertIn(CODES["ihs"], confirmed(series(ihs)))

    def test_head_not_above_shoulders_is_not_hs(self):
        no_head = [100, 110, 100, 112, 100, 110, 104, 92]         # head only ~2% above
        self.assertNotIn(CODES["hs"], confirmed(series(no_head)))

    def test_hs_fails_when_price_clears_the_head(self):
        d = series([100, 110, 100, 122, 100, 110, 104, 130])
        hs = [p for p in detect_patterns(d) if p.kind == "hs"]
        self.assertTrue(hs)
        self.assertTrue(all(p.status == "failed" for p in hs))

    def test_cup_and_handle(self):
        rim, bottom = 100.0, 78.0
        cup = list(rim - (rim - bottom) * np.sin(np.linspace(0, np.pi, 41)))   # rounded
        pre = list(np.linspace(90, rim, 12))[:-1]
        handle = list(np.linspace(rim, 95, 5))[1:] + list(np.linspace(95, 99, 4))[1:]
        c = np.array(pre + cup + handle + [104, 106])
        d = series(list(c), leg=1)
        self.assertIn(CODES["cup"], confirmed(d))

    def test_v_shaped_cup_is_not_rounded(self):
        rim, bottom = 100.0, 78.0
        v = list(np.linspace(rim, bottom, 21)) + list(np.linspace(bottom, rim, 21))[1:]
        pre = list(np.linspace(90, rim, 12))[:-1]
        handle = list(np.linspace(rim, 95, 5))[1:] + list(np.linspace(95, 99, 4))[1:]
        d = series(pre + v + handle + [104, 106], leg=1)
        self.assertNotIn(CODES["cup"], confirmed(d))


class LifecycleTests(unittest.TestCase):
    def test_patterns_are_causal(self):
        # Truncating the future never changes what was knowable before it.
        d = series([100, 115, 100, 115, 100, 115, 100, 112, 125, 118, 130])
        full = detect_patterns(d)
        cut = {k: v[:70] for k, v in d.items()}
        early = detect_patterns(cut)
        formed_full = sorted((p.kind, p.formed) for p in full if p.formed < 70)
        formed_cut = sorted((p.kind, p.formed) for p in early)
        self.assertEqual(formed_full, formed_cut)

    def test_forming_before_break(self):
        box = series([100, 115, 100, 115, 100, 115, 100, 110])
        pats = detect_patterns(box)
        self.assertTrue(any(p.kind == "rect" and p.status == "forming" for p in pats))

    def test_formed_after_last_pivot_confirmation(self):
        d = series([100, 110, 100, 122, 100, 110, 104, 92])
        for p in detect_patterns(d):
            self.assertGreater(p.formed, p.last_pivot + PatternConfig().n)
            if p.resolved is not None:
                self.assertGreaterEqual(p.resolved, p.formed)

    def test_combined_codes(self):
        pts = [Pattern("ihs", 1, 10, 9, [], 0, 5, 6, status="confirmed", resolved=20, code=11),
               Pattern("rect", 0, 10, 9, [], 0, 5, 6, status="confirmed", resolved=20, code=10),
               Pattern("hs", -1, 10, 11, [], 0, 5, 6, status="failed", resolved=20)]
        self.assertEqual(breaks_by_bar(pts), {20: [11, 10]})
        self.assertEqual(pack([11, 10]), 11010)
        self.assertEqual(pack([13]), 13)


class ChartPatternTests(unittest.TestCase):
    def test_chart_patterns_carry_times_levels_and_track_record(self):
        d = with_tail([100, 115, 100, 115, 100, 115, 100, 112], [125])
        pats = chart_patterns(d)
        rect = [p for p in pats if p["kind"] == "rect" and p["status"] == "confirmed"]
        self.assertTrue(rect)
        p = rect[0]
        self.assertEqual(p["direction"], 1)
        self.assertEqual(len(p["levels"]), 2)
        self.assertLess(p["start"], p["end"])
        self.assertIn("upside break", p["track_record"])
        times = [a["time"] for a in p["anchors"]]
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(isinstance(t, int) for t in times))

    def test_old_and_expired_patterns_are_left_out(self):
        d = with_tail([100, 115, 100, 115, 100, 115, 100, 112], [125] + [126] * 40, leg=8)
        self.assertEqual(chart_patterns(d, recent=20), [])
        self.assertFalse(any(p["status"] == "expired" for p in chart_patterns(d)))


if __name__ == "__main__":
    unittest.main()
