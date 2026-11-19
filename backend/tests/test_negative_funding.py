"""The negative funding study's rules (docs/reviews/negative-funding-study.md), on made-up data."""
from research import negative_funding as nf

H, STEP = nf.HOUR, nf.STEP
T0 = nf.EV_START + 30 * 24 * H          # well inside the event window


def hourly(rates, start=T0):
    return [(start + k * H, r, 1.0) for k, r in enumerate(rates)]


def flat_candles(n, start=T0 - 10 * STEP, price=1.0):
    return [(start + k * STEP, price, price, price, price) for k in range(n)]


def test_event_needs_threshold_and_a_quiet_week_before():
    p = hourly([0.0001] * 5 + [-0.0011] + [-0.002] * 3 + [0.0] * 200 + [-0.0015])
    ev = nf.events(p, nf.THRESH)
    assert ev == [T0 + 5 * H, T0 + 209 * H]          # 201 hours after the last hit: a new episode
    p2 = hourly([-0.0011] + [0.0] * 100 + [-0.0011])
    assert nf.events(p2, nf.THRESH) == [T0]          # 101 hours later: the same episode


def test_threshold_is_per_hour_whatever_the_interval():
    eight = [(T0, -0.008, 8.0)]                       # -0.8% over 8 hours = -0.1% an hour
    four = [(T0, -0.0039, 4.0)]                       # just under -0.1% an hour in size: not a hit
    assert nf.events(eight, nf.THRESH) == [T0]
    assert nf.events(four, nf.THRESH) == []
    assert nf.events([(T0, 0.0012, 1.0)], nf.POS_THRESH) == [T0]


def test_events_outside_the_window_do_not_count():
    assert nf.events([(nf.EV_START - H, -0.01, 1.0)], nf.THRESH) == []
    assert nf.events([(nf.EV_END, -0.01, 1.0)], nf.THRESH) == []


def test_entry_is_the_first_close_at_or_after_the_print():
    c = flat_candles(20, start=T0)
    assert nf.entry_index(c, T0 + 1 * H) == 0         # closes at T0 + 4h
    assert nf.entry_index(c, T0 + STEP) == 0
    assert nf.entry_index(c, T0 + STEP + 1) == 1
    assert nf.entry_index(c, T0 + 100 * STEP) is None


def test_outcome_returns_spike_drop_and_carry():
    c = flat_candles(60, start=T0)
    c[10] = (c[10][0], 1.0, 1.5, 0.6, 1.2)            # inside the next 7 days of candle 0
    c[6] = (c[6][0], 1.0, 1.0, 1.0, 1.1)              # closes 24 hours after candle 0's close
    p = hourly([-0.001] * 300, start=T0)
    s = nf.Series(p, c)
    o = nf.outcome(s, 0)
    assert abs(o["r24"] - 0.1) < 1e-12
    assert abs(o["up7"] - 0.5) < 1e-12 and abs(o["down7"] + 0.4) < 1e-12
    assert abs(o["carry7"] - 0.168) < 1e-9            # 168 hourly prints of -0.1%, received by a long
    assert o["ended"] is False


def test_outcome_flags_a_coin_whose_candles_end():
    c = flat_candles(8, start=T0)
    s = nf.Series([], c)
    o = nf.outcome(s, 0)
    assert o["ended"] is True and o["r168"] == 0.0


def test_ordinary_leaves_out_the_week_after_a_hit():
    c = flat_candles(120, start=T0)
    p = [(T0 + 10 * STEP, -0.002, 1.0)]
    idx = nf.ordinary(c, p, nf.THRESH)
    closes = {c[i][0] + STEP for i in idx}
    assert T0 + 10 * STEP not in closes and T0 + 10 * STEP + 167 * H not in closes
    assert T0 + 10 * STEP + 168 * H in closes and T0 + 9 * STEP in closes


def test_binomial_tail():
    assert abs(nf.binom_sf(1, 1, 0.3) - 0.3) < 1e-12
    assert abs(nf.binom_sf(2, 2, 0.5) - 0.25) < 1e-12
    assert nf.binom_sf(0, 5, 0.1) == 1.0
    assert nf.binom_sf(1105, 1105, 0.05) < 1e-300 and abs(nf.binom_sf(500, 1000, 0.5) - 0.5126) < 1e-3


def _o(t, up7, r168):
    return {"t": t, "up7": up7, "r168": r168}


def test_judge_passes_only_with_every_condition():
    comp = [_o(k, 0.0, -0.01) for k in range(1000)] + [_o(k, 0.4, 0.0) for k in range(50)]   # 4.8% spikes
    ev = [_o(k, 0.5 if k % 2 == 0 else 0.0, 0.05) for k in range(40)]                         # 50% spikes
    v = nf.judge(ev, comp)
    assert v["met"] and all(v["conditions"].values())
    ev_late = [_o(k, 0.5 if k >= 20 else 0.0, 0.05) for k in range(40)]                       # all in one half
    assert not nf.judge(ev_late, comp)["conditions"]["halves"]
    ev_down = [_o(k, 0.5 if k % 2 == 0 else 0.0, -0.05) for k in range(40)]
    assert not nf.judge(ev_down, comp)["conditions"]["median"]
    assert nf.judge(ev[:29], comp)["reason"] == "too few events"


def test_event_records_the_qualifying_print_when_two_share_a_time():
    c = flat_candles(120, start=T0)
    p = [(T0 + 10 * STEP, -0.008, 1.0), (T0 + 10 * STEP, 0.001, 1.0)]     # two prints at one time, as in the archive
    r = nf.analyse({"X": (p, c)}, nf.THRESH)
    assert [e["rate_per_hour"] for e in r["events"]] == [-0.008]
