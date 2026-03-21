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

The layer applies 6 independent filters in priority order:

    1. Cooldown / trailing     — prevents rapid flip/flop on the same signal
    2. BEAR-DIV flapping       — requires 2 consecutive BEAR-DIV bars before blocking
    3. Confidence stability    — freezes upgrades when confidence is swinging
    4. Heat / Z divergence     — warns + downgrades when heat and z move opposite
    5. Cross-TF tiebreaker     — resolves CONFLICTING confluence toward 1D
    6. Margin safety           — blocks new entries when margin utilisation is high

Filters are *additive* — each may inject warnings or override the signal but
hard exit signals (TRIM, TRIM_HARD, NO_LONG, RISK_OFF) are always preserved.

History storage
---------------
Filter state lives in ScanCache attributes added on first use:
    cache.signal_history:     Dict[str, List[str]]            — last 5 signals/symbol
    cache.confidence_history: Dict[str, List[float]]          — last 3 conf/symbol
    cache.divergence_history: Dict[str, List[Optional[str]]]  — last 3 div/symbol
    cache.prev_zscore:        Dict[str, float]                — previous z-score
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

# Filter 3: confidence stability
_CONF_SWING_THRESHOLD = 20.0     # % swing that marks an unstable confidence
_CONF_HISTORY_LEN = 3            # bars of confidence to keep

# Filter 4: heat/z divergence
_HEAT_RISE_MIN = 5               # heat must climb at least this many points
_Z_DROP_MIN = 0.15               # z must fall at least this much concurrently

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
    cache: Any,
    out: AgentOutput,
) -> str:
    """Filter 1: Cooldown / trailing.

    Rules:
    - Same entry signal must not repeat within _COOLDOWN_BARS bars.
    - After a hard exit signal, re-entry requires _FLIP_CONFIRM_BARS bars
      of the same entry signal before it is allowed through.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal  # exits always pass

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
    symbol: str,
    cache: Any,
    out: AgentOutput,
) -> str:
    """Filter 2: BEAR-DIV flapping guard.

    A single bar of BEAR-DIV is unreliable.  Require 2 consecutive BEAR-DIV
    bars before allowing it to block entry signals.  If only 1 bar detected,
    add a warning but let the signal through.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal

    div_history: List[Optional[str]] = cache.divergence_history.get(symbol, [])

    # If current bar has no BEAR-DIV, nothing to do
    if divergence != "BEAR-DIV":
        return signal

    # Current bar IS BEAR-DIV — check history
    prev_divs = div_history[-(_DIV_HISTORY_LEN - 1):]  # all but the current bar
    consecutive_bear = all(d == "BEAR-DIV" for d in prev_divs) if prev_divs else False

    if not consecutive_bear:
        # Only 1 bar of BEAR-DIV — warn but don't block
        out.alerts.append(
            "[bear-div] Single-bar BEAR-DIV detected — warning only, "
            "not blocking (requires 2 consecutive bars)"
        )
        out.filters_fired.append("bear_div:warn_only")
        return signal
    else:
        # 2+ consecutive BEAR-DIV — block entry signals
        if signal in _ENTRY_SIGNALS:
            out.alerts.append(
                "[bear-div] 2+ consecutive BEAR-DIV bars — blocking entry signal"
            )
            out.filters_fired.append("bear_div:blocked")
            return "WAIT"

    return signal


def _filter_confidence_stability(
    signal: str,
    confidence: float,
    symbol: str,
    cache: Any,
    out: AgentOutput,
) -> str:
    """Filter 3: Confidence stability.

    If confidence has swung by more than _CONF_SWING_THRESHOLD in the last
    3 bars, the regime read is noisy — freeze any signal upgrade to WAIT.
    Downgrades and exits are not affected.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal

    conf_hist: List[float] = cache.confidence_history.get(symbol, [])
    if len(conf_hist) < 2:
        return signal

    swing = max(conf_hist) - min(conf_hist)
    if swing > _CONF_SWING_THRESHOLD and signal in _ENTRY_SIGNALS:
        out.alerts.append(
            f"[conf-stability] Confidence swinging {swing:.1f}% over last "
            f"{len(conf_hist)} bars — entry frozen at WAIT"
        )
        out.filters_fired.append("conf_stability:frozen")
        return "WAIT"

    return signal


def _filter_heat_z_divergence(
    signal: str,
    symbol: str,
    current_heat: int,
    current_z: float,
    cache: Any,
    out: AgentOutput,
) -> str:
    """Filter 4: Heat / Z structural divergence.

    When heat is rising while z-score is falling (distribution forming), or
    when heat is falling while z is spiking (momentum without structural support),
    we warn and downgrade STRONG_LONG → LIGHT_LONG.
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal

    prev_heat: int = getattr(cache, "prev_heat", {}).get(symbol, current_heat)
    prev_z: float = cache.prev_zscore.get(symbol, current_z)

    heat_rising = (current_heat - prev_heat) >= _HEAT_RISE_MIN
    z_falling = (prev_z - current_z) >= _Z_DROP_MIN

    if heat_rising and z_falling and signal in _ENTRY_SIGNALS:
        out.alerts.append(
            f"[heat-z-div] Heat rising ({prev_heat}→{current_heat}) "
            f"while Z falling ({prev_z:.2f}→{current_z:.2f}) — "
            "structural divergence, downgrading STRONG_LONG→LIGHT_LONG"
        )
        out.filters_fired.append("heat_z_div:downgrade")
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
    """
    if signal in _HARD_EXIT_SIGNALS:
        return signal

    if not confluence:
        return signal

    label = confluence.get("label", "")
    if label != "CONFLICTING":
        return signal

    # Only act on 4H — 1D is the reference timeframe
    if timeframe != "4h":
        return signal

    signal_1d = confluence.get("signal_1d", "")
    regime_4h = confluence.get("regime_4h", "")
    regime_1d = confluence.get("regime_1d", "")

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
    adjusted_signal: str,
    confidence: float,
    divergence: Optional[str],
    current_z: float,
    cache: Any,
) -> None:
    _push(cache.signal_history, symbol, adjusted_signal, _SIGNAL_HISTORY_LEN)
    _push(cache.confidence_history, symbol, confidence, _CONF_HISTORY_LEN)
    _push(cache.divergence_history, symbol, divergence, _DIV_HISTORY_LEN)
    cache.prev_zscore[symbol] = current_z


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

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
        Open positions for margin safety check.  May be empty.
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
    original_signal = scan_result.get("signal", "WAIT")
    confidence = float(scan_result.get("confidence", 0.0))
    divergence = scan_result.get("divergence")
    current_heat = int(scan_result.get("heat", 0))
    current_z = float(scan_result.get("zscore", 0.0))
    confluence = scan_result.get("confluence")
    if isinstance(confluence, object) and hasattr(confluence, "__dict__"):
        # Pydantic model — convert to dict
        try:
            confluence = confluence.model_dump()
        except AttributeError:
            confluence = vars(confluence)

    out = AgentOutput(
        adjusted_signal=original_signal,
        original_signal=original_signal,
    )

    signal = original_signal

    # ---------- apply filters in priority order ----------

    # F1: Cooldown / trailing (catches flip-flop before anything else)
    signal = _filter_cooldown(signal, symbol, cache, out)

    # F2: BEAR-DIV flapping (single-bar divergence should not block entries)
    signal = _filter_bear_div_flapping(signal, divergence, symbol, cache, out)

    # F3: Confidence stability (noisy regimes should not drive upgrades)
    signal = _filter_confidence_stability(signal, confidence, symbol, cache, out)

    # F4: Heat / Z structural divergence (distribution forming)
    signal = _filter_heat_z_divergence(signal, symbol, current_heat, current_z, cache, out)

    # F5: Cross-TF tiebreaker (CONFLICTING confluence → defer to 1D)
    signal = _filter_cross_tf_tiebreaker(signal, timeframe, confluence, out)

    # F6: Margin safety (no new entries when overextended)
    signal = _filter_margin_safety(signal, positions, out)

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
        if p_symbol.split("/")[0] == symbol.split("/")[0]:
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
            out.position_actions.append(action)

    # Mutate scan_result in-place (additive fields only)
    scan_result["agent_signal"] = signal if signal != original_signal else None
    scan_result["agent_warnings"] = out.alerts
    scan_result["agent_filters_fired"] = out.filters_fired

    # Update persistent history with the ADJUSTED signal
    _update_history(symbol, signal, confidence, divergence, current_z, cache)

    if out.filters_fired:
        logger.debug(
            "Agent [%s/%s] %s→%s filters=%s",
            symbol, timeframe, original_signal, signal, out.filters_fired,
        )

    return out
