import time
from collections import deque

import hl_intelligence as hl
from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition


def pos(coin, side, size, entry, mark):
    return WalletPosition(coin=coin, side=side, size=size, size_usd=abs(size) * mark, entry_px=entry,
                          unrealized_pnl=0.0, leverage=3.0)


def test_positioning_map_counts_sides_entries_and_profit(monkeypatch):
    a, b, c = TrackedWallet("0xa"), TrackedWallet("0xb"), TrackedWallet("0xc")
    now = time.time()
    snaps = {
        "0xa": deque([PositionSnapshot(now, [pos("SUI", "LONG", 100, 3.0, 3.3), pos("kPEPE", "SHORT", 1e6, 0.01, 0.012)], 1e6)]),
        "0xb": deque([PositionSnapshot(now, [pos("SUI", "LONG", 50, 3.5, 3.3)], 1e6)]),
        "0xc": deque([PositionSnapshot(now, [pos("SUI", "SHORT", 10, 3.1, 3.3)], 1e6)]),   # large account
    }
    monkeypatch.setattr(hl, "_roster", [a, b, c])
    monkeypatch.setattr(hl, "_roster_money_printers", [a, b])
    monkeypatch.setattr(hl, "_roster_smart_money", [c])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    pm = hl.positioning_map("profitable")
    assert pm["wallets"] == 2
    sui = pm["coins"]["SUI"]
    assert sui["long"] == {"n": 2, "usd": 495, "median_entry": 3.25, "in_profit": 1}
    assert sui["short"]["n"] == 0 and abs(sui["mark"] - 3.3) < 1e-9
    assert pm["coins"]["PEPE"]["short"]["in_profit"] == 0          # kPEPE normalised; short above entry
    assert hl.positioning_map("large")["coins"]["SUI"]["short"]["n"] == 1
