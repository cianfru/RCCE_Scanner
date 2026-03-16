"""
Structural Heat Map V3 -- Python / NumPy port.

Replicates the Pine Script indicator logic:
  * Weekly BMSB baseline (EMA-21 + SMA-20 mid)
  * Daily ATR(14), weekly ATR(14), weekly ATR-SMA(20)
  * Hybrid volatility scaling  R3 = (ATR_d / ATR_w) * (ATR_w / ATR_w_sma)
  * Heat 0-100,  phase classification, ATR regime
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Constants (matching Pine defaults)
# ---------------------------------------------------------------------------

EMA_LEN = 21
SMA_LEN = 20

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _sma(arr: np.ndarray, n: int) -> np.ndarray:
    """Simple Moving Average.

    Handles NaN-containing input (e.g. ATR series with leading NaN).
    Pine's ta.sma skips leading NaN and starts the window from the first
    valid value.  For a fully numeric array the first (n-1) outputs are NaN.
    """
    arr = np.asarray(arr, dtype=np.float64)
    out = np.full(len(arr), np.nan, dtype=np.float64)
    if len(arr) < n:
        return out

    # If the array has no NaN we can use the fast cumsum path
    if not np.any(np.isnan(arr)):
        cumsum = np.cumsum(arr)
        out[n - 1 :] = (cumsum[n - 1 :] - np.concatenate(([0.0], cumsum[: -n]))) / n
        return out

    # Slow but NaN-safe path: find first valid index, then compute SMA on
    # the valid sub-array and place results back.
    valid_mask = ~np.isnan(arr)
    first_valid = int(np.argmax(valid_mask))
    if not valid_mask[first_valid]:
        return out  # all NaN

    valid_sub = arr[first_valid:]
    # In Pine, once the indicator starts producing values it doesn't go
    # back to NaN, so treat the valid tail as a contiguous series.
    sub_len = len(valid_sub)
    if sub_len < n:
        return out
    cumsum = np.cumsum(valid_sub)
    sma_vals = np.empty(sub_len, dtype=np.float64)
    sma_vals[:] = np.nan
    sma_vals[n - 1 :] = (
        cumsum[n - 1 :] - np.concatenate(([0.0], cumsum[: -n]))
    ) / n
    out[first_valid : first_valid + sub_len] = sma_vals
    return out


def _ema(arr: np.ndarray, n: int) -> np.ndarray:
    """Exponential Moving Average (Pine-style: SMA seed then EMA recurrence)."""
    out = np.full_like(arr, np.nan, dtype=np.float64)
    if len(arr) < n:
        return out
    # Seed with SMA of first n values
    seed = np.mean(arr[:n])
    out[n - 1] = seed
    k = 2.0 / (n + 1.0)
    for i in range(n, len(arr)):
        out[i] = arr[i] * k + out[i - 1] * (1.0 - k)
    return out


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """True Range series.  First element uses high - low (no previous close)."""
    tr = np.empty(len(high), dtype=np.float64)
    tr[0] = high[0] - low[0]
    prev_close = close[:-1]
    tr[1:] = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - prev_close),
            np.abs(low[1:] - prev_close),
        ),
    )
    return tr


def _atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    n: int,
) -> np.ndarray:
    """Average True Range -- RMA (Wilder smoothing), matching Pine's ta.atr.

    Pine's ``ta.atr`` uses ``ta.rma`` internally, which is an exponential
    moving average with ``alpha = 1/n`` (Wilder smoothing), seeded by the SMA
    of the first *n* true-range values.
    """
    tr = _true_range(high, low, close)
    out = np.full_like(tr, np.nan, dtype=np.float64)
    if len(tr) < n:
        return out
    # Seed with SMA of first n TR values
    out[n - 1] = np.mean(tr[:n])
    alpha = 1.0 / n
    for i in range(n, len(tr)):
        out[i] = alpha * tr[i] + (1.0 - alpha) * out[i - 1]
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_heatmap(ohlcv_daily: dict, ohlcv_weekly: dict) -> dict:
    """Compute Structural Heat Map V3 values from daily + weekly OHLCV data.

    Parameters
    ----------
    ohlcv_daily : dict
        Keys ``"open", "high", "low", "close", "volume", "timestamp"`` each
        mapping to a numpy array of daily bars, oldest-first.
    ohlcv_weekly : dict
        Same structure but weekly bars.

    Returns
    -------
    dict
        ``heat``          – 0-100 score (int)
        ``direction``     – +1 above BMSB mid, -1 below (int)
        ``phase``         – structural phase label (str)
        ``atr_regime``    – ATR regime label (str)
        ``deviation_pct`` – percentage deviation from BMSB mid (float)
        ``deviation_abs`` – absolute point deviation (float)
        ``bmsb_mid``      – weekly BMSB midline value (float)
        ``r3``            – hybrid volatility scaling factor (float)
    """
    # ---- Constants -----------------------------------------------------------
    ATR_LEN_D = 14
    ATR_LEN_W = 14
    ATR_REGIME_LEN = 20

    # ---- Unpack arrays -----------------------------------------------------
    d_high = np.asarray(ohlcv_daily["high"], dtype=np.float64)
    d_low = np.asarray(ohlcv_daily["low"], dtype=np.float64)
    d_close = np.asarray(ohlcv_daily["close"], dtype=np.float64)

    w_high = np.asarray(ohlcv_weekly["high"], dtype=np.float64)
    w_low = np.asarray(ohlcv_weekly["low"], dtype=np.float64)
    w_close = np.asarray(ohlcv_weekly["close"], dtype=np.float64)

    # ---- Validate minimum data ---------------------------------------------
    min_daily = ATR_LEN_D + 2  # need at least 3 heat bars for phase detection
    min_weekly_bmsb = max(EMA_LEN, SMA_LEN)  # 21 weeks for BMSB mid
    if len(d_close) < min_daily or len(w_close) < min_weekly_bmsb:
        return _default_result()

    # ---- Weekly BMSB baseline ----------------------------------------------
    bmsb_ema_w = _ema(w_close, EMA_LEN)
    bmsb_sma_w = _sma(w_close, SMA_LEN)
    bmsb_mid_series = (bmsb_ema_w + bmsb_sma_w) / 2.0

    # Use the last valid weekly BMSB mid value
    bmsb_mid = _last_valid(bmsb_mid_series)
    if np.isnan(bmsb_mid):
        return _default_result()

    # ---- Volatility components ---------------------------------------------
    atr_d_series = _atr(d_high, d_low, d_close, ATR_LEN_D)
    atr_w_series = _atr(w_high, w_low, w_close, ATR_LEN_W)
    atr_w_sma_series = _sma(atr_w_series, ATR_REGIME_LEN)

    atr_d = _last_valid(atr_d_series)
    atr_w = _last_valid(atr_w_series)
    atr_w_sma = _last_valid(atr_w_sma_series)

    if np.isnan(atr_d) or atr_d == 0.0:
        return _default_result()

    # ---- Hybrid scaling R3 -------------------------------------------------
    # If weekly ATR or its SMA is unavailable (< 34 weeks of data),
    # default r3=1.0 so heat is computed from BMSB deviation alone.
    if np.isnan(atr_w) or atr_w == 0.0 or np.isnan(atr_w_sma) or atr_w_sma == 0.0:
        r1 = 1.0
        r2 = 1.0
    else:
        r1 = atr_d / atr_w
        r2 = atr_w / atr_w_sma
    r3 = r1 * r2

    # ---- Deviation from BMSB mid (daily close) -----------------------------
    # We compute heat for the last 3 daily bars so phase logic can look back.
    n_bars = min(3, len(d_close))
    closes = d_close[-n_bars:]

    devs = closes - bmsb_mid
    abs_devs = np.abs(devs)
    dirs = np.where(devs >= 0, 1, -1)

    # x and heat for each of the last n_bars
    xs = (abs_devs / atr_d) * r3
    heats = np.minimum(100, np.round(xs * 12.5)).astype(int)

    # Current bar values
    heat = int(heats[-1])
    direction = int(dirs[-1])
    dev = float(devs[-1])
    abs_dev = float(abs_devs[-1])

    # Previous bar values (with safe fallback)
    heat_prev1 = int(heats[-2]) if n_bars >= 2 else 0
    heat_prev2 = int(heats[-3]) if n_bars >= 3 else 0
    dir_cur = direction

    # ---- Phase classification ----------------------------------------------
    # Slope / fading
    slope = heat - heat_prev1
    is_fading = slope < 0 and heat > 40

    # Blow-off entry (dir > 0 only)
    enter_up_peak = heat > 80 and dir_cur > 0 and heat_prev1 <= 80

    # Exhaustion detection (both sides)
    exhaust_top = (
        heat_prev1 > 80
        and heat_prev1 > heat
        and heat_prev1 > heat_prev2
        and dir_cur > 0
    )
    exhaust_bottom = (
        heat_prev1 > 80
        and heat_prev1 > heat
        and heat_prev1 > heat_prev2
        and dir_cur < 0
    )

    phase: str = "Neutral"
    if exhaust_top or exhaust_bottom:
        phase = "Exhaustion"
    elif enter_up_peak:
        phase = "Entry"
    elif is_fading:
        phase = "Fading"
    elif heat > 20:
        phase = "Extension"

    # ---- ATR regime classification -----------------------------------------
    atr_regime: str = "Normal"
    if r3 > 1.5:
        atr_regime = "High"
    elif r3 > 1.1:
        atr_regime = "Elevated"
    elif r3 < 0.8:
        atr_regime = "Compressed"

    # ---- Deviation stats ---------------------------------------------------
    deviation_pct = (dev / bmsb_mid) * 100.0 if bmsb_mid != 0.0 else 0.0

    return {
        "heat": heat,
        "direction": direction,
        "phase": phase,
        "atr_regime": atr_regime,
        "deviation_pct": round(deviation_pct, 4),
        "deviation_abs": round(abs_dev, 4),
        "bmsb_mid": round(bmsb_mid, 4),
        "r3": round(r3, 4),
    }


def compute_bmsb_series(
    w_close: np.ndarray, w_timestamps: np.ndarray
) -> dict:
    """Compute full BMSB series for chart overlay.

    Returns dict with ``mid``, ``ema``, ``sma`` keys — each a list of
    ``{"time": <unix_seconds>, "value": <float>}`` dicts suitable for
    lightweight-charts ``LineSeries.setData()``.
    """
    empty = {"mid": [], "ema": [], "sma": []}
    if len(w_close) < max(EMA_LEN, SMA_LEN):
        return empty

    bmsb_ema = _ema(w_close, EMA_LEN)
    bmsb_sma = _sma(w_close, SMA_LEN)
    bmsb_mid = (bmsb_ema + bmsb_sma) / 2.0

    def _to_series(arr):
        return [
            {"time": int(w_timestamps[i] / 1000), "value": round(float(arr[i]), 6)}
            for i in range(len(w_timestamps))
            if not np.isnan(arr[i])
        ]

    return {
        "mid": _to_series(bmsb_mid),
        "ema": _to_series(bmsb_ema),
        "sma": _to_series(bmsb_sma),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _last_valid(arr: np.ndarray) -> float:
    """Return the last non-NaN value in *arr*, or NaN if none exists."""
    mask = ~np.isnan(arr)
    if not np.any(mask):
        return np.nan
    return float(arr[mask][-1])


def _default_result() -> dict:
    """Fallback result when data is insufficient or invalid."""
    return {
        "heat": 0,
        "direction": 0,
        "phase": "Neutral",
        "atr_regime": "Normal",
        "deviation_pct": 0.0,
        "deviation_abs": 0.0,
        "bmsb_mid": 0.0,
        "r3": 0.0,
    }
