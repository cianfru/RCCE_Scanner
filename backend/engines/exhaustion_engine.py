"""
Exhaustion Engine V6 — Python / numpy port
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ports the "V6.0-Down (Right Diagnostic)" Pine Script indicator.

Detects exhaustion-selling conditions (absorption clusters, climax reversals,
floor confirmations) relative to the weekly BMSB (Bull-Market Support Band)
midpoint.

Public API
----------
    compute_exhaustion(ohlcv, ohlcv_weekly) -> dict
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Helper functions — vectorised where possible
# ---------------------------------------------------------------------------

def _sma(arr: NDArray[np.float64], n: int) -> NDArray[np.float64]:
    """Simple Moving Average.  First (n-1) values are NaN."""
    out = np.full_like(arr, np.nan, dtype=np.float64)
    if len(arr) < n:
        return out
    cumsum = np.cumsum(arr, dtype=np.float64)
    out[n - 1:] = (cumsum[n - 1:] - np.concatenate(([0.0], cumsum[:-n]))) / n
    return out


def _rma(arr: NDArray[np.float64], n: int) -> NDArray[np.float64]:
    """Wilder's smoothing (RMA / SMMA).

    rma[i] = (rma[i-1] * (n - 1) + arr[i]) / n

    Pine's ``ta.rma`` initialises with the SMA of the first *n* values.
    """
    out = np.full_like(arr, np.nan, dtype=np.float64)
    if len(arr) < n:
        return out
    # Seed with SMA of the first n values
    out[n - 1] = np.mean(arr[:n])
    alpha = 1.0 / n
    for i in range(n, len(arr)):
        out[i] = out[i - 1] * (1.0 - alpha) + arr[i] * alpha
    return out


def _ema(arr: NDArray[np.float64], n: int) -> NDArray[np.float64]:
    """Exponential Moving Average.

    Pine's ``ta.ema`` seeds with the SMA of the first *n* values and then
    applies the standard multiplier  2 / (n + 1).
    """
    out = np.full_like(arr, np.nan, dtype=np.float64)
    if len(arr) < n:
        return out
    out[n - 1] = np.mean(arr[:n])
    k = 2.0 / (n + 1.0)
    for i in range(n, len(arr)):
        out[i] = arr[i] * k + out[i - 1] * (1.0 - k)
    return out


def _true_range(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> NDArray[np.float64]:
    """True Range (``ta.tr(true)`` in Pine — handles gaps).

    TR = max(high - low, |high - prev_close|, |low - prev_close|)
    The very first bar uses (high - low) since there is no previous close.
    """
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]          # no prior bar — fall back to current
    prev_close[1:] = close[:-1]

    hl = high - low
    hpc = np.abs(high - prev_close)
    lpc = np.abs(low - prev_close)
    return np.maximum(hl, np.maximum(hpc, lpc))


def _atr(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    n: int,
) -> NDArray[np.float64]:
    """Average True Range using Wilder's RMA (matches Pine ``ta.atr``)."""
    tr = _true_range(high, low, close)
    return _rma(tr, n)


def _rolling_sum_bool(
    mask: NDArray[np.bool_], window: int
) -> NDArray[np.int64]:
    """Rolling sum of a boolean array over *window* bars (inclusive of current).

    Equivalent to Pine's ``math.sum(cond ? 1 : 0, window)``.
    """
    vals = mask.astype(np.int64)
    cumsum = np.cumsum(vals)
    out = np.empty_like(cumsum)
    out[:window] = cumsum[:window]
    out[window:] = cumsum[window:] - cumsum[:-window]
    return out


def _nz(arr: NDArray[np.float64], replacement: float = 0.0) -> NDArray[np.float64]:
    """Replace NaN (and inf) with *replacement* — mirrors Pine ``nz()``."""
    out = arr.copy()
    bad = ~np.isfinite(out)
    out[bad] = replacement
    return out


# ---------------------------------------------------------------------------
# Weekly BMSB mid — (EMA(21) + SMA(20)) / 2 on weekly bars
# ---------------------------------------------------------------------------

def _weekly_bmsb_mid(close_w: NDArray[np.float64]) -> float:
    """Return the LAST valid weekly BMSB midpoint price.

    BMSB mid = (EMA(close, 21) + SMA(close, 20)) / 2   on weekly data.
    """
    ema21 = _ema(close_w, 21)
    sma20 = _sma(close_w, 20)
    mid = (ema21 + sma20) / 2.0
    # Return last non-NaN value
    valid = np.where(np.isfinite(mid))[0]
    if len(valid) == 0:
        return np.nan
    return float(mid[valid[-1]])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_exhaustion(
    ohlcv: dict[str, NDArray[np.float64]],
    ohlcv_weekly: dict[str, NDArray[np.float64]],
    *,
    atr_len: int = 14,
    vol_lookback: int = 20,
    sens: float = 1.2,
    cluster_req: int = 3,
    cluster_look: int = 10,
) -> dict:
    """Port of the *Exhaustion Engine V6* Pine Script indicator.

    Parameters
    ----------
    ohlcv : dict
        Daily (or 4-hour) OHLCV data with numpy arrays keyed by
        ``"open"``, ``"high"``, ``"low"``, ``"close"``, ``"volume"``.
    ohlcv_weekly : dict
        Weekly OHLCV data (same key structure).
    atr_len : int
        ATR look-back period (default 14).
    vol_lookback : int
        Relative-volume SMA look-back (default 20).
    sens : float
        Exhaustion sensitivity multiplier (default 1.2).
    cluster_req : int
        Minimum absorption dots in the cluster window (default 3).
    cluster_look : int
        Number of bars in the cluster window (default 10).

    Returns
    -------
    dict
        ``effort``           – smoothed directional effort on the last bar
        ``rel_vol``          – relative volume on the last bar
        ``state``            – one of EXHAUSTED_FLOOR / CLIMAX / ABSORBING /
                               BEAR_ZONE / NEUTRAL
        ``dist_pct``         – distance from weekly BMSB mid (%)
        ``is_absorption``    – absorption signal on current bar
        ``is_climax``        – climax signal on current bar
        ``floor_confirmed``  – cluster + volume-divergence confirmation
        ``w_bmsb``           – weekly BMSB mid price
    """

    # --- unpack arrays ------------------------------------------------
    o = np.asarray(ohlcv["open"],   dtype=np.float64)
    h = np.asarray(ohlcv["high"],   dtype=np.float64)
    l = np.asarray(ohlcv["low"],    dtype=np.float64)
    c = np.asarray(ohlcv["close"],  dtype=np.float64)
    v = np.asarray(ohlcv["volume"], dtype=np.float64)

    c_w = np.asarray(ohlcv_weekly["close"], dtype=np.float64)

    n = len(c)

    # Guard: not enough data ------------------------------------------
    if n < 2:
        return _empty_result()

    # === DATA PREP ====================================================

    # True Range (ta.tr(true))
    tr = _true_range(h, l, c)

    # ATR via Wilder's RMA
    avg_atr = _atr(h, l, c, atr_len)

    # --- Directional Effort ---
    prev_c = np.empty_like(c)
    prev_c[0] = c[0]
    prev_c[1:] = c[:-1]

    roc_down = np.where(c < prev_c, np.abs(c - prev_c), 0.0)
    avg_atr_safe = _nz(avg_atr, 1.0)
    eff_down = roc_down / avg_atr_safe
    eff_s = _sma(eff_down, 3)
    eff_s = _nz(eff_s, 0.0)

    # --- Candle Anatomy ---
    is_red = c < o
    body_size = np.abs(c - o)
    lower_wick = np.where(is_red, c - l, o - l)
    upper_wick = np.where(is_red, h - o, h - c)

    # === Weekly BMSB Anchor ===========================================
    w_mid = _weekly_bmsb_mid(c_w)
    if np.isnan(w_mid):
        # Not enough weekly data — fall back to neutral
        return _empty_result()

    weekly_down_zone = c < w_mid                         # bool array
    dist_pct_arr = ((c - w_mid) / w_mid) * 100.0

    # === Signal Logic =================================================
    effort_avg = _sma(eff_s, 20)
    effort_avg_safe = _nz(effort_avg, 0.0)
    effort_peak = eff_s > (effort_avg_safe * sens)

    avg_atr_safe_broadcast = _nz(avg_atr, 1.0)

    is_absorption_arr = (
        weekly_down_zone
        & is_red
        & (tr < avg_atr_safe_broadcast)
        & effort_peak
    )

    is_climax_arr = (
        weekly_down_zone
        & (tr > avg_atr_safe_broadcast * 1.5)
        & (lower_wick > body_size * 1.5)
        & (lower_wick > upper_wick)
        & effort_peak
    )

    # === Relative Volume ==============================================
    vol_sma = _sma(v, vol_lookback)
    vol_sma_safe = _nz(vol_sma, 1.0)
    # Protect against zero in vol_sma
    vol_sma_safe = np.where(vol_sma_safe == 0.0, 1.0, vol_sma_safe)
    rel_vol_arr = v / vol_sma_safe

    # === Cluster & Divergence (stateful — must iterate) ===============
    aqua_in_window = _rolling_sum_bool(is_absorption_arr, cluster_look)

    # Stateful start_vol tracking — mirrors Pine ``var float start_vol``
    start_vol = np.full(n, np.nan, dtype=np.float64)
    current_start_vol = np.nan

    for i in range(n):
        if is_absorption_arr[i] and aqua_in_window[i] == 1:
            current_start_vol = v[i]
        start_vol[i] = current_start_vol

    floor_confirmed_arr = (aqua_in_window >= cluster_req) & (v < start_vol)

    # === Extract last-bar values ======================================
    idx = n - 1

    eff_s_last        = float(eff_s[idx])
    rel_vol_last      = float(rel_vol_arr[idx])
    dist_pct_last     = float(dist_pct_arr[idx])
    is_absorption_last = bool(is_absorption_arr[idx])
    is_climax_last     = bool(is_climax_arr[idx])
    floor_last         = bool(floor_confirmed_arr[idx])

    # --- State classification (priority order) ---
    if floor_last:
        state = "EXHAUSTED_FLOOR"
    elif is_climax_last:
        state = "CLIMAX"
    elif is_absorption_last:
        state = "ABSORBING"
    elif bool(weekly_down_zone[idx]):
        state = "BEAR_ZONE"
    else:
        state = "NEUTRAL"

    return {
        "effort":          eff_s_last,
        "rel_vol":         rel_vol_last,
        "state":           state,
        "dist_pct":        dist_pct_last,
        "is_absorption":   is_absorption_last,
        "is_climax":       is_climax_last,
        "floor_confirmed": floor_last,
        "w_bmsb":          float(w_mid),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _empty_result() -> dict:
    """Return a safe default when there is insufficient data."""
    return {
        "effort":          0.0,
        "rel_vol":         0.0,
        "state":           "NEUTRAL",
        "dist_pct":        0.0,
        "is_absorption":   False,
        "is_climax":       False,
        "floor_confirmed": False,
        "w_bmsb":          0.0,
    }
