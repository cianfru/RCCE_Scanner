import sqlite3

from convergence import Tracker, find_convergence


def pos(coin, side, px, usd=10_000):
    return {"coin": coin, "side": side, "entry_px": px, "size_usd": usd, "mark_px": px}


def test_first_reading_is_baseline_and_new_positions_are_opens():
    t = Tracker(clock=lambda: 2000)
    assert t.observe("a", "profitable", 100, [pos("SUI", "long", 3.0)]) == []
    assert t.observe("a", "profitable", 100, [pos("ETH", "long", 1.0)]) == []          # same reading: ignored
    opens = t.observe("a", "profitable", 1900, [pos("SUI", "long", 3.0), pos("ETH", "short", 2500)])
    assert [(o["coin"], o["side"], o["prev_ts"]) for o in opens] == [("ETH", "short", 100)]


def test_two_profitable_traders_converge_once_and_again_when_a_third_joins():
    now = [10_000.0]
    t = Tracker(conn=sqlite3.connect(":memory:"), clock=lambda: now[0])
    for a in ("a", "b", "c", "w"):
        t.observe(a, "large" if a == "w" else "profitable", 9000, [])
    new = t.observe("a", "profitable", 9500, [pos("SUI", "long", 3.00)])
    new += t.observe("w", "large", 9500, [pos("SUI", "long", 3.00)])                  # whales never count
    assert t.check(new) == []
    new = t.observe("b", "profitable", 9900, [pos("SUI", "long", 3.10)])
    [c] = t.check(new)
    assert (c["coin"], c["side"], c["n"], c["first_px"], c["last_px"]) == ("SUI", "long", 2, 3.00, 3.10)
    assert t.check(t.observe("a", "profitable", 9950, [pos("SUI", "long", 3.00)])) == []  # no repeat
    now[0] = 10_100
    [c] = t.check(t.observe("c", "profitable", 10_050, [pos("SUI", "long", 3.05)]))
    assert c["n"] == 3
    assert len(t.convergences_since(0, "SUI")) == 2 and len(t.opens_for("SUI", 0)) == 4


def test_price_already_moved_or_crowded_is_not_a_convergence():
    o = lambda a, ts, px: {"ts": ts, "prev_ts": ts - 1800, "address": a, "coin": "X", "side": "long", "entry_px": px, "size_usd": 1}
    key = ("X", "long")
    hold = {"a": {key}, "b": {key}}
    assert find_convergence([o("a", 100, 1.0), o("b", 200, 1.06)], hold, key, 300) is None          # moved 6%
    crowded = {**hold, "c": {key}, "d": {key}, "e": {key}}
    assert find_convergence([o("a", 100, 1.0), o("b", 200, 1.01)], crowded, key, 300) is None       # 3 already on it
    assert find_convergence([o("a", 100, 1.0), o("b", 200, 1.01)], {"a": {key}}, key, 300) is None  # b left
    assert find_convergence([o("a", 100, 1.0), o("b", 200, 1.01)], hold, key, 100 + 25 * 3600) is None  # too old
    assert find_convergence([o("a", 100, 1.0), o("b", 200, 1.01)], hold, key, 300)["n"] == 2
