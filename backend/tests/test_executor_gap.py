"""The executor-gap position managers (docs/reviews/executor-gap-study.md): with the backtest's four rules the
class trades exactly as the backtest manager; each rule changes only what it names."""
import unittest
from types import SimpleNamespace

from backtest import executor_gap as G
from backtest.larsson_study import INITIAL_CAPITAL, _costed_pm_class

SYMS = ["A/USDT", "B/USDT"]


def bar(t, sym, price, signal):
    return SimpleNamespace(timestamp=float(t), symbol=sym, price=price, signal=signal, confluence_label="STRONG")


def run(cls, bars, blocked=()):
    pm = cls(INITIAL_CAPITAL, SYMS)
    for b in bars:
        pm.macro_blocked = b.timestamp in blocked
        pm.process_bar(b)
    return pm


def exits(pm):
    return [(t.symbol, t.exit_signal, round(t.pnl_usd, 6)) for t in pm.trades]


class ExecutorGapTests(unittest.TestCase):
    def test_backtest_flags_equal_the_backtest_manager(self):
        bars, t = [], 0
        script = [("LIGHT_LONG", 100), ("WAIT", 104), ("WAIT", 99), ("TRIM", 103), ("STRONG_LONG", 100),
                  ("WAIT", 91), ("LIGHT_LONG", 90)] + [("WAIT", 95)] * 25 + [("LIGHT_LONG", 96), ("RISK_OFF", 97)]
        for sig, px in script:
            t += 1
            bars += [bar(t, "A/USDT", px, sig), bar(t, "B/USDT", px * 2, "LIGHT_LONG" if sig == "WAIT" else "WAIT")]
        a = run(_costed_pm_class(), bars, blocked={5.0})
        b = run(G.manager(**G.BACKTEST), bars, blocked={5.0})
        self.assertTrue(a.trades)
        self.assertEqual(exits(a), exits(b))
        self.assertAlmostEqual(a.get_equity(), b.get_equity(), places=6)

    def test_breakeven_closes_at_entry_after_five_percent(self):
        bars = [bar(1, "A/USDT", 100, "LIGHT_LONG"), bar(2, "A/USDT", 106, "WAIT"), bar(3, "A/USDT", 100, "WAIT")]
        self.assertEqual([e[1] for e in exits(run(G.manager(**G.EXECUTOR), bars))], ["BE_STOP"])
        self.assertEqual(exits(run(G.manager(**{**G.EXECUTOR, "breakeven": False}), bars)), [])
        unarmed = [bar(1, "A/USDT", 100, "LIGHT_LONG"), bar(2, "A/USDT", 104, "WAIT"), bar(3, "A/USDT", 99, "WAIT")]
        self.assertEqual(exits(run(G.manager(**G.EXECUTOR), unarmed)), [])

    def test_decay_only_when_set(self):
        bars = [bar(1, "A/USDT", 100, "LIGHT_LONG")] + [bar(1 + i, "A/USDT", 101, "WAIT") for i in range(1, 25)]
        self.assertEqual(exits(run(G.manager(**G.EXECUTOR), bars)), [])
        pm = run(G.manager(**{**G.EXECUTOR, "decay": 20}), bars)
        self.assertEqual([e[1] for e in exits(pm)], ["DECAY_EXIT"])
        self.assertEqual(pm.trades[0].bars_held, 20)

    def test_band_blocks_entries_only_when_set(self):
        bars = [bar(1, "A/USDT", 100, "LIGHT_LONG")]
        self.assertEqual(len(run(G.manager(**G.EXECUTOR), bars, blocked={1.0}).positions), 1)
        self.assertEqual(len(run(G.manager(**{**G.EXECUTOR, "band": True}), bars, blocked={1.0}).positions), 0)

    def test_risk_off_scope(self):
        bars = [bar(1, "A/USDT", 100, "LIGHT_LONG"), bar(1, "B/USDT", 50, "LIGHT_LONG"), bar(2, "A/USDT", 99, "RISK_OFF")]
        self.assertEqual(sorted(run(G.manager(**G.EXECUTOR), bars).positions), ["B/USDT"])
        self.assertEqual(run(G.manager(**{**G.EXECUTOR, "risk_off_all": True}), bars).positions, {})

    def test_executor_constants_match(self):
        import executor
        self.assertEqual((executor._HARD_STOP_PCT, executor._BE_ARM_PCT), (100 * G.STOP_PCT, 100 * G.BE_ARM))
        self.assertEqual(set(executor._ENTRY_SIGNALS), {"STRONG_LONG", "LIGHT_LONG", "REVIVAL_SEED"})
        self.assertEqual(set(executor._EXIT_SIGNALS), set(G.EXIT_SIGNALS) | {"RISK_OFF"})


if __name__ == "__main__":
    unittest.main()
