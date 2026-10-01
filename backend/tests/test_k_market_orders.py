"""Orders on Hyperliquid's k markets (kPEPE, kSHIB, kBONK ...) leave under Hyperliquid's name.

The app keys them KPEPE (ticker_renames). Every order, close and leverage call is sent as "kPEPE",
and every position and fill read back is keyed KPEPE again. Mocks only: no network, no keys.
"""
import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import executor as executor_mod
import hyperliquid_data
import main
import manual_trader
from executor import Executor
from trading_engine import EngineError, HyperliquidEngine, PaperEngine

# A slice of Hyperliquid's meta: (name, szDecimals). The asset index is the position in the list.
UNIVERSE = [("BTC", 5), ("ETH", 4), ("SOL", 2), ("kPEPE", 0), ("BONK", 0), ("kBONK", 0), ("kNEIRO", 1), ("KAS", 0)]
INDEX = {name: i for i, (name, _) in enumerate(UNIVERSE)}


class FakeInfo:
    """The SDK's Info, as the engine uses it: name -> asset index -> szDecimals, user state, fills."""

    def __init__(self, positions=(), fills=()):
        self.asset_to_sz_decimals = {i: d for i, (_, d) in enumerate(UNIVERSE)}
        self._positions, self._fills = list(positions), list(fills)

    def name_to_asset(self, name):
        return INDEX[name]                                  # KeyError for "KPEPE", as the SDK

    def user_state(self, address):
        return {"marginSummary": {"accountValue": "1000", "totalMarginUsed": "10"},
                "assetPositions": [{"position": p} for p in self._positions]}

    def user_fills(self, address):
        return list(self._fills)


class FakeExchange:
    """The SDK's Exchange: builds the order wire as the SDK does (asset index from the name)."""

    def __init__(self, info):
        self.info, self.orders, self.leverage, self.closes = info, [], [], []

    def market_open(self, name, is_buy, sz, px=None, slippage=0.05):
        self.orders.append({"coin": name, "a": self.info.name_to_asset(name), "b": is_buy, "s": sz, "r": False})
        return {"status": "ok", "response": {"data": {"statuses": [{"filled": {"oid": 7, "avgPx": "0.0105", "totalSz": str(sz)}}]}}}

    def market_close(self, name, slippage=0.05):
        self.closes.append({"coin": name, "a": self.info.name_to_asset(name)})
        return {"status": "ok", "response": {"data": {"statuses": [{"filled": {"oid": 8}}]}}}

    def update_leverage(self, leverage, name, is_cross=True):
        self.info.name_to_asset(name)
        self.leverage.append((name, leverage, is_cross))


def fake_engine(**info_kw):
    eng = HyperliquidEngine.__new__(HyperliquidEngine)         # no key, no SDK, no network
    eng._info = FakeInfo(**info_kw)
    eng._exchange = FakeExchange(eng._info)
    eng._address = "0x" + "0" * 40
    eng._default_leverage, eng._leverage_cache, eng._order_counter = 3, {}, 0
    return eng


@pytest.fixture
def state_file(tmp_path):
    with patch.object(executor_mod, "_STATE_FILE", tmp_path / "executor_state.json"):
        yield


# ------------------------------------------------------------------ the engine boundary
def test_kpepe_order_leaves_as_kpepe_with_its_asset_index():
    eng = fake_engine()
    out = eng.buy("KPEPE/USDT", 95057.03, 0.01052, leverage=5)
    order = eng._exchange.orders[-1]
    assert order["coin"] == "kPEPE" and order["a"] == INDEX["kPEPE"] and order["b"] is True
    assert order["s"] == 95057                                  # kPEPE's szDecimals (0), floored
    assert eng._exchange.leverage == [("kPEPE", 5, True)]
    assert out["coin"] == "kPEPE" and out["volume"] == 95057
    eng.sell("KPEPE/USDT", 10.9, 0.0105)
    assert eng._exchange.orders[-1] == {"coin": "kPEPE", "a": INDEX["kPEPE"], "b": False, "s": 10, "r": False}


def test_k_market_size_uses_its_own_size_decimals():
    eng = fake_engine()
    eng.buy("KNEIRO/USDT", 1234.56, 0.41)
    assert eng._exchange.orders[-1]["coin"] == "kNEIRO" and eng._exchange.orders[-1]["s"] == 1234.5
    with pytest.raises(EngineError):
        eng.buy("KPEPE/USDT", 0.4, 0.0105)                     # under one k-unit: not sent
    assert len(eng._exchange.orders) == 1 and len(eng._exchange.leverage) == 1


def test_close_and_leverage_leave_as_kpepe():
    eng = fake_engine()
    eng.close_position("KPEPE/USDT")
    assert eng._exchange.closes == [{"coin": "kPEPE", "a": INDEX["kPEPE"]}]
    assert eng.set_leverage("KPEPE", 4)["coin"] == "kPEPE"
    eng.set_leverage("kPEPE", 2)                                # Hyperliquid's own name passes through
    assert eng._exchange.leverage == [("kPEPE", 4, True), ("kPEPE", 2, True)]


def test_normal_coins_are_unchanged():
    eng = fake_engine()
    eng.buy("BTC/USDT", 0.01234567, 81000.0, leverage=3)       # floored to BTC's szDecimals (5)
    assert eng._exchange.orders[-1] == {"coin": "BTC", "a": INDEX["BTC"], "b": True, "s": 0.01234, "r": False}
    eng.close_position("BTC/USDT")
    assert eng._exchange.closes[-1]["coin"] == "BTC"
    # The legacy per-token BONK stays BONK, separate from the k market.
    eng.buy("BONK/USDT", 1234.0, 0.00002)
    assert eng._exchange.orders[-1]["coin"] == "BONK" and eng._exchange.orders[-1]["a"] == INDEX["BONK"]
    eng.buy("KAS/USDT", 100.0, 0.08)                            # an ordinary K ticker
    assert eng._exchange.orders[-1]["coin"] == "KAS"


def test_positions_and_fills_read_back_under_the_app_key():
    pos = lambda coin, szi: {"coin": coin, "szi": szi, "entryPx": "0.0101", "unrealizedPnl": "1",
                             "marginUsed": "5", "leverage": {"type": "cross", "value": 3}}
    eng = fake_engine(positions=[pos("kPEPE", "95057"), pos("BTC", "-0.01")],
                      fills=[{"coin": "kPEPE", "side": "B", "sz": "95057", "px": "0.0105", "time": 2},
                             {"coin": "BTC", "side": "A", "sz": "0.01", "px": "81000", "time": 1}])
    ps = eng.get_portfolio()["positions"]
    assert [(p["coin"], p["symbol"]) for p in ps] == [("KPEPE", "KPEPE/USDT"), ("BTC", "BTC/USDT")]
    assert [f["coin"] for f in eng.get_fills()] == ["KPEPE", "BTC"]


# ------------------------------------------------------------------ the executor
def test_executor_sizes_kpepe_in_k_units(state_file):
    """$1,000 on kPEPE at 0.01052 (per 1,000 PEPE) is 95,057 k-units: 95,057,000 PEPE."""
    ex = Executor(mode="live", initial_balance=10000.0)
    ex.engine = fake_engine()
    ex.pair_map = {"KPEPE/USDT": "kPEPE"}
    ex.initialized = ex.enabled = True
    assert len(ex.whitelist) == 10                              # allocation $1,000 at 100%
    action = asyncio.run(ex._execute_entry("KPEPE/USDT", "STRONG_LONG", 0.01052, 1.0, "STRONG"))
    assert action
    order = ex.engine._exchange.orders[-1]
    assert order["coin"] == "kPEPE" and order["a"] == INDEX["kPEPE"]
    assert order["s"] == 95057 == int(1000 / 0.01052)
    assert abs(order["s"] * 0.01052 - 1000) < 0.01052           # within one k-unit of the notional
    assert abs(order["s"] * 1000 * 0.01052e-3 - 1000) < 0.02    # the same in tokens x per-token price
    p = ex.positions["KPEPE/USDT"]                              # recorded under the app's key
    assert p.exchange_pair == "kPEPE" and p.cost_usd == 1000.0 and ex.engine._exchange.leverage == [("kPEPE", 5, True)]


def test_live_pair_map_finds_k_markets_and_keeps_legacy_tokens_apart(state_file, monkeypatch):
    class M:
        def __init__(self, coin):
            self.coin = coin

    async def metrics():
        return {c: M(c) for c in ("BTC", "kPEPE", "kBONK", "KAS")}

    monkeypatch.setattr(hyperliquid_data, "fetch_hyperliquid_metrics", metrics)
    monkeypatch.setattr(executor_mod, "HyperliquidEngine", lambda: fake_engine())
    ex = Executor(mode="live")
    asyncio.run(ex.initialize(["BTC/USDT", "KPEPE/USDT", "KBONK/USDT", "BONK/USDT", "FLOKI/USDT", "KAS/USDT"]))
    assert ex.pair_map == {"BTC/USDT": "BTC", "KPEPE/USDT": "kPEPE", "KBONK/USDT": "kBONK", "KAS/USDT": "KAS"}


def test_paper_pair_map_is_unchanged(state_file):
    ex = Executor(mode="paper")
    asyncio.run(ex.initialize(["BTC/USDT", "KPEPE/USDT", "BONK/USDT", "FLOKI/USDT"]))
    assert isinstance(ex.engine, PaperEngine)
    assert ex.pair_map == {"BTC/USDT": "BTC", "KPEPE/USDT": "KPEPE", "BONK/USDT": "BONK", "FLOKI/USDT": "FLOKI"}


def test_wallet_positions_match_the_scan_row():
    ps = hyperliquid_data.parse_open_positions({"assetPositions": [
        {"position": {"coin": "kPEPE", "szi": "100", "entryPx": "0.01"}},
        {"position": {"coin": "BTC", "szi": "0.1", "entryPx": "80000"}},
        {"position": {"coin": "xyz:TSLA", "szi": "1", "entryPx": "300"}}]})
    assert [(p["coin"], p["symbol"]) for p in ps] == [("kPEPE", "KPEPE/USDT"), ("BTC", "BTC/USDT"),
                                                      ("xyz:TSLA", "xyz:TSLA/USDT")]


# ------------------------------------------------------------------ the manual trade endpoints
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("REFLEX_ADMIN_KEY", raising=False)
    monkeypatch.setattr(manual_trader, "_TRADES_FILE", tmp_path / "manual_trades.json")
    monkeypatch.setattr(manual_trader, "_journal", None)
    return TestClient(main.app)


def test_manual_trade_endpoints_with_kpepe(client, monkeypatch):
    info = FakeInfo(positions=[{"coin": "kPEPE", "szi": "-950", "entryPx": "0.0105", "leverage": {"type": "cross", "value": 3}},
                               {"coin": "BTC", "szi": "0.01", "entryPx": "81000", "leverage": {"type": "cross", "value": 3}}],
                    fills=[{"coin": "kPEPE", "side": "A", "sz": "950", "px": "0.0105", "time": 1}])
    monkeypatch.setattr(main, "_get_hl_info", lambda: info)
    addr = "0x" + "a" * 40
    ps = client.get(f"/api/trade/positions?address={addr}").json()["positions"]
    assert [p["coin"] for p in ps] == ["KPEPE", "BTC"] and ps[0]["side"] == "SHORT"
    assert [f["coin"] for f in client.get(f"/api/trade/fills?address={addr}").json()["fills"]] == ["KPEPE"]

    # The panel logs the order under KPEPE; a close reported from Hyperliquid's kPEPE finds it.
    r = client.post("/api/trade/log", json={"address": addr, "symbol": "KPEPE/USDT", "coin": "KPEPE", "side": "SHORT",
                                            "size_usd": 10, "volume": 950, "leverage": 3, "entry_price": 0.0105})
    assert r.status_code == 200 and r.json()["trade"]["symbol"] == "KPEPE/USDT" and r.json()["trade"]["coin"] == "KPEPE"
    r = client.post("/api/trade/log-close", json={"symbol": "kPEPE/USDT", "exit_price": 0.0100})
    assert r.status_code == 200 and r.json()["trade"]["symbol"] == "KPEPE/USDT" and r.json()["trade"]["status"] == "CLOSED"


def test_executor_leverage_endpoint_with_kpepe(client, monkeypatch):
    ex = Executor(mode="live")
    ex.engine, ex.initialized = fake_engine(), True
    monkeypatch.setattr(executor_mod, "_executor", ex)
    r = client.post("/api/executor/hl/leverage", json={"coin": "KPEPE", "leverage": 4})
    assert r.status_code == 200 and r.json()["coin"] == "kPEPE"
    assert ex.engine._exchange.leverage == [("kPEPE", 4, True)]
    r = client.post("/api/executor/hl/leverage", json={"coin": "BTC", "leverage": 2})
    assert r.json()["coin"] == "BTC"
