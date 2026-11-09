"""research/band_marks.py: the script's marks on daily candles, the outcomes, the chance and the bars."""
import math

import numpy as np

from research import band_marks as M
from research.stretch_tops import band_mid


def _walk(n=2600, seed=11):
    """A walk with fast legs both ways, so the states and most marks occur."""
    rng = np.random.default_rng(seed)
    drift = np.zeros(n)
    i = 0
    while i < n:
        k = int(rng.integers(30, 160))
        drift[i: i + k] = rng.choice([0.012, -0.012, 0.0005, -0.0005, 0.02, -0.02])
        i += k
    r = drift + rng.normal(0, 0.035, n)
    close = 100 * np.exp(np.cumsum(r))
    high = close * np.exp(np.abs(rng.normal(0, 0.02, n)))
    low = close * np.exp(-np.abs(rng.normal(0, 0.02, n)))
    return np.arange(17000, 17000 + n), high, low, close


def _reference(days, high, low, close, p=M.PARAMS):
    """The script's rules written out plainly, bar by bar, without running sums or shared helpers."""
    n = len(close)
    mid = band_mid(days, close)
    s = np.log(close / mid)
    loc = np.full(n, np.nan)
    hist = []
    for i in range(n):
        if not np.isfinite(s[i]):
            continue
        hist.append(s[i])
        w = np.array(hist[-p["norm_days"]:])
        up, dn = w[w > 0], w[w < 0]
        r_all = math.sqrt(np.mean(w * w))
        r_up = math.sqrt(np.mean(up * up)) if len(up) >= p["min_side"] else r_all
        r_dn = math.sqrt(np.mean(dn * dn)) if len(dn) >= p["min_side"] else r_all
        if len(hist) >= p["min_loc_days"]:
            loc[i] = s[i] / r_up if s[i] >= 0 else s[i] / r_dn
    r1 = np.concatenate([[np.nan], np.diff(np.log(close))])
    speed = np.full(n, np.nan)
    for i in range(p["vol_days"], n):
        sd = r1[i - p["vol_days"] + 1: i + 1].std()
        speed[i] = math.log(close[i] / close[i - p["speed_days"]]) / (sd * math.sqrt(p["speed_days"]))

    def f(x):
        return bool(np.isfinite(x))
    rising = [i >= p["slope_days"] and f(mid[i]) and f(mid[i - p["slope_days"]]) and mid[i] > mid[i - p["slope_days"]]
              for i in range(n)]
    in_zone = [f(loc[i]) and p["zone_lo"] <= loc[i] <= p["zone_hi"] for i in range(n)]
    hot = [f(loc[i]) and f(speed[i]) and loc[i] >= p["stretch_line"] and speed[i] >= p["speed_line"] for i in range(n)]
    cold = [f(loc[i]) and f(speed[i]) and loc[i] <= -p["stretch_line"] and speed[i] <= -p["speed_line"]
            for i in range(n)]

    def since(m, i):
        for j in range(i, -1, -1):
            if m[j]:
                return i - j
        return None

    def ext(i, fn):
        w = [loc[j] for j in range(max(0, i - p["turn_days"] + 1), i + 1) if f(loc[j])]
        return fn(w) if w else float("nan")
    exh, bas, lost, top, bot, rec, cross = ([False] * n for _ in range(7))
    for i in range(n):
        sh, sc = since(hot, i), since(cold, i)
        exh[i] = not hot[i] and sh is not None and sh <= p["turn_days"] and loc[i] <= ext(i, max) - p["turn_drop"]
        bas[i] = not cold[i] and sc is not None and sc <= p["turn_days"] and loc[i] >= ext(i, min) + p["turn_drop"]
        lost[i] = f(mid[i]) and close[i] < mid[i] and not rising[i]
        if i >= 364 and f(loc[i]):
            back = range(i - 364, i - 29)
            if any(hot[j] for j in back) and close[i] >= max(close[i - 364: i + 1]) and 0 < loc[i] < p["stretch_line"]:
                top[i] = True
            if any(cold[j] for j in back) and close[i] <= min(close[i - 364: i + 1]) and -p["stretch_line"] < loc[i] < 0:
                bot[i] = True
        rec[i] = i > 0 and sc is not None and sc <= p["reclaim_days"] and f(mid[i]) and close[i] > mid[i] \
            and f(mid[i - 1]) and close[i - 1] <= mid[i - 1]
        cross[i] = i > 0 and f(loc[i]) and f(loc[i - 1]) and loc[i] > p["leg_level"] and loc[i - 1] <= p["leg_level"]
    out = {k: [False] * n for k in ("buy", "exh", "leg", "cap_turn", "reclaim", "top_div", "bot_div", "lost")}
    cand = {"exh": [exh[i] and not (i and exh[i - 1]) for i in range(n)],
            "cap_turn": [bas[i] and not (i and bas[i - 1]) for i in range(n)],
            "lost": [lost[i] and not (i and lost[i - 1]) for i in range(n)],
            "top_div": top, "bot_div": bot, "reclaim": rec}
    tops_before = lambda i: [j for j in range(i) if top[j]]
    cand["leg"] = [cross[i] and bool(tops_before(i)) and i - tops_before(i)[-1] <= p["leg_days"] for i in range(n)]
    for k, c in cand.items():
        prev = [j for j in range(n) if c[j]]
        for i in prev:
            earlier = [j for j in prev if j < i]
            out[k][i] = not earlier or i - earlier[-1] > p["gap_days"]
    armed = True
    for i in range(n):
        out["buy"][i] = in_zone[i] and rising[i] and i > 0 and close[i] > high[i - 1] and armed
        if out["buy"][i]:
            armed = False
        if not in_zone[i]:
            armed = True
    return {k: np.array(v) for k, v in out.items()}, loc, speed


def test_the_model_is_the_scripts_rules():
    days, high, low, close = _walk()
    got = M.model(days, high, low, close)
    ref, loc, speed = _reference(days, high, low, close)
    assert np.allclose(got["loc"], loc, equal_nan=True, rtol=1e-9)
    assert np.allclose(got["speed"], speed, equal_nan=True, rtol=1e-9)
    for k, v in ref.items():
        assert (got[k] == v).all(), k
    assert (got["take_profit"] == (ref["exh"] | ref["leg"])).all()
    fired = {k for k, v in ref.items() if v.any()}
    assert {"buy", "exh", "cap_turn", "reclaim", "lost"} <= fired, fired


def test_reclaim_fires_only_on_the_first_close_back_above_the_band_after_capitulating():
    days, high, low, close = _walk(seed=5)
    o = M.model(days, high, low, close)
    for i in np.flatnonzero(o["reclaim"]):
        assert close[i] > o["mid"][i] and close[i - 1] <= o["mid"][i - 1]
        assert o["cold"][max(0, i - M.PARAMS["reclaim_days"]): i + 1].any()


def test_outcome_both_ways():
    close = np.array([100.0] * 31 + [80.0] * 30 + [90.0] * 30 + [120.0] * 40)
    t = 30                                       # the close 90 days later is close[120] = 120
    up = M.outcome(close, t, +1)
    assert up["right"] and math.isclose(up["r"], 0.2) and math.isclose(up["adverse"], -0.2)
    assert math.isclose(up["r_short"], -0.2)     # close[60] = 80
    down = M.outcome(close, t, -1)
    assert not down["right"] and math.isclose(down["adverse"], -0.2)   # the highest close after: 80
    assert math.isclose(up["timing"], 20 / 40)   # between 80 and 120 over the 30 days before and 90 after


def test_chance_weights_each_coin_by_its_marks():
    days = {"A": {"to 2021": np.array([0.1, 0.1, -0.1, -0.1]), "from 2022": np.array([])},
            "B": {"to 2021": np.array([0.1, 0.1, 0.1, -0.1]), "from 2022": np.array([])}}
    rows = [{"coin": "A", "era": "to 2021", "right": True, "r": 0.3, "r_short": 0, "adverse": 0, "timing": 0}] * 3 + \
           [{"coin": "B", "era": "to 2021", "right": False, "r": -0.2, "r_short": 0, "adverse": 0, "timing": 0}]
    out = M.summarize(rows, days, +1)
    assert math.isclose(out["chance"], (3 * 0.5 + 1 * 0.75) / 4)
    assert math.isclose(out["right"], 0.75) and math.isclose(out["margin"], 0.75 - out["chance"])
    sell = M.summarize(rows, days, -1)
    assert math.isclose(sell["chance"], (3 * 0.5 + 1 * 0.25) / 4)


def test_weighted_median():
    assert M._wmedian(np.array([1.0, 2.0, 3.0]), np.array([1.0, 1.0, 5.0])) == 3.0
    assert M._wmedian(np.array([3.0, 1.0, 2.0]), np.array([1.0, 1.0, 1.0])) == 2.0


def test_the_bars():
    ok = {"marks": 40, "margin": 0.12, "median": 0.05, "chance_median": 0.0}
    parts = {k: {"marks": 6, "margin": 0.01} for k in ("calibration", "test", "to 2021", "from 2022")}
    assert M.verdict(ok, parts, +1)["met"]
    assert not M.verdict({**ok, "marks": 29}, parts, +1)["met"]
    assert not M.verdict({**ok, "margin": 0.0999}, parts, +1)["met"]
    assert not M.verdict(ok, parts, -1)["met"]                       # a sell mark needs a median below chance's
    assert not M.verdict(ok, {**parts, "from 2022": {"marks": 4, "margin": 0.5}}, +1)["met"]
    assert not M.verdict(ok, {**parts, "test": {"marks": 9, "margin": -0.01}}, +1)["met"]


def test_the_parts_leave_out_the_seen_coins():
    pt = M.parts()
    every = pt["calibration"] + pt["test"]
    assert not set(every) & set(M.SEEN) and "SOL" not in every and len(every) == 37   # FTT left out at the data
