import copy
import unittest
from paper_setups import initial_state, advance
from setup_v2 import features, candidate
from test_forward_setups import contract, bar, book, funding, T, H
import test_forward_setups as fixtures


class SetupV2Tests(unittest.TestCase):
    def test_next_open_is_precommitted_not_backdated(self):
        c = contract()
        c.update(
            entry_mode="next_open",
            execution=dict(book(T + 1), spread_bps=1),
            reference_close=T,
        )
        s = initial_state(c)
        self.assertEqual(s["status"], "scheduled")
        self.assertEqual(s["entry_due"], T + H)
        early = advance(c, s, [bar(T)], book(T + H + 1), [], as_of=T + H + 1)
        self.assertIsNone(early["entry_at"])
        filled = advance(
            c, early, [bar(T + H)], book(T + 2 * H + 1), [], as_of=T + 2 * H + 1
        )
        self.assertEqual(filled["entry_at"], T + H)

    def test_break_even_uses_closed_bar_and_is_effective_next_bar(self):
        c = contract()
        c.update(
            entry_mode="next_open",
            execution=dict(book(T + 1), spread_bps=1),
            reference_close=T,
            target=150,
            atr=3,
        )
        c["parameters"].update(protection="be_5pct", protection_min_bars=1)
        s = advance(
            c,
            initial_state(c),
            [bar(T + H, high=112, low=100, close=110)],
            book(T + 2 * H + 1),
            [],
            as_of=T + 2 * H + 1,
        )
        self.assertEqual(s["status"], "open")
        self.assertGreater(s["active_stop"], s["entry"])
        out = advance(
            c,
            s,
            [bar(T + 2 * H, open=110, high=111, low=103, close=104)],
            book(T + 3 * H + 1),
            funding(T, T + 3 * H),
            as_of=T + 3 * H + 1,
        )
        self.assertEqual(out["reason"], "Protected stop hit")
        self.assertGreaterEqual(out["before_funding_return"], -1e-12)

    def test_high_alone_does_not_arm_break_even(self):
        c = contract()
        c.update(
            entry_mode="next_open",
            execution=dict(book(T + 1), spread_bps=1),
            reference_close=T,
            target=150,
            atr=3,
        )
        c["parameters"].update(protection="be_5pct", protection_min_bars=1)
        s = advance(
            c,
            initial_state(c),
            [bar(T + H, high=112, low=100, close=105)],
            book(T + 2 * H + 1),
            [],
            as_of=T + 2 * H + 1,
        )
        self.assertNotIn("active_stop", s)

    def test_mandatory_gates_and_freshness_are_preserved(self):
        row, daily, data, now = fixtures.DefinitionTests().fixture()
        row.update(regime="MARKUP", entry_blocked=True)
        daily.update(regime="MARKUP")
        p = dict(name="fixture", family="trend", hold=24, target=3)
        f = features(row, daily, data, book(now), now)
        self.assertEqual(candidate(row, daily, f, p, now)[0]["status"], "blocked")
        row["entry_blocked"] = False
        f = features(row, daily, data, None, now)
        self.assertEqual(candidate(row, daily, f, p, now)[0]["status"], "unavailable")


class MacroExceptionTests(unittest.TestCase):
    def test_exception_requires_known_macro_reason_and_keeps_other_guards(self):
        row, daily, data, now = fixtures.DefinitionTests().fixture()
        row.update(
            regime="MARKUP",
            entry_blocked=True,
            bmsb_valid=True,
            signal="WAIT",
            signal_reason="Macro blocked (BMSB bearish) — MARKUP regime, long entries blocked",
        )
        daily.update(regime="MARKUP")
        f = features(row, daily, data, book(now), now)
        f["previous20high"] = f["price"] - 1
        p = dict(
            name="fixture", family="breakout", hold=12, target=2, macro_recovery=True
        )
        c = candidate(row, daily, f, p, now)[0]
        self.assertEqual(c["status"], "pending")
        self.assertTrue(c["macro_recovery"])
        row["signal_reason"] = "Climactic volume"
        self.assertEqual(candidate(row, daily, f, p, now)[0]["status"], "blocked")
        row["signal_reason"] = "Macro blocked (BMSB bearish)"
        row["bmsb_valid"] = False
        self.assertEqual(candidate(row, daily, f, p, now)[0]["status"], "blocked")
        row["bmsb_valid"] = True
        daily["signal"] = "RISK_OFF"
        self.assertEqual(candidate(row, daily, f, p, now)[0]["status"], "blocked")

    def test_missing_volume_and_cto_never_pass_confirmations(self):
        row, daily, data, now = fixtures.DefinitionTests().fixture()
        row.update(regime="MARKUP", entry_blocked=False)
        daily.update(regime="MARKUP")
        f = features(row, daily, data, book(now), now)
        f["previous20high"] = f["price"] - 1
        p = dict(
            name="fixture",
            family="breakout",
            hold=12,
            target=2,
            cto="confirm",
            min_rel_vol=1.2,
        )
        self.assertEqual(candidate(row, daily, f, p, now)[0]["status"], "no_setup")
        row["cto"] = {
            "direction": "up",
            "data_quality": "ready",
            "candle_close_time": row["signal_bar_close_time"],
        }
        self.assertIn("volume", candidate(row, daily, f, p, now)[0]["reason"])
        row["rel_vol"] = 1.5
        self.assertEqual(candidate(row, daily, f, p, now)[0]["status"], "pending")


class ProductionIntegrationTests(unittest.TestCase):
    def test_new_profile_keeps_legacy_contracts_and_has_rollback(self):
        import os
        from unittest.mock import patch
        from setup_v2 import build_live_setups
        from trading_setups import build_setups

        row, daily, data, now = fixtures.DefinitionTests().fixture()
        legacy = build_setups(row, daily, data, book(now), as_of=now)
        with patch.dict(os.environ, {"PAPER_SETUP_V2_ENABLED": "1"}):
            combined = build_live_setups(row, daily, data, book(now), as_of=now)
        self.assertEqual(combined[1:], legacy)
        self.assertEqual(combined[0]["entry_mode"], "next_open")
        self.assertFalse(combined[0].get("macro_recovery"))
        with patch.dict(os.environ, {"PAPER_SETUP_V2_ENABLED": "0"}):
            self.assertEqual(
                build_live_setups(row, daily, data, book(now), as_of=now), legacy
            )

    def test_only_one_scheduled_episode_and_active_records_are_visible(self):
        import tempfile
        from pathlib import Path
        from paper_setups import PaperLedger

        c = contract()
        c.update(
            entry_mode="next_open",
            execution=dict(book(T + 1), spread_bps=1),
            reference_close=T,
        )
        with tempfile.TemporaryDirectory() as root:
            ledger = PaperLedger(Path(root) / "ledger.db")
            first = ledger.observe(c)
            self.assertEqual(first["state"]["status"], "scheduled")
            second = ledger.observe(dict(c, id="second"))
            self.assertEqual(second["state"]["status"], "blocked")
            for i in range(35):
                ledger.observe(
                    dict(c, id=f"no{i}", status="no_setup", observed_at=T + 100 + i)
                )
            self.assertEqual(len(ledger.report()["active_records"]), 1)
            self.assertEqual(
                ledger.report()["active_records"][0]["contract"]["id"], c["id"]
            )
            ledger.close()


class StopAuditTests(unittest.TestCase):
    def test_stop_adjustment_is_an_explicit_ledger_event(self):
        import tempfile
        from pathlib import Path
        from paper_setups import PaperLedger

        c = contract()
        c.update(
            entry_mode="next_open",
            execution=dict(book(T + 1), spread_bps=1),
            reference_close=T,
            target=150,
            atr=3,
        )
        c["parameters"].update(protection="be_5pct", protection_min_bars=1)
        with tempfile.TemporaryDirectory() as root:
            ledger = PaperLedger(Path(root) / "p.db")
            previous = ledger.observe(c)["state"]
            after = advance(
                c,
                previous,
                [bar(T + H, high=112, low=100, close=110)],
                book(T + 2 * H + 1),
                [],
                as_of=T + 2 * H + 1,
            )
            ledger.save_state(c, previous, after, T + 2 * H + 1)
            self.assertEqual(
                [x["event"] for x in ledger.events(c["id"])],
                ["observed", "entry", "stop_updated"],
            )
            ledger.close()


class IdentityTests(unittest.TestCase):
    def test_execution_assumptions_are_part_of_contract_identity(self):
        from unittest.mock import patch
        from trading_setups import PARAMETERS

        row, daily, data, now = fixtures.DefinitionTests().fixture()
        row.update(regime="MARKUP")
        daily.update(regime="MARKUP")
        f = features(row, daily, data, book(now), now)
        p = dict(name="fixture", family="breakout", hold=12, target=2)
        a = candidate(row, daily, f, p, now)[0]
        with patch.dict(PARAMETERS, {"fee_bps": 10}):
            b = candidate(row, daily, f, p, now)[0]
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(a["parameters"]["entry_zone_atr"], 1)
        self.assertEqual(a["parameters"]["entry_zone_below_atr"], 0.5)
