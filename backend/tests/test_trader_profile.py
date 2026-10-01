import time
from collections import deque

import pytest

import hl_intelligence as hl
import trader_profile as tp
from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition

A = "0x" + "a" * 40
B = "0x" + "b" * 40
C = "0x" + "c" * 40


def fill(t, side, px, sz, start=None, coin="ETH", pnl=0.0, fee=0.0, d=None, twap=False):
    f = {"coin": coin, "time": int(t * 1000), "side": side, "px": str(px), "sz": str(sz),
         "dir": d or ("Open Long" if side == "B" else "Close Long"), "closedPnl": str(pnl), "fee": str(fee), "twap": twap}
    if start is not None:
        f["startPosition"] = str(start)
    return f


# open 10 @100, add 5 @110, trim 5 @120, close 10 @130; open 4 @125, flip to short 6 @120, close @110
SEQ = [
    fill(0, "B", 100, 10, 0, fee=1),
    fill(60, "B", 110, 5, 10, fee=1),
    fill(120, "A", 120, 5, 15, pnl=83.33, fee=1),
    fill(180, "A", 130, 10, 10, pnl=266.67, fee=1),
    fill(240, "B", 125, 4, 0, fee=1),
    fill(300, "A", 120, 10, 4, pnl=-20, fee=2.5, d="Long > Short"),
    fill(360, "B", 110, 6, -6, pnl=60, fee=1, d="Close Short"),
]


def test_fill_classification_open_add_trim_close_flip():
    cl = tp.classify_fills(SEQ)
    assert [f["kind"] for f in cl] == ["open", "add", "trim", "close", "open", "flip", "close"]
    assert [f["side"] for f in cl] == ["long", "long", "long", "long", "long", "short", "short"]
    assert [f["after"] for f in cl] == [10, 15, 10, 0, 4, -6, 0]
    assert cl[0]["avg_entry"] == 100
    assert cl[1]["avg_entry"] == pytest.approx((100 * 10 + 110 * 5) / 15)
    assert cl[2]["avg_entry"] == pytest.approx((100 * 10 + 110 * 5) / 15)     # a trim keeps the average
    assert cl[3]["avg_entry"] is None and cl[5]["avg_entry"] == 120            # flat, then the flip's price
    assert cl[2]["pnl"] == pytest.approx(82.33)                                # closed PnL net of the fee


def test_classification_without_start_position_uses_the_running_size():
    seq = [{k: v for k, v in f.items() if k != "startPosition"} for f in SEQ]
    assert [f["kind"] for f in tp.classify_fills(seq)] == ["open", "add", "trim", "close", "open", "flip", "close"]


def test_same_millisecond_fills_chain_and_spot_twap_and_builder_fills_are_left_out():
    seq = [
        fill(0, "B", 1, 5, 0), fill(10, "A", 1, 2, 2), fill(10, "A", 1, 3, 5),   # listed out of chain order
        fill(10, "A", 1, 3, 5, twap=True),                                        # same slice again
        fill(5, "B", 1, 1, 0, coin="@107", d="Buy"), fill(5, "B", 1, 1, 0, coin="xyz:TSLA"),
    ]
    cl = tp.classify_fills(seq)
    assert [(f["kind"], f["after"]) for f in cl] == [("open", 5), ("trim", 2), ("close", 0)]


def test_round_trips_and_win_rate():
    now = 400
    trips = tp.round_trips(tp.classify_fills(SEQ))
    closed = trips["closed"]
    assert [(t["side"], t["opened_at"], t["closed_at"]) for t in closed] == [
        ("short", 300, 360), ("long", 240, 300), ("long", 0, 180)]
    first = closed[-1]
    assert first["entry_px"] == pytest.approx((100 * 10 + 110 * 5) / 15)
    assert first["exit_px"] == pytest.approx((120 * 5 + 130 * 10) / 15)
    assert first["pnl"] == pytest.approx(83.33 + 266.67 - 4)
    assert first["adds"] == 1 and first["trims"] == 1 and first["fills"] == 4 and first["peak_size"] == 15
    flipped = closed[1]
    assert flipped["pnl"] == pytest.approx(-20 - 1 - 1)          # its open fee, and 4/10 of the flip's fee
    assert closed[0]["pnl"] == pytest.approx(60 - 1 - 1.5)       # 6/10 of the flip's fee, the close's fee
    assert trips["open"] == {}
    st = tp.win_stats(closed, now)
    assert st["all"] == {"wins": 2, "n": 3, "rate": 66.7}


def test_a_position_opened_before_the_fills_on_hand_is_partial_and_not_counted():
    seq = [fill(0, "A", 10, 5, 8, pnl=5), fill(60, "A", 11, 3, 3, pnl=6), fill(120, "B", 9, 2, 0)]
    trips = tp.round_trips(tp.classify_fills(seq))
    assert trips["closed"][0]["partial"] and trips["closed"][0]["entry_px"] is None
    assert trips["open"]["ETH"]["opened_at"] == 120
    assert tp.win_stats(trips["closed"], 200)["all"]["n"] == 0


def test_win_stats_windows():
    now = 100 * 86400
    closed = [{"partial": False, "closed_at": now - 2 * 86400, "pnl": 5},
              {"partial": False, "closed_at": now - 20 * 86400, "pnl": -5},
              {"partial": False, "closed_at": now - 90 * 86400, "pnl": 5}]
    st = tp.win_stats(closed, now)
    assert st["7d"] == {"wins": 1, "n": 1, "rate": 100.0}
    assert st["30d"] == {"wins": 1, "n": 2, "rate": 50.0}
    assert st["all"]["n"] == 3


def _wallet(addr, pnl, week, all_time, av=1e6):
    return TrackedWallet(addr, account_value=av, pnl=pnl, roi=pnl / 1e4, all_time_pnl=all_time,
                         week_pnl=week, week_roi=None if week is None else week / 1e4, all_time_roi=all_time / 1e5)


def _pos(coin, side, usd):
    return WalletPosition(coin=coin, side=side, size=usd / 10, size_usd=usd, entry_px=10, unrealized_pnl=0, leverage=3)


@pytest.fixture
def board(monkeypatch):
    small = "0x" + "d" * 40
    ws = [_wallet(A, 100, 50, 900), _wallet(B, 300, None, 400), _wallet(C, 200, 80, 100), _wallet(small, 999, 999, 999, av=4e3)]
    now = time.time()
    snaps = {A: deque([PositionSnapshot(now, [_pos(c, "LONG", 1000 * (i + 1)) for i, c in enumerate(["BTC", "ETH", "SOL", "DOGE", "AVAX", "LINK"])]
                                        + [_pos("xyz:TSLA", "LONG", 1e6)], 1e6)]),
             B: deque([PositionSnapshot(now, [_pos("kPEPE", "SHORT", 500)], 1e6)])}
    monkeypatch.setattr(hl, "_roster", ws)
    monkeypatch.setattr(hl, "_roster_money_printers", ws)
    monkeypatch.setattr(hl, "_roster_smart_money", [ws[0]])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    monkeypatch.setattr(tp, "_board_cache", {})
    monkeypatch.setattr(tp, "_stats", {C: (now, {"7d": None, "30d": {"wins": 3, "n": 4, "rate": 75.0}, "all": None})})
    warmed = []
    monkeypatch.setattr(tp, "_schedule_warm", lambda addrs: warmed.append(list(addrs)))
    return warmed


def test_leaderboard_ranks_by_the_window_pnl(board):
    by = lambda w: [r["address"] for r in tp.leaderboard(w)["rows"]]
    assert by("30d") == [B, C, A]                   # the $4K account is below the display floor
    assert by("7d") == [C, A, B]                    # no 7-day figure sorts last
    assert by("all") == [A, B, C]
    rows = tp.leaderboard("30d")["rows"]
    assert [r["rank"] for r in rows] == [1, 2, 3]
    a = next(r for r in rows if r["address"] == A)
    assert a["positions"] == 6 and a["coins"] == ["LINK", "AVAX", "DOGE", "SOL", "ETH"] and a["more_coins"] == 1
    assert a["band"] == "$1M–10M" and a["roi"] == pytest.approx(0.01)
    assert next(r for r in rows if r["address"] == B)["coins"] == ["KPEPE"]   # kPEPE under the scanner's key
    assert next(r for r in rows if r["address"] == C)["win_rate"] == 75.0
    assert a["win_rate"] is None and set(board[-1]) == {A, B}          # the missing win rates get computed
    page = tp.leaderboard("30d", offset=1, limit=1)
    assert page["total"] == 3 and [r["address"] for r in page["rows"]] == [C]


def test_size_band():
    assert [tp.size_band(v) for v in (None, 60e3, 300e3, 2e6, 20e6)] == [None, "$50K–250K", "$250K–1M", "$1M–10M", "$10M+"]


@pytest.fixture
def client(board, monkeypatch):
    from fastapi.testclient import TestClient
    import hyperliquid_data
    import main

    async def state(address):
        if address != A:
            return None
        return {"marginSummary": {"accountValue": "1000"}, "assetPositions": [{"position": {
            "coin": "ETH", "szi": "6", "entryPx": "120", "positionValue": "780", "unrealizedPnl": "60",
            "leverage": {"type": "cross", "value": 5}, "liquidationPx": "60", "marginUsed": "156", "returnOnEquity": "0.38"}}]}

    async def port(address):
        if address != A:
            return tp.parse_portfolio([])
        hist = [[1_000_000, "0.0"], [2_000_000, "900"]]
        return tp.parse_portfolio([[k, {"accountValueHistory": [[1_000_000, "100"], [2_000_000, "1000"]], "pnlHistory": hist}]
                                   for k in ("week", "month", "allTime")])

    async def fills(address):
        return {"fills": SEQ[:5] + [fill(400, "B", 130, 2, 4)], "covered_from": None} if address == A else {"fills": [], "covered_from": None}

    monkeypatch.setattr(hyperliquid_data, "fetch_clearinghouse_state", state)
    monkeypatch.setattr(tp, "portfolio", port)
    monkeypatch.setattr(tp, "wallet_fills", fills)
    monkeypatch.setattr(tp, "_profile_cache", {})
    return TestClient(main.app)


def test_leaderboard_endpoint(client):
    r = client.get("/api/traders/leaderboard?window=7d")
    assert r.status_code == 200
    body = r.json()
    assert body["window"] == "7d" and body["total"] == 3 and body["rows"][0]["address"] == C
    assert set(body["rows"][0]) >= {"rank", "address", "pnl", "roi", "win_rate", "positions", "coins", "more_coins", "band", "account_value"}
    assert client.get("/api/traders/leaderboard?window=90d").status_code == 422
    assert client.get("/api/traders/leaderboard?cohort=whales").status_code == 422


def test_profile_endpoint(client):
    body = client.get(f"/api/traders/{A.upper().replace('X', 'x')}").json()
    assert body["address"] == A and body["tracked"] and body["ranks"]["30d"] == 3
    assert body["windows"]["30d"] == {"pnl": 100, "roi": 0.01, "source": "leaderboard"}
    assert body["account_value"] == 1000 and len(body["equity"]["7d"]) == 2
    p = body["positions"][0]
    assert p["coin"] == "ETH" and p["side"] == "long" and p["mark_px"] == pytest.approx(130)
    assert p["opened_at"] == 240 and p["adds"] == 1 and p["liq_distance_pct"] is not None
    assert body["win"]["all"] == {"wins": 1, "n": 1, "rate": 100.0}


def test_profile_errors(client):
    assert client.get("/api/traders/0x123").status_code == 422
    assert client.get("/api/traders/0x" + "g" * 40).status_code == 422
    assert client.get("/api/traders/0x" + "e" * 40).status_code == 404      # nothing on Hyperliquid
    assert client.get(f"/api/traders/0x123/fills").status_code == 422
    assert client.get(f"/api/traders/{A}/fills?coin=ET;H").status_code == 422


def test_fills_and_history_endpoints(client):
    body = client.get(f"/api/traders/{A}/fills?coin=ETH&since=100").json()
    assert body["coin"] == "ETH" and body["count"] == 4
    assert [f["kind"] for f in body["fills"]] == ["add", "open", "close", "trim"]      # most recent first
    assert set(body["fills"][0]) >= {"t", "kind", "side", "px", "sz", "usd", "avg_entry", "pnl"}
    assert client.get(f"/api/traders/{A}/fills?coin=BTC").json()["count"] == 0
    h = client.get(f"/api/traders/{A}/history?limit=1").json()
    assert h["total"] == 1 and h["trips"][0]["closed_at"] == 180 and h["trips"][0]["coin"] == "ETH"
    assert h["coins"] == [{"coin": "ETH", "n": 1}] and h["earliest_fill"] == 0
