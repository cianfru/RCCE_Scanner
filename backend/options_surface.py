"""
options_surface.py
~~~~~~~~~~~~~~~~~~
Options-market context for the coin page: Derive's implied volatility for BTC and ETH,
read from the derive_scan service (its own repo), which records the surface every 15
minutes.

Cost: nothing is read until someone opens a recorded coin's page, then at most one
small read per coin per derive_scan snapshot (the body is kept until the next one is
due). Coins derive_scan does not record never cause a read. When derive_scan cannot be
reached the last good body is served, marked stale.

Railway variables:
    DERIVE_SCAN_URL           derive_scan's base URL; unset turns the panel off
    DERIVE_SCAN_UNDERLYINGS   coins it records (default BTC,ETH)

The values are context, not a signal: no study has tested them against Reflex's
signals yet (see the derive_scan repo's plan).
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger("options_surface")

SNAPSHOT_SEC = 900          # derive_scan's recording interval
GRACE_SEC = 120             # a snapshot takes a few seconds to land
RETRY_SEC = 60              # after a failed read, wait this long before trying again
STALE_SEC = 3 * SNAPSHOT_SEC

_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}   # coin -> (last attempt, body)
_locks: Dict[str, asyncio.Lock] = {}


def base_url() -> str:
    return os.environ.get("DERIVE_SCAN_URL", "").strip().rstrip("/")


def recorded() -> set:
    raw = os.environ.get("DERIVE_SCAN_UNDERLYINGS", "BTC,ETH")
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def coin_of(symbol: str) -> str:
    return (symbol or "").upper().split("/")[0].split("-")[0].strip()


def shape(surface: Dict[str, Any]) -> Dict[str, Any]:
    """derive_scan's /api/surface body -> what the panel draws."""
    f = surface.get("features") or {}
    iv30 = f.get("atm_iv_30d")
    index = f.get("index_price")
    # One standard deviation over 30 days, from the 30-day implied volatility.
    move = iv30 * math.sqrt(30 / 365) if iv30 else None
    curve = [{"days": round(e["tenor_days"], 2), "iv": round(e["atm_iv"], 4)}
             for e in surface.get("expiries") or []
             if e.get("atm_iv") and (e.get("tenor_days") or 0) > 0]
    r = lambda v, n=4: round(v, n) if isinstance(v, (int, float)) else None
    return {
        "available": True,
        "venue": "Derive",
        "ts": surface.get("ts"),
        "iv": {"7": r(f.get("atm_iv_7d")), "30": r(iv30), "90": r(f.get("atm_iv_90d"))},
        "rr25_30d": r(f.get("rr25_30d")),
        "bf25_30d": r(f.get("bf25_30d")),
        "funding_ann": r(f.get("funding_ann")),
        "index_price": r(index, 2),
        "move_30d": r(move),
        "range_30d": [r(index * (1 - move), 2), r(index * (1 + move), 2)] if move and index else None,
        "curve": curve,
    }


def _due(body: Optional[Dict[str, Any]], attempted: float, now: float) -> bool:
    """Whether a read could bring anything new."""
    if body is None or not body.get("ts"):
        return now - attempted >= RETRY_SEC
    next_snapshot = body["ts"] + SNAPSHOT_SEC + GRACE_SEC
    return now >= next_snapshot and now - attempted >= RETRY_SEC


async def _read(coin: str) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{base_url()}/api/surface/{coin}") as resp:
            resp.raise_for_status()
            return await resp.json()


async def surface_for(symbol: str, now: Optional[float] = None) -> Dict[str, Any]:
    coin = coin_of(symbol)
    if not base_url() or coin not in recorded():
        return {"available": False}
    now = time.time() if now is None else now
    attempted, body = _cache.get(coin, (0.0, None))
    if _due(body, attempted, now):
        lock = _locks.setdefault(coin, asyncio.Lock())
        async with lock:
            attempted, body = _cache.get(coin, (0.0, None))
            if _due(body, attempted, now):
                try:
                    body = shape(await _read(coin))
                except Exception as e:
                    logger.warning("derive_scan read for %s failed: %s", coin, e)
                _cache[coin] = (now, body)
    if body is None:
        return {"available": False}
    out = dict(body, symbol=coin)
    out["as_of"] = body.get("ts")
    out["stale"] = bool(body.get("ts")) and now - body["ts"] > STALE_SEC
    return out
