"""
RCCE v2.2 Engine -- Python / numpy port (hybrid baseline)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ports the RCCE v2.2 Pine Script indicator to a pure-numpy implementation,
enhanced with a hybrid z-score baseline:

  - **Primary**: linreg(300) — follows the macro trend slope so trending
    assets don't appear overextended with limited history.
  - **Fallback**: SMA(200) — used when the coin has < 300 bars of data.

Public API
----------
    compute_rcce(ohlcv, btc_ohlcv=None, eth_ohlcv=None) -> dict

Z-score normalisation uses a 200-bar window for the inner mean/stdev,
with optional smoothing (Z_SMOOTH) and scaling (Z_SCALE).  A warmup
dampening factor is applied for coins with fewer than 2 * LEN_LONG bars.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# CONFIG CONSTANTS (match Pine v2.2)
# ---------------------------------------------------------------------------
LEN_LONG: int = 200
LEN_SHORT: int = 30
LEN_ENERGY_FAST: int = 14
LEN_ENERGY_SLOW: int = 50
LEN_BETA: int = 100
LEN_ATR_FAST: int = 14
LEN_ATR_SLOW: int = 50
LEN_REGRESSION: int = 300       # linreg window (primary baseline)
Z_SMOOTH: int = 1               # z-score SMA smoothing (1 = off)
Z_SCALE: float = 1.0            # z-score output multiplier
Z_BLOWOFF: float = 2.5          # raised from 2.0 — hybrid baseline is tighter
Z_CAPITULATION: float = -1.0
Z_TRIM: float = 3.0
Z_TRIM_HARD: float = 3.5
MIN_REGIME_BARS: int = 5

# Regime label ordering (index -> name)
_REGIME_LABELS: List[str] = [
    "MARKUP",
    "BLOWOFF",
    "REACC",
    "MARKDOWN",
    "CAP",
    "ACCUM",
]

_EPS: float = 1e-10

# Minimum series length required for full z-score warm-up: two stacked
# rolling windows of LEN_LONG.
_MIN_ZSCORE_BARS: int = 2 * LEN_LONG - 1

# ---------------------------------------------------------------------------
# Rolling-window helpers (operate on 1-D float64 arrays)
# ---------------------------------------------------------------------------

def _sma(arr: np.ndarray, n: int) -> np.ndarray:
    """Simple moving average.  First n-1 values are NaN.

    NaN values in the input propagate: if any element within the window is
    NaN, the output is NaN (matches the cumsum-based approach).
    """
    out = np.full(len(arr), np.nan, dtype=np.float64)
    if n < 1 or len(arr) < n:
        return out
    cumsum = np.cumsum(arr)
    out[n - 1 :] = (cumsum[n - 1 :] - np.concatenate(([0.0], cumsum[:-n]))) / n
    return out


def _sma_nan_safe(arr: np.ndarray, n: int) -> np.ndarray:
    """SMA that gracefully handles NaN inputs by using an expanding window
    for the first ``n`` valid elements and a fixed ``n``-bar window thereafter.

    This mirrors Pine Script behaviour where ``ta.sma`` on a series that
    starts with NaN simply begins producing output once enough non-NaN bars
    have been seen.
    """
    length = len(arr)
    out = np.full(length, np.nan, dtype=np.float64)
    if n < 1 or length == 0:
        return out

    # Find the first non-NaN index
    valid_mask = ~np.isnan(arr)
    if not np.any(valid_mask):
        return out

    first_valid = int(np.argmax(valid_mask))

    # Replace NaN with 0 for cumsum, then correct with counts
    arr_filled = np.where(valid_mask, arr, 0.0)
    cumsum = np.cumsum(arr_filled)
    counts = np.cumsum(valid_mask.astype(np.float64))

    for i in range(first_valid, length):
        lo = max(i - n + 1, 0)
        s = cumsum[i] - (cumsum[lo - 1] if lo > 0 else 0.0)
        c = counts[i] - (counts[lo - 1] if lo > 0 else 0.0)
        if c >= min(n, i - first_valid + 1) and c > 0:
            out[i] = s / c
    return out


def _stdev(arr: np.ndarray, n: int) -> np.ndarray:
    """Rolling *population* std-dev (matches Pine ``ta.stdev`` which divides
    by N, not N-1).  First n-1 values are NaN.
    """
    out = np.full(len(arr), np.nan, dtype=np.float64)
    if n < 1 or len(arr) < n:
        return out
    cumsum = np.cumsum(arr)
    cumsum2 = np.cumsum(arr * arr)
    s = cumsum[n - 1 :] - np.concatenate(([0.0], cumsum[:-n]))
    s2 = cumsum2[n - 1 :] - np.concatenate(([0.0], cumsum2[:-n]))
    var = s2 / n - (s / n) ** 2
    var = np.maximum(var, 0.0)
    out[n - 1 :] = np.sqrt(var)
    return out


def _stdev_nan_safe(arr: np.ndarray, n: int) -> np.ndarray:
    """Rolling population std-dev that handles NaN input the same way as
    ``_sma_nan_safe``.
    """
    length = len(arr)
    out = np.full(length, np.nan, dtype=np.float64)
    if n < 1 or length == 0:
        return out

    valid_mask = ~np.isnan(arr)
    if not np.any(valid_mask):
        return out

    first_valid = int(np.argmax(valid_mask))

    arr_filled = np.where(valid_mask, arr, 0.0)
    arr2_filled = np.where(valid_mask, arr * arr, 0.0)
    cumsum = np.cumsum(arr_filled)
    cumsum2 = np.cumsum(arr2_filled)
    counts = np.cumsum(valid_mask.astype(np.float64))

    for i in range(first_valid, length):
        lo = max(i - n + 1, 0)
        s = cumsum[i] - (cumsum[lo - 1] if lo > 0 else 0.0)
        s2 = cumsum2[i] - (cumsum2[lo - 1] if lo > 0 else 0.0)
        c = counts[i] - (counts[lo - 1] if lo > 0 else 0.0)
        if c >= min(n, i - first_valid + 1) and c > 0:
            var = s2 / c - (s / c) ** 2
            out[i] = np.sqrt(max(var, 0.0))
    return out


def _variance(arr: np.ndarray, n: int) -> np.ndarray:
    """Rolling *population* variance (matches Pine ``ta.variance``)."""
    out = np.full(len(arr), np.nan, dtype=np.float64)
    if n < 1 or len(arr) < n:
        return out
    cumsum = np.cumsum(arr)
    cumsum2 = np.cumsum(arr * arr)
    s = cumsum[n - 1 :] - np.concatenate(([0.0], cumsum[:-n]))
    s2 = cumsum2[n - 1 :] - np.concatenate(([0.0], cumsum2[:-n]))
    var = s2 / n - (s / n) ** 2
    var = np.maximum(var, 0.0)
    out[n - 1 :] = var
    return out


def _variance_nan_safe(arr: np.ndarray, n: int) -> np.ndarray:
    """Rolling population variance, NaN-safe."""
    length = len(arr)
    out = np.full(length, np.nan, dtype=np.float64)
    if n < 1 or length == 0:
        return out

    valid_mask = ~np.isnan(arr)
    if not np.any(valid_mask):
        return out

    first_valid = int(np.argmax(valid_mask))

    arr_filled = np.where(valid_mask, arr, 0.0)
    arr2_filled = np.where(valid_mask, arr * arr, 0.0)
    cumsum = np.cumsum(arr_filled)
    cumsum2 = np.cumsum(arr2_filled)
    counts = np.cumsum(valid_mask.astype(np.float64))

    for i in range(first_valid, length):
        lo = max(i - n + 1, 0)
        s = cumsum[i] - (cumsum[lo - 1] if lo > 0 else 0.0)
        s2 = cumsum2[i] - (cumsum2[lo - 1] if lo > 0 else 0.0)
        c = counts[i] - (counts[lo - 1] if lo > 0 else 0.0)
        if c >= min(n, i - first_valid + 1) and c > 0:
            var = s2 / c - (s / c) ** 2
            out[i] = max(var, 0.0)
    return out


def _percentile_rolling(arr: np.ndarray, n: int, pct: float) -> np.ndarray:
    """Rolling percentile with linear interpolation
    (Pine ``percentile_linear_interpolation``).

    ``pct`` is in 0-100 range.  NaN values in the window are ignored.
    """
    out = np.full(len(arr), np.nan, dtype=np.float64)
    if n < 1 or len(arr) < n:
        return out

    # Detect which keyword numpy.percentile accepts (changed in 1.22)
    _pct_kwargs: dict
    try:
        np.percentile([1.0, 2.0], 50, method="linear")
        _pct_kwargs = {"method": "linear"}
    except TypeError:
        _pct_kwargs = {"interpolation": "linear"}

    for i in range(n - 1, len(arr)):
        window = arr[i - n + 1 : i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            out[i] = np.percentile(valid, pct, **_pct_kwargs)
    return out


# ---------------------------------------------------------------------------
# Core calculations (vectorised over the full series)
# ---------------------------------------------------------------------------

def _linreg(arr: np.ndarray, n: int) -> np.ndarray:
    """Rolling linear regression fitted value at offset 0.

    Matches Pine ``ta.linreg(src, length, 0)`` — fits a least-squares line
    over the trailing *n* bars and returns the fitted value at the current bar.
    Fully vectorised (no Python loops).
    """
    length = len(arr)
    out = np.full(length, np.nan, dtype=np.float64)
    if n < 2 or length < n:
        return out

    # Constants for x = 0, 1, ..., n-1
    sx = n * (n - 1) / 2.0
    sx2 = n * (n - 1) * (2 * n - 1) / 6.0
    denom = n * sx2 - sx * sx
    if abs(denom) < 1e-15:
        return out

    indices = np.arange(length, dtype=np.float64)
    jy = indices * arr

    cumsum_y = np.cumsum(arr)
    cumsum_jy = np.cumsum(jy)

    # Vectorised rolling sums
    sy = cumsum_y[n - 1 :] - np.concatenate(([0.0], cumsum_y[: length - n]))
    sum_jy = cumsum_jy[n - 1 :] - np.concatenate(([0.0], cumsum_jy[: length - n]))
    lo = np.arange(0, length - n + 1, dtype=np.float64)  # window start index
    sxy = sum_jy - lo * sy

    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    out[n - 1 :] = a + b * (n - 1)
    return out


def _calc_zscore_hybrid(
    close: np.ndarray,
    len_ma: int,
    len_reg: int,
    z_smooth: int = 1,
    z_scale: float = 1.0,
) -> np.ndarray:
    """Hybrid z-score: linreg(len_reg) baseline with SMA(len_ma) fallback.

    Matches the "Structural Risk & Exhaustion" Pine Script logic:

    1. Primary baseline: ``ta.linreg(logp, len_reg, 0)`` — follows the
       macro trend slope, so trending assets don't appear overextended.
    2. Fallback baseline: ``ta.sma(logp, len_ma)`` — used when the coin
       has fewer than ``len_reg`` bars of history.
    3. Z-score normalisation uses the SMA window (``len_ma``) for the
       inner mean/stdev of deviation, matching the Pine implementation.
    4. Optional smoothing: ``ta.sma(z, z_smooth)`` (default 1 = off).
    5. Optional scale multiplier (default 1.0).
    """
    logp = np.log(np.maximum(close, _EPS))

    # SMA baseline (fallback)
    log_ma = _sma(logp, len_ma)

    # Linear regression baseline (primary)
    log_reg = _linreg(logp, len_reg)

    # Hybrid: use regression where available, SMA fallback
    log_baseline = np.where(np.isnan(log_reg), log_ma, log_reg)

    # Deviation from baseline
    dev = logp - log_baseline  # NaN where baseline is NaN

    # Z-score normalisation (same window as SMA)
    mean_dev = _sma_nan_safe(dev, len_ma)
    std_dev = _stdev_nan_safe(dev, len_ma)

    effectively_zero = (std_dev < _EPS) | np.isnan(std_dev)
    safe_std = np.where(effectively_zero, 1.0, std_dev)
    z = (dev - mean_dev) / safe_std
    z = np.where(effectively_zero, 0.0, z)

    # Scale
    z = z * z_scale

    # Smooth
    if z_smooth > 1:
        z = _sma_nan_safe(z, z_smooth)

    return z


def _calc_zscore(close: np.ndarray, length: int) -> np.ndarray:
    """Legacy SMA-only z-score (kept for reference, no longer used)."""
    logp = np.log(np.maximum(close, _EPS))
    ma = _sma(logp, length)
    dev = logp - ma
    mean_dev = _sma_nan_safe(dev, length)
    std_dev = _stdev_nan_safe(dev, length)
    effectively_zero = (std_dev < _EPS) | np.isnan(std_dev)
    safe_std = np.where(effectively_zero, 1.0, std_dev)
    z = (dev - mean_dev) / safe_std
    z = np.where(effectively_zero, 0.0, z)
    return z


def _calc_beta(
    asset_close: np.ndarray,
    bench_close: np.ndarray,
    length: int,
) -> np.ndarray:
    """Pine ``calc_beta``: rolling beta of asset returns vs benchmark returns.

    The Pine code is::

        asset_ret  = change(asset_price) / asset_price[1]
        bench_ret  = change(benchmark_price) / benchmark_price[1]
        asset_mean = sma(asset_ret, len)
        bench_mean = sma(bench_ret, len)
        covar      = sma((asset_ret - asset_mean) * (bench_ret - bench_mean), len)
        bench_var  = variance(bench_ret, len)
        covar / (bench_var == 0 ? 1e-10 : bench_var)

    Returns are NaN on the first bar, so SMA/variance start one bar later.
    We use NaN-safe helpers for the downstream calculations.
    """
    # Simple returns; first element is NaN
    asset_ret = np.empty_like(asset_close, dtype=np.float64)
    asset_ret[0] = np.nan
    prev_a = asset_close[:-1]
    prev_a_safe = np.where(prev_a == 0, _EPS, prev_a)
    asset_ret[1:] = (asset_close[1:] - asset_close[:-1]) / prev_a_safe

    bench_ret = np.empty_like(bench_close, dtype=np.float64)
    bench_ret[0] = np.nan
    prev_b = bench_close[:-1]
    prev_b_safe = np.where(prev_b == 0, _EPS, prev_b)
    bench_ret[1:] = (bench_close[1:] - bench_close[:-1]) / prev_b_safe

    asset_mean = _sma_nan_safe(asset_ret, length)
    bench_mean = _sma_nan_safe(bench_ret, length)

    cross = (asset_ret - asset_mean) * (bench_ret - bench_mean)
    covar = _sma_nan_safe(cross, length)
    bench_var = _variance_nan_safe(bench_ret, length)

    safe_var = np.where((bench_var == 0) | np.isnan(bench_var), _EPS, bench_var)
    beta = covar / safe_var
    return beta


# ---------------------------------------------------------------------------
# ATR & volatility scaling
# ---------------------------------------------------------------------------

def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Compute True Range series (NaN for bar 0)."""
    tr = np.full(len(high), np.nan, dtype=np.float64)
    if len(high) < 2:
        return tr
    prev_close = np.concatenate(([np.nan], close[:-1]))
    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    tr[0] = high[0] - low[0]
    return tr


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int) -> np.ndarray:
    """Average True Range (simple moving average of TR)."""
    tr = _true_range(high, low, close)
    return _sma_nan_safe(tr, n)


def _vol_scale_factor(atr_ratio: float) -> float:
    """Derive a threshold scaling multiplier from the ATR fast/slow ratio.

    In compressed volatility regimes, z-scores are less meaningful at
    fixed absolute levels, so thresholds tighten.  In elevated vol,
    z-scores naturally extend further, so thresholds widen.

    Returns a multiplier for Z_BLOWOFF, Z_TRIM, etc.
    """
    if atr_ratio < 0.8:
        return 0.85       # Compressed: tighter thresholds
    if atr_ratio < 1.1:
        return 1.0         # Normal: baseline
    if atr_ratio < 1.5:
        return 1.15        # Elevated: wider thresholds
    return 1.25             # High vol: widest


# ---------------------------------------------------------------------------
# Regime probability vectors (vectorised)
# ---------------------------------------------------------------------------

def _soft_gate(x: np.ndarray, center: float, width: float = 0.15) -> np.ndarray:
    """Smooth sigmoid transition: 0→1 over ~2*width around center.

    Replaces hard np.where cutoffs so regime probabilities transition
    gradually instead of flipping 0↔1 at a single z-score value.
    """
    return 1.0 / (1.0 + np.exp(-(x - center) / max(width, 0.01)))


def _calc_regime_probabilities(
    z: np.ndarray,
    energy: np.ndarray,
    vol: np.ndarray,
    vol_low: np.ndarray,
    vol_high: np.ndarray,
    vol_scale: float = 1.0,
) -> Tuple[np.ndarray, ...]:
    """Return six probability arrays (markup, blowoff, reacc, markdown,
    cap, accum) normalised so they sum to 1 at each bar.

    NaN inputs are replaced with 0.0 before computing so that bars without
    a valid z-score yield uniform-ish probabilities rather than NaN output.

    ``vol_scale`` adjusts the Z-score thresholds used for regime boundaries
    (dynamic thresholds based on ATR regime).

    Regime probabilities use smooth sigmoid transitions (``_soft_gate``)
    instead of hard step functions, so confidence values change gradually
    as z-score drifts across boundaries rather than flipping 0%↔100%.
    """
    # Dynamic Z-thresholds scaled by volatility regime
    z_blowoff = Z_BLOWOFF * vol_scale
    z_cap = Z_CAPITULATION * vol_scale

    # Replace NaN with neutral values for safe arithmetic
    z_safe = np.nan_to_num(z, nan=0.0)
    energy_safe = np.nan_to_num(energy, nan=0.0)
    vol_safe = np.nan_to_num(vol, nan=0.0)

    # Convert bool arrays, handling potential NaN underneath
    vl = np.asarray(vol_low, dtype=bool)
    vh = np.asarray(vol_high, dtype=bool)

    # Vol-state as smooth float [0,1] for gating
    vl_f = vl.astype(np.float64)
    vh_f = vh.astype(np.float64)
    not_vh_f = 1.0 - vh_f

    # Vol gates as *boosters* (base + boost), not hard gates.
    # Without this, normal-vol bars only have MARKUP + REACC competing
    # which always gives 100% confidence — no uncertainty.
    _BASE = 0.15  # baseline probability weight even without vol confirmation
    vl_boost = _BASE + (1.0 - _BASE) * vl_f   # 0.15 base, 1.0 when vol_low
    vh_boost = _BASE + (1.0 - _BASE) * vh_f   # 0.15 base, 1.0 when vol_high
    not_vh_boost = _BASE + (1.0 - _BASE) * not_vh_f

    # Dynamic MARKUP/REACC deadband — prevents regime whiplash on small z moves
    # and adapts to market energy. In strong trending markets the deadband widens
    # so mild pullbacks stay labelled MARKUP (not flipped to REACC on every dip).
    #   - Base deadband: 0.3 * vol_scale (0.25 compressed → 0.38 high vol)
    #   - Energy bonus: accelerating markets (energy > 1.1) add (e-1.1)*0.3
    # Shift z-view so MARKUP and REACC have a gap between them around zero.
    z_deadband = 0.3 * vol_scale + np.maximum(0.0, energy_safe - 1.1) * 0.3
    z_markup_view = z_safe + z_deadband  # MARKUP activates when z > -deadband
    z_reacc_view = z_safe - z_deadband   # REACC activates when z < -deadband

    # MARKUP: ramps up with positive shifted z, energy > 1 boosts
    energy_boost = 0.5 + 0.5 * _soft_gate(energy_safe, 1.0, 0.2)
    p_markup = np.maximum(0.0, z_markup_view) * energy_boost

    # BLOWOFF: ramps up beyond z_blowoff (smooth onset) — unchanged, uses raw z
    p_blowoff = np.maximum(0.0, z_safe - z_blowoff) * _soft_gate(z_safe, z_blowoff, 0.2)

    # REACC: smooth ramp for shifted z < 0, boosted by NOT high-vol
    p_reacc = np.maximum(0.0, -z_reacc_view) * _soft_gate(-z_reacc_view, 0.0, 0.2) * not_vh_boost

    # MARKDOWN: z < 0, boosted by high-vol
    p_md = vol_safe * 2.0 * _soft_gate(-z_safe, 0.0, 0.2) * vh_boost

    # CAPITULATION: z below cap threshold, boosted by low-vol
    p_cap = np.maximum(0.0, -z_safe) * _soft_gate(-z_safe, -z_cap, 0.3) * vl_boost

    # ACCUM: z near zero — smooth bell shape, boosted by low-vol
    p_acc = _soft_gate(z_safe, -0.5, 0.15) * (1.0 - _soft_gate(z_safe, 0.5, 0.15)) * vl_boost

    sum_p = p_markup + p_blowoff + p_reacc + p_md + p_cap + p_acc + _EPS

    p_markup = p_markup / sum_p
    p_blowoff = p_blowoff / sum_p
    p_reacc = p_reacc / sum_p
    p_md = p_md / sum_p
    p_cap = p_cap / sum_p
    p_acc = p_acc / sum_p

    return p_markup, p_blowoff, p_reacc, p_md, p_cap, p_acc


# ---------------------------------------------------------------------------
# Regime persistence (bar-by-bar simulation)
# ---------------------------------------------------------------------------

def _resolve_regime_with_persistence(
    prob_stack: np.ndarray,  # shape (6, N)
) -> Tuple[np.ndarray, np.ndarray]:
    """Simulate Pine-style regime persistence with hysteresis.

    The dominant regime is the one with the highest probability.
    A new regime must persist for ``MIN_REGIME_BARS`` consecutive bars before
    the label actually switches.

    **Hysteresis** (asymmetric transitions within bullish family):
    When current regime is MARKUP/REACC/ACCUM and the candidate is another
    bullish regime, require the candidate's probability to exceed the current
    regime's probability by ``_HYSTERESIS_RATIO`` before accepting the switch.
    This prevents regime whiplash on small z-score fluctuations.
    Exit transitions (to BLOWOFF/MARKDOWN/CAP) are NOT hysteresis-protected
    for safety — if a bearish regime becomes dominant, switch immediately
    (subject to persistence).

    Returns
    -------
    regimes : int array  -- regime index per bar
    confidences : float array  -- confidence (probability of dominant regime)
    """
    n = prob_stack.shape[1]
    if n == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float64)

    # Regime indices: 0=MARKUP, 1=BLOWOFF, 2=REACC, 3=MARKDOWN, 4=CAP, 5=ACCUM
    BULLISH_FAMILY = {0, 2, 5}  # MARKUP, REACC, ACCUM
    _HYSTERESIS_RATIO = 1.25    # candidate must have 25% more prob to switch

    def _pick_candidate(current: int, probs: np.ndarray) -> int:
        """Apply hysteresis: within bullish family, current regime gets a boost."""
        if current not in BULLISH_FAMILY:
            return int(np.argmax(probs))
        # Boost current regime's probability within bullish family only
        adjusted = probs.copy()
        for idx in BULLISH_FAMILY:
            if idx == current:
                continue
            # Candidate must beat current by the hysteresis ratio
            adjusted[idx] = probs[idx] / _HYSTERESIS_RATIO
        return int(np.argmax(adjusted))

    regimes = np.empty(n, dtype=np.int64)
    confidences = np.empty(n, dtype=np.float64)

    current_regime: int = int(np.argmax(prob_stack[:, 0]))
    pending_regime: int = current_regime
    pending_count: int = 1

    for i in range(n):
        col = prob_stack[:, i]
        candidate = _pick_candidate(current_regime, col)

        if candidate == current_regime:
            pending_regime = current_regime
            pending_count = 0
        elif candidate == pending_regime:
            pending_count += 1
            if pending_count >= MIN_REGIME_BARS:
                current_regime = pending_regime
                pending_count = 0
        else:
            pending_regime = candidate
            pending_count = 1

        regimes[i] = current_regime
        confidences[i] = float(prob_stack[current_regime, i])

    return regimes, confidences


# ---------------------------------------------------------------------------
# Signal generation (Module 14)
# ---------------------------------------------------------------------------

def _generate_signal(
    phase: str,
    z: float,
    vol_low: bool,
    vol_high: bool,
    confidence: float,
    market_consensus: Optional[str] = None,
    vol_scale: float = 1.0,
) -> str:
    """Derive the action signal from the current regime and market state.

    Priority-ordered rules matching the Pine Script Module 14 logic.
    ``confidence`` here is already in 0-1 scale (not percentage).
    ``vol_scale`` adjusts Z-thresholds for the current volatility regime.
    """
    z_trim = Z_TRIM * vol_scale
    z_trim_hard = Z_TRIM_HARD * vol_scale
    z_blowoff = Z_BLOWOFF * vol_scale

    if phase == "ABSORBING":
        return "NO_LONG"
    if phase == "BLOWOFF" and z > z_trim_hard:
        return "TRIM_HARD"
    if phase == "BLOWOFF" and z > z_trim:
        return "TRIM"
    if phase == "BLOWOFF":
        return "TRIM"
    if phase == "MARKDOWN" and market_consensus == "RISK_OFF":
        return "RISK_OFF"
    if phase == "MARKDOWN":
        return "WAIT"
    # Entry conditions
    if phase == "ACCUM" and z < 0 and vol_low and confidence > 0.4:
        return "ACCUMULATE"
    if phase == "CAP" and z < -1.0 and vol_high and confidence > 0.3:
        return "ACCUMULATE"
    if phase == "MARKUP" and z > -0.5 and z < 1.0 and confidence > 0.6:
        return "STRONG_LONG"
    if phase == "MARKUP" and z > 1.0 and z < z_blowoff and confidence > 0.5:
        return "LIGHT_LONG"
    if phase == "REACC" and z < 0.5 and confidence > 0.4:
        return "LIGHT_LONG"
    return "WAIT"


# ---------------------------------------------------------------------------
# Volatility state label
# ---------------------------------------------------------------------------

def _vol_state_label(vol_low_flag: bool, vol_high_flag: bool) -> str:
    if vol_high_flag:
        return "HIGH"
    if vol_low_flag:
        return "LOW"
    return "MID"


# ---------------------------------------------------------------------------
# Tiny helpers for safe last-value extraction
# ---------------------------------------------------------------------------

def _last_finite(arr: np.ndarray, fallback: float = 0.0) -> float:
    """Return the last finite (non-NaN, non-Inf) element, or *fallback*."""
    if len(arr) == 0:
        return fallback
    val = arr[-1]
    if np.isfinite(val):
        return float(val)
    # Scan backwards for a finite value
    finite_mask = np.isfinite(arr)
    if not np.any(finite_mask):
        return fallback
    return float(arr[finite_mask][-1])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_rcce(
    ohlcv: Dict[str, np.ndarray],
    btc_ohlcv: Optional[Dict[str, np.ndarray]] = None,
    eth_ohlcv: Optional[Dict[str, np.ndarray]] = None,
) -> dict:
    """Compute the RCCE v2.2 indicator for the given OHLCV series.

    Parameters
    ----------
    ohlcv : dict
        Keys ``"open"``, ``"high"``, ``"low"``, ``"close"``, ``"volume"``,
        ``"timestamp"`` each mapping to a 1-D numpy array of equal length.
    btc_ohlcv, eth_ohlcv : dict or None
        Same structure as *ohlcv* for BTC and ETH reference series.
        Used to compute rolling beta.  Pass ``None`` when unavailable.

    Returns
    -------
    dict  with keys:
        regime, confidence, z_score, energy, vol_state, raw_signal,
        asset_class, beta_btc, beta_eth, momentum, regime_probabilities
    """
    close: np.ndarray = np.asarray(ohlcv["close"], dtype=np.float64)
    n = len(close)

    # Default / empty result used when data is insufficient
    _empty_result: dict = {
        "regime": "FLAT",
        "confidence": 0.0,
        "z_score": 0.0,
        "energy": 0.0,
        "vol_state": "MID",
        "raw_signal": "WAIT",
        "asset_class": "",
        "beta_btc": 0.0,
        "beta_eth": 0.0,
        "momentum": 0.0,
        "regime_probabilities": {
            "markup": 0.0,
            "blowoff": 0.0,
            "reacc": 0.0,
            "markdown": 0.0,
            "cap": 0.0,
            "accum": 0.0,
        },
    }

    # ------------------------------------------------------------------
    # Guard: not enough data
    # ------------------------------------------------------------------
    if n < LEN_LONG:
        return _empty_result

    # ------------------------------------------------------------------
    # Warmup quality: how well-populated is the z-score normalisation?
    # Full warmup needs 2 × LEN_LONG bars.  With fewer bars the inner
    # SMA/stdev operate over a truncated window, inflating z-scores.
    # warmup_ratio goes from ~0.0 (barely enough) to 1.0 (fully warmed).
    # ------------------------------------------------------------------
    warmup_ratio = min(1.0, max(0.0, (n - LEN_LONG) / LEN_LONG))

    # ------------------------------------------------------------------
    # 1. Z-Score (hybrid linreg + SMA fallback)
    # ------------------------------------------------------------------
    z_series = _calc_zscore_hybrid(
        close, len_ma=LEN_LONG, len_reg=LEN_REGRESSION,
        z_smooth=Z_SMOOTH, z_scale=Z_SCALE,
    )

    # Determine which baseline was actually used on the last bar
    has_regression = n >= LEN_REGRESSION
    baseline_type = "REGRESSION" if has_regression else "SMA_FALLBACK"

    # Dampen z-scores when warmup is incomplete.  A coin with only
    # 250 bars (warmup_ratio ≈ 0.25) gets its z multiplied by ~0.25,
    # preventing inflated regime calls on thin data.
    if warmup_ratio < 1.0:
        z_series = z_series * warmup_ratio

    # ------------------------------------------------------------------
    # 2. Volatility
    # ------------------------------------------------------------------
    vol_series = _stdev(close, LEN_SHORT) / np.maximum(close, _EPS)
    vol_p25 = _percentile_rolling(vol_series, LEN_SHORT, 25)
    vol_p75 = _percentile_rolling(vol_series, LEN_SHORT, 75)

    vol_low_series = np.where(
        np.isnan(vol_series) | np.isnan(vol_p25), False, vol_series < vol_p25,
    )
    vol_high_series = np.where(
        np.isnan(vol_series) | np.isnan(vol_p75), False, vol_series > vol_p75,
    )

    # ------------------------------------------------------------------
    # 3. Energy
    # ------------------------------------------------------------------
    stdev_fast = _stdev(close, LEN_ENERGY_FAST)
    stdev_slow = _stdev(close, LEN_ENERGY_SLOW)
    energy_series = stdev_fast / np.where(
        (stdev_slow == 0) | np.isnan(stdev_slow), _EPS, stdev_slow,
    )

    # ------------------------------------------------------------------
    # 3b. ATR-based volatility scaling (dynamic thresholds)
    # ------------------------------------------------------------------
    high: np.ndarray = np.asarray(ohlcv["high"], dtype=np.float64)
    low: np.ndarray = np.asarray(ohlcv["low"], dtype=np.float64)
    atr_fast = _atr(high, low, close, LEN_ATR_FAST)
    atr_slow = _atr(high, low, close, LEN_ATR_SLOW)
    atr_fast_last = _last_finite(atr_fast, 1.0)
    atr_slow_last = _last_finite(atr_slow, 1.0)
    atr_ratio = atr_fast_last / atr_slow_last if atr_slow_last > _EPS else 1.0
    vol_scale = _vol_scale_factor(atr_ratio)

    # ------------------------------------------------------------------
    # 4. Regime probabilities (vectorised, with dynamic thresholds)
    # ------------------------------------------------------------------
    p_markup, p_blowoff, p_reacc, p_md, p_cap, p_acc = (
        _calc_regime_probabilities(
            z_series, energy_series, vol_series, vol_low_series, vol_high_series,
            vol_scale=vol_scale,
        )
    )
    prob_stack = np.vstack(
        [p_markup, p_blowoff, p_reacc, p_md, p_cap, p_acc],
    )  # (6, N)

    # ------------------------------------------------------------------
    # 5. Regime persistence (bar-by-bar)
    # ------------------------------------------------------------------
    # Find the first bar where z_series is valid (finite) so persistence
    # starts from meaningful data.
    finite_z = np.isfinite(z_series)
    if not np.any(finite_z):
        return _empty_result
    first_valid = int(np.argmax(finite_z))

    regime_indices, confidence_series = _resolve_regime_with_persistence(
        prob_stack[:, first_valid:],
    )
    full_regime = np.full(
        n,
        regime_indices[0] if len(regime_indices) > 0 else 5,
        dtype=np.int64,
    )
    full_regime[first_valid:] = regime_indices
    full_confidence = np.full(n, 0.0, dtype=np.float64)
    full_confidence[first_valid:] = confidence_series

    # ------------------------------------------------------------------
    # 6. Beta calculations
    # ------------------------------------------------------------------
    beta_btc_val: float = 0.0
    beta_eth_val: float = 0.0

    if btc_ohlcv is not None:
        btc_close = np.asarray(btc_ohlcv["close"], dtype=np.float64)
        if np.array_equal(close, btc_close):
            beta_btc_val = 1.0
        else:
            min_len = min(len(close), len(btc_close))
            if min_len > LEN_BETA + 1:
                beta_btc_series = _calc_beta(
                    close[-min_len:], btc_close[-min_len:], LEN_BETA,
                )
                beta_btc_val = _last_finite(beta_btc_series, 0.0)

    if eth_ohlcv is not None:
        eth_close = np.asarray(eth_ohlcv["close"], dtype=np.float64)
        if np.array_equal(close, eth_close):
            beta_eth_val = 1.0
        else:
            min_len = min(len(close), len(eth_close))
            if min_len > LEN_BETA + 1:
                beta_eth_series = _calc_beta(
                    close[-min_len:], eth_close[-min_len:], LEN_BETA,
                )
                beta_eth_val = _last_finite(beta_eth_series, 0.0)

    # ------------------------------------------------------------------
    # 7. Extract LAST-bar scalars
    # ------------------------------------------------------------------
    z_last = _last_finite(z_series, 0.0)
    energy_last = _last_finite(energy_series, 0.0)

    vol_low_last = bool(vol_low_series[-1])
    vol_high_last = bool(vol_high_series[-1])

    regime_idx = int(full_regime[-1])
    regime_label = (
        _REGIME_LABELS[regime_idx] if regime_idx < len(_REGIME_LABELS) else "FLAT"
    )
    confidence_last = float(full_confidence[-1])

    # ------------------------------------------------------------------
    # 8. Momentum proxy (short-term z-score rate of change)
    # ------------------------------------------------------------------
    momentum_lookback = min(5, n - 1)
    if (
        momentum_lookback > 0
        and np.isfinite(z_series[-1])
        and np.isfinite(z_series[-1 - momentum_lookback])
    ):
        momentum = float(z_series[-1] - z_series[-1 - momentum_lookback])
    else:
        momentum = 0.0

    # ------------------------------------------------------------------
    # 8b. Blowoff declining detection (z peaked and now rolling over)
    # ------------------------------------------------------------------
    # Matches Pine: z_declining = z_final < ta.highest(z_final, 2)
    if n >= 3 and np.isfinite(z_series[-1]) and np.isfinite(z_series[-2]):
        z_recent_peak = float(np.nanmax(z_series[-3:]))
        z_declining = z_last < z_recent_peak
    else:
        z_declining = False

    # ------------------------------------------------------------------
    # 9. Raw Signal (RCCE-only, before cross-engine synthesis)
    # ------------------------------------------------------------------
    raw_signal = _generate_signal(
        phase=regime_label,
        z=z_last,
        vol_low=vol_low_last,
        vol_high=vol_high_last,
        confidence=confidence_last,
        market_consensus=None,  # synthesizer handles consensus gating
        vol_scale=vol_scale,
    )

    # ------------------------------------------------------------------
    # 10. Assemble output
    # ------------------------------------------------------------------
    return {
        "regime": regime_label,
        "confidence": round(confidence_last * 100.0, 2),
        "z_score": round(z_last, 4),
        "energy": round(energy_last, 4),
        "vol_state": _vol_state_label(vol_low_last, vol_high_last),
        "raw_signal": raw_signal,
        "asset_class": "",  # placeholder -- scanner sets this
        "beta_btc": round(beta_btc_val, 4),
        "beta_eth": round(beta_eth_val, 4),
        "momentum": round(momentum, 4),
        "vol_scale": round(vol_scale, 3),
        "atr_ratio": round(atr_ratio, 3),
        "data_bars": n,
        "warmup_quality": round(warmup_ratio, 2),
        "baseline_type": baseline_type,
        "z_declining": z_declining,
        "regime_probabilities": {
            "markup": round(float(np.nan_to_num(p_markup[-1], nan=0.0)), 4),
            "blowoff": round(float(np.nan_to_num(p_blowoff[-1], nan=0.0)), 4),
            "reacc": round(float(np.nan_to_num(p_reacc[-1], nan=0.0)), 4),
            "markdown": round(float(np.nan_to_num(p_md[-1], nan=0.0)), 4),
            "cap": round(float(np.nan_to_num(p_cap[-1], nan=0.0)), 4),
            "accum": round(float(np.nan_to_num(p_acc[-1], nan=0.0)), 4),
        },
    }
