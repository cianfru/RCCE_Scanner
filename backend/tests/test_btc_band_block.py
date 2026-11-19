"""The BTC weekly-band entry block: the same rule as the backtest's, and the executor skips entries while it is on."""
import asyncio

import numpy as np
import pytest

import btc_band_block as bb
import executor as executor_mod
from backtest.larsson_study import _compute_bmsb_filter

DAY = 86_400


def daily_series(weekly_closes, first_monday=20003):        # 20003 = Monday 7 October 2024
    """Daily candles (open time in s) whose Sunday closes are `weekly_closes`; other days at the same level."""
    ts, cs = [], []
    for w, c in enumerate(weekly_closes):
        for k in range(7):
            ts.append((first_monday + 7 * w + k) * DAY)
            cs.append(c)
    return ts, cs


def test_weeks_run_monday_to_sunday():
    ts, cs = daily_series([1.0, 2.0])
    wk = bb.weekly_closes(ts, cs)
    assert [d % 7 for d, _ in wk] == [bb.SUNDAY, bb.SUNDAY] and [c for _, c in wk] == [1.0, 2.0]


def test_state_matches_the_backtest_filter():
    rng = np.random.default_rng(4)
    closes = list(np.exp(np.cumsum(rng.normal(0, 0.06, 120))) * 30000)
    weeks = [(20003 + 7 * i + 6, c) for i, c in enumerate(closes)]
    ref = _compute_bmsb_filter({"close": np.array(closes), "timestamp": np.array([float(d) for d, _ in weeks])})
    for n in range(21, len(weeks) + 1):
        assert bb.state(weeks[:n])["blocked"] == ref[float(weeks[n - 1][0])], n


def test_two_weeks_under_the_mid_block():
    up = [100.0 * 1.01 ** i for i in range(40)]
    assert bb.state([(i, c) for i, c in enumerate(up)])["blocked"] is False
    one = up + [50.0]
    s1 = bb.state([(i, c) for i, c in enumerate(one)])
    assert s1["weeks_below"] == 1 and not s1["blocked"]
    s2 = bb.state([(i, c) for i, c in enumerate(one + [50.0])])
    assert s2["weeks_below"] == 2 and s2["blocked"] and s2["since"] == 40
    assert bb.state([(i, 1.0) for i in range(10)]) is None


class Store:
    def __init__(self, ts, cs):
        self.ts, self.cs = ts, cs

    def get(self, sym, tf):
        return {"timestamp": np.array(self.ts, dtype=float) * 1000, "close": np.array(self.cs)} if sym.startswith("BTC") and tf == "1d" else None


def test_current_reads_completed_days_only():
    bb._cache.clear()
    up = [100.0 * 1.01 ** i for i in range(40)]
    ts, cs = daily_series(up + [50.0, 50.0])
    now = ts[-1] + DAY + 60                                  # the last Sunday has closed
    assert bb.blocked(Store(ts, cs), now) is True
    bb._cache.clear()
    assert bb.blocked(Store(ts, cs), ts[-1] + 60) is False   # the last Sunday still open: one week under
    bb._cache.clear()
    assert bb.blocked(Store([], []), now) is False           # no data: off


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    monkeypatch.setattr(executor_mod, "_STATE_FILE", tmp_path / "executor_state.json")


def test_executor_skips_entries_while_blocked(state_file, monkeypatch):
    from trading_engine import PaperEngine
    ex = executor_mod.Executor(mode="paper")
    ex.engine = PaperEngine(10000)
    ex.pair_map = {"SOL/USDT": "SOL"}
    ex.whitelist = ["SOL/USDT"] + [f"X{i}/USDT" for i in range(9)]
    ex.enabled = ex.initialized = True
    ex.reference_provider = lambda symbol: {"SOL": 150.0}
    monkeypatch.setattr(executor_mod.btc_band_block, "blocked", lambda *a, **k: True)
    row = dict(symbol="SOL/USDT", signal="STRONG_LONG", price=150.0, confluence={"label": "STRONG"})
    asyncio.run(ex.process_scan_results([row]))
    assert "SOL/USDT" not in ex.positions
    monkeypatch.setattr(executor_mod.btc_band_block, "blocked", lambda *a, **k: False)
    asyncio.run(ex.process_scan_results([row]))
    assert "SOL/USDT" in ex.positions


def test_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(bb, "current", lambda *a, **k: {"blocked": True, "weeks_below": 2, "mid": 1.0, "close": 0.5, "week": 1, "since": 0})
    body = TestClient(main.app).get("/api/btc-band").json()
    assert body["on"] is True and body["available"] and body["blocked"] and body["weeks_below"] == 2
