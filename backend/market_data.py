"""
market_data.py
~~~~~~~~~~~~~~
Fetches global crypto market metrics from CoinGecko (free API, no key required).

Provides BTC dominance, ETH dominance, total market cap, and alt market cap
with a 5-minute TTL cache and automatic fallback to last-known values.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CoinGecko endpoint
# ---------------------------------------------------------------------------

_COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"

# Cache TTL in seconds — 5 min is safe within CoinGecko's ~30 req/min limit
_CACHE_TTL = 5 * 60

# Retry configuration
_MAX_RETRIES = 2
_RETRY_DELAY_S = 2.0
_REQUEST_TIMEOUT_S = 15


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class GlobalMetrics:
    """Snapshot of global crypto market data."""
    btc_dominance: float = 0.0       # BTC market share (0-100)
    eth_dominance: float = 0.0       # ETH market share (0-100)
    total_market_cap: float = 0.0    # Total crypto market cap in USD
    alt_market_cap: float = 0.0      # Total - BTC market cap
    btc_market_cap: float = 0.0      # BTC market cap in USD
    timestamp: float = 0.0           # When this data was fetched


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

@dataclass
class _MetricsCache:
    """Simple TTL cache for global metrics."""
    data: Optional[GlobalMetrics] = None
    expires_at: float = 0.0

    def get(self) -> Optional[GlobalMetrics]:
        """Return cached metrics if still valid, else None."""
        if self.data is None:
            return None
        if time.monotonic() > self.expires_at:
            return None
        return self.data

    def put(self, metrics: GlobalMetrics) -> None:
        """Store metrics with TTL."""
        self.data = metrics
        self.expires_at = time.monotonic() + _CACHE_TTL

    def get_fallback(self) -> Optional[GlobalMetrics]:
        """Return last known data even if expired (for resilience)."""
        return self.data


_cache = _MetricsCache()


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

async def fetch_global_metrics() -> Optional[GlobalMetrics]:
    """Fetch global crypto market metrics from CoinGecko.

    Returns cached data if still fresh.  On fetch failure, returns
    the last known data (even if expired) for resilience.

    Returns
    -------
    GlobalMetrics or None
        None only if CoinGecko has never been reachable.
    """
    # Check cache first
    cached = _cache.get()
    if cached is not None:
        logger.debug("Global metrics cache hit (BTC.D=%.1f%%)", cached.btc_dominance)
        return cached

    # Fetch from CoinGecko with retries
    last_error: Optional[Exception] = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            metrics = await _fetch_from_coingecko()
            _cache.put(metrics)
            logger.info(
                "Fetched global metrics: BTC.D=%.1f%% ETH.D=%.1f%% MCap=$%.0fB",
                metrics.btc_dominance,
                metrics.eth_dominance,
                metrics.total_market_cap / 1e9,
            )
            return metrics

        except aiohttp.ClientError as exc:
            last_error = exc
            logger.warning(
                "CoinGecko request failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.error(
                "Unexpected error fetching global metrics (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_S)

    # All retries exhausted — fall back to last known data
    fallback = _cache.get_fallback()
    if fallback is not None:
        logger.warning(
            "Using stale global metrics (BTC.D=%.1f%%) after fetch failure: %s",
            fallback.btc_dominance, last_error,
        )
        return fallback

    logger.error("Global metrics unavailable — no cached data and fetch failed: %s", last_error)
    return None


async def _fetch_from_coingecko() -> GlobalMetrics:
    """Make the actual HTTP request to CoinGecko."""
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(_COINGECKO_GLOBAL_URL) as resp:
            resp.raise_for_status()
            payload = await resp.json()

    data = payload.get("data", {})
    market_cap_pct = data.get("market_cap_percentage", {})
    total_mcap_usd = data.get("total_market_cap", {}).get("usd", 0.0)

    btc_dom = market_cap_pct.get("btc", 0.0)
    eth_dom = market_cap_pct.get("eth", 0.0)

    # BTC market cap = total * btc_dominance / 100
    btc_mcap = total_mcap_usd * btc_dom / 100.0
    alt_mcap = total_mcap_usd - btc_mcap

    return GlobalMetrics(
        btc_dominance=round(btc_dom, 2),
        eth_dominance=round(eth_dom, 2),
        total_market_cap=total_mcap_usd,
        alt_market_cap=alt_mcap,
        btc_market_cap=btc_mcap,
        timestamp=time.time(),
    )


def get_cached_metrics() -> Optional[GlobalMetrics]:
    """Return the current cached metrics (even if expired). Useful for sync callers."""
    return _cache.get_fallback()
