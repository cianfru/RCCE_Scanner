"""The shared Hyperliquid weight budget (hl_calls.Budget), candle weight, 429 backoff, and the
scanner's startup: restored markets are scanned from stored candles, with the same results."""
import asyncio
import json
from unittest import mock

import numpy as np
import pytest

import data_fetcher
import hl_calls
import scanner
from scan_schedule import ScanSchedule

H4 = 14_400


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def drain(budget, clock, demand, seconds, step=0.05):
    """Every consumer in ``demand`` (name -> weight per call) asks as often as it is allowed for
    ``seconds``. Returns the weight each one got."""
    got = {name: 0 for name in demand}
    end = clock.t + seconds
    while clock.t < end:
        for name in sorted(demand, key=lambda n: budget.consumers[n]["priority"]):
            while budget.try_take(name, demand[name]) == 0:
                got[name] += demand[name]
        clock.t += step
    return got


# --- the budget --------------------------------------------------------------------------------

def test_total_stays_under_the_target_and_priority_decides_who_waits():
    clock = Clock()
    b = hl_calls.Budget(per_min=1000, clock=clock)
    got = drain(b, clock, {"scanner": 20, "positions": 2, "fills": 20, "cohorts": 2}, 600)
    per_min = {k: v / 10 for k, v in got.items()}
    assert sum(per_min.values()) <= 1000 + hl_calls.BURST / 10 + 1
    assert per_min["scanner"] == pytest.approx(800, abs=10)          # first, up to its cap
    assert per_min["positions"] == pytest.approx(200, abs=10)        # the rest
    assert per_min["fills"] < 5 and per_min["cohorts"] < 5           # wait while the others use it all


def test_without_the_scanner_the_others_share_in_priority_order():
    clock = Clock()
    b = hl_calls.Budget(per_min=1000, clock=clock)
    got = drain(b, clock, {"positions": 2, "fills": 20, "cohorts": 2}, 600)
    per_min = {k: v / 10 for k, v in got.items()}
    assert per_min["positions"] == pytest.approx(300, abs=10)        # each up to its cap ...
    assert per_min["fills"] == pytest.approx(300, abs=10)
    assert per_min["cohorts"] == pytest.approx(400, abs=10)          # ... 1,000 in all
    clock2 = Clock()
    b2 = hl_calls.Budget(per_min=600, clock=clock2)                   # less room: the last one waits
    got2 = drain(b2, clock2, {"positions": 2, "fills": 20, "cohorts": 2}, 600)
    assert got2["positions"] / 10 == pytest.approx(300, abs=10)
    assert got2["fills"] / 10 == pytest.approx(300, abs=10)
    assert got2["cohorts"] / 10 < 10


def test_each_consumer_alone_stays_within_its_cap():
    for name, (_, cap) in hl_calls.CONSUMERS.items():
        clock = Clock()
        b = hl_calls.Budget(per_min=1000, clock=clock)
        got = drain(b, clock, {name: 20}, 600)
        assert got[name] / 10 <= cap + 10, name


def test_reserve_serves_higher_priorities_first():
    clock = Clock()
    b = hl_calls.Budget(per_min=1000, clock=clock)
    b.level = 30.0
    assert b.try_take("cohorts", 2) > 0          # needs 3 * 20 kept back plus its 2
    assert b.try_take("fills", 20) > 0           # needs 40 + 20
    assert b.try_take("positions", 2) == 0       # needs 20 + 2
    assert b.try_take("scanner", 20) == 0        # needs 20


def test_calls_that_cannot_wait_are_taken_at_once_and_others_wait_for_them():
    clock = Clock()
    b = hl_calls.Budget(per_min=1000, clock=clock)
    for _ in range(10):
        b.charge("other", 20)                    # page views: never refused, never wait
    assert b.level < 0
    wait = b.try_take("scanner", 20)
    assert wait == pytest.approx((20 - b.level) / (1000 / 60), rel=1e-6)


def test_a_429_slows_everyone_for_a_while():
    clock = Clock()
    b = hl_calls.Budget(per_min=1000, clock=clock)
    b.penalize("scanner")
    assert b.level <= 0 and b.rate == pytest.approx(1000 / 120)
    assert b.status()["consumers"]["scanner"]["rate_limited"] == 1
    clock.t += hl_calls.PENALTY_S + 1
    b.try_take("scanner", 1)
    assert b.rate == pytest.approx(1000 / 60)


def test_acquire_waits_with_the_fake_clock():
    clock = Clock()
    slept = []

    async def sleep(s):
        slept.append(s)
        clock.t += s
    b = hl_calls.Budget(per_min=1000, clock=clock, sleep=sleep)
    b.level = 0.0

    async def go():
        return await b.acquire("scanner", 20)
    waited = asyncio.run(go())
    assert waited == pytest.approx(20 / (1000 / 60), rel=0.01) and sum(slept) == pytest.approx(waited)
    assert b.status()["consumers"]["scanner"]["waits"] == 1


def test_status_reports_weight_by_consumer(monkeypatch):
    monkeypatch.setattr(hl_calls, "budget", hl_calls.Budget())
    hl_calls.reset()
    t0 = (int(hl_calls._started // 60) + 10) * 60
    hl_calls.record("metaAndAssetCtxs", now=t0)                    # other: 20
    hl_calls._count("candleSnapshot", 1, 30, "scanner", t0)
    st = hl_calls.stats(now=t0 + 70)["budget"]
    assert st["target_per_min"] == hl_calls.TARGET_PER_MIN
    assert st["consumers"]["scanner"]["weight_since_start"] == 30
    assert st["consumers"]["other"]["weight_since_start"] == 20
    assert set(st["consumers"]) == {"scanner", "positions", "fills", "cohorts", "other"}


def test_net_stats_exposes_the_budget():
    from fastapi.testclient import TestClient
    import main
    body = TestClient(main.app).get("/api/net-stats").json()
    assert "scanner" in body["hyperliquid_budget"]["consumers"]


# --- candle weight -----------------------------------------------------------------------------

def test_candle_weight_counts_items():
    assert hl_calls.candle_weight(0) == 20
    assert hl_calls.candle_weight(3) == 20
    assert hl_calls.candle_weight(59) == 20
    assert hl_calls.candle_weight(60) == 21
    assert hl_calls.candle_weight(601) == 30


class FakeResponse:
    def __init__(self, status, body):
        self.status, self.body = status, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return self.body


class FakeSession:
    """Answers the given statuses in turn, then 200 with ``n`` candles."""

    def __init__(self, statuses, n):
        self.statuses, self.n, self.posts = list(statuses), n, 0

    def post(self, url, json=None, headers=None):
        self.posts += 1
        status = self.statuses.pop(0) if self.statuses else 200
        candles = [{"t": 1_700_000_000_000 + i * H4 * 1000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}
                   for i in range(self.n)]
        return FakeResponse(status, candles if status == 200 else None)


def run_candles(session, limit, sleeps=None):
    async def fake_sleep(s):
        if sleeps is not None:
            sleeps.append(s)
    with mock.patch.object(data_fetcher.asyncio, "sleep", fake_sleep):
        return asyncio.run(data_fetcher._fetch_hl_candles(session, "BTC", "4h", limit))


def test_candle_requests_are_counted_at_their_weight(monkeypatch):
    monkeypatch.setattr(hl_calls, "budget", hl_calls.unlimited())
    hl_calls.reset()
    run_candles(FakeSession([], 601), 600)            # a full read: 20 + 601 // 60
    run_candles(FakeSession([], 3), 2)                # an incremental read
    run_candles(FakeSession([], 100), 600)            # a short listing: less than asked
    assert hl_calls._wtotals["candleSnapshot"] == 30 + 20 + 21
    assert hl_calls._totals["candleSnapshot"] == 3
    assert hl_calls._ctotals["scanner"] == 71


# --- 429 ---------------------------------------------------------------------------------------

def test_backoff_is_exponential_with_jitter():
    assert hl_calls.backoff_delay(0, rng=lambda: 0.0) == 1.0
    assert hl_calls.backoff_delay(0, rng=lambda: 1.0) == 2.0
    assert hl_calls.backoff_delay(3, rng=lambda: 0.0) == 8.0
    assert hl_calls.backoff_delay(10, rng=lambda: 1.0) == 60.0          # capped


def test_a_429_backs_off_and_slows_the_shared_budget(monkeypatch):
    b = hl_calls.Budget()
    monkeypatch.setattr(hl_calls, "budget", b)
    sleeps = []
    out = run_candles(FakeSession([429, 429], 3), 2, sleeps)
    assert out is not None and len(out["close"]) == 3
    assert 1.0 <= sleeps[0] <= 2.0 and 2.0 <= sleeps[1] <= 4.0       # not the old flat 1 s and 2 s
    assert b.rate < b.base_rate and b.status()["consumers"]["scanner"]["rate_limited"] == 2


def test_persistent_429_keeps_the_stored_series_and_no_cex_fallback(monkeypatch):
    store, cache = data_fetcher.OHLCVStore(), data_fetcher.DataCache()
    stored = series(1_790_000_000 // H4 * H4 - 30 * H4, 30)
    store.update("ABC/USDT", "4h", stored)
    store._updated_at["ABC/USDT|4h"] -= 3600                          # due for a read

    async def limited(*a, **k):
        raise data_fetcher.HLRateLimited("ABC 4h")
    cex = mock.AsyncMock(return_value=stored)
    only = set()
    with mock.patch.object(data_fetcher, "_ohlcv_store", store), mock.patch.object(data_fetcher, "_cache", cache), \
            mock.patch.object(data_fetcher, "_ccxt_only", only), \
            mock.patch.object(data_fetcher, "_fetch_ohlcv_hyperliquid", limited), \
            mock.patch.object(data_fetcher, "_fetch_ohlcv_ccxt", cex):
        out = asyncio.run(data_fetcher.fetch_ohlcv("ABC/USDT", "4h"))
    assert out is stored or np.array_equal(out["close"], stored["close"])
    assert not cex.called and "ABC/USDT" not in only

    sleeps = []
    with pytest.raises(data_fetcher.HLRateLimited):
        run_candles(FakeSession([429] * 10, 3), 2, sleeps)
    assert len(sleeps) == data_fetcher._HL_429_ATTEMPTS - 1


# --- startup -----------------------------------------------------------------------------------

T = 1_790_000_000 // H4 * H4 + 2 * 3600 + 600      # two hours and ten minutes after a 4h close


def series(start_s, n, step_s=H4, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    ts = (start_s + np.arange(n) * step_s) * 1000.0
    return {"timestamp": ts, "open": close * 0.99, "high": close * 1.02, "low": close * 0.97,
            "close": close, "volume": rng.uniform(1e5, 1e6, n)}


def stored_markets(symbols, now=T):
    """A store as a restart finds it: every market read a few minutes before ``now``."""
    store = data_fetcher.OHLCVStore()
    week0 = data_fetcher.DataCache._last_close("1w", now)
    for i, sym in enumerate(symbols):
        store.update(sym, "4h", series(now // H4 * H4 - 599 * H4, 600, seed=i + 1))
        store.update(sym, "1d", series(now // 86400 * 86400 - 599 * 86400, 600, 86400, seed=i + 11))
        store.update(sym, "1w", series(week0 - 199 * 604800, 200, 604800, seed=i + 21))
    return store


def test_bars_to_fetch_reads_only_what_is_missing():
    store = data_fetcher.OHLCVStore()
    store.update("A/USDT", "4h", series(T // H4 * H4 - 9 * H4, 10))
    now_ms = T * 1000
    assert store.bars_to_fetch("A/USDT", "4h", now_ms) == 2                          # last bar is the open one
    assert store.bars_to_fetch("A/USDT", "4h", now_ms + 3 * H4 * 1000) == 4          # three closes missed
    assert store.bars_to_fetch("B/USDT", "4h", now_ms) == data_fetcher._DEFAULT_LIMIT["4h"]


def test_restart_reads_nothing_already_read_since_the_last_close():
    syms = ["BTC/USDT", "ETH/USDT", "AAA/USDT", "BBB/USDT"]
    with mock.patch("time.time", return_value=T):
        store = stored_markets(syms[:3])                       # BBB/USDT: nothing stored
        with mock.patch.object(scanner, "_ohlcv_store", store):
            restored = scanner.restored_symbols(syms)
            assert restored == ["BTC/USDT", "ETH/USDT", "AAA/USDT"]
            sched = ScanSchedule()
            scanner.seed_schedule(sched, restored)
        import time as _t
        due = sched.next_due(syms, _t.monotonic(), lambda s: "hot" if s in ("BTC/USDT", "ETH/USDT") else "active",
                             lambda s: "perp", True, wall=T)
        assert due == "BBB/USDT"                               # only the market without stored candles
        sched.record("BBB/USDT", _t.monotonic(), True, wall=T)
        assert sched.next_due(syms, _t.monotonic(), lambda s: "active", lambda s: "perp", True, wall=T) is None
        # After the next 4h close every market is read again, BTC first.
        assert sched.next_due(syms, _t.monotonic(), lambda s: "active", lambda s: "perp", True,
                              wall=T + H4) == "BTC/USDT"


def test_stored_series_count_as_fetched_when_they_were_read():
    cache = data_fetcher.DataCache()
    store = data_fetcher.OHLCVStore()
    with mock.patch("time.time", return_value=T):
        store.update("A/USDT", "1d", series(T // 86400 * 86400 - 9 * 86400, 10, 86400))
        store.update("A/USDT", "4h", series(T // H4 * H4 - 9 * H4, 10))
        with mock.patch.object(data_fetcher, "_ohlcv_store", store):
            cache.seed("A/USDT", "1d", T - 120)                 # read 2 min before the restart
            cache.seed("A/USDT", "4h", T - 600)                 # 10 min: past the 5-min TTL
            assert cache.get("A/USDT", "1d") is not None
            assert cache.get("A/USDT", "4h") is None
    day_close = T // 86400 * 86400 + 86400
    with mock.patch("time.time", return_value=day_close + 300), mock.patch.object(data_fetcher, "_ohlcv_store", store):
        cache.seed("A/USDT", "1d", day_close - 600)              # within the TTL, but before a daily close
        assert cache.get("A/USDT", "1d") is None


def drip(symbols, store, offline, fetched):
    """One drip pass over ``symbols`` against ``store``; Hyperliquid answers with the stored bars."""
    cache = scanner.ScanCache()
    cache.symbols = list(symbols)

    async def hl(symbol, timeframe, limit=None):
        fetched.append((symbol, timeframe, limit))
        data = store.get(symbol, timeframe)
        return {k: v[-limit:].copy() for k, v in data.items()}

    async def go():
        for s in symbols:
            await scanner._drip_one_symbol(s, cache, offline=offline)
    with mock.patch.object(data_fetcher, "_ohlcv_store", store), \
            mock.patch.object(data_fetcher, "_cache", data_fetcher.DataCache()), \
            mock.patch.object(scanner, "_ohlcv_store", store), \
            mock.patch.object(data_fetcher, "_fetch_ohlcv_hyperliquid", hl):
        asyncio.run(go())
    return cache._results_by_sym


def comparable(results):
    out = {}
    for sym, by_tf in results.items():
        for tf, r in by_tf.items():
            out[(sym, tf)] = json.dumps({k: v for k, v in r.items() if k != "candles_checked_at"},
                                        sort_keys=True, default=str)
    return out


def test_stored_candle_pass_gives_the_same_results_without_a_request():
    syms = ["BTC/USDT", "ETH/USDT", "AAA/USDT"]
    with mock.patch("time.time", return_value=T):
        online_fetched, offline_fetched = [], []
        online = drip(syms, stored_markets(syms), False, online_fetched)
        offline = drip(syms, stored_markets(syms), True, offline_fetched)
    assert offline_fetched == []
    assert ("BTC/USDT", "1w") not in {(s, tf) for s, tf, _ in online_fetched}    # closed weeks already held
    assert {(s, tf) for s, tf, _ in online_fetched} == {(s, tf) for s in syms for tf in ("4h", "1d")}
    assert all(limit == 2 for _, _, limit in online_fetched)
    assert len(online) == 3 and comparable(online) == comparable(offline)


def test_weekly_read_once_per_closed_week_gives_the_same_results():
    """Before: the weekly series was read on every refresh (TTL 1 h). The engines use closed weeks
    only, so reading it once after each weekly close changes no result."""
    syms = ["BTC/USDT", "ETH/USDT", "AAA/USDT"]
    with mock.patch("time.time", return_value=T):
        before_fetched, after_fetched = [], []
        with mock.patch.object(data_fetcher.OHLCVStore, "complete", lambda *a, **k: False):
            before = drip(syms, stored_markets(syms), False, before_fetched)
        after = drip(syms, stored_markets(syms), False, after_fetched)
    assert sum(1 for _, tf, _ in before_fetched if tf == "1w") == 3
    assert sum(1 for _, tf, _ in after_fetched if tf == "1w") == 0
    assert comparable(before) == comparable(after)


def test_warm_pass_fills_the_scan_from_the_store():
    syms = ["BTC/USDT", "ETH/USDT", "AAA/USDT"]

    async def no_request(*a, **k):
        raise AssertionError("no request expected")
    cache = scanner.ScanCache()
    cache.symbols = list(syms)
    with mock.patch("time.time", return_value=T):
        store = stored_markets(syms)
        with mock.patch.object(data_fetcher, "_ohlcv_store", store), \
                mock.patch.object(scanner, "_ohlcv_store", store), \
                mock.patch.object(scanner, "WARM_GAP_S", 0), \
                mock.patch.object(data_fetcher, "_fetch_ohlcv_hyperliquid", no_request):
            done = asyncio.run(scanner.warm_from_store(cache, scanner.restored_symbols(syms)))
    assert done == 3 and set(cache._results_by_sym) == set(syms)
    assert all(set(v) == {"4h", "1d"} for v in cache._results_by_sym.values())


def test_after_a_close_the_stored_pass_shows_the_scan_from_before_the_restart():
    """Restarted after a 4h close: every market must be read again, which takes a while within the
    budget. Meanwhile the stored pass serves the scan as it stood when the candles were read; the
    bar that was open then is not taken as closed."""
    syms = ["BTC/USDT", "ETH/USDT", "AAA/USDT"]
    with mock.patch("time.time", return_value=T):
        before = drip(syms, stored_markets(syms), False, [])
        store = stored_markets(syms)
    later = (T // H4 + 1) * H4 + 600
    for key in store._updated_at:
        store._updated_at[key] -= later - T              # read at T, before the close
    fetched = []
    with mock.patch("time.time", return_value=later):
        with mock.patch.object(scanner, "_ohlcv_store", store):
            assert scanner.restored_symbols(syms) == []              # all of them are read again
            assert scanner.stored_symbols(syms) == syms
        offline = drip(syms, store, True, fetched)
    assert fetched == [] and comparable(offline) == comparable(before)
