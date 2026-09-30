"""Executor price guard and the one-time PURR paper-ledger correction."""
import asyncio
import json
from unittest.mock import patch

import pytest

import executor as executor_mod
from executor import Executor, ExecutorPosition, _LEDGER_CORRECTIONS
from executor_ledger_audit import closure_issue
from executor_performance import performance
from trading_engine import PaperEngine

PURR = dict(symbol="PURR/USDT", exchange_pair="PURR", side="LONG", entry_price=0.12409,
            entry_time=1790425994.2996264, entry_signal="LIGHT_LONG", exit_price=13.015,
            exit_time=1790489004.928304, exit_signal="TRIM", volume=314.79,
            pnl_pct=10388.35522604561, pnl_usd=4057.951260174067, cost_usd=39.0625,
            order_ids=["paper-1854", "paper-1856"], entry_reason="", entry_warnings=[], kraken_pair="PURR")
OTHER = dict(PURR, symbol="JTO/USDT", exchange_pair="JTO", entry_price=0.58956, exit_price=0.58508,
             exit_signal="BE_STOP", volume=66.26, pnl_pct=-0.7598887305787245,
             pnl_usd=-0.29683153538231427, kraken_pair="JTO")
OPEN_PURR = dict(symbol="PURR/USDT", exchange_pair="PURR", side="LONG", entry_price=0.14187,
                 entry_time=1790611396.92348, entry_signal="LIGHT_LONG", volume=275.34, cost_usd=39.0625,
                 size_pct=0.5, confluence_at_entry="STRONG", order_id="paper-1881")


@pytest.fixture
def state_file(tmp_path):
    path = tmp_path / "executor_state.json"
    with patch.object(executor_mod, "_STATE_FILE", path):
        yield path


def paper_executor(refs, symbols=("PURR/USDT",)):
    ex = Executor(mode="paper")
    ex.engine = PaperEngine(10000)
    ex.pair_map = {s: s.split("/")[0] for s in symbols}
    ex.whitelist = list(symbols) + [f"X{i}/USDT" for i in range(9)]
    ex.enabled = ex.initialized = True
    ex.reference_provider = lambda symbol: dict(refs)
    return ex


def row(price, signal, **extra):
    return {"symbol": "PURR/USDT", "signal": signal, "price": price,
            "confluence": {"label": "STRONG"}, **extra}


def open_position(ex, entry=0.12409):
    ex.engine.buy("PURR/USDT", 314.79, entry)
    ex.positions["PURR/USDT"] = ExecutorPosition(symbol="PURR/USDT", exchange_pair="PURR",
                                                 entry_price=entry, volume=314.79, cost_usd=39.0625)


def test_normal_price_passes(state_file):
    ex = paper_executor({"candle close": 0.1300, "Hyperliquid mark": 0.1305})
    out = asyncio.run(ex.process_scan_results([row(0.1302, "STRONG_LONG")]))
    assert out["actions"] and "PURR/USDT" in ex.positions
    assert ex.last_price_rejections == []


def test_100x_price_rejected_for_entries(state_file):
    ex = paper_executor({"candle close": 0.1300, "Hyperliquid mark": 0.1305})
    out = asyncio.run(ex.process_scan_results([row(13.015, "STRONG_LONG")]))
    assert out["actions"] == [] and "PURR/USDT" not in ex.positions
    status = asyncio.run(ex.get_status())
    assert status["last_price_rejections"][0]["symbol"] == "PURR/USDT"
    assert status["last_price_rejections"][0]["price"] == 13.015


def test_100x_price_rejected_for_exits_and_stops(state_file):
    # The incident: both stored timeframes carried the bad bars, the live mark did not.
    ex = paper_executor({"candle close": 13.015, "Hyperliquid mark": 0.131})
    open_position(ex)
    cash = ex.engine.cash
    for signal in ("TRIM", "WAIT"):
        asyncio.run(ex.process_scan_results([row(13.015, signal)]))
        assert "PURR/USDT" in ex.positions and ex.trade_log == [] and ex.engine.cash == cash
        assert ex.positions["PURR/USDT"].peak_unrealized_pct == 0  # the stop rails never saw it
    assert len(ex.last_price_rejections) == 2
    # A market price the next cycle exits normally.
    ex.reference_provider = lambda s: {"candle close": 0.1319, "Hyperliquid mark": 0.1319}
    asyncio.run(ex.process_scan_results([row(0.13194, "TRIM")]))
    assert "PURR/USDT" not in ex.positions and ex.trade_log[0].exit_price == 0.13194


def test_missing_reference_behaviour(state_file):
    ex = paper_executor({})
    open_position(ex)
    # No reference: compared with the position's last known mark (its entry here).
    asyncio.run(ex.process_scan_results([row(13.015, "TRIM")]))
    assert "PURR/USDT" in ex.positions and len(ex.last_price_rejections) == 1
    # Candle close alone agreeing with the bad price is not enough either.
    ex.reference_provider = lambda s: {"candle close": 13.015}
    asyncio.run(ex.process_scan_results([row(13.015, "TRIM")]))
    assert "PURR/USDT" in ex.positions and len(ex.last_price_rejections) == 2
    # A price near the last mark is traded.
    ex.reference_provider = lambda s: {}
    asyncio.run(ex.process_scan_results([row(0.1319, "TRIM")]))
    assert "PURR/USDT" not in ex.positions


def test_zero_price_and_scanner_flag_are_skipped(state_file):
    ex = paper_executor({"Hyperliquid mark": 0.131})
    open_position(ex)
    asyncio.run(ex.process_scan_results([row(0.0, "TRIM")]))
    asyncio.run(ex.process_scan_results([row(0.1302, "TRIM", price_rejected={"price": 13.015, "reason": "x"})]))
    assert "PURR/USDT" in ex.positions and len(ex.last_price_rejections) == 2


# ---------------------------------------------------------------------------
# Ledger correction
# ---------------------------------------------------------------------------

def write_state(path, trades, cash=7345.35):
    path.write_text(json.dumps({
        "mode": "paper", "enabled": True, "initial_balance": 10000.0, "whitelist": ["PURR/USDT"],
        "positions": {"PURR/USDT": OPEN_PURR}, "trade_log": trades, "pair_map": {"PURR/USDT": "PURR"},
        "total_executions": 5,
        "engine_state": {"type": "paper", "cash": cash, "order_counter": 1886, "initial_balance": 10000.0,
                         "holdings": {"PURR/USDT": {"symbol": "PURR/USDT", "volume": 275.34, "avg_price": 0.14187}}},
    }))


def start(path):
    ex = Executor(mode="paper")
    asyncio.run(ex.initialize(["PURR/USDT"]))
    return ex


def test_correction_applies_once_with_exact_fields(state_file):
    write_state(state_file, [OTHER, PURR])
    ex = start(state_file)
    purr = ex.trade_log[1]
    pnl_pct = (0.13194 - 0.12409) / 0.12409 * 100
    pnl_usd = 39.0625 * (pnl_pct / 100)
    assert purr.exit_price == 0.13194
    assert purr.pnl_pct == pytest.approx(pnl_pct) and purr.pnl_usd == pytest.approx(pnl_usd)
    assert pnl_usd == pytest.approx(2.4711, abs=1e-4)
    c = purr.correction
    assert (c["original_exit_price"], c["original_pnl_usd"], c["original_pnl_pct"]) == (13.015, PURR["pnl_usd"], PURR["pnl_pct"])
    assert c["reason"] == "exit filled ~100x above market (price feed error)" and c["corrected_at"] > 0
    assert ex.engine.cash == pytest.approx(7345.35 - (PURR["pnl_usd"] - pnl_usd))
    # Time, size, reason and everything else stay; the open position is untouched.
    for key in ("entry_time", "exit_time", "volume", "cost_usd", "exit_signal", "entry_price", "order_ids"):
        assert getattr(purr, key) == PURR[key]
    assert ex.trade_log[0].to_dict() == {**OTHER}
    assert ex.positions["PURR/USDT"].entry_price == 0.14187 and ex.engine.holdings["PURR/USDT"].volume == 275.34
    # Persisted.
    saved = json.loads(state_file.read_text())
    assert saved["trade_log"][1]["exit_price"] == 0.13194 and saved["trade_log"][1]["correction"]
    assert saved["engine_state"]["cash"] == pytest.approx(ex.engine.cash)
    assert "correction" not in saved["trade_log"][0]

    # Second startup: nothing more happens.
    again = start(state_file)
    assert again.engine.cash == pytest.approx(ex.engine.cash)
    assert again.trade_log[1].to_dict() == purr.to_dict()
    assert again._apply_ledger_corrections() == 0


def test_correction_is_a_no_op_without_the_trade(state_file):
    write_state(state_file, [OTHER])
    before = state_file.read_text()
    ex = start(state_file)
    assert ex.engine.cash == 7345.35 and ex.trade_log[0].correction is None
    assert state_file.read_text() == before  # not even re-saved
    # Only the exact record is corrected.
    write_state(state_file, [dict(PURR, exit_time=PURR["exit_time"] + 86400)])
    assert start(state_file).trade_log[0].exit_price == 13.015


def test_correction_is_paper_only(state_file):
    ex = Executor(mode="live")
    ex.engine = PaperEngine(10000)
    ex.trade_log = [executor_mod.ExecutorTrade(**{k: v for k, v in PURR.items() if k != "kraken_pair"})]
    assert ex._apply_ledger_corrections() == 0 and ex.trade_log[0].exit_price == 13.015


def test_audit_before_and_after_correction(state_file):
    assert _LEDGER_CORRECTIONS[0]["exit_price"] == 13.015
    assert "bad exit price" in closure_issue(PURR)  # an uncorrected ledger stays flagged
    write_state(state_file, [OTHER, PURR])
    ex = start(state_file)
    rows = ex.get_trades()
    assert rows[1]["quality_issue"] is None and rows[1]["correction"]["original_exit_price"] == 13.015
    result = performance([], rows, {}, 10000, 1790700000)
    assert result["flagged_closed_trades"] == 0 and result["closed_trades"] == 2
    assert result["realized_pnl_usd"] == pytest.approx(OTHER["pnl_usd"] + rows[1]["pnl_usd"])
