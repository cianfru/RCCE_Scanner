from trader_entries import position_bursts


def f(t, d, px, sz, start, side="B", twap=False, coin="2Z"):
    return {"coin": coin, "time": t * 1000, "dir": d, "px": str(px), "sz": str(sz), "startPosition": str(start),
            "side": side, "twap": twap}


def test_current_position_starts_after_last_flat():
    fills = [
        f(0, "Open Long", 1.0, 10, 0), f(60, "Close Long", 1.2, 10, 10, side="A"),   # earlier round trip
        f(7200, "Open Long", 2.0, 5, 0), f(7260, "Open Long", 2.2, 5, 5),            # current, one burst
        f(20000, "Open Long", 3.0, 10, 10, twap=True),                               # timed-order add
        f(20000, "Open Long", 9.0, 1, 0, coin="BTC"),                                # other coin ignored
    ]
    r = position_bursts(fills, "2Z", now_s=20100)
    assert r["opened_at"] == 7200
    assert [(b["kind"], b["twap"], b["fills"]) for b in r["bursts"]] == [("open", False, 2), ("open", True, 1)]
    assert abs(r["bursts"][0]["px"] - 2.1) < 1e-9 and r["bursts"][0]["usd"] == 21
    assert r["buying_now"] is True


def test_flip_starts_a_new_position_and_unknown_start():
    fills = [f(0, "Open Long", 1.0, 10, 0), f(100, "Long > Short", 1.5, 15, 10, side="A")]
    r = position_bursts(fills, "2Z", now_s=10_000)
    assert r["opened_at"] == 100 and r["bursts"][0]["side"] == "short" and not r["buying_now"]
    # Only adds in the window: the position was opened before it.
    r = position_bursts([f(0, "Open Long", 1.0, 5, 5)], "2Z", now_s=10)
    assert r["opened_at"] is None and len(r["bursts"]) == 1
