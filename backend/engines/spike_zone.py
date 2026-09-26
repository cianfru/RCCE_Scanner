"""
After a spike: where past spikes bottomed, and where the engine's mean is today
(docs/reviews/after-the-spike-study.md, "Spike fan on the coin chart").

- ``mean_levels``: the price at which z would be 0 and 1 on each bar, from the same
  regression baseline, deviation mean and deviation spread as the engine's z-score.
- ``last_spike``: the engine's cool-off spike (last bar with z >= Z_BLOWOFF, its run of
  bars with z >= 2.0) and its anchor, the first bar after the run (known at the time).
- ``zone``: the box where past spikes bottomed, from seeds/spike_paths.json, placed from
  the anchor. A picture of history, not a forecast.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from engines.rcce_engine import (
    LEN_LONG, LEN_REGRESSION, Z_BLOWOFF, _EPS, _linreg, _sma, _sma_nan_safe, _stdev_nan_safe,
)

SEED = Path(__file__).resolve().parent.parent / "seeds" / "spike_paths.json"
RUN_Z = 2.0
HORIZON = 60


def mean_levels(close, ks=(0.0, 1.0)) -> Dict[float, np.ndarray]:
    """Price per bar at which the engine's z-score would equal each k."""
    close = np.asarray(close, dtype=np.float64)
    n = len(close)
    logp = np.log(np.maximum(close, _EPS))
    log_reg = _linreg(logp, LEN_REGRESSION)
    base = np.where(np.isnan(log_reg), _sma(logp, LEN_LONG), log_reg)
    dev = logp - base
    mean_dev = _sma_nan_safe(dev, LEN_LONG)
    std_dev = _stdev_nan_safe(dev, LEN_LONG)
    # compute_rcce scales z by the warm-up ratio on short histories; invert that too.
    warm = min(1.0, max(0.0, (n - LEN_LONG) / LEN_LONG)) or 1.0
    return {k: np.exp(base + mean_dev + (k / warm) * std_dev) for k in ks}


def last_spike(z, close) -> Optional[dict]:
    """The last spike and its anchor bar (None if no bar reached Z_BLOWOFF)."""
    z = np.nan_to_num(np.asarray(z, dtype=np.float64), nan=-np.inf)
    close = np.asarray(close, dtype=np.float64)
    idx = np.where(z >= Z_BLOWOFF)[0]
    if len(idx) == 0:
        return None
    s = int(idx[-1])
    a, b = s, s
    while a > 0 and z[a - 1] >= RUN_Z:
        a -= 1
    while b + 1 < len(z) and z[b + 1] >= RUN_Z:
        b += 1
    peak_i = a + int(np.argmax(close[a:b + 1]))
    anchor = b + 1 if b + 1 < len(z) else None          # None: the spike is still running
    # A later close above the peak means the trend resumed: the unwind picture no longer applies.
    superseded = bool(np.any(close[b + 1:] > close[peak_i]))
    return {"run_start": a, "run_end": b, "peak_index": peak_i, "peak": float(close[peak_i]), "superseded": superseded,
            "anchor_index": anchor, "anchor_close": float(close[anchor]) if anchor is not None else None,
            "bars_since_anchor": (len(z) - 1 - anchor) if anchor is not None else None}


@lru_cache(maxsize=1)
def _stats() -> dict:
    try:
        return json.loads(SEED.read_text())
    except (OSError, ValueError):
        return {}


def zone(timeframe: str, anchor_close: float) -> Optional[dict]:
    """Where past spikes bottomed, relative to this anchor: price box and bar offsets."""
    st = _stats().get(timeframe)
    if not st:
        return None
    d, t = st["low_depth"], st["low_bar"]
    return {"n": st["n"], "top": anchor_close * (1 + d["p75"]), "bottom": anchor_close * (1 + d["p25"]),
            "median_price": anchor_close * (1 + d["p50"]), "from_bar": t["p25"], "to_bar": t["p75"], "median_bar": t["p50"],
            "never_fell_5pct": st["never_fell_5pct"], "horizon": st["horizon"]}
