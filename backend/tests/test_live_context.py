"""backtest/live_context.py: funding and stablecoin context for the replay, as the live scanner reads them."""
import math

import numpy as np

from backtest import live_context as LC
from backtest import replay_engine as RE

H = 3_600_000
DAY = 86_400_000


def test_positioning_reads_the_last_payment_before_the_close_and_divides_by_8():
    fund = np.array([[100 * DAY, 0.0001], [100 * DAY + 8 * H, 0.001], [100 * DAY + 16 * H, -0.002]])
    p = LC.positioning_at(fund, 100 * DAY + 9 * H)
    assert math.isclose(p["funding_rate"], 0.001 / 8) and p["funding_regime"] == "CROWDED_LONG"
    assert p["oi_trend"] == "UNKNOWN" and p["top_trader_lsr"] == 1.0
    assert LC.positioning_at(fund, 100 * DAY + 3 * H)["funding_regime"] == "NEUTRAL"       # 0.0001 / 8
    assert LC.positioning_at(fund, 100 * DAY + 16 * H)["funding_regime"] == "CROWDED_SHORT"  # at the close: known
    assert LC.positioning_at(fund, 100 * DAY - 1) is None                                    # before any payment
    assert LC.positioning_at(fund, 100 * DAY + 32 * H + 1) is None                           # 16 hours stale
    assert LC.positioning_at(np.zeros((0, 2)), DAY) is None


def test_stablecoin_compares_the_last_completed_day_with_a_week_before():
    caps = {10: 100.0, 17: 102.0, 18: 98.0}
    s = LC.stablecoin_at(caps, 18 * DAY)                 # a bar closing at the start of day 18: day 17 is the last
    assert s["trend"] == "EXPANDING" and math.isclose(s["change_7d_pct"], 2.0)
    assert LC.stablecoin_at(caps, 18 * DAY + 4 * H)["trend"] == "EXPANDING"
    assert LC.stablecoin_at({11: 100.0, 18: 98.0}, 19 * DAY)["trend"] == "CONTRACTING"
    assert LC.stablecoin_at(caps, 20 * DAY) is None      # day 19 unknown


def test_the_hook_marks_each_input_fresh_or_missing():
    hook = LC.make_hook(["ABC"], funding_of=lambda s: np.array([[50 * DAY, 0.0008]]), caps={42: 1.0, 49: 1.0})
    ctx, meta = hook({"symbol": "ABC/USDT"}, 50 * DAY)
    assert ctx["positioning"]["funding_regime"] == "NEUTRAL" and ctx["stablecoin"]["trend"] == "STABLE"
    assert meta["funding"]["observed_at"] == 50 * 86_400 and meta["stablecoin"]["observed_at"] == 50 * 86_400
    ctx, meta = hook({"symbol": "XYZ/USDT"}, 50 * DAY)
    assert ctx["positioning"] is None and meta["funding"]["observed_at"] is None


def test_without_a_hook_the_replay_context_is_unchanged(monkeypatch):
    monkeypatch.setattr(RE, "CONTEXT_HOOK", None)
    ctx, meta = {"consensus": {"consensus": "RISK-ON"}}, {"sentiment": {"observed_at": 1.0}}
    assert RE._with_context({}, 0, ctx, meta) == (ctx, meta)
    monkeypatch.setattr(RE, "CONTEXT_HOOK", lambda row, t: ({"stablecoin": {"trend": "STABLE"}}, {"stablecoin": {"observed_at": 2.0}}))
    c2, m2 = RE._with_context({}, 0, ctx, meta)
    assert c2["stablecoin"]["trend"] == "STABLE" and c2["consensus"] == ctx["consensus"] and m2["sentiment"] == meta["sentiment"]


def test_the_decision_keeps_fresh_funding_and_stablecoin_context():
    from decision_pipeline import input_quality, fresh_context
    ctx = {"positioning": {"funding_regime": "NEUTRAL"}, "stablecoin": {"trend": "STABLE"}}
    meta = {"funding": {"observed_at": 1000.0}, "stablecoin": {"observed_at": 1000.0}}
    kept = fresh_context(ctx, input_quality(meta, 1000.0))
    assert kept["positioning"] and kept["stablecoin"]
    dropped = fresh_context(ctx, input_quality({}, 1000.0))
    assert dropped["positioning"] is None and dropped["stablecoin"] is None
