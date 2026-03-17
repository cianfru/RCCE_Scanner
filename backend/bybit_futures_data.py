"""
bybit_futures_data.py
~~~~~~~~~~~~~~~~~~~~~
Fetches positioning data (OI, funding rates, mark prices) from
Bybit via CCXT.  Acts as fallback for symbols not on Hyperliquid
(e.g. MOG, smaller altcoins).

Bybit funds every 8 hours. ``lastFundingRate`` is per-period (8h);
we normalise to *hourly* to stay consistent with the positioning
engine thresholds.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 5 * 60          # 5 minutes
_FUNDING_PERIOD_HOURS = 8     # Bybit funds every 8h
_CONCURRENCY = 10

# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class BybitFuturesMetrics:
    """Per-asset positioning data from Bybit."""
    coin: str = ""
    funding_rate: float = 0.0          # Hourly funding rate (normalised)
    funding_rate_raw: float = 0.0      # Raw per-period (8h) rate
    open_interest: float = 0.0         # OI in USD
    mark_price: float = 0.0
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _Cache:
    data: Optional[Dict[str, BybitFuturesMetrics]] = None
    expires_at: float = 0.0

    def get(self) -> Optional[Dict[str, BybitFuturesMetrics]]:
        if self.data and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: Dict[str, BybitFuturesMetrics]) -> None:
        self.data = data
        self.expires_at = time.monotonic() + _CACHE_TTL

    def get_fallback(self) -> Optional[Dict[str, BybitFuturesMetrics]]:
        return self.data


_cache = _Cache()

# Reuse exchange instance to avoid repeated load_markets()
_exchange = None


def _get_exchange():
    global _exchange
    if _exchange is None:
        import ccxt
        _exchange = ccxt.bybit({
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
        _exchange.load_markets()
        logger.info("Bybit exchange loaded: %d markets", len(_exchange.markets))
    return _exchange


def _scanner_to_bybit(scanner_symbol: str) -> Optional[str]:
    """Convert scanner symbol to Bybit perp symbol.

    'MOG/USDT' → '1000000MOG/USDT:USDT' or 'MOG/USDT:USDT'
    """
    ex = _get_exchange()
    base = scanner_symbol.split("/")[0]

    # Try exact match first
    direct = f"{base}/USDT:USDT"
    if direct in ex.symbols:
        return direct

    # Try with multiplier prefixes (common for micro-cap coins)
    for prefix in ["1000000", "1000", "10000", "100"]:
        prefixed = f"{prefix}{base}/USDT:USDT"
        if prefixed in ex.symbols:
            return prefixed

    return None


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

async def fetch_bybit_futures_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, BybitFuturesMetrics]:
    """Fetch OI and funding from Bybit for given scanner symbols.

    Only fetches for symbols not covered by HL — call with the
    gap list, not all symbols.
    """
    cached = _cache.get()
    if cached is not None:
        if symbols:
            return {s: cached[s] for s in symbols if s in cached}
        return cached

    if not symbols:
        return {}

    try:
        ex = _get_exchange()
    except Exception as exc:
        logger.error("Failed to init Bybit exchange: %s", exc)
        fallback = _cache.get_fallback()
        return fallback or {}

    now = time.time()
    results: Dict[str, BybitFuturesMetrics] = {}
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _fetch_one(scanner_sym: str):
        async with sem:
            bybit_sym = _scanner_to_bybit(scanner_sym)
            if not bybit_sym:
                return

            base = scanner_sym.split("/")[0]
            try:
                # Funding rate
                loop = asyncio.get_event_loop()
                fr = await loop.run_in_executor(None, ex.fetch_funding_rate, bybit_sym)
                funding_raw = float(fr.get("fundingRate", 0.0))
                funding_hourly = funding_raw / _FUNDING_PERIOD_HOURS
                mark = float(fr.get("markPrice", 0.0)) if fr.get("markPrice") else 0.0

                # Open interest
                # Mark price is already per-contract (e.g. 1000000MOG mark = price per 1M MOG)
                # So OI_amount × mark = correct USD value, no multiplier adjustment needed
                oi_val = 0.0
                try:
                    oi = await loop.run_in_executor(None, ex.fetch_open_interest, bybit_sym)
                    oi_amount = float(oi.get("openInterestAmount", 0.0))
                    oi_val = oi_amount * mark if mark > 0 else 0.0
                except Exception:
                    pass

                results[scanner_sym] = BybitFuturesMetrics(
                    coin=base,
                    funding_rate=funding_hourly,
                    funding_rate_raw=funding_raw,
                    open_interest=oi_val,
                    mark_price=mark,
                    timestamp=now,
                )
            except Exception as exc:
                logger.debug("Bybit fetch failed for %s: %s", scanner_sym, exc)

    tasks = [_fetch_one(s) for s in symbols]
    await asyncio.gather(*tasks, return_exceptions=True)

    if results:
        # Merge into cache
        existing = _cache.data or {}
        existing.update(results)
        _cache.put(existing)
        logger.info("Bybit positioning: fetched %d symbols", len(results))

    return results
