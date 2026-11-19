import math

import numpy as np

from backtest import ranking_study as rk

DAY = rk.DAY_MS
BAR = rk.BAR_MS


def series(n_days, f, symbol, signal=lambda t: "WAIT", start=0):
    """4H rows for one symbol: price f(bar index)."""
    return [{"timestamp": float(start + k * BAR), "symbol": symbol, "price": f(k), "signal": signal(k),
             "conditions_met": 5, "conditions_total": 9, "deviation_pct": 10.0, "heat": 20} for k in range(n_days * 6)]


def test_priority_matches_the_scanner_on_the_recorded_fields():
    import scanner
    r = {"signal": "LIGHT_LONG", "conditions_met": 7, "conditions_total": 9, "deviation_pct": 12.5, "heat": 30}
    full = dict(r, momentum=-10, rel_vol=0.0, floor_confirmed=False, cvd_trend="NEUTRAL", positioning={})
    assert abs(rk.priority_recorded(r) - scanner._compute_priority(full)) < 0.11      # the scanner rounds to 0.1


def test_market_is_the_median_coin_and_scores_follow_it():
    n = 200
    g = [0.001, 0.002, 0.003]                         # three coins drifting up at different rates per bar
    rows = []
    for j, rate in enumerate(g):
        rows += series(n, lambda k, rate=rate: 10 * math.exp(rate * k), f"C{j}")
    px, times, mkt, by_t = rk.prepare(rows)
    assert abs(mkt[times[-1]] - 0.002 * (len(times) - 1)) < 1e-9            # median coin
    i = len(times) - 1
    rs = rk.score("RS14", by_t[times[i]][2], px["C2"], mkt, times, i)
    assert abs(rs - 0.001 * 14 * 6) < 1e-9                                   # beats the median coin by 0.001 a bar


def test_residual_strength_removes_beta_times_the_market():
    n = 160
    rng = np.random.default_rng(3)
    m = np.cumsum(rng.normal(0, 0.01, n * 6))
    rows = []
    rows += series(n, lambda k: 10 * math.exp(m[k]), "A")
    rows += series(n, lambda k: 10 * math.exp(m[k]), "B")
    rows += series(n, lambda k: 5 * math.exp(2 * m[k]), "HI")                 # beta 2 to the market
    px, times, mkt, by_t = rk.prepare(rows)
    i = len(times) - 1
    b = rk.beta(px["HI"], mkt, times, i)
    assert abs(b - 2) < 1e-6
    assert abs(rk.score("RR14", {}, px["HI"], mkt, times, i)) < 1e-6        # nothing left once beta is removed
    assert rk.score("RR14", {}, px["HI"], mkt, times, 10) is None          # too little history for beta


def test_crowded_days_and_the_spread():
    rows = []
    for j in range(8):
        sig = (lambda k: "LIGHT_LONG") if j < 3 else (lambda k: "WAIT")
        rows += series(40, lambda k, j=j: 1 + j + 0.001 * k, f"C{j}", sig)
    px, times, mkt, by_t = rk.prepare(rows)
    days = rk.crowded_days(by_t, times, 0, 40 * DAY)
    assert days and all(t % DAY == 0 for _, t, _ in days) and len(days[0][2]) == 3
    rk.CROWDED_SHARE, old = 0.5, rk.CROWDED_SHARE
    try:
        assert rk.crowded_days(by_t, times, 0, 40 * DAY) == []               # 3 of 8 is under half
    finally:
        rk.CROWDED_SHARE = old
    longs = [{"symbol": s} for s in ("A", "B", "C", "D", "E", "F")]
    sc = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "F": 1}
    fwd = {"A": 10, "B": 8, "C": 0, "D": 0, "E": -2, "F": -4}
    assert rk.day_spread(longs, sc, fwd) == (9 - (-3))                       # top two minus bottom two
    assert rk.day_spread(longs[:2], sc, fwd) is None


def test_forward_return_and_verdict_rules():
    p = {0: 100.0, 10 * DAY: 110.0}
    assert abs(rk.forward(p, 0, 10) - 10) < 1e-9 and rk.forward(p, 0, 20) is None
    good = {"10": {"median": 3.0, "median_halves": [1.0, 2.0]}, "20": {"median": 1.0}}
    base = {"10": {"median": 0.5, "median_halves": [0, 0]}, "20": {"median": 0}}
    one = {"P": base, **{s: good for s in rk.SCORES[1:]}}
    v = rk.verdict({"a": one, "b": one, "c": one})
    assert all(x["passes"] for x in v.values())
    weak_half = dict(good, **{"10": {"median": 3.0, "median_halves": [-0.1, 4.0]}})
    v = rk.verdict({"a": one, "b": dict(one, RS14=weak_half), "c": one})
    assert not v["RS14"]["passes"] and v["RR14"]["passes"]
