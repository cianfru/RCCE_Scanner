"""Shorts covered by spot (or staked HYPE) are counted by net exposure (hl_hedges)."""
import asyncio
import time
from collections import deque
from unittest import mock

import pytest

import hl_hedges as hh
import hl_intelligence as hl
from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition


def pos(coin, side, size, px):
    return WalletPosition(coin=coin, side=side, size=size, size_usd=size * px, entry_px=px, unrealized_pnl=0.0, leverage=3)


@pytest.fixture
def clean(monkeypatch):
    monkeypatch.setattr(hh, "_held", {})
    monkeypatch.setattr(hh, "_read_at", {})
    monkeypatch.setattr(hh, "_loaded", True)
    monkeypatch.setattr(hh, "_save", lambda: None)
    yield


def test_spot_tokens_map_to_perp_coins_and_staked_hype_counts():
    held = hh.parse({"balances": [{"coin": "UBTC", "total": "2.5"}, {"coin": "HYPE", "total": "100"},
                                  {"coin": "USDC", "total": "1e6"}, {"coin": "UBONK", "total": "5000000"},
                                  {"coin": "UFART", "total": "10"}, {"coin": "UNI", "total": "4"}]},
                    {"delegated": "900", "undelegated": "0", "totalPendingWithdrawal": "50"})
    assert held["BTC"] == 2.5 and held["HYPE"] == 1050 and "USDC" not in held
    assert held["KBONK"] == 5000 and held["BONK"] == 5_000_000        # k market: per 1,000 tokens
    assert held["FARTCOIN"] == 10 and held["UNI"] == 4               # UNI is its own token


def test_covered_shorts_are_left_out_or_cut_and_longs_untouched(clean):
    hh._held["0xa"] = {"HYPE": 95.0, "BTC": 1.0}
    ps = [pos("HYPE", "SHORT", 100, 50.0), pos("BTC", "SHORT", 4, 100.0), pos("ETH", "SHORT", 2, 10.0),
          pos("BTC", "LONG", 1, 100.0)]
    out = hh.counted("0xa", ps, hl._normalize_coin)
    assert [(p.coin, p.side, round(p.size, 3)) for p in out] == [("BTC", "SHORT", 3.0), ("ETH", "SHORT", 2), ("BTC", "LONG", 1)]
    assert out[0].size_usd == 300.0                                   # three quarters left uncovered
    assert hh.counted("0xb", ps, hl._normalize_coin) is ps            # nothing held: as is


def test_consensus_counts_a_spot_hedged_short_as_neutral(clean, monkeypatch):
    ws = [TrackedWallet(a, account_value=1e6) for a in ("0xa", "0xb", "0xc")]
    now = time.time()
    snaps = {"0xa": deque([PositionSnapshot(now, [pos("HYPE", "SHORT", 1000, 40.0)], 1e6)]),     # carry trade
             "0xb": deque([PositionSnapshot(now, [pos("HYPE", "SHORT", 500, 40.0)], 1e6)]),      # a real short
             "0xc": deque([PositionSnapshot(now, [pos("HYPE", "LONG", 200, 40.0)], 1e6)])}
    for k, v in {"_roster": ws, "_roster_money_printers": ws, "_roster_smart_money": [], "_snapshots": snaps,
                 "_wallet_cohorts": {a.address: {"money_printer"} for a in ws}, "_entity_of": {}, "_entity_members": {},
                 "_consensus": {}, "_mp_book": {}}.items():
        monkeypatch.setattr(hl, k, v)
    hl._recompute_consensus()
    assert (hl._consensus["HYPE"].long_count, hl._consensus["HYPE"].short_count) == (1, 2)
    hh._held["0xa"] = {"HYPE": 1000.0}                                  # fully covered by staked HYPE
    hl._recompute_consensus()
    h = hl._consensus["HYPE"]
    assert (h.long_count, h.short_count) == (1, 1) and h.short_notional == 500 * 40.0
    lean = hl.profitable_lean(lambda c: (c,))
    assert (lean["HYPE"]["long"], lean["HYPE"]["short"]) == (1, 1)
    pm = hl.positioning_map("profitable")["coins"]["HYPE"]
    assert (pm["long"]["n"], pm["short"]["n"]) == (1, 1)


def test_refresh_reads_due_wallets_once_an_hour_and_hype_stakes_only_when_short_hype(clean):
    calls = []

    class Resp:
        status = 200
        def __init__(self, body): self.body = body
        async def json(self, content_type=None): return self.body
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class Session:
        def post(self, url, json):
            calls.append((json["type"], json["user"]))
            if json["type"] == "spotClearinghouseState":
                return Resp({"balances": [{"coin": "HYPE", "total": "10"}]} if json["user"] == "0xa" else {"balances": []})
            return Resp({"delegated": "90"})

    async def acquire(kind):
        return 0.0

    shorts = {"0xa": {"HYPE"}, "0xb": {"BTC"}}
    assert asyncio.run(hh.refresh(Session(), shorts, acquire, now=1000.0)) == 2
    assert calls == [("spotClearinghouseState", "0xa"), ("delegatorSummary", "0xa"), ("spotClearinghouseState", "0xb")]
    assert hh._held == {"0xa": {"HYPE": 100.0}}
    assert asyncio.run(hh.refresh(Session(), shorts, acquire, now=1000.0 + 600)) == 0      # not due yet
    assert asyncio.run(hh.refresh(Session(), {"0xb": {"BTC"}}, acquire, now=1000.0 + 3700)) == 1
    assert "0xa" not in hh._read_at and "0xa" not in hh._held          # no longer short: forgotten


def test_holdings_survive_a_restart(tmp_path, monkeypatch):
    import hl_persistence as hp
    with mock.patch.object(hp, "_DB_PATH", str(tmp_path / "hl.db")), mock.patch.object(hp, "_conn", None):
        now = time.time()
        hp.save_hedges({"0xa": (now, {"HYPE": 12.5})}, {"0xb": now})
        monkeypatch.setattr(hh, "_held", {})
        monkeypatch.setattr(hh, "_read_at", {})
        monkeypatch.setattr(hh, "_loaded", False)
        hh._load()
        assert hh._held == {"0xa": {"HYPE": 12.5}} and set(hh._read_at) == {"0xa", "0xb"}
        assert hp.mark_counting_change(now, "hedges") is True and hp.mark_counting_change(now + 5, "hedges") is False
        assert [r[4] for r in hp.load_roster_rebuilds(0)] == ["hedges"]
