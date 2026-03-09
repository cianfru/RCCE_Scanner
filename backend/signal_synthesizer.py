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

# Fear & Greed thresholds
FNG_FEAR = 40           # Below this = Fear territory (entries allowed for ACCUMULATE)
FNG_GREED = 70          # Above this = Greed (dampens entries)
FNG_EXTREME_GREED = 80  # Above this = aggressive TRIM

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
    conditions_total: int = 11  # Max conditions for STRONG_LONG (expanded)


# ---------------------------------------------------------------------------
# Main synthesis function
# ---------------------------------------------------------------------------

def synthesize_signal(
    result: dict,
    consensus: dict,
    global_metrics: Optional[dict] = None,
    positioning: Optional[dict] = None,
    sentiment: Optional[dict] = None,
    stablecoin: Optional[dict] = None,
) -> SynthesizedSignal:
    """Produce the final trading signal from all available data.

    Parameters
    ----------
    result : dict
        Merged symbol result dict containing fields from all 3 engines.
    consensus : dict
        Market-wide consensus: {"consensus": str, "strength": float}.
    global_metrics : dict or None
        BTC dominance etc from market_data module.
    positioning : dict or None
        Hyperliquid positioning data (funding_regime, oi_trend, etc.).
    sentiment : dict or None
        Fear & Greed Index data.
    stablecoin : dict or None
        Stablecoin supply data (trend, change_7d_pct).

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
    heat_direction = result.get("heat_direction", 0)
    below_bmsb = heat_direction < 0  # price below weekly BMSB mid

    mkt_consensus = consensus.get("consensus", "MIXED")

    # Unpack new data layers
    funding_regime = (positioning or {}).get("funding_regime", "NEUTRAL")
    oi_trend = (positioning or {}).get("oi_trend", "UNKNOWN")
    funding_rate = (positioning or {}).get("funding_rate", 0.0)

    fear_greed = (sentiment or {}).get("fear_greed_value", 50)

    stable_trend = (stablecoin or {}).get("trend", "STABLE")

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

    # 1b. BLOWOFF exits (only when z is extended)
    if regime == "BLOWOFF":
        if z > Z_TRIM_HARD:
            out.signal = "TRIM_HARD"
            out.reason = f"BLOWOFF + z={z:.2f} > {Z_TRIM_HARD}"
            return out
        if z > Z_TRIM:
            out.signal = "TRIM"
            out.reason = f"BLOWOFF + z={z:.2f} > {Z_TRIM}"
            return out
        # BLOWOFF with moderate z — warn but allow entry evaluation
        warnings.append(f"BLOWOFF regime (z={z:.2f}) — monitor for escalation")

    # 1d. MARKDOWN + RISK-OFF -> RISK_OFF
    if regime == "MARKDOWN" and mkt_consensus == "RISK-OFF":
        out.signal = "RISK_OFF"
        out.reason = f"MARKDOWN + consensus RISK-OFF"
        return out

    # 1e. BEAR-DIV severity scoring
    if divergence == "BEAR-DIV":
        if confidence < CONF_LIGHT:
            # Low confidence + BEAR-DIV → exit
            out.signal = "NO_LONG"
            out.reason = f"BEAR-DIV + confidence={confidence*100:.0f}% < {CONF_LIGHT*100:.0f}%"
            out.warnings = ["Bearish divergence with weak confidence — exit"]
            return out
        # High confidence + BEAR-DIV → warn, block STRONG_LONG but allow LIGHT_LONG
        warnings.append(f"BEAR-DIV active (conf={confidence*100:.0f}%) — STRONG_LONG blocked")

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

    # Build condition checklist for STRONG_LONG (expanded to 10)
    cond_bullish_regime = regime in ("MARKUP", "ACCUM")
    cond_confidence = confidence > CONF_STRONG
    cond_consensus = mkt_consensus in ("RISK-ON", "ACCUMULATION")
    cond_z_range = -0.5 <= z <= 2.5
    cond_no_bear_div = divergence != "BEAR-DIV"
    cond_heat_ok = heat < HEAT_BLOCK_STRONG
    cond_no_climax = not is_climax  # Already handled above, but explicit
    cond_above_bmsb = not below_bmsb  # Must be above weekly BMSB for STRONG/LIGHT
    # New conditions from positioning/sentiment/stablecoin
    cond_funding_ok = funding_regime != "CROWDED_LONG"
    cond_not_greedy = fear_greed < FNG_GREED
    cond_liquidity_ok = stable_trend != "CONTRACTING"

    conditions = [
        cond_bullish_regime,
        cond_confidence,
        cond_consensus,
        cond_z_range,
        cond_no_bear_div,
        cond_heat_ok,
        cond_no_climax,
        cond_above_bmsb,
        cond_funding_ok,
        cond_not_greedy,
        cond_liquidity_ok,
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
        if funding_regime != "NEUTRAL":
            parts.append(f"funding={funding_regime}")
        if oi_trend not in ("UNKNOWN", "STABLE"):
            parts.append(f"OI={oi_trend}")
        if below_bmsb:
            parts.append("BELOW_BMSB")
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
    # Positioning warnings
    if funding_regime == "CROWDED_LONG":
        warnings.append(f"Crowded long funding ({funding_rate*100:.3f}%/hr) — squeeze risk")
    elif funding_regime == "CROWDED_SHORT":
        warnings.append(f"Crowded short funding ({funding_rate*100:.3f}%/hr) — rally fuel")
    if oi_trend == "SQUEEZE":
        warnings.append("OI declining while price rising — short squeeze, may not sustain")
    elif oi_trend == "LIQUIDATING":
        warnings.append("OI declining with price — long liquidation cascade")
    # Sentiment warnings
    if fear_greed >= FNG_EXTREME_GREED:
        warnings.append(f"Extreme Greed (F&G={fear_greed}) — trim signals more urgent")
    elif fear_greed <= 20:
        warnings.append(f"Extreme Fear (F&G={fear_greed}) — accumulation opportunity")
    # Stablecoin warnings
    if stable_trend == "CONTRACTING":
        warnings.append("Stablecoin supply contracting — reduced market liquidity")
    # BMSB structural warning
    if below_bmsb:
        warnings.append("Below weekly BMSB — STRONG/LIGHT_LONG blocked, only ACCUMULATE/REVIVAL allowed")

    # --- STRONG_LONG: ALL conditions must hold + no BEAR-DIV + above BMSB ---
    if conditions_met == len(conditions) and divergence != "BEAR-DIV" and not below_bmsb:
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
    # STRONG_LONG with 8/11 original conditions but blocked by funding/greed/liquidity
    # Must still be above BMSB
    elif conditions_met >= 8 and not cond_funding_ok and not below_bmsb:
        # Downgrade STRONG_LONG → LIGHT_LONG due to crowded funding
        if regime in ("MARKUP", "ACCUM") and divergence != "BEAR-DIV":
            out.signal = "LIGHT_LONG"
            out.reason = " + ".join(_reason_parts()) + " [downgraded: crowded funding]"
            out.warnings = warnings
            return out

    # --- ACCUMULATE: specific ACCUM regime conditions ---
    # Gated by Fear & Greed: only accumulate in Fear territory
    if (
        regime == "ACCUM"
        and z < 0
        and vol_low
        and confidence > CONF_ACCUM
        and mkt_consensus != "RISK-OFF"
        and heat < 70
    ):
        if fear_greed <= FNG_FEAR:
            out.signal = "ACCUMULATE"
            out.reason = " + ".join(_reason_parts()) + f" [ACCUM + F&G={fear_greed}]"
            out.warnings = warnings
            return out
        else:
            # Not fearful enough — signal as WAIT with note
            warnings.append(f"ACCUM conditions met but F&G={fear_greed} > {FNG_FEAR} — waiting for fear")
            # Fall through to LIGHT_LONG evaluation

    # --- ACCUMULATE via absorption (non-CAP regimes) ---
    # Absorption = price below weekly BMSB mid + red candle + contained TR + effort peak.
    # Only valid when regime and consensus support it (not in MARKDOWN/RISK-OFF).
    if (
        is_absorption
        and regime in ("ACCUM", "REACC")
        and mkt_consensus != "RISK-OFF"
        and confidence > CONF_ACCUM
        and heat < 70
    ):
        out.signal = "ACCUMULATE"
        out.reason = " + ".join(_reason_parts()) + f" [absorption in {regime}]"
        out.warnings = warnings
        return out

    # --- REVIVAL_SEED: CAP with strong bottom signals ---
    # Gated by Fear & Greed: revival seeds only in Fear territory
    if (
        regime == "CAP"
        and z < -1.0
        and vol_high
        and confidence > CONF_REVIVAL
        and mkt_consensus != "RISK-OFF"
        and fear_greed <= FNG_FEAR
    ):
        signal = "REVIVAL_SEED"
        if floor_confirmed:
            signal = "REVIVAL_SEED_CONFIRMED"
            warnings.append("Floor confirmed — high confidence revival setup")
        # OI LIQUIDATING boosts confidence (capitulation = opportunity)
        if oi_trend == "LIQUIDATING":
            warnings.append("OI liquidation cascade — capitulation likely near")
        out.signal = signal
        out.reason = " + ".join(_reason_parts()) + f" [CAP revival + F&G={fear_greed}]"
        out.warnings = warnings
        return out

    # --- LIGHT_LONG: 5+ conditions met + supportive regime + above BMSB ---
    if conditions_met >= 5 and regime in ("MARKUP", "REACC", "ACCUM") and not below_bmsb:
        # MARKUP LIGHT_LONG: extended z (1.0-2.0) with decent confidence
        if (regime == "MARKUP" and 1.0 < z < Z_BLOWOFF
                and confidence > CONF_LIGHT
                and heat < HEAT_WARNING
                and mkt_consensus != "RISK-OFF"
                and divergence != "BEAR-DIV"):
            out.signal = "LIGHT_LONG"
            out.reason = " + ".join(_reason_parts()) + " [MARKUP extended]"
            out.warnings = warnings
            return out

        # MARKUP LIGHT_LONG: moderate z with conditions support
        if (regime == "MARKUP" and 0 < z < Z_BLOWOFF
                and confidence > CONF_LIGHT
                and heat < HEAT_BLOCK_STRONG
                and mkt_consensus in ("RISK-ON", "MIXED")
                and divergence != "BEAR-DIV"):
            out.signal = "LIGHT_LONG"
            out.reason = " + ".join(_reason_parts()) + f" [{conditions_met}/{len(conditions)} conditions]"
            out.warnings = warnings
            return out

        # REACC LIGHT_LONG: needs supportive consensus + decent confidence
        if (regime == "REACC" and z < 0.5
                and confidence > CONF_LIGHT
                and heat < HEAT_WARNING
                and mkt_consensus in ("RISK-ON", "MIXED")):
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
