import numpy as np

import setup_map as sm

NOW = 1_800_000_000.0


def row(**kw):
    base = {"symbol": "FET/USDT", "timeframe": "1d", "price": 1.0, "regime": "MARKUP", "signal": "LIGHT_LONG",
            "zscore": 0.5, "heat": 10, "heat_phase": "Neutral", "opportunity": {"trigger_at": NOW - 10 * 86400}}
    base.update(kw)
    return base


def test_stage_rules():
    assert sm.stage(row(signal="TRIM"), NOW) == "leaving"
    assert sm.stage(row(regime="ACCUM", signal="WAIT", regime_transition={"candidate": "MARKUP"}), NOW) == "forming"
    assert sm.stage(row(zscore=2.1), NOW) == "stretched"
    assert sm.stage(row(heat_phase="Exhaustion"), NOW) == "stretched"
    assert sm.stage(row(opportunity={"trigger_at": NOW - 86400}), NOW) == "fresh"
    assert sm.stage(row(), NOW) == "running"
    assert sm.stage(row(signal="WAIT"), NOW) == "waiting"


def test_zone_and_crowd():
    assert sm.zone("running", 0.5, 3) == "watch"
    assert sm.zone("waiting", 0.5, 3) == "outside"          # no setup, not in the box
    assert sm.zone("running", 2.4, 3) == "late"
    assert sm.zone("running", 0.5, 20) == "crowded"
    assert sm.zone("forming", 0.2, 0) == "quiet"
    t = {"pl": 3, "ps": 0, "ple": 0.8, "pse": None, "n24l": 0, "n24s": 0}
    assert sm.crowd(True, t, 1.0) == "crowded"               # 25% past their entry
    assert sm.crowd(True, dict(t, ple=0.99, n24l=1), 1.0) == "early"
    assert sm.crowd(True, dict(t, pl=1, ps=3), 1.0) == "against"
    assert sm.crowd(True, dict(t, pl=0), 1.0) == "quiet"


def test_trader_trail_uses_nearest_record_and_today():
    rec = {1000: (5, 1), 15400: (7, 1)}
    assert sm.trader_trail([1100, 15000, 30000, 40000], rec, 9) == [4, 6, None, 9]


def test_z_trail_is_anchored_to_the_scan_value():
    rng = np.random.default_rng(1)
    close = list(np.exp(np.cumsum(rng.normal(0, 0.02, 700))) * 10)
    tr = sm.z_trail(close, 5, 1.23)
    assert len(tr) == 5 and tr[-1] == 1.23


def test_changes_between_readings():
    prev = {"zone": "outside", "crowd": "holding", "regime": "ACCUM", "signal": "WAIT"}
    cur = {"zone": "watch", "crowd": "crowded", "regime": "MARKUP", "signal": "LIGHT_LONG"}
    assert sm.changes(None, cur) == []
    assert sm.changes(prev, cur) == ["entered the box", "confirmed Uptrend", "turned crowded"]
    assert sm.changes(cur, dict(cur, zone="late", signal="TRIM")) == ["left the box (stretched)", "exit signal Trim"]


def test_watch_check_sends_once_per_change(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "_FILE", tmp_path / "w.json")
    monkeypatch.setattr(sm, "_watch", {})
    monkeypatch.setattr(sm, "_loaded", True)
    assert sm.watch("FET", "1d")
    item = {"coin": "FET", "zone": "outside", "crowd": "holding", "regime": "ACCUM", "signal": "WAIT", "zscore": 0.3,
            "traders": {"pl": 1, "ps": 0}}
    maps = {"1d": {"coins": [item]}}
    assert sm.check(maps) == []                               # first reading is the baseline
    item.update(zone="watch")
    msgs = sm.check(maps)
    assert len(msgs) == 1 and "FET 1D: entered the box" in msgs[0]
    assert sm.check(maps) == []                               # no repeat
    assert (tmp_path / "w.json").exists()


def test_build_reads_numpy_candles_from_the_store():
    rng = np.random.default_rng(2)
    close = np.exp(np.cumsum(rng.normal(0, 0.02, 700))) * 10
    ts = np.array([NOW - (700 - k) * 86400 for k in range(700)], dtype=float) * 1000

    class Store:
        def get(self, sym, tf):
            return {"timestamp": ts, "close": close}
    out = sm.build([dict(row(), market_kind="perpetual")], "1d", Store(), {"FET": {"long": {"n": 2, "median_entry": 1.0}}}, {}, [], {}, NOW)
    c = out["coins"][0]
    assert c["coin"] == "FET" and len(c["trail"]["z"]) == sm.TRAIL["1d"] and c["trail"]["z"][-1] == 0.5
    assert sm.closes({"timestamp": np.array([]), "close": np.array([])}, "1d", NOW) == ([], [])


# ------------------------------------------------------------------ weekly band and money
DAY = 86400


def daily(values_by_day):
    """Store-shaped daily candles: open times in ms for day numbers (day 0 = 1970-01-01)."""
    days = sorted(values_by_day)
    return {"timestamp": np.array([d * DAY * 1000 for d in days], dtype=float),
            "close": np.array([values_by_day[d] for d in days], dtype=float)}


def test_weekly_band_uses_completed_sunday_closes_only():
    from backtest.risk_on_cycles import SUNDAY, weekly_rows
    assert sm.SUNDAY == SUNDAY
    first = 20009                                       # 20009 % 7 == 3: a Sunday
    assert first % 7 == sm.SUNDAY
    closes = {d: 100.0 + (d - first) * 0.5 for d in range(first - 3, first + 7 * 30 + 3)}
    last_sunday = first + 7 * 29
    now = (last_sunday + 1) * DAY + 3600                # an hour after the last Sunday closed
    b = sm.weekly_band(daily(closes), 150.0, now)
    wk = {d: c for d, c in closes.items() if d % 7 == SUNDAY and d <= last_sunday}
    assert b["week_close"] == sm.sig(closes[last_sunday], 5) and b["week"] == (last_sunday + 1) * DAY
    lo, hi = weekly_rows(wk, SUNDAY)[-1][1]             # the same band as the backtest's BTC rule
    assert (b["lo"], b["hi"]) == (sm.sig(lo, 5), sm.sig(hi, 5))
    assert b["sma20"] == sm.sig(sum(wk[d] for d in sorted(wk)[-20:]) / 20, 5)
    # The Sunday still trading is not a completed week: an hour before its close, the week before is used.
    early = sm.weekly_band(daily(closes), 150.0, (last_sunday + 1) * DAY - 3600)
    assert early["week"] == (last_sunday - 6) * DAY and early["week_close"] == sm.sig(closes[last_sunday - 7], 5)


def test_weekly_band_needs_21_weeks_and_fresh_candles():
    first = 20009
    short = {d: 10.0 for d in range(first, first + 7 * 20)}          # 20 Sundays
    now = (first + 7 * 20) * DAY
    assert sm.weekly_band(daily(short), 10.0, now) is None
    enough = {d: 10.0 for d in range(first, first + 7 * 21)}          # 21 Sundays
    assert sm.weekly_band(daily(enough), 10.0, (first + 7 * 21) * DAY)["lo"] == 10.0
    assert sm.weekly_band(daily(enough), 10.0, (first + 7 * 21 + 30) * DAY) is None   # a month without candles
    assert sm.weekly_band(None, 10.0, now) is None


def test_band_state_and_fill():
    assert sm.band_state(90, 100, 110, 115) == {"state": "above", "d": 0.15, "fill": 0.5}
    assert sm.band_state(90, 100, 110, 140)["fill"] == 0.0                # 30%+ above: empty
    assert sm.band_state(90, 100, 110, 100)["state"] == "inside" and sm.band_state(90, 100, 110, 100)["fill"] == 1.0
    assert sm.band_state(90, 100, 95, 85)["state"] == "under_now"          # under now, not at the close
    assert sm.band_state(90, 100, 85, 95)["state"] == "closed_under"       # the weekly close decides red
    assert sm.band_state(90, 100, 85, 120) == {"state": "closed_under", "d": 0.2, "fill": 1.0}
    assert sm.band_state(90, 100, 95, None)["state"] == "inside"          # no price: the weekly close


def test_money_from_positioning_row():
    assert sm.money({"long": {"n": 3, "usd": 7_500_000}, "short": {"n": 1, "usd": 2_500_000.4}}) == \
        {"long_usd": 7_500_000, "short_usd": 2_500_000, "gross_usd": 10_000_000, "net_long_share": 0.75}
    assert sm.money(None) == {"long_usd": 0, "short_usd": 0, "gross_usd": 0, "net_long_share": None}
    assert sm.money({"long": {"n": 0, "usd": 0}, "short": {"n": 2, "usd": 400}})["net_long_share"] == 0.0


def test_build_adds_money_and_band():
    first = 20009
    closes = {d: 10.0 * (1 + 0.001 * (d - first)) for d in range(first - 600, first + 7 * 30)}
    now = (first + 7 * 30) * DAY

    class Store:
        def get(self, sym, tf):
            return daily(closes) if tf == "1d" else None
    prof = {"FET": {"long": {"n": 2, "usd": 3000, "median_entry": 1.0}, "short": {"n": 1, "usd": 1000}}}
    out = sm.build([dict(row(price=11.0), market_kind="perpetual"), dict(row(symbol="SUI/USDT"), market_kind="perpetual")],
                   "1d", Store(), prof, {}, [], {}, now)
    fet, sui = out["coins"]
    assert fet["money"] == {"long_usd": 3000, "short_usd": 1000, "gross_usd": 4000, "net_long_share": 0.75}
    assert fet["band"]["state"] in ("inside", "above", "under_now", "closed_under") and fet["band"]["lo"] <= fet["band"]["hi"]
    assert sui["money"]["gross_usd"] == 0


def test_ladder_counts_medians_and_positions():
    item = {"coin": "FET", "symbol": "FET/USDT", "price": 1.1, "stage": "running", "zscore": 0.4,
            "band": {"lo": 0.9, "hi": 1.0, "state": "above"}}
    ps = [{"address": "0x" + "a" * 40, "side": "long", "size_usd": 5000, "entry": 1.0123456789, "leverage": 5,
           "upnl": 400, "roe": 40.0, "move": 8.0},
          {"address": "0x" + "b" * 40, "side": "long", "size_usd": 1000, "entry": 0.9, "leverage": 2, "upnl": 200, "roe": 40.0, "move": 20.0},
          {"address": "0x" + "c" * 40, "side": "short", "size_usd": 3000, "entry": 1.2, "leverage": 3, "upnl": 250, "roe": 25.0, "move": 8.3}]
    lad = sm.ladder(item, ps, 0.95, NOW)
    assert lad["counts"] == {"long": 2, "short": 1, "long_usd": 6000, "short_usd": 3000,
                             "long_wallets": 2, "short_wallets": 1}
    assert lad["median_entry"] == {"long": sm.sig((1.0123456789 + 0.9) / 2), "short": 1.2}
    assert lad["positions"][0]["entry"] == 1.01235 and lad["band"] == item["band"] and lad["trend"] == 0.95
    empty = sm.ladder(item, [], None, NOW)
    assert empty["counts"]["long"] == 0 and empty["median_entry"] == {"long": None, "short": None} and empty["trend"] is None


def test_ladder_endpoint_shape(monkeypatch):
    import time as _t
    from collections import deque
    from fastapi.testclient import TestClient
    import hl_intelligence as hl
    import main
    from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition
    band = {"lo": 2.5, "hi": 2.8, "sma20": 2.5, "ema21": 2.8, "week_close": 3.2, "week": 0,
            "state": "above", "d": 0.179, "fill": 0.405}
    item = {"coin": "SUI", "symbol": "SUI/USDT", "price": 3.3, "stage": "running", "zscore": 0.8, "band": band}
    monkeypatch.setitem(main._SETUP_MAP_CACHE, "1d", (_t.time(), {"coins": [item]}))
    main._LADDER_CACHE.clear()
    a = TrackedWallet("0x" + "1" * 40)
    p = WalletPosition(coin="SUI", side="LONG", size=100, size_usd=300.0, entry_px=3.0, unrealized_pnl=30.0,
                       leverage=5.0, margin_used=60.0)
    monkeypatch.setattr(hl, "_roster", [a])
    monkeypatch.setattr(hl, "_roster_money_printers", [a])
    monkeypatch.setattr(hl, "_snapshots", {a.address: deque([PositionSnapshot(_t.time(), [p], 1e6)])})
    c = TestClient(main.app)
    body = c.get("/api/setup-map/ladder?coin=SUI&tf=1d").json()
    assert set(body) == {"coin", "symbol", "price", "stage", "zscore", "updated_at", "band", "entry", "trend", "counts",
                         "median_entry", "positions"}
    assert body["band"] == band and body["counts"] == {"long": 1, "short": 0, "long_usd": 300, "short_usd": 0,
                                                              "long_wallets": 1, "short_wallets": 0}
    assert body["positions"] == [{"address": a.address, "side": "long", "size_usd": 300, "entry": 3.0, "leverage": 5.0,
                                  "upnl": 30, "roe": 50.0, "move": 10.0, "entity": None}]
    assert body["median_entry"] == {"long": 3.0, "short": None}
    assert c.get("/api/setup-map/ladder?coin=NOPE&tf=1d").status_code == 404
    assert c.get("/api/setup-map/ladder?coin=SUI&tf=1w").status_code == 422
    main._LADDER_CACHE.clear()


def test_day_ago_reads_the_close_nearest_24h_back():
    now = 1_800_000_000
    lean = {"SUI": {now - 86400 - 3600: (4, 1), now - 3600: (6, 1)}, "BTC": {now - 3600: (9, 2)}}
    assert sm.day_ago(lean, ["SUI", "BTC"], now) == {"SUI": {"long": 4, "short": 1}, "BTC": {"long": 0, "short": 0}}
    assert sm.day_ago({"SUI": {now - 3600: (6, 1)}}, ["SUI"], now) == {}       # no close near a day ago
    assert sm.day_ago({}, ["SUI"], now) == {}
