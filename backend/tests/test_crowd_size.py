"""The crowd-size study's rules on made-up data (docs/reviews/crowd-size-study.md)."""
from research import crowd_size as C


def test_the_check_ranks_rebuilt_against_recorded_and_finds_the_level():
    reb = {d: (100 + d, 50) for d in range(20)}
    rec = {d: (2 * (100 + d), 100) for d in range(5, 25)}               # twice the rebuilt level, same order
    chk = C.check(reb, rec)
    assert chk["days"] == 15 and chk["passed"]
    assert chk["rho_long"] == 1.0 and chk["long_ratio"] == 2.0
    assert abs(chk["share_offset"]) < 0.01
    short = C.check(reb, {d: rec[d] for d in range(5, 15)})            # 10 days: too few
    assert not short["passed"]
    rev = C.check(reb, {d: (1000 - d, 100) for d in range(5, 25)})      # opposite order
    assert not rev["passed"] and rev["rho_long"] == -1.0


def test_joined_puts_the_rebuilt_days_on_the_recorded_level_only_when_the_check_passed():
    reb = {1: (100, 100), 2: (100, 100), 3: (100, 100)}
    rec = {3: (300, 100)}
    chk = {"passed": True, "long_ratio": 3.0, "share_offset": 0.25}
    j = C.joined(reb, rec, chk)
    assert j[1] == (300.0, 0.75) and j[3] == (300, 0.75)               # recorded where present
    assert C.joined(reb, rec, {"passed": False}) == {1: (100, 0.5), 2: (100, 0.5), 3: (100, 0.5)}
    assert C.joined(reb, rec, {"passed": False}, oos=True) == {3: (300, 0.75)}     # out of sample: recorded alone


def test_crowded_needs_both_readings_high_in_their_90_days():
    series = {d: (100, 0.5) for d in range(100)}
    series[95] = (200, 0.9)                                           # many long positions, mostly long
    series[96] = (200, 0.4)                                           # many, but the share is low
    series[97] = (50, 0.95)                                           # mostly long, few positions
    crowd = C.crowd_state(series)
    assert 58 not in crowd and 59 in crowd                            # 60 readings in the window from day 59
    assert crowd[95] and not crowd[96] and not crowd[97]
    assert crowd[50 + 9] is True                                      # a flat series sits at its own top


def test_hot_is_greed_in_a_broad_uptrend():
    rows = [{"day": d} for d in range(5)]
    fg = {0: 75, 1: 75, 2: 60, 4: 80}
    state = {0: {"on": True}, 1: {"on": False}, 2: {"on": True}, 3: {"on": True}, 4: {"on": True}}
    assert C.hot_state(rows, fg, state) == {0: True, 1: False, 2: False, 4: True}


def test_episodes_join_short_gaps_need_a_known_start_and_a_month_apart():
    days = range(0, 120)
    crowd = {d: d in (10, 11, 15, 30, 70, 71) for d in days}
    hot = {d: True for d in days}
    st = C.episodes(crowd, hot)
    assert [(s["first"], s["last"], s["known"]) for s in st] == [(10, 15, True), (30, 30, True), (70, 71, True)]
    assert C.counted(st) == [10, 70]                                  # 30 is 20 days after 10
    late = C.episodes({d: d in (3,) for d in days}, hot)
    assert late[0]["known"] is False and C.counted(late) == []        # its 6 days before are not all readable


def _run(shares):
    rows = [{"day": d, "uptrend": s} for d, s in enumerate(shares)]
    state, runs = C.L.runs(rows)
    return {r["day"]: r["uptrend"] for r in rows}, state, runs


def test_rolled_within_counts_a_20_point_fall_from_the_high_so_far_or_the_end():
    share, state, runs = _run([0.6, 0.9, 0.85, 0.8, 0.75, 0.69, 0.7] + [0.7] * 40)
    last = 46
    assert C.rolled_within(0, state, runs, share, last) is True        # 0.9 -> 0.69 on day 5
    assert C.rolled_within(5, state, runs, share, last) is False       # already rolled; no new fall, no end
    share2, state2, runs2 = _run([0.6] * 10 + [0.5] * 10)
    assert C.rolled_within(2, state2, runs2, share2, 19) is True       # the run ends on day 10
    assert C.rolled_within(12, state2, runs2, share2, 19) is None      # no run under way
    share3, state3, runs3 = _run([0.7] * 20)
    assert C.rolled_within(0, state3, runs3, share3, 19) is None       # 30 days not over yet


def test_the_roll_over_block_compares_rates_and_needs_eight():
    rolled = {d: d < 100 for d in range(200)}
    events = list(range(0, 80, 10))                                   # 8 events, all rolled
    pool = list(range(90, 200))                                       # 10 of 110 rolled
    b = C.roll_block(events, pool, rolled)
    assert b["events"] == 8 and b["rolled"] == 8 and b["verdict"] == "met"
    assert b["comparison_rate"] == round(10 / 110, 3) and b["draws_at_or_beyond"] == 0.0
    few = C.roll_block(events[:5], pool, rolled)
    assert few["verdict"] == "not met" and not few["enough"]


def test_comparison_days_leave_out_the_month_after_a_start_and_crowded_days():
    hot = {d: True for d in range(100)}
    crowd = {d: d == 50 for d in range(100)}
    rolled = {d: False for d in range(100)}
    pool = C.comparison_days(hot, crowd, [10], rolled)
    assert 10 not in pool and 40 not in pool and 41 in pool and 50 not in pool and 9 in pool


def test_the_owners_own_episode_is_reported_apart():
    st = [{"first": 20700, "last": 20705, "known": True}, {"first": 20740, "last": 20750, "known": True},
          {"first": 20775, "last": 20776, "known": True}]
    assert C.split(st, False) == ([20700], [20740])                   # reaches into 29 Sep 2026: seen, not counted
    assert C.split(st, True) == ([20775], [])
