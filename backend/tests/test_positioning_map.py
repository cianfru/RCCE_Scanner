import time
from collections import deque

import hl_intelligence as hl
from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition


def pos(coin, side, size, entry, mark):
    # As parsed from Hyperliquid: size_usd is valued at entry; the mark shows only in unrealised PnL.
    pnl = (mark - entry) * size * (1 if side == "LONG" else -1)
    return WalletPosition(coin=coin, side=side, size=size, size_usd=abs(size) * entry, entry_px=entry,
                          unrealized_pnl=pnl, leverage=3.0)


def test_positioning_map_counts_sides_entries_and_profit(monkeypatch):
    a, b, c, d = TrackedWallet("0xa"), TrackedWallet("0xb"), TrackedWallet("0xc"), TrackedWallet("0xd")
    now = time.time()
    snaps = {
        "0xa": deque([PositionSnapshot(now, [pos("SUI", "LONG", 100, 3.0, 3.3), pos("kPEPE", "SHORT", 1e6, 0.01, 0.012)], 1e6)]),
        "0xb": deque([PositionSnapshot(now, [pos("SUI", "LONG", 50, 3.5, 3.3)], 1e6)]),
        "0xc": deque([PositionSnapshot(now, [pos("SUI", "SHORT", 10, 3.1, 3.3)], 1e6)]),   # large account
        "0xd": deque([PositionSnapshot(now, [], 1e6)]),                                    # flat
    }
    monkeypatch.setattr(hl, "_roster", [a, b, c, d])
    monkeypatch.setattr(hl, "_roster_money_printers", [a, b, d])
    monkeypatch.setattr(hl, "_roster_smart_money", [c])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    pm = hl.positioning_map("profitable")
    assert pm["wallets"] == 3 and pm["holding"] == 2
    sui = pm["coins"]["SUI"]
    assert sui["long"] == {"n": 2, "usd": 475, "wallets": 2, "median_entry": 3.25, "in_profit": 1}
    assert sui["short"]["n"] == 0 and abs(sui["mark"] - 3.3) < 1e-9
    assert pm["coins"]["PEPE"]["short"]["in_profit"] == 0          # kPEPE normalised; short above entry
    assert hl.positioning_map("large")["coins"]["SUI"]["short"]["n"] == 1


def test_restored_readings_count_as_current_for_a_while(monkeypatch):
    now = time.time()
    monkeypatch.setattr(hl, "_restored_until", now + 60)
    assert hl._fresh_limit(now) == hl._RESTORED_MAX_AGE_S
    monkeypatch.setattr(hl, "_restored_until", now - 1)
    assert hl._fresh_limit(now) == hl._SNAPSHOT_MAX_AGE_S


def test_cohort_positions_match_the_positioning_map(monkeypatch):
    a, b, c = TrackedWallet("0xa"), TrackedWallet("0xb"), TrackedWallet("0xc")
    now = time.time()
    snaps = {
        "0xa": deque([PositionSnapshot(now, [pos("SUI", "LONG", 100, 3.0, 3.3), pos("BTC", "LONG", 1, 60000, 61000)], 1e6)]),
        "0xb": deque([PositionSnapshot(now, [pos("SUI", "SHORT", 50, 3.5, 3.3)], 1e6)]),
        "0xc": deque([PositionSnapshot(now, [pos("SUI", "LONG", 1000, 3.0, 3.3)], 1e6)]),   # large account only
    }
    monkeypatch.setattr(hl, "_roster", [a, b, c])
    monkeypatch.setattr(hl, "_roster_money_printers", [a, b])
    monkeypatch.setattr(hl, "_roster_smart_money", [c])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    rows = hl.cohort_positions("SUI", "profitable")
    assert [r["address"] for r in rows] == ["0xa", "0xb"]                  # largest first
    assert rows[0] == {"address": "0xa", "side": "long", "size_usd": 300, "entry": 3.0, "leverage": 3.0,
                       "upnl": 30, "roe": None, "move": 10.0, "entity": None}
    assert rows[1]["side"] == "short" and rows[1]["move"] == round(100 * 10 / 175, 2)
    sui = hl.positioning_map("profitable")["coins"]["SUI"]
    assert sui["long"]["usd"] == sum(r["size_usd"] for r in rows if r["side"] == "long")
    assert sui["short"]["n"] == sum(r["side"] == "short" for r in rows)


def test_positioning_endpoint_adds_the_count_a_day_ago(monkeypatch):
    from fastapi.testclient import TestClient
    import hl_persistence
    import main
    a, b = TrackedWallet("0x" + "a" * 40), TrackedWallet("0x" + "b" * 40)
    now = time.time()
    snaps = {a.address: deque([PositionSnapshot(now, [pos("SUI", "LONG", 100, 3.0, 3.3)], 1e6)]),
             b.address: deque([PositionSnapshot(now, [pos("SUI", "LONG", 50, 3.5, 3.3)], 1e6)])}
    monkeypatch.setattr(hl, "_roster", [a, b])
    monkeypatch.setattr(hl, "_roster_money_printers", [a, b])
    monkeypatch.setattr(hl, "_roster_smart_money", [b])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    monkeypatch.setattr(hl_persistence, "load_trader_lean",
                        lambda prefix, since: [(int(now - 86400), "coin:SUI", 1, 2, 300, 600)])
    main._POSITIONING_CACHE.clear()
    c = TestClient(main.app)
    sui = next(r for r in c.get("/api/hyperlens/positioning?cohort=profitable").json()["rows"] if r["coin"] == "SUI")
    assert sui["long"]["n"] == 2 and sui["day_ago"] == {"long": 1, "short": 2}
    large = c.get("/api/hyperlens/positioning?cohort=large").json()["rows"]
    assert large[0]["day_ago"] is None                                       # the record is profitable traders only
    main._POSITIONING_CACHE.clear()
