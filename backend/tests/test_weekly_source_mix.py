"""The weekly band incident (found 2026-10-01): exchange weeks merged into Hyperliquid weekly series.

A failed Hyperliquid read fell back to Binance/Bybit and the bars were merged into the stored
series by timestamp. Hyperliquid's weeks open Thursday 00:00 UTC, the exchanges' Monday 00:00, so
the weekly series ended up with two "weeks" per week (the Monday bar often stored while still
open) that no later Hyperliquid read ever replaced. SMA20/EMA21 then spanned about ten weeks
instead of twenty: ZEC's band read 1043 against 796 from Hyperliquid's own weeks, and heat never
reached the forced-TRIM level at the 23 and 27 Sep tops.
"""
import asyncio
import pickle
import time
from unittest.mock import patch

import numpy as np

import data_fetcher
import hyperliquid_universe
from data_fetcher import SOURCE_CEX, SOURCE_HL, DataCache, OHLCVStore, on_hl_grid
from engines.heatmap_engine import compute_bmsb_series

DAY = 86_400_000
H4 = 4 * 3_600_000
WEEK = 7 * DAY
NOW = 1_790_870_400_000 + 12 * 3_600_000          # Thu 2026-10-01 12:00 UTC
THIS_WEEK = NOW // WEEK * WEEK                     # Hyperliquid's open week (Thursday 00:00)
ZEC = {"ZEC/USDT": {"symbol": "ZEC/USDT", "coin": "ZEC", "base": "ZEC", "quote": "USDC", "kind": "perpetual"}}


def bars(ts, close):
    ts = np.asarray(ts, dtype=float)
    close = np.asarray(close, dtype=float)
    return {"timestamp": ts, "open": close * 0.98, "high": close * 1.05, "low": close * 0.95,
            "close": close, "volume": np.ones_like(close)}


def rally(n=200, last=THIS_WEEK):
    """Hyperliquid weekly bars ending with the open week: flat, then a 25-week rally."""
    ts = last - (n - 1 - np.arange(n)) * WEEK
    close = np.where(np.arange(n) < n - 25, 300.0, 300.0 * 1.09 ** (np.arange(n) - (n - 25)))
    return bars(ts, close)


def exchange_weeks(hl, n=None):
    """The same market's exchange weeks (opening Monday, three days before the Thursday they precede)."""
    n = len(hl["timestamp"]) if n is None else n
    ts = hl["timestamp"][-n:] - 3 * DAY
    return bars(ts, hl["close"][-n:] * 0.995)


def mid(series):
    return compute_bmsb_series(np.asarray(series["close"]), np.asarray(series["timestamp"]))["mid"][-1]["value"]


def legacy_union(a, b):
    """The merge before the fix: union by timestamp, fetched values winning."""
    ts = np.concatenate([a["timestamp"], b["timestamp"]])
    _, rev = np.unique(ts[::-1], return_index=True)
    idx = (len(ts) - 1 - rev)[-200:]
    return {f: np.concatenate([a[f], b[f]])[idx] for f in a}


def test_hyperliquid_weeks_open_on_thursday_and_exchange_weeks_do_not_fit():
    assert time.strftime("%a", time.gmtime(THIS_WEEK / 1000)) == "Thu"
    hl = rally()
    assert on_hl_grid(hl["timestamp"], "1w").all()
    assert not on_hl_grid(exchange_weeks(hl)["timestamp"], "1w").any()
    # The mechanism: merged by timestamp the two sources interleave, and the 20-bar average
    # covers ten weeks of a rally instead of twenty, so the band sits far too high.
    mixed = legacy_union(hl, exchange_weeks(hl, 6))
    assert mid(mixed) > mid(hl) * 1.05


def test_weekly_close_is_hyperliquids_thursday_close():
    """Weekly series are read once per closed week; the close must be Hyperliquid's (Thursday)."""
    thu = THIS_WEEK / 1000
    assert DataCache._last_close("1w", thu + 3600) == thu
    assert DataCache._last_close("1w", thu - 3600) == thu - 7 * 86400
    store = OHLCVStore()
    store.update("ZEC/USDT", "1w", rally(last=THIS_WEEK - WEEK))
    with patch("time.time", return_value=thu + 300):
        store._updated_at["ZEC/USDT|1w"] = time.monotonic() - (86400 + 300)   # read on Wednesday
        # After Thursday 00:00 the bar read on Wednesday is partial: the series is not complete
        # (with Monday as the close it counted as complete until the next Monday).
        assert not store.complete("ZEC/USDT", "1w")
        store._updated_at["ZEC/USDT|1w"] = time.monotonic() - 120             # read after the close
        assert store.complete("ZEC/USDT", "1w")


def _fetch(store, hl_result, cex_result, symbol="ZEC/USDT", tf="1w", markets=ZEC):
    calls = []

    async def hl(*a, **k):
        return hl_result

    async def cex(*a, **k):
        calls.append(a)
        return cex_result

    only = set()
    with patch.object(data_fetcher, "_ohlcv_store", store), patch.object(data_fetcher, "_cache", DataCache()), \
            patch.object(data_fetcher, "_ccxt_only", only), \
            patch.object(data_fetcher, "_fetch_ohlcv_hyperliquid", hl), \
            patch.object(data_fetcher, "_fetch_ohlcv_ccxt", cex), \
            patch.dict(hyperliquid_universe.MARKETS, markets, clear=True):
        out = asyncio.run(data_fetcher.fetch_ohlcv(symbol, tf))
    return out, calls, only


def test_failed_hyperliquid_read_keeps_the_weekly_series():
    hl = rally()
    store = OHLCVStore()
    store.update("ZEC/USDT", "1w", hl, full_fetch_target=200)
    store._updated_at["ZEC/USDT|1w"] -= 8 * 86400                 # due for a read
    out, calls, only = _fetch(store, None, exchange_weeks(hl, 3))
    assert not calls and not only
    np.testing.assert_array_equal(out["timestamp"], hl["timestamp"])
    assert mid(out) == mid(hl)


def test_exchange_bars_never_enter_a_hyperliquid_series():
    hl = rally()
    store = OHLCVStore()
    store.update("ZEC/USDT", "1w", hl)
    # Weekly: refused outright, older or not (another week).
    out = store.update("ZEC/USDT", "1w", exchange_weeks(hl, 200), source=SOURCE_CEX)
    np.testing.assert_array_equal(out["timestamp"], hl["timestamp"])
    assert store.stats["fallback_bars_refused"] == 200
    # 4h: only older history before the first Hyperliquid bar (deepening a new listing).
    t0 = NOW // H4 * H4 - 99 * H4
    h4 = bars(t0 + np.arange(100) * H4, np.full(100, 10.0))
    store.update("NEW/USDT", "4h", h4)
    cex = bars(t0 + np.arange(-50, 100) * H4, np.full(150, 10.1))
    out = store.update("NEW/USDT", "4h", cex, source=SOURCE_CEX)
    assert len(out["timestamp"]) == 150
    assert (out["close"][:50] == 10.1).all() and (out["close"][50:] == 10.0).all()
    assert store.source("NEW/USDT", "4h") == SOURCE_HL


def test_fetched_range_replaces_stored_bars_and_drops_foreign_ones():
    """The ongoing check: a fresh read's bars replace the stored ones at the same timestamps, and
    stored bars inside the read range that Hyperliquid does not have are dropped."""
    hl = rally()
    store = OHLCVStore()
    store._store["ZEC/USDT|1w"] = legacy_union(hl, exchange_weeks(hl, 6))
    store._updated_at["ZEC/USDT|1w"] = time.monotonic()
    assert len(store.get("ZEC/USDT", "1w")["timestamp"]) == 200          # 194 weeks + 6 exchange weeks
    out = store.update("ZEC/USDT", "1w", {f: v[-10:] for f, v in hl.items()})
    assert on_hl_grid(out["timestamp"], "1w").all()
    assert store.stats["bars_dropped"] == 6
    # 1d: a stored close that disagrees with a fresh read of the same day is replaced.
    t0 = NOW // DAY * DAY - 9 * DAY
    d = bars(t0 + np.arange(10) * DAY, np.arange(10) + 100.0)
    store.update("ETH/USDT", "1d", d)
    store._store["ETH/USDT|1d"]["close"][5] = 104.9                      # an exchange's close
    out = store.update("ETH/USDT", "1d", {f: v[3:] for f, v in d.items()})
    assert out["close"][5] == 105.0 and store.stats["bars_revised"] == 1


def _legacy_pickle(tmp_path, store_data, version=3):
    path = tmp_path / "ohlcv_cache.pkl"
    now = time.time()
    with open(path, "wb") as f:
        pickle.dump({"version": version, "history_targets": {k: 200 for k in store_data},
                     "observed_at": {k: now - 600 for k in store_data}, "store": store_data,
                     "saved_at": now - 600}, f)
    return path


def test_mixed_weekly_series_is_cleaned_on_load_and_read_in_full(tmp_path):
    hl = rally()
    mixed = legacy_union(hl, exchange_weeks(hl, 6))
    exchange_only = exchange_weeks(rally())
    path = _legacy_pickle(tmp_path, {"ZEC/USDT|1w": mixed, "XYZ/USDT|1w": exchange_only})
    store = OHLCVStore()
    assert store.load_from_disk(path)
    cleaned = store.get("ZEC/USDT", "1w")
    assert on_hl_grid(cleaned["timestamp"], "1w").all() and len(cleaned["timestamp"]) == 194
    assert abs(mid(cleaned) / mid(hl) - 1) < 1e-9
    assert store.needs_full_fetch("ZEC/USDT", "1w")
    assert not store.complete("ZEC/USDT", "1w")
    # An exchange-only weekly series is consistent: kept, labelled as such.
    assert store.source("XYZ/USDT", "1w") == SOURCE_CEX and len(store.get("XYZ/USDT", "1w")["timestamp"]) == 200
    # The full Hyperliquid read clears the flag, and it survives a save and load.
    store.update("ZEC/USDT", "1w", hl, full_fetch_target=200)
    assert not store.needs_full_fetch("ZEC/USDT", "1w")
    store.save_to_disk(path, force=True)
    again = OHLCVStore()
    again.load_from_disk(path)
    assert not again.needs_full_fetch("ZEC/USDT", "1w")
    assert again.source("XYZ/USDT", "1w") == SOURCE_CEX


def test_hyperliquid_replaces_an_exchange_series():
    store = OHLCVStore()
    t0 = NOW // DAY * DAY - 299 * DAY
    store.update("ABC/USDT", "1d", bars(t0 + np.arange(300) * DAY, np.full(300, 5.0)), source=SOURCE_CEX,
                 full_fetch_target=600)
    assert store.needs_full_fetch("ABC/USDT", "1d")                     # next Hyperliquid read is a full one
    hl = bars(t0 + np.arange(100, 300) * DAY, np.full(200, 5.2))
    out = store.update("ABC/USDT", "1d", hl, full_fetch_target=600)
    assert store.source("ABC/USDT", "1d") == SOURCE_HL
    assert (out["close"][:100] == 5.0).all() and (out["close"][100:] == 5.2).all()   # older history kept


def test_store_check_against_hyperliquid_repairs_once_and_resumes(tmp_path):
    hl_w = rally()
    t0 = NOW // DAY * DAY - 599 * DAY
    hl_d = bars(t0 + np.arange(600) * DAY, 100 + np.arange(600) * 0.1)
    # As production stored them: exchange weeks merged in (and a stretch of Thursday weeks missing),
    # and a few exchange closes on the daily series.
    mixed = legacy_union(hl_w, exchange_weeks(hl_w, 20))
    gap = (mixed["timestamp"] > THIS_WEEK - 15 * WEEK) & (mixed["timestamp"] < THIS_WEEK - 8 * WEEK) \
        & on_hl_grid(mixed["timestamp"], "1w")
    mixed = {f: v[~gap] for f, v in mixed.items()}
    bad_d = {f: v.copy() for f, v in hl_d.items()}
    bad_d["close"][-30:-25] *= 1.001
    path = _legacy_pickle(tmp_path, {"ZEC/USDT|1w": mixed, "ZEC/USDT|1d": bad_d})
    store = OHLCVStore()
    store.load_from_disk(path)

    consumers = []

    async def candles(session, coin, timeframe, limit=None, consumer="scanner"):
        consumers.append(consumer)
        return {"1w": hl_w, "1d": hl_d}[timeframe]

    with patch.object(data_fetcher, "_ohlcv_store", store), \
            patch.object(data_fetcher, "_fetch_hl_candles", candles), \
            patch.dict(hyperliquid_universe.MARKETS, ZEC, clear=True):
        assert data_fetcher.verify_due() == ["ZEC/USDT|1w", "ZEC/USDT|1d"]       # weekly first
        out = asyncio.run(data_fetcher.verify_store())
        assert out == {"checked": 2, "changed": 2, "due": 2}
        assert set(consumers) == {data_fetcher.VERIFY_CONSUMER}
        np.testing.assert_array_equal(store.get("ZEC/USDT", "1w")["timestamp"], hl_w["timestamp"])
        np.testing.assert_array_equal(store.get("ZEC/USDT", "1d")["close"], hl_d["close"])
        assert mid(store.get("ZEC/USDT", "1w")) == mid(hl_w)
        # Idempotent: nothing is due again before the interval, also after a restart.
        assert data_fetcher.verify_due() == []
        store.save_to_disk(path, force=True)
        again = OHLCVStore()
        again.load_from_disk(path)
        with patch.object(data_fetcher, "_ohlcv_store", again):
            assert data_fetcher.verify_due() == []
            assert data_fetcher.verify_due(now=time.time() + data_fetcher.VERIFY_INTERVAL_S + 1) == \
                ["ZEC/USDT|1w", "ZEC/USDT|1d"]
