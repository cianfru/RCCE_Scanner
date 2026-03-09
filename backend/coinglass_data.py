"""
coinglass_data.py
~~~~~~~~~~~~~~~~~
Fetches aggregated positioning data (OI, funding rates, liquidations,
long/short ratios) from the CoinGlass API v4.

Endpoint: GET https://open-api-v4.coinglass.com/api/futures/coins-markets
Auth:     Header ``CG-API-KEY``

CoinGlass aggregates data across all major exchanges (Binance, OKX, Bybit,
etc.) so we get a *single* cross-exchange view of each coin's positioning
instead of stitching together Kraken + Hyperliquid data.

Key advantage: the API returns pre-computed OI change percentages at
multiple timeframes (5m, 15m, 30m, 1h, 4h, 24h), which eliminates the
cold-start problem where ``prev_oi`` was empty on every deploy.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API config
# ---------------------------------------------------------------------------

_BASE_URL = "https://open-api-v4.coinglass.com"
_COINS_MARKETS_PATH = "/api/futures/coins-markets"

_CACHE_TTL = 5 * 60          # 5 minutes (matches scan interval)
_REQUEST_TIMEOUT_S = 20
_MAX_RETRIES = 2
_RETRY_DELAY_S = 3.0
_PER_PAGE = 100               # max results per page


def _get_api_key() -> str:
    """Read API key from environment variable."""
    key = os.environ.get("COINGLASS_API_KEY", "")
    if not key:
        logger.warning("COINGLASS_API_KEY not set -- CoinGlass data will be unavailable")
    return key


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class CoinglassMetrics:
    """Per-coin aggregated positioning data from CoinGlass."""
    coin: str = ""                          # e.g. "BTC"
    current_price: float = 0.0

    # Funding rate (OI-weighted average across exchanges)
    funding_rate: float = 0.0               # avg_funding_rate_by_oi (per-period)

    # Open interest
    open_interest_usd: float = 0.0          # aggregated across exchanges
    oi_change_pct_1h: float = 0.0
    oi_change_pct_4h: float = 0.0
    oi_change_pct_24h: float = 0.0

    # Price changes
    price_change_pct_1h: float = 0.0
    price_change_pct_4h: float = 0.0
    price_change_pct_24h: float = 0.0

    # Long/short ratios
    long_short_ratio_4h: float = 1.0
    long_short_ratio_24h: float = 1.0

    # Liquidation data
    liquidation_usd_24h: float = 0.0
    long_liquidation_usd_24h: float = 0.0
    short_liquidation_usd_24h: float = 0.0

    # Volume
    volume_24h: float = 0.0                 # 24h notional volume

    # OI/market cap ratio (leverage proxy)
    oi_market_cap_ratio: float = 0.0

    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _CGCache:
    """TTL cache for CoinGlass metrics."""
    data: Optional[Dict[str, CoinglassMetrics]] = None
    expires_at: float = 0.0

    def get(self) -> Optional[Dict[str, CoinglassMetrics]]:
        if self.data and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: Dict[str, CoinglassMetrics]) -> None:
        self.data = data
        self.expires_at = time.monotonic() + _CACHE_TTL

    def get_fallback(self) -> Optional[Dict[str, CoinglassMetrics]]:
        """Return stale data as fallback."""
        return self.data


_cache = _CGCache()


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

async def fetch_coinglass_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, CoinglassMetrics]:
    """Fetch aggregated OI, funding, and positioning from CoinGlass.

    Returns a dict keyed by scanner symbol (e.g. ``'BTC/USDT'``).

    Parameters
    ----------
    symbols : list[str] or None
        If provided, filter results to these scanner symbols.
        If None, return all available coins.
    """
    api_key = _get_api_key()
    if not api_key:
        return {}

    # Check cache
    cached = _cache.get()
    if cached is not None:
        if symbols:
            return {s: cached[s] for s in symbols if s in cached}
        return cached

    last_error: Optional[Exception] = None
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)

    for attempt in range(_MAX_RETRIES + 1):
        try:
            all_metrics: Dict[str, CoinglassMetrics] = {}

            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Paginate to get all coins
                page = 1
                while True:
                    url = f"{_BASE_URL}{_COINS_MARKETS_PATH}"
                    params = {
                        "per_page": _PER_PAGE,
                        "page": page,
                    }
                    headers = {
                        "CG-API-KEY": api_key,
                        "Accept": "application/json",
                    }

                    async with session.get(url, params=params, headers=headers) as resp:
                        resp.raise_for_status()
                        body = await resp.json()

                    if body.get("code") != "0":
                        logger.warning(
                            "CoinGlass API error: code=%s msg=%s",
                            body.get("code"), body.get("msg"),
                        )
                        break

                    items = body.get("data", [])
                    if not items:
                        break

                    for item in items:
                        m = _parse_item(item)
                        if m is not None:
                            scanner_sym = f"{m.coin}/USDT"
                            all_metrics[scanner_sym] = m

                    # If we got fewer than per_page, we've reached the end
                    if len(items) < _PER_PAGE:
                        break
                    page += 1

                    # Safety: don't paginate forever
                    if page > 10:
                        break

            # Cache
            _cache.put(all_metrics)

            # Log summary
            btc = all_metrics.get("BTC/USDT")
            logger.info(
                "Fetched CoinGlass metrics for %d coins "
                "(BTC: funding=%.4f%%, OI=$%.1fB, OI_chg_4h=%.2f%%)",
                len(all_metrics),
                (btc.funding_rate * 100) if btc else 0.0,
                (btc.open_interest_usd / 1e9) if btc else 0.0,
                btc.oi_change_pct_4h if btc else 0.0,
            )

            if symbols:
                return {s: all_metrics[s] for s in symbols if s in all_metrics}
            return all_metrics

        except aiohttp.ClientError as exc:
            last_error = exc
            logger.warning(
                "CoinGlass request failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )
        except Exception as exc:
            last_error = exc
            logger.error(
                "Unexpected error fetching CoinGlass data (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_S)

    # Fallback to stale cache
    fallback = _cache.get_fallback()
    if fallback is not None:
        logger.warning("Using stale CoinGlass data after fetch failure: %s", last_error)
        if symbols:
            return {s: fallback[s] for s in symbols if s in fallback}
        return fallback

    logger.error("CoinGlass data unavailable: %s", last_error)
    return {}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# CoinGlass uses "1000PEPE", "1000BONK" etc. for meme tokens.
# Our scanner uses plain "PEPE", "BONK" — strip the prefix.
_CG_PREFIX_MAP = {
    "1000PEPE": "PEPE",
    "1000BONK": "BONK",
    "1000FLOKI": "FLOKI",
    "1000SHIB": "SHIB",
    "1MBABYDOGE": "BABYDOGE",
}


def _parse_item(item: dict) -> Optional[CoinglassMetrics]:
    """Parse a single item from the coins-markets response."""
    try:
        raw_symbol = item.get("symbol", "")
        if not raw_symbol:
            return None

        # Map CoinGlass symbol to scanner symbol
        coin = _CG_PREFIX_MAP.get(raw_symbol, raw_symbol)

        now = time.time()
        return CoinglassMetrics(
            coin=coin,
            current_price=_f(item, "current_price"),
            # avg_funding_rate_by_oi is in decimal form per 8h period
            # (e.g. 0.00196 = 0.196%/8h).  Normalise to hourly for
            # the positioning engine thresholds.
            funding_rate=_f(item, "avg_funding_rate_by_oi") / 8.0,
            open_interest_usd=_f(item, "open_interest_usd"),
            oi_change_pct_1h=_f(item, "open_interest_change_percent_1h"),
            oi_change_pct_4h=_f(item, "open_interest_change_percent_4h"),
            oi_change_pct_24h=_f(item, "open_interest_change_percent_24h"),
            price_change_pct_1h=_f(item, "price_change_percent_1h"),
            price_change_pct_4h=_f(item, "price_change_percent_4h"),
            price_change_pct_24h=_f(item, "price_change_percent_24h"),
            long_short_ratio_4h=_f(item, "long_short_ratio_4h", 1.0),
            long_short_ratio_24h=_f(item, "long_short_ratio_24h", 1.0),
            liquidation_usd_24h=_f(item, "liquidation_usd_24h"),
            long_liquidation_usd_24h=_f(item, "long_liquidation_usd_24h"),
            short_liquidation_usd_24h=_f(item, "short_liquidation_usd_24h"),
            volume_24h=_f(item, "volume_change_usd_24h"),
            oi_market_cap_ratio=_f(item, "open_interest_market_cap_ratio"),
            timestamp=now,
        )
    except (ValueError, TypeError, KeyError) as exc:
        logger.debug("Failed to parse CoinGlass item %s: %s", item.get("symbol"), exc)
        return None


def _f(d: dict, key: str, default: float = 0.0) -> float:
    """Safely extract a float from a dict."""
    v = d.get(key)
    if v is None:
        return default
    return float(v)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_cached_metrics() -> Optional[Dict[str, CoinglassMetrics]]:
    """Return cached CoinGlass metrics (even if expired)."""
    return _cache.get_fallback()
