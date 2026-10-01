"""Renamed Hyperliquid tickers (FTM -> S, MATIC -> POL, RNDR -> RENDER): current names everywhere,
and stored records under the old names moved once, idempotently, without touching the executor."""
import json
import pickle
import sqlite3
import time

import numpy as np

import ticker_renames as tr


# ------------------------------------------------------------------ names
def test_current_names_in_every_form():
    assert tr.current_coin("MATIC") == "POL" and tr.current_coin("RNDR") == "RENDER" and tr.current_coin("FTM") == "S"
    assert tr.current_coin("BTC") == "BTC" and tr.current_coin("POL") == "POL"
    assert tr.current_symbol("MATIC/USDT") == "POL/USDT"
    assert tr.current_symbol("RNDR/USDT:USDT") == "RENDER/USDT:USDT"
    assert tr.current_symbol("coin:FTM") == "coin:S"
    assert tr.current_symbol("FTM") == "S"
    # Only exact tickers: FTMX or MATICX are other coins, and spot pairs keep their names.
    assert tr.current_symbol("FTMX/USDT") == "FTMX/USDT" and tr.current_symbol("S/USDT") == "S/USDT"
    assert tr.current_symbol("") == "" and tr.current_symbol(None) is None


def test_live_maps_use_current_names():
    import data_fetcher
    import scanner
    from hl_intelligence import _normalize_coin
    for old, new in tr.RENAMED.items():
        assert _normalize_coin(new) == new and _normalize_coin(f"{new}/USDT") == new
        assert data_fetcher._hl_coin_name(f"{new}/USDT") == new
    lists = data_fetcher.DEFAULT_SYMBOLS + data_fetcher.FULL_SYMBOLS + scanner.TIER1_SYMBOLS
    assert not [s for s in lists if tr.renamed(s)]
    assert "RENDER/USDT" in scanner.TIER1_SYMBOLS and "POL/USDT" in data_fetcher.FULL_SYMBOLS
    # The "k" markets map both ways under one key (test_k_markets.py).
    assert data_fetcher._hl_coin_name("KPEPE/USDT") == "kPEPE" and _normalize_coin("kPEPE") == "KPEPE"


def test_sectors_use_current_names_and_studies_keep_theirs():
    import sectors
    assert sectors.groups("POL") == ("sector:Layer 2", "ecosystem:Ethereum", "pocket:Layer 2|Ethereum")
    assert sectors.groups("RENDER")[0] == "sector:AI" and sectors.groups("S") == ("sector:Layer 1",)
    assert not set(tr.RENAMED) & set(sectors._S)
    # The studies' coin lists (old Binance pairs too) are unchanged, in the same order.
    assert list(sectors.STUDY_S)[-3:] == ["RNDR", "FTM", "MATIC"]
    assert sectors.STUDY_S["MATIC"] == sectors._S["POL"]


def test_lists_and_keys():
    assert tr.rename_list(["BTC/USDT", "MATIC/USDT", "POL/USDT", "RNDR/USDT"]) == (["BTC/USDT", "POL/USDT", "RENDER/USDT"], 2)
    d, n = tr.rename_keys({"POL": {"tf": "4h"}, "MATIC": {"tf": "1d"}, "FTM": {"tf": "1d"}, "BTC": {}})
    assert d == {"POL": {"tf": "4h"}, "S": {"tf": "1d"}, "BTC": {}} and n == 2


# ------------------------------------------------------------------ SQLite stores
def _make_stores(tmp_path):
    import accounts
    import radar_log
    from cohorts import store as cstore
    from hl_persistence import _SCHEMA as HL_SCHEMA
    from opportunity_journal import OpportunityJournal

    paths = {k: tmp_path / f"{k}.db" for k in ("signal_events", "signal_outcomes", "hyperlens", "cohorts", "accounts", "opportunities")}
    c = sqlite3.connect(paths["signal_events"])
    c.executescript("CREATE TABLE signal_events (id INTEGER PRIMARY KEY, symbol TEXT, timeframe TEXT, signal TEXT, timestamp REAL);"
                    "CREATE TABLE regime_events (id INTEGER PRIMARY KEY, symbol TEXT, timeframe TEXT, regime TEXT, timestamp REAL);")
    c.executemany("INSERT INTO signal_events (symbol, timeframe, signal, timestamp) VALUES (?, '4h', ?, ?)",
                  [("MATIC/USDT", "LIGHT_LONG", 1), ("POL/USDT", "WAIT", 2), ("FTM/USDT", "TRIM", 3), ("BTC/USDT", "WAIT", 4)])
    c.execute("INSERT INTO regime_events (symbol, timeframe, regime, timestamp) VALUES ('RNDR/USDT', '1d', 'MARKUP', 1)")
    c.commit(); c.close()

    c = sqlite3.connect(paths["signal_outcomes"])
    c.execute("CREATE TABLE signal_outcomes (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, signal TEXT)")
    c.execute("INSERT INTO signal_outcomes (symbol, signal) VALUES ('MATIC/USDT', 'STRONG_LONG')")
    c.commit(); c.close()

    c = sqlite3.connect(paths["hyperlens"])
    c.executescript(HL_SCHEMA)
    radar_log.ensure(c)
    row = lambda day, coin: (day, coin, 0.0, "quiet", "running", "quiet", 1, 0, None, 10.0, None, None, 0.1, 1.0, 1.0,
                             None, None, 0, 1, 2, 1)
    radar_log.write(c, [row(100, "MATIC"), row(200, "MATIC"), row(200, "POL"), row(100, "BTC")])
    c.executemany("INSERT INTO trader_lean (bar_close, grp, long, short, long_usd, short_usd) VALUES (?, ?, 1, 0, 5, 0)",
                  [(1, "coin:RNDR"), (2, "coin:RNDR"), (1, "sector:AI"), (1, "coin:BTC")])
    # Raw Hyperliquid records keep the names the markets traded under.
    c.execute("INSERT INTO position_first_seen VALUES ('0xa', 'MATIC', 1)")
    c.commit(); c.close()

    s = cstore.Store(str(paths["cohorts"]))
    s.write_snapshot(1000, [{"dimension": "size", "cohort": "whale", "symbol": "FTM", "bias": 0.5},
                            {"dimension": "size", "cohort": "whale", "symbol": None, "bias": 0.1}])
    s.db.execute("INSERT INTO wallet_state_latest VALUES ('0xa', 1, 100, ?)",
                 (json.dumps([["MATIC", 50.0, 1, 123.0, 2.0], ["BTC", 10.0, 0, 5.0, 0.1]]),))
    s.db.commit(); s.db.close()

    c = sqlite3.connect(paths["accounts"])
    c.executescript(accounts.SCHEMA)
    c.executemany("INSERT INTO watch VALUES (?, ?, '1d', 1)", [("u1", "MATIC"), ("u1", "POL"), ("u2", "RNDR")])
    c.commit(); c.close()

    j = OpportunityJournal(paths["opportunities"])
    j.db.execute("INSERT INTO states VALUES ('RNDR/USDT', '4h', '{}')")
    j.db.execute("INSERT INTO snapshots VALUES ('RNDR/USDT', '4h', 1, 'v', '{}')")
    j.db.execute("INSERT INTO transitions (observed_at, symbol, timeframe) VALUES (1, 'RNDR/USDT', '4h')")
    j.db.commit(); j.db.close()
    return paths


def _q(path, sql):
    c = sqlite3.connect(path)
    try:
        return c.execute(sql).fetchall()
    finally:
        c.close()


def test_migrate_stores_renames_once(tmp_path):
    paths = _make_stores(tmp_path)
    marker = tmp_path / "ticker_renames.json"
    state = tr.migrate_stores(paths, marker, executor_state=tmp_path / "none.json")
    assert set(state["done"]) == set(paths) | {"hyperlens_k", "cohorts_k", "accounts_k"}

    assert _q(paths["signal_events"], "SELECT symbol FROM signal_events ORDER BY timestamp") == \
        [("POL/USDT",), ("POL/USDT",), ("S/USDT",), ("BTC/USDT",)]
    assert _q(paths["signal_events"], "SELECT symbol FROM regime_events") == [("RENDER/USDT",)]
    assert _q(paths["signal_outcomes"], "SELECT symbol FROM signal_outcomes") == [("POL/USDT",)]
    # Radar record: the day already read under the current name keeps that reading.
    assert _q(paths["hyperlens"], "SELECT day, coin FROM radar_readings ORDER BY day, coin") == \
        [(100, "BTC"), (100, "POL"), (200, "POL")]
    assert state["done"]["hyperlens"]["radar_readings.coin"] == {"renamed": 1, "duplicates_dropped": 1}
    assert _q(paths["hyperlens"], "SELECT bar_close, grp FROM trader_lean ORDER BY bar_close, grp") == \
        [(1, "coin:BTC"), (1, "coin:RENDER"), (1, "sector:AI"), (2, "coin:RENDER")]
    assert _q(paths["hyperlens"], "SELECT coin FROM position_first_seen") == [("MATIC",)]
    assert _q(paths["cohorts"], "SELECT symbol FROM cohort_snapshots ORDER BY symbol") == [("",), ("S",)]
    (ps,), = _q(paths["cohorts"], "SELECT positions FROM wallet_state_latest")
    assert json.loads(ps) == [["POL", 50.0, 1, 123.0, 2.0], ["BTC", 10.0, 0, 5.0, 0.1]]
    assert _q(paths["accounts"], "SELECT user, coin FROM watch ORDER BY user, coin") == [("u1", "POL"), ("u2", "RENDER")]
    for t in ("states", "snapshots", "transitions"):
        assert _q(paths["opportunities"], f"SELECT symbol FROM {t}") == [("RENDER/USDT",)]

    # Once: a second start skips every store, and a fresh run over migrated stores changes nothing.
    before = {k: _q(p, "SELECT COUNT(*) FROM sqlite_master") for k, p in paths.items()}
    again = tr.migrate_stores(paths, marker, executor_state=tmp_path / "none.json")
    assert again["done"] == state["done"]
    marker.unlink()
    fresh = tr.migrate_stores(paths, marker, executor_state=tmp_path / "none.json")
    assert all(set(v) == {"at"} for v in fresh["done"].values())
    assert before == {k: _q(p, "SELECT COUNT(*) FROM sqlite_master") for k, p in paths.items()}


def test_missing_store_is_not_created_and_failed_store_retries(tmp_path):
    marker = tmp_path / "m.json"
    paths = {"signal_events": tmp_path / "absent.db", "hyperlens": tmp_path / "broken.db"}
    (tmp_path / "broken.db").write_text("not a database")
    state = tr.migrate_stores(paths, marker, executor_state=tmp_path / "none.json")
    assert not (tmp_path / "absent.db").exists()
    assert state["done"] == {}                       # both tried again at the next start


# ------------------------------------------------------------------ the executor: read only
def test_executor_state_is_reported_never_changed(tmp_path):
    path = tmp_path / "executor_state.json"
    saved = {"mode": "paper", "whitelist": ["BTC/USDT", "MATIC/USDT"],
             "positions": {"RNDR/USDT": {"symbol": "RNDR/USDT"}, "ETH/USDT": {"symbol": "ETH/USDT"}},
             "pair_map": {"FTM/USDT": "FTM", "BTC/USDT": "BTC"},
             "trade_log": [{"symbol": "FTM/USDT"}, {"symbol": "BTC/USDT"}]}
    text = json.dumps(saved, indent=2)
    path.write_text(text)
    state = tr.migrate_stores({}, tmp_path / "m.json", executor_state=path)
    assert path.read_text() == text
    assert state["executor"] == {"checked": True, "old_names": True, "open_positions": ["RNDR/USDT"],
                                 "whitelist": ["MATIC/USDT"], "pair_map": ["FTM/USDT"],
                                 "closed_trade_symbols": ["FTM/USDT"]}
    assert tr.executor_exposure(tmp_path / "absent.json") == {"checked": True, "old_names": False}


# ------------------------------------------------------------------ stores renamed on load
def test_ohlcv_cache_loads_under_current_names(tmp_path):
    from data_fetcher import OHLCVStore
    n = 250
    series = lambda close: {f: np.full(n, close, dtype=np.float64) for f in ("open", "high", "low", "close", "volume")} | \
        {"timestamp": np.arange(n, dtype=np.float64) * 86_400_000}
    now = time.time()
    path = tmp_path / "ohlcv_cache.pkl"
    with open(path, "wb") as f:
        pickle.dump({"version": 3, "saved_at": now, "store": {
            "MATIC/USDT|1d": series(0.4), "FTM/USDT|1d": series(0.7), "S/USDT|1d": series(0.3), "BTC/USDT|1d": series(9.0)},
            "history_targets": {"MATIC/USDT|1d": 600, "FTM/USDT|1d": 600},
            "observed_at": {"MATIC/USDT|1d": now - 60, "S/USDT|1d": now - 30}}, f)
    s = OHLCVStore()
    assert s.load_from_disk(path)
    assert sorted(s._store) == ["BTC/USDT|1d", "POL/USDT|1d", "S/USDT|1d"]
    assert float(s.get("POL/USDT", "1d")["close"][-1]) == 0.4
    assert float(s.get("S/USDT", "1d")["close"][-1]) == 0.3        # the current series wins
    assert s._history_targets == {"POL/USDT|1d": 600}
    assert abs(s.observed_at("POL/USDT", "1d") - (now - 60)) < 5
    assert s.save_to_disk(path, force=True)
    again = OHLCVStore()
    again.load_from_disk(path)
    assert sorted(again._store) == ["BTC/USDT|1d", "POL/USDT|1d", "S/USDT|1d"]


def test_favorites_load_under_current_names(tmp_path, monkeypatch):
    import favorites
    path = tmp_path / "favorites.json"
    path.write_text(json.dumps(["MATIC/USDT", "POL/USDT", "RNDR/USDT", "BTC/USDT"]))
    monkeypatch.setattr(favorites, "_FAVORITES_PATH", path)
    monkeypatch.setattr(favorites, "_PERSIST_DIR", tmp_path)
    monkeypatch.setattr(favorites, "_favorites", set())
    favorites.load()
    assert favorites.get() == {"POL/USDT", "RENDER/USDT", "BTC/USDT"}
    assert json.loads(path.read_text()) == ["BTC/USDT", "POL/USDT", "RENDER/USDT"]
    favorites.add("ftm")
    assert "S/USDT" in favorites.get()


def test_radar_watch_list_loads_under_current_names(tmp_path, monkeypatch):
    import setup_map as sm
    path = tmp_path / "watched_coins.json"
    path.write_text(json.dumps({"MATIC": {"tf": "1d", "added": 1, "state": None}, "BTC": {"tf": "4h", "added": 2, "state": None}}))
    monkeypatch.setattr(sm, "_FILE", path)
    monkeypatch.setattr(sm, "_watch", {})
    monkeypatch.setattr(sm, "_loaded", False)
    assert set(sm.watched()) == {"POL", "BTC"}
    assert set(json.loads(path.read_text())) == {"POL", "BTC"}
    sm.unwatch("MATIC")
    assert set(sm.watched()) == {"BTC"}
    assert sm.watch("RNDR", "1d") and "RENDER" in sm.watched()
