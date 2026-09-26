"""
confluence.py
~~~~~~~~~~~~~
Multi-timeframe confluence scoring.

Compares 4h and 1d scan results for each symbol to determine how well
the two timeframes agree.  High confluence = high conviction signal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regime families for comparison
# ---------------------------------------------------------------------------

_BULLISH = {"MARKUP", "REACC", "ACCUM"}
_BEARISH = {"MARKDOWN", "CAP", "BLOWOFF"}
_ENTRY_SIGNALS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}
_EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}
_MAX_POINTS = 90  # 40 + 5 regime, 30 signal, 15 heat


def unified_signal(result_4h: Optional[dict], result_1d: Optional[dict]) -> str:
    """One cross-timeframe decision for the API, UI and outcome tracker."""
    rows = [r for r in (result_4h, result_1d) if r is not None]
    valid = [r for r in rows if r.get("signal_status") != "unavailable"]
    exits = [r["signal"] for r in valid if r.get("signal") in _EXIT_SIGNALS]
    if exits:
        rank = {"NO_LONG": 0, "TRIM": 1, "TRIM_HARD": 2, "RISK_OFF": 3}
        return max(exits, key=rank.get)
    if len(valid) != 2:
        return "WAIT"
    signals = [r.get("signal", "WAIT") for r in valid]
    if signals == ["LIGHT_SHORT", "LIGHT_SHORT"]:
        return "LIGHT_SHORT"
    if "LIGHT_SHORT" in signals:
        return "WAIT"
    regimes = [r.get("regime", "FLAT") for r in valid]
    entries = [s for s in signals if s in _ENTRY_SIGNALS]
    if any(r in _BEARISH for r in regimes):
        return "WAIT"
    # A timeframe the engine has blocked (e.g. below the weekly BMSB) cannot lend
    # its trend to the other timeframe's entry.
    if any(r.get("entry_blocked") for r in valid):
        return "WAIT"
    if entries and (all(r in _BULLISH for r in regimes) or len(entries) == 2):
        rank = {"REVIVAL_SEED": 0, "REVIVAL_SEED_CONFIRMED": 1,
                "ACCUMULATE": 2, "LIGHT_LONG": 3, "STRONG_LONG": 4}
        return min(entries, key=rank.get)
    return "WAIT"


# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------

@dataclass
class ConfluenceResult:
    """Cross-timeframe confluence analysis for a single symbol."""
    score: int = 0                       # 0-100 confluence score
    label: str = "UNKNOWN"               # STRONG | MODERATE | WEAK | CONFLICTING
    regime_aligned: bool = False         # Both TFs in same regime family
    signal_aligned: Optional[bool] = False  # Both TFs same signal direction; None when both WAIT
    regime_4h: str = ""
    regime_1d: str = ""
    signal_4h: str = ""
    signal_1d: str = ""


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def compute_confluence(
    result_4h: Optional[dict],
    result_1d: Optional[dict],
) -> ConfluenceResult:
    """Score how well 4h and 1d timeframes align for a symbol.

    Raw points (90 at most):
    - Regime family match: +40 (+5 for the exact same regime)
    - Signal direction match: +30
    - Heat agreement: +15

    The published score is the raw points rescaled to 0-100. Labels are taken
    from the raw points, so executor sizing is unchanged by the rescale:
    - STRONG: >= 75
    - MODERATE: >= 50
    - WEAK: >= 25
    - CONFLICTING: < 25
    """
    out = ConfluenceResult()

    if result_4h is None or result_1d is None:
        out.label = "UNKNOWN"
        return out

    regime_4h = result_4h.get("regime", "FLAT").upper()
    regime_1d = result_1d.get("regime", "FLAT").upper()
    signal_4h = result_4h.get("signal", "WAIT")
    signal_1d = result_1d.get("signal", "WAIT")
    heat_4h = result_4h.get("heat", 0)
    heat_1d = result_1d.get("heat", 0)

    out.regime_4h = regime_4h
    out.regime_1d = regime_1d
    out.signal_4h = signal_4h
    out.signal_1d = signal_1d

    score = 0

    # 1. Regime family match (+40)
    r4h_bullish = regime_4h in _BULLISH
    r1d_bullish = regime_1d in _BULLISH
    r4h_bearish = regime_4h in _BEARISH
    r1d_bearish = regime_1d in _BEARISH

    if (r4h_bullish and r1d_bullish) or (r4h_bearish and r1d_bearish):
        score += 40
        out.regime_aligned = True
        # Exact regime match bonus
        if regime_4h == regime_1d:
            score += 5  # small bonus for exact match
    elif regime_4h == "FLAT" or regime_1d == "FLAT":
        score += 15  # neutral — not conflicting, not confirming

    # 2. Signal direction match (+30)
    s4h_entry = signal_4h in _ENTRY_SIGNALS
    s1d_entry = signal_1d in _ENTRY_SIGNALS
    s4h_exit = signal_4h in _EXIT_SIGNALS
    s1d_exit = signal_1d in _EXIT_SIGNALS
    s4h_wait = signal_4h == "WAIT"
    s1d_wait = signal_1d == "WAIT"

    if (s4h_entry and s1d_entry) or (s4h_exit and s1d_exit):
        score += 30
        out.signal_aligned = True
    elif (s4h_entry and s1d_wait) or (s4h_wait and s1d_entry):
        score += 10  # partial — one TF has signal, other is neutral
    elif (s4h_exit and s1d_wait) or (s4h_wait and s1d_exit):
        score += 10
    elif s4h_wait and s1d_wait:
        score += 15  # both neutral
        out.signal_aligned = None  # neither agreeing nor differing: both waiting
    # entry vs exit = 0 (conflicting)

    # 3. Heat agreement (+15)
    both_cool = heat_4h < 60 and heat_1d < 60
    both_hot = heat_4h >= 80 and heat_1d >= 80
    if both_cool or both_hot:
        score += 15
    elif abs(heat_4h - heat_1d) < 20:
        score += 8  # close enough

    score = max(0, min(_MAX_POINTS, score))
    out.score = round(score * 100 / _MAX_POINTS)

    # Label (raw points)
    if score >= 75:
        out.label = "STRONG"
    elif score >= 50:
        out.label = "MODERATE"
    elif score >= 25:
        out.label = "WEAK"
    else:
        out.label = "CONFLICTING"

    return out


def compute_all_confluences(
    results_4h: List[dict],
    results_1d: List[dict],
) -> Dict[str, ConfluenceResult]:
    """Compute confluence for all symbols across both timeframes.

    Parameters
    ----------
    results_4h, results_1d : list[dict]
        Scan results keyed by symbol.

    Returns
    -------
    dict[str, ConfluenceResult]
        Keyed by symbol name.
    """
    # Index by symbol
    by_sym_4h = {r.get("symbol", ""): r for r in results_4h}
    by_sym_1d = {r.get("symbol", ""): r for r in results_1d}

    all_symbols = set(by_sym_4h.keys()) | set(by_sym_1d.keys())
    confluences: Dict[str, ConfluenceResult] = {}

    for sym in all_symbols:
        if not sym:
            continue
        confluences[sym] = compute_confluence(
            by_sym_4h.get(sym),
            by_sym_1d.get(sym),
        )

    # Log summary
    labels = [c.label for c in confluences.values()]
    logger.info(
        "Confluence: %d STRONG, %d MODERATE, %d WEAK, %d CONFLICTING",
        labels.count("STRONG"),
        labels.count("MODERATE"),
        labels.count("WEAK"),
        labels.count("CONFLICTING"),
    )

    return confluences
