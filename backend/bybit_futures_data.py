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
_CONCURRENCY = 5              # Keep low to avoid rate limits

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
_symbol_map: Dict[str, str] = {}  # scanner_sym → bybit_sym


def _init_exchange():
    """Synchronous init — must be called from executor."""
    global _exchange, _symbol_map
    if _exchange is not None:
        return

    import ccxt
    _exchange = ccxt.bybit({
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
    })
    _exchange.load_markets()

    # Pre-build symbol map for all USDT perps
    for sym in _exchange.symbols:
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]

        # Strip known multiplier prefixes to get scanner base
        scanner_base = base
        for prefix in ["1000000", "10000", "1000", "100"]:
            if base.startswith(prefix) and len(base) > len(prefix):
                scanner_base = base[len(prefix):]
                break

        scanner_sym = f"{scanner_base}/USDT"
        # Only store if not already mapped (prefer non-prefixed)
        if scanner_sym not in _symbol_map or not any(
            base.startswith(p) for p in ["1000000", "10000", "1000", "100"]
        ):
            _symbol_map[scanner_sym] = sym

    logger.info("Bybit exchange loaded: %d markets, %d mapped symbols",
                len(_exchange.markets), len(_symbol_map))


def _fetch_one_sync(scanner_sym: str, bybit_sym: str) -> Optional[BybitFuturesMetrics]:
    """Synchronous fetch for one symbol — runs in executor."""
    ex = _exchange
    if ex is None:
        return None

    base = scanner_sym.split("/")[0]
    try:
        # Funding rate
        fr = ex.fetch_funding_rate(bybit_sym)
        funding_raw = float(fr.get("fundingRate", 0.0))
        funding_hourly = funding_raw / _FUNDING_PERIOD_HOURS
        mark = float(fr.get("markPrice", 0.0)) if fr.get("markPrice") else 0.0

        # Open interest
        oi_val = 0.0
        try:
            oi = ex.fetch_open_interest(bybit_sym)
            oi_amount = float(oi.get("openInterestAmount", 0.0))
            oi_val = oi_amount * mark if mark > 0 else 0.0
        except Exception:
            pass

        return BybitFuturesMetrics(
            coin=base,
            funding_rate=funding_hourly,
            funding_rate_raw=funding_raw,
            open_interest=oi_val,
            mark_price=mark,
            timestamp=time.time(),
        )
    except Exception as exc:
        logger.debug("Bybit fetch failed for %s (%s): %s", scanner_sym, bybit_sym, exc)
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

    loop = asyncio.get_running_loop()

    # Init exchange in executor (blocking load_markets)
    try:
        if _exchange is None:
            await loop.run_in_executor(None, _init_exchange)
    except Exception as exc:
        logger.error("Failed to init Bybit exchange: %s", exc)
        fallback = _cache.get_fallback()
        return fallback or {}

    # Map scanner symbols to Bybit symbols
    to_fetch = []
    for s in symbols:
        bybit_sym = _symbol_map.get(s)
        if bybit_sym:
            to_fetch.append((s, bybit_sym))

    if not to_fetch:
        logger.info("Bybit fallback: no symbols matched from %d requested", len(symbols))
        return {}

    # Fetch in bounded parallel batches via executor
    sem = asyncio.Semaphore(_CONCURRENCY)
    results: Dict[str, BybitFuturesMetrics] = {}

    async def _fetch_one(scanner_sym: str, bybit_sym: str):
        async with sem:
            m = await loop.run_in_executor(None, _fetch_one_sync, scanner_sym, bybit_sym)
            if m is not None:
                results[scanner_sym] = m

    tasks = [_fetch_one(s, b) for s, b in to_fetch]
    await asyncio.gather(*tasks, return_exceptions=True)

    if results:
        # Merge into cache
        existing = _cache.data or {}
        existing.update(results)
        _cache.put(existing)
        logger.info("Bybit positioning: fetched %d/%d symbols", len(results), len(to_fetch))

    return results
