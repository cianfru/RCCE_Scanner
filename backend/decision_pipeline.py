"""Deterministic decision evaluation for live scans and recorded replay.

No network, wall-clock reads or persistence in evaluate_decision. Callers supply
the observation time, context snapshots and per-run state explicitly.
"""
from __future__ import annotations

import copy
import logging
import math
import time
from engines.positioning_engine import interpret_oi_context
from types import SimpleNamespace

from agent_layer import process as apply_agent
from candle_snapshot import TF_MS
from signal_synthesizer import synthesize_signal, compute_signal_score, enforce_signal_constraints

VERSION = "decision-2"
logger = logging.getLogger("scanner")
MAX_AGE = {"funding": 1800, "cvd": 1800, "coinglass": 1800, "hyperlens": 1800,
           "global_metrics": 1800, "macro": 86400, "sentiment": 129600, "stablecoin": 129600}


def new_state():
    return SimpleNamespace(signal_first_seen_at={}, signal_first_seen_label={},
                           prev_regime_by_tf={}, regime_change_log={})


def input_quality(metadata: dict, as_of: float) -> dict:
    quality = {}
    for name, ttl in MAX_AGE.items():
        item = metadata.get(name) or {}
        observed = item.get("observed_at")
        age = as_of - observed if isinstance(observed, (int, float)) and math.isfinite(observed) and observed > 0 else None
        status = "missing" if age is None else "future" if age < 0 else "stale" if age > ttl else "ready"
        quality[name] = dict(source=item.get("source"), observed_at=observed,
                             age_seconds=age, max_age_seconds=ttl, status=status)
    return quality


def fresh_context(context: dict, quality: dict) -> dict:
    context = copy.deepcopy(context)
    if quality["global_metrics"]["status"] != "ready":
        context["global_metrics"] = None
    if quality["funding"]["status"] != "ready":
        context["positioning"] = None
    for name in ("sentiment", "stablecoin"):
        if quality[name]["status"] != "ready":
            context[name] = None
    if quality["cvd"]["status"] != "ready":
        context.update(cvd_trend="UNAVAILABLE", cvd_divergence=False, spot_dominance="UNAVAILABLE")
    if quality["coinglass"]["status"] != "ready":
        context.update(has_coinglass=False, long_short_ratio=1.0, liquidation_24h_usd=0.0)
        if context.get("positioning"):
            pos = context["positioning"]
            pos.update(top_trader_lsr=1.0, long_short_ratio=1.0, liquidation_24h_usd=0.0,
                       spot_dominance="UNAVAILABLE", spot_futures_ratio=0.0)
            if pos.get("source_map", {}).get("oi_trend") == "coinglass":
                pos.update(oi_trend="UNKNOWN", oi_change_pct=0.0)
        context["spot_dominance"] = "UNAVAILABLE"
    if quality["macro"]["status"] != "ready":
        context.update(etf_flow_usd=0.0, cb_premium=0.0)
    if quality["hyperlens"]["status"] != "ready":
        context.update(has_hyperlens=False, hl_consensus_trend="NEUTRAL",
                       hl_consensus_confidence=0.0, hl_consensus_net_ratio=0.0)
    return context


def evaluate_decision(row: dict, context: dict, state, *, as_of: float,
                      metadata: dict | None = None, positions=(), synthesizer=synthesize_signal) -> dict:
    """Mutate one engine snapshot into a final, auditable baseline decision."""
    row["decision_state"] = capture_state(state, row.get("symbol"), row.get("timeframe"))
    row["decision_anomalies"] = copy.deepcopy([a for a in getattr(state, "anomalies", []) if a.get("symbol") == row.get("symbol")])
    row["decision_positions"] = [copy.deepcopy(p if isinstance(p, dict) else vars(p)) for p in positions]
    engine_fields = ("symbol", "timeframe", "regime", "raw_signal", "confidence", "zscore", "heat", "heat_phase",
                     "heat_direction", "bmsb_valid", "bmsb_mid", "previous_heat", "vol_state", "vol_scale",
                     "is_climax", "is_absorption", "floor_confirmed", "exhaustion_state", "divergence",
                     "signal_bar_close_time", "decision_input_id", "decision_price", "price", "cto", "structure", "engine_errors",
                     "confluence", "momentum", "rel_vol", "asset_class", "normalization_ready", "buy_sell_ratio", "vpin")
    row["decision_input"] = {key: copy.deepcopy(row[key]) for key in engine_fields if key in row}
    row["decision_context"] = copy.deepcopy(context)
    row["input_metadata"] = copy.deepcopy(metadata or {})
    row["decision_version"] = VERSION
    row["evaluated_at"] = as_of
    quality = input_quality(metadata or {}, as_of)
    row["input_quality"] = quality
    context = fresh_context(context, quality)
    row["positioning"] = context.get("positioning")
    row["cvd_trend"] = context.get("cvd_trend", "UNAVAILABLE")
    if quality["cvd"]["status"] != "ready":
        row.update(buy_sell_ratio=1.0, vpin=None)
    key = f"{row.get('symbol')}:{row.get('timeframe')}"
    for name in ("prev_regime_by_tf", "regime_change_log", "signal_first_seen_at", "signal_first_seen_label"):
        if not hasattr(state, name):
            setattr(state, name, {})
    if not hasattr(state, "regime_bar_baselines"):
        state.regime_bar_baselines = {}
    bar = row.get("signal_bar_close_time")
    baseline = state.regime_bar_baselines.get(key)
    if baseline and baseline["bar"] == bar:
        state.prev_regime_by_tf[key] = baseline["regime"]
        state.regime_change_log[key] = list(baseline["changes"])
    else:
        state.regime_bar_baselines[key] = {"bar": bar, "regime": state.prev_regime_by_tf.get(key),
                                           "changes": list(state.regime_change_log.get(key, []))}
    regime = row.get("regime", "FLAT")
    changes = [t for t in state.regime_change_log.get(key, []) if as_of - 7 * 86400 <= t <= as_of]
    if state.prev_regime_by_tf.get(key) not in (None, regime):
        changes.append(as_of)
    state.regime_change_log[key] = changes
    state.prev_regime_by_tf[key] = regime
    row.update(regime_changes_7d=len(changes), regime_unstable=len(changes) >= 3)

    close_time = row.get("signal_bar_close_time")
    # One bar plus a 20-minute grace: the drip refreshes every market after each
    # close (scan_schedule), which takes several minutes across the universe.
    ttl = TF_MS.get(row.get("timeframe"), TF_MS["4h"]) / 1000 + 1200
    candle_age = as_of - close_time if isinstance(close_time, (int, float)) and math.isfinite(close_time) else None
    candle_status = "missing" if candle_age is None else "future" if candle_age < 0 else "stale" if candle_age > ttl else "ready"
    quality["candles"] = dict(source="market_candles", observed_at=close_time, age_seconds=candle_age,
                              max_age_seconds=ttl, status=candle_status)
    try:
        synth = synthesizer(row, **context)
    except Exception as exc:
        synth = exc
    apply_synthesis_result(row, synth)
    if candle_status != "ready":
        row.update(signal="WAIT", entry_blocked=True, signal_status="unavailable",
                   signal_reason=f"Candle snapshot {candle_status}; new entries unavailable")

    # Historical replay and live evaluation run exactly the same agent filters.
    if row.get("signal_status") != "unavailable":
        saved_anomalies = getattr(state, "anomalies", [])
        state.anomalies = [a for a in saved_anomalies if isinstance(a.get("timestamp"), (int, float))
                           and 0 <= as_of - a["timestamp"] <= 1800
                           and (a.get("anomaly_type") != "EXTREME_FUNDING" or quality["funding"]["status"] == "ready")]
        try:
            agent = apply_agent(row, list(positions), state)
            row["signal"] = agent.adjusted_signal
            row["signal_warnings"] += agent.alerts
            if agent.adjusted_signal != agent.original_signal:
                row["signal_reason"] += f" [agent: {agent.reasoning}]"
        except Exception as exc:
            apply_synthesis_result(row, exc)
        finally:
            state.anomalies = saved_anomalies
    for name in ("confidence_history", "funding_history", "oi_history", "oi_change_history",
                 "lsr_history", "bsr_history", "spot_ratio_history", "vpin_history"):
        row[name] = list(getattr(state, name, {}).get(key, []))
    condition_sources = {"funding_ok": "funding", "not_greedy": "sentiment", "liquidity_ok": "stablecoin",
                         "oi_confirms": "funding", "cvd_confirms": "cvd", "smart_money_ok": "coinglass",
                         "macro_tailwind": "macro", "hl_whale_aligned": "hyperlens", "hl_not_counter": "hyperlens"}
    for condition in row.get("conditions_detail", []):
        source_key = condition_sources.get(condition["name"], "candles")
        if condition["name"] == "oi_confirms" and (context.get("positioning") or {}).get("source_map", {}).get("oi_trend") == "coinglass":
            source_key = "coinglass"
        item = quality[source_key]
        condition.update(source=item["source"], observed_at=item["observed_at"], freshness=item["status"])
    row["baseline_signal"] = row["signal"]
    from opportunities import shadow_variants
    row["cto_shadow"] = shadow_variants(row)
    from cto_policy import active_policy
    from opportunities import assess_variant
    policy, mode, evidence, scope = active_policy()
    if mode == "validated" and (row.get("symbol") not in scope.get("symbols", []) or row.get("timeframe") != scope.get("timeframe")):
        policy, mode = ("baseline", 1), "shadow"
    row.update(cto_mode=mode, cto_policy=list(policy), cto_policy_evidence=evidence, cto_rank_adjustment=0)
    if mode == "validated":
        assessment = assess_variant(row, *policy)
        row["signal"] = assessment["signal"]
        row["cto_rank_adjustment"] = assessment["rank_adjustment"]
        row["signal_reason"] += " [CTO: " + assessment["reason"] + "]"
    finalize_signal(row, state, as_of=as_of)
    return row


def apply_synthesis_result(result: dict, synth) -> None:
    """Use the same fail-closed output in every scanner path."""
    result.update(agent_signal=None, agent_warnings=[], agent_filters_fired=[])
    if isinstance(synth, Exception) or result.get("engine_errors"):
        logger.error("Signal unavailable for %s: %s", result.get("symbol"),
                     synth if isinstance(synth, Exception) else result["engine_errors"])
        result.update(signal="WAIT", signal_status="unavailable",
                      signal_reason="Signal computation unavailable — entries suppressed",
                      signal_warnings=["Signal pipeline failed"], conditions_detail=[],
                      conditions_met=0, conditions_total=9, effective_conditions=0.0,
                      weighted_total=9.0, evidence_coverage=0.0, signal_confidence=0,
                      signal_score=0, entry_blocked=True, strong_long_blockers=[], unified_signal="WAIT")
        return
    result.update(signal=synth.signal, signal_status="ready", signal_reason=synth.reason,
                  signal_warnings=synth.warnings, conditions_detail=synth.conditions_detail,
                  conditions_met=synth.conditions_met, conditions_total=synth.conditions_total,
                  effective_conditions=synth.effective_conditions, weighted_total=synth.weighted_total,
                  evidence_coverage=synth.evidence_coverage, vol_scale=synth.vol_scale,
                  strong_long_blockers=synth.strong_long_blockers, entry_blocked=synth.entry_blocked)
    result["signal_confidence"] = round(synth.conditions_met / synth.conditions_total * 100) if synth.conditions_total else 0


def finalize_signal(result: dict, scan_cache, *, as_of=None) -> None:
    """Label, score and age must all describe the post-filter decision."""
    as_of = time.time() if as_of is None else as_of
    original = result.get("signal", "WAIT")
    final = enforce_signal_constraints(original,
        entry_blocked=result.get("entry_blocked", False),
        strong_long_blockers=result.get("strong_long_blockers", []))
    if result.get("signal_status") == "unavailable":
        final = "WAIT"
    if final != original:
        result["signal_reason"] += " [final eligibility cap]"
    result["signal"] = final
    result["signal_score"] = compute_signal_score(final, result.get("effective_conditions", 0), result.get("weighted_total", 9))
    result["oi_context"] = interpret_oi_context((result.get("positioning") or {}).get("oi_trend", "UNKNOWN"), final)
    key = (result.get("symbol", ""), result.get("timeframe", ""))
    if scan_cache.signal_first_seen_label.get(key) != final:
        scan_cache.signal_first_seen_label[key] = final
        scan_cache.signal_first_seen_at[key] = as_of
    result["signal_first_seen_at"] = scan_cache.signal_first_seen_at.get(key)
    result["signal_age_seconds"] = int(as_of - result["signal_first_seen_at"]) if result["signal_first_seen_at"] else 0




STATE_MAPS = ("signal_first_seen_at", "signal_first_seen_label", "prev_regime_by_tf", "regime_change_log",
              "signal_history", "divergence_history", "confidence_history", "smoothed_confidence", "prev_heat",
              "prev_zscore", "signal_inertia", "funding_history", "oi_history", "oi_change_history", "lsr_history",
              "bsr_history", "spot_ratio_history", "vpin_history", "agent_bar_baselines", "regime_bar_baselines")


def capture_state(state, symbol, timeframe):
    keys = (f"{symbol}:{timeframe}", (symbol, timeframe))
    return {name: [[list(k) if isinstance(k, tuple) else k, copy.deepcopy(v)]
                   for k, v in getattr(state, name, {}).items() if k in keys] for name in STATE_MAPS}


def replay_recorded(snapshot):
    """Reproduce an isolated recorded evaluation including its pre-decision history."""
    if snapshot.get("decision_version") != VERSION:
        raise ValueError("Snapshot requires a different decision version")
    state = new_state()
    for name, entries in snapshot["decision_state"].items():
        setattr(state, name, {tuple(k) if isinstance(k, list) else k: copy.deepcopy(v) for k, v in entries})
    state.anomalies = copy.deepcopy(snapshot.get("decision_anomalies", []))
    return evaluate_decision(copy.deepcopy(snapshot["decision_input"]), snapshot["decision_context"], state,
                             as_of=snapshot["evaluated_at"], metadata=snapshot.get("input_metadata"),
                             positions=snapshot.get("decision_positions", []))
