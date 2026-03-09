"""
data_loader.py
~~~~~~~~~~~~~~
Fetches historical OHLCV data from CCXT with pagination support,
plus historical Fear & Greed Index from Alternative.me.

Designed for backtesting — fetches large date ranges in chunks
and returns full numpy arrays matching the engine input format.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp
import numpy as np

logger = logging.getLogger(__name__)

# Reuse CCXT helpers from data_fetcher
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_fetcher import _parse_ohlcv, _create_exchange

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_CANDLES_PER_REQUEST = 1000  # Binance limit
_MAX_CONCURRENT_FETCHES = 3     # Lower than live scanner to avoid rate limits
_INTER_REQUEST_DELAY_S = 0.25   # Slightly longer delay for reliability
_FALLBACK_EXCHANGES = ["binance", "bybit"]

# Timeframe durations in milliseconds
_TF_MS = {
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
    "1w": 7 * 24 * 60 * 60 * 1000,
}


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _date_to_ms(date_str: str) -> int:
    """Convert 'YYYY-MM-DD' to milliseconds since epoch (UTC)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _ms_to_date(ms: int) -> str:
    """Convert milliseconds to 'YYYY-MM-DD'."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Single symbol historical fetch (with pagination)
# ---------------------------------------------------------------------------

async def fetch_historical_ohlcv(
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    exchange_id: str = "binance",
) -> Optional[dict]:
    """Fetch historical OHLCV for a single symbol with pagination.

    Parameters
    ----------
    symbol : str
        Trading pair (e.g. "BTC/USDT").
    timeframe : str
        Candle interval ("4h", "1d", "1w").
    start_ms : int
        Start timestamp in milliseconds.
    end_ms : int
        End timestamp in milliseconds.
    exchange_id : str
        Primary exchange.

    Returns
    -------
    dict or None
        Dict of numpy arrays {timestamp, open, high, low, close, volume}.
    """
    tf_ms = _TF_MS.get(timeframe)
    if tf_ms is None:
        logger.error("Unsupported timeframe: %s", timeframe)
        return None

    for exch_id in [exchange_id] + [e for e in _FALLBACK_EXCHANGES if e != exchange_id]:
        try:
            exchange = await _create_exchange(exch_id)
            await exchange.load_markets()

            if symbol not in exchange.markets:
                logger.debug("%s not found on %s, trying next exchange", symbol, exch_id)
                await exchange.close()
                continue

            all_candles = []
            cursor = start_ms

            while cursor < end_ms:
                try:
                    candles = await exchange.fetch_ohlcv(
                        symbol, timeframe,
                        since=cursor,
                        limit=_MAX_CANDLES_PER_REQUEST,
                    )
                except Exception as exc:
                    logger.debug("Fetch failed for %s at %d: %s", symbol, cursor, exc)
                    break

                if not candles:
                    break

                # Filter to within our range
                for c in candles:
                    if c[0] <= end_ms:
                        all_candles.append(c)

                # Advance cursor past last candle
                last_ts = candles[-1][0]
                if last_ts <= cursor:
                    break  # No progress — avoid infinite loop
                cursor = last_ts + tf_ms

                await asyncio.sleep(_INTER_REQUEST_DELAY_S)

            await exchange.close()

            if len(all_candles) < 10:
                logger.warning("Insufficient data for %s on %s (%d candles)", symbol, exch_id, len(all_candles))
                continue

            # Deduplicate by timestamp and sort
            seen = set()
            unique = []
            for c in all_candles:
                if c[0] not in seen:
                    seen.add(c[0])
                    unique.append(c)
            unique.sort(key=lambda x: x[0])

            logger.info(
                "Fetched %d %s candles for %s from %s (%s to %s)",
                len(unique), timeframe, symbol, exch_id,
                _ms_to_date(unique[0][0]), _ms_to_date(unique[-1][0]),
            )
            return _parse_ohlcv(unique)

        except Exception as exc:
            logger.warning("Failed to fetch %s from %s: %s", symbol, exch_id, exc)
            try:
                await exchange.close()
            except Exception:
                pass

    logger.error("Could not fetch historical data for %s on any exchange", symbol)
    return None


# ---------------------------------------------------------------------------
# Batch fetch (all symbols, one timeframe)
# ---------------------------------------------------------------------------

async def fetch_historical_batch(
    symbols: List[str],
    timeframe: str,
    start_date: str,
    end_date: str,
    warmup_bars: int = 0,
) -> Dict[str, dict]:
    """Fetch historical OHLCV for all symbols with concurrency control.

    Parameters
    ----------
    symbols : list[str]
        List of trading pairs.
    timeframe : str
        Candle interval.
    start_date : str
        Start date "YYYY-MM-DD".
    end_date : str
        End date "YYYY-MM-DD".
    warmup_bars : int
        Extra bars to fetch before start_date for engine warmup.

    Returns
    -------
    dict[str, dict]
        {symbol: ohlcv_dict} — missing symbols omitted.
    """
    end_ms = _date_to_ms(end_date)
    start_ms = _date_to_ms(start_date)

    # Subtract warmup bars from start
    tf_ms = _TF_MS.get(timeframe, _TF_MS["4h"])
    warmup_ms = warmup_bars * tf_ms
    fetch_start_ms = start_ms - warmup_ms

    results: Dict[str, dict] = {}
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

    fetch_count = [0]

    async def _fetch_one(sym: str):
        async with semaphore:
            logger.info("Fetching %s %s (%d/%d)...", sym, timeframe, fetch_count[0] + 1, len(symbols))
            data = await fetch_historical_ohlcv(sym, timeframe, fetch_start_ms, end_ms)
            fetch_count[0] += 1
            if data is not None:
                results[sym] = data
                logger.info("Fetched %s %s: %d bars", sym, timeframe, len(data.get("close", [])))
            else:
                logger.warning("Failed to fetch %s %s (no data returned)", sym, timeframe)

    tasks = [_fetch_one(sym) for sym in symbols]
    await asyncio.gather(*tasks)

    logger.info(
        "Batch fetch complete: %d/%d symbols for %s (%s to %s, warmup=%d)",
        len(results), len(symbols), timeframe, start_date, end_date, warmup_bars,
    )
    return results


# ---------------------------------------------------------------------------
# Fear & Greed historical data
# ---------------------------------------------------------------------------

async def fetch_historical_fear_greed(days: int = 365) -> Dict[str, int]:
    """Fetch historical Fear & Greed Index from Alternative.me.

    Returns
    -------
    dict[str, int]
        {date_str: fear_greed_value} for lookup during replay.
        Date format: "YYYY-MM-DD".
    """
    url = f"https://api.alternative.me/fng/?limit={days}"
    timeout = aiohttp.ClientTimeout(total=15)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        data_list = payload.get("data", [])
        result: Dict[str, int] = {}

        for entry in data_list:
            ts = int(entry.get("timestamp", 0))
            value = int(entry.get("value", 50))
            if ts > 0:
                date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                result[date_str] = value

        logger.info("Fetched %d days of Fear & Greed history", len(result))
        return result

    except Exception as exc:
        logger.warning("Failed to fetch F&G history: %s", exc)
        return {}
