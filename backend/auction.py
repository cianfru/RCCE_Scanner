"""
The coin chart's Value layer: value areas, points of control and reference levels
(engines/auction_engine.py), built when someone turns the layer on.

Each build reads one series of Hyperliquid candles a step below the chart's (15m under 4h,
1h under 1d) and the stored daily candles, and the answer is kept for 15 minutes. Only the
answers are kept (a few KB each, the newest MAX_CACHED), never the candles, so the layer adds
no standing memory and no background work.

A build costs 68 to 92 of Hyperliquid's weight (20 a request plus 1 per 60 candles). The layer
has its own small share of the per-IP budget so chart views cannot crowd out the scan: when
that share is used up the request is answered "busy" and the page tries again later.
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
BUSY_WAIT_S = 6               # how long a view waits for its share of the budget before "busy"
MIN_SESSIONS = 2
_bucket = TokenBucket(240, capacity=240)

_cache: Dict[Tuple[str, str], tuple] = {}            # (symbol, timeframe) -> (built_at, body)
_building: Dict[Tuple[str, str], asyncio.Future] = {}


class Busy(Exception):
    """The layer's share of the Hyperliquid budget is used up, or Hyperliquid is limiting us."""


class NoData(Exception):
    """Hyperliquid has no intraday candles for this market (or too few for one session)."""


async def _candles(coin: str, interval: str, days: int, now_ms: int) -> Optional[dict]:
    from data_fetcher import _parse_hl_candles
    start = (now_ms // auction_engine.DAY_MS - days) * auction_engine.DAY_MS
    weight = hl_calls.candle_weight(days * auction_engine.DAY_MS // auction_engine.INTERVAL_MS[interval])
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
    candles = await _candles(_hl_coin_name(symbol), plan["interval"], plan["days"], now_ms)
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


def _prune(now: float) -> None:
    for k in [k for k, (at, _) in _cache.items() if now - at >= CACHE_S]:
        del _cache[k]
    while len(_cache) > MAX_CACHED:
        del _cache[min(_cache, key=lambda k: _cache[k][0])]


async def levels(symbol: str, timeframe: str) -> dict:
    """The Value layer for one chart; views of the same chart share one build and its answer."""
    key = (symbol, timeframe)
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_S:
        return hit[1]
    task = _building.get(key)
    if task is None:
        async def run() -> dict:
            body = await _build(symbol, timeframe)
            _cache[key] = (time.time(), body)
            _prune(time.time())
            return body
        task = _building[key] = asyncio.ensure_future(run())
        # Retrieve the result even when every waiting view has gone, so a failure is not logged as unhandled.
        task.add_done_callback(lambda t: (_building.pop(key, None), t.cancelled() or t.exception()))
    return await asyncio.shield(task)
