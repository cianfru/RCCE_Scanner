"""
signal_synthesizer.py
~~~~~~~~~~~~~~~~~~~~~
Cross-engine signal synthesis implementing the RCCE User Guide v2.1
Decision Matrix.

Receives outputs from all three engines (RCCE, Heatmap, Exhaustion) plus
market context (consensus, divergence, BTC dominance) and produces a
final trading signal with human-readable reasoning and warnings.

This module replaces the single-engine signal generation that lived
inside rcce_engine._generate_signal().  The RCCE engine still produces
a ``raw_signal`` for reference, but the scanner pipeline calls
``synthesize_signal()`` here to derive the definitive output.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Z-score thresholds (must match rcce_engine.py)
# ---------------------------------------------------------------------------

Z_BLOWOFF = 2.0
Z_TRIM = 3.0
Z_TRIM_HARD = 3.5

# Heat thresholds
HEAT_WARNING = 80       # Include warning when heat >= 80
HEAT_BLOCK_STRONG = 85  # Block STRONG_LONG when heat >= 85
HEAT_FORCE_TRIM = 95    # Force TRIM when heat >= 95

# Confidence thresholds
CONF_STRONG = 0.60      # Required for STRONG_LONG
CONF_LIGHT = 0.50       # Required for LIGHT_LONG
CONF_ACCUM = 0.40       # Required for ACCUMULATE
CONF_REVIVAL = 0.30     # Required for REVIVAL_SEED
CONF_BLOCK = 0.30       # Below this + BEAR-DIV -> NO_LONG

# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------

@dataclass
class SynthesizedSignal:
    """Result of the signal synthesis process."""
    signal: str = "WAIT"
    raw_signal: str = "WAIT"
    reason: str = ""
    warnings: list = field(default_factory=list)
    conditions_met: int = 0
    conditions_total: int = 7   # Max conditions for STRONG_LONG


# ---------------------------------------------------------------------------
# Main synthesis function
# ---------------------------------------------------------------------------

def synthesize_signal(
    result: dict,
    consensus: dict,
    global_metrics: Optional[dict] = None,
) -> SynthesizedSignal:
    """Produce the final trading signal from all available data.

    Parameters
    ----------
    result : dict
        Merged symbol result dict containing fields from all 3 engines:
        regime, confidence, zscore, energy, vol_state, momentum,
        raw_signal, heat, heat_direction, heat_phase, atr_regime,
        exhaustion_state, floor_confirmed, is_absorption, is_climax,
        divergence, asset_class.
    consensus : dict
        Market-wide consensus: {"consensus": str, "strength": float}.
    global_metrics : dict or None
        BTC dominance etc from market_data module.

    Returns
    -------
    SynthesizedSignal
    """
    # Unpack fields with safe defaults
    regime = result.get("regime", "FLAT").upper()
    raw_signal = result.get("raw_signal", "WAIT")
    z = result.get("zscore", 0.0)
    confidence = result.get("confidence", 0.0) / 100.0  # Convert to 0-1 scale
    vol_state = result.get("vol_state", "MID")
    vol_low = vol_state == "LOW"
    vol_high = vol_state == "HIGH"
    heat = result.get("heat", 0)
    is_climax = result.get("is_climax", False)
    is_absorption = result.get("is_absorption", False)
    floor_confirmed = result.get("floor_confirmed", False)
    divergence = result.get("divergence")
    exhaustion_state = result.get("exhaustion_state", "NEUTRAL")

    mkt_consensus = consensus.get("consensus", "MIXED")

    out = SynthesizedSignal(raw_signal=raw_signal)
    reasons: list = []
    warnings: list = []

    # -----------------------------------------------------------------------
    # STEP 1: EXIT RULES (highest priority — any single trigger fires)
    # -----------------------------------------------------------------------

    # 1a. Heat force-trim (extreme overextension)
    if heat >= HEAT_FORCE_TRIM:
        out.signal = "TRIM"
        out.reason = f"Heat={heat} >= {HEAT_FORCE_TRIM} (extreme overextension)"
        out.warnings = [f"Heat at {heat}/100 — forced exit"]
        return out

    # 1b. ABSORBING phase -> NO_LONG
    if regime == "ABSORBING":
        out.signal = "NO_LONG"
        out.reason = "ABSORBING phase detected"
        return out

    # 1c. BLOWOFF exits
    if regime == "BLOWOFF":
        if z > Z_TRIM_HARD:
            out.signal = "TRIM_HARD"
            out.reason = f"BLOWOFF + z={z:.2f} > {Z_TRIM_HARD}"
            return out
        if z > Z_TRIM:
            out.signal = "TRIM"
            out.reason = f"BLOWOFF + z={z:.2f} > {Z_TRIM}"
            return out
        # BLOWOFF without extreme z still warrants TRIM
        out.signal = "TRIM"
        out.reason = f"BLOWOFF regime (z={z:.2f})"
        return out

    # 1d. MARKDOWN + RISK-OFF -> RISK_OFF
    if regime == "MARKDOWN" and mkt_consensus == "RISK-OFF":
        out.signal = "RISK_OFF"
        out.reason = f"MARKDOWN + consensus RISK-OFF"
        return out

    # 1e. BEAR-DIV with low confidence -> NO_LONG
    if divergence == "BEAR-DIV" and confidence < CONF_BLOCK:
        out.signal = "NO_LONG"
        out.reason = f"BEAR-DIV + confidence={confidence*100:.0f}% < {CONF_BLOCK*100:.0f}%"
        out.warnings = ["Bearish divergence with weak confidence"]
        return out

    # 1f. EUPHORIA consensus + high z -> NO_LONG
    if mkt_consensus == "EUPHORIA" and z > Z_BLOWOFF:
        out.signal = "NO_LONG"
        out.reason = f"Consensus EUPHORIA + z={z:.2f} > {Z_BLOWOFF}"
        out.warnings = ["Market in euphoria with extended z-score"]
        return out

    # 1g. MARKDOWN without RISK-OFF -> WAIT (no entries allowed)
    if regime == "MARKDOWN":
        out.signal = "WAIT"
        out.reason = f"MARKDOWN regime (consensus={mkt_consensus})"
        if divergence == "BULL-DIV":
            warnings.append("Bullish divergence in MARKDOWN — watch for reversal")
        out.warnings = warnings
        return out

    # 1h. Exhaustion climax -> block entries
    if is_climax:
        out.signal = "WAIT"
        out.reason = "Exhaustion climax detected — entries blocked"
        out.warnings = ["Climactic selling/buying volume — wait for resolution"]
        return out

    # -----------------------------------------------------------------------
    # STEP 2: ENTRY RULES (evaluated by signal strength)
    # -----------------------------------------------------------------------

    # Build condition checklist for STRONG_LONG
    cond_bullish_regime = regime in ("MARKUP", "ACCUM")
    cond_confidence = confidence > CONF_STRONG
    cond_consensus = mkt_consensus in ("RISK-ON", "ACCUMULATION")
    cond_z_range = -0.5 <= z <= 2.5
    cond_no_bear_div = divergence != "BEAR-DIV"
    cond_heat_ok = heat < HEAT_BLOCK_STRONG
    cond_no_climax = not is_climax  # Already handled above, but explicit

    conditions = [
        cond_bullish_regime,
        cond_confidence,
        cond_consensus,
        cond_z_range,
        cond_no_bear_div,
        cond_heat_ok,
        cond_no_climax,
    ]
    conditions_met = sum(conditions)
    out.conditions_met = conditions_met
    out.conditions_total = len(conditions)

    # Build reason parts
    def _reason_parts() -> list:
        parts = [regime]
        parts.append(f"z={z:.2f}")
        parts.append(f"conf={confidence*100:.0f}%")
        parts.append(f"consensus={mkt_consensus}")
        if heat > 0:
            parts.append(f"heat={heat}")
        if divergence:
            parts.append(f"div={divergence}")
        return parts

    # Collect warnings
    if divergence == "BEAR-DIV":
        warnings.append("BEAR-DIV: BTC diverging bearishly")
    if divergence == "BULL-DIV":
        warnings.append("BULL-DIV: potential bottom forming")
    if heat >= HEAT_WARNING:
        warnings.append(f"Heat at {heat}/100 — approaching overextension")
    if floor_confirmed:
        warnings.append("Floor confirmed — downside support detected")
    if is_absorption:
        warnings.append("Absorption detected — accumulation underway")
    if mkt_consensus == "EUPHORIA":
        warnings.append("Market consensus: EUPHORIA — elevated risk")

    # --- STRONG_LONG: ALL 7 conditions must hold ---
    if conditions_met == len(conditions):
        # MARKUP with full confirmation
        if regime == "MARKUP" and z > -0.5 and z < 1.0:
            out.signal = "STRONG_LONG"
            out.reason = " + ".join(_reason_parts()) + " [all conditions met]"
            out.warnings = warnings
            return out
        # ACCUM with full confirmation
        if regime == "ACCUM":
            out.signal = "STRONG_LONG"
            out.reason = " + ".join(_reason_parts()) + " [all conditions met]"
            out.warnings = warnings
            return out

    # --- ACCUMULATE: specific ACCUM regime conditions ---
    if (
        regime == "ACCUM"
        and z < 0
        and vol_low
        and confidence > CONF_ACCUM
        and mkt_consensus != "RISK-OFF"
    ):
        out.signal = "ACCUMULATE"
        out.reason = " + ".join(_reason_parts()) + " [ACCUM entry]"
        out.warnings = warnings
        return out

    # --- REVIVAL_SEED: CAP with strong bottom signals ---
    if (
        regime == "CAP"
        and z < -1.0
        and vol_high
        and confidence > CONF_REVIVAL
        and mkt_consensus != "RISK-OFF"
    ):
        signal = "REVIVAL_SEED"
        if floor_confirmed:
            signal = "REVIVAL_SEED"
            warnings.append("Floor confirmed — higher confidence revival")
        out.signal = signal
        out.reason = " + ".join(_reason_parts()) + " [CAP revival]"
        out.warnings = warnings
        return out

    # --- LIGHT_LONG: 2+ conditions met + supportive regime ---
    if conditions_met >= 2 and regime in ("MARKUP", "REACC", "ACCUM"):
        # MARKUP LIGHT_LONG: z between 1.0 and Z_BLOWOFF, decent confidence
        if regime == "MARKUP" and z > 1.0 and z < Z_BLOWOFF and confidence > CONF_LIGHT:
            # Check consensus isn't actively against us
            if mkt_consensus != "RISK-OFF":
                out.signal = "LIGHT_LONG"
                out.reason = " + ".join(_reason_parts()) + " [MARKUP extended]"
                out.warnings = warnings
                return out

        # MARKUP LIGHT_LONG: reasonable z but missing some conditions
        if regime == "MARKUP" and confidence > CONF_LIGHT and mkt_consensus != "RISK-OFF":
            if heat < HEAT_BLOCK_STRONG:
                out.signal = "LIGHT_LONG"
                out.reason = " + ".join(_reason_parts()) + f" [{conditions_met}/{len(conditions)} conditions]"
                out.warnings = warnings
                return out

        # REACC LIGHT_LONG: needs RISK-ON consensus
        if regime == "REACC" and z < 0.5 and confidence > CONF_ACCUM:
            if mkt_consensus == "RISK-ON":
                out.signal = "LIGHT_LONG"
                out.reason = " + ".join(_reason_parts()) + " [REACC + RISK-ON]"
                out.warnings = warnings
                return out

    # --- CAP without strong revival conditions ---
    if regime == "CAP" and z < -1.0 and confidence > CONF_REVIVAL:
        if is_absorption:
            out.signal = "ACCUMULATE"
            out.reason = " + ".join(_reason_parts()) + " [CAP absorption]"
            out.warnings = warnings
            return out

    # -----------------------------------------------------------------------
    # STEP 3: DEFAULT — WAIT
    # -----------------------------------------------------------------------

    out.signal = "WAIT"
    out.reason = " + ".join(_reason_parts()) + f" [{conditions_met}/{len(conditions)} conditions — insufficient]"
    out.warnings = warnings
    return out
