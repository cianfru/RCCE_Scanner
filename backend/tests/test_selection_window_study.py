"""The selection window study's code, on made-up wallets (docs/reviews/selection-window-study.md)."""
from backtest import selection_window_study as s

DAY = s.DAY
START = s.T0 - 450 * DAY
END = s.T0 + 31 * DAY


def _days():
    return range(int((END - START) // DAY) + 1)


def _wallet(addr, av_fn, pnl_fn, pav_fn=None):
    pts = [START + d * DAY for d in _days()]
    pav_fn = pav_fn or av_fn
    return s.Wallet(addr, {"av": [[t * 1000, av_fn(t)] for t in pts], "pnl": [[t * 1000, pnl_fn(t)] for t in pts],
                           "pav": [[t * 1000, pav_fn(t)] for t in pts]})


def _steady(i, per_day=1_500.0):
    rate = per_day + 10 * i
    return _wallet(f"0xs{i:02d}", lambda t: 200_000.0, lambda t: rate * (t - START) / DAY)


def _lucky(i):
    """+$100K and -$100K in turn, in the 30-day blocks the study's dates start; $200K account."""
    def offset(t):
        m, frac = divmod((t - s.T0) / (30 * DAY), 1)
        good = (int(m) + i) % 2 == 0
        return 100_000.0 * (frac if good else 1 - frac)
    return _wallet(f"0xl{i:02d}", lambda t: 200_000.0 + offset(t), lambda t: 500_000.0 + offset(t))


def test_series_interpolates_and_reports_the_span():
    w = s.Series([[1_000_000, 10], [1_000_000 + 4 * DAY * 1000, 50]])
    assert w.at(999) == 0.0                                   # before the first point: no account yet
    assert w.at(1000 + 2 * DAY) == 30.0
    assert w.at(1000 + 9 * DAY) == 50.0                       # after the last: the last
    assert w.span(1000 + DAY) == 4 * DAY and w.span(1000) == 0.0


def test_roi_counts_deposits_in_the_base_but_not_withdrawals():
    t0, t1 = START, START + 30 * DAY
    dep = _wallet("0xd", lambda t: 100_000.0 if t < t0 + DAY else 200_000.0, lambda t: 0.0 if t <= t0 else 20_000.0)
    pnl, roi = s.window(dep, t0, t1)
    assert pnl == 20_000.0 and abs(roi - 20_000 / 180_000) < 1e-9      # 80K deposited on top of 100K
    wd = _wallet("0xw", lambda t: 100_000.0 if t <= t0 else 50_000.0, lambda t: 0.0 if t <= t0 else 10_000.0)
    assert abs(s.window(wd, t0, t1)[1] - 0.10) < 1e-9                  # a withdrawal leaves the base
    tiny = _wallet("0xt", lambda t: 500.0, lambda t: 0.0 if t <= t0 else 5_000.0)
    assert s.window(tiny, t0, t1)[1] is None                            # nearly empty start: no ROI


def test_ranked_applies_the_list_rules():
    t = s.T0
    good = _steady(1)
    small = _wallet("0xsmall", lambda x: 9_000.0, lambda x: 2_000.0 * (x - START) / DAY)
    no_perp = _wallet("0xnoperp", lambda x: 200_000.0, lambda x: 1_500.0 * (x - START) / DAY, lambda x: 1_000.0)
    lost_before = _wallet("0xlost", lambda x: 200_000.0,
                          lambda x: -700_000.0 + 1_500.0 * (x - START) / DAY)   # all-time (-$25K) under the window's $45K
    r = s.ranked([good, small, no_perp, lost_before], t, 30)
    assert [a for _, a in r] == ["0xs01"]


def test_bar_needs_size_breadth_and_interval():
    assert s.bar([5.0] * 12)["met"]
    nine = s.bar([5.0] * 9 + [-1.0] * 3)
    assert nine["dates_positive"] == 9 and not nine["met"]
    assert not s.bar([2.0] * 12)["met"]                                  # under 3 points on average


def test_a_longer_window_that_drops_lucky_months_meets_the_bar():
    ws = [_steady(i) for i in range(6)] + [_lucky(i) for i in range(6)]
    res = s.analyse(ws, 0.01)                                            # k = 4
    assert res["k"] == 4
    for p in res["primary"]:
        assert p[30]["hit"] == 25.0 and p[60]["hit"] == 100.0 and p[90]["hit"] == 100.0
    assert res["verdict"][60]["met"] and res["verdict"][90]["met"]
    assert res["signal"] and res["chosen_window"] in (60, 90)
    assert res["baseline"][0]["hit"] == 75.0


def test_no_difference_is_context_not_a_signal():
    ws = [_steady(i, 1_000.0 + 100 * i) for i in range(12)]
    res = s.analyse(ws, 0.01)
    assert not res["signal"] and res["chosen_window"] == 30
    assert all(v["mean_pp"] == 0.0 for v in res["verdict"].values())


def test_sample_is_a_fixed_hash():
    a = "0x" + "ab" * 20
    assert s.in_sample(a, 1.0) and not s.in_sample(a, 0.0)
    assert s.in_sample(a, 0.3) == (s.skey(a) < 3000)
    assert len(s.dates()) == 12 and s.dates()[0] == s.T0 and s.dates()[-1] == s.T0 - 330 * DAY
