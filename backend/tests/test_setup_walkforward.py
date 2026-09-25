import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from backtest.setup_walkforward import ReplayLedger, scenario_book, run
from paper_setups import PaperLedger
from setup_research_service import apply_research_cycle
import test_forward_setups as fixtures
from test_forward_setups import H
from trading_setups import UNIVERSE


class WalkForwardTests(unittest.TestCase):
    def test_memory_adapter_matches_production_ledger(self):
        row, daily, data, now = fixtures.DefinitionTests().fixture()
        daily["symbol"] = row["symbol"]
        with tempfile.TemporaryDirectory() as root:
            sql = PaperLedger(Path(root) / "paper.db")
            mem = ReplayLedger()
            caches = [SimpleNamespace(paper_ledger=l, results={}) for l in (sql, mem)]
            for i in range(8):
                t = now + i * H
                if i:
                    data = {
                        k: np.append(v, v[-1] + H * 1000 if k == "timestamp" else v[-1])
                        for k, v in data.items()
                    }
                row.update(
                    signal_bar_close_time=t - 1, decision_price=float(data["close"][-1])
                )
                daily["signal_bar_close_time"] = t - 1
                market = {
                    row["symbol"]: dict(
                        candles=data,
                        book=scenario_book(float(data["close"][-1]), t, 2),
                        funding=[],
                        bars=[
                            dict(
                                time=float(data["timestamp"][j]) / 1000,
                                **{
                                    k: float(data[k][j])
                                    for k in ("open", "high", "low", "close")
                                },
                            )
                            for j in range(len(data["close"]))
                        ],
                    )
                }
                for cache in caches:
                    cache.results = {
                        "4h": [copy.deepcopy(row)],
                        "1d": [copy.deepcopy(daily)],
                    }
                    apply_research_cycle(cache, market, as_of=t)
                actual = {r["contract"]["id"]: r for r in sql.records()}
                self.assertEqual(actual, mem.all)
            sql.close()

    def test_no_book_is_not_replaced_with_assumed_liquidity(self):
        self.assertIsNone(scenario_book(100, 123, None))
        self.assertFalse(scenario_book(100, 123, 2)["historical_observation"])


class CausalityTests(unittest.IsolatedAsyncioTestCase):
    async def test_future_prices_do_not_change_past_contracts(self):
        row, daily, data, now = fixtures.DefinitionTests().fixture()
        daily["symbol"] = row["symbol"]
        rows = []
        dailies = []
        for symbol in UNIVERSE:
            rows.append(dict(row, symbol=symbol))
            dailies.append(dict(daily, symbol=symbol))
        history = {
            tf: {s: copy.deepcopy(data) for s in UNIVERSE} for tf in ("4h", "1d", "1w")
        }
        decisions = [dict(time=now - 1, rows=rows, daily=dailies)]
        a = await run(history, {}, as_of_ms=(now + 60) * 1000, decision_bars=decisions)
        for data in history["4h"].values():
            for k, v in data.items():
                data[k] = np.append(
                    v, v[-1] + H * 1000 if k == "timestamp" else v[-1] * 100
                )
        b = await run(history, {}, as_of_ms=(now + 60) * 1000, decision_bars=decisions)
        self.assertEqual(a, b)


class RollingPercentileTests(unittest.TestCase):
    def test_batched_percentiles_match_original_window_loop(self):
        from engines.rcce_engine import _percentile_rolling

        rng = np.random.default_rng(130)
        for n in (1, 7, 30, 100):
            for pct in (0, 15, 50, 85, 100):
                for missing in (False, True):
                    data = rng.normal(size=160)
                    if missing:
                        data[:50] = np.nan
                        data[90:95] = np.nan
                    expected = np.full(len(data), np.nan)
                    for i in range(n - 1, len(data)):
                        valid = data[i - n + 1 : i + 1]
                        valid = valid[~np.isnan(valid)]
                        if len(valid):
                            expected[i] = np.percentile(valid, pct, method="linear")
                    np.testing.assert_array_equal(
                        _percentile_rolling(data, n, pct), expected
                    )


class LedgerLifecycleParityTests(unittest.TestCase):
    def test_trigger_entry_exit_and_funding_match_sql(self):
        c = fixtures.contract()
        with tempfile.TemporaryDirectory() as root:
            sql = PaperLedger(Path(root) / "p.db")
            mem = ReplayLedger()
            for ledger in (sql, mem):
                ledger.observe(c)
            steps = [
                (fixtures.T + 2 * H + 1, [fixtures.bar(fixtures.T + H)]),
                (
                    fixtures.T + 4 * H + 1,
                    [
                        fixtures.bar(fixtures.T + 2 * H),
                        fixtures.bar(fixtures.T + 3 * H, high=130, low=103),
                    ],
                ),
            ]
            for t, bars in steps:
                feed = {
                    c["symbol"]: dict(
                        bars=bars,
                        book=fixtures.book(t),
                        funding=fixtures.funding(fixtures.T, t),
                    )
                }
                for ledger in (sql, mem):
                    ledger.advance_all(feed, as_of=t)
                self.assertEqual(
                    {r["contract"]["id"]: r for r in sql.records()}, mem.all
                )
            self.assertEqual(mem.all[c["id"]]["state"]["status"], "closed")
            self.assertTrue(mem.all[c["id"]]["state"]["funding_complete"])
            sql.close()
