"""Lockstep wallets (hl_entities) and counting them as one trader."""
import asyncio
import os
import sqlite3
import tempfile
import time
from collections import deque
from unittest import mock

import pytest

import hl_entities as ent
import hl_intelligence as hl
import setup_map
from convergence import Tracker
from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition

H, D = 3600.0, 86400.0
NOW = 1_800_000_000.0
BTC = 100_000.0


def ch(day, hour, coin, before, after, px=BTC, lag_h=1.0):
    """One logged change: seen at day/hour, previous reading lag_h hours earlier."""
    t1 = NOW - 30 * D + day * D + hour * H
    return (t1 - lag_h * H, t1, coin, before, after, px)


def whale(scale, offsets):
    """A BTC-only book built and sold in three steps; offsets shift each step by hours."""
    o1, o2, o3 = offsets
    return [ch(2, 10 + o1, "BTC", 0, 400 * scale), ch(12, 3 + o2, "BTC", 400 * scale, 600 * scale),
            ch(25, 20 + o3, "BTC", 600 * scale, 0)]


def test_lockstep_wallets_are_one_entity_and_independent_ones_are_not():
    changes = {
        "0xaaa1": whale(1.0, (0, 0, 0)),
        "0xaaa2": whale(1.0, (0.3, 0, 31)),          # same moves; the sale a day and a half later
        # Accumulates BTC on the same days, but half a day off every time: not one book.
        "0xeee1": whale(0.5, (12, 12, 12)),
        "0xaaa3": whale(0.66, (0.5, 0, 0)),           # smaller, same proportions
        # Buys the same dip but holds on and trades on alone afterwards.
        "0xbbb1": [ch(2, 12, "BTC", 0, 300), ch(5, 1, "BTC", 300, 350), ch(18, 4, "BTC", 350, 200),
                   ch(28, 9, "BTC", 200, 500)],
        # Busy multi-coin trader: one BTC move lines up, most of what it does does not.
        "0xccc1": [ch(2, 11, "BTC", 0, 50)] + [ch(d, 6, "ETH", 10 * d, 10 * d + 10, px=4000) for d in range(1, 29, 2)],
        # Same three dates as the whales but opposite direction.
        "0xddd1": [ch(2, 10, "BTC", 0, -100), ch(12, 3, "BTC", -100, -150), ch(25, 20, "BTC", -150, 0)],
    }
    books = {"0xbbb1": {"BTC": (500.0, 5e7)}, "0xccc1": {"BTC": (50.0, 5e6), "ETH": (290.0, 1.16e6)}}
    groups, links = ent.find_entities(changes, books, now=NOW)
    assert set(groups) == {"0xaaa1", "0xaaa2", "0xaaa3"}
    assert len(set(groups.values())) == 1 and groups["0xaaa2"] == "grp-aaa1"
    info = {(l["a"], l["b"]): l for l in links}
    assert info[("0xaaa1", "0xaaa2")]["matched"] == 3 and info[("0xaaa1", "0xaaa2")]["correlation"] >= ent.MIN_CORRELATION
    grid = [NOW - 30 * D + k * 4 * H for k in range(181)]
    ok, why = ent.linked(changes["0xaaa1"], changes["0xeee1"], {}, {}, grid, {"BTC": BTC})
    assert not ok and why["matched"] == 3 and why["median_gap_h"] == 12.0


def test_rule_parts():
    ok, info = ent.linked(whale(1, (0, 0, 0)), [ch(2, 10, "BTC", 0, 400), ch(12, 3, "BTC", 400, 600),
                                                ch(20, 1, "BTC", 600, 0)], {}, {},
                          [NOW - 30 * D + k * 4 * H for k in range(181)], {"BTC": BTC})
    assert not ok and info["matched"] == 2 and info["share_a"] < ent.MIN_SHARE     # sold 5 days apart
    # A move needs the same direction: adding to a long does not match cutting one.
    assert ent.match(ent.moves([ch(1, 1, "BTC", 0, 5)]), ent.moves([ch(1, 2, "BTC", 5, 0)])) == []
    # Consecutive changes in one direction are one move.
    ms = ent.moves([ch(1, 1, "BTC", 0, 5), ch(1, 2, "BTC", 5, 9), ch(3, 1, "BTC", 9, 12)])
    assert len(ms) == 2 and ms[0]["usd"] == 9 * BTC
    assert ent.note(3) == "Part of a group of 3 wallets that trade together"


# ---------------------------------------------------------------- counting as one trader

def pos(coin, side, size, entry, mark):
    pnl = (mark - entry) * size * (1 if side == "LONG" else -1)
    return WalletPosition(coin=coin, side=side, size=size, size_usd=abs(size) * entry, entry_px=entry,
                          unrealized_pnl=pnl, leverage=3.0)


@pytest.fixture
def book(monkeypatch):
    """Two lockstep profitable wallets long BTC, one independent profitable wallet short, one large
    account long. The group is grp-aaa1."""
    ws = [TrackedWallet(a, account_value=1e6) for a in ("0xaaa1", "0xaaa2", "0xbbb1", "0xccc1")]
    now = time.time()
    snaps = {
        "0xaaa1": deque([PositionSnapshot(now, [pos("BTC", "LONG", 400, 100.0, 110.0), pos("SOL", "LONG", 10, 200.0, 190.0)], 1e6)]),
        "0xaaa2": deque([PositionSnapshot(now, [pos("BTC", "LONG", 200, 90.0, 110.0)], 1e6)]),
        "0xbbb1": deque([PositionSnapshot(now, [pos("BTC", "SHORT", 100, 120.0, 110.0)], 1e6)]),
        "0xccc1": deque([PositionSnapshot(now, [pos("BTC", "LONG", 1000, 100.0, 110.0)], 2e6)]),
    }
    monkeypatch.setattr(hl, "_roster", ws)
    monkeypatch.setattr(hl, "_roster_money_printers", ws[:3])
    monkeypatch.setattr(hl, "_roster_smart_money", ws[3:])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    monkeypatch.setattr(hl, "_wallet_cohorts", {"0xaaa1": {"money_printer"}, "0xaaa2": {"money_printer"},
                                                "0xbbb1": {"money_printer"}, "0xccc1": {"smart_money"}})
    monkeypatch.setattr(hl, "_entity_of", {"0xaaa1": "grp-aaa1", "0xaaa2": "grp-aaa1"})
    monkeypatch.setattr(hl, "_entity_members", {"grp-aaa1": ["0xaaa1", "0xaaa2"]})
    monkeypatch.setattr(hl, "_consensus", {})
    monkeypatch.setattr(hl, "_mp_book", {})
    return ws


def test_consensus_counts_the_group_once_and_sums_its_dollars(book):
    hl._recompute_consensus()
    btc = hl._consensus["BTC"]
    assert (btc.long_count, btc.short_count) == (2, 1)                 # the group + the large account; one short
    assert (btc.money_printer_long_count, btc.money_printer_short_count) == (1, 1)
    assert btc.money_printer_long_notional == 400 * 100 + 200 * 90    # dollars of both wallets
    assert btc.total_tracked == 3                                      # traders, not wallets
    assert hl._consensus_wallets == 4
    assert set(hl._mp_book) == {"grp-aaa1", "0xbbb1"}
    assert hl._mp_book["grp-aaa1"]["BTC"] == 58_000


def test_trader_record_and_radar_count_the_group_once(book):
    hl._recompute_consensus()
    lean = hl.profitable_lean(lambda c: (f"coin:{c}",))
    assert (lean["coin:BTC"]["long"], lean["coin:BTC"]["short"]) == (1, 1)
    assert lean["coin:BTC"]["long_usd"] == 58_000
    assert hl.profitable_traders_positioned() == 2
    pm = hl.positioning_map("profitable")
    long = pm["coins"]["BTC"]["long"]
    assert (long["n"], long["wallets"], long["usd"]) == (1, 2, 58_000)
    assert long["median_entry"] == pytest.approx((40_000 * 100 + 18_000 * 90) / 58_000)   # dollar-weighted entry
    assert long["in_profit"] == 1
    assert (pm["wallets"], pm["traders"], pm["holding"], pm["traders_holding"]) == (3, 2, 3, 2)
    t = setup_map.traders("BTC", pm["coins"], {}, [], time.time())
    assert t["pl"] - t["ps"] == 0                                       # the Radar's net long: 1 - 1
    positions = hl.cohort_positions("BTC", "profitable")
    assert {p["entity"] for p in positions} == {"grp-aaa1", None}
    lad = setup_map.ladder({"coin": "BTC", "symbol": "BTC/USDT"}, positions, None, time.time())
    assert lad["counts"]["long"] == 1 and lad["counts"]["long_wallets"] == 2
    assert lad["counts"]["long_usd"] == 58_000


def test_group_opening_together_is_not_a_convergence():
    t = Tracker(conn=sqlite3.connect(":memory:"), clock=lambda: 10_000.0)
    t.entity_of = lambda a: {"a1": "grp-a", "a2": "grp-a"}.get(a, a)
    p = {"coin": "SUI", "side": "long", "entry_px": 3.0, "size_usd": 10_000, "mark_px": 3.0}
    for a in ("a1", "a2", "b"):
        t.observe(a, "profitable", 9000, [])
    new = t.observe("a1", "profitable", 9500, [p]) + t.observe("a2", "profitable", 9600, [p])
    assert t.check(new) == []                                          # one trader, two wallets
    assert {o["entity"] for o in new} == {"grp-a"}
    [c] = t.check(t.observe("b", "profitable", 9900, [p]))            # a second trader joins
    assert c["n"] == 2
    opens = [dict(o, ts=9_990.0) for o in new]
    assert setup_map.traders("SUI", {}, {}, opens, 10_000.0)["n24l"] == 1


def test_wallet_and_trader_profiles_show_the_group(book):
    info = hl.entity_info("0xAAA2")
    assert info["id"] == "grp-aaa1" and info["size"] == 2 and info["note"] == "Part of a group of 2 wallets that trade together"
    assert hl.entity_info("0xbbb1") is None
    with mock.patch.object(hl, "_db_load_full_trades", return_value=[]), mock.patch.object(hl, "_db_load_equity", return_value=[]):
        assert hl.get_wallet_profile("0xaaa1")["entity"]["members"] == ["0xaaa1", "0xaaa2"]
    assert [r["entity"] for r in hl.get_roster(min_av=0)][:3] == ["grp-aaa1", "grp-aaa1", None]


# ---------------------------------------------------------------- the change log

def test_change_log_records_real_changes_only(monkeypatch):
    monkeypatch.setattr(hl, "_pending_changes", [])
    t = time.time()
    prev = PositionSnapshot(t - 900, [pos("BTC", "LONG", 10, 100_000.0, 100_000.0)], 1e6)
    same = PositionSnapshot(t, [pos("BTC", "LONG", 10.001, 100_000.0, 100_000.0)], 1e6)        # dust
    hl._note_change("0xa", prev, same)
    assert hl._pending_changes == []
    more = PositionSnapshot(t, [pos("BTC", "LONG", 12, 100_000.0, 100_000.0), pos("ETH", "SHORT", 5, 4000.0, 4000.0)], 1e6)
    hl._note_change("0xa", prev, more)
    assert sorted((c[3], c[4], c[5]) for c in hl._pending_changes) == [("BTC", 10, 12), ("ETH", 0, -5)]
    assert all(c[1] == t - 900 and c[2] == t for c in hl._pending_changes)
    hl._pending_changes.clear()
    stale = PositionSnapshot(t - 5 * 3600, prev.positions, 1e6)                                  # gap too long to time
    hl._note_change("0xa", stale, more)
    assert hl._pending_changes == []


def test_recompute_reads_the_stored_log(monkeypatch):
    import hl_persistence as hp
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(hp, "_DB_PATH", os.path.join(d, "hl.db"))
        monkeypatch.setattr(hp, "_conn", None)
        now = time.time()
        rows = []
        for a, shift in (("0xaaa1", 0), ("0xaaa2", 2)):
            for day, before, after in ((3, 0, 400), (13, 400, 600), (26, 600, 0)):
                t1 = now - 30 * D + day * D + shift * H
                rows.append((a, t1 - H, t1, "BTC", before, after, BTC))
        hp.save_position_changes(rows)
        monkeypatch.setattr(hl, "_roster", [TrackedWallet("0xaaa1"), TrackedWallet("0xaaa2")])
        monkeypatch.setattr(hl, "_snapshots", {})
        monkeypatch.setattr(hl, "_entity_of", {})
        monkeypatch.setattr(hl, "_entity_members", {})
        assert asyncio.run(hl.recompute_entities()) == 1
        assert hl.entity_of("0xaaa2") == "grp-aaa1"
        assert hp.get_db_stats()["position_changes"] == 6
        hp._conn.close()


def test_changes_rebuilt_from_fills_for_the_seed():
    ms = lambda t: int(t * 1000)
    fills = [
        {"coin": "BTC", "time": ms(NOW - 10 * D), "px": "100000", "sz": "2", "side": "B", "startPosition": "0"},
        {"coin": "BTC", "time": ms(NOW - 10 * D + 120), "px": "100100", "sz": "1", "side": "B", "startPosition": "2"},
        {"coin": "BTC", "time": ms(NOW - 3 * D), "px": "110000", "sz": "3", "side": "A", "startPosition": "3"},
        {"coin": "BTC", "time": ms(NOW - 2 * D), "px": "110000", "sz": "0.001", "side": "B", "startPosition": "0"},  # dust
        {"coin": "@107", "time": ms(NOW - 2 * D), "px": "1", "sz": "5000", "side": "B", "startPosition": "0"},       # spot
        {"coin": "ETH", "time": ms(NOW - 40 * D), "px": "4000", "sz": "10", "side": "A", "startPosition": "0"},      # too old
    ]
    rows = ent.changes_from_fills(fills, NOW - 30 * D, NOW)
    assert [(r[2], r[3], r[4]) for r in rows] == [("BTC", 0.0, 3.0), ("BTC", 3.0, 0.0)]
    assert rows[0][0] == NOW - 10 * D and rows[0][1] == NOW - 10 * D + 120 and rows[0][5] == 100100.0
    assert ent.changes_from_fills(fills, NOW - 30 * D, NOW - 5 * D) == rows[:1]       # only before the log starts


def test_seed_runs_once_and_fills_the_log_before_it_starts(monkeypatch):
    import hl_persistence as hp
    import trader_entries as te
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(hp, "_DB_PATH", os.path.join(d, "hl.db"))
        monkeypatch.setattr(hp, "_conn", None)
        now = time.time()
        fills = [{"coin": "BTC", "time": int((now - 5 * D) * 1000), "px": "100000", "sz": "1", "side": "B", "startPosition": "0"}]
        post = mock.AsyncMock(return_value=fills)
        monkeypatch.setattr(te, "_post", post)
        monkeypatch.setattr(hl, "_roster", [TrackedWallet("0xaaa1"), TrackedWallet("0xaaa2")])
        assert asyncio.run(hl.seed_changes_from_fills()) == 2
        assert post.call_count == 2 and post.call_args.args[1]["type"] == "userFills"
        post.reset_mock()                                               # the log has rows now: never again
        assert asyncio.run(hl.seed_changes_from_fills()) == 0 and post.call_count == 0
        hp._conn.close()
