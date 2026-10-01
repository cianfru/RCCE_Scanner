"""Every live order size is floored to the market's szDecimals from Hyperliquid's meta.

The executor sizes by price (BTC to 8 decimals); Hyperliquid takes at most szDecimals (BTC 5), so
the engine floors every size it sends: buys, sells and fallback closes. Flooring never rounds up, so
a close never exceeds the position, and a size that floors to zero is refused before any call.
Mocks only: no network, no keys.
"""
import asyncio
import math
from unittest.mock import patch

import pytest

import executor as executor_mod
from executor import Executor, ExecutorPosition
from test_k_market_orders import INDEX, FakeExchange, FakeInfo, fake_engine
from trading_engine import EngineError


@pytest.fixture
def state_file(tmp_path):
    with patch.object(executor_mod, "_STATE_FILE", tmp_path / "executor_state.json"):
        yield


@pytest.mark.parametrize("symbol, volume, sent", [
    ("BTC/USDT", 0.123456789, 0.12345),         # szDecimals 5
    ("ETH/USDT", 1.23456789, 1.2345),           # szDecimals 4
    ("SOL/USDT", 0.29, 0.29),                   # 0.29 is 0.28999... as a float; not floored a step
    ("SOL/USDT", 12.3456, 12.34),               # szDecimals 2
    ("KPEPE/USDT", 95057.9, 95057),             # a k market at 0
    ("KNEIRO/USDT", 1234.56, 1234.5),           # a k market at 1
    ("KAS/USDT", 1234.9, 1234),                 # szDecimals 0
    ("BTC/USDT", 0.01234, 0.01234),             # already on the step: unchanged
])
def test_every_market_floors_to_its_size_decimals(symbol, volume, sent):
    for side in ("buy", "sell"):
        eng = fake_engine()
        out = getattr(eng, side)(symbol, volume, 1.0, leverage=3)
        order = eng._exchange.orders[-1]
        assert order["s"] == sent and out["volume"] == sent
        assert order["b"] is (side == "buy")
        assert order["s"] <= volume                                   # never rounded up


@pytest.mark.parametrize("symbol, volume", [
    ("BTC/USDT", 0.000004),        # under one BTC step (0.00001)
    ("ETH/USDT", 0.00009),
    ("KPEPE/USDT", 0.4),           # under one k-unit
    ("BTC/USDT", 0.0),
    ("BTC/USDT", -0.5),
    ("BTC/USDT", math.nan),
    ("BTC/USDT", math.inf),
])
def test_a_size_that_floors_to_zero_is_refused_before_any_call(symbol, volume):
    eng = fake_engine()
    for side in ("buy", "sell"):
        with pytest.raises(EngineError):
            getattr(eng, side)(symbol, volume, 1.0, leverage=3)
    assert eng._exchange.orders == [] and eng._exchange.leverage == []


def test_size_decimals_come_from_meta_when_the_cached_map_misses():
    class LateInfo(FakeInfo):
        def name_to_asset(self, name):
            if name == "NEWCOIN":
                raise KeyError(name)                                 # listed after the SDK loaded
            return super().name_to_asset(name)

        def meta(self):
            return {"universe": [{"name": "NEWCOIN", "szDecimals": 1}]}

    eng = fake_engine()
    eng._info = LateInfo()
    eng._exchange = FakeExchange(eng._info)
    assert eng._order_size("NEWCOIN/USDT", 12.345) == 12.3
    eng._info.meta = lambda: {"universe": []}
    with pytest.raises(EngineError):                                 # no szDecimals: no order
        eng._order_size("NEWCOIN/USDT", 12.345)


class FailingClose(FakeExchange):
    def market_close(self, name, slippage=0.05):
        raise RuntimeError("market_close unavailable")


@pytest.mark.parametrize("side, closing_is_buy", [("LONG", False), ("SHORT", True)])
def test_fallback_close_never_exceeds_the_position(state_file, side, closing_is_buy):
    """A position recorded at the executor's 8 decimals closes, on the fallback path, at most its size."""
    ex = Executor(mode="live", initial_balance=10000.0)
    ex.engine = fake_engine()
    ex.engine._exchange = FailingClose(ex.engine._info)
    ex.initialized = ex.enabled = True
    ex.pair_map = {"BTC/USDT": "BTC"}
    ex.positions["BTC/USDT"] = ExecutorPosition(symbol="BTC/USDT", exchange_pair="BTC", side=side,
                                                entry_price=81000.0, volume=0.01234567, cost_usd=1000.0)
    assert asyncio.run(ex._execute_exit("BTC/USDT", "TRIM", 82000.0))
    order = ex.engine._exchange.orders[-1]
    assert order["coin"] == "BTC" and order["b"] is closing_is_buy
    assert order["s"] == 0.01234 and order["s"] <= 0.01234567
    assert "BTC/USDT" not in ex.positions


def test_executor_btc_entry_is_sent_at_five_decimals(state_file):
    """$1,000 of BTC at 81,000 is 0.01234568 at the executor's 8 decimals; 0.01234 is sent."""
    ex = Executor(mode="live", initial_balance=10000.0)
    ex.engine = fake_engine()
    ex.pair_map = {"BTC/USDT": "BTC"}
    ex.initialized = ex.enabled = True
    assert asyncio.run(ex._execute_entry("BTC/USDT", "STRONG_LONG", 81000.0, 1.0, "STRONG"))
    order = ex.engine._exchange.orders[-1]
    assert order == {"coin": "BTC", "a": INDEX["BTC"], "b": True, "s": 0.01234, "r": False}
    assert ex.positions["BTC/USDT"].cost_usd == 1000.0                # the notional is unchanged
