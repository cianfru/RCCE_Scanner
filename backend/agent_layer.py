"""
agent_layer.py
~~~~~~~~~~~~~~
Post-synthesis agent layer: a pure signal transformer that sits between
signal_synthesizer.py and position_monitor.py in the scan pipeline.

Contract
--------
    from agent_layer import process, AgentOutput

    output = process(scan_result_dict, positions, cache)
    # scan_result_dict is modified in-place AND AgentOutput returned

The layer applies 7 independent filters in priority order:

    1. Cooldown / trailing     — prevents rapid flip/flop on the same signal
    2. BEAR-DIV flapping       — requires 2 consecutive BEAR-DIV bars before blocking
    3. Heat / Z divergence     — warns + downgrades when heat and z move opposite
    4. Cross-TF tiebreaker     — resolves CONFLICTING confluence toward 1D
    5. Margin safety           — blocks new entries when margin utilisation is high
    6. Anomaly context         — squeeze setups, crowded funding blocks, anomaly warnings
    7. Signal inertia          — holds entry signals through brief downgrades (2-bar confirm)

Filters are *additive* — each may inject warnings or override the signal but
hard exit signals (TRIM, TRIM_HARD, NO_LONG, RISK_OFF) are always preserved.

History storage
---------------
Filter state lives in ScanCache attributes added on first use:
    cache.signal_history:     Dict[str, List[str]]            — last 5 signals/symbol
    cache.confidence_history: Dict[str, List[float]]          — last 48 conf/symbol
    cache.divergence_history: Dict[str, List[Optional[str]]]  — last 2 div/symbol
    cache.prev_zscore:        Dict[str, float]                — previous z-score
    cache.prev_heat:          Dict[str, int]                  — previous heat score
    cache.signal_inertia:     Dict[str, Dict]                 — per-symbol inertia state
    cache.funding_history:    Dict[str, List[float]]          — last 48 funding rates
    cache.oi_history:         Dict[str, List[float]]          — last 48 OI values (USD)
    cache.oi_change_history:  Dict[str, List[float]]          — last 48 OI change %
    cache.lsr_history:        Dict[str, List[float]]          — last 48 retail LSR
    cache.bsr_history:        Dict[str, List[float]]          — last 48 buy/sell ratios
    cache.spot_ratio_history: Dict[str, List[float]]          — last 48 spot/futures ratios
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Signals that must never be overridden or blocked by the agent layer
_HARD_EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "NO_LONG", "RISK_OFF"}

# Signals that are "entry" signals (eligible for filtering)
_ENTRY_SIGNALS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED"}

# Signal rank (lower = more bearish)
_SIGNAL_RANK: Dict[str, int] = {
    "RISK_OFF": 0, "NO_LONG": 1, "TRIM_HARD": 2, "TRIM": 3,
    "WAIT": 4, "REVIVAL_SEED": 5, "ACCUMULATE": 6,
    "LIGHT_LONG": 7, "STRONG_LONG": 8,
}

# Filter 1: cooldown
_COOLDOWN_BARS = 2               # min bars before repeating same entry signal
_FLIP_CONFIRM_BARS = 2           # bars required to re-enter after a hard exit

# Confidence history (kept for charting, no longer used for filtering)
_CONF_HISTORY_LEN = 48           # bars of confidence to keep (for sparkline chart)
_POS_HISTORY_LEN = 48            # bars of positioning metrics to keep

# Filter 6: signal inertia
_DOWNGRADE_CONFIRM_BARS = 2      # consecutive bars needed to confirm a voluntary downgrade

# Filter 4: heat/z divergence
_HEAT_RISE_MIN = 5               # heat must climb at least this many points (strict path)
_Z_DROP_MIN = 0.15               # z must fall at least this much (strict path)
_Z_SOLO_DROP_MIN = 0.50          # z-drop alone triggers at lower heat threshold (fallback)
_HEAT_RISE_SOFT = 2              # softer heat threshold for z-solo fallback path

# Filter 6: margin safety
_MARGIN_BLOCK_PCT = 0.80         # block new entries when margin > 80 %

# History lengths
_SIGNAL_HISTORY_LEN = 5
_DIV_HISTORY_LEN = 2             # only need last 2 for flap detection


# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------

@dataclass
class AgentOutput:
    """Returned by process().  scan_result is also modified in-place."""
    adjusted_signal: str = "WAIT"
    original_signal: str = "WAIT"
    alerts: List[str] = field(default_factory=list)
    reasoning: str = ""
    position_actions: List[Dict[str, Any]] = field(default_factory=list)
    filters_fired: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _ensure_history(cache: Any) -> None:
    """Lazily init history dicts on the ScanCache object."""
    if not hasattr(cache, "signal_history"):
        cache.signal_history: Dict[str, List[str]] = {}
    if not hasattr(cache, "confidence_history"):
        cache.confidence_history: Dict[str, List[float]] = {}
    if not hasattr(cache, "divergence_history"):
        cache.divergence_history: Dict[str, List[Optional[str]]] = {}
    if not hasattr(cache, "prev_zscore"):
        cache.prev_zscore: Dict[str, float] = {}
    if not hasattr(cache, "prev_heat"):
        cache.prev_heat: Dict[str, int] = {}
    if not hasattr(cache, "signal_inertia"):
        cache.signal_inertia: Dict[str, Dict] = {}
    if not hasattr(cache, "smoothed_confidence"):
        cache.smoothed_confidence: Dict[str, float] = {}
    # Positioning metric histories (48 ticks each)
    for attr in ("funding_history", "oi_history", "oi_change_history",
                 "lsr_history", "bsr_history", "spot_ratio_history"):
        if not hasattr(cache, attr):
            setattr(cache, attr, {})


# EMA periods per timeframe (4h: 12h lookback, 1d: 2d lookback)
_EMA_PERIOD: Dict[str, int] = {"4h": 3, "1d": 2}


def _smooth_confidence(
    raw_conf: float, symbol: str, timeframe: str, cache: Any,
) -> float:
    """Apply EMA smoothing to raw confidence. Prevents single-bar noise."""
    key = f"{symbol}:{timeframe}"
    prev = cache.smoothed_confidence.get(key, raw_conf)
    period = _EMA_PERIOD.get(timeframe, 3)
    alpha = 2.0 / (period + 1)
    smoothed = alpha * raw_conf + (1.0 - alpha) * prev
    cache.smoothed_confidence[key] = smoothed
    return smoothed


def _push(hist: Dict[str, list], key: str, value: Any, maxlen: int) -> None:
    """Append value to hist[key], keeping last maxlen entries."""
    if key not in hist:
        hist[key] = []
    hist[key].append(value)
    if len(hist[key]) > maxlen:
        hist[key] = hist[key][-maxlen:]


# ---------------------------------------------------------------------------
# Individual filters
# ---------------------------------------------------------------------------

def _filter_cooldown(
    signal: str,
    symbol: str,
    is_positioned: bool,
    cache: Any,
    out: AgentOutput,
) -> str:
    """Filter 1: Cooldown / trailing.

    Rules:
    - Same entry signal must not repeat within _COOLDOWN_BARS bars.
    - After a hard exit signal, re-entry requires _FLIP_CONFIRM_BARS bars
      of the same entry signal before it is allowed through.

    Both rules are skipped when no open position exists for this symbol.
    Without a position there is nothing to protect — applying cooldown would
    only add phantom friction to a legitimate re-entry after a stop-loss or
    manual close.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal  # exits always pass

    # No position — cooldown rules don't apply
    if not is_positioned:
        return signal

    history: List[str] = cache.signal_history.get(symbol, [])
    if not history:
        return signal

    # Rule A: same entry signal repeated too quickly
    if signal in _ENTRY_SIGNALS:
        recent = history[-_COOLDOWN_BARS:]
        if len(recent) >= _COOLDOWN_BARS and all(s == signal for s in recent):
            # Already emitted this same entry N times — likely already positioned
            out.alerts.append(
                f"[cooldown] {signal} repeated {_COOLDOWN_BARS}+ bars — "
                "suppressed (likely already positioned)"
            )
            out.filters_fired.append("cooldown:repeated")
            return "WAIT"

    # Rule B: rapid flip-flop — hard exit then immediate re-entry
    if signal in _ENTRY_SIGNALS:
        exit_positions = [
            i for i, s in enumerate(history)
            if s in _HARD_EXIT_SIGNALS
        ]
        if exit_positions:
            last_exit_idx = exit_positions[-1]
            bars_since_exit = len(history) - 1 - last_exit_idx
            # Check that re-entry signal has appeared _FLIP_CONFIRM_BARS times
            # consistently since the exit
            post_exit = history[last_exit_idx + 1:]
            entry_run = sum(1 for s in post_exit if s == signal)
            if bars_since_exit < _FLIP_CONFIRM_BARS and entry_run < _FLIP_CONFIRM_BARS:
                out.alerts.append(
                    f"[cooldown] {signal} after recent hard exit — "
                    f"requires {_FLIP_CONFIRM_BARS} confirmation bars ({bars_since_exit} so far)"
                )
                out.filters_fired.append("cooldown:flip-confirm")
                return "ACCUMULATE" if signal in ("STRONG_LONG", "LIGHT_LONG") else "WAIT"

    return signal


def _filter_bear_div_flapping(
    signal: str,
    divergence: Optional[str],
    regime: str,
    symbol: str,
    cache: Any,
    out: AgentOutput,
) -> str:
    """Filter 2: BEAR-DIV flapping guard.

    A single bar of BEAR-DIV is unreliable.  Require 2 consecutive BEAR-DIV
    bars before allowing it to block entry signals.  If only 1 bar detected,
    add a warning but let the signal through.

    Regime context modulates severity:
    - MARKDOWN: BEAR-DIV is the regime, not a divergence — filter skipped entirely.
    - REACC:    Bearish divergence is structurally expected during a reaccumulation
                dip.  Even 2 consecutive bars produce a warning only, not a block.
                The signal passes through unchanged.
    - MARKUP / BLOWOFF / other: full filter applies.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal

    # In MARKDOWN the price is already declining — BEAR-DIV is the regime, not a warning
    if regime == "MARKDOWN":
        return signal

    div_history: List[Optional[str]] = cache.divergence_history.get(symbol, [])

    # If current bar has no BEAR-DIV, nothing to do
    if divergence != "BEAR-DIV":
        return signal

    # Current bar IS BEAR-DIV — check history
    prev_divs = div_history[-(_DIV_HISTORY_LEN - 1):]  # all but the current bar
    consecutive_bear = all(d == "BEAR-DIV" for d in prev_divs) if prev_divs else False

    if not consecutive_bear:
        # Only 1 bar of BEAR-DIV — warn but don't block regardless of regime
        out.alerts.append(
            "[bear-div] Single-bar BEAR-DIV detected — warning only, "
            "not blocking (requires 2 consecutive bars)"
        )
        out.filters_fired.append("bear_div:warn_only")
        return signal

    # 2+ consecutive BEAR-DIV bars
    if regime == "REACC":
        # Divergence is expected during reaccumulation dip — elevated warning, no block
        out.alerts.append(
            "[bear-div] 2-bar BEAR-DIV in REACC regime — elevated warning, "
            "not blocking (divergence expected during reaccumulation dip)"
        )
        out.filters_fired.append("bear_div:reacc_warn")
        return signal

    if signal in _ENTRY_SIGNALS:
        out.alerts.append(
            "[bear-div] 2+ consecutive BEAR-DIV bars — blocking entry signal"
        )
        out.filters_fired.append("bear_div:blocked")
        return "WAIT"

    return signal


def _filter_signal_inertia(
    signal: str,
    symbol: str,
    cache: Any,
    out: AgentOutput,
) -> str:
    """Filter 6: Signal-level inertia.

    Once an entry signal fires, it holds through brief deterioration.
    Voluntary downgrades (STRONG→LIGHT→WAIT) require _DOWNGRADE_CONFIRM_BARS
    consecutive bars at the lower signal before confirming.

    Rules:
    - Hard exits (TRIM, RISK_OFF, etc.): always immediate, no inertia
    - Entries from WAIT: always immediate, no delay
    - Upgrades (LIGHT→STRONG): always immediate
    - Downgrades (STRONG→LIGHT, LIGHT→WAIT): require 2 consecutive bars
    """
    # Use timeframe-scoped key so 4h and 1d don't interfere
    tf_key = f"{symbol}:{cache._current_timeframe}" if hasattr(cache, "_current_timeframe") else symbol

    if signal in _HARD_EXIT_SIGNALS:
        cache.signal_inertia[tf_key] = {"signal": signal, "downgrade_count": 0}
        return signal

    prev = cache.signal_inertia.get(tf_key, {"signal": "WAIT", "downgrade_count": 0})
    prev_sig = prev["signal"]

    # No inertia from WAIT or non-entry previous signals — new entries fire immediately
    if prev_sig not in _ENTRY_SIGNALS:
        cache.signal_inertia[tf_key] = {"signal": signal, "downgrade_count": 0}
        return signal

    # Previous was an entry signal — check rank change
    prev_rank = _SIGNAL_RANK.get(prev_sig, 4)
    curr_rank = _SIGNAL_RANK.get(signal, 4)

    if curr_rank >= prev_rank:
        # Upgrade or same level — immediate
        cache.signal_inertia[tf_key] = {"signal": signal, "downgrade_count": 0}
        return signal

    # Downgrade detected — require confirmation
    count = prev["downgrade_count"] + 1
    if count >= _DOWNGRADE_CONFIRM_BARS:
        # Confirmed downgrade after N consecutive bars
        cache.signal_inertia[tf_key] = {"signal": signal, "downgrade_count": 0}
        out.alerts.append(
            f"[inertia] Downgrade confirmed ({count} bars): {prev_sig} \u2192 {signal}"
        )
        out.filters_fired.append("inertia:confirmed_downgrade")
        return signal
    else:
        # Hold previous signal — downgrade not yet confirmed
        cache.signal_inertia[tf_key] = {"signal": prev_sig, "downgrade_count": count}
        out.alerts.append(
            f"[inertia] Holding {prev_sig} (downgrade to {signal} needs "
            f"{_DOWNGRADE_CONFIRM_BARS - count} more bar(s))"
        )
        out.filters_fired.append("inertia:holding")
        return prev_sig


def _filter_heat_z_divergence(
    signal: str,
    symbol: str,
    current_heat: int,
    current_z: float,
    cache: Any,
    out: AgentOutput,
) -> str:
    """Filter 4: Heat / Z structural divergence.

    Strict path: heat rising while z-score is falling (classic distribution).
    Fallback path: z falling sharply on its own with any meaningful heat uptick
                   (momentum loss without requiring full heat surge).

    Both paths downgrade STRONG_LONG → LIGHT_LONG only.  Never blocks outright.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal

    if signal not in _ENTRY_SIGNALS:
        return signal

    prev_heat: int = cache.prev_heat.get(symbol, current_heat)
    prev_z: float = cache.prev_zscore.get(symbol, current_z)

    heat_delta = current_heat - prev_heat
    z_delta = prev_z - current_z  # positive = z fell

    heat_rising = heat_delta >= _HEAT_RISE_MIN
    z_falling = z_delta >= _Z_DROP_MIN

    # Strict path: both heat and z moving together
    if heat_rising and z_falling:
        out.alerts.append(
            f"[heat-z-div] Heat rising ({prev_heat}→{current_heat}) "
            f"while Z falling ({prev_z:.2f}→{current_z:.2f}) — "
            "structural divergence, downgrading STRONG_LONG→LIGHT_LONG"
        )
        out.filters_fired.append("heat_z_div:downgrade")
        if signal == "STRONG_LONG":
            return "LIGHT_LONG"

    # Fallback path: steep z-drop with even a modest heat uptick
    elif z_delta >= _Z_SOLO_DROP_MIN and heat_delta >= _HEAT_RISE_SOFT:
        out.alerts.append(
            f"[heat-z-div] Steep Z-drop ({prev_z:.2f}→{current_z:.2f}, "
            f"Δ{z_delta:.2f}) with heat uptick ({prev_heat}→{current_heat}) — "
            "momentum loss, downgrading STRONG_LONG→LIGHT_LONG"
        )
        out.filters_fired.append("heat_z_div:z_solo_downgrade")
        if signal == "STRONG_LONG":
            return "LIGHT_LONG"

    return signal


def _filter_cross_tf_tiebreaker(
    signal: str,
    timeframe: str,
    confluence: Optional[Dict],
    out: AgentOutput,
) -> str:
    """Filter 5: Cross-TF tiebreaker.

    When confluence label = CONFLICTING:
    - Default to 1D signal (captured in confluence.signal_1d)
    - Exception: if current bar regime is BLOWOFF on 4H while 1D is MARKUP,
      the 4H urgency takes precedence (imminent exit).

    This filter only runs on the 4H timeframe scan since 1D is the authority.

    Special case (runs regardless of confluence label):
    - If 1D regime is BLOWOFF, cap any bullish 4H entry signal to WAIT.
      Distribution phase on the daily makes new entries unwarranted even if
      the synthesizer missed the cross-TF conflict.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal

    if not confluence:
        return signal

    regime_1d = confluence.get("regime_1d", "")

    # Unconditional 1D BLOWOFF cap — runs before the CONFLICTING label check
    if regime_1d == "BLOWOFF" and timeframe == "4h" and signal in _ENTRY_SIGNALS:
        out.alerts.append(
            "[cross-tf] 1D regime is BLOWOFF — capping bullish 4H signal to WAIT "
            "(distribution phase, new entries not warranted)"
        )
        out.filters_fired.append("cross_tf:1d_blowoff_cap")
        return "WAIT"

    label = confluence.get("label", "")
    if label != "CONFLICTING":
        return signal

    # Only act on 4H — 1D is the reference timeframe
    if timeframe != "4h":
        return signal

    signal_1d = confluence.get("signal_1d", "")
    regime_4h = confluence.get("regime_4h", "")

    # BLOWOFF exception: 4H showing exit urgency while 1D is still bullish
    if regime_4h == "BLOWOFF" and regime_1d in ("MARKUP", "REACC"):
        out.alerts.append(
            "[cross-tf] 4H BLOWOFF overrides CONFLICTING confluence — "
            "imminent exit signal preserved"
        )
        out.filters_fired.append("cross_tf:blowoff_override")
        return signal  # keep the 4H signal (likely a trim)

    # Default: defer to 1D signal
    if signal_1d and signal_1d != signal:
        signal_1d_rank = _SIGNAL_RANK.get(signal_1d, 4)
        current_rank = _SIGNAL_RANK.get(signal, 4)

        # Only override if 1D is more conservative (lower rank = less bullish)
        if signal_1d_rank < current_rank:
            out.alerts.append(
                f"[cross-tf] CONFLICTING confluence → deferring 4H ({signal}) "
                f"to 1D authority ({signal_1d})"
            )
            out.filters_fired.append("cross_tf:deferred_to_1d")
            return signal_1d

    return signal


def _filter_margin_safety(
    signal: str,
    positions: List[Any],
    out: AgentOutput,
) -> str:
    """Filter 6: Margin safety.

    When open positions represent > _MARGIN_BLOCK_PCT of available capital
    (approximated from position sizes), block new entry signals.

    Hard exits always pass through.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal

    if not positions:
        return signal

    # Sum up size_pct or size_usd across positions to estimate utilisation
    total_alloc = 0.0
    for p in positions:
        if hasattr(p, "size_pct"):
            total_alloc += getattr(p, "size_pct", 0.0)
        elif isinstance(p, dict):
            total_alloc += p.get("size_pct", 0.0)

    if total_alloc >= _MARGIN_BLOCK_PCT and signal in _ENTRY_SIGNALS:
        out.alerts.append(
            f"[margin] Position allocation at {total_alloc:.0%} — "
            "blocking new entries until below 80%"
        )
        out.filters_fired.append("margin:blocked")
        return "WAIT"

    return signal


# ---------------------------------------------------------------------------
# History update (called AFTER all filters so we persist the adjusted state)
# ---------------------------------------------------------------------------

def _update_history(
    symbol: str,
    timeframe: str,
    adjusted_signal: str,
    confidence: float,
    divergence: Optional[str],
    current_z: float,
    current_heat: int,
    cache: Any,
    positioning: Optional[Dict[str, Any]] = None,
    bsr: float = 1.0,
) -> None:
    tf_key = f"{symbol}:{timeframe}"
    _push(cache.signal_history, tf_key, adjusted_signal, _SIGNAL_HISTORY_LEN)
    # Push EMA-smoothed confidence (not raw) so sparkline is smooth
    smoothed = _smooth_confidence(confidence, symbol, timeframe, cache)
    _push(cache.confidence_history, tf_key, round(smoothed, 1), _CONF_HISTORY_LEN)
    _push(cache.divergence_history, tf_key, divergence, _DIV_HISTORY_LEN)
    cache.prev_zscore[symbol] = current_z
    cache.prev_heat[symbol] = current_heat

    # Push positioning metric histories for sparklines
    if positioning:
        pos = positioning
        if pos.get("funding_rate") is not None:
            _push(cache.funding_history, tf_key, round(pos["funding_rate"] * 100, 4), _POS_HISTORY_LEN)
        if pos.get("oi_value") and pos["oi_value"] > 0:
            _push(cache.oi_history, tf_key, round(pos["oi_value"]), _POS_HISTORY_LEN)
        if pos.get("oi_change_pct") is not None:
            _push(cache.oi_change_history, tf_key, round(pos["oi_change_pct"], 2), _POS_HISTORY_LEN)
        lsr = pos.get("long_short_ratio")
        if lsr and lsr != 1.0:
            _push(cache.lsr_history, tf_key, round(lsr, 3), _POS_HISTORY_LEN)
        if bsr and bsr != 1.0:
            _push(cache.bsr_history, tf_key, round(bsr, 3), _POS_HISTORY_LEN)
        spot = pos.get("spot_futures_ratio")
        if spot and spot > 0:
            _push(cache.spot_ratio_history, tf_key, round(spot, 3), _POS_HISTORY_LEN)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _filter_anomaly_context(
    signal: str,
    symbol: str,
    cache: Any,
    out: AgentOutput,
) -> str:
    """F6: Anomaly context — informational warnings from anomaly detector.

    Purely informational — never changes the signal. Attaches warnings so
    the user and the LLM assistant are aware of unusual activity.

    The only exception: EXTREME_FUNDING SHORT + WAIT → ACCUMULATE (squeeze
    setup). This is the one case where an anomaly represents a tradeable
    opportunity that the normal signal logic can't express.
    """
    anomalies = getattr(cache, "anomalies", [])
    if not anomalies:
        return signal

    sym_anomalies = [a for a in anomalies if a.get("symbol") == symbol]
    if not sym_anomalies:
        return signal

    for a in sym_anomalies:
        atype = a.get("anomaly_type", "")
        severity = a.get("severity", "")
        direction = a.get("direction", "")
        context = a.get("context", "")

        # --- Extreme funding ---
        if atype == "EXTREME_FUNDING":
            if direction == "SHORT" and signal == "WAIT":
                # Only signal change: squeeze setup upgrade
                signal = "ACCUMULATE"
                out.alerts.append(f"Squeeze setup: {context}")
                out.filters_fired.append("anomaly:funding_squeeze_upgrade")
            else:
                out.alerts.append(f"Extreme funding: {context}")
                out.filters_fired.append("anomaly:extreme_funding_warn")

        # --- OI surge ---
        elif atype == "OI_SURGE":
            out.alerts.append(f"OI surge: {context}")
            out.filters_fired.append("anomaly:oi_surge_warn")

        # --- Volume spike ---
        elif atype == "VOLUME_SPIKE":
            out.alerts.append(f"Volume spike: {context}")
            out.filters_fired.append("anomaly:volume_spike_warn")

        # --- LSR extreme: crowded positioning ---
        elif atype == "LSR_EXTREME":
            if direction == "LONG" and signal in _ENTRY_SIGNALS:
                out.alerts.append(f"Crowd long warning: {context}")
                out.filters_fired.append("anomaly:lsr_crowd_long_warn")
            elif direction == "SHORT" and signal == "WAIT":
                out.alerts.append(f"Crowd short — squeeze potential: {context}")
                out.filters_fired.append("anomaly:lsr_squeeze_hint")

        # --- CVD extreme ---
        elif atype == "CVD_EXTREME":
            if severity == "critical":
                out.alerts.append(f"CVD extreme: {context}")
                out.filters_fired.append("anomaly:cvd_extreme_warn")

    return signal


def process(
    scan_result: Dict[str, Any],
    positions: List[Any],
    cache: Any,
) -> AgentOutput:
    """Apply all agent filters to a single scan result.

    Parameters
    ----------
    scan_result : dict
        A single result dict from the scanner pipeline (mutated in-place).
    positions : list
        Open positions for margin safety check and cooldown context.  May be empty.
    cache : ScanCache
        The module-level ScanCache instance (for persistent history).

    Returns
    -------
    AgentOutput
        Contains adjusted_signal, alerts, reasoning, and which filters fired.
        The scan_result dict is also updated with agent-specific fields.
    """
    _ensure_history(cache)

    symbol = scan_result.get("symbol", "")
    timeframe = scan_result.get("timeframe", "")
    # Stash current timeframe so filters can scope state per-TF
    cache._current_timeframe = timeframe
    original_signal = scan_result.get("signal", "WAIT")
    confidence = float(scan_result.get("confidence", 0.0))
    divergence = scan_result.get("divergence")
    regime = scan_result.get("regime", "")
    current_heat = int(scan_result.get("heat", 0))
    current_z = float(scan_result.get("zscore", 0.0))
    confluence = scan_result.get("confluence")
    if isinstance(confluence, object) and hasattr(confluence, "__dict__"):
        # Pydantic model — convert to dict
        try:
            confluence = confluence.model_dump()
        except AttributeError:
            confluence = vars(confluence)

    # Determine if this symbol has an open position (used by cooldown filter)
    symbol_base = symbol.split("/")[0]
    is_positioned = any(
        (getattr(p, "symbol", None) or (p.get("symbol") if isinstance(p, dict) else "")
         or "").split("/")[0] == symbol_base
        for p in positions
    )

    out = AgentOutput(
        adjusted_signal=original_signal,
        original_signal=original_signal,
    )

    signal = original_signal

    # ---------- apply filters in priority order ----------

    # F1: Cooldown / trailing (catches flip-flop before anything else)
    signal = _filter_cooldown(signal, symbol, is_positioned, cache, out)

    # F2: BEAR-DIV flapping (single-bar divergence should not block entries)
    signal = _filter_bear_div_flapping(signal, divergence, regime, symbol, cache, out)

    # F3: Heat / Z structural divergence (distribution forming)
    signal = _filter_heat_z_divergence(signal, symbol, current_heat, current_z, cache, out)

    # F4: Cross-TF tiebreaker (CONFLICTING confluence → defer to 1D)
    signal = _filter_cross_tf_tiebreaker(signal, timeframe, confluence, out)

    # F5: Margin safety (no new entries when overextended)
    signal = _filter_margin_safety(signal, positions, out)

    # F6: Anomaly context (squeeze setups, crowded funding blocks, warnings)
    signal = _filter_anomaly_context(signal, symbol, cache, out)

    # F7: Signal inertia (LAST — holds entries through brief downgrades)
    signal = _filter_signal_inertia(signal, symbol, cache, out)

    # ---------- finalise ----------

    out.adjusted_signal = signal
    out.reasoning = "; ".join(out.alerts) if out.alerts else "No agent filters fired"

    # Build position actions for currently held coins
    for p in positions:
        p_symbol = (
            getattr(p, "symbol", None) or
            (p.get("symbol") if isinstance(p, dict) else None) or
            ""
        )
        if p_symbol.split("/")[0] == symbol_base:
            action: Dict[str, Any] = {"symbol": p_symbol, "signal": signal}
            if signal in _HARD_EXIT_SIGNALS:
                action["action"] = "EXIT"
                action["reason"] = out.reasoning
            elif signal in _ENTRY_SIGNALS:
                action["action"] = "HOLD"
                action["reason"] = "Signal confirmed — hold position"
            else:
                action["action"] = "MONITOR"
                action["reason"] = f"Signal weakened to {signal}"

            # F2 gap: if BEAR-DIV confirmed on a held position, attach a warning
            # even though no signal change occurred (position was opened before divergence)
            if "bear_div:blocked" in out.filters_fired or "bear_div:reacc_warn" in out.filters_fired:
                action["bear_div_warning"] = (
                    "Confirmed BEAR-DIV on held position — monitor for structural breakdown"
                )

            out.position_actions.append(action)

    # Mutate scan_result in-place (additive fields only)
    scan_result["agent_signal"] = signal if signal != original_signal else None
    scan_result["agent_warnings"] = out.alerts
    scan_result["agent_filters_fired"] = out.filters_fired

    # Update persistent history with the ADJUSTED signal
    _update_history(
        symbol, timeframe, signal, confidence, divergence, current_z, current_heat, cache,
        positioning=scan_result.get("positioning"),
        bsr=scan_result.get("buy_sell_ratio", 1.0),
    )

    # Attach smoothed confidence for downstream use
    tf_key = f"{symbol}:{timeframe}"
    scan_result["smoothed_confidence"] = cache.smoothed_confidence.get(tf_key, confidence)

    if out.filters_fired:
        logger.debug(
            "Agent [%s/%s] %s→%s filters=%s",
            symbol, timeframe, original_signal, signal, out.filters_fired,
        )

    return out
