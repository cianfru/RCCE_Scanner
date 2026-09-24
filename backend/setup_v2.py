"""Versioned closed-candle setups with precommitted, bounded next-open entry."""

import copy
import hashlib
import json
import os
import numpy as np
from candle_snapshot import closed_candles
from trading_setups import build_setups, PARAMETERS, finite

# Retrospectively selected after comparing entry, exit and filter alternatives.
# Forward outcomes remain unvalidated; this definition never submits orders.
PRODUCTION_PROFILE = dict(
    name="confirmed-breakout-v2",
    family="breakout",
    hold=12,
    target=2,
    stop_atr=2,
    cto="reference",
    macro_recovery=False,
    protection="none",
)


def build_live_setups(row, daily, candles, book, *, as_of):
    legacy = build_setups(row, daily, candles, book, as_of=as_of)
    if os.environ.get("PAPER_SETUP_V2_ENABLED", "1").lower() in ("0", "false", "off"):
        return legacy
    f = features(row, daily, candles, book, as_of)
    return candidate(row, daily, f, PRODUCTION_PROFILE, as_of) + legacy


def features(row, daily, candles, book, as_of):
    base = build_setups(row, daily, candles, book, as_of=as_of)
    if not base:
        return None
    b = base[0]
    if "atr" not in b:
        return dict(base=b, valid=False)
    data = closed_candles(candles, "4h", as_of * 1000)
    close = np.asarray(data["close"][-60:])
    high = np.asarray(data["high"][-60:])
    low = np.asarray(data["low"][-60:])
    return dict(
        base=b,
        valid=True,
        price=float(close[-1]),
        ma10=float(np.mean(close[-10:])),
        ma20=float(np.mean(close[-20:])),
        previous20high=float(max(high[-21:-1])),
        previous3high=float(max(high[-4:-1])),
        low10=float(min(low[-10:])),
        atr=b["atr"],
        pullback=b["pullback_atr"],
    )


def candidate(row, daily, f, config, as_of):
    if not f:
        return []
    b = copy.deepcopy(f["base"])
    p = dict(
        PARAMETERS,
        max_hold_bars=config["hold"],
        target_r=config["target"],
        min_reward_r=1.2,
        expiry_bars=3,
        protection=config.get("protection", "none"),
        protection_min_bars=config.get("protection_min_bars", 6),
        entry_zone_atr=config.get("zone_up", 1),
        entry_zone_below_atr=config.get("zone_down", 0.5),
        stop_atr=config.get("stop_atr", 2),
        max_stop_fraction=0.12,
    )
    version = "setups-2-" + config["name"]
    strategy = "adaptive_" + config["family"]
    identity = hashlib.sha256(
        json.dumps(
            [version, config, p, row["symbol"], b["reference_close"]], sort_keys=True
        ).encode()
    ).hexdigest()[:24]
    b.update(
        id=identity,
        version=version,
        strategy=strategy,
        parameters=p,
        configuration=copy.deepcopy(config),
        entry_mode="next_open",
        trigger_rule="Completed-candle context confirmed; commit to next future 4h opening inside price bounds",
        status="unavailable",
        reason="Required completed context unavailable",
    )
    if not f["valid"]:
        return [b]
    price, atr = f["price"], f["atr"]
    daily = daily or {}
    up = daily.get("regime") in ("MARKUP", "REACC")
    current_up = row.get("regime") in ("MARKUP", "REACC")
    family = config["family"]
    if family == "trend":
        context = up and current_up and price > f["ma20"]
        reason = "Upward 4h/daily context and close above 20-bar mean required"
    elif family == "pullback":
        context = up and current_up and 0.25 <= f["pullback"] <= 3
        reason = "Upward 4h/daily context and 0.25–3 ATR pullback required"
    elif family == "recovery":
        context = (
            daily.get("regime") in ("ACCUM", "REACC", "MARKUP")
            and row.get("regime") in ("ACCUM", "REACC", "MARKUP")
            and (row.get("floor_confirmed") or row.get("is_absorption"))
            and price > f["ma10"]
        )
        reason = "Floor or absorption evidence followed by close above 10-bar mean, with non-bearish context required"
    elif family == "breakout":
        context = up and current_up and price > f["previous20high"]
        reason = "Close above prior 20-bar high with upward 4h/daily context required"
    else:
        raise ValueError("Unknown setup family")
    context_reasons = [reason]
    cto = row.get("cto") or {}
    cto_ready = cto.get("data_quality") == "ready" and cto.get(
        "candle_close_time"
    ) == row.get("signal_bar_close_time")
    if config.get("cto") == "confirm":
        context_reasons.append("Upward CTO confirmation required")
        if context and (not cto_ready or cto.get("direction") != "up"):
            reason = "CTO is not upward; confirmation unavailable or opposed"
        context = context and cto_ready and cto.get("direction") == "up"
    elif config.get("cto") == "veto":
        context = context and cto_ready and cto.get("direction") != "down"
    if config.get("min_rel_vol"):
        volume = row.get("rel_vol")
        volume = volume if finite(volume) else 0
        context_reasons.append(
            f"Relative volume of at least {config['min_rel_vol']} required"
        )
        if context and volume < config["min_rel_vol"]:
            reason = f"Relative volume {volume:.2f} is below {config['min_rel_vol']}; breakout lacks participation"
        context = context and volume >= config["min_rel_vol"]
    macro_exception = bool(
        config.get("macro_recovery")
        and family == "breakout"
        and row.get("bmsb_valid") is True
        and row.get("signal_reason", "").startswith("Macro blocked (BMSB bearish)")
        and row.get("signal") == "WAIT"
        and not row.get("engine_errors")
    )
    stop = price - config.get("stop_atr", 2) * atr
    risk = price - stop
    b.update(
        trigger=price,
        stop=stop,
        target=price + p["target_r"] * risk,
        entry_zone=[
            price - config.get("zone_down", 0.5) * atr,
            price + config.get("zone_up", 1) * atr,
        ],
        reward_r=p["target_r"],
        context_reasons=context_reasons,
        invalidation_rule=f"Initial stop {config.get('stop_atr', 2)} ATR below confirmed close; protection changes only after completed bars",
    )
    if not context:
        b.update(status="no_setup", reason=reason)
    elif b["execution"]["status"] != "ready":
        b.update(status=b["execution"]["status"], reason=b["execution"]["reason"])
    elif (
        (row.get("entry_blocked") and not macro_exception)
        or row.get("signal") in ("TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG")
        or daily.get("signal") in ("TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG")
    ):
        b.update(
            status="blocked",
            reason="Scanner mandatory entry restriction or exit warning",
        )
    elif stop <= 0 or risk / price > 0.12:
        b.update(
            status="blocked", reason="Initial stop exceeds 12% of price or is invalid"
        )
    else:
        b.update(
            status="pending",
            reason="Completed-candle setup confirmed; await bounded next opening",
        )
    b["macro_recovery"] = macro_exception
    if macro_exception:
        b["context_reasons"].append(
            "Recovery breakout below the weekly macro filter; separate countertrend hypothesis"
        )
    return [b]
