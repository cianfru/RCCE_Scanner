"""
data_fetcher.py
~~~~~~~~~~~~~~~
Fetches OHLCV data from Hyperliquid (primary) with CCXT exchange fallback.

Primary source  : Hyperliquid candleSnapshot API (all crypto + HIP-3)
Fallback (CCXT) : Kraken → KuCoin → Binance → Bybit (only for HL failures)

Concurrency is throttled with an asyncio.Semaphore.  Results are cached
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

# Minimum candle counts per timeframe for full z-score warm-up.
# Z-score needs 2 × LEN_LONG (400) bars; we add margin for the
# inner SMA/stdev to normalise over a representative window.
_DEFAULT_LIMIT: Dict[str, int] = {
    "4h": 500,     # ~83 days — plenty for 4h
    "1d": 600,     # ~1.6 years — full warmup + margin
    "1w": 500,     # ~9.6 years — covers most crypto history
}

# Concurrency knobs — tuned for Hyperliquid rate limits.
# HL returns 429 when hit too hard; 10 concurrent + 50ms stagger
# keeps us under the limit even at 200+ symbols × 2 timeframes.
_MAX_CONCURRENT_FETCHES = 10
_INTER_REQUEST_DELAY_S = 0.05  # 50 ms stagger

# Symbols known to need CCXT (HL candleSnapshot fails).
# Populated at runtime; most symbols work fine on HL.
_ccxt_only: set = set()

# Symbols known to exist on Binance.  Populated once on first batch fetch
# via load_markets(), then reused.  Symbols on this set are fetched from
# Binance (fast, generous rate limits); the rest go to HL.
_binance_symbols: Optional[set] = None
_binance_symbols_lock = asyncio.Lock()


async def _ensure_binance_symbols() -> set:
    """Lazy-load the set of Binance-listed symbols (cached for process life)."""
    global _binance_symbols
    if _binance_symbols is not None:
        return _binance_symbols

    async with _binance_symbols_lock:
        if _binance_symbols is not None:
            return _binance_symbols

        try:
            exchange = await _create_exchange("binance")
            try:
                await exchange.load_markets()
                _binance_symbols = set(exchange.markets.keys())
                logger.info("Binance market list loaded: %d symbols", len(_binance_symbols))
            finally:
                await exchange.close()
        except Exception as exc:
            logger.warning("Failed to load Binance markets: %s — will use HL only", exc)
            _binance_symbols = set()

        return _binance_symbols

# Hyperliquid coin name mapping — handles rebrands and HL-specific names.
# Key: CCXT base (from "BASE/USDT"), Value: HL coin name.
_HL_COIN_MAP: Dict[str, str] = {
    "MATIC": "POL",       # Polygon rebrand
    "SHIB":  "kSHIB",     # HL uses kSHIB
    "PEPE":  "kPEPE",     # HL uses kPEPE
    "BONK":  "kBONK",     # HL uses kBONK
    "FLOKI": "kFLOKI",    # HL uses kFLOKI
    "RNDR":  "RENDER",    # Render rebrand
    "FTM":   "S",         # Sonic rebrand
}


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


def _parse_hl_candles(candles: list) -> Optional[dict]:
    """Parse Hyperliquid candle JSON into numpy arrays."""
    if not candles or not isinstance(candles, list):
        return None
    rows = []
    for c in candles:
        try:
            rows.append([
                float(c["t"]),
                float(c["o"]),
                float(c["h"]),
                float(c["l"]),
                float(c["c"]),
                float(c["v"]),
            ])
        except (KeyError, ValueError, TypeError):
            continue
    if not rows:
        return None
    arr = np.array(rows, dtype=np.float64)
    return {
        "timestamp": arr[:, 0],
        "open":      arr[:, 1],
        "high":      arr[:, 2],
        "low":       arr[:, 3],
        "close":     arr[:, 4],
        "volume":    arr[:, 5],
    }


async def _fetch_hl_candles(
    session: aiohttp.ClientSession,
    coin: str,
    timeframe: str,
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch candles from Hyperliquid using a shared session.

    Parameters
    ----------
    session : shared aiohttp session (avoids per-call overhead)
    coin : HL coin name (e.g. "BTC", "xyz:GOLD")
    timeframe : "4h", "1d", or "1w"
    limit : number of candles
    """
    tf_ms = _TF_MS.get(timeframe)
    if tf_ms is None:
        return None

    if limit is None:
        limit = _DEFAULT_LIMIT.get(timeframe, 500)

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

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session.post(
                _HL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status == 429:
                    # Rate limited — back off and retry
                    wait = 1.0 * (attempt + 1)
                    logger.debug("HL 429 for %s/%s, retry %d in %.1fs", coin, timeframe, attempt + 1, wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    return None
                candles = await resp.json()
            return _parse_hl_candles(candles)
        except Exception as exc:
            logger.debug("HL candle fetch failed for %s/%s: %s", coin, timeframe, exc)
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
                continue
            return None
    return None


def _hl_coin_name(symbol: str) -> str:
    """Convert scanner symbol 'BASE/USDT' → HL coin name, applying renames."""
    base = symbol.split("/")[0]
    return _HL_COIN_MAP.get(base, base)


async def _fetch_ohlcv_hyperliquid(
    symbol: str,
    timeframe: str,
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch OHLCV from Hyperliquid (creates its own session — for single calls)."""
    coin = _hl_coin_name(symbol)
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            return await _fetch_hl_candles(session, coin, timeframe, limit)
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
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch OHLCV data for a single *symbol*.

    Tries Hyperliquid first (primary), then CCXT exchanges as fallback.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        logger.error("Unsupported timeframe '%s'. Use one of %s", timeframe, SUPPORTED_TIMEFRAMES)
        return None

    if limit is None:
        limit = _DEFAULT_LIMIT.get(timeframe, 500)

    # Check cache first
    cached = _cache.get(symbol, timeframe)
    if cached is not None:
        return cached

    # Known CCXT-only symbol → skip HL
    if symbol in _ccxt_only:
        return await _fetch_ohlcv_ccxt(symbol, timeframe, exchange_id, limit)

    # Primary: Hyperliquid
    hl_data = await _fetch_ohlcv_hyperliquid(symbol, timeframe, limit)
    if hl_data is not None:
        _cache.put(symbol, timeframe, hl_data)
        return hl_data

    # Fallback: CCXT exchanges
    data = await _fetch_ohlcv_ccxt(symbol, timeframe, exchange_id, limit)
    if data is not None:
        _ccxt_only.add(symbol)  # Remember for next time
        logger.info("Learned CCXT-only: %s (total %d)", symbol, len(_ccxt_only))
    return data


async def _fetch_ohlcv_ccxt(
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch OHLCV via CCXT exchange fallback chain."""
    if limit is None:
        limit = _DEFAULT_LIMIT.get(timeframe, 500)

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
                continue
            raw = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not raw:
                continue
            data = _parse_ohlcv(raw)
            _cache.put(symbol, timeframe, data)
            logger.debug("Fetched %d bars for %s (%s) from %s", len(raw), symbol, timeframe, exch_id)
            return data
        except (ccxt.BadSymbol, ccxt.NetworkError, ccxt.ExchangeError) as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            logger.error("Unexpected error fetching %s from %s: %s", symbol, exch_id, exc)
            continue
        finally:
            await exchange.close()

    if last_error:
        logger.warning("All CCXT exchanges failed for %s: %s", symbol, last_error)
    return None


async def fetch_batch(
    symbols: Optional[List[str]] = None,
    timeframe: str = "4h",
    skip_ccxt_fallback: bool = True,
) -> Dict[str, Optional[dict]]:
    """Fetch OHLCV data for many symbols concurrently.

    Dual-source strategy:
      - **Binance** for symbols listed there (~180 of 229 HL perps).
        Fast, generous rate limits (1200 req/min), deep history.
      - **Hyperliquid** for HL-exclusive symbols (~50).
        Small enough batch to avoid 429 rate limits.

    Both pools are fetched in parallel for speed.
    """
    if symbols is None:
        symbols = DEFAULT_SYMBOLS

    results: Dict[str, Optional[dict]] = {}

    # ── Phase 1: Check cache, split uncached into Binance vs HL pools ──
    binance_symbols = await _ensure_binance_symbols()

    binance_queue: List[str] = []
    hl_queue: List[str] = []

    for sym in symbols:
        cached = _cache.get(sym, timeframe)
        if cached is not None:
            results[sym] = cached
        elif sym in binance_symbols:
            binance_queue.append(sym)
        else:
            hl_queue.append(sym)

    logger.info(
        "Batch fetch %s: %d cached, %d→Binance, %d→HL",
        timeframe, len(results), len(binance_queue), len(hl_queue),
    )

    # ── Phase 2a: Binance pool (CCXT, high concurrency) ──
    async def _fetch_binance_pool() -> None:
        if not binance_queue:
            return
        exchange = await _create_exchange("binance")
        try:
            await exchange.load_markets()
            semaphore = asyncio.Semaphore(20)  # Binance handles this easily

            async def _bn_fetch(sym: str) -> None:
                async with semaphore:
                    try:
                        limit = _DEFAULT_LIMIT.get(timeframe, 500)
                        raw = await exchange.fetch_ohlcv(sym, timeframe, limit=limit)
                        if raw:
                            data = _parse_ohlcv(raw)
                            _cache.put(sym, timeframe, data)
                            results[sym] = data
                    except (ccxt.BadSymbol, ccxt.NetworkError, ccxt.ExchangeError) as exc:
                        logger.debug("Binance failed for %s: %s", sym, exc)
                    except Exception as exc:
                        logger.debug("Binance error for %s: %s", sym, exc)

            tasks = [asyncio.create_task(_bn_fetch(s)) for s in binance_queue]
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await exchange.close()

    # ── Phase 2b: Hyperliquid pool (chunked waves, avoids 429) ──
    hl_failures: List[str] = []

    async def _fetch_hl_pool() -> None:
        if not hl_queue:
            return
        _WAVE_SIZE = 15
        _WAVE_PAUSE_S = 0.3
        timeout = aiohttp.ClientTimeout(total=60)
        connector = aiohttp.TCPConnector(limit=_MAX_CONCURRENT_FETCHES, keepalive_timeout=30)

        async def _hl_fetch(session: aiohttp.ClientSession, sym: str) -> None:
            coin = _hl_coin_name(sym)
            data = await _fetch_hl_candles(session, coin, timeframe)
            if data is not None:
                _cache.put(sym, timeframe, data)
                results[sym] = data
            else:
                hl_failures.append(sym)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            for i in range(0, len(hl_queue), _WAVE_SIZE):
                wave = hl_queue[i : i + _WAVE_SIZE]
                tasks = [asyncio.create_task(_hl_fetch(session, s)) for s in wave]
                await asyncio.gather(*tasks, return_exceptions=True)
                if i + _WAVE_SIZE < len(hl_queue):
                    await asyncio.sleep(_WAVE_PAUSE_S)

    # ── Run both pools in parallel ──
    await asyncio.gather(
        _fetch_binance_pool(),
        _fetch_hl_pool(),
        return_exceptions=True,
    )

    # ── Phase 3: Binance symbols that failed → try HL as fallback ──
    binance_misses = [s for s in binance_queue if s not in results]
    if binance_misses:
        logger.info("Binance misses → HL fallback for %d: %s", len(binance_misses), binance_misses[:5])
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for sym in binance_misses:
                coin = _hl_coin_name(sym)
                data = await _fetch_hl_candles(session, coin, timeframe)
                if data is not None:
                    _cache.put(sym, timeframe, data)
                    results[sym] = data

    if hl_failures:
        logger.debug("HL-only failures (%d): %s", len(hl_failures), hl_failures[:10])

    # Fill None for any remaining
    for sym in symbols:
        if sym not in results:
            results[sym] = None

    return results


def get_cache() -> DataCache:
    """Return the module-level cache (useful for inspection / testing)."""
    return _cache


# ---------------------------------------------------------------------------
# TradFi / HIP-3 symbols (trade.xyz on Hyperliquid)
# ---------------------------------------------------------------------------

TRADFI_SYMBOLS: List[dict] = [
    # Commodities — Precious Metals
    {"coin": "GOLD",      "symbol": "GOLD/USD",      "name": "Gold",              "category": "Commodities"},
    {"coin": "SILVER",    "symbol": "SILVER/USD",     "name": "Silver",            "category": "Commodities"},
    {"coin": "PLATINUM",  "symbol": "PLATINUM/USD",   "name": "Platinum",          "category": "Commodities"},
    {"coin": "PALLADIUM", "symbol": "PALLADIUM/USD",  "name": "Palladium",         "category": "Commodities"},
    # Commodities — Energy
    {"coin": "CL",        "symbol": "CL/USD",         "name": "WTI Crude Oil",     "category": "Commodities"},
    {"coin": "BRENTOIL",  "symbol": "BRENTOIL/USD",   "name": "Brent Crude Oil",   "category": "Commodities"},
    {"coin": "NATGAS",    "symbol": "NATGAS/USD",     "name": "Natural Gas",       "category": "Commodities"},
    # Commodities — Industrial
    {"coin": "COPPER",    "symbol": "COPPER/USD",     "name": "Copper",            "category": "Commodities"},
    # Indices
    {"coin": "XYZ100",    "symbol": "XYZ100/USD",     "name": "US 100 Index",      "category": "Indices"},
    # Equities — US
    {"coin": "TSLA",      "symbol": "TSLA/USD",       "name": "Tesla",             "category": "Equities"},
    {"coin": "NVDA",      "symbol": "NVDA/USD",       "name": "NVIDIA",            "category": "Equities"},
    {"coin": "GOOGL",     "symbol": "GOOGL/USD",      "name": "Alphabet",          "category": "Equities"},
    {"coin": "AMZN",      "symbol": "AMZN/USD",       "name": "Amazon",            "category": "Equities"},
    {"coin": "AMD",       "symbol": "AMD/USD",        "name": "AMD",               "category": "Equities"},
    {"coin": "AAPL",      "symbol": "AAPL/USD",       "name": "Apple",             "category": "Equities"},
    {"coin": "BABA",      "symbol": "BABA/USD",       "name": "Alibaba",           "category": "Equities"},
    {"coin": "CRWV",      "symbol": "CRWV/USD",       "name": "CoreWeave",         "category": "Equities"},
    # Korea / International
    {"coin": "SMSN",      "symbol": "SMSN/USD",       "name": "Samsung",           "category": "Equities"},
    {"coin": "SKHX",      "symbol": "SKHX/USD",       "name": "SK Hynix",          "category": "Equities"},
    {"coin": "HYUNDAI",   "symbol": "HYUNDAI/USD",    "name": "Hyundai Motor",     "category": "Equities"},
    # ETFs
    {"coin": "EWY",       "symbol": "EWY/USD",        "name": "iShares Korea ETF", "category": "ETFs"},
    {"coin": "EWJ",       "symbol": "EWJ/USD",        "name": "iShares Japan ETF", "category": "ETFs"},
]

# Quick lookups
TRADFI_COIN_MAP: Dict[str, dict] = {s["coin"]: s for s in TRADFI_SYMBOLS}
TRADFI_SYMBOL_LIST: List[str] = [s["symbol"] for s in TRADFI_SYMBOLS]
TRADFI_COIN_TO_SYMBOL: Dict[str, str] = {s["coin"]: s["symbol"] for s in TRADFI_SYMBOLS}
TRADFI_SYMBOL_TO_COIN: Dict[str, str] = {s["symbol"]: s["coin"] for s in TRADFI_SYMBOLS}


async def fetch_ohlcv_hip3(
    symbol: str,
    timeframe: str,
    limit: Optional[int] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[dict]:
    """Fetch OHLCV from Hyperliquid for a HIP-3 (trade.xyz) asset.

    Accepts an optional shared session for batch operations.
    """
    cached = _cache.get(symbol, timeframe)
    if cached is not None:
        return cached

    if limit is None:
        limit = _DEFAULT_LIMIT.get(timeframe, 500)

    coin = TRADFI_SYMBOL_TO_COIN.get(symbol)
    if coin is None:
        coin = symbol.split("/")[0]

    # HIP-3 spot tokens require "xyz:" prefix for candleSnapshot API
    hl_coin = f"xyz:{coin}"

    if session is not None:
        data = await _fetch_hl_candles(session, hl_coin, timeframe, limit)
    else:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            data = await _fetch_hl_candles(s, hl_coin, timeframe, limit)

    if data is not None:
        _cache.put(symbol, timeframe, data)
    return data


async def fetch_batch_hip3(
    timeframe: str = "4h",
) -> Dict[str, Optional[dict]]:
    """Fetch OHLCV data for all TradFi HIP-3 symbols concurrently.

    Uses a single shared aiohttp session for all requests.
    """
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)
    results: Dict[str, Optional[dict]] = {}
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=_MAX_CONCURRENT_FETCHES, keepalive_timeout=30)

    async def _guarded_fetch(session: aiohttp.ClientSession, sym: str) -> None:
        async with semaphore:
            results[sym] = await fetch_ohlcv_hip3(sym, timeframe, session=session)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [
            asyncio.create_task(_guarded_fetch(session, sym))
            for sym in TRADFI_SYMBOL_LIST
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results
