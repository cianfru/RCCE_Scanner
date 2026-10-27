import asyncio

import pytest

import bybit_futures_data as bf


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(bf, "_cache", bf._Cache())
    monkeypatch.setattr(bf, "_failed_at", None)


ROWS = [
    {"symbol": "BTCUSDT", "fundingRate": "0.0001", "markPrice": "100000", "openInterestValue": "5000000000"},
    {"symbol": "1000PEPEUSDT", "fundingRate": "0.0002", "markPrice": "0.01", "openInterestValue": "100"},
    {"symbol": "PEPEUSDT", "fundingRate": "0.0003", "markPrice": "0.00001", "openInterestValue": "200"},
    {"symbol": "1000BONKUSDT", "fundingRate": "0.0004", "markPrice": "0.02", "openInterestValue": "300"},
    {"symbol": "10000BONKUSDT", "fundingRate": "0.0005", "markPrice": "0.2", "openInterestValue": "400"},
    {"symbol": "BTCPERP", "fundingRate": "0.1", "markPrice": "1", "openInterestValue": "1"},
    {"symbol": "BTC-26DEC25", "fundingRate": "0.1", "markPrice": "1", "openInterestValue": "1"},
]


def test_tickers_map_to_scanner_symbols_with_8h_funding_made_hourly():
    out = bf._parse_tickers(ROWS, 1.0)
    assert set(out) == {"BTC/USDT", "PEPE/USDT", "BONK/USDT"}           # USDC perps, dated futures out
    btc = out["BTC/USDT"]
    assert btc.funding_rate_raw == pytest.approx(0.0001) and btc.funding_rate == pytest.approx(0.0001 / 8)
    assert btc.open_interest == 5e9 and btc.mark_price == 100000 and btc.coin == "BTC"
    assert out["PEPE/USDT"].funding_rate_raw == pytest.approx(0.0003)     # unprefixed listing wins
    assert out["BONK/USDT"].funding_rate_raw == pytest.approx(0.0004)     # first prefixed listing kept


def test_spot_pairs_never_trigger_a_request(monkeypatch):
    async def boom():
        raise AssertionError("no request for symbols Bybit cannot have")
    monkeypatch.setattr(bf, "_fetch_all", boom)
    assert asyncio.run(bf.fetch_bybit_futures_metrics(["PURR/USDC", "HYPE/USDC"])) == {}


def test_one_request_serves_the_cache_and_a_failure_backs_off(monkeypatch):
    calls = []

    async def fetch_all():
        calls.append(1)
        return bf._parse_tickers(ROWS, 1.0)
    monkeypatch.setattr(bf, "_fetch_all", fetch_all)
    got = asyncio.run(bf.fetch_bybit_futures_metrics(["BTC/USDT", "PURR/USDC"]))
    assert set(got) == {"BTC/USDT"}
    assert set(asyncio.run(bf.fetch_bybit_futures_metrics(["PEPE/USDT"]))) == {"PEPE/USDT"}
    assert calls == [1]

    bf._cache.expires_at = 0                                             # cache expired; Bybit down
    async def down():
        calls.append("down")
        raise RuntimeError("403")
    monkeypatch.setattr(bf, "_fetch_all", down)
    assert set(asyncio.run(bf.fetch_bybit_futures_metrics(["BTC/USDT"]))) == {"BTC/USDT"}   # last good
    asyncio.run(bf.fetch_bybit_futures_metrics(["BTC/USDT"]))
    assert calls == [1, "down"]                                          # backed off, no retry


def test_ccxt_is_not_used():
    import inspect
    assert "ccxt" not in inspect.getsource(bf).replace("(no ccxt:", "")
