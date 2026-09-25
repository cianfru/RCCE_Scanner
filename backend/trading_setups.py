"""Versioned research hypotheses. These definitions never place exchange orders."""

from __future__ import annotations
import hashlib
import json
import math
import numpy as np
from candle_snapshot import closed_candles, TF_MS

VERSION = "setups-1"
UNIVERSE = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
STRATEGIES = ("continuation_pullback", "confirmed_reversal", "trend_comparator")
PARAMETERS = dict(
    expiry_bars=3,
    max_hold_bars=12,
    target_r=2.0,
    min_reward_r=1.5,
    stop_atr_buffer=0.1,
    entry_zone_atr=0.25,
    min_risk_atr=0.5,
    max_risk_atr=4.0,
    fee_bps=5.0,
    slippage_bps=5.0,
    max_spread_bps=10.0,
    paper_notional_usd=1000.0,
    min_depth_multiple=10.0,
    max_book_age_seconds=60.0,
)
TF_SECONDS = TF_MS["4h"] / 1000


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def execution_quality(book, *, as_of, params=None):
    p = params or PARAMETERS
    if (
        not book
        or not finite(book.get("observed_at"))
        or not 0 <= as_of - book["observed_at"] <= p["max_book_age_seconds"]
    ):
        return dict(
            status="unavailable",
            reason="Fresh order book required",
            source="hyperliquid",
        )
    bid, ask = book.get("bid"), book.get("ask")
    if not all(finite(v) and v > 0 for v in (bid, ask)) or bid > ask:
        return dict(
            status="unavailable",
            reason="Invalid or crossed order book",
            source="hyperliquid",
        )
    spread = (ask - bid) / ((ask + bid) / 2) * 10000
    depth = min(book.get("bid_depth_usd", 0), book.get("ask_depth_usd", 0))
    passed = (
        finite(depth)
        and spread <= p["max_spread_bps"]
        and depth >= p["paper_notional_usd"] * p["min_depth_multiple"]
    )
    return dict(
        book,
        spread_bps=spread,
        status="ready" if passed else "blocked",
        reason="Observed spread/depth pass research limits"
        if passed
        else "Spread too wide or insufficient depth within 10 bps",
        assumed_fee_bps=p["fee_bps"],
        assumed_slippage_bps=p["slippage_bps"],
        paper_notional_usd=p["paper_notional_usd"],
        source="hyperliquid",
    )


def build_setups(row, daily, candles, book, *, as_of):
    """One immutable first-observed definition per strategy and completed candle."""
    data = closed_candles(candles, "4h", as_of * 1000) if candles is not None else None
    execution = execution_quality(book, as_of=as_of)
    problems = []
    if row.get("symbol") not in UNIVERSE or row.get("timeframe") != "4h":
        return []
    if row.get("signal_status") == "unavailable" or row.get("engine_errors"):
        problems.append("Scanner decision unavailable")
    close_at = row.get("signal_bar_close_time")
    if not finite(close_at) or not 0 <= as_of - close_at <= TF_SECONDS + 300:
        problems.append("Fresh completed 4h decision required")
    d_close = (daily or {}).get("signal_bar_close_time")
    if (
        not daily
        or daily.get("signal_status") == "unavailable"
        or not finite(d_close)
        or not 0 <= as_of - d_close <= 86400 + 300
    ):
        problems.append("Fresh completed daily context required")
    valid_data = data is not None and len(data.get("close", [])) >= 50
    if valid_data:
        data = {k: np.asarray(v[-60:], dtype=float) for k, v in data.items()}
        valid_data = all(
            np.isfinite(data[k]).all()
            for k in ("timestamp", "open", "high", "low", "close")
        )
        valid_data = (
            valid_data
            and np.all(np.diff(data["timestamp"]) == TF_MS["4h"])
            and np.all(data["low"] > 0)
        )
        valid_data = (
            valid_data
            and np.all(data["low"] <= np.minimum(data["open"], data["close"]))
            and np.all(data["high"] >= np.maximum(data["open"], data["close"]))
        )
        valid_data = (
            valid_data and (data["timestamp"][-1] + TF_MS["4h"]) / 1000 == close_at
        )
    if not valid_data:
        problems.append("Matching contiguous Hyperliquid candles required")
    if (
        valid_data
        and finite(row.get("decision_price"))
        and not math.isclose(
            float(data["close"][-1]), row["decision_price"], rel_tol=1e-8
        )
    ):
        problems.append(
            "Scanner and execution-venue candle revisions differ; await matching snapshot"
        )
    output = []
    for strategy in STRATEGIES:
        identity = hashlib.sha256(
            json.dumps(
                [VERSION, PARAMETERS, row["symbol"], strategy, close_at], sort_keys=True
            ).encode()
        ).hexdigest()[:24]
        contract = dict(
            id=identity,
            version=VERSION,
            strategy=strategy,
            symbol=row["symbol"],
            timeframe="4h",
            direction="long",
            observed_at=as_of,
            reference_close=close_at,
            regime=row.get("regime"),
            daily_regime=(daily or {}).get("regime"),
            validation_status="unvalidated",
            mode="paper",
            parameters=dict(PARAMETERS),
            decision_input_id=row.get("decision_input_id"),
            baseline_signal=row.get("baseline_signal", row.get("signal")),
            cto_reference=row.get("cto"),
            execution=execution,
            context_reasons=[],
            status="unavailable",
            reason="; ".join(problems),
            trigger=None,
            stop=None,
            target=None,
            expires_at=as_of + PARAMETERS["expiry_bars"] * TF_SECONDS,
            trigger_rule="Future completed 4h close above the frozen trigger; entry at a subsequent precommitted open",
        )
        if problems:
            output.append(contract)
            continue
        close, high, low = data["close"], data["high"], data["low"]
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])),
        )
        atr = float(np.mean(tr[-14:]))
        if atr <= 0:
            contract["reason"] = "Positive ATR required"
            output.append(contract)
            continue
        price = float(close[-1])
        regime = row.get("regime")
        daily_regime = daily.get("regime")
        pullback = (float(max(close[-20:-1])) - price) / atr
        if strategy == "continuation_pullback":
            context = (
                regime in ("MARKUP", "REACC")
                and daily_regime in ("MARKUP", "REACC")
                and 0.5 <= pullback <= 3
            )
            context_reason = "4h/daily upward context and a 0.5–3 ATR pullback required"
        elif strategy == "confirmed_reversal":
            context = (
                regime in ("CAP", "ACCUM", "REACC")
                and daily_regime in ("ACCUM", "REACC", "MARKUP")
                and bool(row.get("floor_confirmed"))
                and bool(row.get("is_absorption"))
            )
            context_reason = "Confirmed floor plus absorption, with non-bearish daily context required"
        else:
            context = price > float(np.mean(close[-20:])) and daily_regime in (
                "MARKUP",
                "REACC",
            )
            context_reason = (
                "Price above 20-bar average and upward daily context required"
            )
        contract["context_reasons"] = [context_reason]
        trigger = float(max(high[-3:])) if strategy != "trend_comparator" else price
        stop = (
            float(min(low[-10:])) - PARAMETERS["stop_atr_buffer"] * atr
            if strategy != "trend_comparator"
            else price - 2 * atr
        )
        risk = trigger - stop
        target = trigger + PARAMETERS["target_r"] * risk
        resistance = float(max(high[-50:-3]))
        if resistance > trigger and strategy != "trend_comparator":
            target = min(target, resistance - PARAMETERS["stop_atr_buffer"] * atr)
        reward_r = (target - trigger) / risk if risk > 0 else 0
        contract.update(
            atr=atr,
            trigger=trigger,
            stop=stop,
            target=target,
            entry_zone=[trigger, trigger + PARAMETERS["entry_zone_atr"] * atr],
            reward_r=reward_r,
            pullback_atr=pullback,
            invalidation_rule="Paper stop at frozen 10-bar low minus 0.1 ATR"
            if strategy != "trend_comparator"
            else "Paper stop 2 ATR below reference price",
        )
        if not context:
            contract.update(status="no_setup", reason=context_reason)
        elif execution["status"] != "ready":
            contract.update(status=execution["status"], reason=execution["reason"])
        elif (
            not PARAMETERS["min_risk_atr"] * atr
            <= risk
            <= PARAMETERS["max_risk_atr"] * atr
            or stop <= 0
        ):
            contract.update(
                status="blocked",
                reason="Stop distance outside 0.5–4 ATR research bounds",
            )
        elif reward_r < PARAMETERS["min_reward_r"]:
            contract.update(
                status="blocked",
                reason="Insufficient room before recorded resistance (minimum 1.5R)",
            )
        elif (
            row.get("entry_blocked")
            or row.get("signal") in ("TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG")
            or daily.get("signal") in ("TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG")
        ):
            contract.update(
                status="blocked",
                reason="Scanner mandatory entry restriction or exit warning",
            )
        else:
            contract.update(
                status="pending",
                reason="Context eligible; await future completed-candle trigger",
            )
        output.append(contract)
    return output
