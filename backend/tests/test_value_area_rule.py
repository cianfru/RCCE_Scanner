"""The 80% rule study: event detection (known at the time) and the outcome of each event."""
import unittest

import numpy as np

from research import value_area_rule as V

DAY = V.DAY_MS
T0 = 1_788_739_200_000            # Monday 2026-09-07 00:00 UTC
VAH, VAL = 110.0, 100.0


def day(prices, start=T0, wick=0.0):
    """One UTC day of 5-minute candles from a price per half hour (48 values; each fills its six candles)."""
    closes = np.repeat(np.asarray(prices, dtype=float), 6)
    ts = start + np.arange(len(closes)) * V.BAR_MS
    return {"start": start, "ts": ts, "open": closes.copy(), "high": closes + wick, "low": closes - wick, "close": closes}


def path(*legs):
    """Half-hour prices from (count, price) legs, padded with the last price to 48."""
    out = [p for n, p in legs for _ in range(n)]
    return out + [out[-1]] * (48 - len(out))


class EventTests(unittest.TestCase):
    def test_open_above_then_two_closes_inside_is_a_rule_event(self):
        d = day(path((3, 115), (1, 112), (2, 108)))
        ev = V.find_event(d, VAH, VAL)
        self.assertEqual((ev["kind"], ev["state"], ev["side"], ev["bucket"]), ("rule", "event", 1, 5))
        self.assertEqual(ev["t"], T0 + 6 * V.HALF_HOUR_MS)           # known at the close of the second bar inside
        self.assertEqual((ev["entry"], ev["extreme"]), (108.0, 115.0))

    def test_one_close_inside_then_out_again_is_not_acceptance(self):
        d = day(path((2, 115), (1, 108), (1, 112), (1, 109), (43, 113)))
        self.assertEqual(V.find_event(d, VAH, VAL)["state"], "no_acceptance")
        self.assertEqual(V.find_event(d, VAH, VAL, need=1)["bucket"], 2)   # the one-close reading takes it

    def test_touching_the_other_edge_before_acceptance_is_not_an_event(self):
        d = day(path((2, 115), (1, 99), (2, 105)))
        self.assertEqual(V.find_event(d, VAH, VAL)["state"], "crossed_first")

    def test_open_below_mirrors(self):
        ev = V.find_event(day(path((4, 95), (2, 101))), VAH, VAL)
        self.assertEqual((ev["kind"], ev["side"], ev["bucket"], ev["extreme"]), ("rule", -1, 5, 95.0))

    def test_open_inside_needs_a_close_outside_first(self):
        self.assertEqual(V.find_event(day(path((48, 105))), VAH, VAL)["state"], "stayed_inside")
        ev = V.find_event(day(path((3, 105), (2, 113), (2, 107))), VAH, VAL)
        self.assertEqual((ev["kind"], ev["state"], ev["side"], ev["bucket"], ev["extreme"]), ("control", "event", 1, 6, 113.0))
        # The low before the excursion does not count against it: only what happened since the close outside.
        ev = V.find_event(day(path((1, 105), (1, 100.5), (2, 113), (2, 107)), wick=1.0), VAH, VAL)
        self.assertEqual(ev["state"], "event")

    def test_an_edge_itself_is_inside(self):
        self.assertEqual(V.find_event(day(path((2, 111), (2, 110))), VAH, VAL)["bucket"], 3)


class StudyTests(unittest.TestCase):
    def coin(self, today):
        """Two days: a previous day with 70% of its volume between 103 and 107 (the rest out to 100 and 110),
        then ``today`` (half-hour prices)."""
        prev = day([105.0] * 48, start=T0 - DAY)
        prev["high"] = np.where(np.arange(288) < 144, 110.0, 107.0)
        prev["low"] = np.where(np.arange(288) < 144, 100.0, 103.0)
        cur = day(today)
        d = {k: np.concatenate([prev[k], cur[k]]) for k in ("ts", "open", "high", "low", "close")}
        d["volume"] = np.ones(len(d["ts"]))
        return d

    def event(self, today):
        d = self.coin(today)
        rows = V.events_of("X", d, V.iso(T0), V.iso(T0))
        self.assertEqual(len(rows), 1)
        return d, rows[0]

    def test_levels_come_from_the_previous_day_only(self):
        _, ev = self.event(path((3, 115), (3, 106)))
        self.assertAlmostEqual(ev["vah"], 107.0, delta=0.1)
        self.assertAlmostEqual(ev["val"], 103.0, delta=0.1)
        self.assertAlmostEqual(ev["poc"], 105.0, delta=0.1)
        self.assertEqual((ev["open_side"], ev["state"], ev["bucket"]), (1, "event", 4))
        self.assertEqual(ev["day_end"] - ev["gi"] - 1, 288 - 6 * (ev["bucket"] + 1))

    def test_reaching_the_other_edge_is_a_win_at_that_edge(self):
        d, ev = self.event(path((3, 115), (3, 106), (2, 104), (2, 102)))
        out = V.score(d, ev)
        self.assertTrue(out["traverse"])
        self.assertFalse(out["stopped_first"])
        self.assertAlmostEqual(out["gross"], (106 - ev["val"]) / 106)
        self.assertAlmostEqual(out["net"], out["gross"] - V.COST)
        self.assertAlmostEqual(out["r"], (106 - ev["val"]) / (115 + ev["step"] - 106))
        self.assertEqual(out["minutes"], 3 * 30 + 5)               # three half hours on, at the first candle there

    def test_a_stop_before_the_edge_is_a_loss_even_if_the_edge_comes_later(self):
        d, ev = self.event(path((3, 115), (3, 106), (1, 116), (4, 102)))
        out = V.score(d, ev)
        self.assertTrue(out["traverse"])                           # the claim counts the edge by the day's end
        self.assertTrue(out["stopped_first"])
        self.assertAlmostEqual(out["gross"], -(115 + ev["step"] - 106) / 106)
        self.assertAlmostEqual(out["r"], -1.0)

    def test_neither_stop_nor_edge_leaves_at_the_days_close(self):
        d, ev = self.event(path((3, 115), (3, 106), (42, 105.5)))
        out = V.score(d, ev)
        self.assertFalse(out["traverse"])
        self.assertAlmostEqual(out["gross"], 0.5 / 106)
        self.assertFalse(out["traverse_24h"])

    def test_the_point_of_control_counts_only_when_the_entry_is_beyond_it(self):
        d, ev = self.event(path((3, 115), (3, 106), (42, 104.5)))
        self.assertTrue(V.score(d, ev)["poc"])                     # in at 106, the POC near 105 was traded
        d, ev = self.event(path((3, 115), (3, 104), (42, 104)))
        self.assertIsNone(V.score(d, ev)["poc"])                   # in below the POC already

    def test_a_long_after_an_open_below(self):
        d, ev = self.event(path((3, 95), (3, 104), (4, 108)))
        out = V.score(d, ev)
        self.assertEqual(ev["side"], -1)
        self.assertTrue(out["traverse"])
        self.assertAlmostEqual(out["gross"], (ev["vah"] - 104) / 104)

    def test_days_missing_candles_are_left_out(self):
        d = self.coin(path((3, 115), (3, 106)))
        keep = np.ones(len(d["ts"]), dtype=bool)
        keep[300:310] = False                                      # ten candles gone from the event day
        d = {k: v[keep] for k, v in d.items()}
        self.assertEqual(V.events_of("X", d, V.iso(T0), V.iso(T0)), [])


class StatsTests(unittest.TestCase):
    def rows(self, per_day, key="x"):
        return [{"day": T0 + i * DAY, key: v} for i, vals in enumerate(per_day) for v in vals]

    def test_ratio_pools_events_and_resamples_days(self):
        rows = self.rows([[1, 1, 1], [0], [1, 0], [1]] * 30)
        st = V.ratio(rows, "x", draws=1000)
        self.assertEqual((st["n"], st["days"]), (210, 120))
        self.assertAlmostEqual(st["value"], 5 / 7)
        self.assertLess(st["low"], st["value"])
        self.assertGreater(st["high"], st["value"])
        self.assertAlmostEqual(st["first_half"], 5 / 7)

    def test_difference_of_two_groups(self):
        a = self.rows([[1, 1], [1, 0]] * 60)
        b = self.rows([[0, 1], [0, 0]] * 60)
        d = V.difference(a, b, "x", draws=1000)
        self.assertAlmostEqual(d["value"], 0.5)
        self.assertGreater(d["low"], 0.3)

    def test_the_claim_bar_needs_the_rate_the_interval_and_both_halves(self):
        ok = {"n": 500, "days": 300, "value": 0.79, "low": 0.74, "first_half": 0.8, "second_half": 0.78}
        self.assertTrue(V.claim_bar(ok)["met"])
        self.assertFalse(V.claim_bar({**ok, "value": 0.74})["met"])
        self.assertFalse(V.claim_bar({**ok, "low": 0.69})["met"])
        self.assertFalse(V.claim_bar({**ok, "second_half": 0.65})["met"])
        self.assertFalse(V.claim_bar({**ok, "n": 150})["met"])

    def test_the_trade_bar_needs_btc_too(self):
        net = {"n": 500, "days": 300, "value": 0.002, "low": 0.0005, "first_half": 0.001, "second_half": 0.003}
        self.assertTrue(V.trade_bar(net, {"value": 0.001})["met"])
        self.assertFalse(V.trade_bar(net, {"value": -0.001})["met"])
        self.assertFalse(V.trade_bar({**net, "low": -0.0001}, {"value": 0.001})["met"])

    def test_months_and_archive_rows(self):
        self.assertEqual(V.months("2020-12", "2021-02"), ["2020-12", "2021-01", "2021-02"])


class EndToEndTests(unittest.TestCase):
    """The whole study on made-up candles: every figure is produced and the counts agree."""

    def test_shape_and_run_on_a_small_made_up_cache(self):
        import tempfile
        from pathlib import Path
        rng = np.random.default_rng(7)
        syms = ("BTCUSDT", "AAAUSDT")
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            n = 288 * 80                                           # 80 days from T0
            for k, sym in enumerate(syms):
                close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
                open_ = np.concatenate(([100.0], close[:-1]))
                spread = np.abs(rng.normal(0, 0.001, n)) * close
                np.savez_compressed(cache / f"{sym}-5m.npz", ts=T0 + np.arange(n) * V.BAR_MS, open=open_,
                                    high=np.maximum(open_, close) + spread, low=np.minimum(open_, close) - spread,
                                    close=close, volume=rng.random(n) + 0.1, taker=np.zeros(n))
            first, last = V.iso(T0 + DAY), V.iso(T0 + 79 * DAY)
            sh = V.shape(first, last, cache, syms)
            two = sh["readings"]["two_closes"]
            self.assertEqual(two["coin_days"], 2 * 79)
            self.assertEqual(two["rule"]["coin_days"] + two["control"]["coin_days"], two["coin_days"])
            self.assertEqual(sum(two["rule"]["states"].values()), two["rule"]["coin_days"])
            self.assertEqual(sum(two["rule"]["per_day"]), two["rule"]["events"])
            self.assertGreaterEqual(sh["readings"]["one_close"]["rule"]["events"], two["rule"]["events"])
            res = V.run_study(first, last, cache, syms, draws=300)
            self.assertEqual(res["data_sha256"], sh["data_sha256"])
            block = res["readings"]["two_closes"]
            self.assertEqual(block["R1"]["rule"]["n"], two["rule"]["events"])        # the run scores the events shape counted
            self.assertEqual(block["R2"]["control"]["n"], two["control"]["events"])
            self.assertFalse(block["R1"]["met"])                                      # far too few events for any bar
            self.assertFalse(block["R3"]["met"])
            for key in ("trade", "poc_first", "within_24h", "by_side", "by_hour", "by_width", "by_coin", "by_year"):
                self.assertIn(key, block["reported"])
            self.assertEqual(res["all_days_touch_both_edges"]["all"]["n"], 2 * 79)
            self.assertIn("traverse", res["one_hour_close"])
            pw = V.power(sh, reps=20)
            self.assertEqual(pw["events"], two["rule"]["events"])


if __name__ == "__main__":
    unittest.main()
