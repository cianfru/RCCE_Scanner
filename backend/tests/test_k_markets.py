"""Hyperliquid's "k" markets (kPEPE, kBONK ...: perps quoted per 1,000 tokens) under one key.

The scanner's symbol is KPEPE/USDT, so the app's key is "KPEPE"; HyperLens positions arrive as
"kPEPE" and must land on the same key, and Hyperliquid is always asked by its own name.
"""
import json
import sqlite3
import time
from collections import deque

import pytest

import hl_intelligence as hl
import setup_map as sm
import ticker_renames as tr
from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition, _normalize_coin

# Hyperliquid's meta, 2026-10-01: the k markets (kDOGS delisted) and two ordinary K tickers.
LIVE_K = ["kPEPE", "kSHIB", "kBONK", "kLUNC", "kFLOKI", "kDOGS", "kNEIRO"]


# ------------------------------------------------------------------ the key, both ways
@pytest.mark.parametrize("hl_coin", LIVE_K)
def test_key_round_trip(hl_coin):
    import data_fetcher
    key = "K" + hl_coin[1:]
    assert _normalize_coin(hl_coin) == key                         # a HyperLens position
    assert _normalize_coin(f"{key}/USDT") == key                   # a scan row
    assert _normalize_coin(key) == key and _normalize_coin(f"{key}/USDT:USDT") == key
    assert _normalize_coin(f"1000{hl_coin[1:]}") == key            # the same per-1,000 unit elsewhere
    assert tr.hl_name(key) == hl_coin and tr.k_key(hl_coin) == key
    assert data_fetcher._hl_coin_name(f"{key}/USDT") == hl_coin    # candles asked by Hyperliquid's name


def test_ordinary_tickers_are_left_alone(monkeypatch):
    import data_fetcher
    import hyperliquid_universe
    monkeypatch.setattr(hyperliquid_universe, "MARKETS", {})
    for coin in ("KAS", "KAITO", "BTC", "S", "POL"):
        assert _normalize_coin(coin) == coin and tr.hl_name(coin) == coin
        assert data_fetcher._hl_coin_name(f"{coin}/USDT") == coin
    # The bare base is a 1-token instrument: never mapped onto the per-1,000 market.
    assert _normalize_coin("PEPE") == "PEPE" and tr.hl_name("PEPE") == "PEPE"
    assert data_fetcher._hl_coin_name("PEPE/USDT") == "PEPE"
    assert _normalize_coin("xyz:GOLD") == "xyz:GOLD"


def test_a_new_k_market_follows_the_universe(monkeypatch):
    import hyperliquid_universe
    markets = hyperliquid_universe.parse_markets({"universe": [{"name": "kFOO"}, {"name": "KAS"}]},
                                                 {"tokens": [], "universe": []})
    monkeypatch.setattr(hyperliquid_universe, "MARKETS", markets)
    assert set(markets) == {"KFOO/USDT", "KAS/USDT"}
    assert _normalize_coin("kFOO") == "KFOO" and tr.hl_name("KFOO") == "kFOO"
    assert tr.hl_name("KAS") == "KAS"


def test_sectors_know_the_key():
    import sectors
    assert sectors.groups("KPEPE") == sectors.groups("PEPE") == ("sector:Memes", "ecosystem:Ethereum", "pocket:Memes|Ethereum")
    assert sectors.groups("KLUNC")[0] == "sector:Layer 1" and sectors.classify("KAS/USDT", "KAS")[0] == "Layer 1"
    assert "KPEPE" not in sectors.STUDY_S                          # the studies' coin lists unchanged


# ------------------------------------------------------------------ the Radar row gets its traders
def _pos(coin, side, size, entry, mark):
    pnl = (mark - entry) * size * (1 if side == "LONG" else -1)
    return WalletPosition(coin=coin, side=side, size=size, size_usd=size * entry, entry_px=entry,
                          unrealized_pnl=pnl, leverage=3.0)


@pytest.fixture
def k_book(monkeypatch):
    """Three profitable traders, two long kPEPE (per 1,000 tokens: ~$0.0098), one short kBONK."""
    ws = [TrackedWallet("0xa"), TrackedWallet("0xb"), TrackedWallet("0xc")]
    now = time.time()
    snaps = {
        "0xa": deque([PositionSnapshot(now, [_pos("kPEPE", "LONG", 1e6, 0.0100, 0.0098)], 1e6)]),
        "0xb": deque([PositionSnapshot(now, [_pos("kPEPE", "LONG", 5e5, 0.0096, 0.0098)], 1e6)]),
        "0xc": deque([PositionSnapshot(now, [_pos("kBONK", "SHORT", 1e6, 0.0200, 0.0190)], 1e6)]),
    }
    monkeypatch.setattr(hl, "_roster", ws)
    monkeypatch.setattr(hl, "_roster_money_printers", ws)
    monkeypatch.setattr(hl, "_roster_smart_money", [])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    return now


def test_radar_row_gets_trader_counts_and_entry(k_book):
    now = k_book
    pm = hl.positioning_map("profitable")
    assert set(pm["coins"]) == {"KPEPE", "KBONK"}
    opens = [{"coin": _normalize_coin("kPEPE"), "cohort": "profitable", "side": "long", "ts": now - 60, "address": "0xa"}]

    class Store:
        def get(self, sym, tf):
            return None
    rows = [{"symbol": "KPEPE/USDT", "market_kind": "perpetual", "price": 0.0098, "zscore": 0.2, "signal": "WAIT", "regime": "MARKUP"},
            {"symbol": "KBONK/USDT", "market_kind": "perpetual", "price": 0.0190, "zscore": -0.1, "signal": "WAIT", "regime": "MARKUP"}]
    out = {c["coin"]: c for c in sm.build(rows, "1d", Store(), pm["coins"], {}, opens, {}, now)["coins"]}
    pepe, bonk = out["KPEPE"], out["KBONK"]
    assert (pepe["traders"]["pl"], pepe["traders"]["ps"], pepe["traders"]["n24l"]) == (2, 0, 1)
    assert (bonk["traders"]["pl"], bonk["traders"]["ps"]) == (0, 1)
    assert pepe["money"]["long_usd"] == round(1e6 * 0.0100 + 5e5 * 0.0096)
    # Like for like: both prices per 1,000 tokens, so the entry sits a few percent from the price.
    avg = (1e6 * 0.0100 * 0.0100 + 5e5 * 0.0096 * 0.0096) / (1e6 * 0.0100 + 5e5 * 0.0096)
    assert pepe["entry"]["dist_pct"] == round(100 * (0.0098 / avg - 1), 2) and abs(pepe["entry"]["dist_pct"]) < 5


def test_coin_page_and_trader_filters_match(k_book):
    held = hl.get_symbol_positions("KPEPE/USDT")
    assert sorted(p["address"] for p in held) == ["0xa", "0xb"]
    assert all(p["coin"] == "kPEPE" for p in held)                 # the raw name stays on the record
    import trader_profile as tp
    for f in ("KPEPE", "kPEPE", "KPEPE/USDT"):
        assert tp._match(f, "kPEPE")
    assert not tp._match("PEPE", "kPEPE") and not tp._match("KAS", "kPEPE")


def test_position_changes_compare_on_the_key(monkeypatch):
    now = time.time()
    w = TrackedWallet("0xa")
    snaps = {"0xa": deque([PositionSnapshot(now - 3600, [], 1e6),
                           PositionSnapshot(now, [_pos("kPEPE", "LONG", 1e6, 0.01, 0.01)], 1e6)])}
    monkeypatch.setattr(hl, "_roster", [w])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    assert hl.get_position_changes("KPEPE/USDT", window_minutes=30)["opened"] == 1


# ------------------------------------------------------------------ stored records
def _stores(tmp_path):
    import accounts
    import convergence
    import radar_log
    from cohorts import store as cstore
    from hl_persistence import _SCHEMA as HL_SCHEMA
    paths = {k: tmp_path / f"{k}.db" for k in ("hyperlens", "cohorts", "accounts")}
    c = sqlite3.connect(paths["hyperlens"])
    c.executescript(HL_SCHEMA)
    c.executescript(convergence._SCHEMA)
    radar_log.ensure(c)
    row = lambda day, coin: (day, coin, 0.0, "quiet", "running", "quiet", 0, 0, None, 0.0, None, None, 0.1, 0.0098, 0.0098,
                             None, None, 0, 1, 2, 1)
    radar_log.write(c, [row(100, "KPEPE"), row(100, "BTC")])
    c.executemany("INSERT INTO trader_lean (bar_close, grp, long, short, long_usd, short_usd) VALUES (?, ?, 2, 0, 5, 0)",
                  [(1, "coin:PEPE"), (2, "coin:PEPE"), (2, "coin:KPEPE"), (1, "coin:BONK"), (1, "sector:Memes"), (1, "coin:KAS")])
    c.executemany("INSERT INTO position_opens (ts, prev_ts, address, cohort, coin, side, entry_px, size_usd) "
                  "VALUES (1, 0, '0xa', 'profitable', ?, 'long', 0.01, 100)", [("PEPE",), ("BTC",)])
    c.execute("INSERT INTO convergences (ts, coin, side, n, first_ts, first_px, last_px, mark_px, others, wallets) "
              "VALUES (1, 'SHIB', 'long', 2, 0, 0.012, 0.012, 0.012, '[]', '[]')")
    # Raw Hyperliquid records keep Hyperliquid's name.
    c.execute("INSERT INTO position_first_seen VALUES ('0xa', 'kPEPE', 1)")
    c.commit(); c.close()

    s = cstore.Store(str(paths["cohorts"]))
    s.write_snapshot(1000, [{"dimension": "size", "cohort": "whale", "symbol": "PEPE", "bias": 0.5},
                            {"dimension": "size", "cohort": "whale", "symbol": "BTC", "bias": 0.1}])
    s.db.execute("INSERT INTO wallet_state_latest VALUES ('0xa', 1, 100, ?)",
                 (json.dumps([["FLOKI", 50.0, 1, 123.0, 2.0], ["BTC", 10.0, 0, 5.0, 0.1]]),))
    s.db.commit(); s.db.close()

    c = sqlite3.connect(paths["accounts"])
    c.executescript(accounts.SCHEMA)
    c.executemany("INSERT INTO watch VALUES (?, ?, '1d', 1)", [("u1", "PEPE"), ("u1", "KPEPE"), ("u2", "BONK"), ("u2", "BTC")])
    c.commit(); c.close()
    return paths


def _q(path, sql):
    c = sqlite3.connect(path)
    try:
        return c.execute(sql).fetchall()
    finally:
        c.close()


def test_migration_moves_hyperlens_records_to_the_key(tmp_path):
    paths = _stores(tmp_path)
    marker = tmp_path / "ticker_renames.json"
    # A store whose renames already ran under the first marker still gets the k step.
    marker.write_text(json.dumps({"version": tr.VERSION, "done": {"hyperlens": {"at": 1}, "cohorts": {"at": 1}, "accounts": {"at": 1}}}))
    state = tr.migrate_stores(paths, marker, executor_state=tmp_path / "none.json")
    assert {"hyperlens_k", "cohorts_k", "accounts_k"} <= set(state["done"])

    # The day already recorded under the key wins; other groups and coins untouched.
    assert _q(paths["hyperlens"], "SELECT bar_close, grp FROM trader_lean ORDER BY bar_close, grp") == \
        [(1, "coin:KAS"), (1, "coin:KBONK"), (1, "coin:KPEPE"), (1, "sector:Memes"), (2, "coin:KPEPE")]
    assert _q(paths["hyperlens"], "SELECT coin FROM position_opens ORDER BY coin") == [("BTC",), ("KPEPE",)]
    assert _q(paths["hyperlens"], "SELECT coin FROM convergences") == [("KSHIB",)]
    assert _q(paths["hyperlens"], "SELECT coin FROM radar_readings ORDER BY coin") == [("BTC",), ("KPEPE",)]
    assert _q(paths["hyperlens"], "SELECT coin FROM position_first_seen") == [("kPEPE",)]
    assert _q(paths["cohorts"], "SELECT symbol FROM cohort_snapshots ORDER BY symbol") == [("BTC",), ("KPEPE",)]
    (ps,), = _q(paths["cohorts"], "SELECT positions FROM wallet_state_latest")
    assert json.loads(ps) == [["KFLOKI", 50.0, 1, 123.0, 2.0], ["BTC", 10.0, 0, 5.0, 0.1]]
    assert _q(paths["accounts"], "SELECT user, coin FROM watch ORDER BY user, coin") == \
        [("u1", "KPEPE"), ("u2", "BTC"), ("u2", "KBONK")]

    # Once, and idempotent: a second start skips; a fresh run over migrated stores changes nothing.
    again = tr.migrate_stores(paths, marker, executor_state=tmp_path / "none.json")
    assert again["done"] == state["done"]
    marker.unlink()
    fresh = tr.migrate_stores(paths, marker, executor_state=tmp_path / "none.json")
    assert all(set(v) == {"at"} for v in fresh["done"].values())


def test_executor_state_is_not_touched_by_the_k_step(tmp_path):
    path = tmp_path / "executor_state.json"
    text = json.dumps({"positions": {"BONK/USDT": {"symbol": "BONK/USDT"}}, "whitelist": ["PEPE/USDT", "KPEPE/USDT"]})
    path.write_text(text)
    state = tr.migrate_stores({}, tmp_path / "m.json", executor_state=path)
    assert path.read_text() == text and state["executor"]["old_names"] is False
