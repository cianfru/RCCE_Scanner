"""
binance_futures_data.py
~~~~~~~~~~~~~~~~~~~~~~~
Fetches positioning data (OI, funding rates, mark prices) from
Binance USDS-M Futures public REST API.

Two endpoints:
  1. GET /fapi/v1/premiumIndex  (no symbol → returns ALL symbols)
       → funding rates, mark prices, index prices
       Weight: 10 (all symbols)

  2. GET /fapi/v1/openInterest?symbol=BTCUSDT  (per-symbol)
       → current open interest in base currency
       Weight: 1 each

No API key required — public market data.
Binance has the largest futures OI/volume of any exchange.

Funding periods: every 8 hours (00:00, 08:00, 16:00 UTC).
``lastFundingRate`` is per-period (8h); we normalise to *hourly*
to stay consistent with the positioning engine thresholds.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API config
# ---------------------------------------------------------------------------

_BINANCE_FAPI_BASE = "https://fapi.binance.com"
_PREMIUM_INDEX_URL = f"{_BINANCE_FAPI_BASE}/fapi/v1/premiumIndex"
_OPEN_INTEREST_URL = f"{_BINANCE_FAPI_BASE}/fapi/v1/openInterest"

_CACHE_TTL = 5 * 60          # 5 minutes (matches scan interval)
_REQUEST_TIMEOUT_S = 15
_MAX_RETRIES = 2
_RETRY_DELAY_S = 2.0
_FUNDING_PERIOD_HOURS = 8     # Binance funds every 8 hours

# Max concurrent OI requests to avoid hammering the API
_OI_CONCURRENCY = 10


# ---------------------------------------------------------------------------
# Symbol mapping
# ---------------------------------------------------------------------------

def _scanner_symbol(binance_symbol: str) -> Optional[str]:
    """Convert Binance USDT perp symbol → scanner symbol.

    'BTCUSDT' → 'BTC/USDT', 'ETHUSDT' → 'ETH/USDT'.
    Returns None for non-USDT pairs (e.g. BTCBUSD).
    """
    if not binance_symbol.endswith("USDT"):
        return None
    base = binance_symbol[:-4]  # strip 'USDT'
    if not base:
        return None
    return f"{base}/USDT"


def _binance_symbol(scanner_symbol: str) -> str:
    """Convert scanner symbol → Binance perp symbol.

    'BTC/USDT' → 'BTCUSDT'.
    """
    return scanner_symbol.replace("/", "")


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class BinanceFuturesMetrics:
    """Per-asset positioning data from Binance Futures."""
    coin: str = ""                     # Scanner base, e.g. "BTC"
    funding_rate: float = 0.0          # Hourly funding rate (normalised)
    funding_rate_raw: float = 0.0      # Raw per-period (8h) rate from Binance
    open_interest: float = 0.0         # OI in USD
    open_interest_coins: float = 0.0   # OI in base currency
    mark_price: float = 0.0
    index_price: float = 0.0
    next_funding_time: int = 0         # timestamp ms
    binance_symbol: str = ""           # e.g. "BTCUSDT"
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _BFCache:
    """TTL cache for Binance Futures metrics."""
    data: Optional[Dict[str, BinanceFuturesMetrics]] = None
    expires_at: float = 0.0

    def get(self) -> Optional[Dict[str, BinanceFuturesMetrics]]:
        if self.data and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: Dict[str, BinanceFuturesMetrics]) -> None:
        self.data = data
        self.expires_at = time.monotonic() + _CACHE_TTL

    def get_fallback(self) -> Optional[Dict[str, BinanceFuturesMetrics]]:
        """Return stale data as fallback."""
        return self.data


_cache = _BFCache()


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

async def fetch_binance_futures_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, BinanceFuturesMetrics]:
    """Fetch OI, funding, and mark prices from Binance Futures.

    Returns a dict keyed by scanner symbol (e.g. ``'BTC/USDT'``).

    Parameters
    ----------
    symbols : list[str] or None
        If provided, only fetch OI for these scanner symbols.
        Funding data is always fetched for all symbols (one API call).
    """
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
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Step 1: Fetch premiumIndex for ALL symbols (1 API call)
                async with session.get(_PREMIUM_INDEX_URL) as resp:
                    resp.raise_for_status()
                    premium_data = await resp.json()

                # Step 2: Parse funding data into metrics dict
                metrics = _parse_premium_index(premium_data, symbols)

                # Step 3: Fetch OI for each symbol (parallel, bounded)
                await _fetch_open_interest_batch(session, metrics)

            # Cache all results
            _cache.put(metrics)

            # Log summary
            btc = metrics.get("BTC/USDT")
            logger.info(
                "Fetched Binance Futures metrics for %d perps "
                "(BTC funding=%.4f%%/hr, OI=$%.0fM)",
                len(metrics),
                (btc.funding_rate * 100) if btc else 0.0,
                (btc.open_interest / 1e6) if btc else 0.0,
            )

            if symbols:
                return {s: metrics[s] for s in symbols if s in metrics}
            return metrics

        except aiohttp.ClientError as exc:
            last_error = exc
            logger.warning(
                "Binance Futures request failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )
        except Exception as exc:
            last_error = exc
            logger.error(
                "Unexpected error fetching Binance Futures data (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_S)

    # Fallback to stale cache
    fallback = _cache.get_fallback()
    if fallback is not None:
        logger.warning("Using stale Binance Futures data after fetch failure: %s", last_error)
        if symbols:
            return {s: fallback[s] for s in symbols if s in fallback}
        return fallback

    logger.error("Binance Futures data unavailable: %s", last_error)
    return {}


# ---------------------------------------------------------------------------
# Premium Index parser
# ---------------------------------------------------------------------------

def _parse_premium_index(
    data: list,
    symbols: Optional[List[str]],
) -> Dict[str, BinanceFuturesMetrics]:
    """Parse premiumIndex response (all symbols)."""
    now = time.time()
    result: Dict[str, BinanceFuturesMetrics] = {}

    # Build set of wanted bases for filtering
    wanted_syms = None
    if symbols:
        wanted_syms = {_binance_symbol(s) for s in symbols}

    for item in data:
        binance_sym = item.get("symbol", "")
        if not binance_sym.endswith("USDT"):
            continue

        if wanted_syms and binance_sym not in wanted_syms:
            continue

        scanner_sym = _scanner_symbol(binance_sym)
        if scanner_sym is None:
            continue

        try:
            funding_raw = float(item.get("lastFundingRate", 0.0))
            mark = float(item.get("markPrice", 0.0))
            index = float(item.get("indexPrice", 0.0))
            next_funding = int(item.get("nextFundingTime", 0))

            # Normalise funding rate from per-period (8h) to hourly
            funding_hourly = funding_raw / _FUNDING_PERIOD_HOURS

            base = binance_sym[:-4]  # strip USDT

            result[scanner_sym] = BinanceFuturesMetrics(
                coin=base,
                funding_rate=funding_hourly,
                funding_rate_raw=funding_raw,
                mark_price=mark,
                index_price=index,
                next_funding_time=next_funding,
                binance_symbol=binance_sym,
                timestamp=now,
            )
        except (ValueError, TypeError) as exc:
            logger.debug("Failed to parse Binance premium data for %s: %s", binance_sym, exc)

    return result


# ---------------------------------------------------------------------------
# Open Interest batch fetch
# ---------------------------------------------------------------------------

async def _fetch_open_interest_batch(
    session: aiohttp.ClientSession,
    metrics: Dict[str, BinanceFuturesMetrics],
) -> None:
    """Fetch open interest for all symbols in ``metrics`` (bounded concurrency).

    Modifies each ``BinanceFuturesMetrics`` in-place to add OI values.
    """
    sem = asyncio.Semaphore(_OI_CONCURRENCY)

    async def _fetch_one(scanner_sym: str, m: BinanceFuturesMetrics) -> None:
        async with sem:
            try:
                params = {"symbol": m.binance_symbol}
                async with session.get(_OPEN_INTEREST_URL, params=params) as resp:
                    if resp.status != 200:
                        return
                    body = await resp.json()

                oi_coins = float(body.get("openInterest", 0.0))
                m.open_interest_coins = oi_coins
                m.open_interest = oi_coins * m.mark_price if m.mark_price > 0 else 0.0

            except Exception as exc:
                logger.debug("Failed to fetch OI for %s: %s", m.binance_symbol, exc)

    tasks = [
        _fetch_one(sym, m)
        for sym, m in metrics.items()
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_cached_metrics() -> Optional[Dict[str, BinanceFuturesMetrics]]:
    """Return cached Binance Futures metrics (even if expired)."""
    return _cache.get_fallback()
