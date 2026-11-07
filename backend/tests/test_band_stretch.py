"""band_stretch.py: the same readings as the stretch-at-tops study, the market rows, the record and the coin page."""
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


def test_the_coin_reading_uses_closed_days_and_is_cached():
    days, close = _walk(1000)
    now = float((days[-1] + 1) * 86_400 + 3600)                  # an hour into the day after the last close
    ts = list((days * 86_400_000).astype(float)) + [float((days[-1] + 1) * 86_400_000)]   # plus the forming day
    calls = []

    async def fetch(symbol, tf, limit):
        calls.append((symbol, tf, limit))
        return {"timestamp": ts, "close": list(close) + [close[-1] * 3]}       # the forming day is far off

    B._COIN_CACHE.clear()
    r = asyncio.run(B.coin_reading("ABC/USDT", now=now, fetch=fetch))
    assert r["available"] and r["day"] == int(days[-1]) and r["line"] == B.LINE
    expected = B.coin_view(days, close)
    assert r["a"] == expected["a"] and len(r["history"]) == 365
    asyncio.run(B.coin_reading("ABC/USDT", now=now + 60, fetch=fetch))
    assert len(calls) == 1                                       # cached until the next close
    asyncio.run(B.coin_reading("ABC/USDT", now=now + 86_400, fetch=fetch))
    assert len(calls) == 2


def test_the_coin_reading_without_data_retries_soon():
    async def fetch(symbol, tf, limit):
        return None
    B._COIN_CACHE.clear()
    r = asyncio.run(B.coin_reading("NONE/USDT", now=1_000_000.0, fetch=fetch))
    assert r == {"symbol": "NONE/USDT", "available": False}
    assert B._COIN_CACHE["NONE/USDT"][0] == 1_000_000.0 + 600


def test_the_market_view_reads_seed_then_live_rows(monkeypatch):
    import market_history as mh
    monkeypatch.setattr(mh, "_stretch_seed", {"rows": [[1, 50, 5, 0.1], [2, 39, 4, 0.2], [3, 50, 6, 0.3]]})
    monkeypatch.setattr(mh, "_stretch", {3: [3, 99, 9, 9.9], 4: [4, 51, 7, 0.4]})
    assert mh.stretch_rows_all() == [[1, 50, 5, 0.1], [2, 39, 4, 0.2], [3, 50, 6, 0.3], [4, 51, 7, 0.4]]
    v = mh.stretch_view({"min_coins": 40})
    assert v["line"] == B.LINE and [r[0] for r in v["rows"]] == [1, 3, 4]      # day 2 had too few coins
