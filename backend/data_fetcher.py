"""
data_fetcher.py
~~~~~~~~~~~~~~~
Fetches OHLCV data from crypto exchanges via CCXT (async).

Primary exchange : Kraken  (matches execution venue)
Fallback exchanges: KuCoin → Binance → Bybit → Hyperliquid

Hyperliquid is the final fallback via its candleSnapshot REST API,
covering HL-only pairs that aren't listed on CEXes.

Concurrency is throttled with an asyncio.Semaphore (max 5 parallel
requests) and an inter-request delay of 100 ms.  Results are cached
in memory with a configurable TTL (5 min for 4h candles, 30 min for
daily candles).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp
import ccxt.async_support as ccxt
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default watchlist (25 high-priority symbols, CCXT pair format)
# ---------------------------------------------------------------------------

DEFAULT_SYMBOLS: List[str] = [
    # Large caps
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "NEAR/USDT",
    # L2 / New L1
    "ARB/USDT", "OP/USDT", "SUI/USDT", "INJ/USDT", "TIA/USDT",
    # Meme
    "DOGE/USDT", "PEPE/USDT", "WIF/USDT",
    # AI / Compute
    "FET/USDT", "RNDR/USDT", "TAO/USDT",
    # DeFi
    "AAVE/USDT", "RUNE/USDT",
    # Infra
    "TON/USDT", "HBAR/USDT",
]

# ---------------------------------------------------------------------------
# Full list (65 symbols, available as preset)
# ---------------------------------------------------------------------------

FULL_SYMBOLS: List[str] = [
    # Large caps
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "MATIC/USDT",
    "NEAR/USDT", "UNI/USDT", "ATOM/USDT", "FIL/USDT", "APT/USDT",
    # L2 / New L1
    "ARB/USDT", "OP/USDT", "SUI/USDT", "SEI/USDT", "INJ/USDT",
    "TIA/USDT",
    # Meme
    "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "WIF/USDT", "BONK/USDT",
    "FLOKI/USDT", "MEME/USDT",
    # AI / Compute
    "FET/USDT", "RNDR/USDT", "TAO/USDT",
    # DeFi
    "AAVE/USDT", "MKR/USDT", "LDO/USDT", "CRV/USDT", "SNX/USDT",
    "COMP/USDT", "RUNE/USDT",
    # Infrastructure / Misc
    "STX/USDT", "ICP/USDT", "HBAR/USDT", "VET/USDT", "ALGO/USDT",
    "FTM/USDT", "SAND/USDT", "MANA/USDT", "AXS/USDT", "GMT/USDT",
    "IMX/USDT", "GALA/USDT",
    # Newer listings
    "BLUR/USDT", "JTO/USDT", "JUP/USDT", "PYTH/USDT", "W/USDT",
    "WLD/USDT", "STRK/USDT", "ORDI/USDT",
    # Additional
    "TRX/USDT", "TON/USDT", "CAKE/USDT", "DYDX/USDT", "ENS/USDT",
    "GRT/USDT", "OCEAN/USDT",
]

# ---------------------------------------------------------------------------
# Supported timeframes and their cache TTLs (seconds)
# ---------------------------------------------------------------------------

_CACHE_TTL: Dict[str, int] = {
    "4h": 5 * 60,      # 5 minutes
    "1d": 30 * 60,     # 30 minutes
    "1w": 60 * 60,     # 1 hour
}

SUPPORTED_TIMEFRAMES = list(_CACHE_TTL.keys())

# Concurrency knobs
_MAX_CONCURRENT_FETCHES = 15
_INTER_REQUEST_DELAY_S = 0.05  # 50 ms

# Self-learning exchange hint: symbols that only resolve via Hyperliquid.
# Populated at runtime when all CCXT exchanges fail and HL succeeds.
_hl_only: set = set()


# ---------------------------------------------------------------------------
# DataCache -- simple in-memory TTL cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    data: dict
    expires_at: float


class DataCache:
    """Thread-unsafe, in-memory TTL cache keyed by (symbol, timeframe)."""

    def __init__(self) -> None:
        self._store: Dict[str, _CacheEntry] = {}

    @staticmethod
    def _key(symbol: str, timeframe: str) -> str:
        return f"{symbol}|{timeframe}"

    def get(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Return cached OHLCV dict or *None* if missing / expired."""
        key = self._key(symbol, timeframe)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.data

    def put(self, symbol: str, timeframe: str, data: dict, ttl: Optional[int] = None) -> None:
        """Store *data* with a TTL derived from the timeframe (or explicit)."""
        if ttl is None:
            ttl = _CACHE_TTL.get(timeframe, 300)
        key = self._key(symbol, timeframe)
        self._store[key] = _CacheEntry(data=data, expires_at=time.monotonic() + ttl)

    def invalidate(self, symbol: str, timeframe: str) -> None:
        """Remove a single entry."""
        self._store.pop(self._key(symbol, timeframe), None)

    def clear(self) -> None:
        """Drop every cached entry."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# Module-level cache instance shared across calls
_cache = DataCache()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_ohlcv(raw: list) -> dict:
    """Convert the list-of-lists returned by CCXT into a dict of numpy arrays.

    Each sub-list is ``[timestamp, open, high, low, close, volume]``.
    """
    arr = np.array(raw, dtype=np.float64)
    return {
        "timestamp": arr[:, 0],
        "open":      arr[:, 1],
        "high":      arr[:, 2],
        "low":       arr[:, 3],
        "close":     arr[:, 4],
        "volume":    arr[:, 5],
    }


# ---------------------------------------------------------------------------
# Hyperliquid candle fallback (direct REST, no CCXT)
# ---------------------------------------------------------------------------

_HL_API_URL = "https://api.hyperliquid.xyz/info"

# Timeframe → milliseconds per candle (for calculating startTime)
_TF_MS: Dict[str, int] = {
    "4h": 4 * 3600 * 1000,
    "1d": 86400 * 1000,
    "1w": 7 * 86400 * 1000,
}


async def _fetch_ohlcv_hyperliquid(
    symbol: str,
    timeframe: str,
    limit: int = 250,
) -> Optional[dict]:
    """Fetch OHLCV candles from Hyperliquid's candleSnapshot API.

    Falls back to this when all CCXT exchanges fail. Returns the same
    dict-of-numpy-arrays format as _parse_ohlcv(), or None on failure.
    """
    coin = symbol.split("/")[0]  # Preserve case (HL has kPEPE, kSHIB, etc.)
    tf_ms = _TF_MS.get(timeframe)
    if tf_ms is None:
        return None

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (limit * tf_ms)

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": timeframe,
            "startTime": start_ms,
            "endTime": now_ms,
        },
    }

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                _HL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status != 200:
                    return None
                candles = await resp.json()

        if not candles or not isinstance(candles, list):
            return None

        # Parse HL candle format: {t, T, s, i, o, c, h, l, v, n}
        # Values are strings except t, T, n
        rows = []
        for c in candles:
            try:
                rows.append([
                    float(c["t"]),        # timestamp (ms)
                    float(c["o"]),        # open
                    float(c["h"]),        # high
                    float(c["l"]),        # low
                    float(c["c"]),        # close
                    float(c["v"]),        # volume
                ])
            except (KeyError, ValueError, TypeError):
                continue

        if not rows:
            return None

        arr = np.array(rows, dtype=np.float64)
        data = {
            "timestamp": arr[:, 0],
            "open":      arr[:, 1],
            "high":      arr[:, 2],
            "low":       arr[:, 3],
            "close":     arr[:, 4],
            "volume":    arr[:, 5],
        }

        logger.info(
            "Fetched %d bars for %s (%s) from hyperliquid",
            len(rows), symbol, timeframe,
        )
        return data

    except Exception as exc:
        logger.debug("Hyperliquid candle fetch failed for %s: %s", symbol, exc)
        return None


async def _create_exchange(exchange_id: str) -> ccxt.Exchange:
    """Instantiate a CCXT async exchange with rate-limiting enabled."""
    exchange_class = getattr(ccxt, exchange_id, None)
    if exchange_class is None:
        raise ValueError(f"Unknown exchange: {exchange_id}")
    exchange = exchange_class({
        "enableRateLimit": True,
    })
    return exchange


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    limit: int = 250,
) -> Optional[dict]:
    """Fetch OHLCV data for a single *symbol*.

    Returns a dict of numpy arrays (keys: open, high, low, close, volume,
    timestamp) or ``None`` when the symbol cannot be fetched from any
    supported exchange.

    Parameters
    ----------
    symbol:
        Trading pair in CCXT format, e.g. ``"BTC/USDT"``.
    timeframe:
        Candle interval -- ``"4h"`` or ``"1d"``.
    exchange_id:
        Primary exchange to try (default ``"kraken"``).
    limit:
        Number of candles to retrieve (default 250).
    """

    if timeframe not in SUPPORTED_TIMEFRAMES:
        logger.error("Unsupported timeframe '%s'. Use one of %s", timeframe, SUPPORTED_TIMEFRAMES)
        return None

    # Check cache first
    cached = _cache.get(symbol, timeframe)
    if cached is not None:
        logger.debug("Cache hit for %s %s", symbol, timeframe)
        return cached

    # Fast path: known HL-only symbol → skip CCXT entirely
    if symbol in _hl_only:
        hl_data = await _fetch_ohlcv_hyperliquid(symbol, timeframe, limit)
        if hl_data is not None:
            _cache.put(symbol, timeframe, hl_data)
            logger.debug("HL-only fast path for %s %s", symbol, timeframe)
            return hl_data
        # HL failed — maybe delisted? Clear hint, fall through to CCXT
        _hl_only.discard(symbol)

    # Try primary exchange, then fallbacks
    # Kraken is default (execution venue); kucoin/binance as fallbacks
    exchanges_to_try = [exchange_id]
    if exchange_id == "kraken":
        exchanges_to_try.extend(["kucoin", "binance", "bybit"])
    elif exchange_id == "binance":
        exchanges_to_try.extend(["kraken", "bybit", "kucoin"])

    last_error: Optional[Exception] = None

    for exch_id in exchanges_to_try:
        exchange = await _create_exchange(exch_id)
        try:
            await exchange.load_markets()

            if symbol not in exchange.markets:
                logger.debug(
                    "%s not found on %s, trying next exchange",
                    symbol, exch_id,
                )
                continue

            raw = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            if not raw:
                logger.warning("Empty OHLCV response for %s on %s", symbol, exch_id)
                continue

            data = _parse_ohlcv(raw)
            _cache.put(symbol, timeframe, data)
            logger.debug(
                "Fetched %d bars for %s (%s) from %s",
                len(raw), symbol, timeframe, exch_id,
            )
            return data

        except ccxt.BadSymbol:
            logger.debug("%s not listed on %s", symbol, exch_id)
            continue
        except ccxt.NetworkError as exc:
            last_error = exc
            logger.warning("Network error fetching %s from %s: %s", symbol, exch_id, exc)
            continue
        except ccxt.ExchangeError as exc:
            last_error = exc
            logger.warning("Exchange error fetching %s from %s: %s", symbol, exch_id, exc)
            continue
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.error("Unexpected error fetching %s from %s: %s", symbol, exch_id, exc)
            continue
        finally:
            await exchange.close()

    # Final fallback: Hyperliquid candleSnapshot (covers HL-only pairs)
    hl_data = await _fetch_ohlcv_hyperliquid(symbol, timeframe, limit)
    if hl_data is not None:
        _hl_only.add(symbol)  # Remember: skip CCXT next time
        _cache.put(symbol, timeframe, hl_data)
        logger.info("Learned HL-only: %s (total %d)", symbol, len(_hl_only))
        return hl_data

    if last_error:
        logger.error("All exchanges + Hyperliquid failed for %s: %s", symbol, last_error)
    else:
        logger.debug("Symbol %s not available on any exchange or Hyperliquid", symbol)

    return None


async def fetch_batch(
    symbols: Optional[List[str]] = None,
    timeframe: str = "4h",
) -> Dict[str, Optional[dict]]:
    """Fetch OHLCV data for many symbols concurrently.

    Concurrency is capped at ``_MAX_CONCURRENT_FETCHES`` simultaneous
    requests with a 100 ms delay injected between each launch to avoid
    hammering the exchange API.

    Parameters
    ----------
    symbols:
        List of trading pairs.  Defaults to :data:`DEFAULT_SYMBOLS`.
    timeframe:
        Candle interval (``"4h"`` or ``"1d"``).

    Returns
    -------
    dict
        Mapping of symbol -> OHLCV dict (or ``None`` for failures).
    """

    if symbols is None:
        symbols = DEFAULT_SYMBOLS

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)
    results: Dict[str, Optional[dict]] = {}

    async def _guarded_fetch(sym: str) -> None:
        async with semaphore:
            results[sym] = await fetch_ohlcv(sym, timeframe)
            await asyncio.sleep(_INTER_REQUEST_DELAY_S)

    tasks = []
    for sym in symbols:
        tasks.append(asyncio.create_task(_guarded_fetch(sym)))
        # Small stagger so the first N tasks don't all fire at t=0
        await asyncio.sleep(_INTER_REQUEST_DELAY_S)

    await asyncio.gather(*tasks, return_exceptions=False)
    return results


def get_cache() -> DataCache:
    """Return the module-level cache (useful for inspection / testing)."""
    return _cache
