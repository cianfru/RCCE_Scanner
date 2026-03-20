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
import os
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


# ---------------------------------------------------------------------------
# Fear & Greed Index (CoinGlass v4)
# ---------------------------------------------------------------------------

_FNG_URL = "https://open-api-v4.coinglass.com/api/index/fear-greed-history"


def _get_cg_api_key() -> str:
    return os.environ.get("COINGLASS_API_KEY", "")


@dataclass
class SentimentData:
    """Fear & Greed Index snapshot."""
    fear_greed_value: int = 50       # 0-100
    fear_greed_label: str = "Neutral"  # Extreme Fear / Fear / Neutral / Greed / Extreme Greed
    timestamp: float = 0.0


@dataclass
class _SentimentCache:
    data: Optional[SentimentData] = None
    expires_at: float = 0.0

    def get(self) -> Optional[SentimentData]:
        if self.data and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: SentimentData) -> None:
        self.data = data
        # F&G updates once daily — cache for 4 hours to avoid hammering CoinGlass
        self.expires_at = time.monotonic() + 4 * 3600

    def get_fallback(self) -> Optional[SentimentData]:
        return self.data


_sentiment_cache = _SentimentCache()


def _fng_label(value: int) -> str:
    """Convert 0-100 F&G value to human label."""
    if value <= 20:
        return "Extreme Fear"
    elif value <= 40:
        return "Fear"
    elif value <= 60:
        return "Neutral"
    elif value <= 80:
        return "Greed"
    return "Extreme Greed"


async def fetch_fear_greed() -> Optional[SentimentData]:
    """Fetch the current Fear & Greed Index from CoinGlass v4.

    Uses /api/index/fear-greed-history — returns parallel arrays of
    data_list (values), price_list (BTC prices), time_list (timestamps).
    We take the most recent entry.
    """
    cached = _sentiment_cache.get()
    if cached is not None:
        return cached

    api_key = _get_cg_api_key()
    if not api_key:
        logger.warning("COINGLASS_API_KEY not set — F&G unavailable")
        return _sentiment_cache.get_fallback()

    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
    headers = {"CG-API-KEY": api_key}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_FNG_URL, headers=headers) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        if payload.get("code") != "0":
            logger.warning("CoinGlass F&G error: %s", payload.get("msg"))
            return _sentiment_cache.get_fallback()

        data = payload.get("data", [])
        if not data:
            return _sentiment_cache.get_fallback()

        # Response is [{data_list: [...], price_list: [...], time_list: [...]}]
        entry = data[0] if isinstance(data, list) else data
        values = entry.get("data_list") or entry.get("dataList") or []
        if not values:
            return _sentiment_cache.get_fallback()

        # Most recent value is last in the array
        fng_value = int(values[-1])
        result = SentimentData(
            fear_greed_value=fng_value,
            fear_greed_label=_fng_label(fng_value),
            timestamp=time.time(),
        )
        _sentiment_cache.put(result)
        logger.info("Fear & Greed Index (CoinGlass): %d (%s)", result.fear_greed_value, result.fear_greed_label)
        return result

    except Exception as exc:
        logger.warning("Failed to fetch Fear & Greed from CoinGlass: %s", exc)
        return _sentiment_cache.get_fallback()


# ---------------------------------------------------------------------------
# Stablecoin Supply (CoinGecko)
# ---------------------------------------------------------------------------

_STABLECOIN_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&ids=tether,usd-coin&order=market_cap_desc"
)


@dataclass
class StablecoinData:
    """Stablecoin market cap snapshot."""
    usdt_market_cap: float = 0.0
    usdc_market_cap: float = 0.0
    total_stablecoin_cap: float = 0.0
    trend: str = "STABLE"            # EXPANDING / CONTRACTING / STABLE
    change_7d_pct: float = 0.0       # 7-day change percentage
    timestamp: float = 0.0


@dataclass
class _StablecoinCache:
    data: Optional[StablecoinData] = None
    expires_at: float = 0.0
    # Track history for trend calculation (deque of (timestamp, total_cap))
    history: list = field(default_factory=list)

    def get(self) -> Optional[StablecoinData]:
        if self.data and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: StablecoinData) -> None:
        self.data = data
        self.expires_at = time.monotonic() + _CACHE_TTL
        # Add to history (keep last 7 days at 5-min intervals = ~2016 entries)
        self.history.append((data.timestamp, data.total_stablecoin_cap))
        if len(self.history) > 2100:
            self.history = self.history[-2016:]

    def get_fallback(self) -> Optional[StablecoinData]:
        return self.data

    def compute_trend(self, current_cap: float) -> tuple:
        """Compute 7-day trend from history.

        Returns (trend_label, change_pct).
        """
        if not self.history:
            return "STABLE", 0.0

        # Find entry closest to 7 days ago
        target_time = time.time() - 7 * 24 * 3600
        old_cap = None
        for ts, cap in self.history:
            if ts >= target_time:
                old_cap = cap
                break

        if old_cap is None or old_cap == 0:
            # Not enough history — use oldest available
            old_cap = self.history[0][1] if self.history else current_cap

        if old_cap == 0:
            return "STABLE", 0.0

        change_pct = ((current_cap - old_cap) / old_cap) * 100.0

        if change_pct > 1.0:
            trend = "EXPANDING"
        elif change_pct < -1.0:
            trend = "CONTRACTING"
        else:
            trend = "STABLE"

        return trend, round(change_pct, 2)


_stablecoin_cache = _StablecoinCache()


async def fetch_stablecoin_supply() -> Optional[StablecoinData]:
    """Fetch USDT and USDC market caps from CoinGecko.

    Computes 7-day trend from cached history.
    """
    cached = _stablecoin_cache.get()
    if cached is not None:
        return cached

    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_STABLECOIN_URL) as resp:
                resp.raise_for_status()
                coins = await resp.json()

        usdt_cap = 0.0
        usdc_cap = 0.0
        for coin in coins:
            cid = coin.get("id", "")
            mcap = coin.get("market_cap", 0) or 0
            if cid == "tether":
                usdt_cap = float(mcap)
            elif cid == "usd-coin":
                usdc_cap = float(mcap)

        total_cap = usdt_cap + usdc_cap
        trend, change_pct = _stablecoin_cache.compute_trend(total_cap)

        result = StablecoinData(
            usdt_market_cap=usdt_cap,
            usdc_market_cap=usdc_cap,
            total_stablecoin_cap=total_cap,
            trend=trend,
            change_7d_pct=change_pct,
            timestamp=time.time(),
        )
        _stablecoin_cache.put(result)
        logger.info(
            "Stablecoin supply: $%.1fB (USDT $%.1fB + USDC $%.1fB) trend=%s (%.1f%%)",
            total_cap / 1e9, usdt_cap / 1e9, usdc_cap / 1e9, trend, change_pct,
        )
        return result

    except Exception as exc:
        logger.warning("Failed to fetch stablecoin supply: %s", exc)
        return _stablecoin_cache.get_fallback()


def get_cached_sentiment() -> Optional[SentimentData]:
    """Return cached Fear & Greed data."""
    return _sentiment_cache.get_fallback()


def get_cached_stablecoin() -> Optional[StablecoinData]:
    """Return cached stablecoin data."""
    return _stablecoin_cache.get_fallback()
