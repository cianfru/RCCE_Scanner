"""Stablecoin supply from DefiLlama's list: USDT + USDC now vs a week ago."""
import asyncio

import market_data
from market_data import parse_llama_stablecoins


def _asset(sym, now, week):
    return {"symbol": sym, "circulating": {"peggedUSD": now}, "circulatingPrevWeek": {"peggedUSD": week}}


def test_parse_sums_usdt_usdc_and_trend():
    d = parse_llama_stablecoins({"peggedAssets": [_asset("USDT", 180e9, 175e9), _asset("USDC", 75e9, 74e9),
                                                  _asset("USDS", 7e9, 1e9)]})
    assert d.usdt_market_cap == 180e9 and d.usdc_market_cap == 75e9 and d.total_stablecoin_cap == 255e9
    assert d.change_7d_pct == round((255 - 249) / 249 * 100, 2) and d.trend == "EXPANDING"


def test_parse_contracting_and_stable():
    assert parse_llama_stablecoins({"peggedAssets": [_asset("USDT", 170e9, 180e9), _asset("USDC", 70e9, 70e9)]}).trend == "CONTRACTING"
    assert parse_llama_stablecoins({"peggedAssets": [_asset("USDT", 180e9, 179.5e9), _asset("USDC", 70e9, 70e9)]}).trend == "STABLE"


def test_parse_first_usdt_only_and_empty():
    d = parse_llama_stablecoins({"peggedAssets": [_asset("USDT", 180e9, 180e9), _asset("usdt", 1e9, 1e9), _asset("USDC", 70e9, 70e9)]})
    assert d.usdt_market_cap == 180e9
    assert parse_llama_stablecoins({"peggedAssets": []}) is None
    assert parse_llama_stablecoins({}) is None


def test_fetch_falls_back_when_llama_fails(monkeypatch):
    market_data._stablecoin_cache.data = None
    market_data._stablecoin_cache.expires_at = 0.0

    class Resp:
        def __init__(self, url):
            self.url = url
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        def raise_for_status(self):
            if "llama" in self.url:
                raise RuntimeError("blocked")
        async def json(self):
            return [{"id": "tether", "market_cap": 180e9}, {"id": "usd-coin", "market_cap": 70e9}]

    class Session:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        def get(self, url):
            return Resp(url)

    monkeypatch.setattr(market_data.aiohttp, "ClientSession", Session)
    d = asyncio.run(market_data.fetch_stablecoin_supply())
    assert d.total_stablecoin_cap == 250e9
    market_data._stablecoin_cache.data = None
    market_data._stablecoin_cache.expires_at = 0.0
