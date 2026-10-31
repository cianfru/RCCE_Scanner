"""The coin page's long/short record: cohort groups per coin, profitable traders, rebuild markers."""
import asyncio
import os
import sqlite3
import time
from unittest import mock

import pytest

from cohorts.assign import Position, WalletState, aggregate, coin_groups, coin_groups_from_rows
from cohorts.store import Store
from cohorts.sweeper import Sweeper, TokenBucket


def _w(addr, equity, pnl, *ps):
    return WalletState(addr, equity, pnl, [Position(c, usd, long, 0.0) for c, usd, long in ps])


STATES = [
    _w("a", 2e6, 5e6, ("BTC", 300.0, True), ("ETH", 100.0, False)),     # winner and whale
    _w("b", 200e3, 150e3, ("BTC", 50.0, False)),                         # winner
    _w("c", 50e3, -20e3, ("BTC", 70.0, True), ("PURR", 5.0, True)),      # loser
    _w("d", 3e6, 20e3, ("PURR", 9.0, False)),                            # whale only
    _w("e", 500e3, 50e3),                                                # no position: not counted
    _w("mm", 2e6, 5e6, *[(f"C{i}", 1.0, True) for i in range(30)]),      # market maker: excluded
]


def test_coin_groups_merge_cohorts_and_count_each_wallet_on_its_net_side():
    g = coin_groups(STATES)
    assert g["BTC"]["winners"] == [1, 1, 300.0, 50.0]
    assert g["BTC"]["losers"] == [1, 0, 70.0, 0.0]
    assert g["BTC"]["whales"] == [1, 0, 300.0, 0.0]
    assert g["PURR"]["whales"] == [0, 1, 0.0, 9.0]
    assert "winners" not in g["PURR"]
    assert g[""]["winners"] == [1, 1, 300.0, 150.0]       # a net long over all coins, b short
    assert "C0" not in g


def test_groups_from_stored_cohort_rows_match_groups_from_states():
    # The backfill path (from the 40-coin cohort rows) gives the same numbers for those coins.
    rows = aggregate(STATES, now=1_000_000.0, top_symbols=40)
    assert coin_groups_from_rows(rows) == coin_groups(STATES)


def _store(tmp_path):
    return Store(str(tmp_path / "c.db"))


def test_record_once_per_4h_candle_with_every_coin_and_a_time_marker(tmp_path):
    st = _store(tmp_path)
    sw = Sweeper(st, None, TokenBucket(6000))
    bar = 14400 * 5000
    sw.record_coin_groups(STATES, bar + 100)
    sw.record_coin_groups(STATES, bar + 1900)               # same candle: not stored again
    sw.record_coin_groups(STATES[:1], bar + 14400 + 60)     # next candle: only wallet a
    times, vals = st.coin_history("PURR", 0)
    assert times == [(bar + 100, 1), (bar + 14400 + 60, 1)]
    assert list(vals) == [bar + 100]                         # nobody held PURR at the second time
    assert vals[bar + 100][8:12] == (0, 1, 0, 9)             # whales: 1 short, $9
    import cohorts.sweeper as mod
    assert mod.live_coin_groups()[0] == bar + 14400 + 60


def test_backfill_fills_the_40_coin_history_once_and_marks_it_partial(tmp_path):
    st = _store(tmp_path)
    t0 = 14400 * 5000 + 1260
    st.write_snapshot(t0, aggregate(STATES, t0, top_symbols=1))    # only BTC kept, as the top-40 cut does
    sw = Sweeper(st, None, TokenBucket(6000))
    sw.record_coin_groups(STATES, t0 + 14400)
    times, vals = st.coin_history("BTC", 0)
    assert times == [(t0, 0), (t0 + 14400, 1)]
    assert vals[t0][:4] == (1, 1, 300, 50)
    times, vals = st.coin_history("PURR", 0)
    assert list(vals) == [t0 + 14400]                        # PURR was outside the cut: not recorded at t0
    assert st.backfill_coin_groups() == 0                     # only while empty


@pytest.fixture
def hl_db(tmp_path):
    import hl_persistence as hp
    with mock.patch.object(hp, "_DB_PATH", str(tmp_path / "hl.db")), mock.patch.object(hp, "_conn", None):
        yield hp
        if hp._conn is not None:
            hp._conn.close()


def test_roster_rebuilds_count_who_joined_and_left(hl_db):
    hp = hl_db
    t = int(time.time()) - 7200
    assert hp.save_roster_rebuild(t, ["a", "b", "c"]) == (None, None)
    assert hp.save_roster_rebuild(t + 3600, ["b", "c", "d", "e"]) == (2, 1)
    assert hp.load_roster_rebuilds(0) == [(t, 3, None, None, None), (t + 3600, 4, 2, 1, None)]


def test_past_rebuilds_are_estimated_from_first_snapshots(hl_db):
    hp = hl_db
    conn = hp._get_conn()
    h0 = int(time.time() // 3600) * 3600 - 50 * 3600
    rows = [(f"old{i}", h0 + t * 3600) for i in range(10) for t in range(30)]      # tracked all along
    rows += [(f"flat{i}", h0 + 2 * 3600 + 60 + t * 7200) for i in range(8) for t in range(14)]  # flat: read
    #   every 2 h, so their oldest snapshot after the 30-day cut is hours after the oldest of all: no marker
    rows += [(f"new{i}", h0 + 20 * 3600 + 120) for i in range(6)]                   # six joined at hour 20
    rows += [("lone", h0 + 25 * 3600)]                                              # one: no marker
    conn.executemany("INSERT INTO snapshots (address, timestamp, account_value, positions_json) "
                     "VALUES (?, ?, 0, '[]')", rows)
    hp.save_roster_rebuild(h0 + 40 * 3600, ["x"])
    assert hp.load_roster_rebuilds(0)[:-1] == [(h0 + 20 * 3600, None, 6, None, None)]


def test_the_switch_to_new_roster_rules_is_marked_once(hl_db):
    hp = hl_db
    b = int(time.time() // 14400) * 14400 - 10 * 14400
    row = {"coin:BTC": {"long": 1, "short": 0, "long_usd": 1.0, "short_usd": 0.0}}
    hp.save_trader_lean(b, row)                       # rules version 1: roster_version NULL
    hp.save_trader_lean(b + 14400, row, 2)
    hp.save_trader_lean(b + 28800, row, 2)
    hp.save_roster_rebuild(b + 40000, ["a"])
    assert hp.load_roster_rebuilds(0)[0] == (b + 14400, None, None, None, "rules")


def test_rules_marker_when_a_restart_left_both_versions_at_the_switch_close(hl_db):
    hp = hl_db
    b = int(time.time() // 14400) * 14400 - 10 * 14400
    two = {"coin:BTC": {"long": 1, "short": 0, "long_usd": 1.0, "short_usd": 0.0},
           "coin:PURR": {"long": 1, "short": 0, "long_usd": 1.0, "short_usd": 0.0}}
    hp.save_trader_lean(b, two)
    hp.save_trader_lean(b + 14400, two)                                    # old process
    hp.save_trader_lean(b + 14400, {"coin:BTC": two["coin:BTC"]}, 2)       # new process rewrote part of it
    hp.save_trader_lean(b + 28800, {"coin:BTC": two["coin:BTC"]}, 2)
    hp.save_roster_rebuild(b + 40000, ["a"])
    assert [r for r in hp.load_roster_rebuilds(0) if r[4] == "rules"] == [(b + 14400, None, None, None, "rules")]


def test_prefix_reads_stay_on_the_close_key(hl_db):
    hp = hl_db
    plan = " ".join(str(r) for r in hp._get_conn().execute(
        "EXPLAIN QUERY PLAN SELECT bar_close, grp, long, short, long_usd, short_usd FROM trader_lean "
        "WHERE +grp >= ? AND +grp < ? AND bar_close >= ? ORDER BY bar_close", ("coin:", "coin:\uffff", 0)))
    assert "idx_tl_grp" not in plan
    one = " ".join(str(r) for r in hp._get_conn().execute(
        "EXPLAIN QUERY PLAN SELECT bar_close FROM trader_lean WHERE grp = ? AND bar_close >= ?", ("coin:BTC", 0)))
    assert "idx_tl_grp" in one


def test_a_restart_does_not_rewrite_a_recorded_close(hl_db, monkeypatch):
    import hl_intelligence as hl
    import scan_schedule
    hp = hl_db
    now = time.time()
    bar = int(scan_schedule.last_bar_close(now)) - scan_schedule.SETTLE_SECONDS
    hp.save_trader_lean(bar, {"coin:BTC": {"long": 7, "short": 0, "long_usd": 7.0, "short_usd": 0.0}}, 2)
    monkeypatch.setattr(hl, "_last_lean_bar", 0)
    monkeypatch.setattr(hl, "_roster", ["w"])
    monkeypatch.setattr(hl, "_mp_book", {"e": {"BTC": -5.0}})
    monkeypatch.setattr("activity.is_active", lambda: True)
    assert asyncio.run(hl.record_lean_at_bar_close(now)) is False
    assert hp.load_coin_lean("BTC", 0)[1] == {bar: (7, 0, 7.0, 0.0)}


def test_coin_lean_zero_fills_closes_where_nobody_held_the_coin(hl_db):
    hp = hl_db
    b = int(time.time()) - 28800
    hp.save_trader_lean(b, {"coin:BTC": {"long": 3, "short": 1, "long_usd": 30.0, "short_usd": 5.0},
                            "coin:BTCX": {"long": 9, "short": 9, "long_usd": 9.0, "short_usd": 9.0}})
    hp.save_trader_lean(b + 14400, {"coin:ETH": {"long": 1, "short": 0, "long_usd": 1.0, "short_usd": 0.0}})
    bars, vals = hp.load_coin_lean("BTC", 0)
    assert bars == [b, b + 14400] and vals == {b: (3, 1, 30.0, 5.0)}


def test_endpoint_merges_both_records_and_appends_live_points(tmp_path, hl_db):
    from fastapi.testclient import TestClient
    import cohorts.sweeper as mod
    import hl_intelligence as hl
    import main
    now = time.time()
    bar = int(now // 14400) * 14400
    hp = hl_db
    hp.save_trader_lean(bar - 14400, {"coin:BTC": {"long": 3, "short": 1, "long_usd": 30.0, "short_usd": 5.0}})
    hp.save_trader_lean(bar, {"coin:ETH": {"long": 1, "short": 0, "long_usd": 1.0, "short_usd": 0.0}})
    hp.save_roster_rebuild(bar - 7200, ["a"])
    hp.save_roster_rebuild(bar - 3600, ["b", "c", "d", "e", "f", "g"])
    old = mod._store
    mod._store = _store(tmp_path)
    main._COIN_POS_CACHE.clear()
    try:
        sw = Sweeper(mod._store, None, TokenBucket(6000))
        sw.record_coin_groups(STATES, now - 600)
        live = {"BTC": {"long": 4, "short": 2, "long_usd": 40.0, "short_usd": 9.0}}
        with mock.patch.object(main, "_profitable_live", return_value=live):
            body = TestClient(main.app).get("/api/coin-positioning?coin=BTC/USDT&days=7").json()
    finally:
        mod._store = old
    p = body["groups"]["profitable"]
    assert body["coin"] == "BTC"
    assert p["t"][:2] == [bar - 14400, bar] and p["ln"] == [3, 0, 4] and p["su"] == [5, 0, 9]
    assert p["live"] is True
    w = body["groups"]["winners"]
    assert w["ln"] == [1] and w["lu"] == [300] and w["live"] is False   # the stored time is the latest
    assert body["rebuilds"] == [{"t": bar - 3600, "joined": 6, "left": 1, "note": None}]
    assert body["covered"] is True


def test_endpoint_cache_is_bounded_and_builder_dex_coins_are_not_covered(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    main._COIN_POS_CACHE.clear()
    monkeypatch.setattr(main, "_coin_positioning_body",
                        lambda c, d, now: {"coin": c, "days": d, "groups": {}, "rebuilds": [], "held": {}})
    c = TestClient(main.app)
    for i in range(main._COIN_POS_CACHE_MAX + 10):
        assert c.get(f"/api/coin-positioning?coin=C{i}&days=7").json()["coin"] == f"C{i}"
    assert len(main._COIN_POS_CACHE) == main._COIN_POS_CACHE_MAX
    assert c.get("/api/coin-positioning?coin=xyz:GOLD").json()["covered"] is False
    assert c.get("/api/coin-positioning?coin=BTC&days=180").status_code == 422
