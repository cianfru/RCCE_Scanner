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
from typing import Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------------------
# CVD (Cumulative Volume Delta)
# ---------------------------------------------------------------------------

@dataclass
class CoinglassCVD:
    """Per-coin CVD data from CoinGlass taker buy/sell volume history."""
    coin: str = ""
    cvd_trend: str = "NEUTRAL"       # "BULLISH" | "BEARISH" | "NEUTRAL"
    cvd_value: float = 0.0           # net (buy - sell) USD over lookback bars
    cvd_divergence: bool = False     # price dir != CVD dir
    buy_volume_usd: float = 0.0     # total buy vol (last N bars)
    sell_volume_usd: float = 0.0    # total sell vol (last N bars)
    buy_sell_ratio: float = 1.0     # buy / sell
    timestamp: float = 0.0


@dataclass
class _CVDCacheEntry:
    """TTL cache entry for a single coin's CVD data."""
    data: CoinglassCVD = field(default_factory=CoinglassCVD)
    expires_at: float = 0.0


_CVD_CACHE_TTL = 4 * 60 * 60   # 4-hour TTL (CVD is slow-moving)
_cvd_cache: Dict[str, _CVDCacheEntry] = {}
_CVD_SEMAPHORE_LIMIT = 8
_CVD_PATH = "/api/futures/taker-buy-sell-volume/history"


def _get_cached_cvd_entry(coin: str) -> Optional[_CVDCacheEntry]:
    entry = _cvd_cache.get(coin)
    if entry and time.monotonic() < entry.expires_at:
        return entry
    return None


async def _fetch_single_cvd(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    api_key: str,
    coin: str,
    time_type: str,
    limit: int,
    price_change_pct: Optional[float],
) -> Tuple[str, CoinglassCVD]:
    """Fetch CVD for a single coin, returning (coin, CoinglassCVD)."""
    async with sem:
        url = f"{_BASE_URL}{_CVD_PATH}"
        params = {"symbol": coin, "time_type": time_type, "limit": limit}
        headers = {"CG-API-KEY": api_key, "Accept": "application/json"}
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                resp.raise_for_status()
                body = await resp.json()

            if body.get("code") != "0":
                logger.debug("CVD fetch for %s returned code %s", coin, body.get("code"))
                return coin, CoinglassCVD(coin=coin, timestamp=time.time())

            bars = body.get("data", [])
            if not bars:
                return coin, CoinglassCVD(coin=coin, timestamp=time.time())

            total_buy = sum(float(b.get("buy", 0) or 0) for b in bars)
            total_sell = sum(float(b.get("sell", 0) or 0) for b in bars)
            cvd_value = total_buy - total_sell
            buy_sell_ratio = total_buy / total_sell if total_sell > 0 else 1.0

            if cvd_value > 0 and buy_sell_ratio > 1.05:
                cvd_trend = "BULLISH"
            elif cvd_value < 0 and buy_sell_ratio < 0.95:
                cvd_trend = "BEARISH"
            else:
                cvd_trend = "NEUTRAL"

            # Divergence: price and CVD moving in opposite directions
            cvd_divergence = False
            if price_change_pct is not None:
                price_up = price_change_pct > 0
                price_down = price_change_pct < 0
                if (price_up and cvd_trend == "BEARISH") or (price_down and cvd_trend == "BULLISH"):
                    cvd_divergence = True

            return coin, CoinglassCVD(
                coin=coin,
                cvd_trend=cvd_trend,
                cvd_value=cvd_value,
                cvd_divergence=cvd_divergence,
                buy_volume_usd=total_buy,
                sell_volume_usd=total_sell,
                buy_sell_ratio=buy_sell_ratio,
                timestamp=time.time(),
            )

        except Exception as exc:
            logger.debug("CVD fetch error for %s: %s", coin, exc)
            return coin, CoinglassCVD(coin=coin, timestamp=time.time())


async def fetch_cvd_batch(
    coins: List[str],
    time_type: str = "4h",
    limit: int = 6,
    price_changes: Optional[Dict[str, float]] = None,
) -> Dict[str, CoinglassCVD]:
    """Fetch CVD for a batch of coins concurrently (max 8 concurrent).

    Parameters
    ----------
    coins : list[str]
        Base coin names, e.g. ["BTC", "ETH"].
    time_type : str
        Bar timeframe to request from CoinGlass (e.g. "4h").
    limit : int
        Number of bars to sum over (default 6).
    price_changes : dict[str, float] or None
        Coin -> recent price change pct for divergence detection.

    Returns
    -------
    dict[str, CoinglassCVD]
        Keyed by base coin name (e.g. "BTC").
    """
    api_key = _get_api_key()
    if not api_key:
        return {}

    results: Dict[str, CoinglassCVD] = {}
    coins_to_fetch: List[str] = []

    # Check cache first
    for coin in coins:
        entry = _get_cached_cvd_entry(coin)
        if entry is not None:
            results[coin] = entry.data
        else:
            coins_to_fetch.append(coin)

    if not coins_to_fetch:
        return results

    sem = asyncio.Semaphore(_CVD_SEMAPHORE_LIMIT)
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            _fetch_single_cvd(
                session, sem, api_key, coin, time_type, limit,
                price_changes.get(coin) if price_changes else None,
            )
            for coin in coins_to_fetch
        ]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)

    for outcome in fetched:
        if isinstance(outcome, Exception):
            logger.debug("CVD batch task raised: %s", outcome)
            continue
        coin, cvd = outcome
        results[coin] = cvd
        # Cache the result
        _cvd_cache[coin] = _CVDCacheEntry(
            data=cvd,
            expires_at=time.monotonic() + _CVD_CACHE_TTL,
        )

    bullish_count = sum(1 for v in results.values() if v.cvd_trend == "BULLISH")
    bearish_count = sum(1 for v in results.values() if v.cvd_trend == "BEARISH")
    logger.info(
        "CVD batch: %d coins — %d BULLISH, %d BEARISH, %d NEUTRAL",
        len(results), bullish_count, bearish_count,
        len(results) - bullish_count - bearish_count,
    )
    return results


def get_cached_cvd(coin: str) -> Optional[CoinglassCVD]:
    """Return cached CVD for a coin (even if expired)."""
    entry = _cvd_cache.get(coin)
    return entry.data if entry else None


# ---------------------------------------------------------------------------
# Spot Market Data
# ---------------------------------------------------------------------------

@dataclass
class CoinglassSpot:
    """Per-coin spot market data from CoinGlass."""
    coin: str = ""
    spot_volume_usd: float = 0.0         # 24h spot volume in USD
    spot_price_change_24h: float = 0.0
    futures_volume_usd: float = 0.0      # from coins-markets for comparison
    spot_futures_ratio: float = 0.0      # spot_vol / (spot_vol + futures_vol)
    spot_dominance: str = "NEUTRAL"      # "SPOT_LED" | "FUTURES_LED" | "NEUTRAL"
    timestamp: float = 0.0


_SPOT_CACHE_TTL = 5 * 60              # 5 minutes (matches scan interval)
_SPOT_PATH = "/api/spot/coins-markets"
_spot_cache = _CGCache()              # reuse same cache class, typed loosely


async def fetch_spot_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, CoinglassSpot]:
    """Fetch spot market data from CoinGlass.

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
    cached_raw = _spot_cache.get()
    if cached_raw is not None:
        # _spot_cache stores Dict[str, CoinglassSpot] in .data
        cached: Dict[str, CoinglassSpot] = cached_raw  # type: ignore[assignment]
        if symbols:
            return {s: cached[s] for s in symbols if s in cached}
        return cached

    last_error: Optional[Exception] = None
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)

    for attempt in range(_MAX_RETRIES + 1):
        try:
            all_spot: Dict[str, CoinglassSpot] = {}

            async with aiohttp.ClientSession(timeout=timeout) as session:
                page = 1
                while True:
                    url = f"{_BASE_URL}{_SPOT_PATH}"
                    params = {"per_page": _PER_PAGE, "page": page}
                    headers = {"CG-API-KEY": api_key, "Accept": "application/json"}

                    async with session.get(url, params=params, headers=headers) as resp:
                        resp.raise_for_status()
                        body = await resp.json()

                    if body.get("code") != "0":
                        logger.warning(
                            "CoinGlass spot API error: code=%s msg=%s",
                            body.get("code"), body.get("msg"),
                        )
                        break

                    items = body.get("data", [])
                    if not items:
                        break

                    # Retrieve futures volume from coins-markets cache for cross-ref
                    futures_cache = _cache.get_fallback() or {}

                    for item in items:
                        try:
                            raw_symbol = item.get("symbol", "")
                            if not raw_symbol:
                                continue
                            coin = _CG_PREFIX_MAP.get(raw_symbol, raw_symbol)
                            scanner_sym = f"{coin}/USDT"

                            spot_vol = _f(item, "volume_usd_24h")
                            price_chg = _f(item, "price_change_percent_24h")

                            # Cross-reference with futures cache
                            futures_vol = 0.0
                            cg_m = futures_cache.get(scanner_sym)
                            if cg_m is not None:
                                futures_vol = cg_m.volume_24h

                            total_vol = spot_vol + futures_vol
                            ratio = spot_vol / total_vol if total_vol > 0 else 0.0
                            if ratio > 0.6:
                                dominance = "SPOT_LED"
                            elif ratio < 0.3 and futures_vol > 0:
                                dominance = "FUTURES_LED"
                            else:
                                dominance = "NEUTRAL"

                            all_spot[scanner_sym] = CoinglassSpot(
                                coin=coin,
                                spot_volume_usd=spot_vol,
                                spot_price_change_24h=price_chg,
                                futures_volume_usd=futures_vol,
                                spot_futures_ratio=round(ratio, 4),
                                spot_dominance=dominance,
                                timestamp=time.time(),
                            )
                        except (ValueError, TypeError, KeyError) as exc:
                            logger.debug(
                                "Failed to parse spot item %s: %s",
                                item.get("symbol"), exc,
                            )
                            continue

                    if len(items) < _PER_PAGE:
                        break
                    page += 1
                    if page > 10:
                        break

            # Cache using the same _CGCache (data field is generic)
            _spot_cache.data = all_spot  # type: ignore[assignment]
            _spot_cache.expires_at = time.monotonic() + _SPOT_CACHE_TTL

            btc_sp = all_spot.get("BTC/USDT")
            logger.info(
                "Fetched CoinGlass spot metrics for %d coins "
                "(BTC: spot_vol=$%.1fB, dominance=%s)",
                len(all_spot),
                (btc_sp.spot_volume_usd / 1e9) if btc_sp else 0.0,
                btc_sp.spot_dominance if btc_sp else "N/A",
            )

            if symbols:
                return {s: all_spot[s] for s in symbols if s in all_spot}
            return all_spot

        except aiohttp.ClientError as exc:
            last_error = exc
            logger.warning(
                "CoinGlass spot request failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )
        except Exception as exc:
            last_error = exc
            logger.error(
                "Unexpected error fetching CoinGlass spot data (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_S)

    # Fallback to stale data
    fallback_raw = _spot_cache.get_fallback()
    if fallback_raw is not None:
        fallback: Dict[str, CoinglassSpot] = fallback_raw  # type: ignore[assignment]
        logger.warning("Using stale CoinGlass spot data after fetch failure: %s", last_error)
        if symbols:
            return {s: fallback[s] for s in symbols if s in fallback}
        return fallback

    logger.error("CoinGlass spot data unavailable: %s", last_error)
    return {}


def get_cached_spot(sym: str) -> Optional[CoinglassSpot]:
    """Return cached spot data for a scanner symbol (e.g. 'BTC/USDT'), even if expired."""
    data = _spot_cache.get_fallback()
    if data is None:
        return None
    return data.get(sym)  # type: ignore[return-value]
