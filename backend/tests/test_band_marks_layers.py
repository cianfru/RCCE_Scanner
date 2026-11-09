"""research/band_marks_layers.py: the layers' readings at a mark, the split and the bar."""
import json
import math

import numpy as np

from research import band_marks_layers as L

DAY = 86_400_000


def test_funding_is_per_8_hours_and_time_weighted():
    rows = L.parse_funding("calc_time,funding_interval_hours,last_funding_rate\n1000,8,0.0003\n2000,4,0.0001\n")
    assert rows == [(1000, 0.0003, 8.0), (2000, 0.0002, 4.0)]
    old = L.parse_funding("calc_time,funding_rate\n1000,0.0005\n")      # older archives: 8-hourly
    assert old == [(1000, 0.0005, 8.0)]
    day = 100
    end = (day + 1) * DAY
    fund = np.array([[end - h * 3_600_000, 0.0001, 8.0] for h in range(0, 168, 8)])        # 21 payments, 168 hours
    assert math.isclose(L.funding_at(fund, day), 0.0001)
    fund[:, 1] = np.where(np.arange(len(fund)) < 3, 0.0004, 0.0001)
    assert math.isclose(L.funding_at(fund, day), (3 * 0.0004 + 18 * 0.0001) / 21)
    assert L.funding_at(fund[:14], day) is None                         # 112 hours: under 120
    assert L.funding_at(np.zeros((0, 3)), day) is None
    late = np.array([[end + 1, 0.01, 8.0]] + fund.tolist())             # after the close: not counted
    assert math.isclose(L.funding_at(late, day), L.funding_at(fund, day))


def test_metrics_take_each_columns_last_value_of_the_day():
    text = ("create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
            "sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
            "2022-01-01 00:00:00,X,10,1,\"\",\"\",\"\",\"\"\n"
            "2022-01-01 23:50:00,X,12,1,1.5,1.2,2.0,0.9\n"
            "2022-01-01 23:55:00,X,13,1,\"\",\"\",\"\",\"\"\n")
    assert L.parse_metrics(text) == [13.0, 1.2, 2.0]


def test_the_split_cuts_at_the_median_ties_high_and_skips_missing():
    rows = [{"i": i} for i in range(6)]
    vals = [{"x": v} for v in (1.0, 2.0, 2.0, 3.0, None, 4.0)]
    hi, lo, cut = L.split(rows, vals, "x", "median")
    assert cut == 2.0 and [r["i"] for r in hi] == [1, 2, 3, 5] and [r["i"] for r in lo] == [0]
    hi, lo, cut = L.split(rows, [{"x": v} for v in (1.0, 0.0, 1.0, None, 0.0, 1.0)], "x", "binary")
    assert [r["i"] for r in hi] == [0, 2, 5] and [r["i"] for r in lo] == [1, 4]


def _rows(n, coin, era, right):
    return [{"coin": coin, "era": era, "right": right, "r": 0.1 if right else -0.1, "r_short": 0.0, "adverse": 0.0,
             "timing": 0.5} for _ in range(n)]


def test_the_bar():
    days = {c: {"to 2021": np.array([0.1, -0.1]), "from 2022": np.array([0.1, -0.1])} for c in ("A", "B")}
    pt = {"calibration": ["A"], "test": ["B"]}
    good, bad = [], []
    for coin in ("A", "B"):
        for era in ("to 2021", "from 2022"):
            good += _rows(8, coin, era, True) + _rows(2, coin, era, False)      # 80% right
            bad += _rows(4, coin, era, True) + _rows(6, coin, era, False)       # 40% right
    rows = good + bad
    vals = [{"x": 1.0}] * len(good) + [{"x": 0.0}] * len(bad)
    r = L.judge(rows, vals, "x", "median", True, days, +1, pt)
    assert r["judged"] and r["high"]["bar"]["met"] and not r["low"]["bar"]["met"]
    assert math.isclose(r["high"]["margin"] - r["with_value"]["margin"], 0.2)
    assert not L.judge(rows, vals, "x", "median", False, days, +1, pt)["high"]["bar"]["met"]   # report only
    # a part where the high group is not ahead fails it
    flip = [dict(x, right=not x["right"]) if x["coin"] == "B" and x["era"] == "from 2022" else x for x in rows]
    assert not L.judge(flip, vals, "x", "median", True, days, +1, pt)["high"]["bar"]["met"]
    # too little coverage: not judged
    few = [{"x": 1.0}] * len(good) + [{"x": None}] * len(bad)
    assert not L.judge(rows, few, "x", "median", True, days, +1, pt)["judged"]


def test_the_seed_layers_read_reflexs_market_history():
    s = L.seed_layers()
    mh = json.loads((L.SEEDS / "market_history_seed.json").read_text())
    row = next(d for d in mh["days"] if d[1] >= L.MIN_SEED_COINS)
    assert math.isclose(s["breadth"][row[0]], row[2] + row[3])
    assert min(s["breadth"]) == row[0]
    assert all(0 <= v <= 1 for k in ("breadth", "market_stretch", "traders_long", "smart_long", "whales_long")
               for v in s[k].values())
