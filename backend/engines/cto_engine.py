"""
CTO Line Advanced — Python / numpy port
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ports the "CTO Line Advanced" Pine Script indicator.

Computes four SMMA lines (v1-fast, m1, m2, v2-slow) on hl2, applies SMA(2)
smoothing, then classifies each bar's trend state into one of five colours:
strong-up, weak-up, strong-down, weak-down, or neutral.

Only v1 (fast) and v2 (slow) are returned for plotting; m1/m2 are used
internally for the noise-filter (internal-conflict check).

Public API
----------
    compute_cto_series(high, low, close, timestamps) -> dict
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Constants (matching Pine defaults)
# ---------------------------------------------------------------------------

SMMA_FAST = 14
SMMA_MID1 = 17
SMMA_MID2 = 20
SMMA_SLOW = 24
SMOOTH_LEN = 2       # SMA applied on top of each SMMA
ATR_LEN = 14
STRONG_MULT = 0.2    # spread > ATR * this ⇒ strong trend

COLOR_STRONG_UP = "#13d460"
COLOR_WEAK_UP   = "#c8d50e"
COLOR_STRONG_DN = "#da0d17"
COLOR_WEAK_DN   = "#ef09c9"
COLOR_NEUTRAL   = "#c0c0c0"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _sma(arr: NDArray[np.float64], n: int) -> NDArray[np.float64]:
    """Simple Moving Average (NaN-safe).

    Handles leading NaN from upstream RMA output by computing the SMA
    only on the valid tail of the array.
    """
    arr = np.asarray(arr, dtype=np.float64)
    out = np.full(len(arr), np.nan, dtype=np.float64)
    if len(arr) < n:
        return out

    # Fast path: no NaN
    if not np.any(np.isnan(arr)):
        cumsum = np.cumsum(arr, dtype=np.float64)
        out[n - 1:] = (cumsum[n - 1:] - np.concatenate(([0.0], cumsum[:-n]))) / n
        return out

    # NaN-safe: find first valid index, compute on valid sub-array
    valid_mask = ~np.isnan(arr)
    first_valid = int(np.argmax(valid_mask))
    if not valid_mask[first_valid]:
        return out
    sub = arr[first_valid:]
    if len(sub) < n:
        return out
    cumsum = np.cumsum(sub, dtype=np.float64)
    sma_vals = np.full(len(sub), np.nan, dtype=np.float64)
    sma_vals[n - 1:] = (cumsum[n - 1:] - np.concatenate(([0.0], cumsum[:-n]))) / n
    out[first_valid:first_valid + len(sub)] = sma_vals
    return out


def _rma(arr: NDArray[np.float64], n: int) -> NDArray[np.float64]:
    """Wilder's smoothing (RMA / SMMA).

    rma[i] = (rma[i-1] * (n - 1) + arr[i]) / n

    Pine's ``ta.rma`` initialises with the SMA of the first *n* values.
    """
    out = np.full_like(arr, np.nan, dtype=np.float64)
    if len(arr) < n:
        return out
    out[n - 1] = np.mean(arr[:n])
    alpha = 1.0 / n
    for i in range(n, len(arr)):
        out[i] = out[i - 1] * (1.0 - alpha) + arr[i] * alpha
    return out


def _true_range(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
) -> NDArray[np.float64]:
    """True Range series.  First element uses high - low."""
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
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    n: int,
) -> NDArray[np.float64]:
    """Average True Range via RMA (Wilder smoothing)."""
    tr = _true_range(high, low, close)
    return _rma(tr, n)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_cto_series(
    high: NDArray[np.float64],
    low: NDArray[np.float64],
    close: NDArray[np.float64],
    timestamps: NDArray[np.float64],
) -> dict:
    """Compute CTO Line Advanced series for charting.

    Parameters
    ----------
    high, low, close :
        OHLCV numpy arrays (oldest-first, any timeframe).
    timestamps :
        Millisecond timestamps matching the OHLCV bars.

    Returns
    -------
    dict
        ``cto_fast`` — list of ``{time, value, color}`` for the fast line (v1)
        ``cto_slow`` — list of ``{time, value, color}`` for the slow line (v2)
    """
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    timestamps = np.asarray(timestamps, dtype=np.float64)

    n = len(close)
    if n < SMMA_SLOW + SMOOTH_LEN:
        return {"cto_fast": [], "cto_slow": []}

    # Source: (high + low) / 2
    hl2 = (high + low) / 2.0

    # Four SMMA lines + SMA smoothing
    def _line(src: NDArray, length: int) -> NDArray:
        x = _rma(src, length)
        return _sma(x, SMOOTH_LEN) if SMOOTH_LEN > 1 else x

    v1 = _line(hl2, SMMA_FAST)
    m1 = _line(hl2, SMMA_MID1)
    m2 = _line(hl2, SMMA_MID2)
    v2 = _line(hl2, SMMA_SLOW)

    # ATR for strong/weak threshold
    atr14 = _atr(high, low, close, ATR_LEN)

    # Build output series with per-bar colours
    cto_fast = []
    cto_slow = []

    for i in range(1, n):
        # Skip bars where any value is NaN
        if (
            np.isnan(v1[i]) or np.isnan(v2[i]) or
            np.isnan(m1[i]) or np.isnan(m2[i]) or
            np.isnan(atr14[i]) or np.isnan(v1[i - 1]) or np.isnan(v2[i - 1])
        ):
            continue

        # Trend classification
        fast_below_slow = v1[i] < v2[i]

        internal_conflict = (
            (v1[i] < m1[i]) != fast_below_slow or
            (m2[i] < v2[i]) != fast_below_slow
        )

        up_slope = v1[i] > v1[i - 1] and v2[i] > v2[i - 1]
        down_slope = v1[i] < v1[i - 1] and v2[i] < v2[i - 1]

        trend_up = not internal_conflict and not fast_below_slow and up_slope
        trend_down = not internal_conflict and fast_below_slow and down_slope

        spread = abs(v1[i] - v2[i])
        atr_val = atr14[i]
        strong_trend = spread > (atr_val * STRONG_MULT) if atr_val > 0 else False

        # Colour
        if trend_up and strong_trend:
            color = COLOR_STRONG_UP
        elif trend_up:
            color = COLOR_WEAK_UP
        elif trend_down and strong_trend:
            color = COLOR_STRONG_DN
        elif trend_down:
            color = COLOR_WEAK_DN
        else:
            color = COLOR_NEUTRAL

        t = int(timestamps[i] / 1000)  # ms → unix seconds
        cto_fast.append({"time": t, "value": round(float(v1[i]), 6), "color": color})
        cto_slow.append({"time": t, "value": round(float(v2[i]), 6), "color": color})

    return {"cto_fast": cto_fast, "cto_slow": cto_slow}
