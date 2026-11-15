"""The cohort selection study's code, on made-up wallets (docs/reviews/cohort-selection-study.md)."""
import itertools

from backtest import cohort_selection_study as c
from backtest import selection_window_study as sw

DAY = sw.DAY
START = sw.T0 - (sw.N_DATES * 30 + 400) * DAY
END = sw.T0 + 31 * DAY
LB = {"av": 200_000.0, "month_vlm": 1e6, "all_vlm": 2e7}


def _pts(fn, times):
    return [[int(t * 1000), fn(t)] for t in times]


def _reply(times, av, pnl):
    return [["month", {"vlm": "1000000"}],
            ["allTime", {"accountValueHistory": _pts(av, times), "pnlHistory": _pts(pnl, times), "vlm": "20000000"}],
            ["perpAllTime", {"accountValueHistory": _pts(av, times), "pnlHistory": _pts(pnl, times)}]]


def _weekly(start=START):
    return [start + d * 7 * DAY for d in range(int((END - start) // (7 * DAY)) + 2)]


def _addr(half, i):
    """An address in the given half (found by trying names in order)."""
    for j in itertools.count():
        a = f"0x{half[0]}{i:03d}{j:04d}"
        if c.half_of(a) == half:
            return a


def _wallet(addr, av, pnl, times=None):
    return sw.Wallet(addr, _reply(times or _weekly(), av, pnl), LB)


def _steady(addr, per_day=500.0, start=START):
    """$200K account earning a fixed amount a day (a small wiggle keeps the active rule satisfied)."""
    return _wallet(addr, lambda t: 200_000.0, lambda t: per_day * (t - start) / DAY + (t // DAY) % 3,
                   times=_weekly(start))


def _lucky(addr, i):
    """Month blocks (aligned with the study's dates) of +$110K and -$100K in turn: up $5K a month on average, never
    steady. The account moves with the PnL (no deposits or withdrawals)."""
    def v(t):
        m, frac = divmod((t - sw.T0) / (30 * DAY), 1)
        m = int(m)
        cum = 5_000.0 * m + (0.0 if m % 2 == 0 else (105_000.0 if i % 2 == 0 else -105_000.0))
        gain = 110_000.0 if (m + i) % 2 == 0 else -100_000.0
        return cum + gain * frac + (t // DAY) % 3
    return _wallet(addr, lambda t: 400_000.0 + v(t), lambda t: 1_000_000.0 + v(t))


# --- measures ----------------------------------------------------------------------------------------

def test_halves_split_the_snapshot_by_the_same_hash():
    assert c.half_of(_addr("read", 1)) == "read" and c.half_of(_addr("unread", 1)) == "unread"
    assert all((c.half_of(a) == "read") == (sw.skey(a) < 5_000) for a in (f"0x{i:x}" for i in range(500)))


def test_old_enough_reads_the_first_point():
    t = sw.T0
    young = _steady("0xy", start=t - 100 * DAY)
    old = _steady("0xo", start=t - 200 * DAY)
    assert not c.old_enough(young, t) and c.old_enough(old, t)
    assert c.long_rules(young, t) is None


def test_blocks_are_month_spans_before_t_newest_first():
    t = sw.T0
    w = _steady("0xb", per_day=1_000.0, start=t - 100 * DAY)
    times = [t - 100 * DAY + d * DAY for d in range(101)]
    w = _wallet("0xb", lambda x: 100_000.0, lambda x: 1_000.0 * (x - (t - 100 * DAY)) / DAY, times=times)
    b = c.block_pnls(w, t, 4)
    assert b[:3] == [30_000.0, 30_000.0, 30_000.0]
    assert b[3] is None                                         # starts before the first point
    assert c.profit_blocks(w, t, 4) == 3


def test_drawdown_is_the_largest_fall_from_a_peak():
    t0 = START
    times = [t0 + d * DAY for d in range(6)]
    pnl = dict(zip(times, (0, 50_000, 20_000, 80_000, 30_000, 60_000)))
    w = _wallet("0xd", lambda x: 100_000.0, lambda x: float(pnl[x]), times=times)
    assert c.drawdown(w, t0, t0 + 5 * DAY) == 50_000
    assert c.drawdown(w, t0 + 3 * DAY, t0 + 5 * DAY) == 50_000     # the peak at the start counts
    assert c.drawdown(w, t0 + 4 * DAY, t0 + 5 * DAY) == 0


def test_nothing_after_t_enters_a_score():
    t = sw.T0
    times = _weekly()
    a = _wallet("0xa", lambda x: 200_000.0, lambda x: 100.0 * (x - START) / DAY + (x // DAY) % 3, times=times)
    b = _wallet("0xa", lambda x: 200_000.0, lambda x: 100.0 * (x - START) / DAY + (x // DAY) % 3
                + (1e6 if x > t else 0), times=times)
    for rule in c.CANDIDATES:
        assert c.score(rule, a, t) == c.score(rule, b, t)
    assert sw._outcome(b, t)["pnl"] > sw._outcome(a, t)["pnl"]


def test_rules_rank_as_declared():
    t = sw.T0
    small = _steady(_addr("read", 1), per_day=200.0)            # $36K over 180 days, steady
    big = _steady(_addr("read", 2), per_day=2_000.0)             # $360K, steady
    lucky = _lucky(_addr("read", 3), 0)                          # up, but losing months in turn
    ws = [small, big, lucky]
    assert c.pick(ws, t, "dollars")[0][0] in (big.addr, lucky.addr)
    steady, pool = c.pick(ws, t, "steady")
    assert lucky.addr not in steady and set(steady) == {small.addr, big.addr} and pool == 2
    assert steady[0] == big.addr                                 # same months profitable: more dollars first
    risk, _ = c.pick(ws, t, "risk")
    assert risk.index(big.addr) < risk.index(lucky.addr) if lucky.addr in risk else True
    lost = _wallet(_addr("read", 4), lambda x: 200_000.0,
                   lambda x: -500_000.0 + 300.0 * (x - START) / DAY + (x // DAY) % 3)   # recovering a big loss
    assert c.long_rules(lost, t) is None                        # all-time PnL under the 180-day PnL


def test_risk_floor_keeps_smooth_accounts_from_dividing_by_nothing():
    t = sw.T0
    w = _steady("0xf", per_day=300.0)
    pnl, roi, base = c.long_rules(w, t)
    assert c.score("risk", w, t) == (roi / c.DD_FLOOR,)


def test_btc_correlation_reads_pnl_changes_against_btc_moves():
    t = sw.T0
    days = range(int((t - 400 * DAY) // DAY), int(t // DAY) + 2)
    price = {d * DAY: 50_000.0 * (1.02 if d % 14 < 7 else 0.98) ** (d % 7) for d in days}
    btc = c.Btc(price)
    follow = _wallet("0xc", lambda x: 200_000.0, lambda x: 10.0 * (btc.at(x) or 50_000.0))
    flat = _steady("0xe")
    assert c.btc_corr(follow, t, btc) > 0.9
    assert c.btc_corr(flat, t, btc) is None or abs(c.btc_corr(flat, t, btc)) < 0.5
    ex = c.exposure([follow], t, btc)
    assert ex["with_btc"] == 100.0 and ex["unknown"] == 0.0


# --- the bar -----------------------------------------------------------------------------------------

def _row(hit, roi=0.0, base_hit=50.0, base_roi=0.0):
    m = lambda h, r: {"hit": h, "mean_roi_clipped": r}
    return {"baseline": m(base_hit, base_roi), **{r: m(hit, roi) for r in c.CANDIDATES}}


UP = [k % 3 == 0 for k in range(sw.N_DATES)]


def test_bar_needs_size_breadth_p_roi_and_both_btc_sides():
    good = [_row(60.0, 1.0) for _ in range(12)]
    assert c.judge(good, "steady", UP)["met"]
    small = [_row(54.0, 1.0) for _ in range(12)]                    # +4 points
    assert not c.judge(small, "steady", UP)["met"]
    few = [_row(80.0 if k < 8 else 45.0, 1.0) for k in range(12)]   # 8 of 12 dates above
    assert not c.judge(few, "steady", UP)["met"]
    worse_roi = [_row(60.0, -1.0) for _ in range(12)]
    assert not c.judge(worse_roi, "steady", UP)["met"]
    one_side = [_row(70.0 if not UP[k] else 45.0, 1.0) for k in range(12)]   # only months BTC fell
    v = c.judge(one_side, "steady", UP)
    assert not v["met"] and not v["btc"]["met"]
    missing = good[:11] + [{"baseline": {"hit": 50.0, "mean_roi_clipped": 0.0},
                            **{r: {"hit": None, "mean_roi_clipped": None} for r in c.CANDIDATES}}]
    assert not c.judge(missing, "steady", UP)["met"]


def test_p_value_condition():
    # 9 positive dates of +12 and 3 of -10: mean +6.5, but p = P(sign-flip mean >= observed)
    diffs = [12.0] * 9 + [-10.0] * 3
    v = c.core(diffs)
    assert v["dates_positive"] == 9 and v["mean_pp"] == 6.5
    assert v["met"] == (v["p"] <= c.BAR_P)


# --- the whole analysis --------------------------------------------------------------------------------

def _half(half, steady_n, lucky_n):
    return ([_steady(_addr(half, i), per_day=600.0 + 20 * i) for i in range(steady_n)]
            + [_lucky(_addr(half, 100 + i), i) for i in range(lucky_n)])


def test_a_rule_must_pass_on_both_halves():
    # Read half: steady earners and lucky wallets; the steady ones keep earning, so the steady rule beats everyone.
    # Unread half: only lucky wallets, so the steady list is empty and cannot pass there.
    ws = _half("read", 6, 6) + _half("unread", 0, 8)
    res = c.analyse(ws, UP)
    assert res["halves"]["read"]["verdict"]["steady"]["met"]
    assert not res["halves"]["unread"]["verdict"]["steady"]["met"]
    assert "steady" not in res["passing"] and res["signal"] is False and res["chosen"] is None
    both = c.analyse(_half("read", 6, 6) + _half("unread", 6, 6), UP)
    assert "steady" in both["passing"] and both["chosen"] in both["passing"]


def test_counts_read_no_outcome():
    ws = _half("read", 3, 2) + _half("unread", 2, 1)
    out = c.counts(ws)
    assert out["read"]["wallets"] == 5 and out["unread"]["wallets"] == 3
    assert set(out["read"]["dates"][0]) == {"date", "baseline", "seasoned", *c.CANDIDATES}


def test_stability_compare_points_before_the_end():
    t = c.STABILITY_END
    times = [t - 20 * DAY, t - 10 * DAY, t + 5 * DAY]
    a = _reply(times, lambda x: 1.0, lambda x: 2.0)
    b = _reply(times[:2] + [t + 6 * DAY], lambda x: 1.0, lambda x: 2.0)
    assert c.compare_points(a, b)["same"]                         # a later point does not count
    d = _reply([t - 20 * DAY, t - 9 * DAY], lambda x: 1.0, lambda x: 2.0)
    r = c.compare_points(a, d)
    assert not r["same"] and r["differing"] == 4
