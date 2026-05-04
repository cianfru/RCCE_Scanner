"""
smc_engine.py
~~~~~~~~~~~~~
Smart Money Concepts engine — BOS, CHoCH, FVG, and Order Blocks.

Uses the ``smartmoneyconcepts`` library for ICT-style structure detection.
Guarded import: degrades gracefully to all-NEUTRAL when the library
is not installed.

This engine is **informational only** — it does not affect signal
synthesis or trade decisions.
"""

from __future__ import annotations

import logging
from typing import Dict

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guarded import — library is optional
# ---------------------------------------------------------------------------

_HAS_SMC = False

try:
    from smartmoneyconcepts.smc import smc as _smc_lib
    import pandas as pd
    _HAS_SMC = True
except ImportError:
    logger.info("smartmoneyconcepts not installed — SMC engine disabled")


# ---------------------------------------------------------------------------
# Neutral fallback
# ---------------------------------------------------------------------------

_NEUTRAL = {
    "smc_bias":  "NEUTRAL",
    "smc_bos":   "NEUTRAL",
    "smc_choch": "NEUTRAL",
    "smc_fvg":   "NEUTRAL",
    "smc_ob":    "NEUTRAL",
}

# How many recent bars to scan for the latest non-zero signal
_LOOKBACK = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _last_nonzero(series, lookback: int = _LOOKBACK):
    """Return the last non-NaN, non-zero value within `lookback` bars."""
    tail = series.iloc[-lookback:]
    valid = tail.dropna()
    valid = valid[valid != 0]
    if valid.empty:
        return 0
    return valid.iloc[-1]


def _direction_label(value, prefix: str) -> str:
    """Map a numeric direction to a labelled string."""
    if value > 0:
        return f"{prefix}_UP"
    elif value < 0:
        return f"{prefix}_DOWN"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_smc(ohlcv: dict, *, swing_length: int = 20) -> dict:
    """Run Smart Money Concepts analysis on OHLCV data.

    Parameters
    ----------
    ohlcv : dict
        Standard OHLCV arrays: open, high, low, close, volume, timestamp.
    swing_length : int
        Lookback for swing high/low detection (default 20).

    Returns
    -------
    dict with keys:
        smc_bias  : "BULLISH" / "BEARISH" / "NEUTRAL"
        smc_bos   : "BOS_UP" / "BOS_DOWN" / "NEUTRAL"
        smc_choch : "CHOCH_UP" / "CHOCH_DOWN" / "NEUTRAL"
        smc_fvg   : "FVG_UP" / "FVG_DOWN" / "NEUTRAL"
        smc_ob    : "OB_UP" / "OB_DOWN" / "NEUTRAL"
    """
    if not _HAS_SMC:
        return dict(_NEUTRAL)

    n = len(ohlcv.get("close", []))
    if n < swing_length * 2 + 10:
        return dict(_NEUTRAL)

    # --- Convert numpy arrays → pandas DataFrame --------------------------
    df = pd.DataFrame({
        "open":   np.asarray(ohlcv["open"],   dtype=np.float64),
        "high":   np.asarray(ohlcv["high"],   dtype=np.float64),
        "low":    np.asarray(ohlcv["low"],    dtype=np.float64),
        "close":  np.asarray(ohlcv["close"],  dtype=np.float64),
        "volume": np.asarray(ohlcv["volume"], dtype=np.float64),
    })

    # --- Step 1: Swing highs/lows ----------------------------------------
    try:
        swing_hl = _smc_lib.swing_highs_lows(df, swing_length=swing_length)
    except Exception:
        logger.debug("SMC swing detection failed")
        return dict(_NEUTRAL)

    # --- Step 2: BOS / CHoCH --------------------------------------------
    bos_val = 0
    choch_val = 0
    try:
        bos_choch = _smc_lib.bos_choch(df, swing_hl, close_break=True)
        # BOS column
        if "BOS" in bos_choch.columns:
            bos_val = _last_nonzero(bos_choch["BOS"])
        # CHoCH column
        if "CHOCH" in bos_choch.columns:
            choch_val = _last_nonzero(bos_choch["CHOCH"])
    except Exception:
        logger.debug("SMC BOS/CHoCH failed")

    # --- Step 3: Fair Value Gaps ----------------------------------------
    fvg_val = 0
    try:
        fvg_df = _smc_lib.fvg(df)
        if "FVG" in fvg_df.columns:
            fvg_val = _last_nonzero(fvg_df["FVG"])
    except Exception:
        logger.debug("SMC FVG failed")

    # --- Step 4: Order Blocks -------------------------------------------
    ob_val = 0
    try:
        ob_df = _smc_lib.ob(df, swing_hl)
        if "OB" in ob_df.columns:
            ob_val = _last_nonzero(ob_df["OB"])
    except Exception:
        logger.debug("SMC Order Blocks failed")

    # --- Derive per-sub-signal labels -----------------------------------
    smc_bos   = _direction_label(bos_val, "BOS")
    smc_choch = _direction_label(choch_val, "CHOCH")
    smc_fvg   = _direction_label(fvg_val, "FVG")
    smc_ob    = _direction_label(ob_val, "OB")

    # --- Compute bias (majority vote across 4 sub-signals) --------------
    bull = sum(1 for v in (bos_val, choch_val, fvg_val, ob_val) if v > 0)
    bear = sum(1 for v in (bos_val, choch_val, fvg_val, ob_val) if v < 0)

    if bull >= 3:
        smc_bias = "BULLISH"
    elif bear >= 3:
        smc_bias = "BEARISH"
    else:
        smc_bias = "NEUTRAL"

    return {
        "smc_bias":  smc_bias,
        "smc_bos":   smc_bos,
        "smc_choch": smc_choch,
        "smc_fvg":   smc_fvg,
        "smc_ob":    smc_ob,
    }
