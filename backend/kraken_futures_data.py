"""
kraken_futures_data.py
~~~~~~~~~~~~~~~~~~~~~~
Fetches positioning data (OI, funding rates, mark prices) from
Kraken Futures' public REST API.

Endpoint: GET https://futures.kraken.com/derivatives/api/v3/tickers
No API key required — public market data.

Kraken is the primary execution venue, so OI / funding from Kraken
are preferred over Hyperliquid.  Symbols not listed on Kraken Futures
fall back to Hyperliquid in the scanner.

Funding periods: every 4 hours (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC).
Rates returned by the API are per-period (4h); we normalise to *hourly*
to stay consistent with the positioning engine's thresholds.
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

_KRAKEN_FUTURES_TICKERS_URL = (
    "https://futures.kraken.com/derivatives/api/v3/tickers"
)

_CACHE_TTL = 5 * 60          # 5 minutes (matches scan interval)
_REQUEST_TIMEOUT_S = 15
_MAX_RETRIES = 2
_RETRY_DELAY_S = 2.0
_FUNDING_PERIOD_HOURS = 4     # Kraken funds every 4 hours


# ---------------------------------------------------------------------------
# Symbol mapping (Kraken Futures → scanner format)
# ---------------------------------------------------------------------------

# Kraken uses XBT for Bitcoin; everything else matches the base coin name.
_KRAKEN_TO_SCANNER: Dict[str, str] = {
    "XBT": "BTC",
}

_SCANNER_TO_KRAKEN: Dict[str, str] = {v: k for k, v in _KRAKEN_TO_SCANNER.items()}


def _kraken_base_to_scanner(kraken_base: str) -> str:
    """Convert Kraken Futures base (e.g. 'XBT') → scanner base (e.g. 'BTC')."""
    return _KRAKEN_TO_SCANNER.get(kraken_base, kraken_base)


def _scanner_symbol(kraken_base: str) -> str:
    """Convert Kraken base → scanner symbol ('XBT' → 'BTC/USDT')."""
    base = _kraken_base_to_scanner(kraken_base)
    return f"{base}/USDT"


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class KrakenFuturesMetrics:
    """Per-asset positioning data from Kraken Futures."""
    coin: str = ""                     # Scanner base, e.g. "BTC"
    funding_rate: float = 0.0          # Hourly funding rate (normalised)
    funding_rate_raw: float = 0.0      # Raw per-period (4h) rate from Kraken
    predicted_funding: float = 0.0     # Predicted next period rate (hourly)
    open_interest: float = 0.0         # OI in USD
    open_interest_coins: float = 0.0   # OI in base currency
    mark_price: float = 0.0
    index_price: float = 0.0          # Kraken calls it indexPrice
    volume_24h: float = 0.0           # 24h volume in USD (volumeQuote)
    volume_24h_coins: float = 0.0     # 24h volume in base currency
    change_24h: float = 0.0           # 24h price change (%)
    kraken_symbol: str = ""           # e.g. "PF_XBTUSD"
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _KFCache:
    """TTL cache for Kraken Futures metrics."""
    data: Optional[Dict[str, KrakenFuturesMetrics]] = None
    expires_at: float = 0.0

    def get(self) -> Optional[Dict[str, KrakenFuturesMetrics]]:
        if self.data and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: Dict[str, KrakenFuturesMetrics]) -> None:
        self.data = data
        self.expires_at = time.monotonic() + _CACHE_TTL

    def get_fallback(self) -> Optional[Dict[str, KrakenFuturesMetrics]]:
        """Return stale data as fallback."""
        return self.data


_cache = _KFCache()


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

async def fetch_kraken_futures_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, KrakenFuturesMetrics]:
    """Fetch OI, funding, and mark prices from Kraken Futures.

    Returns a dict keyed by scanner symbol (e.g. ``'BTC/USDT'``).
    Only perpetual futures (``PF_*``) are included.

    Parameters
    ----------
    symbols : list[str] or None
        If provided, filter results to these scanner symbols.
        If None, return all available perpetuals.
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
                async with session.get(_KRAKEN_FUTURES_TICKERS_URL) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

            return _parse_tickers(data, symbols)

        except aiohttp.ClientError as exc:
            last_error = exc
            logger.warning(
                "Kraken Futures request failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )
        except Exception as exc:
            last_error = exc
            logger.error(
                "Unexpected error fetching Kraken Futures data (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_S)

    # Fallback to stale cache
    fallback = _cache.get_fallback()
    if fallback is not None:
        logger.warning("Using stale Kraken Futures data after fetch failure: %s", last_error)
        if symbols:
            return {s: fallback[s] for s in symbols if s in fallback}
        return fallback

    logger.error("Kraken Futures data unavailable: %s", last_error)
    return {}


def _parse_tickers(
    data: dict,
    symbols: Optional[List[str]],
) -> Dict[str, KrakenFuturesMetrics]:
    """Parse Kraken Futures /tickers response."""
    now = time.time()
    result: Dict[str, KrakenFuturesMetrics] = {}

    if data.get("result") != "success":
        logger.warning("Kraken Futures API returned non-success: %s", data.get("result"))
        return result

    tickers = data.get("tickers", [])

    # Build set of wanted scanner bases for filtering
    wanted_bases = None
    if symbols:
        wanted_bases = {s.split("/")[0].upper() for s in symbols}

    for t in tickers:
        symbol = t.get("symbol", "")

        # Only perpetual futures (PF_ prefix)
        if not symbol.startswith("PF_"):
            continue

        # Extract base from pair field ("XBT:USD" → "XBT")
        pair = t.get("pair", "")
        if ":" not in pair:
            continue
        kraken_base = pair.split(":")[0]
        scanner_base = _kraken_base_to_scanner(kraken_base)

        if wanted_bases and scanner_base not in wanted_bases:
            continue

        scanner_sym = f"{scanner_base}/USDT"

        try:
            funding_raw = float(t.get("fundingRate", 0.0))
            funding_pred_raw = float(t.get("fundingRatePrediction", 0.0))
            oi_coins = float(t.get("openInterest", 0.0))
            mark = float(t.get("markPrice", 0.0))
            index = float(t.get("indexPrice", 0.0))
            vol_coins = float(t.get("vol24h", 0.0))
            vol_usd = float(t.get("volumeQuote", 0.0))
            change = float(t.get("change24h", 0.0))

            # Convert OI from coins to USD
            oi_usd = oi_coins * mark if mark > 0 else 0.0

            # Normalise funding rate from per-period (4h) to hourly
            funding_hourly = funding_raw / _FUNDING_PERIOD_HOURS
            funding_pred_hourly = funding_pred_raw / _FUNDING_PERIOD_HOURS

            metrics = KrakenFuturesMetrics(
                coin=scanner_base,
                funding_rate=funding_hourly,
                funding_rate_raw=funding_raw,
                predicted_funding=funding_pred_hourly,
                open_interest=oi_usd,
                open_interest_coins=oi_coins,
                mark_price=mark,
                index_price=index,
                volume_24h=vol_usd,
                volume_24h_coins=vol_coins,
                change_24h=change,
                kraken_symbol=symbol,
                timestamp=now,
            )
            result[scanner_sym] = metrics

        except (ValueError, TypeError) as exc:
            logger.debug("Failed to parse Kraken Futures data for %s: %s", symbol, exc)
            continue

    # Cache all results
    _cache.put(result)

    # Log summary
    btc = result.get("BTC/USDT")
    logger.info(
        "Fetched Kraken Futures metrics for %d perps (BTC funding=%.4f%%/hr, OI=$%.0fM)",
        len(result),
        (btc.funding_rate * 100) if btc else 0.0,
        (btc.open_interest / 1e6) if btc else 0.0,
    )

    if symbols:
        return {s: result[s] for s in symbols if s in result}
    return result


def get_cached_metrics() -> Optional[Dict[str, KrakenFuturesMetrics]]:
    """Return cached Kraken Futures metrics (even if expired)."""
    return _cache.get_fallback()
