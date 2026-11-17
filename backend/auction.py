"""
Chart data read on demand, when someone asks for it on a coin's chart:

* the Value layer: value areas, points of control and reference levels
  (engines/auction_engine.py), from Hyperliquid candles a step below the chart's (15m under
  1h and 4h, 1h under 1d) and the stored daily candles; the answer is kept for 15 minutes;
* the 1-hour chart's candles (the scan stores 4h, 1d and 1w only), kept for 2 minutes.

Only the newest answers are kept (MAX_CACHED of each, a few KB to 60 KB), so this adds no
standing memory and no background work.

A Value build costs 68 to 92 of Hyperliquid's weight (20 a request plus 1 per 60 candles), an
hourly chart 30. Both draw on one small share of the per-IP budget so chart views cannot crowd
out the scan: when that share is used up the request is answered "busy" and the page tries
again later.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional, Tuple

import aiohttp

import hl_calls
from cohorts.sweeper import TokenBucket
from engines import auction_engine

logger = logging.getLogger(__name__)

INFO_URL = "https://api.hyperliquid.xyz/info"
CACHE_S = 15 * 60
MAX_CACHED = 48
HOUR_BARS = 600               # the 1-hour chart: 25 days
HOUR_CACHE_S = 120
HOUR_MAX_CACHED = 24
BUSY_WAIT_S = 6               # how long a view waits for its share of the budget before "busy"
MIN_SESSIONS = 2
_bucket = TokenBucket(240, capacity=240)

_cache: Dict[Tuple[str, str], tuple] = {}            # (symbol, candle interval) -> (built_at, body)
_hour_cache: Dict[str, tuple] = {}                   # symbol -> (read_at, candles)
_building: Dict[tuple, asyncio.Future] = {}


class Busy(Exception):
    """The layer's share of the Hyperliquid budget is used up, or Hyperliquid is limiting us."""


class NoData(Exception):
    """Hyperliquid has no intraday candles for this market (or too few for one session)."""


async def _candles(coin: str, interval: str, start: int, now_ms: int) -> Optional[dict]:
    from data_fetcher import _parse_hl_candles
    weight = hl_calls.candle_weight((now_ms - start) // auction_engine.INTERVAL_MS[interval])
    try:
        await asyncio.wait_for(_bucket.take(weight), BUSY_WAIT_S)
    except asyncio.TimeoutError:
        raise Busy("budget") from None
    hl_calls.record("candleSnapshot")
    hl_calls.record_weight("candleSnapshot", weight - hl_calls.DEFAULT_WEIGHT)
    body = {"type": "candleSnapshot", "req": {"coin": coin, "interval": interval, "startTime": start, "endTime": now_ms}}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(INFO_URL, json=body) as resp:
            if resp.status == 429:
                _bucket.penalize()
                hl_calls.rate_limited()
                raise Busy("429")
            if resp.status != 200:
                return None
            return _parse_hl_candles(await resp.json(content_type=None))


async def _build(symbol: str, timeframe: str) -> dict:
    from data_fetcher import _hl_coin_name, fetch_ohlcv
    plan = auction_engine.PLANS[timeframe]
    now_ms = int(time.time() * 1000)
    start = (now_ms // auction_engine.DAY_MS - plan["days"]) * auction_engine.DAY_MS
    candles = await _candles(_hl_coin_name(symbol), plan["interval"], start, now_ms)
    if candles is None or len(candles["timestamp"]) < 2:
        raise NoData("No intraday candles for this market")
    daily = None
    try:
        daily = await fetch_ohlcv(symbol, "1d")
    except Exception:
        logger.warning("Value layer: no daily candles for %s", symbol)
    body = auction_engine.build(candles, daily, timeframe, now_ms)
    if len(body["sessions"]) < MIN_SESSIONS:
        raise NoData("Too little history for a value area")
    body["symbol"] = symbol
    return body


def _prune(store: dict, ttl: float, keep: int) -> None:
    now = time.time()
    for k in [k for k, (at, _) in store.items() if now - at >= ttl]:
        del store[k]
    while len(store) > keep:
        del store[min(store, key=lambda k: store[k][0])]


async def _shared(store: dict, key, ttl: float, keep: int, build):
    """The stored answer while it is fresh; otherwise one build shared by every view waiting for it."""
    hit = store.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    slot = (id(store), key)
    task = _building.get(slot)
    if task is None:
        async def run():
            body = await build()
            store[key] = (time.time(), body)
            _prune(store, ttl, keep)
            return body
        task = _building[slot] = asyncio.ensure_future(run())
        # Retrieve the result even when every waiting view has gone, so a failure is not logged as unhandled.
        task.add_done_callback(lambda t: (_building.pop(slot, None), t.cancelled() or t.exception()))
    return await asyncio.shield(task)


async def levels(symbol: str, timeframe: str) -> dict:
    """The Value layer for one chart. Charts built from the same candles (1h and 4h) share one answer."""
    interval = auction_engine.PLANS[timeframe]["interval"]
    body = await _shared(_cache, (symbol, interval), CACHE_S, MAX_CACHED, lambda: _build(symbol, timeframe))
    return body if body.get("timeframe") == timeframe else {**body, "timeframe": timeframe}


async def hour_candles(symbol: str) -> dict:
    """The latest HOUR_BARS 1-hour candles of a market (arrays, times in ms)."""
    async def build() -> dict:
        from data_fetcher import _hl_coin_name
        now_ms = int(time.time() * 1000)
        start = now_ms - HOUR_BARS * auction_engine.INTERVAL_MS["1h"]
        candles = await _candles(_hl_coin_name(symbol), "1h", start, now_ms)
        if candles is None or len(candles["timestamp"]) < 50:
            raise NoData("No hourly candles for this market")
        return candles
    return await _shared(_hour_cache, symbol, HOUR_CACHE_S, HOUR_MAX_CACHED, build)
