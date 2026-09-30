"""Price sanity checks shared by the data fetcher, the scanner and the executor.

A quote is compared with independent references before it is stored, shown or
acted on. Anything more than PRICE_SANITY_MAX_RATIO away from a reference (in
either direction) is treated as a feed error, not a market move.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# A factor of 3 between a quote and its reference is far outside any move seen
# between two scans, and far inside the unit errors seen so far (100x-1000x).
PRICE_SANITY_MAX_RATIO = 3.0

# References that come from Hyperliquid directly rather than from our candle store.
LIVE_REFERENCES = ("Hyperliquid mark", "Hyperliquid mid")
_LIVE_MAX_AGE_S = 6 * 3600


def positive(value) -> Optional[float]:
    """The value as a finite positive float, else None."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def ratio(price, reference) -> Optional[float]:
    """How many times apart two prices are (>= 1), or None if either is unusable."""
    p, r = positive(price), positive(reference)
    if p is None or r is None:
        return None
    return max(p / r, r / p)


def within(price, reference, max_ratio: float = PRICE_SANITY_MAX_RATIO) -> bool:
    """True when *reference* is unusable or *price* is within *max_ratio* of it."""
    k = ratio(price, reference)
    return k is None or k <= max_ratio


def price_rejection(price, references: Dict[str, float], last_mark=None,
                    max_ratio: float = PRICE_SANITY_MAX_RATIO) -> Optional[str]:
    """Why *price* must not be used, or None when it passes.

    *references* maps a reference name to its price; unusable ones are ignored.
    The candle close shares its source with the scan price, so without a live
    Hyperliquid reference the position's last accepted mark is checked too.
    """
    p = positive(price)
    if p is None:
        return f"no usable price ({price!r})"
    usable = {name: positive(ref) for name, ref in references.items() if positive(ref) is not None}
    for name, ref in usable.items():
        k = ratio(p, ref)
        if k > max_ratio:
            return f"price {p:g} is {k:.1f}x away from the {name} {ref:g}"
    if not any(name in LIVE_REFERENCES for name in usable):
        k = ratio(p, last_mark)
        if k is not None and k > max_ratio:
            return f"price {p:g} is {k:.1f}x away from the last accepted mark {positive(last_mark):g}"
    return None


def candle_close(symbol: str) -> Optional[float]:
    """Close of the freshest stored 4h or 1d candle for *symbol*."""
    try:
        from data_fetcher import _ohlcv_store
    except Exception:
        return None
    best = None
    for tf in ("4h", "1d"):
        data = _ohlcv_store.get(symbol, tf)
        if data is None or not len(data.get("close", [])):
            continue
        close = positive(data["close"][-1])
        observed = _ohlcv_store.observed_at(symbol, tf) or 0.0
        if close is not None and (best is None or observed > best[0]):
            best = (observed, close)
    return best[1] if best else None


def live_references(symbol: str, hl_metrics: Optional[dict] = None) -> Dict[str, float]:
    """Hyperliquid mark (from the last synthesis pass) or, failing that, the ticker mid."""
    refs: Dict[str, float] = {}
    if hl_metrics is None:
        try:
            from scanner import cache
            hl_metrics = getattr(cache, "_last_hl_metrics", None) or {}
        except Exception:
            hl_metrics = {}
    metrics = hl_metrics.get(symbol) if hl_metrics else None
    if metrics is not None:
        mark = positive(getattr(metrics, "mark_price", None))
        stamp = positive(getattr(metrics, "timestamp", None))
        if mark is not None and (stamp is None or time.time() - stamp <= _LIVE_MAX_AGE_S):
            refs["Hyperliquid mark"] = mark
    if not refs:
        try:
            from price_ticker import PriceTicker
            ticker = PriceTicker._instance
            mid = positive(ticker._prices.get(symbol)) if ticker is not None else None
            if mid is not None:
                refs["Hyperliquid mid"] = mid
        except Exception:
            pass
    return refs


def reference_prices(symbol: str) -> Dict[str, float]:
    """Every reference available for *symbol*: stored candle close plus live Hyperliquid prices."""
    refs = live_references(symbol)
    close = candle_close(symbol)
    if close is not None:
        refs["candle close"] = close
    return refs


def series_consistent(reference: Optional[dict], candidate: Optional[dict],
                      max_ratio: float = PRICE_SANITY_MAX_RATIO) -> Optional[bool]:
    """Whether two OHLCV series quote the same instrument in the same unit.

    Compares closes at shared candle timestamps (median ratio). Returns None
    when there is nothing to compare.
    """
    if not reference or not candidate:
        return None
    try:
        ref_ts = [float(t) for t in reference.get("timestamp", [])]
        ref_close = [positive(c) for c in reference.get("close", [])]
        cand = {float(t): positive(c) for t, c in zip(candidate.get("timestamp", []), candidate.get("close", []))}
    except (TypeError, ValueError):
        return None
    ratios = sorted(c / r for t, r in zip(ref_ts, ref_close)
                    if r is not None and (c := cand.get(t)) is not None)
    if not ratios:
        return None
    median = ratios[len(ratios) // 2]
    return 1 / max_ratio <= median <= max_ratio
