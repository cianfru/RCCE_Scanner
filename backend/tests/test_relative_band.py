import numpy as np

import band_stretch
import relative_band as rb
from backtest import relative_band_study as st


def days_from(n, start=20000):
    return np.arange(start, start + n, dtype=np.int64)


def test_edges_match_band_mid():
    rng = np.random.default_rng(1)
    d = days_from(400)
    x = np.exp(np.cumsum(rng.normal(0, 0.02, 400)))
    sma, ema = band_stretch.band_edges(d, x)
    mid = band_stretch.band_mid(d, x)
    ok = np.isfinite(mid)
    assert ok.sum() > 200 and np.allclose((sma + ema)[ok] / 2, mid[ok])


def test_align_and_ratio():
    d1, d2 = days_from(10), days_from(10, 20003)
    days, r = rb.align(d1, np.full(10, 4.0), d2, np.full(10, 2.0))
    assert days[0] == 20003 and days[-1] == 20009 and np.allclose(r, 2.0)
    assert len(rb.align(d1, np.ones(10), days_from(5, 30000), np.ones(5))[0]) == 0


def test_crosses_need_a_gap():
    s = np.array([np.nan] * 3 + [0.0] * 20 + [1.0] * 3 + [0.0] * 5 + [1.0] + [-1.0] * 20 + [0.0] * 14 + [-1.0])
    cx = rb.crosses(s)
    assert cx["up"] == [23]                 # the second close above came 6 days after the first: not a new cross
    assert cx["down"] == [32, 66]          # the last under came after 14 days not under: a new cross
    s2 = np.array([0.0] * 20 + [-1.0] * 3 + [0.0] * 14 + [-1.0])
    assert rb.crosses(s2)["down"] == [20, 37]


def test_summary_and_history():
    d = days_from(500)
    r = np.concatenate([np.linspace(1, 0.5, 300), np.linspace(0.5, 1.2, 200)])   # falls against BTC, then rises
    s = rb.summary(d, r)
    assert s["state"] == "above" and s["trend"] == "up" and s["since"] > d[300]
    assert s["spark"]["r"][-1] == 1.0 and len(s["spark"]["r"]) == rb.SPARK_DAYS // rb.SPARK_STEP
    assert s["chg30"] > 0
    h = rb.history(d, r, 365)
    assert len(h["days"]) == 365 and h["up"] and all(x >= h["days"][0] for x in h["up"])
    assert rb.summary(d[:50], r[:50]) is None


def test_study_events_and_verdict():
    d = days_from(900)
    r = np.concatenate([np.linspace(1, 0.5, 400), np.linspace(0.5, 2.0, 500)])
    ev = st.events(d, r, "up")
    assert ev and all(e[60] > 0 for e in ev)          # the ratio kept rising faster than its era mean
    by = {f"C{k}": [{"day": 19000 + k, 30: 0.1, 60: 0.1, 90: 0.1}, {"day": 19500 + k, 30: 0.1, 60: 0.1, 90: 0.1},
                    {"day": 19600 + k, 30: 0.1, 60: 0.1, 90: 0.1}] for k in range(22)}
    v = st.verdict(by)
    assert v["verdict"] == "met" and v["events"] == 66
    by["C0"] = [{"day": 19000, 30: -1, 60: -1, 90: -1}]
    assert st.verdict({"C0": by["C0"]})["verdict"] == "too few"
    flat = {c: [{**e, 60: -0.01} for e in es] for c, es in by.items()}
    assert st.verdict(flat)["verdict"] == "not met"
