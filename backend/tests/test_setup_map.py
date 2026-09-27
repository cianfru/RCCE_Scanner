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
