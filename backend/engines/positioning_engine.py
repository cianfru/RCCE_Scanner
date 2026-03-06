"""
positioning_engine.py
~~~~~~~~~~~~~~~~~~~~~
Converts raw Hyperliquid data (funding rates, open interest) into actionable
positioning metrics per symbol.

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
OI_CHANGE_THRESHOLD = 2.0        # > 2% change considered significant


# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------

@dataclass
class PositioningResult:
    """Per-symbol positioning analysis from Hyperliquid data."""
    funding_regime: str = "NEUTRAL"       # CROWDED_LONG | CROWDED_SHORT | NEUTRAL
    funding_rate: float = 0.0             # Raw hourly funding rate
    oi_trend: str = "UNKNOWN"             # BUILDING | SQUEEZE | LIQUIDATING | SHORTING | STABLE
    oi_value: float = 0.0                 # Open interest in USD
    oi_change_pct: float = 0.0            # OI change since last scan (%)
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
) -> PositioningResult:
    """Analyze positioning from Hyperliquid data.

    Parameters
    ----------
    funding_rate : float
        Current hourly funding rate (decimal, e.g. 0.0001 = 0.01%).
    open_interest : float
        Current open interest in USD.
    price_change_pct : float
        Price change percentage over the scan period (from OHLCV).
    prev_oi : float or None
        Previous scan's open interest for trend calculation.
    predicted_funding : float
        Next predicted funding rate.
    mark_price, oracle_price, volume_24h : float
        Additional context data.

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
    if prev_oi is not None and prev_oi > 0:
        oi_change = ((open_interest - prev_oi) / prev_oi) * 100.0
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
    # Based on funding rate magnitude (higher = more leveraged)
    abs_funding = abs(funding_rate)
    if abs_funding > 0.0003:  # > 0.03%/hr = very high leverage
        result.leverage_risk = "HIGH"
    elif abs_funding > 0.0001:  # > 0.01%/hr = moderate
        result.leverage_risk = "MEDIUM"
    else:
        result.leverage_risk = "LOW"

    return result
