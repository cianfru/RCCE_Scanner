import asyncio

import pytest

import exchange_derivatives_data as ed


def _bars(coin):
    seed = sum(map(ord, coin))
    return [{"buySellRatio": str(1 + ((seed + i) % 7 - 3) / 20), "buyVol": str(100 + seed % 13 + i),
             "sellVol": str(100 + (seed + 2 * i) % 11), "timestamp": 1_790_000_000_000 + i * 14_400_000}
            for i in range(30)]


@pytest.fixture
def exchanges(monkeypatch):
    calls = {"taker": 0, "other": 0, "tickers": 0}

    async def taker(session, coin, sem, limit=30):
        calls["taker"] += 1
        return None if coin == "PURR" else {"coin": coin, "bars": _bars(coin)}

    async def other(session, coin, sem, *a, **k):
        calls["other"] += 1
        return None

    async def tickers(session):
        calls["tickers"] += 1
        return {}
    monkeypatch.setattr(ed, "_fetch_binance_taker_ratio", taker)
    for name in ("_fetch_binance_retail_lsr", "_fetch_binance_top_lsr", "_fetch_binance_oi_history",
                 "_fetch_bybit_oi", "_fetch_okx_oi"):
        monkeypatch.setattr(ed, name, other)
    monkeypatch.setattr(ed, "_fetch_binance_spot_tickers", tickers)
    monkeypatch.setattr(ed, "_fetch_binance_futures_tickers", tickers)
    monkeypatch.setattr(ed, "_cache", ed._Cache())
    monkeypatch.setattr(ed, "_cvd_cache", ed._Cache())
    return calls


def test_cvd_only_gives_the_same_cvd_with_one_request_per_coin(exchanges):
    symbols = ["BTC/USDT", "ETH/USDT", "HYPE/USDT", "PURR/USDC"]
    changes = {"BTC/USDT": 2.5, "ETH/USDT": -1.0}
    _, full, _ = asyncio.run(ed.fetch_exchange_derivatives(symbols, changes))
    full_calls = dict(exchanges)
    metrics, slim, _ = asyncio.run(ed.fetch_exchange_derivatives(symbols, changes, cvd_only=True))
    assert metrics == {}
    assert set(slim) == set(full) == {"BTC", "ETH", "HYPE"}
    from dataclasses import asdict
    for coin in full:
        a, b = asdict(slim[coin]), asdict(full[coin])
        a.pop("timestamp"), b.pop("timestamp")              # when each was computed
        assert a == b
    assert exchanges["taker"] - full_calls["taker"] == 4
    assert exchanges["other"] == full_calls["other"] and exchanges["tickers"] == full_calls["tickers"]


def test_cvd_only_is_cached_apart_from_the_full_fetch(exchanges):
    asyncio.run(ed.fetch_exchange_derivatives(["BTC/USDT"], None, cvd_only=True))
    asyncio.run(ed.fetch_exchange_derivatives(["BTC/USDT"], None, cvd_only=True))
    assert exchanges["taker"] == 1
    metrics, _, _ = asyncio.run(ed.fetch_exchange_derivatives(["BTC/USDT"], None))   # debug endpoints: full
    assert "BTC/USDT" in metrics and exchanges["other"] == 5
