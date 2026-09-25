import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from candle_snapshot import TF_MS, closed_candles, snapshot_key
from signal_synthesizer import synthesize_signal, compute_signal_score
from confluence import unified_signal


def candles(count=500, tf="4h", start=0):
    close = np.linspace(100, 150, count)
    return {"timestamp": start + np.arange(count) * TF_MS[tf],
            "open": close - .1, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.full(count, 1000.)}


def favorable(**overrides):
    return dict(regime="MARKUP", confidence=70, zscore=.5, heat=30,
                heat_phase="Neutral", raw_signal="LIGHT_LONG", bmsb_valid=True,
                heat_direction=1, **overrides)


CONTEXT = dict(positioning={"funding_regime": "NEUTRAL", "oi_trend": "BUILDING"},
               sentiment={"fear_greed_value": 40}, stablecoin={"trend": "STABLE"})


class SignalTests(unittest.TestCase):
    def test_moderate_markup_branch_no_longer_raises(self):
        out = synthesize_signal(favorable(), {"consensus": "MIXED"},
                                sentiment={"fear_greed_value": 80},
                                stablecoin={"trend": "CONTRACTING"})
        self.assertEqual(out.signal, "LIGHT_LONG")
        self.assertIn("effective", out.reason)

    def test_cvd_upgrade_cannot_erase_chop_heat_or_strict_band(self):
        for changes in ({"regime_unstable": True}, {"heat": 90}, {"zscore": 1.2}):
            with self.subTest(changes=changes):
                row = favorable(); row.update(changes)
                out = synthesize_signal(row, {"consensus": "RISK-ON"},
                                        cvd_trend="BULLISH", spot_dominance="SPOT_LED", **CONTEXT)
                self.assertEqual(out.signal, "LIGHT_LONG")
                self.assertTrue(out.strong_long_blockers)

    def test_favorable_complete_context_still_produces_strong_long(self):
        self.assertEqual(synthesize_signal(favorable(), {"consensus": "RISK-ON"}, **CONTEXT).signal, "STRONG_LONG")

    def test_missing_context_is_unknown_and_does_not_earn_points(self):
        out = synthesize_signal(favorable(), {"consensus": "RISK-ON"})
        self.assertEqual(out.conditions_met, 6)
        self.assertAlmostEqual(out.evidence_coverage, 6 / 9)
        unknown = {c["name"] for c in out.conditions_detail if c["status"] == "unknown"}
        self.assertEqual(unknown, {"funding_ok", "not_greedy", "liquidity_ok"})
        self.assertNotEqual(out.signal, "STRONG_LONG")

    def test_neutral_provider_sentinels_do_not_confirm_cvd_or_smart_money(self):
        out = synthesize_signal(favorable(), {"consensus": "RISK-ON"}, has_coinglass=True, **CONTEXT)
        details = {c["name"]: c for c in out.conditions_detail}
        for name in ("cvd_confirms", "smart_money_ok"):
            self.assertFalse(details[name]["met"])
            self.assertFalse(details[name]["available"])

    def test_weighted_denominator_preserves_full_alignment(self):
        for total in (9., 12., 13.):
            self.assertEqual(compute_signal_score("STRONG_LONG", total, total), 100)
        out = synthesize_signal(favorable(), {"consensus": "RISK-ON"}, has_coinglass=True, **CONTEXT)
        self.assertEqual(out.weighted_total, 12)
        self.assertEqual(out.conditions_total, 13)

    def test_short_requires_observed_previous_bar_heat(self):
        row = favorable(); row.update(heat_direction=-1, previous_heat=None)
        self.assertEqual(synthesize_signal(row, {"consensus": "MIXED"}, **CONTEXT).signal, "WAIT")
        row["previous_heat"] = 35
        self.assertEqual(synthesize_signal(row, {"consensus": "MIXED"}, **CONTEXT).signal, "LIGHT_SHORT")
        row["previous_heat"] = 25
        self.assertEqual(synthesize_signal(row, {"consensus": "MIXED"}, **CONTEXT).signal, "WAIT")

    def test_macro_block_is_derived_by_default_for_replay_and_live(self):
        row = favorable(); row.update(heat_direction=-1)
        out = synthesize_signal(row, {"consensus": "RISK-ON"}, **CONTEXT)
        self.assertEqual(out.signal, "WAIT")
        self.assertTrue(out.entry_blocked)

    def test_hard_exit_is_not_erased_by_entry_blocks(self):
        row = favorable(); row.update(heat=100, heat_direction=-1)
        self.assertEqual(synthesize_signal(row, {"consensus": "RISK-ON"}, **CONTEXT).signal, "TRIM")


class CandleTests(unittest.TestCase):
    def test_close_boundary_and_no_unconditional_last_bar_drop(self):
        data = candles(3)
        self.assertEqual(len(closed_candles(data, "4h", 3 * TF_MS["4h"])["close"]), 3)
        self.assertEqual(len(closed_candles(data, "4h", 3 * TF_MS["4h"] - 1)["close"]), 2)

    def test_cache_ignores_live_bar_and_tracks_closed_revisions(self):
        data = candles(4); asof = 3 * TF_MS["4h"]
        original = snapshot_key(data, "4h", as_of_ms=asof)
        data["close"][-1] = 10000
        self.assertEqual(snapshot_key(data, "4h", as_of_ms=asof), original)
        data["close"][-2] += 1
        self.assertNotEqual(snapshot_key(data, "4h", as_of_ms=asof), original)

    def test_cache_tracks_weekly_and_reference_revisions(self):
        data = candles(10); weekly = candles(30, "1w"); btc = candles(10)
        asof = 31 * TF_MS["1w"]
        original = snapshot_key(data, "4h", weekly, btc, as_of_ms=asof)
        weekly["close"][-1] += 1
        revised = snapshot_key(data, "4h", weekly, btc, as_of_ms=asof)
        self.assertNotEqual(revised, original)
        btc["close"][-1] += 1
        self.assertNotEqual(snapshot_key(data, "4h", weekly, btc, as_of_ms=asof), revised)


class PipelineTests(unittest.TestCase):
    def test_real_engines_are_invariant_to_unfinished_bar_changes(self):
        from scanner import _process_symbol
        data = candles(501)
        weekly = candles(80, "1w", start=-80 * TF_MS["1w"])
        asof = 500 * TF_MS["4h"]
        before = _process_symbol("BTC/USDT", "4h", data, weekly, None, None, as_of_ms=asof)
        for name in ("open", "high", "low", "close", "volume"):
            data[name][-1] *= 10
        after = _process_symbol("BTC/USDT", "4h", data, weekly, None, None, as_of_ms=asof)
        self.assertFalse(before["engine_errors"])
        for name in ("regime", "zscore", "heat", "previous_heat", "raw_signal", "decision_price", "exhaustion_state"):
            self.assertEqual(before[name], after[name], name)

    def test_async_synthesis_failure_is_not_restored_by_agent(self):
        from scanner import _synthesize_and_enrich, ScanCache
        row = dict(favorable(), symbol="BTC/USDT", timeframe="4h", signal="STRONG_LONG", asset_class="BTC")
        with patch("scanner.synthesize_signal", side_effect=RuntimeError("test failure")), \
             patch("agent_layer.process") as agent, self.assertLogs("scanner", level="ERROR"):
            asyncio.run(_synthesize_and_enrich([row], "4h", {"consensus": "RISK-ON"},
                        None, None, None, None, {}, ScanCache()))
        agent.assert_not_called()
        self.assertEqual((row["signal"], row["signal_score"], row["signal_status"]), ("WAIT", 0, "unavailable"))

    def test_public_exchange_client_can_be_created_without_removed_import(self):
        from data_fetcher import _create_exchange
        factory = SimpleNamespace(kraken=lambda config: config)
        with patch("data_fetcher._get_ccxt", return_value=factory):
            client = asyncio.run(_create_exchange("kraken"))
        self.assertTrue(client["enableRateLimit"])
        self.assertEqual(client["timeout"], 30000)

    def test_engine_inputs_and_previous_heat_use_completed_bars(self):
        from scanner import _process_symbol
        data = candles(500); weekly = candles(30, "1w", start=-30 * TF_MS["1w"])
        asof = 499 * TF_MS["4h"]
        with patch("scanner.compute_rcce", return_value={}) as rcce, \
             patch("scanner.compute_heatmap", return_value={"heat": 30, "bmsb_mid": 100}) as heat, \
             patch("scanner.compute_exhaustion", return_value={}):
            result = _process_symbol("BTC/USDT", "4h", data, weekly, data, None, as_of_ms=asof)
        self.assertEqual(len(rcce.call_args.args[0]["close"]), 499)
        self.assertEqual(len(rcce.call_args.args[1]["close"]), 499)
        self.assertEqual(result["signal_bar_close_time"], asof / 1000)
        self.assertEqual(result["decision_price"], data["close"][-2])
        self.assertEqual(result["price"], data["close"][-1])
        self.assertEqual(result["previous_heat"], 30)
        self.assertEqual(len(heat.call_args_list[1].args[0]["close"]), 498)

    def test_failure_clears_old_scores_and_never_uses_raw_entry(self):
        from scanner import apply_synthesis_result, finalize_signal, ScanCache
        row = dict(symbol="BTC/USDT", timeframe="4h", raw_signal="STRONG_LONG",
                   signal="STRONG_LONG", signal_score=100, effective_conditions=12)
        apply_synthesis_result(row, NameError("conditions"))
        finalize_signal(row, ScanCache())
        self.assertEqual(row["signal"], "WAIT")
        self.assertEqual(row["signal_score"], 0)
        self.assertEqual(row["signal_status"], "unavailable")

    def test_final_score_and_age_follow_agent_label(self):
        from scanner import apply_synthesis_result, finalize_signal, ScanCache
        row = dict(favorable(), symbol="BTC/USDT", timeframe="4h")
        cache = ScanCache()
        apply_synthesis_result(row, synthesize_signal(row, {"consensus": "RISK-ON"}, **CONTEXT))
        with patch("scanner.time.time", return_value=100):
            finalize_signal(row, cache)
        row["signal"] = "WAIT"
        with patch("scanner.time.time", return_value=150):
            finalize_signal(row, cache)
        self.assertEqual(row["signal_score"], 0)
        self.assertEqual(row["signal_first_seen_at"], 150)

    def test_agent_repeated_polls_do_not_advance_bar_history(self):
        from agent_layer import process
        cache = SimpleNamespace()
        row = dict(favorable(), symbol="BTC/USDT", timeframe="4h", signal="STRONG_LONG", signal_bar_close_time=100)
        process(row.copy(), [], cache)
        process(row.copy(), [], cache)
        self.assertEqual(len(cache.signal_history["BTC/USDT:4h"]), 1)
        row["timeframe"] = "1d"
        process(row.copy(), [], cache)
        self.assertEqual(len(cache.signal_history["BTC/USDT:1d"]), 1)
        self.assertEqual(len(cache.signal_history["BTC/USDT:4h"]), 1)

    def test_agent_inertia_cannot_restore_a_blocked_long(self):
        from agent_layer import process
        cache = SimpleNamespace()
        row = dict(favorable(), symbol="BTC/USDT", timeframe="4h", signal="STRONG_LONG", signal_bar_close_time=100)
        process(row.copy(), [], cache)
        row.update(signal="WAIT", entry_blocked=True, signal_bar_close_time=200)
        self.assertEqual(process(row, [], cache).adjusted_signal, "WAIT")

    def test_inertia_confirmation_counts_candles_instead_of_polls(self):
        from agent_layer import process
        cache = SimpleNamespace()
        row = dict(favorable(), symbol="BTC/USDT", timeframe="4h", signal="STRONG_LONG", signal_bar_close_time=100)
        process(row.copy(), [], cache)
        row.update(signal="LIGHT_LONG", signal_bar_close_time=200)
        for _ in range(3):
            self.assertEqual(process(row.copy(), [], cache).adjusted_signal, "STRONG_LONG")
        row["signal_bar_close_time"] = 300
        self.assertEqual(process(row.copy(), [], cache).adjusted_signal, "LIGHT_LONG")

    def test_unified_signals_cover_short_conflict_and_unavailable(self):
        row = lambda s, **kw: dict(signal=s, regime="MARKUP", **kw)
        self.assertEqual(unified_signal(row("STRONG_LONG"), row("LIGHT_LONG")), "LIGHT_LONG")
        self.assertEqual(unified_signal(row("LIGHT_SHORT"), row("LIGHT_SHORT")), "LIGHT_SHORT")
        self.assertEqual(unified_signal(row("STRONG_LONG"), row("LIGHT_SHORT")), "WAIT")
        self.assertEqual(unified_signal(row("STRONG_LONG"), row("LIGHT_LONG", signal_status="unavailable")), "WAIT")
        self.assertEqual(unified_signal(row("TRIM"), None), "TRIM")
        self.assertEqual(unified_signal(row("LIGHT_LONG"), row("WAIT", entry_blocked=True)), "WAIT")


class ReplayTests(unittest.TestCase):
    def test_daily_weekly_helpers_exclude_unfinished_bars(self):
        from backtest.replay_engine import _find_weekly_slice, _find_daily_index
        weekly = candles(30, "1w"); daily = candles(30, "1d")
        asof = 29 * TF_MS["1w"] + TF_MS["1d"]
        self.assertEqual(len(_find_weekly_slice(weekly, asof)["close"]), 29)
        self.assertEqual(_find_daily_index(daily, 29 * TF_MS["1d"] + TF_MS["4h"]), 29)

    def test_runner_macro_filter_becomes_available_at_week_close(self):
        from backtest.runner import _compute_bmsb_filter
        weekly = candles(30, "1w")
        mapping = _compute_bmsb_filter(weekly)
        self.assertEqual(min(mapping), TF_MS["1w"])
        self.assertEqual(max(mapping), 30 * TF_MS["1w"])

    def test_replay_uses_close_time_and_synthesizes_daily_before_confluence(self):
        from backtest.replay_engine import run_replay
        # Engine stubs isolate event ordering from indicator parameter choices.
        def engine(**kwargs):
            data = kwargs["ohlcv"]
            return dict(favorable(), symbol=kwargs["symbol"], timeframe=kwargs["timeframe"],
                        price=float(data["close"][-1]), signal_bar_close_time=kwargs["as_of_ms"] / 1000,
                        signal="WAIT", vol_state="LOW")
        data = candles(400)
        with patch("backtest.replay_engine._process_symbol", side_effect=engine), \
             patch("backtest.replay_engine.synthesize_signal", side_effect=lambda *a, **kw: __import__("signal_synthesizer").SynthesizedSignal(
                 signal="LIGHT_LONG", raw_signal="WAIT", conditions_met=6, conditions_total=9,
                 reason="test", warnings=[], conditions_detail=[])):
            results = asyncio.run(run_replay(["BTC/USDT"], {"BTC/USDT": data},
                {"BTC/USDT": candles(80, "1d")}, {}, {}, warmup_bars=399))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].timestamp, 400 * TF_MS["4h"])
        self.assertEqual(results[0].confluence_score, 90)


if __name__ == "__main__":
    unittest.main()
