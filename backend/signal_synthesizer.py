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
HEAT_ENTRY_ZONE = 70    # Accumulate only when heat < 70
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

# CoinGlass condition weight (0.75 = confirmation, not primary)
CG_CONDITION_WEIGHT = 0.75
# Smart money LSR threshold — pros not heavily short
SMART_MONEY_LSR_OK = 0.85

# HyperLens smart money consensus weight (0.5 = supplemental signal)
HL_CONDITION_WEIGHT = 0.5
# Minimum confidence for HL consensus to count as a condition
HL_CONFIDENCE_THRESHOLD = 0.15

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
    effective_conditions: float = 0.0  # Weighted score post-boost/penalty
    conditions_total: int = 10  # Raw condition count (10 for HL-native, 14 for CEX)
    conditions_detail: list = field(default_factory=list)  # [{name, label, desc, met}]
    vol_scale: float = 1.0


# ---------------------------------------------------------------------------
# CVD + Spot modifier helper
# ---------------------------------------------------------------------------

def _apply_cvd_modifiers(
    out: "SynthesizedSignal",
    cvd_trend: str,
    cvd_divergence: bool,
    spot_dominance: str,
    long_short_ratio: float,
    liquidation_24h_usd: float,
    top_trader_lsr: float = 1.0,
) -> "SynthesizedSignal":
    """Apply CVD and spot data modifiers to an already-determined signal.

    These are supplemental and additive — they upgrade or downgrade signals
    that were computed by the main decision logic.  Hard exit signals
    (TRIM, TRIM_HARD, RISK_OFF, NO_LONG, LIGHT_SHORT) are never touched.
    """
    _hard_exits = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG", "LIGHT_SHORT"}
    _adverse    = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}
    signal = out.signal

    # Never modify hard exits or WAIT coming from a blocked/climax path
    if signal in _hard_exits:
        return out

    cvd_reasons: list = []
    extra_warnings: list = []

    # 1. ACCUMULATE → LIGHT_LONG upgrade when CVD confirms + spot-led demand
    if (signal == "ACCUMULATE"
            and cvd_trend == "BULLISH"
            and spot_dominance == "SPOT_LED"):
        signal = "LIGHT_LONG"
        cvd_reasons.append("cvd_bullish+spot_led→upgrade")

    # 2. WAIT → ACCUMULATE when CVD is bullish + LSR shows crowded shorts (squeeze setup)
    elif (signal == "WAIT"
            and cvd_trend == "BULLISH"
            and long_short_ratio < 0.85):   # more shorts than longs
        signal = "ACCUMULATE"
        cvd_reasons.append("cvd_bullish+crowded_short→accum")

    # 3. LIGHT_LONG → STRONG_LONG when CVD confirms + spot dominance confirms
    elif (signal == "LIGHT_LONG"
            and cvd_trend == "BULLISH"
            and spot_dominance == "SPOT_LED"):
        signal = "STRONG_LONG"
        cvd_reasons.append("cvd+spot_led→strong")

    # 4. CVD BEARISH divergence → warning only (no signal downgrade)
    #    Previously hard-downgraded STRONG→TRIM and LIGHT→WAIT, but a single
    #    CVD reading shouldn't override 10+ confirming conditions.  The warning
    #    surfaces in the UI so the user can decide.
    if (cvd_divergence
            and cvd_trend == "BEARISH"
            and signal in ("STRONG_LONG", "LIGHT_LONG")):
        extra_warnings.append("CVD bearish divergence — monitor for distribution")

    # 5. Extreme liquidations + entry signal = high conviction (capitulation complete)
    # If liq > $50M in 24h and we have a bullish signal, that's a washout floor
    if (liquidation_24h_usd > 50_000_000
            and signal in ("ACCUMULATE", "REVIVAL_SEED", "WAIT")
            and cvd_trend == "BULLISH"):
        signal = "ACCUMULATE" if signal == "WAIT" else signal
        cvd_reasons.append(f"liq_washout+cvd_bull(${liquidation_24h_usd/1e6:.0f}M)")

    # 6. Smart money LSR — extreme short positioning only (< 0.7)
    # Mild short skew (< 0.85) is now handled by condition #13.
    # This modifier only fires for *extreme* pro short bias → hard downgrade.
    if top_trader_lsr != 1.0:
        if top_trader_lsr < 0.7 and signal in ("STRONG_LONG", "LIGHT_LONG"):
            signal = "LIGHT_LONG" if signal == "STRONG_LONG" else "ACCUMULATE"
            extra_warnings.append(f"smart_money_heavy_short(lsr={top_trader_lsr:.2f})→downgrade")
        if top_trader_lsr > 1.5 and signal not in _adverse:
            extra_warnings.append(f"smart_money_long(lsr={top_trader_lsr:.2f})")

    # Informational warnings (no signal change)
    if spot_dominance == "SPOT_LED" and signal not in _adverse:
        extra_warnings.append("spot_led_demand")
    if long_short_ratio < 0.8:
        extra_warnings.append(f"crowded_short(lsr={long_short_ratio:.2f})")

    if cvd_reasons:
        out.reason = out.reason + " [cvd:" + ", ".join(cvd_reasons) + "]"

    out.signal = signal
    out.warnings = out.warnings + extra_warnings
    return out


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
    macro_blocked: bool = False,
    prev_heat: int = 0,
    bmsb_valid: bool = True,
    cvd_trend: str = "NEUTRAL",
    cvd_divergence: bool = False,
    spot_dominance: str = "NEUTRAL",
    long_short_ratio: float = 1.0,
    liquidation_24h_usd: float = 0.0,
    # Macro data (CoinGlass)
    etf_flow_usd: float = 0.0,
    cb_premium: float = 0.0,
    has_coinglass: bool = False,
    # HyperLens smart money consensus
    hl_consensus_trend: str = "NEUTRAL",
    hl_consensus_confidence: float = 0.0,
    hl_consensus_net_ratio: float = 0.0,
    has_hyperlens: bool = False,
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
        Positioning data (funding_regime, oi_trend, etc.).
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
    confidence = result.get("confidence", 0.0) / 100.0  # HMM outputs 0-100, normalize to 0-1 for thresholds
    vol_state = result.get("vol_state", "MID")
    vol_low = vol_state == "LOW"
    vol_high = vol_state == "HIGH"
    heat = result.get("heat", 0)
    heat_phase = result.get("heat_phase", "Neutral")
    is_climax = result.get("is_climax", False)
    is_absorption = result.get("is_absorption", False)
    floor_confirmed = result.get("floor_confirmed", False)
    divergence = result.get("divergence")
    exhaustion_state = result.get("exhaustion_state", "NEUTRAL")

    mkt_consensus = consensus.get("consensus", "MIXED")

    # Unpack new data layers
    funding_regime = (positioning or {}).get("funding_regime", "NEUTRAL")
    oi_trend = (positioning or {}).get("oi_trend", "UNKNOWN")
    funding_rate = (positioning or {}).get("funding_rate", 0.0)
    top_trader_lsr = (positioning or {}).get("top_trader_lsr", 1.0)

    fear_greed = (sentiment or {}).get("fear_greed_value", 50)

    stable_trend = (stablecoin or {}).get("trend", "STABLE")

    # ── Dynamic Z-score thresholds (Feature A) ──
    vs = result.get("vol_scale", 1.0)
    z_trim = Z_TRIM * vs
    z_trim_hard = Z_TRIM_HARD * vs
    z_blowoff = Z_BLOWOFF * vs

    # ── Regime-adaptive heat thresholds (Feature B) ──
    # BLOWOFF: overextension is more dangerous → tighter thresholds
    # CAP/ACCUM: at bottoms, heat is irrelevant → disabled
    if regime == "BLOWOFF":
        heat_force = 85
        heat_block = 75
    elif regime in ("CAP", "ACCUM"):
        heat_force = 100      # never force-trim at bottoms
        heat_block = 100
    else:
        heat_force = HEAT_FORCE_TRIM
        heat_block = HEAT_BLOCK_STRONG

    out = SynthesizedSignal(raw_signal=raw_signal)
    reasons: list = []
    warnings: list = []

    # -----------------------------------------------------------------------
    # CONDITION CHECKLIST (computed for ALL symbols before exit/entry rules)
    #
    # Core conditions (weight 1.0 each, max 10 pts):
    #   10 engine + macro booleans that determine STRONG_LONG eligibility.
    #
    # CoinGlass conditions (weight 0.75 each, max 3 pts):
    #   4 confirmation signals from CoinGlass.  Only scored when the symbol
    #   has CoinGlass data (CEX-listed); HL-native tokens are scored out
    #   of 10 only, keeping the comparison fair.
    # -----------------------------------------------------------------------

    # -- Core conditions (weight 1.0) --
    # NOTE: RCCE regime probability (formerly "confidence") is no longer a
    # condition gate.  It measured HMM classification certainty, not trade
    # conviction — a coin can have 14/16 conditions met but fail the gate
    # because z-score sits near a regime boundary.  Trade conviction is now
    # the weighted conditions score itself.  Regime probability is still used
    # downstream for entry-specific gates (ACCUM > 40%, REVIVAL > 30%).
    cond_bullish_regime = regime in ("MARKUP", "ACCUM")
    cond_consensus = mkt_consensus in ("RISK-ON", "ACCUMULATION")
    cond_z_range = -0.5 <= z <= 2.5
    cond_no_bear_div = divergence != "BEAR-DIV"
    cond_heat_ok = heat < heat_block
    cond_no_climax = not is_climax
    cond_funding_ok = funding_regime != "CROWDED_LONG"
    cond_not_greedy = fear_greed < FNG_GREED
    cond_liquidity_ok = stable_trend != "CONTRACTING"

    core_conditions = [
        cond_bullish_regime, cond_consensus, cond_z_range,
        cond_no_bear_div, cond_heat_ok, cond_no_climax,
        cond_funding_ok, cond_not_greedy, cond_liquidity_ok,
    ]
    core_met = sum(core_conditions)

    _CORE_NAMES = [
        ("bullish_regime", "Regime",      "MARKUP or ACCUM",         "core"),
        ("consensus",      "Consensus",   "RISK-ON or ACCUMULATION", "core"),
        ("z_range",        "Z-Score",     "-0.5 to 2.5",             "core"),
        ("no_bear_div",    "No Bear Div", "No bearish divergence",   "core"),
        ("heat_ok",        "Heat OK",     f"< {heat_block}",         "core"),
        ("no_climax",      "No Climax",   "No exhaustion climax",    "core"),
        ("funding_ok",     "Funding OK",  "Not crowded long",        "core"),
        ("not_greedy",     "Not Greedy",  f"F&G < {FNG_GREED}",     "core"),
        ("liquidity_ok",   "Liquidity",   "Stables not contracting", "core"),
    ]

    # -- CoinGlass conditions (weight 0.75, only when data available) --
    cond_oi_confirms = oi_trend in ("BUILDING", "STABLE") if regime in ("MARKUP", "ACCUM", "REACC") else oi_trend in ("LIQUIDATING", "SQUEEZE")
    cond_cvd_confirms = cvd_trend in ("BULLISH", "NEUTRAL")  # NEUTRAL = no bias, not counter-evidence
    cond_smart_money = top_trader_lsr >= SMART_MONEY_LSR_OK or top_trader_lsr == 1.0  # 1.0 = no data → neutral pass
    cond_macro_tailwind = etf_flow_usd > 0 or cb_premium > 0

    cg_conditions = [cond_oi_confirms, cond_cvd_confirms, cond_smart_money, cond_macro_tailwind]
    cg_met = sum(cg_conditions)

    _CG_NAMES = [
        ("oi_confirms",      "OI Confirms",     f"OI {oi_trend}",                        "coinglass"),
        ("cvd_confirms",     "CVD Confirms",    f"CVD {cvd_trend}",                      "coinglass"),
        ("smart_money_ok",   "Smart Money",     f"LSR {top_trader_lsr:.2f} >= {SMART_MONEY_LSR_OK}", "coinglass"),
        ("macro_tailwind",   "Macro Tailwind",  f"ETF ${etf_flow_usd/1e6:+.0f}M CB {cb_premium*100:+.2f}%", "coinglass"),
    ]

    # -- HyperLens conditions (weight 0.5, only when data available) --
    # HL whale consensus: are the tracked 500 wallets aligned with this signal?
    cond_hl_aligned = (
        hl_consensus_trend == "BULLISH" and hl_consensus_confidence >= HL_CONFIDENCE_THRESHOLD
    ) if has_hyperlens else False
    cond_hl_not_counter = (
        hl_consensus_trend != "BEARISH" or hl_consensus_confidence < HL_CONFIDENCE_THRESHOLD
    ) if has_hyperlens else True

    hl_conditions = [cond_hl_aligned, cond_hl_not_counter]
    hl_met = sum(hl_conditions)

    _HL_NAMES = [
        ("hl_whale_aligned",  "Whale Aligned",   f"HL {hl_consensus_trend} ({hl_consensus_confidence:.0%})", "hyperlens"),
        ("hl_not_counter",    "No Whale Counter", f"HL not bearish (ratio={hl_consensus_net_ratio:+.2f})",   "hyperlens"),
    ]

    # Weighted scoring: core (1.0) + CoinGlass (0.75 each) + HyperLens (0.5 each)
    # Core max is now 9 (confidence gate removed)
    core_score = float(core_met)  # max 9.0
    if has_coinglass:
        cg_score = float(cg_met) * CG_CONDITION_WEIGHT  # max 3.0
        total_max = 9.0 + 4 * CG_CONDITION_WEIGHT        # 12.0
    else:
        cg_score = 0.0
        total_max = 9.0

    if has_hyperlens:
        hl_score = float(hl_met) * HL_CONDITION_WEIGHT  # max 1.0
        total_max += 2 * HL_CONDITION_WEIGHT             # +1.0
    else:
        hl_score = 0.0

    weighted_score = core_score + cg_score + hl_score
    score_pct = weighted_score / total_max if total_max > 0 else 0.0

    # For backward compat: conditions_met / conditions_total as integers
    if has_coinglass and has_hyperlens:
        conditions_met = core_met + cg_met + hl_met
        conditions_total = 15
    elif has_coinglass:
        conditions_met = core_met + cg_met
        conditions_total = 13
    elif has_hyperlens:
        conditions_met = core_met + hl_met
        conditions_total = 11
    else:
        conditions_met = core_met
        conditions_total = 9

    out.conditions_met = conditions_met
    out.conditions_total = conditions_total

    # Build conditions_detail with group tag
    out.conditions_detail = [
        {"name": n, "label": l, "desc": d, "met": bool(c), "group": g}
        for (n, l, d, g), c in zip(_CORE_NAMES, core_conditions)
    ]
    if has_coinglass:
        out.conditions_detail += [
            {"name": n, "label": l, "desc": d, "met": bool(c), "group": g}
            for (n, l, d, g), c in zip(_CG_NAMES, cg_conditions)
        ]
    if has_hyperlens:
        out.conditions_detail += [
            {"name": n, "label": l, "desc": d, "met": bool(c), "group": g}
            for (n, l, d, g), c in zip(_HL_NAMES, hl_conditions)
        ]

    # ── Feature B: Regime-specific boosters & penalties ──
    effective = weighted_score
    boost_reasons: list = []

    # Exhaustion engine boosters — floor/absorption are strong bottom signals
    if regime in ("CAP", "ACCUM"):
        if floor_confirmed:
            effective += 2
            boost_reasons.append("+2 floor boost")
        if is_absorption:
            effective += 1
            boost_reasons.append("+1 absorption boost")

    # Heat phase penalty — fading momentum in MARKUP is a warning
    if regime == "MARKUP" and heat_phase in ("Fading", "Exhaustion"):
        effective -= 1
        boost_reasons.append(f"-1 heat {heat_phase.lower()}")

    out.effective_conditions = effective
    out.vol_scale = vs

    # Helper: build human-readable reason string
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
        if vs != 1.0:
            parts.append(f"vs={vs:.2f}")
        if has_hyperlens and hl_consensus_trend != "NEUTRAL":
            parts.append(f"whales={hl_consensus_trend}({hl_consensus_confidence:.0%})")
        if boost_reasons:
            parts.append("[" + ", ".join(boost_reasons) + "]")
        return parts

    # -----------------------------------------------------------------------
    # STEP 1: EXIT RULES (highest priority — any single trigger fires)
    # -----------------------------------------------------------------------

    # 1a. Heat force-trim (extreme overextension, regime-adaptive)
    if heat >= heat_force:
        out.signal = "TRIM"
        out.reason = f"Heat={heat} >= {heat_force} (extreme overextension)"
        out.warnings = [f"Heat at {heat}/100 — forced exit"]
        return out

    # 1b. BLOWOFF exits (dynamic z-thresholds scaled by vol_scale)
    # (Absorption-as-entry moved to Step 2, gated by regime/consensus/heat)
    if regime == "BLOWOFF":
        if z > z_trim_hard:
            out.signal = "TRIM_HARD"
            out.reason = f"BLOWOFF + z={z:.2f} > {z_trim_hard:.2f}"
            return out
        if z > z_trim:
            out.signal = "TRIM"
            out.reason = f"BLOWOFF + z={z:.2f} > {z_trim:.2f}"
            return out
        # BLOWOFF with moderate z — warn but allow entry evaluation
        warnings.append(f"BLOWOFF regime (z={z:.2f}) — monitor for escalation")

    # 1d. MARKDOWN + RISK-OFF -> RISK_OFF
    # When macro_blocked, skip RISK_OFF (no longs to exit) — fall through
    # to 1g for LIGHT_SHORT evaluation instead.
    if regime == "MARKDOWN" and mkt_consensus == "RISK-OFF" and not macro_blocked:
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
    if mkt_consensus == "EUPHORIA" and z > z_blowoff:
        out.signal = "NO_LONG"
        out.reason = f"Consensus EUPHORIA + z={z:.2f} > {z_blowoff:.2f}"
        out.warnings = ["Market in euphoria with extended z-score"]
        return out

    # 1g. MARKDOWN without macro_blocked — WAIT (no entries in downtrend)
    if regime == "MARKDOWN" and not macro_blocked:
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

    # 1i. Macro blocked — LIGHT_SHORT for failed rallies, WAIT otherwise
    # Fires across ALL regimes: the RCCE engine reclassifies bear rallies
    # as MARKUP/REACC before z/heat reach short-entry levels, so we use
    # the BMSB macro filter as the bear market confirmation and z/heat/stall
    # to identify rally exhaustion points.
    if macro_blocked:
        # No BMSB data at all → always WAIT (no shorts either without BMSB)
        if not bmsb_valid:
            out.signal = "WAIT"
            out.reason = f"BMSB data unavailable (insufficient weekly bars) — {regime} regime, all entries blocked"
            out.warnings = warnings + ["No BMSB data — token too new or weekly history too short"]
            return out
        if (0.3 <= z <= 1.2
                and heat >= 20
                and heat <= prev_heat          # rally momentum stalling
                and divergence != "BULL-DIV"
                and funding_regime != "CROWDED_SHORT"
                and confidence > 0.30):
            out.signal = "LIGHT_SHORT"
            out.reason = " + ".join(_reason_parts()) + " [macro blocked bear rally short]"
            out.warnings = warnings
            return out
        out.signal = "WAIT"
        out.reason = f"Macro blocked (BMSB bearish) — {regime} regime, long entries blocked"
        out.warnings = warnings
        return out

    # -----------------------------------------------------------------------
    # STEP 2: ENTRY RULES (evaluated by signal strength)
    # -----------------------------------------------------------------------

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
    # F&G removed from per-coin warnings — it's market-wide, not per-coin.
    # Shown in MarketContext strip instead. Still used as condition #9 (Not Greedy).
    # Stablecoin warnings
    if stable_trend == "CONTRACTING":
        warnings.append("Stablecoin supply contracting — reduced market liquidity")
    # HyperLens warnings
    if has_hyperlens and hl_consensus_confidence >= HL_CONFIDENCE_THRESHOLD:
        if hl_consensus_trend == "BULLISH":
            warnings.append(f"Whale consensus BULLISH ({hl_consensus_confidence:.0%}, ratio={hl_consensus_net_ratio:+.2f})")
        elif hl_consensus_trend == "BEARISH":
            warnings.append(f"Whale consensus BEARISH ({hl_consensus_confidence:.0%}, ratio={hl_consensus_net_ratio:+.2f})")

    def _apply_hl_modifiers(out):
        """Apply HyperLens whale consensus modifiers after CVD modifiers."""
        if not has_hyperlens or hl_consensus_confidence < HL_CONFIDENCE_THRESHOLD:
            return out

        _hard_exits = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG", "LIGHT_SHORT"}
        if out.signal in _hard_exits:
            return out

        # Whale BULLISH + entry signal → upgrade one step
        if (hl_consensus_trend == "BULLISH"
                and hl_consensus_confidence >= 0.30
                and hl_consensus_net_ratio > 0.2):
            if out.signal == "ACCUMULATE":
                out.signal = "LIGHT_LONG"
                out.reason += " [whales_bullish→upgrade]"
            elif out.signal == "WAIT" and hl_consensus_confidence >= 0.40:
                out.signal = "ACCUMULATE"
                out.reason += " [whales_loading→accum]"

        # Whale BEARISH + entry signal → add warning (don't hard downgrade,
        # same philosophy as CVD bearish divergence)
        if (hl_consensus_trend == "BEARISH"
                and hl_consensus_confidence >= 0.30
                and out.signal in ("STRONG_LONG", "LIGHT_LONG")):
            out.warnings = out.warnings + [f"WHALE DIVERGENCE: signal {out.signal} but whales BEARISH ({hl_consensus_confidence:.0%})"]

        return out

    def _cvd_return():
        """Shorthand: apply CVD + HL modifiers and return out."""
        result = _apply_cvd_modifiers(
            out, cvd_trend, cvd_divergence, spot_dominance,
            long_short_ratio, liquidation_24h_usd, top_trader_lsr,
        )
        return _apply_hl_modifiers(result)

    # --- STRONG_LONG: effective score >= total_max (all conditions + boosts) + no BEAR-DIV ---
    # Use percentage: >= 75% weighted score for STRONG_LONG
    eff_pct = effective / total_max if total_max > 0 else 0.0
    if eff_pct >= 0.75 and divergence != "BEAR-DIV":
        # MARKUP with full confirmation
        if regime == "MARKUP" and z > -0.5 and z < 1.0:
            _tag = f"[{conditions_met}/{conditions_total} cond, {effective:.1f}/{total_max:.0f} eff ({eff_pct:.0%})]"
            out.signal = "STRONG_LONG"
            out.reason = " + ".join(_reason_parts()) + f" {_tag}"
            out.warnings = warnings
            return _cvd_return()
        # ACCUM with full confirmation (boosts help here)
        if regime in ("ACCUM", "CAP"):
            _tag = f"[{conditions_met}/{conditions_total} cond, {effective:.1f}/{total_max:.0f} eff ({eff_pct:.0%})]"
            out.signal = "STRONG_LONG"
            out.reason = " + ".join(_reason_parts()) + f" {_tag}"
            out.warnings = warnings
            return _cvd_return()
    # STRONG_LONG with 55%+ effective but blocked by funding
    elif eff_pct >= 0.55 and not cond_funding_ok:
        # Downgrade STRONG_LONG → LIGHT_LONG due to crowded funding
        if regime in ("MARKUP", "ACCUM") and divergence != "BEAR-DIV":
            out.signal = "LIGHT_LONG"
            out.reason = " + ".join(_reason_parts()) + " [downgraded: crowded funding]"
            out.warnings = warnings
            return _cvd_return()

    # --- ACCUMULATE: specific ACCUM regime conditions ---
    # Gated by Fear & Greed: only accumulate in Fear territory
    if (
        regime == "ACCUM"
        and z < 0
        and vol_low
        and confidence > CONF_ACCUM
        and mkt_consensus != "RISK-OFF"
        and heat < HEAT_ENTRY_ZONE
    ):
        if fear_greed <= FNG_FEAR:
            out.signal = "ACCUMULATE"
            out.reason = " + ".join(_reason_parts()) + f" [ACCUM + F&G={fear_greed}]"
            out.warnings = warnings
            return _cvd_return()
        else:
            # Not fearful enough — signal as WAIT with note
            warnings.append(f"ACCUM conditions met but F&G={fear_greed} > {FNG_FEAR} — waiting for fear")
            # Fall through to LIGHT_LONG evaluation

    # --- ACCUMULATE via absorption (non-CAP regimes) ---
    # Absorption = declining volume on dips → institutional accumulation.
    # Only valid in ACCUM/REACC regimes with supportive consensus.
    # CAP absorption has its own path below; MARKUP/BLOWOFF are above BMSB
    # where absorption is contradictory.
    if (
        is_absorption
        and regime in ("ACCUM", "REACC")
        and mkt_consensus != "RISK-OFF"
        and confidence > CONF_ACCUM      # 0.40
        and heat < HEAT_ENTRY_ZONE
    ):
        out.signal = "ACCUMULATE"
        out.reason = " + ".join(_reason_parts()) + " [absorption in " + regime + "]"
        out.warnings = warnings
        return _cvd_return()

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
        return _cvd_return()

    # --- LIGHT_LONG: >= 40% effective weighted score + supportive regime ---
    if eff_pct >= 0.40 and regime in ("MARKUP", "REACC", "ACCUM"):
        # MARKUP LIGHT_LONG: extended z (1.0-2.0) with decent confidence
        if (regime == "MARKUP" and 1.0 < z < z_blowoff
                and confidence > CONF_LIGHT
                and heat < HEAT_WARNING
                and mkt_consensus != "RISK-OFF"
                and divergence != "BEAR-DIV"):
            out.signal = "LIGHT_LONG"
            out.reason = " + ".join(_reason_parts()) + " [MARKUP extended]"
            out.warnings = warnings
            return _cvd_return()

        # MARKUP LIGHT_LONG: moderate z with conditions support
        if (regime == "MARKUP" and 0 < z < z_blowoff
                and confidence > CONF_LIGHT
                and heat < heat_block
                and mkt_consensus in ("RISK-ON", "MIXED")
                and divergence != "BEAR-DIV"):
            out.signal = "LIGHT_LONG"
            out.reason = " + ".join(_reason_parts()) + f" [{effective}/{len(conditions)} effective]"
            out.warnings = warnings
            return _cvd_return()

        # REACC LIGHT_LONG: needs supportive consensus + decent confidence
        if (regime == "REACC" and z < 0.5
                and confidence > CONF_LIGHT
                and heat < HEAT_WARNING
                and mkt_consensus in ("RISK-ON", "MIXED")):
            out.signal = "LIGHT_LONG"
            out.reason = " + ".join(_reason_parts()) + " [REACC + RISK-ON]"
            out.warnings = warnings
            return _cvd_return()

    # --- CAP without strong revival conditions ---
    if regime == "CAP" and z < -1.0 and confidence > CONF_REVIVAL:
        if is_absorption:
            out.signal = "ACCUMULATE"
            out.reason = " + ".join(_reason_parts()) + " [CAP absorption]"
            out.warnings = warnings
            return _cvd_return()

    # -----------------------------------------------------------------------
    # STEP 3: DEFAULT — WAIT
    # -----------------------------------------------------------------------

    out.signal = "WAIT"
    out.reason = " + ".join(_reason_parts()) + f" [{effective:.1f}/{total_max:.0f} effective ({eff_pct:.0%}) — insufficient]"
    out.warnings = warnings
    return _apply_cvd_modifiers(
        out, cvd_trend, cvd_divergence, spot_dominance,
        long_short_ratio, liquidation_24h_usd, top_trader_lsr,
    )
