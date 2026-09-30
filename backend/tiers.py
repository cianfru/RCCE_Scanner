"""
Access tiers: "free" (the scanner and a delayed Radar) and "holder" (the live Radar,
alerts, following traders, trader profiles and Telegram).

A holder holds at least REFLEX_TOKEN_MIN of the Reflex token on Hyperliquid spot
(HyperCore), read from the public info API (spotClearinghouseState) and matched by
REFLEX_TOKEN_NAME (or REFLEX_TOKEN_INDEX when set). Addresses in REFLEX_HOLDER_ALLOWLIST
and the owner count as holders. Balances are cached ten minutes per address.

Gating applies only when ACCESS_TIERS is on (and accounts are on, so people can sign in);
otherwise every feature stays open as before.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Awaitable, Callable, Dict, Optional, Tuple

import accounts

logger = logging.getLogger(__name__)

CACHE_S = 600
RETRY_S = 60
FREE, HOLDER = "free", "holder"
HOLDER_FEATURES = ("live_radar", "alerts", "follows", "trader_profiles", "telegram")

_cache: Dict[str, Tuple[float, Optional[float]]] = {}      # address -> (read at, balance or None)
_CACHE_MAX = 20_000


def enforced() -> bool:
    return accounts.enabled() and os.environ.get("ACCESS_TIERS", "").strip().lower() in accounts.TRUE


def radar_delay_s() -> int:
    try:
        return max(0, int(float(os.environ.get("REFLEX_FREE_RADAR_DELAY_MIN", 60)) * 60))
    except ValueError:
        return 3600


def allowlist() -> set:
    out = {a.strip().lower() for a in os.environ.get("REFLEX_HOLDER_ALLOWLIST", "").split(",")
           if accounts.valid_address(a.strip())}
    if accounts.owner():
        out.add(accounts.owner())
    return out


def token_config() -> Optional[dict]:
    """{name, index, min} or None while the token is not configured."""
    name = os.environ.get("REFLEX_TOKEN_NAME", "").strip()
    index = os.environ.get("REFLEX_TOKEN_INDEX", "").strip()
    raw_min = os.environ.get("REFLEX_TOKEN_MIN", "").strip()
    if not (name or index) or not raw_min:
        return None
    try:
        return {"name": name, "index": int(index) if index else None, "min": float(raw_min)}
    except ValueError:
        return None


def balance_of(state: Optional[dict], cfg: dict) -> float:
    """The token's total in a spotClearinghouseState reply (0 when absent)."""
    for b in (state or {}).get("balances") or []:
        if cfg.get("index") is not None:
            match = b.get("token") == cfg["index"]
        else:
            match = str(b.get("coin", "")).upper() == cfg["name"].upper()
        if match:
            try:
                return float(b.get("total") or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


async def _spot_state(address: str) -> Optional[dict]:
    import aiohttp
    from hyperliquid_data import _post_info
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        return await _post_info(session, {"type": "spotClearinghouseState", "user": address})


Fetch = Callable[[str], Awaitable[Optional[dict]]]


async def balance(address: str, now: Optional[float] = None, fetch: Optional[Fetch] = None) -> Optional[float]:
    """The address's token balance, from the cache when fresh. None when unknown."""
    cfg = token_config()
    if cfg is None:
        return None
    now = now or time.time()
    a = address.lower()
    hit = _cache.get(a)
    if hit and now - hit[0] < (CACHE_S if hit[1] is not None else RETRY_S):
        return hit[1]
    try:
        value: Optional[float] = balance_of(await (fetch or _spot_state)(a), cfg)
    except Exception as exc:
        logger.debug("tiers: balance of %s not read: %s", a[:10], exc)
        if hit and hit[1] is not None:           # keep the last known balance, try again in a minute
            _cache[a] = (now - CACHE_S + RETRY_S, hit[1])
            return hit[1]
        value = None
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[a] = (now, value)
    return value


async def tier_for(user: Optional[str], now: Optional[float] = None, fetch: Optional[Fetch] = None) -> str:
    """"holder" for an allowlisted address or one holding at least the threshold, else "free"."""
    if not user:
        return FREE
    a = user.lower()
    if a in allowlist():
        return HOLDER
    cfg = token_config()
    if cfg is None:
        return FREE
    bal = await balance(a, now, fetch)
    return HOLDER if bal is not None and bal >= cfg["min"] else FREE


async def allows(user: Optional[str], now: Optional[float] = None, fetch: Optional[Fetch] = None) -> bool:
    """Whether the user gets the holder features (always, while tiers are off)."""
    return not enforced() or await tier_for(user, now, fetch) == HOLDER


def reset() -> None:
    _cache.clear()
