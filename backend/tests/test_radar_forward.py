"""The Radar forward test (docs/reviews/radar-forward-test.md): entry zone, logging, events, outcomes, verdicts."""
import sqlite3

import pytest

import radar_log
import setup_map as sm
from research import radar_forward as rf

DAY = 86400
D0 = 20360 * DAY          # a 00:00 UTC close


# ------------------------------------------------------------------ entry zone
def test_entry_zone_needs_three_traders_and_three_percent():
    assert sm.entry(3, 100.0, 103.0)["in_zone"] is True            # +3% exactly: inside (inclusive)
    assert sm.entry(3, 100.0, 97.0)["in_zone"] is True             # -3% exactly
    assert sm.entry(3, 100.0, 103.01)["in_zone"] is False
    assert sm.entry(3, 100.0, 96.99)["in_zone"] is False
    assert sm.entry(2, 100.0, 100.0)["in_zone"] is False            # fewer than 3 traders: never in the zone
    e = sm.entry(5, 2.0, 2.1)
    assert e == {"avg_long_entry": 2.0, "dist_pct": 5.0, "in_zone": False}
    assert sm.entry(0, None, 1.0) is None and sm.entry(3, 1.0, None) is None and sm.entry(0, 1.0, 1.0) is None


def test_avg_long_entry_is_dollar_weighted_and_counts_a_lockstep_group_once(monkeypatch):
    import time
    from collections import deque
    import hl_intelligence as hl
    from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition

    def pos(side, size, entry):
        return WalletPosition(coin="SUI", side=side, size=size, size_usd=abs(size) * entry, entry_px=entry,
                              unrealized_pnl=0.0, leverage=3.0)
    ws = [TrackedWallet(a) for a in ("0xa1", "0xa2", "0xb", "0xc", "0xd")]
    now = time.time()
    snaps = {
        "0xa1": deque([PositionSnapshot(now, [pos("LONG", 100, 1.0)], 1e6)]),        # group A: one trader
        "0xa2": deque([PositionSnapshot(now, [pos("LONG", 100, 1.2)], 1e6)]),
        "0xb": deque([PositionSnapshot(now, [pos("LONG", 200, 1.1)], 1e6)]),
        "0xc": deque([PositionSnapshot(now, [pos("SHORT", 50, 1.3)], 1e6)]),          # short: not in the long average
        "0xd": deque([PositionSnapshot(now, [pos("LONG", 1000, 0.5)], 1e6)]),         # not a profitable trader
    }
    monkeypatch.setattr(hl, "_roster", ws)
    monkeypatch.setattr(hl, "_roster_money_printers", ws[:4])
    monkeypatch.setattr(hl, "_roster_smart_money", ws[4:])
    monkeypatch.setattr(hl, "_snapshots", snaps)
    monkeypatch.setattr(hl, "_entity_of", {"0xa1": "grp-a", "0xa2": "grp-a"})
    row = hl.positioning_map("profitable")["coins"]["SUI"]
    assert row["long"]["n"] == 2                                     # the group once, plus 0xb
    want = (100 * 1.0 + 100 * 1.2 * 1.2 + 200 * 1.1 * 1.1) / (100 + 120 + 220)
    assert row["long"]["avg_entry"] == pytest.approx(want)
    assert row["short"]["avg_entry"] == pytest.approx(1.3)
    # Two traders long: not in the zone even at the average.
    assert sm.entry(row["long"]["n"], row["long"]["avg_entry"], want)["in_zone"] is False


def test_map_carries_the_entry_zone():
    prof = {"FET": {"long": {"n": 3, "usd": 3000, "avg_entry": 1.0}, "short": {"n": 0, "usd": 0}}}
    row = {"symbol": "FET/USDT", "timeframe": "1d", "price": 1.02, "regime": "MARKUP", "signal": "LIGHT_LONG",
           "zscore": 0.5, "heat": 10, "market_kind": "perpetual"}
    c = sm.build([row], "1d", None, prof, {}, [], {}, D0)["coins"][0]
    assert c["entry"] == {"avg_long_entry": 1.0, "dist_pct": 2.0, "in_zone": True}
    assert sm.ladder(c, [], None, D0)["entry"] == c["entry"]


# ------------------------------------------------------------------ logging
def smap(coins):
    return {"coins": coins}


def coin(name, z=0.5, pl=3, ps=0, stage="running", zone="watch", in_zone=False):
    return {"coin": name, "symbol": f"{name}/USDT", "zscore": z, "stage": stage, "zone": zone, "crowd": "early",
            "price": 1.0, "traders": {"pl": pl, "ps": ps}, "money": {"gross_usd": 1234},
            "band": {"state": "above", "fill": 0.6}, "entry": {"avg_long_entry": 1.0, "dist_pct": 0.0, "in_zone": in_zone}}


def candles_for(day):
    import numpy as np
    return {"timestamp": np.array([(day - 2 * DAY) * 1000, (day - DAY) * 1000], dtype=float), "close": np.array([1.0, 2.0])}


def test_logging_takes_one_reading_per_coin_per_close():
    c = sqlite3.connect(":memory:")
    radar_log.ensure(c)
    m = smap([coin("SUI"), coin("FET", pl=0, stage="waiting"), dict(coin("NOZ"), zscore=None)])
    before = lambda s, now: {"SUI": {"long": 1, "short": 0}}
    candles = lambda sym: candles_for(D0)
    assert radar_log.take(c, D0 + 10 * 60, lambda: m, before, candles, 2) == 0            # too soon after the close
    assert radar_log.take(c, D0 + 40 * 60, lambda: m, before, candles, 2) == 2            # ready: every candle is in
    assert radar_log.take(c, D0 + 50 * 60, lambda: m, before, candles, 2) == 0            # once per close
    assert radar_log.write(c, radar_log.readings(m, D0, {}, lambda s: 9.0, 2, D0 + 3600)) == 0   # INSERT OR IGNORE
    rows = {r["coin"]: r for r in radar_log.load(c)}
    assert set(rows) == {"SUI", "FET"}                                                    # no z-score: not on the map
    sui = rows["SUI"]
    assert sui["close"] == 2.0 and sui["net_24h"] == 2 and sui["shown"] == 1 and sui["roster_version"] == 2
    assert sui["schema_version"] == radar_log.SCHEMA_VERSION and sui["band_fill"] == 0.6 and sui["in_zone"] == 0
    assert rows["FET"]["shown"] == 0 and rows["FET"]["net_24h"] is None
    # Late: 7 hours after the close the day is missing.
    assert radar_log.take(c, D0 + DAY + 7 * 3600, lambda: m, before, candles, 2) == 0


def test_logging_waits_for_the_candles_then_reads_at_two_hours():
    c = sqlite3.connect(":memory:")
    radar_log.ensure(c)
    m = smap([coin("SUI")])
    old = lambda sym: candles_for(D0 - DAY)                     # the store still ends the day before
    assert radar_log.take(c, D0 + 40 * 60, lambda: m, lambda s, n: {}, old, 2) == 0
    assert radar_log.take(c, D0 + 2 * 3600 + 60, lambda: m, lambda s, n: {}, old, 2) == 1
    assert radar_log.load(c)[0]["close"] is None


# ------------------------------------------------------------------ events
def reading(coinname, day, **kw):
    r = {"coin": coinname, "day": day, "zone": "watch", "stage": "running", "crowd": "early", "long": 3, "short": 0,
         "net_24h": 1, "gross_usd": 1.0, "band_state": "above", "band_fill": 0.5, "z": 0.5, "price": 1.0, "close": 1.0,
         "avg_long_entry": 1.0, "entry_dist": 0.0, "in_zone": 0, "shown": 1, "roster_version": 2, "schema_version": 1}
    r.update(kw)
    return r


def test_h1_thresholds():
    assert rf.h1(reading("A", D0))
    assert not rf.h1(reading("A", D0, long=2))
    assert not rf.h1(reading("A", D0, net_24h=0)) and not rf.h1(reading("A", D0, net_24h=None))
    assert not rf.h1(reading("A", D0, band_fill=0.49))
    assert not rf.h1(reading("A", D0, band_state="closed_under", band_fill=1.0))
    assert rf.h1(reading("A", D0, band_state="inside", band_fill=1.0))
    assert not rf.h1(reading("A", D0, band_state=None, band_fill=None))
    assert not rf.h1(reading("A", D0, zone="crowded"))
    assert rf.h3(reading("A", D0, z=2.0, crowd="crowded")) and not rf.h3(reading("A", D0, z=1.99, crowd="crowded"))


def test_first_day_rule_and_fourteen_day_spacing():
    on = lambda d: reading("A", D0 + d * DAY)
    off = lambda d: reading("A", D0 + d * DAY, zone="outside")
    rows = [on(0), on(1), off(2), on(3), off(4), on(5)] + [off(d) for d in range(6, 16)] + [on(16), on(17)]
    ev = rf.first_day_events(rows, rf.h1)
    # Day 0 is the baseline; day 3 is the first day; day 5 is inside 14 days; day 16 is 13 days after day 3: skipped.
    assert ev == [("A", D0 + 3 * DAY)]
    rows2 = rows + [off(18)] + [on(19)]
    assert rf.first_day_events(rows2, rf.h1) == [("A", D0 + 3 * DAY), ("A", D0 + 19 * DAY)]
    # A gap of more than 3 days: no previous reading, so the day only sets a baseline.
    gap = [off(0), on(5)]
    assert rf.first_day_events(gap, rf.h1) == []
    assert rf.first_day_events([off(0), on(3)], rf.h1) == [("A", D0 + 3 * DAY)]


def test_spaced_events_for_h2_groups():
    rows = [reading("A", D0 + d * DAY, in_zone=1) for d in range(0, 30)]
    assert rf.spaced_events(rows, rf.h2_zone) == [("A", D0), ("A", D0 + 14 * DAY), ("A", D0 + 28 * DAY)]
    assert rf.spaced_events(rows, rf.h2_comparison) == []
    assert rf.h2_comparison(reading("A", D0, long=3, in_zone=0)) and not rf.h2_comparison(reading("A", D0, long=2))


def test_readings_under_another_roster_do_not_count():
    rows = [reading("A", D0), reading("B", D0, roster_version=None), reading("C", D0, schema_version=2)]
    assert [r["coin"] for r in rf.counted(rows)] == ["A"]


# ------------------------------------------------------------------ outcomes
def test_excess_is_return_minus_the_median_coin():
    rows = []
    for k in range(21):                                   # 21 coins: returns 0%, 1%, ..., 20% -> median 10%
        rows.append(reading(f"C{k}", D0, close=100.0))
        rows.append(reading(f"C{k}", D0 + 14 * DAY, close=100.0 + k))
    cl = rf.Closes(rows)
    assert cl.bench(D0, 14) == pytest.approx(0.10)
    assert cl.excess("C20", D0, 14) == pytest.approx(0.10)
    assert cl.excess("C0", D0, 14) == pytest.approx(-0.10)
    # A missing close at D + 14 comes from the stored candles.
    rows2 = [r for r in rows if not (r["coin"] == "C20" and r["day"] > D0)]
    assert rf.Closes(rows2).ret("C20", D0, 14) is None
    assert rf.Closes(rows2, {"C20": {D0 + 14 * DAY: 130.0}}).ret("C20", D0, 14) == pytest.approx(0.30)
    # Fewer than 20 coins: no median coin.
    assert rf.Closes(rows[:38]).bench(D0, 14) is None


def test_outcomes_split_scored_pending_and_unscored():
    rows = [reading(f"C{k}", d, close=100.0 + k) for k in range(20) for d in (D0, D0 + 14 * DAY)]
    cl = rf.Closes(rows)
    out = rf.outcomes([("C1", D0), ("C1", D0 + 10 * DAY), ("ZZ", D0)], cl, D0 + 20 * DAY, 14)
    assert len(out["scored"]) == 1 and out["pending"] == 1 and out["unscored"] == 1


# ------------------------------------------------------------------ verdicts and bootstrap
def test_verdict_rules_at_the_boundaries():
    v = rf.verdict
    assert v(29, 20, 0.05, (0.01, 0.09), 0.7) == "too few"
    assert v(30, 14, 0.05, (0.01, 0.09), 0.7) == "too few"
    assert v(30, 15, 0.0, (0.01, 0.09), 0.7) == "fails"                  # median 0 fails
    assert v(30, 15, -0.01, None, 0.2) == "fails"
    assert v(30, 15, 0.05, (0.01, 0.09), 0.56) == "holds"
    assert v(30, 15, 0.05, (0.01, 0.09), 0.55) == "undecided"            # more than 55% is needed
    assert v(30, 15, 0.05, (0.0, 0.09), 0.7) == "undecided"              # interval must exclude 0
    assert v(30, 15, 0.05, (-0.01, 0.09), 0.7) == "undecided"
    assert v(30, 15, 0.05, (0.01, 0.09), 0.7, enough_other=False) == "too few"


def test_bootstrap_is_deterministic_with_the_seed():
    ev = [(f"C{k % 17}", D0 + (k % 40) * DAY, ((k * 37) % 101) / 1000 - 0.05) for k in range(60)]
    a = rf.bootstrap([ev], rf.med)
    b = rf.bootstrap([ev], rf.med)
    assert a == b and a[0] < a[1]
    import random
    draw = lambda seed: rf.block_days(D0, D0 + 39 * DAY, random.Random(seed))
    assert draw(rf.BOOT_SEED) == draw(rf.BOOT_SEED) and draw(rf.BOOT_SEED) != draw(1)
    assert a[0] <= rf.med(ev) <= a[1]
    days = rf.block_days(D0, D0 + 9 * DAY, __import__("random").Random(3), block=4)
    assert len(days) == 10 and all(D0 <= d <= D0 + 9 * DAY for d in days)


def test_report_says_too_few_until_the_minimum():
    rows = [reading(f"C{k}", D0 + d * DAY, zone="outside" if d == 0 else "watch", close=100.0 + d)
            for k in range(25) for d in range(0, 20)]
    rep = rf.report(rows, today=D0 + 19 * DAY)
    h1 = rep["hypotheses"]["H1"]
    assert h1["events"] == 25 and h1["scored"] == 25 and h1["verdict"] == "too few"
    assert rep["days_logged"] == 20 and rep["next_report_day"] == 30
    assert rep["hypotheses"]["H2"]["verdict"] == "too few" and rep["hypotheses"]["H3"]["verdict"] == "description only"
    st = rf.status(rep)
    assert st["H1"]["scored"] == 25 and st["min_events"] == 30


def market(move):
    """60 coins over 40 days: coins 0-29 turn into early setups (outside the box the day before) on days
    1-10 and move by ``move`` from their 14th day on; coins 30-59 stay outside and flat."""
    rows = []
    for k in range(60):
        start = D0 + (1 + k % 10) * DAY if k < 30 else None
        for d in range(40):
            day = D0 + d * DAY
            in_box = start is not None and start <= day < start + 5 * DAY
            moved = start is not None and day >= start + 14 * DAY
            rows.append(reading(f"C{k}", day, zone="watch" if in_box else "outside", close=100.0 * (1 + move if moved else 1)))
    return rows


def test_report_holds_when_events_beat_the_median_coin():
    rep = rf.report(market(0.05), today=D0 + 39 * DAY)
    h1 = rep["hypotheses"]["H1"]
    assert h1["scored"] == 30 and h1["coins"] == 30
    assert h1["median_excess_14d"] > 0 and h1["interval_90"][0] > 0 and h1["share_beating_median_coin"] == 1.0
    assert h1["verdict"] == "holds"


def test_report_fails_when_events_trail_the_median_coin():
    h1 = rf.report(market(-0.05), today=D0 + 39 * DAY)["hypotheses"]["H1"]
    assert h1["scored"] == 30 and h1["median_excess_14d"] < 0 and h1["verdict"] == "fails"


# ------------------------------------------------------------------ endpoint
def test_forward_test_endpoint_shape(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    c = sqlite3.connect(":memory:", check_same_thread=False)
    radar_log.ensure(c)
    radar_log.write(c, [tuple(reading("SUI", D0)[k] if k in reading("SUI", D0) else (D0 if k == "taken_at" else None)
                              for k in radar_log.COLUMNS)])
    monkeypatch.setattr(radar_log, "conn", lambda: c)
    main._RADAR_FT_CACHE.clear()
    body = TestClient(main.app).get("/api/radar/forward-test").json()
    assert set(body) == {"declared", "doc", "days_logged", "first_close", "last_close", "days_since_first",
                         "next_report_day", "min_events", "min_coins", "H1", "H2", "H3"}
    assert body["days_logged"] == 1 and body["H1"]["verdict"] == "too few" and body["min_events"] == 30
    assert set(body["H1"]) == {"events", "scored", "pending", "coins", "median_excess_14d", "interval_90",
                               "share_beating_median_coin", "verdict"}
    main._RADAR_FT_CACHE.clear()
