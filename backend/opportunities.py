"""Explainable opportunity states and CTO research policies (shadow by default)."""
from __future__ import annotations

import hashlib
import json

from candle_snapshot import TF_MS

LONGS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}
ENTRIES = LONGS | {"LIGHT_SHORT"}
EXITS = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}
VARIANTS = ("baseline", "cto_ranking", "cto_confirmation", "cto_veto")
POLICY_VERSION = "cto-policy-1"


def assess_variant(row: dict, variant="baseline", confirmation_bars=1) -> dict:
    if variant not in VARIANTS or confirmation_bars not in (1, 2, 3):
        raise ValueError("Unsupported CTO policy")
    signal = row.get("baseline_signal", row.get("signal", "WAIT"))
    result = dict(variant=variant, signal=signal, rank_adjustment=0, status="confirmed" if signal in ENTRIES else "emerging",
                  reason="Baseline decision", confirmation_bars=confirmation_bars)
    if row.get("signal_status") == "unavailable":
        return dict(result, signal="WAIT", status="unavailable", reason=row.get("signal_reason", "Required data unavailable"))
    if signal in EXITS:
        return dict(result, status="risk_warning", reason="Exit warning takes precedence")
    if row.get("entry_blocked") and signal != "LIGHT_SHORT":
        return dict(result, signal="WAIT", status="blocked", reason=row.get("signal_reason", "Entry eligibility failed"))
    if variant == "baseline" or signal not in ENTRIES:
        return result
    cto = row.get("cto") or {}
    expected = "down" if signal == "LIGHT_SHORT" else "up"
    direction = cto.get("direction", "unavailable")
    available = cto.get("data_quality") == "ready" and direction != "unavailable"
    aligned = direction == expected
    opposing = direction in ("up", "down") and not aligned
    persistent = cto.get("direction_age_bars", 0) >= confirmation_bars
    if variant == "cto_ranking":
        return dict(result, rank_adjustment=10 if available and aligned and persistent else -10 if available and opposing else 0,
                    reason="CTO ranking only; eligibility unchanged" if available else "CTO unavailable; no rank bonus")
    if not available:
        return dict(result, signal="WAIT", status="unavailable", reason="CTO unavailable")
    if variant == "cto_veto":
        if opposing and persistent:
            return dict(result, signal="WAIT", status="blocked", reason="Persistent opposing CTO direction")
        return dict(result, reason="No persistent opposing CTO direction")
    if aligned and persistent:
        return dict(result, reason=f"CTO {expected} confirmed for {confirmation_bars} closed bar(s)")
    reversal = row.get("regime") in ("CAP", "ACCUM", "REACC")
    return dict(result, signal="WAIT", status="emerging" if reversal or not opposing else "blocked",
                reason=f"Await CTO {expected} for {confirmation_bars} closed bar(s)")


def build_opportunity(row: dict, previous: dict | None, *, as_of: float,
                      variant="baseline", confirmation_bars=1, ttl_bars=3) -> dict:
    """Create one stable lifecycle record; polls never reset trigger/expiry time."""
    assessment = assess_variant(row, variant, confirmation_bars)
    signal = row.get("baseline_signal", row.get("signal", "WAIT"))
    direction = "short" if signal == "LIGHT_SHORT" else "long" if signal in LONGS else None
    setup = "reversal" if row.get("regime") in ("CAP", "ACCUM", "REACC") else "continuation"
    status, reason = assessment["status"], assessment["reason"]
    close_time = row.get("signal_bar_close_time")
    candle_quality = (row.get("input_quality") or {}).get("candles", {})
    if candle_quality.get("status") == "stale":
        status, reason = "expired", "Candle snapshot is stale; await refreshed completed candles"
    if signal == "WAIT" and status == "emerging":
        reason = row.get("signal_reason") or "Await baseline entry trigger"
    structural = row.get("structure") or {}
    invalidation = structural.get("swing_high" if direction == "short" else "swing_low") if direction else None
    continuing = bool(previous and previous.get("direction") == direction and previous.get("setup_type") == setup
                      and previous.get("status") in ("confirmed", "emerging", "expired"))
    trigger_at = previous.get("trigger_at") if continuing else close_time
    invalidation = previous.get("invalidation_level", invalidation) if continuing else invalidation
    expiry = (trigger_at + ttl_bars * TF_MS.get(row.get("timeframe"), TF_MS["4h"]) / 1000) if trigger_at else None
    decision_price = row.get("decision_price")
    broken = invalidation is not None and decision_price is not None and (
        decision_price >= invalidation if direction == "short" else decision_price <= invalidation)
    if previous and previous.get("status") == "confirmed" and signal not in ENTRIES | EXITS and status != "unavailable":
        status, reason = "invalidated", "Baseline entry trigger no longer holds"
    elif broken and continuing:
        status, reason = "invalidated", "Completed candle crossed the recorded structural invalidation level"
    elif expiry and as_of > expiry and status == "confirmed":
        status, reason = "expired", "Setup age limit reached; await a new setup"
    # A failed or expired episode requires a fresh trigger, rather than resetting on each poll.
    if previous and previous.get("status") in ("expired", "invalidated") and previous.get("baseline_signal") == signal:
        status, reason = previous["status"], previous["reason"]
        trigger_at, expiry = previous.get("trigger_at"), previous.get("expires_at")
    if previous and status == "invalidated":
        direction, setup = previous.get("direction"), previous.get("setup_type")
        trigger_at, expiry = previous.get("trigger_at"), previous.get("expires_at")
        invalidation = previous.get("invalidation_level")
    basis = [row.get("symbol"), row.get("timeframe"), variant, direction, setup, trigger_at]
    identity = hashlib.sha256(json.dumps(basis).encode()).hexdigest()[:20]
    execution = row.get("execution") or {}
    # No order book/spread snapshot: avoid inventing executable prices or costs.
    feasibility = {"status": "unknown", "reason": "No fresh spread/depth snapshot",
                   "estimated_cost_bps": None}
    if execution.get("observed_at") and 0 <= as_of - execution["observed_at"] <= 60:
        feasibility = dict(execution, status="observed")
    return dict(id=identity, policy_version=POLICY_VERSION, policy=variant,
                status=status, direction=direction, setup_type=setup, reason=reason,
                baseline_signal=signal, signal=assessment["signal"], trigger_at=trigger_at,
                candle_close_time=close_time, expires_at=expiry, invalidation_level=invalidation,
                invalidation_basis="10 completed-bar price extreme" if invalidation is not None else None,
                evidence_coverage=row.get("evidence_coverage", 0), cto_state=(row.get("cto") or {}).get("state", "unavailable"),
                blockers=list(row.get("strong_long_blockers") or []), execution=feasibility,
                reassessment="New completed candle or refreshed missing inputs")


def meaningful_transition(previous: dict | None, current: dict) -> bool:
    if previous is None:
        return current["status"] in ("confirmed", "risk_warning")
    return any(previous.get(k) != current.get(k) for k in ("status", "direction", "setup_type", "signal"))


def shadow_variants(row: dict) -> dict:
    return {f"{variant}:{bars}": assess_variant(row, variant, bars)
            for variant in VARIANTS for bars in ((1, 2, 3) if variant in ("cto_confirmation", "cto_veto") else (1,))}
