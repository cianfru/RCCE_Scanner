"""
coinglass_data.py
~~~~~~~~~~~~~~~~~
Fetches aggregated positioning data (OI, funding rates) from the CoinGlass
API v3 (Hobbyist plan).

Endpoints used:
  GET https://open-api.coinglass.com/public/v2/funding
      → Bulk fetch: all 1000+ coins' funding rates in one call.
  GET https://open-api.coinglass.com/public/v2/open_interest?symbol=XXX
      → Per-coin: OI, OI change %, volume (limited to top N coins).

Auth:  Header ``coinglassSecret``

CoinGlass aggregates data across all major exchanges (Binance, OKX, Bybit,
etc.) so we get a *single* cross-exchange view of each coin's positioning
instead of stitching together Kraken + Hyperliquid data.

Note: CVD (taker buy/sell volume), long/short ratios, liquidations, and spot
market data require a higher CoinGlass plan and are not fetched here.  All
public helpers for those features return empty results gracefully so the rest
of the pipeline is unaffected.
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
# API config  (CoinGlass v3 — Hobbyist plan)
# ---------------------------------------------------------------------------

_BASE_URL_V3   = "https://open-api.coinglass.com"
_FUNDING_PATH  = "/public/v2/funding"          # bulk: all coins, 1 request
_OI_PATH       = "/public/v2/open_interest"    # per-coin: OI + OI change %
_AUTH_HEADER   = "coinglassSecret"

_CACHE_TTL         = 5 * 60          # 5 minutes (matches scan interval)
_REQUEST_TIMEOUT_S = 20
_MAX_RETRIES       = 2
_RETRY_DELAY_S     = 3.0

# Max concurrent per-coin OI requests (avoid rate limiting)
_OI_SEMAPHORE      = 5
# Max number of coins for which we fetch detailed OI (per scan)
_OI_FETCH_LIMIT    = 30


def _get_api_key() -> str:
    """Read API key from environment variable."""
    key = os.environ.get("COINGLASS_API_KEY", "")
    if not key:
        logger.warning("COINGLASS_API_KEY not set — CoinGlass data will be unavailable")
    return key


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class CoinglassMetrics:
    """Per-coin aggregated positioning data from CoinGlass."""
    coin: str = ""                          # e.g. "BTC"
    current_price: float = 0.0

    # Funding rate (aggregated across exchanges, normalised to per-hour)
    # Underlying CoinGlass value is per 8h period → divided by interval hrs
    funding_rate: float = 0.0

    # Open interest (aggregated across exchanges)
    open_interest_usd: float = 0.0
    oi_change_pct_1h: float = 0.0
    oi_change_pct_4h: float = 0.0
    oi_change_pct_24h: float = 0.0

    # Price changes (not available from v3 bulk endpoint — kept for compat)
    price_change_pct_1h: float = 0.0
    price_change_pct_4h: float = 0.0
    price_change_pct_24h: float = 0.0

    # Long/short ratios (not available on Hobbyist plan — defaults to 1.0)
    long_short_ratio_4h: float = 1.0
    long_short_ratio_24h: float = 1.0

    # Liquidation data (not available on Hobbyist plan — defaults to 0)
    liquidation_usd_24h: float = 0.0
    long_liquidation_usd_24h: float = 0.0
    short_liquidation_usd_24h: float = 0.0

    # 24h notional volume (from OI endpoint when fetched)
    volume_24h: float = 0.0

    # OI/market-cap ratio — not available on Hobbyist plan
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
# Symbol normalisation
# ---------------------------------------------------------------------------

# CoinGlass uses "1000PEPE", "1000BONK" etc. for meme tokens.
# Our scanner uses plain "PEPE", "BONK" — strip the prefix.
_CG_PREFIX_MAP = {
    "1000PEPE":    "PEPE",
    "1000BONK":    "BONK",
    "1000FLOKI":   "FLOKI",
    "1000SHIB":    "SHIB",
    "1MBABYDOGE":  "BABYDOGE",
}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_funding_item(item: dict) -> Optional[CoinglassMetrics]:
    """Parse a single entry from the /funding bulk response.

    Each item has ``symbol``, ``uPrice`` and ``uMarginList`` (USDT-margined
    exchange funding rates).  We compute a simple average of active funding
    rates, normalised to hourly.
    """
    try:
        raw_symbol = item.get("symbol", "")
        if not raw_symbol:
            return None
        coin = _CG_PREFIX_MAP.get(raw_symbol, raw_symbol)

        price = float(item.get("uPrice") or item.get("uIndexPrice") or 0.0)

        # --- Compute hourly funding rate from uMarginList ---
        u_list: list = item.get("uMarginList") or []

        rates_hourly: list[float] = []
        binance_rate_hourly: Optional[float] = None

        for ex in u_list:
            raw_rate = ex.get("rate")
            if raw_rate is None:
                continue
            interval_hrs = float(ex.get("fundingIntervalHours") or 8)
            hourly = float(raw_rate) / interval_hrs
            rates_hourly.append(hourly)
            if ex.get("exchangeName", "").lower() == "binance":
                binance_rate_hourly = hourly

        # Prefer Binance rate; fall back to mean across exchanges
        if binance_rate_hourly is not None:
            funding_rate = binance_rate_hourly
        elif rates_hourly:
            funding_rate = sum(rates_hourly) / len(rates_hourly)
        else:
            funding_rate = 0.0

        return CoinglassMetrics(
            coin=coin,
            current_price=price,
            funding_rate=funding_rate,
            timestamp=time.time(),
        )
    except (ValueError, TypeError, KeyError) as exc:
        logger.debug("Failed to parse CoinGlass funding item %s: %s", item.get("symbol"), exc)
        return None


def _parse_oi_item(item: dict, coin: str) -> Optional[CoinglassMetrics]:
    """Parse the first (aggregate) row from a per-coin /open_interest response.

    The v3 endpoint returns an array — first element contains the aggregated
    cross-exchange totals.
    """
    try:
        # avgFundingRateBySymbol is an 8h-period rate → hourly
        raw_funding = float(item.get("avgFundingRateBySymbol") or 0.0)
        funding_rate = raw_funding / 8.0

        oi_usd      = float(item.get("openInterest") or 0.0)
        oi_chg_1h   = float(item.get("h1OIChangePercent") or 0.0)
        oi_chg_4h   = float(item.get("h4OIChangePercent") or 0.0)
        oi_chg_24h  = float(item.get("oichangePercent") or 0.0)
        vol_usd     = float(item.get("volUsd") or 0.0)

        return CoinglassMetrics(
            coin=coin,
            funding_rate=funding_rate,
            open_interest_usd=oi_usd,
            oi_change_pct_1h=round(oi_chg_1h, 2),
            oi_change_pct_4h=round(oi_chg_4h, 2),
            oi_change_pct_24h=round(oi_chg_24h, 2),
            volume_24h=vol_usd,
            timestamp=time.time(),
        )
    except (ValueError, TypeError, KeyError) as exc:
        logger.debug("Failed to parse CoinGlass OI item for %s: %s", coin, exc)
        return None


def _f(d: dict, key: str, default: float = 0.0) -> float:
    """Safely extract a float from a dict."""
    v = d.get(key)
    if v is None:
        return default
    return float(v)


# ---------------------------------------------------------------------------
# Bulk funding fetch  (1 call → all coins)
# ---------------------------------------------------------------------------

async def _fetch_all_funding(
    session: aiohttp.ClientSession,
    api_key: str,
) -> Dict[str, CoinglassMetrics]:
    """Fetch funding rates for all coins in a single request."""
    url = f"{_BASE_URL_V3}{_FUNDING_PATH}"
    headers = {_AUTH_HEADER: api_key, "Accept": "application/json"}

    async with session.get(url, headers=headers) as resp:
        resp.raise_for_status()
        body = await resp.json()

    if str(body.get("code", "")) not in ("0", 0):
        logger.warning(
            "CoinGlass funding API error: code=%s msg=%s",
            body.get("code"), body.get("msg"),
        )
        return {}

    result: Dict[str, CoinglassMetrics] = {}
    for item in body.get("data") or []:
        m = _parse_funding_item(item)
        if m is not None:
            scanner_sym = f"{m.coin}/USDT"
            result[scanner_sym] = m

    return result


# ---------------------------------------------------------------------------
# Per-coin OI fetch  (limited set — up to _OI_FETCH_LIMIT coins)
# ---------------------------------------------------------------------------

async def _fetch_single_oi(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    api_key: str,
    scanner_sym: str,
) -> Tuple[str, Optional[CoinglassMetrics]]:
    """Fetch OI data for a single coin (returns scanner symbol + metrics)."""
    coin = scanner_sym.split("/")[0]
    async with sem:
        try:
            url = f"{_BASE_URL_V3}{_OI_PATH}"
            params = {"symbol": coin}
            headers = {_AUTH_HEADER: api_key, "Accept": "application/json"}

            async with session.get(url, params=params, headers=headers) as resp:
                resp.raise_for_status()
                body = await resp.json()

            if str(body.get("code", "")) not in ("0", 0):
                return scanner_sym, None

            rows = body.get("data") or []
            if not rows:
                return scanner_sym, None

            # First row is the aggregate
            m = _parse_oi_item(rows[0], coin)
            return scanner_sym, m

        except Exception as exc:
            logger.debug("OI fetch error for %s: %s", scanner_sym, exc)
            return scanner_sym, None


async def _fetch_oi_batch(
    session: aiohttp.ClientSession,
    api_key: str,
    symbols: List[str],
) -> Dict[str, CoinglassMetrics]:
    """Fetch OI for up to _OI_FETCH_LIMIT symbols concurrently."""
    target = symbols[:_OI_FETCH_LIMIT]
    sem = asyncio.Semaphore(_OI_SEMAPHORE)

    tasks = [
        _fetch_single_oi(session, sem, api_key, sym)
        for sym in target
    ]
    fetched = await asyncio.gather(*tasks, return_exceptions=True)

    result: Dict[str, CoinglassMetrics] = {}
    for outcome in fetched:
        if isinstance(outcome, Exception):
            logger.debug("OI batch task raised: %s", outcome)
            continue
        sym, m = outcome
        if m is not None:
            result[sym] = m

    return result


# ---------------------------------------------------------------------------
# Main public fetch function
# ---------------------------------------------------------------------------

async def fetch_coinglass_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, CoinglassMetrics]:
    """Fetch aggregated OI and funding data from CoinGlass.

    Phase 1: bulk ``/funding`` call → funding rates + prices for all ~1000 coins.
    Phase 2: per-coin ``/open_interest`` for up to ``_OI_FETCH_LIMIT`` symbols
             → OI USD, OI change %, volume (merged back into Phase 1 results).

    Returns a dict keyed by scanner symbol (e.g. ``'BTC/USDT'``).
    """
    api_key = _get_api_key()
    if not api_key:
        return {}

    # --- Cache check ---
    cached = _cache.get()
    if cached is not None:
        if symbols:
            return {s: cached[s] for s in symbols if s in cached}
        return cached

    last_error: Optional[Exception] = None
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)

    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:

                # --- Phase 1: bulk funding ---
                all_metrics = await _fetch_all_funding(session, api_key)

                # --- Phase 2: per-coin OI (top coins only) ---
                oi_targets = symbols if symbols else list(all_metrics.keys())
                oi_data = await _fetch_oi_batch(session, api_key, oi_targets)

                # Merge OI into funding results
                for sym, oi_m in oi_data.items():
                    if sym in all_metrics:
                        base = all_metrics[sym]
                        # OI endpoint has more accurate funding rate — prefer it
                        base.funding_rate   = oi_m.funding_rate if oi_m.funding_rate != 0.0 else base.funding_rate
                        base.open_interest_usd  = oi_m.open_interest_usd
                        base.oi_change_pct_1h   = oi_m.oi_change_pct_1h
                        base.oi_change_pct_4h   = oi_m.oi_change_pct_4h
                        base.oi_change_pct_24h  = oi_m.oi_change_pct_24h
                        base.volume_24h         = oi_m.volume_24h
                    else:
                        # OI-fetched coin wasn't in the funding list
                        oi_m.current_price = all_metrics.get(sym, CoinglassMetrics()).current_price
                        all_metrics[sym] = oi_m

            # Cache full result set
            _cache.put(all_metrics)

            btc = all_metrics.get("BTC/USDT")
            logger.info(
                "CoinGlass v3: %d coins "
                "(BTC: funding=%.4f%%/hr, OI=$%.1fB, OI_chg_4h=%.2f%%)",
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
# Public helpers
# ---------------------------------------------------------------------------

def get_cached_metrics() -> Optional[Dict[str, CoinglassMetrics]]:
    """Return cached CoinGlass metrics (even if expired)."""
    return _cache.get_fallback()


# ---------------------------------------------------------------------------
# CVD (Cumulative Volume Delta)
# NOTE: Taker buy/sell volume history requires a higher CoinGlass plan.
#       All CVD helpers return empty results gracefully.
# ---------------------------------------------------------------------------

@dataclass
class CoinglassCVD:
    """Per-coin CVD data (stub — not available on Hobbyist plan)."""
    coin: str = ""
    cvd_trend: str = "NEUTRAL"
    cvd_value: float = 0.0
    cvd_divergence: bool = False
    buy_volume_usd: float = 0.0
    sell_volume_usd: float = 0.0
    buy_sell_ratio: float = 1.0
    timestamp: float = 0.0


@dataclass
class _CVDCacheEntry:
    data: CoinglassCVD = field(default_factory=CoinglassCVD)
    expires_at: float = 0.0


_cvd_cache: Dict[str, _CVDCacheEntry] = {}


async def fetch_cvd_batch(
    coins: List[str],
    time_type: str = "4h",
    limit: int = 6,
    price_changes: Optional[Dict[str, float]] = None,
) -> Dict[str, CoinglassCVD]:
    """CVD fetch stub — not available on CoinGlass Hobbyist plan.

    Returns an empty dict so callers work without modification.
    """
    logger.debug("CVD not available on current CoinGlass plan — skipping")
    return {}


def get_cached_cvd(coin: str) -> Optional[CoinglassCVD]:
    """Return cached CVD for a coin (always None on Hobbyist plan)."""
    entry = _cvd_cache.get(coin)
    return entry.data if entry else None


# ---------------------------------------------------------------------------
# Spot Market Data
# NOTE: Spot market data endpoint requires a higher CoinGlass plan.
#       All spot helpers return empty results gracefully.
# ---------------------------------------------------------------------------

@dataclass
class CoinglassSpot:
    """Per-coin spot market data (stub — not available on Hobbyist plan)."""
    coin: str = ""
    spot_volume_usd: float = 0.0
    spot_price_change_24h: float = 0.0
    futures_volume_usd: float = 0.0
    spot_futures_ratio: float = 0.0
    spot_dominance: str = "NEUTRAL"
    timestamp: float = 0.0


@dataclass
class _SpotCache:
    data: Optional[Dict[str, CoinglassSpot]] = None
    expires_at: float = 0.0

    def get_fallback(self) -> Optional[Dict[str, CoinglassSpot]]:
        return self.data


_spot_cache = _SpotCache()


async def fetch_spot_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, CoinglassSpot]:
    """Spot metrics fetch stub — not available on CoinGlass Hobbyist plan.

    Returns an empty dict so callers work without modification.
    """
    logger.debug("Spot metrics not available on current CoinGlass plan — skipping")
    return {}


def get_cached_spot(sym: str) -> Optional[CoinglassSpot]:
    """Return cached spot data for a scanner symbol (always None on Hobbyist plan)."""
    data = _spot_cache.get_fallback()
    if data is None:
        return None
    return data.get(sym)
