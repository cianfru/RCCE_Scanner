import copy
import json
import tempfile
import unittest
import numpy as np
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from trading_setups import PARAMETERS, TF_SECONDS as H, build_setups, execution_quality
from paper_setups import initial_state, advance, PaperLedger, summarize
from setup_research_service import parse_book, apply_research_cycle
from test_signal_reliability import candles

T = 1440000.0


def book(at):
    return dict(
        bid=104.0,
        ask=104.01,
        observed_at=at,
        bid_depth_usd=500000.0,
        ask_depth_usd=500000.0,
    )


def contract(identity="fixture"):
    return dict(
        id=identity,
        version="setups-1",
        symbol="BTC/USDT",
        strategy="continuation_pullback",
        timeframe="4h",
        regime="REACC",
        observed_at=T + 1,
        reference_close=T,
        status="pending",
        reason="Await trigger",
        trigger=103.0,
        stop=95.0,
        target=125.0,
        entry_zone=[103.0, 106.0],
        expires_at=T + 3 * H + 1,
        parameters=dict(PARAMETERS),
    )


def bar(start, open=104.0, high=106.0, low=103.0, close=105.0):
    return dict(time=start, open=open, high=high, low=low, close=close)


def funding(start, end):
    return [
        dict(time=t, rate=0.0001) for t in range(int(start + 3600), int(end + 1), 3600)
    ]


def scheduled(c=None):
    c = c or contract()
    now = T + 2 * H + 1
    s = advance(c, initial_state(c), [bar(T + H)], book(now), [], as_of=now)
    return c, s


class DefinitionTests(unittest.TestCase):
    def fixture(self):
        data = candles(60)
        data["close"] = np.linspace(100, 110, 60)
        data.update(
            open=data["close"] - 0.1, high=data["close"] + 1, low=data["close"] - 1
        )
        end = float(data["timestamp"][-1] / 1000 + H)
        now = end + 1
        row = dict(
            symbol="BTC/USDT",
            timeframe="4h",
            signal="ACCUMULATE",
            regime="ACCUM",
            signal_bar_close_time=end,
            floor_confirmed=True,
            is_absorption=True,
            decision_price=float(data["close"][-1]),
        )
        daily = dict(regime="ACCUM", signal="ACCUMULATE", signal_bar_close_time=end)
        return row, daily, data, now

    def test_reversal_is_explicit_and_versioned(self):
        row, daily, data, now = self.fixture()
        defs = build_setups(row, daily, data, book(now), as_of=now)
        reversal = next(d for d in defs if d["strategy"] == "confirmed_reversal")
        self.assertEqual(reversal["status"], "pending")
        self.assertLess(reversal["stop"], reversal["trigger"])
        self.assertGreater(reversal["target"], reversal["trigger"])
        self.assertEqual(reversal["parameters"], PARAMETERS)
        self.assertEqual(reversal["validation_status"], "unvalidated")
        row["cto"] = {"state": "strong_down"}
        self.assertEqual(
            next(
                d
                for d in build_setups(row, daily, data, book(now), as_of=now)
                if d["strategy"] == "confirmed_reversal"
            )["status"],
            "pending",
        )

    def test_missing_stale_daily_book_and_gaps_are_explicit(self):
        row, daily, data, now = self.fixture()
        self.assertTrue(
            all(
                d["status"] == "unavailable"
                for d in build_setups(row, None, data, book(now), as_of=now)
            )
        )
        self.assertEqual(
            execution_quality(book(now - 61), as_of=now)["status"], "unavailable"
        )
        wide = dict(book(now), ask=110)
        self.assertEqual(execution_quality(wide, as_of=now)["status"], "blocked")
        data["timestamp"][40] += 1
        self.assertTrue(
            all(
                d["status"] == "unavailable"
                for d in build_setups(row, daily, data, book(now), as_of=now)
            )
        )

    def test_monotonic_uptrend_is_not_a_pullback(self):
        row, daily, data, now = self.fixture()
        row["regime"] = "MARKUP"
        daily["regime"] = "MARKUP"
        c = build_setups(row, daily, data, book(now), as_of=now)[0]
        self.assertEqual(c["status"], "no_setup")

    def test_book_depth_uses_near_market_levels(self):
        result = parse_book(
            dict(
                time=T * 1000,
                levels=[
                    [{"px": "100", "sz": "100"}, {"px": "50", "sz": "999999"}],
                    [{"px": "100.01", "sz": "100"}],
                ],
            )
        )
        self.assertEqual(result["bid_depth_usd"], 10000)
        self.assertIsNone(parse_book(None))


class SimulatorTests(unittest.TestCase):
    def test_trigger_and_entry_never_use_past_open(self):
        c, s = scheduled()
        self.assertEqual(s["status"], "scheduled")
        self.assertEqual(s["entry_due"], T + 3 * H)
        self.assertGreaterEqual(s["entry_due"], s["trigger_at"])
        result = advance(
            c, s, [bar(T + 2 * H), bar(T + 3 * H)], book(T + 4 * H), [], as_of=T + 4 * H
        )
        self.assertEqual(result["status"], "open")
        self.assertEqual(result["entry_at"], T + 3 * H)

    def test_open_candle_cannot_trigger(self):
        c = contract()
        s = advance(
            c, initial_state(c), [bar(T + H)], book(T + H + 1), [], as_of=T + H + 1
        )
        self.assertEqual(s["status"], "pending")

    def test_target_costs_and_funding_are_separate(self):
        c, s = scheduled()
        end = T + 4 * H
        bars = [bar(T + 2 * H), bar(T + 3 * H, high=126, close=124)]
        s = advance(c, s, bars, book(end), [], as_of=end)
        self.assertEqual(s["status"], "closed")
        self.assertIsNone(s["net_return"])
        self.assertFalse(s["funding_complete"])
        finished = advance(
            c, s, [], None, funding(s["entry_at"], s["exit_at"]), as_of=end + 60
        )
        self.assertTrue(finished["funding_complete"])
        self.assertLess(finished["net_return"], finished["gross_return"])
        self.assertLess(finished["net_return"], finished["before_funding_return"])
        self.assertEqual(finished["exit_at"], s["exit_at"])

    def test_gap_outside_entry_zone_is_missed(self):
        c, s = scheduled()
        s = advance(
            c,
            s,
            [bar(T + 2 * H), bar(T + 3 * H, open=110, high=112, low=109, close=110)],
            None,
            [],
            as_of=T + 4 * H,
        )
        self.assertEqual(s["status"], "missed")
        self.assertIsNone(s["entry"])

    def test_stop_target_tie_is_pessimistic_and_flagged(self):
        c, s = scheduled()
        s = advance(
            c,
            s,
            [bar(T + 2 * H), bar(T + 3 * H, high=130, low=90)],
            None,
            [],
            as_of=T + 4 * H,
        )
        self.assertEqual(s["status"], "closed")
        self.assertTrue(s["ambiguous"])
        self.assertLess(s["exit"], c["stop"])
        self.assertEqual(s["mfe"], 0)

    def test_stop_gap_fills_at_worse_open(self):
        c, s = scheduled()
        s = advance(c, s, [bar(T + 2 * H), bar(T + 3 * H)], None, [], as_of=T + 4 * H)
        s = advance(
            c,
            s,
            [bar(T + 4 * H, open=90, high=92, low=89, close=91)],
            None,
            [],
            as_of=T + 5 * H,
        )
        self.assertLess(s["exit"], 90)
        self.assertEqual(s["status"], "closed")

    def test_intervening_gap_is_unscorable(self):
        c, s = scheduled()
        s = advance(c, s, [bar(T + 3 * H)], None, [], as_of=T + 4 * H)
        self.assertEqual(s["status"], "data_gap")
        self.assertIsNone(s["net_return"])

    def test_unknown_candles_pause_instead_of_inventing_expiry(self):
        c = contract()
        s = advance(c, initial_state(c), [], None, [], as_of=T + 5 * H)
        self.assertEqual(s["status"], "pending")
        self.assertIn("paused_reason", s)

    def test_untriggered_expiry_and_time_exit(self):
        c = contract()
        bars = [
            bar(T + i * H, open=101, high=102, low=100, close=101) for i in (1, 2, 3)
        ]
        s = advance(c, initial_state(c), bars, book(T + 4 * H), [], as_of=T + 4 * H)
        self.assertEqual(s["status"], "expired")
        c = contract()
        c["parameters"]["max_hold_bars"] = 1
        c, s = scheduled(c)
        s = advance(c, s, [bar(T + 2 * H), bar(T + 3 * H)], None, [], as_of=T + 4 * H)
        self.assertEqual(s["reason"], "Time exit")

    def test_repeat_observation_does_not_advance_trade_twice(self):
        c, s = scheduled()
        bars = [bar(T + 2 * H), bar(T + 3 * H)]
        first = advance(c, s, bars, None, [], as_of=T + 4 * H)
        again = advance(c, first, bars, None, [], as_of=T + 4 * H)
        self.assertEqual(first, again)


class LedgerTests(unittest.TestCase):
    def test_restart_contract_immutability_and_one_active_episode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.db"
            ledger = PaperLedger(path)
            c = contract()
            ledger.observe(c)
            changed = dict(c, target=999)
            self.assertEqual(ledger.observe(changed)["contract"]["target"], 125)
            another = ledger.observe(contract("second"))
            self.assertEqual(another["state"]["status"], "blocked")
            ledger.close()
            ledger = PaperLedger(path)
            self.assertEqual(len(ledger.records()), 2)
            self.assertEqual(len(ledger.events(c["id"])), 1)
            ledger.close()

    def test_cancel_and_missing_funding_do_not_count_as_losses(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = PaperLedger(Path(folder) / "ledger.db")
            c = contract()
            ledger.observe(c)
            ledger.cancel_pending(c["symbol"], "Daily became bearish", as_of=T + 100)
            report = ledger.report()
            summary = next(iter(report["strategies"].values()))["summary"]
            self.assertEqual(summary["states"]["cancelled"], 1)
            self.assertIsNone(summary["expectancy"])
            ledger.close()

    def test_entry_and_exit_are_preserved_in_events(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = PaperLedger(Path(folder) / "ledger.db")
            c, s = scheduled()
            original = ledger.observe(c)["state"]
            ledger.save_state(c, original, s, T + 2 * H + 1)
            final = advance(
                c,
                s,
                [bar(T + 2 * H), bar(T + 3 * H, high=126)],
                None,
                [],
                as_of=T + 4 * H,
            )
            ledger.save_state(c, s, final, T + 4 * H)
            names = [e["event"] for e in ledger.events(c["id"])]
            self.assertEqual(names, ["observed", "scheduled", "entry", "closed"])
            ledger.close()

    def test_cycle_persists_no_setup_and_hydrates_cards(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = PaperLedger(Path(folder) / "ledger.db")
            data = candles(60)
            end = float(data["timestamp"][-1] / 1000 + H)
            row = dict(
                symbol="BTC/USDT",
                timeframe="4h",
                regime="FLAT",
                signal="WAIT",
                signal_bar_close_time=end,
            )
            cache = SimpleNamespace(
                paper_ledger=ledger,
                results={"4h": [row], "1d": [dict(row, timeframe="1d")]},
            )
            feed = {
                "BTC/USDT": dict(candles=data, bars=[], book=book(end + 1), funding=[])
            }
            apply_research_cycle(cache, feed, as_of=end + 1)
            apply_research_cycle(cache, feed, as_of=end + 2)
            self.assertEqual(len(ledger.records()), 3)
            self.assertEqual(len(row["trading_setups"]), 3)
            self.assertTrue(
                all(r["state"]["status"] == "no_setup" for r in ledger.records())
            )
            ledger.close()


if __name__ == "__main__":
    unittest.main()


class BackgroundIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_is_scheduled_once_without_blocking_scan(self):
        import asyncio
        from setup_research_service import schedule_setup_research, stop_setup_research

        gate = asyncio.Event()
        cache = SimpleNamespace(results={"4h": [], "1d": []})

        async def fake_update(value):
            await gate.wait()

        with patch(
            "setup_research_service.update_setup_research", side_effect=fake_update
        ) as update:
            schedule_setup_research(cache)
            first = cache.paper_research_task
            schedule_setup_research(cache)
            self.assertIs(first, cache.paper_research_task)
            await asyncio.sleep(0)
            self.assertEqual(update.call_count, 1)
            self.assertFalse(first.done())
            await stop_setup_research(cache)
            self.assertTrue(first.cancelled())
