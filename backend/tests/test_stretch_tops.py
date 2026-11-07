"""The stretch-at-tops study's rules on made-up data (docs/reviews/stretch-tops-study.md)."""
import numpy as np

from engines.heatmap_engine import _ema, _sma
from research import stretch_tops as T


def test_the_split_leaves_out_the_seen_coins_and_alternates_alphabetically():
    cal, test = T.split()
    assert len(cal) == 19 and len(test) == 19 and not set(cal) & set(test)
    assert "BTC" not in cal + test and "ETH" not in cal + test
    assert cal[:3] == ["ADA", "ATOM", "BCH"] and test[:3] == ["ALGO", "AVAX", "BNB"]


def test_a_coin_with_a_long_halt_is_left_out(monkeypatch):
    days = np.arange(100)
    fake = {"A1": {"filled": 0}, "B2": {"filled": T.MAX_FILLED + 1}}
    monkeypatch.setattr(T, "PRIMARY", ["A1", "B2"]); monkeypatch.setattr(T, "SECONDARY", [])
    monkeypatch.setattr(T, "fetch", lambda c: {**fake[c], "coin": c, "days": days, "close": np.ones(100)})
    assert list(T.load_all()) == ["A1"] and list(T.load_all(keep_all=True)) == ["A1", "B2"]


def test_missing_days_take_the_close_before():
    days, close, filled = T.on_grid([10, 11, 13], [1.0, 2.0, 4.0])
    assert list(days) == [10, 11, 12, 13] and list(close) == [1.0, 2.0, 2.0, 4.0] and filled == 1


def test_the_band_is_the_engines_on_thursday_weeks_with_the_week_under_way():
    rng = np.random.default_rng(1)
    days = np.arange(7 * 3 + 2, 7 * 3 + 2 + 400)                  # starts on a Saturday
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, len(days))))
    mid = T.band_mid(days, close)
    for i in (150, 151, 152, 260, 399):
        wk = days[: i + 1] // 7
        weekly = [close[np.flatnonzero(wk == w)[-1]] for w in np.unique(wk)]      # the last close of each week
        weekly[-1] = close[i]                                     # the week under way at the day's close
        w = np.array(weekly)
        expected = (_sma(w, 20)[-1] + _ema(w, 21)[-1]) / 2
        if np.isnan(expected):
            assert np.isnan(mid[i])
        else:
            assert abs(mid[i] / expected - 1) < 1e-12
    assert np.isnan(mid[100])                                     # fewer than 21 weeks


def test_the_scalings_read_a_steady_stretch_and_volatility():
    days = np.arange(2000)
    close = np.exp(0.002 * days)                                  # a steady climb: a steady stretch over the band
    m = T.measures(days, close)
    es = m["eval_start"]
    assert es is not None
    # today's stretch is the usual one (it wobbles a little within each week as the week under way moves)
    assert abs(m["A"][-1] - 1.0) < 0.05 and abs(m["B"][-1] - 1.0) < 0.05
    assert np.isnan(m["C"][-1]) or m["C"][-1] > 0                 # no volatility at all: C is undefined, not 0
    # evaluation begins once a year of stretch exists
    first_s = int(np.argmax(np.isfinite(m["stretch"])))
    assert es == first_s + T.MIN_HISTORY - 1


def test_a_top_is_a_180_day_high_followed_by_a_40_percent_fall_before_a_new_high():
    base = [50.0] * 200
    close = np.array(base + [100.0, 95.0, 101.0, 80.0, 60.0, 59.0] + [55.0] * 30)
    assert T.tops(close) == [202]                                 # 100 is overtaken by 101; 101 falls to 59 (-41.6%)
    close2 = np.array(base + [100.0] + [70.0] * 400)              # a 30% fall only
    assert T.tops(close2) == []
    close3 = np.array([100.0] + [50.0] * 300)                     # no 180 days of data before it
    assert T.tops(close3) == []
    close4 = np.array(base + [100.0, 100.0, 50.0])                # a later equal close takes it over
    assert T.tops(close4) == [201]
    slow = np.array(base + [100.0] + list(np.linspace(99, 70, 365)) + [50.0])   # 50% only after 366 days
    assert T.tops(slow) == []


def test_hits_episodes_and_precision():
    n = 1000
    alarm = np.zeros(n, dtype=bool)
    alarm[[100, 103, 111, 300]] = True                            # 100-103-111: one episode (gaps 2 and 7); 300 alone
    eps = T.episodes(alarm)
    assert eps == [(100, 111), (300, 300)]
    s = T.score_coin(alarm, top_days=[126, 500], eval_start=0)
    assert s["hits"] == 0                                         # the window 112..126 holds no alarm
    s = T.score_coin(alarm, top_days=[120, 500], eval_start=0)
    assert s["hits"] == 1 and s["tops"] == 2                      # 106..120 holds 111
    assert s["episodes"] == 2 and s["at_top"] == 1                # 120 <= 111 + 14
    late = np.zeros(n, dtype=bool)
    late[n - 300] = True                                          # ends too close to the last close to count
    assert T.score_coin(late, [], 0)["episodes"] == 0
    s = T.score_coin(alarm, top_days=[], eval_start=0, all_tops=[305])
    assert s["at_top"] == 1                                       # a top not counted for hits still marks an episode


def test_guides_are_the_pooled_95th_percentile_of_the_calibration_days():
    a = {"A": np.arange(100.0), "B": np.arange(100.0), "C": np.arange(100.0), "E": np.arange(100.0), "eval_start": 0}
    b = {k: (v + 100 if k != "eval_start" else 50) for k, v in a.items()}
    g = T.guides({"x": a, "y": b})
    vals = np.concatenate([np.arange(100.0), np.arange(150.0, 200.0)])
    assert g["A"] == float(np.quantile(vals, 0.95))


def test_the_divergence_mark():
    n = 800
    close = np.linspace(1, 2, n)                                  # every day a new closing high
    x = np.full(n, 0.5)
    x[500] = 3.0                                                  # an earlier stretched day
    d = T.divergence(close, x, guide=2.0, eval_start=0)
    assert d[530] and d[799]                                      # 30 or more days after it, reading 0.5 < 3.0
    assert not d[529]                                             # within 30 days of it
    assert not d[400]                                             # before it
    longer = np.linspace(1, 2, 900)
    xl = np.full(900, 0.5); xl[500] = 3.0
    dl = T.divergence(longer, xl, guide=2.0, eval_start=0)
    assert dl[865] and not dl[866]                                # 365 days back at most
    x2 = x.copy(); x2[600] = 3.5                                  # today's reading above the earlier peak: no mark
    assert not T.divergence(close, x2, guide=2.0, eval_start=0)[600]
    flat = close.copy(); flat[700] = flat[699] * 0.9              # not a new high
    assert not T.divergence(flat, x, guide=2.0, eval_start=0)[700]
    neg = x.copy(); neg[650] = -0.2                               # under the band
    assert not T.divergence(close, neg, guide=2.0, eval_start=0)[650]


def test_the_bars():
    base = {"tops": 30, "hits": 15, "hit_rate": 0.5, "precision": 0.4, "alarm_days": 100}
    better = {"tops": 30, "hits": 18, "hit_rate": 0.6, "precision": 0.36, "alarm_days": 120}
    assert T.beats(better, base)["met"]
    assert not T.beats({**better, "precision": 0.34}, base)["met"]           # precision 6 points under
    assert not T.beats({**better, "hit_rate": 0.59}, base)["met"]            # 9 points only
    assert not T.beats({**better, "tops": 24}, base)["met"]
    assert not T.beats({**better, "alarm_days": 151}, base, alarms_cap=1.5)["met"]
    v = T.scale_verdict({"A": base, "B": better, "C": {**better, "hit_rate": 0.6}})
    assert v["scale"] == "B"                                                  # a tie goes to B
    v = T.scale_verdict({"A": base, "B": better, "C": {**better, "hit_rate": 0.7}})
    assert v["scale"] == "C"
    v = T.scale_verdict({"A": base, "B": base, "C": base})
    assert v["scale"] == "A"
    v = T.scale_verdict({"A": base, "B": {**better, "alarm_days": 126}, "C": base})
    assert v["scale"] == "A"                                                  # more than 1.25 times A's alarm days
