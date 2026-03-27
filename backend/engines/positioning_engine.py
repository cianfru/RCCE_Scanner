"""
positioning_engine.py
~~~~~~~~~~~~~~~~~~~~~
Converts raw positioning data (funding rates, open interest) into actionable
metrics per symbol.  Primary data source: CoinGlass (aggregated cross-exchange).

Produces funding regime (CROWDED_LONG / CROWDED_SHORT / NEUTRAL),
OI trend (BUILDING / SQUEEZE / LIQUIDATING / SHORTING), and leverage risk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Funding rate thresholds (hourly rate as decimal, e.g. 0.0001 = 0.01%)
FUNDING_CROWDED_LONG = 0.0001    # > 0.01%/hr → longs paying shorts
FUNDING_CROWDED_SHORT = -0.0001  # < -0.01%/hr → shorts paying longs

# OI change thresholds (percentage change between scans)
OI_CHANGE_THRESHOLD = 1.0        # > 1% change considered significant (lowered from 2% for CoinGlass multi-exchange data)


# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------

@dataclass
class PositioningResult:
    """Per-symbol positioning analysis (CoinGlass aggregated / exchange)."""
    funding_regime: str = "NEUTRAL"       # CROWDED_LONG | CROWDED_SHORT | NEUTRAL
    funding_rate: float = 0.0             # Funding rate (decimal)
    oi_trend: str = "UNKNOWN"             # BUILDING | SQUEEZE | LIQUIDATING | SHORTING | STABLE
    oi_value: float = 0.0                 # Open interest in USD
    oi_change_pct: float = 0.0            # OI change (%)
    leverage_risk: str = "UNKNOWN"        # HIGH | MEDIUM | LOW
    predicted_funding: float = 0.0        # Next predicted funding rate
    mark_price: float = 0.0
    oracle_price: float = 0.0
    volume_24h: float = 0.0


# ---------------------------------------------------------------------------
# Compute function
# ---------------------------------------------------------------------------

def compute_positioning(
    funding_rate: float,
    open_interest: float,
    price_change_pct: float,
    prev_oi: Optional[float] = None,
    predicted_funding: float = 0.0,
    mark_price: float = 0.0,
    oracle_price: float = 0.0,
    volume_24h: float = 0.0,
    oi_change_pct_override: Optional[float] = None,
    oi_market_cap_ratio: Optional[float] = None,
) -> PositioningResult:
    """Analyze positioning from exchange data.

    Parameters
    ----------
    funding_rate : float
        Funding rate (decimal, e.g. 0.0001 = 0.01%).
    open_interest : float
        Current open interest in USD.
    price_change_pct : float
        Price change percentage over the scan period.
    prev_oi : float or None
        Previous scan's open interest for trend calculation (legacy).
    predicted_funding : float
        Next predicted funding rate.
    mark_price, oracle_price, volume_24h : float
        Additional context data.
    oi_change_pct_override : float or None
        Pre-computed OI change percentage (from CoinGlass).
        When provided, bypasses ``prev_oi`` calculation — eliminates
        the cold-start problem on deploy.
    oi_market_cap_ratio : float or None
        OI-to-market-cap ratio (leverage proxy from CoinGlass).
        Used for leverage_risk when available.

    Returns
    -------
    PositioningResult
    """
    result = PositioningResult(
        funding_rate=funding_rate,
        oi_value=open_interest,
        predicted_funding=predicted_funding,
        mark_price=mark_price,
        oracle_price=oracle_price,
        volume_24h=volume_24h,
    )

    # --- Funding Regime ---
    if funding_rate > FUNDING_CROWDED_LONG:
        result.funding_regime = "CROWDED_LONG"
    elif funding_rate < FUNDING_CROWDED_SHORT:
        result.funding_regime = "CROWDED_SHORT"
    else:
        result.funding_regime = "NEUTRAL"

    # --- OI Trend ---
    # Prefer pre-computed OI change from CoinGlass (no cold-start issue)
    oi_change: Optional[float] = None
    if oi_change_pct_override is not None:
        oi_change = oi_change_pct_override
    elif prev_oi is not None and prev_oi > 0:
        oi_change = ((open_interest - prev_oi) / prev_oi) * 100.0

    if oi_change is not None:
        result.oi_change_pct = round(oi_change, 2)

        oi_up = oi_change > OI_CHANGE_THRESHOLD
        oi_down = oi_change < -OI_CHANGE_THRESHOLD
        price_up = price_change_pct > 0
        price_down = price_change_pct < 0

        if oi_up and price_up:
            # New money entering longs — real trend confirmation
            result.oi_trend = "BUILDING"
        elif oi_down and price_up:
            # Shorts being squeezed — not sustainable
            result.oi_trend = "SQUEEZE"
        elif oi_down and price_down:
            # Long liquidation cascade — capitulation
            result.oi_trend = "LIQUIDATING"
        elif oi_up and price_down:
            # New shorts opening — aggressive bears
            result.oi_trend = "SHORTING"
        else:
            result.oi_trend = "STABLE"
    else:
        result.oi_trend = "UNKNOWN"

    # --- Leverage Risk ---
    # Prefer OI/market-cap ratio from CoinGlass (more accurate than funding alone)
    if oi_market_cap_ratio is not None and oi_market_cap_ratio > 0:
        if oi_market_cap_ratio > 0.05:     # OI > 5% of market cap = very leveraged
            result.leverage_risk = "HIGH"
        elif oi_market_cap_ratio > 0.03:   # OI > 3% of market cap = moderate
            result.leverage_risk = "MEDIUM"
        else:
            result.leverage_risk = "LOW"
    else:
        # Fallback: use funding rate magnitude
        abs_funding = abs(funding_rate)
        if abs_funding > 0.0003:  # > 0.03%/hr = very high leverage
            result.leverage_risk = "HIGH"
        elif abs_funding > 0.0001:  # > 0.01%/hr = moderate
            result.leverage_risk = "MEDIUM"
        else:
            result.leverage_risk = "LOW"

    return result


# ---------------------------------------------------------------------------
# OI context interpretation
# ---------------------------------------------------------------------------

_ENTRY_SIGNALS = frozenset({
    "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE",
    "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
})
_EXIT_SIGNALS = frozenset({
    "TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG", "LIGHT_SHORT",
})

_OI_CONTEXT = {
    #                  entry                    exit                neutral
    "BUILDING":    ("confirms entry",       "counter-trend OI",  "new positioning"),
    "SQUEEZE":     ("short-cover rally",    "confirms exit",     "shorts closing"),
    "LIQUIDATING": ("long cascade — caution", "confirms exit",   "capitulation"),
    "SHORTING":    ("bears aggressive",     "confirms exit",     "bears opening"),
}


def interpret_oi_context(oi_trend: str, signal: str) -> str:
    """Return a short contextual label for the OI trend given the active signal."""
    row = _OI_CONTEXT.get(oi_trend)
    if not row:
        return ""
    if signal in _ENTRY_SIGNALS:
        return row[0]
    if signal in _EXIT_SIGNALS:
        return row[1]
    return row[2]
