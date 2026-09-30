"""Price sanity: the PURR/USDT 13.015 incident (2026-09-27) and the guards around it."""
import asyncio
import time
from unittest.mock import patch

import numpy as np

import data_fetcher
import hyperliquid_universe
import price_sanity
from hyperliquid_data import HyperliquidMetrics
from price_sanity import PRICE_SANITY_MAX_RATIO, price_rejection, series_consistent

H4 = 4 * 3600 * 1000
T0 = 1790000000000 // H4 * H4


def series(closes, start=T0):
    closes = np.asarray(closes, dtype=float)
    ts = np.arange(len(closes), dtype=float) * H4 + start
    return {"timestamp": ts, "open": closes, "high": closes, "low": closes, "close": closes,
            "volume": np.ones_like(closes)}


PURR_MARKET = {"PURR/USDT": {"symbol": "PURR/USDT", "coin": "PURR", "base": "PURR",
                             "quote": "USDC", "kind": "perpetual"}}


def test_constant_and_threshold():
    assert PRICE_SANITY_MAX_RATIO == 3.0
    assert price_rejection(0.29, {"candle close": 0.1}) is None
    assert price_rejection(0.034, {"candle close": 0.1}) is None
    assert "3.1x" in price_rejection(0.31, {"candle close": 0.1})
    assert price_rejection(13.015, {"Hyperliquid mark": 0.131})
    assert price_rejection(0, {}) and price_rejection(None, {}) and price_rejection(float("nan"), {})


def test_missing_reference_falls_back_to_last_mark():
    # No reference at all: nothing to compare against, unless a position has a mark.
    assert price_rejection(13.015, {}) is None
    assert price_rejection(13.015, {}, last_mark=0.12409)
    assert price_rejection(0.131, {}, last_mark=0.12409) is None
    # The candle close shares the scan price's source, so on its own it cannot vouch for it.
    assert price_rejection(13.015, {"candle close": 13.015}, last_mark=0.12409)
    # A live Hyperliquid reference outranks the last mark (a real move since entry is fine).
    assert price_rejection(0.5, {"Hyperliquid mark": 0.49}, last_mark=0.12409) is None


def test_series_consistency():
    hl = series([0.13] * 10)
    assert series_consistent(hl, series([0.1302, 0.1311], start=T0 + 8 * H4)) is True
    assert series_consistent(hl, series([13.02, 13.015], start=T0 + 8 * H4)) is False
    assert series_consistent(hl, series([0.13], start=T0 + 20 * H4)) is None
    assert series_consistent(None, hl) is None


def _run_fetch(symbol, stored, hl_result, cex_result, pinned=False):
    store, cache = data_fetcher.OHLCVStore(), data_fetcher.DataCache()
    if stored is not None:
        store.update(symbol, "4h", stored)

    async def hl(*a, **k):
        return hl_result

    async def cex(*a, **k):
        return cex_result

    only = {symbol} if pinned else set()
    with patch.object(data_fetcher, "_ohlcv_store", store), patch.object(data_fetcher, "_cache", cache), \
            patch.object(data_fetcher, "_ccxt_only", only), \
            patch.object(data_fetcher, "_fetch_ohlcv_hyperliquid", hl), \
            patch.object(data_fetcher, "_fetch_ohlcv_ccxt", cex), \
            patch.dict(hyperliquid_universe.MARKETS, PURR_MARKET, clear=True):
        out = asyncio.run(data_fetcher.fetch_ohlcv(symbol, "4h"))
    return out, only


def test_ticker_fallback_cannot_replace_the_hyperliquid_series():
    """Root cause: a failed Hyperliquid fetch fell back to Binance/Bybit "PURRUSDT",
    another instrument about 100x the token, and its last two bars became the scan
    price (13.015) and one closed bar (z-score 11.5)."""
    stored = series([0.12409] * 30)
    other = series([13.02, 13.015], start=T0 + 28 * H4)
    out, pinned = _run_fetch("PURR/USDT", stored, None, other)
    assert float(out["close"][-1]) == 0.12409
    assert "PURR/USDT" not in pinned
    # Already pinned to the fallback: the bad bars are refused and the pin dropped.
    out, pinned = _run_fetch("PURR/USDT", stored, None, other, pinned=True)
    assert float(out["close"][-1]) == 0.12409
    assert "PURR/USDT" not in pinned
    # Nothing stored to compare with: a Hyperliquid market does not take unverified bars.
    out, pinned = _run_fetch("PURR/USDT", None, None, other)
    assert out is None and "PURR/USDT" not in pinned


def test_consistent_fallback_still_works():
    stored = series([0.13] * 30)
    same = series([0.1302, 0.1311], start=T0 + 28 * H4)
    out, pinned = _run_fetch("PURR/USDT", stored, None, same)
    assert float(out["close"][-1]) == 0.1311
    assert "PURR/USDT" in pinned


def test_scan_row_price_is_guarded_and_flagged():
    import scanner

    store = data_fetcher.OHLCVStore()
    store.update("PURR/USDT", "4h", series([0.1302] * 10 + [13.02, 13.015]))

    class Cache:
        _last_hl_metrics = {"PURR/USDT": HyperliquidMetrics(coin="PURR", mark_price=0.131, timestamp=time.time()),
                            "BTC/USDT": HyperliquidMetrics(coin="BTC", mark_price=65000, timestamp=time.time())}

    bad = {"symbol": "PURR/USDT", "timeframe": "4h", "price": 13.015}
    good = {"symbol": "BTC/USDT", "timeframe": "4h", "price": 65100.0}
    unknown = {"symbol": "XMR/BTC", "timeframe": "4h", "price": 0.004}
    with patch.object(data_fetcher, "_ohlcv_store", store), \
            patch.object(price_sanity, "live_references", price_sanity.live_references):
        assert scanner.guard_row_prices({"4h": [bad, good, unknown]}, Cache()) == 1
        assert bad["price"] == 0.1302
        assert bad["price_rejected"]["price"] == 13.015
        assert "price_rejected" not in good and good["price"] == 65100.0
        assert "price_rejected" not in unknown
        # Not refreshed yet: the substitute stays flagged.
        assert scanner.guard_row_prices({"4h": [bad]}, Cache()) == 1
        assert bad["price_rejected"]
        # Refreshed with a real close: the flag goes.
        bad["price"] = 0.1319
        assert scanner.guard_row_prices({"4h": [bad]}, Cache()) == 0
        assert "price_rejected" not in bad
