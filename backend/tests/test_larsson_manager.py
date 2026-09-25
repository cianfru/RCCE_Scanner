import unittest

from backtest.larsson_manager import DayBar, LarssonManager, ManagerConfig

DAY = 86_400_000.0
NO_COST = dict(fee_bps=0.0, slip_bps=0.0)


def bar(sym, i, o, h=None, l=None, c=None, **kw):
    c = o if c is None else c
    return DayBar(symbol=sym, timestamp=i * DAY, open=o, high=h if h is not None else max(o, c),
                  low=l if l is not None else min(o, c), close=c, **kw)


def run(mgr, days):
    for i, bars in enumerate(days):
        mgr.process_day(i * DAY, {b.symbol: b for b in bars})
    return mgr


class SizingTests(unittest.TestCase):
    def test_trend_entry_fills_next_open_with_risk_sizing(self):
        cfg = ManagerConfig(variant="L1", risk_pct=0.01, **NO_COST)
        m = LarssonManager(10_000, ["BTC"], cfg)
        run(m, [[bar("BTC", 0, 100, trend="gold", flip="gold", last_actionable="gold")],
                [bar("BTC", 1, 110, trend="gold", last_actionable="gold")]])
        pos = m.positions["BTC"]
        # 12% fallback stop: allocation = 1% x 10,000 / 0.12 = 833.33, first tranche 50%.
        self.assertAlmostEqual(pos.cost, 10_000 * 0.01 / 0.12 * 0.5, places=6)
        self.assertAlmostEqual(pos.avg_entry, 110.0)          # filled at the next open, not the signal close
        self.assertAlmostEqual(pos.stop, 110 * 0.88)

    def test_allocation_cap_25pct(self):
        cfg = ManagerConfig(variant="L3", risk_pct=0.02, stop_buffer=0.0, **NO_COST)
        m = LarssonManager(10_000, ["X"], cfg)
        ev = [{"event": "bounce", "level": 99.0}]
        run(m, [[bar("X", 0, 100, range_state=True, events=ev, trend="grey")],
                [bar("X", 1, 100, range_state=True, trend="grey")]])
        # 2% risk over a 1% stop would be 200% of equity; the cap is 25%.
        self.assertAlmostEqual(m.positions["X"].cost, 2_500.0)

    def test_costs_charged_both_sides(self):
        cfg = ManagerConfig(variant="L3", risk_pct=0.01, fee_bps=5, slip_bps=5)
        m = LarssonManager(10_000, ["X"], cfg)
        ev = [{"event": "breakout", "level": 90.0}]
        run(m, [[bar("X", 0, 100, range_state=True, events=ev, trend="grey")],
                [bar("X", 1, 100, range_state=True, trend="grey")]])
        alloc = m.positions["X"].cost
        self.assertAlmostEqual(alloc, 10_000 * 0.01 / ((100 - 90 * 0.99) / 100), places=6)
        m.close_all_at_end(2 * DAY)
        # Flat price: the round trip costs 10 bps on the way in and 10 bps on the way out.
        self.assertAlmostEqual(m.get_equity(), 10_000 - alloc * (1 - 0.999 ** 2), places=6)
        self.assertAlmostEqual(m.trades[0].pnl_usd, -alloc * (1 - 0.999 ** 2), places=6)


class StopTests(unittest.TestCase):
    def test_gap_through_stop_fills_at_open(self):
        cfg = ManagerConfig(variant="L1", **NO_COST)
        m = LarssonManager(10_000, ["BTC"], cfg)
        run(m, [[bar("BTC", 0, 100, trend="gold", flip="gold", last_actionable="gold")],
                [bar("BTC", 1, 100, trend="gold", last_actionable="gold")],          # fill @100, stop 88
                [bar("BTC", 2, 95, c=85, trend="gold", last_actionable="gold")],     # close below stop
                [bar("BTC", 3, 70, c=72, trend="gold", last_actionable="gold")]])    # gaps down: fill @ open 70
        self.assertNotIn("BTC", m.positions)
        t = m.trades[-1]
        self.assertEqual(t.exit_reason, "stop")
        self.assertAlmostEqual(t.r_multiple, (70 - 100) / 12, places=6)   # -2.5R: the gap cost more than 1R

    def test_stop_is_close_checked_not_intrabar(self):
        cfg = ManagerConfig(variant="L1", **NO_COST)
        m = LarssonManager(10_000, ["BTC"], cfg)
        run(m, [[bar("BTC", 0, 100, trend="gold", flip="gold", last_actionable="gold")],
                [bar("BTC", 1, 100, trend="gold", last_actionable="gold")],
                [bar("BTC", 2, 100, l=80, c=95, trend="gold", last_actionable="gold")],   # wick below stop only
                [bar("BTC", 3, 96, trend="gold", last_actionable="gold")]])
        self.assertIn("BTC", m.positions)


class TrancheTests(unittest.TestCase):
    def test_second_tranche_limit_at_support(self):
        cfg = ManagerConfig(variant="L1", **NO_COST)
        m = LarssonManager(10_000, ["BTC"], cfg)
        g = dict(trend="gold", last_actionable="gold", sr_levels=[90.0, 120.0])
        run(m, [[bar("BTC", 0, 100, flip="gold", **g)],
                [bar("BTC", 1, 100, **g)],
                [bar("BTC", 2, 95, l=89, c=94, **g)]])        # low reaches the 90 support
        pos = m.positions["BTC"]
        self.assertAlmostEqual(pos.cost, 10_000 * 0.01 / 0.12)   # both halves in
        self.assertLess(pos.avg_entry, 100)

    def test_blue_flip_sells_half_then_rest_at_resistance(self):
        cfg = ManagerConfig(variant="L1", **NO_COST)
        m = LarssonManager(10_000, ["BTC"], cfg)
        g = dict(last_actionable="gold", sr_levels=[80.0])
        days = [[bar("BTC", 0, 100, trend="gold", flip="gold", **g)],
                [bar("BTC", 1, 100, trend="gold", **g)],
                [bar("BTC", 2, 99, trend="blue", flip="blue", last_actionable="blue", sr_levels=[80.0, 104.0])],
                [bar("BTC", 3, 98, trend="blue", last_actionable="blue", sr_levels=[80.0, 104.0])],
                [bar("BTC", 4, 99, c=105, trend="blue", last_actionable="blue", sr_levels=[80.0, 104.0])],
                [bar("BTC", 5, 106, trend="blue", last_actionable="blue")]]
        run(m, days[:4])
        self.assertIn("BTC", m.positions)                       # half sold at bar 3's open
        run(m, days[4:])
        self.assertNotIn("BTC", m.positions)
        self.assertEqual(m.trades[-1].exit_reason, "blue_flip_rest")

    def test_rest_sells_after_ten_bars_without_resistance(self):
        cfg = ManagerConfig(variant="L1", **NO_COST)
        m = LarssonManager(10_000, ["BTC"], cfg)
        days = [[bar("BTC", 0, 100, trend="gold", flip="gold", last_actionable="gold")],
                [bar("BTC", 1, 100, trend="gold", last_actionable="gold")],
                [bar("BTC", 2, 99, trend="blue", flip="blue", last_actionable="blue")]]
        days += [[bar("BTC", i, 98, trend="blue", last_actionable="blue")] for i in range(3, 15)]
        run(m, days)
        self.assertNotIn("BTC", m.positions)


class BudgetTests(unittest.TestCase):
    def test_at_most_two_new_alt_entries_per_bar(self):
        syms = ["A", "B", "C"]
        cfg = ManagerConfig(variant="L1", risk_pct=0.005, **NO_COST)
        m = LarssonManager(100_000, syms, cfg)
        g = dict(trend="gold", last_actionable="gold", is_alt=True)
        run(m, [[bar(s, 0, 100, flip="gold", **g) for s in syms],
                [bar(s, 1, 100, **g) for s in syms]])
        self.assertEqual(sorted(m.positions), ["A", "B"])
        run(m, [[bar(s, 2, 100, **g) for s in syms]])
        self.assertIn("C", m.positions)                        # queued entry fills on the next bar

    def test_alt_open_risk_capped_at_5pct(self):
        syms = [f"S{i}" for i in range(8)]
        cfg = ManagerConfig(variant="L1", risk_pct=0.02, max_new_alt_per_bar=99, **NO_COST)
        m = LarssonManager(100_000, syms, cfg)
        g = dict(trend="gold", last_actionable="gold", is_alt=True)
        run(m, [[bar(s, 0, 100, flip="gold", **g) for s in syms],
                [bar(s, 1, 100, **g) for s in syms]])
        risk = sum(p.qty * (p.avg_entry - p.stop) for p in m.positions.values())
        self.assertLessEqual(risk, 0.05 * 100_000 + 1e-6)

    def test_btc_is_not_budgeted_as_alt(self):
        cfg = ManagerConfig(variant="L1", risk_pct=0.02, **NO_COST)
        m = LarssonManager(100_000, ["BTC"], cfg)
        run(m, [[bar("BTC", 0, 100, trend="gold", flip="gold", last_actionable="gold", is_alt=False)],
                [bar("BTC", 1, 100, trend="gold", last_actionable="gold", is_alt=False)]])
        self.assertAlmostEqual(m.positions["BTC"].cost, 100_000 * 0.02 / 0.12 * 0.5)


class VariantTests(unittest.TestCase):
    def test_range_mode_ignores_blue_flip(self):
        cfg = ManagerConfig(variant="L3", **NO_COST)
        m = LarssonManager(10_000, ["X"], cfg)
        run(m, [[bar("X", 0, 100, range_state=True, trend="grey", events=[{"event": "bounce", "level": 97.0}])],
                [bar("X", 1, 100, range_state=True, trend="grey")],
                [bar("X", 2, 99, range_state=True, trend="blue", flip="blue", last_actionable="blue")],
                [bar("X", 3, 99, range_state=True, trend="blue", last_actionable="blue")]])
        self.assertIn("X", m.positions)

    def test_l1_ignores_level_events(self):
        m = LarssonManager(10_000, ["X"], ManagerConfig(variant="L1", **NO_COST))
        run(m, [[bar("X", 0, 100, range_state=True, trend="grey", events=[{"event": "bounce", "level": 97.0}])],
                [bar("X", 1, 100, range_state=True, trend="grey")]])
        self.assertEqual(m.positions, {})

    def test_l4_trims_on_grey_and_restores_on_gold(self):
        cfg = ManagerConfig(variant="L4", **NO_COST)
        m = LarssonManager(10_000, ["X"], cfg)
        g = dict(last_actionable="gold")
        run(m, [[bar("X", 0, 100, trend="gold", flip="gold", **g)],
                [bar("X", 1, 100, trend="gold", **g)],
                [bar("X", 2, 100, trend="grey", grey_after_gold=True, **g)],
                [bar("X", 3, 100, trend="grey", **g)]])
        after_trim = m.positions["X"].qty
        run(m, [[bar("X", 4, 100, trend="gold", **g)], [bar("X", 5, 100, trend="gold", **g)]])
        self.assertAlmostEqual(m.positions["X"].qty, after_trim * 2, places=6)

    def test_l5_gate_blocks_new_longs(self):
        m = LarssonManager(10_000, ["X"], ManagerConfig(variant="L5", **NO_COST))
        run(m, [[bar("X", 0, 100, trend="gold", flip="gold", last_actionable="gold", gate_ok=False)],
                [bar("X", 1, 100, trend="gold", last_actionable="gold", gate_ok=False)]])
        self.assertEqual(m.positions, {})

    def test_window_start_in_gold_counts_as_found_late_entry(self):
        m = LarssonManager(10_000, ["X"], ManagerConfig(variant="L1", **NO_COST))
        run(m, [[bar("X", 0, 100, trend="grey", last_actionable="gold", first_bar=True)],
                [bar("X", 1, 100, trend="grey", last_actionable="gold")]])
        self.assertIn("X", m.positions)
        m2 = LarssonManager(10_000, ["X"], ManagerConfig(variant="L1", enter_at_start=False, **NO_COST))
        run(m2, [[bar("X", 0, 100, trend="grey", last_actionable="gold", first_bar=True)],
                 [bar("X", 1, 100, trend="grey", last_actionable="gold")]])
        self.assertEqual(m2.positions, {})


if __name__ == "__main__":
    unittest.main()
