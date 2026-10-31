"""The selection window study's code, on made-up wallets (docs/reviews/selection-window-study.md)."""
import json

from backtest import selection_window_study as s

DAY = s.DAY
START = s.T0 - 450 * DAY
END = s.T0 + 31 * DAY
BIG_LB = {"av": 200_000.0, "month_vlm": 1e6, "all_vlm": 2e7}


def _pts(fn, times):
    return [[t * 1000, fn(t)] for t in times]


def _reply(times, av, pnl, pav=None, ppnl=None, all_vlm=2e7, month_vlm=1e6):
    return [["month", {"vlm": str(month_vlm)}],
            ["allTime", {"accountValueHistory": _pts(av, times), "pnlHistory": _pts(pnl, times), "vlm": str(all_vlm)}],
            ["perpAllTime", {"accountValueHistory": _pts(pav or av, times), "pnlHistory": _pts(ppnl or pnl, times)}]]


def _daily():
    return [START + d * DAY for d in range(int((END - START) // DAY) + 1)]


def _wallet(addr, av, pnl, pav=None, ppnl=None, lb=None, times=None):
    return s.Wallet(addr, _reply(times or _daily(), av, pnl, pav, ppnl), lb or BIG_LB)


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


ALTERNATE = [k % 2 == 0 for k in range(s.N_DATES)]


# --- series and measures --------------------------------------------------------------------

def test_values_are_the_last_point_at_or_before():
    w = s.Series([[1_000_000, 10], [1_000_000 + 4 * DAY * 1000, 50]])
    assert w.asof(999) == 0.0 and w.asof(1000) == 10.0
    assert w.asof(1000 + 2 * DAY) == 10.0                    # never interpolated
    assert w.asof(1000 + 4 * DAY) == 50.0 and w.asof(1000 + 9 * DAY) == 50.0
    assert w.times(1000, 1000 + 4 * DAY) == [1000 + 4 * DAY]
    assert w.staleness(999) is None and w.staleness(1000 + DAY) == DAY


def test_a_gain_after_the_date_is_in_the_outcome_not_the_selection():
    t = s.T0
    times = [t - 60 * DAY, t - 30 * DAY, t - 2 * DAY, t + 5 * DAY, t + 30 * DAY]
    pnl = {times[0]: 0, times[1]: 0, times[2]: 20_000, times[3]: 80_000, times[4]: 80_000}
    w = _wallet("0xj", lambda x: 100_000.0 + pnl[x], lambda x: float(pnl[x]), times=times)
    assert s.window(w, t - 30 * DAY, t)[0] == 20_000                     # the jump after t is not seen at t
    assert s.window(w, t, t + 30 * DAY)[0] == 60_000                     # it is all in the outcome


def test_roi_base_takes_the_largest_deposit_and_ignores_withdrawals():
    t0 = START + DAY
    times = [t0 + d * DAY for d in (0, 10, 20, 30, 40)]
    av = dict(zip(times, (10_000, 210_000, 310_000, 60_000, 90_000)))
    pnl = dict(zip(times, (0, 0, 100_000, 100_000, 130_000)))
    w = _wallet("0xr", lambda x: float(av[x]), lambda x: float(pnl[x]), times=times)
    p, roi, base = s.window(w, t0, t0 + 40 * DAY)
    assert p == 130_000 and base == 210_000 and abs(roi - 130 / 210) < 1e-9
    tiny = _wallet("0xt", lambda x: 500.0, lambda x: 0.0 if x <= t0 else 5_000.0)
    assert s.window(tiny, t0, t0 + 30 * DAY)[1] is None                  # nearly empty start: no ROI


def test_perps_measures_use_the_perps_series():
    w = _wallet("0xp", lambda t: 300_000.0, lambda t: 2_000.0 * (t - START) / DAY,
                pav=lambda t: 100_000.0, ppnl=lambda t: 1_000.0 * (t - START) / DAY)
    assert s.window(w, s.T0 - 30 * DAY, s.T0, perps=True)[:2] == (30_000.0, 0.3)


# --- the list's rules -----------------------------------------------------------------------

def test_ranked_applies_the_list_rules():
    t = s.T0
    lin = lambda per: (lambda x: per * (x - START) / DAY)
    good = _steady(1)
    small = _wallet("0xsmall", lambda x: 9_000.0, lin(2_000.0))
    no_perp = _wallet("0xnoperp", lambda x: 200_000.0, lin(1_500.0), pav=lambda x: 1_000.0)
    idle = _wallet("0xidle", lambda x: 200_000.0, lin(1_500.0), ppnl=lambda x: 5.0)
    lost = _wallet("0xlost", lambda x: 200_000.0, lambda x: -700_000.0 + 1_500.0 * (x - START) / DAY)
    nine = _wallet("0xnine", lambda x: 20_000.0, lin(300.0))                  # $9K over 30 days
    mm = _wallet("0xmm", lambda x: 200_000.0, lin(3_000.0), lb={"av": 200_000.0, "month_vlm": 3e7, "all_vlm": 2e9})
    drained = _wallet("0xdrained", lambda x: 200_000.0, lin(3_000.0), lb={"av": 50.0, "month_vlm": 3e7, "all_vlm": 2e9})
    r = s.ranked([good, small, no_perp, idle, lost, nine, mm, drained], t, 30)
    assert [a for _, a in r] == ["0xdrained", "0xs01"]
    assert "0xmm" in [a for _, a in s.ranked([mm], t, 30, drop_mm=False)]
    assert "0xidle" in [a for _, a in s.ranked([idle], t, 30, need_active=False)]


def test_ties_are_broken_by_address():
    a, b = _steady(3), _steady(3)
    b.addr = "0xa0"
    assert [x for _, x in s.ranked([a, b], s.T0, 30)] == ["0xa0", "0xs03"]


def test_sub_account_rows_are_flagged():
    w = s.Wallet("0xm", _reply(_daily(), lambda t: 1e6, lambda t: 0.0, all_vlm=1e8), {"av": 1e6, "month_vlm": 0, "all_vlm": 1e9})
    assert w.sub_accounts()
    assert not _steady(1).sub_accounts()


# --- measures of an arm and the bar ---------------------------------------------------------

def test_median_and_hits():
    assert s.median([3, 1, 2]) == 2 and s.median([4, 1, 2, 3]) == 2.5 and s.median([]) is None
    outs = [{"pnl": p, "roi": p / 10_000, "base": 10_000, "big": True, "sub": False} for p in (99, 100, 0, -500)]
    m = s.metrics(outs)
    assert m["hit"] == 25.0 and m["inactive"] == 50.0 and m["hit_active"] == 50.0
    assert s.metrics([])["hit"] is None


def test_sign_flip_p_is_exact():
    assert s.sign_flip_p([1.0, 1.0]) == 0.25
    assert s.sign_flip_p([5.0] * 12) == 1 / 4096
    assert abs(s.sign_flip_p([20.0] * 10 + [-60.0] * 2) - 1201 / 4096) < 1e-12


def test_core_needs_size_breadth_and_the_sign_flip_test():
    assert s.core([5.0] * 12)["met"]
    assert s.core([5.0] * 10 + [0.0] * 2)["met"]                          # ties are not positive, 10 are
    assert not s.core([5.0] * 9 + [0.0] * 3)["met"]
    assert not s.core([2.0] * 12)["met"]                                 # under 3 points on average
    hard = s.core([20.0] * 10 + [-60.0] * 2)                              # mean +6.7, 10 positive, p 0.29
    assert hard["dates_positive"] == 10 and hard["mean_pp"] > 3 and not hard["met"]


def test_btc_sides_required_only_with_three_dates_each():
    assert s.side_means([5, 5, 5, -1, -1, -1], [True] * 3 + [False] * 3) == {
        "up_dates": 3, "down_dates": 3, "up_mean": 5.0, "down_mean": -1.0, "required": True, "met": False}
    assert s.side_means([5, 5, 5, 5, -1, -1], [True] * 4 + [False] * 2)["met"]


def test_equal_arms_take_the_shortest_pool():
    pools = {30: [(1, "a"), (0.5, "b"), (0.2, "c")], 60: [(1, "a")], 90: [(1, "x"), (0.9, "y")]}
    arms, size = s.equal_arms(pools, 2)
    assert size == 1 and arms == {30: ["a"], 60: ["a"], 90: ["x"]}


# --- the whole analysis ---------------------------------------------------------------------

def test_a_longer_window_that_drops_lucky_months_meets_the_bar():
    ws = [_steady(i) for i in range(6)] + [_lucky(i) for i in range(6)]
    res = s.analyse(ws, 0.01, ALTERNATE)                                  # k = 4
    assert res["k"] == 4 and set(res["sizes"]) == {4}
    for p in res["primary"]:
        assert p[30]["hit"] == 25.0 and p[60]["hit"] == 100.0 and p[90]["hit"] == 100.0
    v = res["verdict"]
    assert v[60]["met"] and v[90]["met"] and v[60]["p"] == 1 / 4096
    assert all(c["met"] for c in v[60]["checks"].values())
    assert res["ninety_vs_sixty"]["mean_pp"] == 0.0 and res["chosen_window"] == 60   # 90 must beat 60 to be chosen
    assert res["baseline"][0]["hit"] == 75.0
    assert res["turnover"][30][0] == {"from": res["dates"][1], "to": res["dates"][0], "replaced": 75.0}
    assert res["turnover"][60][0]["replaced"] == 0.0


def test_no_btc_record_means_no_verdict():
    ws = [_steady(i) for i in range(6)] + [_lucky(i) for i in range(6)]
    res = s.analyse(ws, 0.01, None)
    assert not res["signal"] and res["chosen_window"] == 30


def test_no_difference_is_context_not_a_signal():
    ws = [_steady(i, 1_000.0 + 100 * i) for i in range(12)]
    res = s.analyse(ws, 0.01, ALTERNATE)
    assert not res["signal"] and res["chosen_window"] == 30
    assert all(v["mean_pp"] == 0.0 for v in res["verdict"].values())


def test_market_makers_are_left_out_of_the_primary_arms_only():
    mm = _wallet("0xmm", lambda x: 200_000.0, lambda x: 5_000.0 * (x - START) / DAY,
                 lb={"av": 200_000.0, "month_vlm": 3e7, "all_vlm": 2e9})
    ws = [_steady(i) for i in range(6)] + [mm]
    res = s.analyse(ws, 0.01, ALTERNATE)
    assert res["primary"][0][30]["n"] == 4 and res["with_mm"][0][30]["n"] == 4
    assert res["pools"][0][30] == 6                                       # the market maker is not in the pool


# --- data -----------------------------------------------------------------------------------

def test_replies_are_validated():
    good = _reply([START, END], lambda t: 1.0, lambda t: 0.0)
    assert s.valid(good)
    assert not s.valid(None) and not s.valid({"error": "x"}) and not s.valid([])
    assert not s.valid([["allTime", {"accountValueHistory": [], "pnlHistory": []}]])


def test_leaderboard_is_pinned_and_market_makers_are_still_sampled(tmp_path):
    rows = [{"ethAddress": f"0x{i:040x}", "accountValue": "50", "displayName": None,
             "windowPerformances": [["month", {"pnl": "0", "roi": "0", "vlm": "1000000"}],
                                    ["allTime", {"pnl": "0", "roi": "0", "vlm": "20000000"}]]} for i in range(50)]
    lb = tmp_path / "lb.json"
    lb.write_text(json.dumps({"leaderboardRows": rows}))
    conn = s.connect(tmp_path / "db.sqlite")
    assert s.load_leaderboard(conn, lb) == 50
    meta = dict(conn.execute("SELECT k, v FROM meta"))
    assert meta["leaderboard_rows"] == "50" and len(meta["leaderboard_sha256"]) == 64
    assert len(s.sample(conn, 1.0)) == 50                                 # month volume 20,000x the account: kept
    assert s.main(["analyse", "--db", str(tmp_path / "db.sqlite"), "--share", "1.0"]) == 1   # nothing read: refuses


def test_dates_and_sample():
    a = "0x" + "ab" * 20
    assert s.in_sample(a, 1.0) and not s.in_sample(a, 0.0)
    assert s.in_sample(a, 0.5) == (s.skey(a) < 5000)
    assert len(s.dates()) == 12 and s.dates()[0] == s.T0 and s.dates()[-1] == s.T0 - 330 * DAY
