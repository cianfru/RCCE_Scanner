"""Calibrated next-bar range forecast.

Empirical, not a model. Answers one question: what is the probability that the
next bar's true range lands in the TOP QUARTILE of this market's own trailing
100-bar range distribution? The conditioning variable is where the *current*
bar's range sits in that same distribution -- volatility clusters, so a large
bar is followed by a large bar far more often than chance.

Forecasts MAGNITUDE ONLY. It says nothing about direction. Next-bar direction
was tested with the identical method and behaved like a coin flip
(train->test sign agreement 36-61%), whereas this held up with train->test
correlation above 0.97 and 0.02pp pooled calibration error on 4h. Treat it as
risk context -- position sizing and stop placement -- never as a trade signal.

The table is fitted on the full Hyperliquid perp history (~718k 4h bars,
~148k 1d bars) after being validated on a chronological train/test split.
Refit it when the universe or venue changes materially.
"""
from __future__ import annotations

from typing import Optional, Sequence

# Per-timeframe: index = bucket of the current bar's trailing range percentile
# (<25th, 25-50th, 50-75th, 75-90th, >90th).
#   p        = P(next bar's true range in the top quartile of trailing 100)
#   atr_mult = median(next bar's true range / ATR14), a size expectation
_TABLE = {
    "4h": [
        {"p": 0.111, "atr_mult": 0.80, "n": 199123},
        {"p": 0.174, "atr_mult": 0.85, "n": 173732},
        {"p": 0.256, "atr_mult": 0.88, "n": 164873},
        {"p": 0.370, "atr_mult": 0.92, "n": 100146},
        {"p": 0.561, "atr_mult": 1.05, "n": 80253},
    ],
    "1d": [
        {"p": 0.059, "atr_mult": 0.77, "n": 51635},
        {"p": 0.120, "atr_mult": 0.84, "n": 34742},
        {"p": 0.230, "atr_mult": 0.89, "n": 29892},
        {"p": 0.419, "atr_mult": 0.93, "n": 17186},
        {"p": 0.680, "atr_mult": 1.11, "n": 14646},
    ],
}
_EDGES = (0.25, 0.50, 0.75, 0.90)
_LABELS = ("VERY LOW", "LOW", "NORMAL", "ELEVATED", "HIGH")
WINDOW = 100
ATR_N = 14


def _bucket(pct: float) -> int:
    for i, e in enumerate(_EDGES):
        if pct < e:
            return i
    return len(_EDGES)


def forecast(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    timeframe: str,
) -> Optional[dict]:
    """Return the next-bar range forecast, or None when data is insufficient.

    Uses only bars up to and including the last one -- no lookahead.
    """
    table = _TABLE.get(timeframe)
    if table is None or len(close) < WINDOW + 2:
        return None
    try:
        trs = []
        for j in range(len(close) - WINDOW, len(close)):
            prev = close[j - 1]
            trs.append(max(high[j] - low[j], abs(high[j] - prev), abs(low[j] - prev)))
    except (IndexError, TypeError):
        return None
    atr = sum(trs[-ATR_N:]) / ATR_N
    if atr <= 0:
        return None
    current = trs[-1]
    pct = sum(1 for t in trs if t <= current) / len(trs)
    row = table[_bucket(pct)]
    last = close[-1]
    return {
        "probability": row["p"],
        "label": _LABELS[_bucket(pct)],
        "atr_mult": row["atr_mult"],
        "expected_range_pct": round(row["atr_mult"] * atr / last * 100, 2) if last else 0.0,
        "current_percentile": round(pct * 100, 1),
        "sample_size": row["n"],
    }
