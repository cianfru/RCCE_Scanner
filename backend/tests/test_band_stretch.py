"""band_stretch.py: the same readings as the stretch-at-tops study, the market rows, the record and the replay."""
import asyncio
import json
import os
import tempfile

import numpy as np

import band_stretch as B
from research import stretch_tops as T


def _walk(n=1600, seed=3):
    rng = np.random.default_rng(seed)
    days = np.arange(18000, 18000 + n)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.035, n)))
    return days, close


def test_the_readings_are_the_studys():
    days, close = _walk()
    rd = B.readings(days, close)
    m = T.measures(days, close)
    es = m["eval_start"]
    assert np.allclose(rd["mid"], T.band_mid(days, close), equal_nan=True)
    assert np.allclose(rd["a"][es:], m["A"][es:], rtol=1e-9)
    assert np.allclose(rd["c"][es:], m["C"][es:], rtol=1e-9)
    # the divergence mark, once its whole look-back lies in the study's evaluation days
    d_study = T.divergence(close, m["A"], B.GUIDE_A, es)
    for t in range(es + 365, len(close)):
        assert B.divergence_at(close, rd["a"], B.GUIDE_A, t) == bool(d_study[t])


def test_band_z_is_shown_from_180_days_of_stretch():
    days, close = _walk()
    rd = B.readings(days, close)
    first = int(np.argmax(np.isfinite(rd["mid"])))
    assert np.isnan(rd["a"][first + B.MIN_DAYS - 2]) and np.isfinite(rd["a"][first + B.MIN_DAYS - 1])


def test_on_days_reads_only_closes_up_to_the_day():
    days, close = _walk()
    d = int(days[1200])
    full = B.on_days(days, close, [d])[d]
    cut = B.on_days(days[:1201], close[:1201], [d])[d]
    assert full == cut
    assert set(full) == {"close", "mid", "pct", "a", "c", "d_a", "d_c"}


def test_daily_series_fills_a_missing_day():
    ms = lambda d: d * 86_400_000
    days, close = B.daily_series([ms(10), ms(11), ms(13)], [1.0, 2.0, 4.0])
    assert list(days) == [10, 11, 12, 13] and list(close) == [1.0, 2.0, 2.0, 4.0]


def test_the_market_row():
    per = {"X": {"a": 2.0}, "Y": {"a": 1.6}, "Z": {"a": -0.4}, "W": {"a": None}}
    assert B.aggregate(5, per) == [5, 3, 2, 1.6]
    assert B.aggregate(5, {"W": {"a": None}}) is None


def test_the_record_round_trip(monkeypatch):
    import hl_persistence as hp
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(hp, "_DB_PATH", os.path.join(d, "t.db"))
        monkeypatch.setattr(hp, "_conn", None)
        n = hp.save_band_stretch(20000, {"BTCUSDT": {"close": 1.0, "mid": 0.9, "a": 1.2, "c": 8.0, "d_a": False,
                                                     "d_c": None}})
        assert n == 1
        assert hp.load_band_stretch(20000) == [("BTCUSDT", 1.0, 0.9, 1.2, 8.0, 0, None)]
        hp.save_band_stretch(20000, {"BTCUSDT": {"close": 1.1, "mid": 0.9, "a": 1.3, "c": 8.1, "d_a": True, "d_c": True}})
        assert hp.load_band_stretch(20000)[0][1:] == (1.1, 0.9, 1.3, 8.1, 1, 1)
        hp._conn.close()
        monkeypatch.setattr(hp, "_conn", None)


def test_the_market_view_reads_seed_then_live_rows(monkeypatch):
    import market_history as mh
    monkeypatch.setattr(mh, "_stretch_seed", {"rows": [[1, 50, 5, 0.1], [2, 39, 4, 0.2], [3, 50, 6, 0.3]]})
    monkeypatch.setattr(mh, "_stretch", {3: [3, 99, 9, 9.9], 4: [4, 51, 7, 0.4]})
    assert mh.stretch_rows_all() == [[1, 50, 5, 0.1], [2, 39, 4, 0.2], [3, 50, 6, 0.3], [4, 51, 7, 0.4]]
    v = mh.stretch_view({"min_coins": 40})
    assert v["line"] == B.LINE and [r[0] for r in v["rows"]] == [1, 3, 4]      # day 2 had too few coins


def test_band_z_at_a_bar_is_the_band_with_the_bars_price_over_the_days_before():
    rng = np.random.default_rng(9)
    days = np.arange(19000, 19000 + 900)
    close = 50 * np.exp(np.cumsum(rng.normal(0.0004, 0.04, len(days))))
    st = B.bar_state(days, close)
    for i in (400, 401, 405, 600, 899):
        price = close[i] * 1.013
        c2 = close[: i + 1].copy(); c2[i] = price
        mid = B.band_mid(days[: i + 1], c2)[i]
        s = np.log(close[:i] / B.band_mid(days[:i], close[:i]))
        s = s[np.isfinite(s)][-730:]
        expected = np.log(price / mid) / np.sqrt(np.mean(s * s))
        assert abs(B.band_z_at(st, int(days[i]), price) - expected) < 1e-12
    assert B.band_z_at(st, int(days[100]), close[100]) is None          # no band yet
    assert B.band_z_at(st, int(days[-1]) + 1, close[-1]) is None        # outside the series
    # at the day's own close, band z over the days before matches the readings but for the RMS's last day
    i = 700
    a = B.readings(days, close)["a"][i]
    assert abs(B.band_z_at(st, int(days[i]), close[i]) / a - 1) < 0.02


def test_the_replay_switch_sets_the_exit_and_gives_rows_their_band_z(monkeypatch):
    import signal_synthesizer as ss
    import backtest.replay_engine as re_mod
    from backtest import live_logic_replay as lr
    days, close = _walk(900)

    class FakeBH:
        def load(self, pair, tf, start, end):
            assert tf == "1d" and start == "2017-01-01"
            return {"timestamp": days * 86_400_000.0, "close": close} if pair == "ABCUSDT" else None

    monkeypatch.setattr(ss, "TOP_EXIT", "heat")
    monkeypatch.setattr(re_mod, "BAR_HOOK", None)
    lr._band_exit(FakeBH(), ["ABC", "XYZ"])
    assert ss.TOP_EXIT == "band" and re_mod.BAR_HOOK is not None
    row = {"symbol": "ABC/USDT", "decision_price": float(close[700])}
    close_ms = int(days[700] + 1) * 86_400_000                         # the bar closing at the end of day 700
    re_mod.BAR_HOOK(row, close_ms)
    st = B.bar_state(days, close)
    assert row["band_z"] == B.band_z_at(st, int(days[700]), float(close[700]))
    other = {"symbol": "XYZ/USDT", "decision_price": 1.0}
    re_mod.BAR_HOOK(other, close_ms)
    assert other["band_z"] is None
