"""The Portfolio page's coin context (portfolio_context.py, /api/portfolio/context)."""

import time
from unittest import mock

import pytest

import portfolio_context as pc

NOW = 1_800_000_000.0
DAY = 86400


def _store(n_days=30, start_px=10.0, now=NOW):
    """Daily candles: high = close + 1, low = close - 1, close rising by 0.5 a day; the last one still open."""
    t0 = (int(now) // DAY - n_days) * DAY
    ts, o, h, lo, c = [], [], [], [], []
    for i in range(n_days + 1):
        px = start_px + 0.5 * i
        ts.append((t0 + i * DAY) * 1000)
        o.append(px)
        h.append(px + 1)
        lo.append(px - 1)
        c.append(px)
    return {"timestamp": ts, "open": o, "high": h, "low": lo, "close": c}


def _row(sym, signal="STRONG_LONG", regime="MARKUP", heat=74, prev=68, z=1.6, since=NOW - 2 * DAY, price=79.9, kind="perpetual"):
    return {"symbol": sym, "market_kind": kind, "signal": signal, "regime": regime, "heat": heat, "previous_heat": prev,
            "zscore": z, "signal_first_seen_at": since, "price": price, "sector": "L1",
            "structure": {"swing_low": 74.2, "swing_high": 84.1, "lookback_bars": 10}}


def _sources(**over):
    store = _store()
    base = dict(
        rows={"4h": {"HYPE": _row("HYPE/USDT"), "KPEPE": _row("KPEPE/USDT", price=0.01)},
              "1d": {"HYPE": _row("HYPE/USDT", signal="LIGHT_LONG", since=NOW - 6 * DAY)}},
        tradfi={"4h": {"SILVER": _row("SILVER/USD", signal="WAIT", regime="FLAT", heat=22, prev=25, z=0.3, price=54.0)},
                "1d": {"SILVER": _row("SILVER/USD", signal="RISK_OFF", regime="MARKDOWN")}},
        candles=lambda symbol, tf: store if tf == "1d" else None,
        band=lambda symbol, price: {"lo": 70.1, "hi": 74.8, "state": "above", "d": 0.068},
        trend=lambda symbol: 72.4,
        prof={"HYPE": {"long": {"n": 9, "median_entry": 76.2, "in_profit": 7},
                       "short": {"n": 2, "median_entry": 81.0, "in_profit": 1}}},
        day_ago={"HYPE": {"long": 10, "short": 1}},
        opens=[{"coin": "HYPE", "side": "short", "ts": NOW - 3600, "cohort": "profitable", "address": "0xa"},
               {"coin": "HYPE", "side": "short", "ts": NOW - 1800, "cohort": "profitable", "address": "0xb"},
               {"coin": "HYPE", "side": "long", "ts": NOW - 8 * 3600, "cohort": "profitable", "address": "0xc"}],
        entity=lambda a: "E1" if a in ("0xa", "0xb") else a,      # 0xa and 0xb trade as one
    )
    base.update(over)
    return pc.Sources(**base)


# ------------------------------------------------------------------ pure parts
def test_atr_matches_a_hand_computed_wilder_series():
    high = [11, 12, 13, 12, 14, 15, 14, 16, 17, 16, 18, 19, 18, 20, 21, 20]
    low = [9, 10, 11, 10, 12, 13, 12, 14, 15, 14, 16, 17, 16, 18, 19, 18]
    close = [10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 17, 18, 17, 19, 20, 19]
    # Bar by bar: TR = max(h - l, |h - prev close|, |l - prev close|).
    trs = [max(h - lo, abs(h - pc), abs(lo - pc)) for h, lo, pc in zip(high[1:], low[1:], close[:-1])]
    assert trs[:4] == [2, 2, 2, 3]
    first = sum(trs[:14]) / 14
    expected = (first * 13 + trs[14]) / 14
    assert pc.atr_wilder(high, low, close) == pytest.approx(expected)
    assert pc.atr_wilder(high[:14], low[:14], close[:14]) is None      # needs 15 bars


def test_atr_uses_completed_daily_candles_only():
    d = pc.completed(_store(), DAY, NOW)
    assert len(d["close"]) == 30                                       # the open candle is left out
    # Every true range is 2 (range 2, close-to-close step 0.5), so the ATR is 2.
    assert pc.atr_wilder(d["high"], d["low"], d["close"]) == pytest.approx(2.0)


def test_coins_are_deduplicated_sorted_and_capped_with_raw_names_kept():
    raw = ",".join(["ZEC", "BTC", "kPEPE", "xyz:MSTR", "BTC", " HYPE ", "bad coin", "@107"]
                   + [f"C{i:02d}" for i in range(20)])
    out = pc.parse_coins(raw)
    assert len(out) == pc.MAX_COINS
    assert out == sorted(out)
    assert out[:4] == ["@107", "BTC", "C00", "C01"]
    assert "kPEPE" in pc.parse_coins("kPEPE,BTC") and "bad coin" not in out
    assert pc.parse_coins("") == [] and pc.parse_coins(None) == []


def test_app_keys():
    assert pc.app_key("kPEPE") == "KPEPE"
    assert pc.app_key("xyz:mstr") == "xyz:MSTR"
    assert pc.app_key("HYPE") == "HYPE"
    assert pc.app_key("@107") is None and pc.app_key("flx:ABC") is None


def test_a_covered_coin_reads_every_field():
    ctx = pc.coin_context("HYPE", _sources(), NOW)
    assert ctx["covered"] and ctx["price"] == 79.9 and ctx["sector"] == "L1"
    assert ctx["h4"] == {"signal": "STRONG_LONG", "since": NOW - 2 * DAY, "regime": "MARKUP", "heat": 74, "heat_prev": 68, "z": 1.6}
    assert ctx["d1"] == {"signal": "LIGHT_LONG", "since": NOW - 6 * DAY, "regime": "MARKUP"}
    assert ctx["band"] == {"lo": 70.1, "hi": 74.8, "state": "above", "dist_pct": 6.8}
    assert ctx["trend"] == 72.4 and ctx["swing"] == {"lo": 74.2, "hi": 84.1}
    assert ctx["atr_1d"] == pytest.approx(2.0)
    t = ctx["traders"]
    assert t["long"] == {"n": 9, "n_day_ago": 10, "median_entry": 76.2, "in_profit": 7, "opens_6h": 0}
    # Two short opens in the last 6 h by linked wallets count once; the long open is older than 6 h.
    assert t["short"] == {"n": 2, "n_day_ago": 1, "median_entry": 81.0, "in_profit": 1, "opens_6h": 1}


def test_k_market_is_read_under_its_raw_name():
    ctx = pc.coin_context("kPEPE", _sources(), NOW)
    assert ctx["covered"] and ctx["h4"]["signal"] == "STRONG_LONG" and ctx["d1"] is None


def test_uncovered_coins():
    src = _sources()
    for coin in ("XMR", "@107", "flx:ABC", "xyz:NVDA"):
        assert pc.coin_context(coin, src, NOW) == {"covered": False}


def test_xyz_coin_reads_the_tradfi_rows_without_band_trend_atr_or_traders():
    ctx = pc.coin_context("xyz:SILVER", _sources(), NOW)
    assert ctx["covered"] and ctx["sector"] == "TradFi" and ctx["price"] == 54.0
    assert ctx["h4"]["signal"] == "WAIT" and ctx["h4"]["heat"] == 22 and ctx["d1"]["signal"] == "RISK_OFF"
    assert ctx["band"] is None and ctx["trend"] is None and ctx["atr_1d"] is None and ctx["traders"] is None


def test_a_failing_band_or_trend_leaves_the_rest():
    def boom(*_):
        raise RuntimeError("no candles")
    ctx = pc.coin_context("HYPE", _sources(band=boom, trend=boom), NOW)
    assert ctx["covered"] and ctx["band"] is None and ctx["trend"] is None and ctx["h4"]["signal"] == "STRONG_LONG"


def test_memo_per_scan_and_last_good_on_failure():
    memo = pc.Memo()
    calls = []

    def build():
        calls.append(1)
        return {"covered": True, "n": len(calls)}
    assert memo.get("s1", "HYPE", build, NOW) == ({"covered": True, "n": 1}, None)
    assert memo.get("s1", "HYPE", build, NOW)[0]["n"] == 1             # same scan: memoised
    assert memo.get("s2", "HYPE", build, NOW)[0]["n"] == 2             # a new scan rebuilds

    def boom():
        raise RuntimeError("broken")
    val, built_at = memo.get("s3", "HYPE", boom, NOW + 60)
    assert val["n"] == 2 and built_at == NOW
    body = pc.context_body(["HYPE"], _sources(), "s4", NOW + 60, memo, now=NOW + 120)
    assert body["coins"]["HYPE"]["covered"] and "stale" not in body


def test_body_marks_stale_when_a_coin_comes_from_its_last_good_reading():
    memo = pc.Memo()
    src = _sources()
    pc.context_body(["HYPE"], src, "s1", NOW, memo, now=NOW)
    with mock.patch.object(pc, "coin_context", side_effect=RuntimeError("down")):
        body = pc.context_body(["HYPE", "XMR"], src, "s2", NOW + 300, memo, now=NOW + 300)
    assert body["stale"] is True and body["as_of"] == NOW
    assert body["coins"]["HYPE"]["covered"] and body["coins"]["XMR"] == {"covered": False}


def test_etag_follows_the_body():
    a = {"as_of": 1, "coins": {"HYPE": {"covered": True}}}
    assert pc.etag(a) == pc.etag(dict(a))
    assert pc.etag(a) != pc.etag({"as_of": 2, "coins": {}})
    assert pc.not_modified(pc.etag(a), pc.etag(a)) and not pc.not_modified(None, pc.etag(a))
    assert pc.not_modified(f'"x", {pc.etag(a)}', pc.etag(a))


# ------------------------------------------------------------------ the route
@pytest.fixture
def no_network(monkeypatch):
    """Any Hyperliquid (or other outbound) call fails the test."""
    import urllib.request

    import aiohttp

    import hl_calls

    def boom(*a, **k):
        raise AssertionError("outbound call from the portfolio context")

    async def aboom(*a, **k):
        raise AssertionError("outbound call from the portfolio context")
    monkeypatch.setattr(aiohttp.ClientSession, "_request", aboom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(hl_calls, "acquire", aboom)
    monkeypatch.setattr(hl_calls, "record", boom)
    monkeypatch.setattr(hl_calls, "record_weight", boom)


@pytest.fixture
def client(monkeypatch, no_network):
    from fastapi.testclient import TestClient

    import main
    monkeypatch.delenv("PORTFOLIO_CONTEXT", raising=False)
    monkeypatch.setattr(main, "_PF_MEMO", pc.Memo())
    monkeypatch.setattr(main, "_PF_BODIES", pc.BodyCache())
    return TestClient(main.app), main


def test_on_by_default_with_a_kill_switch(monkeypatch):
    assert pc.enabled({}) is True
    for off in ("0", "false", "no", "off", " OFF "):
        assert pc.enabled({"PORTFOLIO_CONTEXT": off}) is False
    for on in ("1", "true", "yes", "on", ""):
        assert pc.enabled({"PORTFOLIO_CONTEXT": on}) is True


def test_kill_switch_answers_404(client, monkeypatch):
    c, main = client
    monkeypatch.setattr(main, "_pf_sources", lambda: _sources())
    monkeypatch.setattr(main, "_pf_scan_id", lambda: "s_1")
    assert c.get("/api/portfolio/context?coins=HYPE").status_code == 200
    monkeypatch.setenv("PORTFOLIO_CONTEXT", "0")
    assert c.get("/api/portfolio/context?coins=HYPE").status_code == 404
    assert c.get("/api/portfolio/events?coins=HYPE").status_code == 404


def test_route_answers_with_etag_and_304(client, monkeypatch):
    c, main = client
    monkeypatch.setattr(main, "_pf_sources", lambda: _sources())
    monkeypatch.setattr(main, "_pf_scan_id", lambda: "s_1")
    r = c.get("/api/portfolio/context?coins=XMR,HYPE,xyz:SILVER,HYPE")
    assert r.status_code == 200
    body = r.json()
    assert list(body["coins"]) == ["HYPE", "XMR", "xyz:SILVER"]
    assert body["coins"]["XMR"] == {"covered": False} and body["scan_id"] == "s_1"
    assert r.headers["cache-control"] == "max-age=60"
    tag = r.headers["etag"]
    r2 = c.get("/api/portfolio/context?coins=HYPE,XMR,xyz:SILVER", headers={"If-None-Match": tag})
    assert r2.status_code == 304 and r2.headers["etag"] == tag
    assert c.get("/api/portfolio/context?coins=").status_code == 400


def test_route_builds_from_memory_without_any_hyperliquid_call(client, monkeypatch):
    c, main = client
    import data_fetcher
    store = _store(now=time.time())
    monkeypatch.setitem(main.cache.results, "4h", [_row("HYPE/USDT"), _row("HYPE/USDC", kind="spot", signal="WAIT")])
    monkeypatch.setitem(main.cache.results, "1d", [_row("HYPE/USDT", signal="LIGHT_LONG")])
    monkeypatch.setattr(main.cache, "symbols", ["HYPE/USDT", "HYPE/USDC"])
    monkeypatch.setattr(data_fetcher._ohlcv_store, "get", lambda symbol, tf: store if tf == "1d" else None)
    r = c.get("/api/portfolio/context?coins=HYPE,BTC")
    assert r.status_code == 200, r.text
    hype = r.json()["coins"]["HYPE"]
    assert hype["covered"] and hype["h4"]["signal"] == "STRONG_LONG" and hype["d1"]["signal"] == "LIGHT_LONG"
    assert hype["atr_1d"] == pytest.approx(2.0)
    assert r.json()["coins"]["BTC"] == {"covered": False}


def test_rate_limit_class():
    import ratelimit
    assert ratelimit.classify("GET", "/api/portfolio/context", {}) == "portfolio"
    assert ratelimit.classify("GET", "/api/portfolio/events", {}) == "portfolio"
    assert ratelimit.classify("GET", "/api/portfolio/other", {}) is None
    limits = ratelimit.Limits(env={})
    # A page asks twice on load and twice per scan notice; a burst of 30 covers many tabs behind one address.
    assert all(limits.check("portfolio", "1.2.3.4", now=0.0)[0] for _ in range(30))
    assert limits.check("portfolio", "1.2.3.4", now=0.0)[0] is False
    assert limits.check("portfolio", "5.6.7.8", now=0.0)[0] is True


def test_both_feeds_go_through_the_edge_cache_as_member_feeds():
    import edge
    assert {"/api/portfolio/context", "/api/portfolio/events"} <= edge.EDGE_PATHS
    assert not ({"/api/portfolio/context", "/api/portfolio/events"} & edge.PUBLIC_PATHS)


def test_sources_are_built_only_when_a_coin_is_not_memoised():
    memo = pc.Memo()
    built = []

    def sources():
        built.append(1)
        return _sources()
    pc.context_body(["HYPE", "XMR"], sources, "s1", NOW, memo, now=NOW)
    assert built == [1]                                                  # once for both coins
    pc.context_body(["HYPE", "XMR"], sources, "s1", NOW, memo, now=NOW)
    assert built == [1]                                                  # memoised: not built again
    pc.context_body(["HYPE"], sources, "s2", NOW, memo, now=NOW)
    assert built == [1, 1]                                               # a new scan


def test_body_cache_keeps_answers_a_minute_and_stays_bounded():
    cache = pc.BodyCache(ttl=60, max_items=3)
    cache.put(("context", "s1", ("HYPE",)), "a", now=NOW)
    assert cache.get(("context", "s1", ("HYPE",)), now=NOW + 59) == "a"
    assert cache.get(("context", "s1", ("HYPE",)), now=NOW + 61) is None
    for i in range(10):
        cache.put(("context", "s1", (f"C{i}",)), i, now=NOW + i)
    assert len(cache) <= 3 and cache.get(("context", "s1", ("C9",)), now=NOW + 9) == 9


def test_the_access_log_keeps_the_path_not_the_coin_set():
    import logging

    import main  # noqa: F401  (installs the filter)
    f = [x for x in logging.getLogger("uvicorn.access").filters if isinstance(x, pc.DropPortfolioQuery)]
    assert f, "the filter is installed on uvicorn.access"
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "GET", "/api/portfolio/context?coins=BTC,HYPE,xyz:UNITREE", "1.1", 200), None)
    assert f[0].filter(rec) is True
    assert rec.getMessage() == '1.2.3.4:5 - "GET /api/portfolio/context HTTP/1.1" 200'
    other = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                              ("1.2.3.4:5", "GET", "/api/scan?timeframe=4h", "1.1", 200), None)
    f[0].filter(other)
    assert "timeframe=4h" in other.getMessage()


def test_the_answer_holds_counts_never_an_address(client, monkeypatch):
    c, main = client
    monkeypatch.setattr(main, "_pf_sources", lambda: _sources())
    monkeypatch.setattr(main, "_pf_scan_id", lambda: "s_addr")
    r = c.get("/api/portfolio/context?coins=HYPE&address=0x348c000000000000000000000000000000001eee")
    assert r.status_code == 200
    text = r.text.lower()
    for a in ("0xa", "0xb", "0xc", "0x348c"):
        assert f'"{a}' not in text
    assert r.json()["coins"]["HYPE"]["traders"]["short"]["opens_6h"] == 1


def test_route_builds_once_per_scan_and_coin_set(client, monkeypatch):
    c, main = client
    builds = []

    def sources():
        builds.append(1)
        return _sources()
    monkeypatch.setattr(main, "_pf_sources", sources)
    monkeypatch.setattr(main, "_pf_scan_id", lambda: "s_once")
    a = c.get("/api/portfolio/context?coins=HYPE,kPEPE")
    b = c.get("/api/portfolio/context?coins=kPEPE,HYPE")
    assert a.status_code == b.status_code == 200 and a.json() == b.json() and a.headers["etag"] == b.headers["etag"]
    assert builds == [1]
