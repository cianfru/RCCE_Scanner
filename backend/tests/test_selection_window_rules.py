"""The selection window study's declared rules at their edges (tests added after the second review, before any result)."""
import json
import time
import zlib

from backtest import selection_window_study as s

DAY = s.DAY
T = s.T0
START = s.T0 - 450 * DAY
END = s.T0 + 31 * DAY
BIG = {"av": 200_000.0, "month_vlm": 1e6, "all_vlm": 2e7}
SMALL = {"av": 200_000.0, "month_vlm": 1e6, "all_vlm": 2e6}
ALT = [k % 2 == 0 for k in range(s.N_DATES)]


def _pts(fn, times):
    return [[t * 1000, fn(t)] for t in times]


def _reply(times, av, pnl, pav=None, ppnl=None):
    return [["month", {"vlm": "1000000"}],
            ["allTime", {"accountValueHistory": _pts(av, times), "pnlHistory": _pts(pnl, times), "vlm": "2e7"}],
            ["perpAllTime", {"accountValueHistory": _pts(pav or av, times), "pnlHistory": _pts(ppnl or pnl, times)}]]


def _daily():
    return [START + d * DAY for d in range(int((END - START) // DAY) + 1)]


def _w(addr, av, pnl, pav=None, ppnl=None, lb=None, times=None):
    return s.Wallet(addr, _reply(times or _daily(), av, pnl, pav, ppnl), lb or BIG)


def _pts_w(addr, avs, pnls, lb=None):
    """Explicit points: {time: value}."""
    times = sorted(avs)
    return _w(addr, lambda x: float(avs[x]), lambda x: float(pnls[x]), lb=lb, times=times)


def _addrs(r):
    return [a for _, a in r]


# --- declared constants -------------------------------------------------------------------

def test_declared_dates_and_list_size():
    assert time.gmtime(s.T0)[:6] == (2026, 10, 1, 0, 0, 0)
    assert time.gmtime(s.dates()[-1])[:3] == (2025, 11, 5)
    assert s.analyse([], 0.5)["k"] == 200 and s.analyse([], 0.5)["cap"] == 300


# --- list rules at their declared edges ---------------------------------------------------

def test_list_floors_are_inclusive_and_exact():
    ts = [T - 60 * DAY, T - 30 * DAY, T - DAY, T, T + 30 * DAY]
    def mk(addr, av, pnl, **kw):
        return _pts_w(addr, dict(zip(ts, av)), dict(zip(ts, pnl)), **kw)
    av10k = mk("0xav10k", [10_000] * 5, [0, 0, 5_000, 12_000, 12_000])                # AV exactly $10K: kept
    av_lo = mk("0xavlo", [9_999] * 5, [0, 0, 5_000, 12_000, 12_000])                  # just under: dropped
    pnl10k = mk("0xpnl10k", [200_000] * 5, [50_000, 50_000, 55_000, 60_000, 60_000])  # window PnL exactly $10K
    pnl_lo = mk("0xpnllo", [200_000] * 5, [50_000, 50_000, 55_000, 59_999, 59_999])
    at_eq = mk("0xateq", [200_000] * 5, [0, 0, 10_000, 30_000, 30_000])               # all-time = window: kept
    at_lo = mk("0xatlo", [200_000] * 5, [-20_000, -20_000, 0, 15_000, 15_000])        # all-time +15K < window 35K
    base1k = mk("0xbase1k", [1_000, 1_000, 20_000, 21_000, 21_000], [0, 0, 19_000, 20_000, 20_000])
    base_lo = mk("0xbaselo", [999, 999, 19_999, 20_999, 20_999], [0, 0, 19_000, 20_000, 20_000])
    got = set(_addrs(s.ranked([av10k, av_lo, pnl10k, pnl_lo, at_eq, at_lo, base1k, base_lo], T, 30)))
    assert got == {"0xav10k", "0xpnl10k", "0xateq", "0xbase1k"}


def test_perps_floor_is_inclusive():
    lin = lambda per: (lambda x: per * (x - START) / DAY)
    edge = _w("0xp5k", lambda x: 200_000.0, lin(1_500.0), pav=lambda x: 5_000.0)
    lo = _w("0xp4k", lambda x: 200_000.0, lin(1_500.0), pav=lambda x: 4_999.0)
    assert _addrs(s.ranked([edge, lo], T, 30)) == ["0xp5k"]


def test_perps_arm_uses_perps_all_time():
    w = _w("0xpat", lambda x: 300_000.0, lambda x: 1e6 + 1_500.0 * (x - START) / DAY,
           pav=lambda x: 100_000.0, ppnl=lambda x: -425_000.0 + 1_000.0 * (x - START) / DAY)
    assert s.ranked([w], T, 30, perps=True) == []          # perps all-time +25K < perps window +30K


def test_nothing_after_t_enters_the_list_rules():
    lin = lambda per: (lambda x: per * (x - START) / DAY)
    jump = _w("0xjump", lambda x: 200_000.0, lambda x: 1e6 + 10.0 * (x - START) / DAY + (50_000.0 if x > T else 0.0))
    crash = _w("0xcrash", lambda x: 200_000.0, lambda x: 1_500.0 * (x - START) / DAY - (1e6 if x > T else 0.0))
    gone = _w("0xgone", lambda x: 200_000.0 if x <= T else 0.0, lin(1_500.0))
    wakes = _w("0xwakes", lambda x: 200_000.0, lin(1_500.0),
               ppnl=lambda x: 5.0 if x <= T else 5.0 + (x - T) / DAY)
    assert set(_addrs(s.ranked([jump, crash, gone, wakes], T, 30))) == {"0xcrash", "0xgone"}


def test_outcome_is_exactly_the_next_30_days():
    ts = [T - 30 * DAY, T - DAY, T, T + 30 * DAY, T + 30 * DAY + DAY // 2, END]
    w = _pts_w("0xo", dict(zip(ts, [200_000] * 6)), dict(zip(ts, [0, 1, 2, 2, 50_002, 50_002])))
    assert s._outcome(w, T)["pnl"] == 0.0


def test_market_maker_edges():
    mk = lambda av, vlm: s.Wallet("0xm", _reply(_daily(), lambda t: 1.0, lambda t: 0.0),
                                  {"av": av, "month_vlm": vlm, "all_vlm": 2e7})
    assert not mk(10_000.0, 1_000_000.0).market_maker()     # exactly 100x: not over
    assert mk(10_000.0, 1_000_001.0).market_maker()
    assert mk(50_000.0, 6_000_000.0).market_maker()         # 120x a $50K account
    assert not mk(9_999.0, 1e9).market_maker()


# --- the bar ------------------------------------------------------------------------------

def test_bar_edges():
    assert s.core([3.0] * 12)["met"]                         # +3 exactly meets condition 1
    near = s.core([6.0] * 10 + [-9.0] * 2)                   # mean 3.5, 10 positive, p 0.0486
    assert near["mean_pp"] >= 3 and near["dates_positive"] == 10 and 0.025 < near["p"] <= 0.05 and not near["met"]
    assert not s.side_means([5, 5, 5, 0, 0, 0], [True] * 3 + [False] * 3)["met"]   # a side at 0 is not above 0


def test_btc_up_compares_each_date_with_30_days_later(tmp_path):
    conn = s.connect(tmp_path / "db.sqlite")
    pts = [T + 30 * DAY] + s.dates() + [s.dates()[-1] - 30 * DAY]
    opens = {t: (100.0 if i % 2 == 0 else 50.0) for i, t in enumerate(pts)}
    conn.execute("INSERT INTO meta VALUES ('btc_open', ?)", (json.dumps(opens),))
    assert s.btc_up(conn) == ALT


# --- verdict and choice, on fixed pools and outcomes ---------------------------------------

def _wallets(lb_of):
    return [s.Wallet(a, _reply([START, END], lambda t: 100_000.0, lambda t: 0.0), lb_of(a)) for a in ADDRS]


ADDRS = [f"{p}{i}" for p in ("a", "b", "c", "A", "B") for i in range(10)]
SHARE = 10 / 400                                              # k = 10


def _fake(monkeypatch, pools, outcome, perps_pools=None, perps_outcome=None):
    """pools(i, days) -> addresses in rank order; outcome(addr, i) -> (pnl, roi); i = date index."""
    idx = {t: i for i, t in enumerate(s.dates())}

    def ranked(wallets, t, days, min_roi=None, perps=False, need_active=True, drop_mm=True):
        src = perps_pools if (perps and perps_pools) else pools
        return [(1.0 - j * 1e-3, a) for j, a in enumerate(src(idx[t], days))]

    def _outcome(w, t, perps=False):
        src = perps_outcome if (perps and perps_outcome) else outcome
        pnl, roi = src(w.addr, idx[t])
        return {"pnl": pnl, "roi": roi, "base": 100_000.0, "big": w.big(), "sub": False}

    monkeypatch.setattr(s, "ranked", ranked)
    monkeypatch.setattr(s, "_outcome", _outcome)


def _hits(table):
    """table: {prefix: hits per date (int or list)} -> outcome(addr, i)."""
    def outcome(a, i):
        h = table.get(a[0], 0)
        h = h[i] if isinstance(h, list) else h
        return (1_000.0, 0.01) if int(a[1:]) < h else (-1_000.0, -0.01)
    return outcome


ARM = {30: "a", 60: "b", 90: "c"}


def _plain(i, days):
    return [f"{ARM[days]}{j}" for j in range(10)]


def test_ninety_is_chosen_when_it_beats_sixty_on_the_bar(monkeypatch):
    _fake(monkeypatch, _plain, _hits({"a": 3, "b": 5, "c": 8}))
    res = s.analyse(_wallets(lambda a: BIG), SHARE, ALT)
    assert res["verdict"][60]["met"] and res["verdict"][90]["met"] and res["chosen_window"] == 90


def test_sixty_is_kept_when_ninety_beats_it_only_on_average(monkeypatch):
    c = [7] * 9 + [5] * 3                                     # 90 - 60: +10 on 9 dates, -10 on 3: mean +5
    _fake(monkeypatch, _plain, _hits({"a": 3, "b": 6, "c": c}))
    res = s.analyse(_wallets(lambda a: BIG), SHARE, ALT)
    assert res["verdict"][90]["met"] and res["ninety_vs_sixty"]["mean_pp"] > 3 and res["chosen_window"] == 60


def test_the_one_window_that_passes_is_chosen(monkeypatch):
    _fake(monkeypatch, _plain, _hits({"a": 3, "b": 3, "c": 8}))
    res = s.analyse(_wallets(lambda a: BIG), SHARE, ALT)
    assert not res["verdict"][60]["met"] and res["chosen_window"] == 90 and res["signal"]


def test_big_check_reranks_among_10m_wallets_only(monkeypatch):
    pools = lambda i, d: ([f"a{j}" for j in range(10)] + [f"A{j}" for j in range(10)]) if d != 60 else [f"b{j}" for j in range(10)]
    _fake(monkeypatch, pools, _hits({"a": 0, "A": 10, "b": 10}))
    res = s.analyse(_wallets(lambda a: SMALL if a[0] == "a" else BIG), SHARE, ALT)
    assert res["primary"][0][60]["hit"] == 100 and res["primary"][0][30]["hit"] == 0
    assert not res["verdict"][60]["checks"]["big"]["met"] and not res["signal"]


def test_perps_check_selects_on_perps(monkeypatch):
    perps_pools = lambda i, d: [f"a{j}" for j in range(10)] if d == 60 else _plain(i, d)
    _fake(monkeypatch, lambda i, d: _plain(i, d) if d != 90 else _plain(i, 30), _hits({"a": 0, "b": 10}),
          perps_pools=perps_pools)
    res = s.analyse(_wallets(lambda a: BIG), SHARE, ALT)
    assert not res["verdict"][60]["checks"]["perps"]["met"] and not res["signal"]


def test_perps_check_measures_the_outcome_on_perps(monkeypatch):
    _fake(monkeypatch, lambda i, d: _plain(i, d) if d != 90 else _plain(i, 30), _hits({"a": 0, "b": 10}),
          perps_outcome=_hits({"a": 0, "b": 0}))
    res = s.analyse(_wallets(lambda a: BIG), SHARE, ALT)
    assert not res["verdict"][60]["checks"]["perps"]["met"] and not res["signal"]


def test_roi_check_uses_the_clipped_mean(monkeypatch):
    def outcome(a, i):
        if a[0] != "b":
            return (0.0, 0.0)
        j = int(a[1:])
        return (1_000.0, 20.0) if j == 0 else (1_000.0, 0.01) if j < 6 else (-1_000.0, -0.5)
    _fake(monkeypatch, lambda i, d: _plain(i, d) if d != 90 else _plain(i, 30), outcome)
    res = s.analyse(_wallets(lambda a: BIG), SHARE, ALT)
    v = res["verdict"][60]
    assert v["mean_pp"] == 60.0 and v["checks"]["roi"]["mean_pp"] < 0 and not res["signal"]


def test_a_pick_that_stopped_trading_is_a_miss(monkeypatch):
    def outcome(a, i):
        j = int(a[1:])
        if a[0] == "b":
            return (1_000.0, 0.01) if j < 6 else (-100.0, -0.001)
        return (1_000.0, 0.01) if j < 3 else (0.0, 0.0)
    _fake(monkeypatch, lambda i, d: _plain(i, d) if d != 90 else _plain(i, 30), outcome)
    res = s.analyse(_wallets(lambda a: BIG), SHARE, ALT)
    assert res["verdict"][60]["mean_pp"] == 30.0 and res["chosen_window"] == 60


def test_a_date_without_arms_means_no_verdict(monkeypatch):
    _fake(monkeypatch, lambda i, d: [] if i == 11 else _plain(i, d), _hits({"a": 3, "b": 5, "c": 8}))
    res = s.analyse(_wallets(lambda a: BIG), SHARE, ALT)
    assert not res["signal"] and res["verdict"][60]["missing_dates"] == 1


# --- data -----------------------------------------------------------------------------------

def test_reply_needs_pnl_history():
    assert not s.valid([["allTime", {"accountValueHistory": [[0, "1"]], "pnlHistory": []}]])


def test_analyse_refuses_while_a_sampled_wallet_is_unread(tmp_path):
    rows = [{"ethAddress": f"0x{i:040x}", "accountValue": "50",
             "windowPerformances": [["month", {"vlm": "1"}], ["allTime", {"vlm": "2e7"}]]} for i in range(2)]
    lb = tmp_path / "lb.json"
    lb.write_text(json.dumps({"leaderboardRows": rows}))
    conn = s.connect(tmp_path / "db.sqlite")
    s.load_leaderboard(conn, lb)
    raw = _reply([START, END], lambda t: 1.0, lambda t: 0.0)
    conn.execute("INSERT INTO portfolio VALUES (?,?,?)", (f"0x{0:040x}", zlib.compress(json.dumps(raw).encode()), 0))
    conn.commit()
    assert s.main(["analyse", "--db", str(tmp_path / "db.sqlite"), "--share", "1.0"]) == 1


def test_floors_are_read_where_the_outcome_starts():
    """Perps points 4 days after the total's: a perps loss between the total's last point before t and t falls in
    the outcome's span, so it must not decide eligibility at t."""
    tot = [T - 5 * DAY - 7 * k * DAY for k in range(20)][::-1] + [T + 2 * DAY, T + 30 * DAY, END]
    per = [x + 4 * DAY for x in tot]
    loss_at = T - 3 * DAY

    def pnl(x):
        return 1_500.0 * (x - START) / DAY - (80_500.0 if x >= loss_at else 0.0)

    def pav(x):
        return 2_000.0 if x >= loss_at else 82_500.0
    reply = [["month", {"vlm": "1000000"}],
             ["allTime", {"accountValueHistory": _pts(lambda x: 200_000.0, tot), "pnlHistory": _pts(pnl, tot), "vlm": "2e7"}],
             ["perpAllTime", {"accountValueHistory": _pts(pav, per), "pnlHistory": _pts(pnl, per)}]]
    w = s.Wallet("0xlag", reply, BIG)
    assert s.eligible_base(w, T)                              # read as of T - 5 d, the outcome's start
    assert "0xlag" in _addrs(s.ranked([w], T, 30))
    assert s._outcome(w, T)["pnl"] == 1_500.0 * 35 - 80_500.0  # the loss is scored in the outcome (from T - 5 d)


def test_effective_days_follow_the_points_read():
    w = _pts_w("0xe", {T - 40 * DAY: 1, T - 33 * DAY: 1, T - 5 * DAY: 1, T + 26 * DAY: 1},
               {T - 40 * DAY: 0, T - 33 * DAY: 0, T - 5 * DAY: 0, T + 26 * DAY: 0})
    assert s.effective_days(w, T - 30 * DAY, T) == 28.0
    assert s.effective_days(w, T, T + 30 * DAY) == 31.0
    assert s.effective_days(w, T - 90 * DAY, T) == 35.0       # from the first point
