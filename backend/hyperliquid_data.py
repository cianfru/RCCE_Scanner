"""
hyperliquid_data.py
~~~~~~~~~~~~~~~~~~~
Fetches on-chain positioning data from Hyperliquid's REST API.

Provides funding rates, open interest, mark/oracle prices, and predicted
funding for all listed perpetual contracts.  No API key required.

Endpoint: POST https://api.hyperliquid.xyz/info
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
# Hyperliquid API endpoint
# ---------------------------------------------------------------------------

_HL_API_URL = "https://api.hyperliquid.xyz/info"

_CACHE_TTL = 5 * 60        # 5 minutes, matching scan interval
_REQUEST_TIMEOUT_S = 15
_MAX_RETRIES = 2
_RETRY_DELAY_S = 2.0


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class HyperliquidMetrics:
    """Per-asset positioning data from Hyperliquid."""
    coin: str = ""                   # e.g. "BTC"
    funding_rate: float = 0.0        # Current hourly funding rate
    open_interest: float = 0.0       # Open interest in USD
    mark_price: float = 0.0          # Mark price
    oracle_price: float = 0.0        # Oracle price
    volume_24h: float = 0.0          # 24h trading volume in USD
    predicted_funding: float = 0.0   # Next predicted funding rate
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _HLCache:
    """TTL cache for Hyperliquid metrics."""
    data: Optional[Dict[str, HyperliquidMetrics]] = None
    expires_at: float = 0.0

    def get(self) -> Optional[Dict[str, HyperliquidMetrics]]:
        if self.data and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: Dict[str, HyperliquidMetrics]) -> None:
        self.data = data
        self.expires_at = time.monotonic() + _CACHE_TTL

    def get_fallback(self) -> Optional[Dict[str, HyperliquidMetrics]]:
        return self.data


_cache = _HLCache()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

async def _post_info(session: aiohttp.ClientSession, payload: dict) -> dict:
    """POST to Hyperliquid info endpoint."""
    async with session.post(
        _HL_API_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


def _coin_from_symbol(symbol: str) -> str:
    """Convert scanner symbol 'BTC/USDT' → Hyperliquid coin name 'BTC'."""
    return symbol.split("/")[0].upper()


def _symbol_from_coin(coin: str) -> str:
    """Convert Hyperliquid coin name 'BTC' → scanner symbol 'BTC/USDT'."""
    return f"{coin}/USDT"


# ---------------------------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------------------------

async def fetch_hyperliquid_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, HyperliquidMetrics]:
    """Fetch funding rates, OI, and prices for all Hyperliquid perps.

    Returns a dict keyed by scanner symbol (e.g. 'BTC/USDT').
    Symbols not listed on Hyperliquid are omitted from the result.

    Parameters
    ----------
    symbols : list[str] or None
        If provided, filter results to only these scanner symbols.
        If None, return all available perps.
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
                # Fetch meta + asset contexts in a single call
                meta_resp = await _post_info(session, {"type": "metaAndAssetCtxs"})

                # Fetch predicted fundings
                try:
                    pred_resp = await _post_info(session, {"type": "predictedFundings"})
                except Exception:
                    pred_resp = []

            return _parse_metrics(meta_resp, pred_resp, symbols)

        except aiohttp.ClientError as exc:
            last_error = exc
            logger.warning(
                "Hyperliquid request failed (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )
        except Exception as exc:
            last_error = exc
            logger.error(
                "Unexpected error fetching Hyperliquid data (attempt %d/%d): %s",
                attempt + 1, _MAX_RETRIES + 1, exc,
            )

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_RETRY_DELAY_S)

    # Fallback to stale cache
    fallback = _cache.get_fallback()
    if fallback is not None:
        logger.warning("Using stale Hyperliquid data after fetch failure: %s", last_error)
        if symbols:
            return {s: fallback[s] for s in symbols if s in fallback}
        return fallback

    logger.error("Hyperliquid data unavailable: %s", last_error)
    return {}


def _parse_metrics(
    meta_resp: list,
    pred_resp: list,
    symbols: Optional[List[str]],
) -> Dict[str, HyperliquidMetrics]:
    """Parse metaAndAssetCtxs response into HyperliquidMetrics dict."""
    now = time.time()
    result: Dict[str, HyperliquidMetrics] = {}

    # metaAndAssetCtxs returns [meta_info, [asset_ctx, ...]]
    if not isinstance(meta_resp, list) or len(meta_resp) < 2:
        logger.warning("Unexpected metaAndAssetCtxs format")
        return result

    meta_info = meta_resp[0]
    asset_ctxs = meta_resp[1]

    # Get universe (coin metadata)
    universe = meta_info.get("universe", [])

    # Build predicted funding lookup
    # Response format: ["COIN", [["BinPerp", {fundingRate}], ["HlPerp", {fundingRate}], ...]]
    pred_lookup: Dict[str, float] = {}
    if isinstance(pred_resp, list):
        for item in pred_resp:
            if isinstance(item, list) and len(item) >= 2:
                coin = item[0]
                venues = item[1]
                if isinstance(venues, list):
                    # Prefer HlPerp, fallback to first venue
                    for venue in venues:
                        if isinstance(venue, list) and len(venue) >= 2 and venue[0] == "HlPerp":
                            if isinstance(venue[1], dict):
                                pred_lookup[coin] = float(venue[1].get("fundingRate", 0.0))
                            break
                    else:
                        # No HlPerp found — use first venue
                        if venues and isinstance(venues[0], list) and len(venues[0]) >= 2:
                            if isinstance(venues[0][1], dict):
                                pred_lookup[coin] = float(venues[0][1].get("fundingRate", 0.0))
                elif isinstance(venues, dict):
                    pred_lookup[coin] = float(venues.get("fundingRate", 0.0))

    # Parse ALL assets (never filter during parse — cache needs the full set)
    for i, ctx in enumerate(asset_ctxs):
        if i >= len(universe):
            break

        coin_info = universe[i]
        coin = coin_info.get("name", "")
        scanner_symbol = _symbol_from_coin(coin)

        try:
            funding = float(ctx.get("funding", 0.0))
            oi_raw = float(ctx.get("openInterest", 0.0))
            mark = float(ctx.get("markPx", 0.0))
            oracle = float(ctx.get("oraclePx", 0.0))
            vol_24h = float(ctx.get("dayNtlVlm", 0.0))

            # OI is in coins, convert to USD using mark price
            oi_usd = oi_raw * mark if mark > 0 else 0.0

            metrics = HyperliquidMetrics(
                coin=coin,
                funding_rate=funding,
                open_interest=oi_usd,
                mark_price=mark,
                oracle_price=oracle,
                volume_24h=vol_24h,
                predicted_funding=pred_lookup.get(coin, 0.0),
                timestamp=now,
            )
            result[scanner_symbol] = metrics

        except (ValueError, TypeError) as exc:
            logger.debug("Failed to parse Hyperliquid data for %s: %s", coin, exc)
            continue

    # Cache all results
    _cache.put(result)

    logger.info(
        "Fetched Hyperliquid metrics for %d perps (BTC funding=%.4f%%, OI=$%.0fM)",
        len(result),
        result.get("BTC/USDT", HyperliquidMetrics()).funding_rate * 100,
        result.get("BTC/USDT", HyperliquidMetrics()).open_interest / 1e6,
    )

    if symbols:
        return {s: result[s] for s in symbols if s in result}
    return result


async def fetch_funding_history(
    coin: str,
    hours: int = 24,
) -> List[dict]:
    """Fetch historical funding rates for a single coin.

    Parameters
    ----------
    coin : str
        Hyperliquid coin name (e.g. "BTC", not "BTC/USDT").
    hours : int
        How many hours of history to fetch.

    Returns
    -------
    list[dict]
        Each dict has 'coin', 'fundingRate', 'premium', 'time'.
    """
    start_time = int((time.time() - hours * 3600) * 1000)
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            resp = await _post_info(session, {
                "type": "fundingHistory",
                "coin": coin,
                "startTime": start_time,
            })
        return resp if isinstance(resp, list) else []
    except Exception as exc:
        logger.warning("Failed to fetch funding history for %s: %s", coin, exc)
        return []


def get_cached_metrics() -> Optional[Dict[str, HyperliquidMetrics]]:
    """Return cached Hyperliquid metrics (even if expired)."""
    return _cache.get_fallback()


# ---------------------------------------------------------------------------
# User position fetching (clearinghouse state)
# ---------------------------------------------------------------------------

_POS_CACHE_TTL = 60  # 1 minute — positions refresh fast


@dataclass
class _PosCacheEntry:
    data: Optional[dict] = None
    expires_at: float = 0.0


_pos_cache: Dict[str, _PosCacheEntry] = {}


async def fetch_clearinghouse_state(address: str) -> Optional[dict]:
    """Fetch a user's clearinghouse state from Hyperliquid (public, no auth).

    Returns the raw API response dict containing:
      - marginSummary: {accountValue, totalMarginUsed, ...}
      - assetPositions: [{position: {coin, szi, entryPx, leverage, ...}}, ...]
      - crossMarginSummary, withdrawable, etc.

    Returns None on failure.
    """
    address = address.lower()

    # Check per-address cache
    entry = _pos_cache.get(address)
    if entry and time.monotonic() < entry.expires_at:
        return entry.data

    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            data = await _post_info(session, {
                "type": "clearinghouseState",
                "user": address,
            })
        _pos_cache[address] = _PosCacheEntry(data=data, expires_at=time.monotonic() + _POS_CACHE_TTL)
        return data
    except Exception as exc:
        logger.warning("Failed to fetch clearinghouse state for %s: %s", address[:10], exc)
        # Return stale cache if available
        if entry and entry.data:
            return entry.data
        return None


def parse_open_positions(clearinghouse: dict) -> List[dict]:
    """Extract open positions from clearinghouse state response.

    Returns list of dicts with keys:
      coin, side, size, size_usd, entry_px, unrealized_pnl, leverage, liq_px, margin_used
    """
    positions = []
    for ap in clearinghouse.get("assetPositions", []):
        pos = ap.get("position", {})
        szi = float(pos.get("szi", 0))
        if szi == 0:
            continue

        entry_px = float(pos.get("entryPx", 0))
        coin = pos.get("coin", "")
        leverage_val = pos.get("leverage", {})
        lev = float(leverage_val.get("value", 1)) if isinstance(leverage_val, dict) else float(leverage_val or 1)

        positions.append({
            "coin": coin,
            "symbol": f"{coin}/USDT",
            "side": "LONG" if szi > 0 else "SHORT",
            "size": abs(szi),
            "size_usd": abs(szi) * entry_px,
            "entry_px": entry_px,
            "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
            "leverage": lev,
            "liq_px": float(pos.get("liquidationPx", 0) or 0),
            "margin_used": float(pos.get("marginUsed", 0)),
        })
    return positions


# ---------------------------------------------------------------------------
# Builder DEX (HIP-3) discovery + metrics
# ---------------------------------------------------------------------------

# Cache for perpDexs discovery (refreshed daily)
_perp_dexs_cache: Optional[list] = None
_perp_dexs_expires_at: float = 0
_PERP_DEXS_TTL = 24 * 3600  # 24 hours

# Per-dex metrics cache
_dex_caches: Dict[str, _HLCache] = {}


async def fetch_perp_dexs() -> List[str]:
    """Discover all live builder-deployed DEXes on HyperLiquid.

    Returns a list of dex name strings (e.g., ["xyz", "flx", "vntl", ...]).
    Cached for 24 hours.
    """
    global _perp_dexs_cache, _perp_dexs_expires_at

    now = time.monotonic()
    if _perp_dexs_cache is not None and now < _perp_dexs_expires_at:
        return _perp_dexs_cache

    try:
        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            resp = await _post_info(session, {"type": "perpDexs"})

        dexs = []
        if isinstance(resp, list):
            for entry in resp:
                if entry is not None and isinstance(entry, dict):
                    name = entry.get("name", "")
                    if name:
                        dexs.append(name)

        _perp_dexs_cache = dexs
        _perp_dexs_expires_at = now + _PERP_DEXS_TTL
        logger.info("Discovered %d builder DEXes: %s", len(dexs), ", ".join(dexs))
        return dexs

    except Exception as exc:
        logger.warning("Failed to fetch perpDexs: %s", exc)
        return _perp_dexs_cache or []


async def fetch_hyperliquid_dex_metrics(
    dex: str = "xyz",
) -> Dict[str, HyperliquidMetrics]:
    """Fetch funding rates, OI, and prices for all instruments on a builder DEX.

    Returns a dict keyed by scanner-format symbol (e.g. 'GOLD/USD').
    """
    # Per-dex cache
    if dex not in _dex_caches:
        _dex_caches[dex] = _HLCache()
    cache = _dex_caches[dex]

    cached = cache.get()
    if cached is not None:
        return cached

    try:
        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            meta_resp = await _post_info(session, {"type": "metaAndAssetCtxs", "dex": dex})

            # Try predicted fundings for this dex
            try:
                pred_resp = await _post_info(session, {"type": "predictedFundings", "dex": dex})
            except Exception:
                pred_resp = []

        return _parse_dex_metrics(meta_resp, pred_resp, dex, cache)

    except Exception as exc:
        logger.warning("Failed to fetch %s DEX metrics: %s", dex, exc)
        fallback = cache.get_fallback()
        return fallback if fallback is not None else {}


def _parse_dex_metrics(
    meta_resp: list,
    pred_resp: list,
    dex: str,
    cache: _HLCache,
) -> Dict[str, HyperliquidMetrics]:
    """Parse metaAndAssetCtxs for a builder DEX into HyperliquidMetrics dict."""
    now = time.time()
    result: Dict[str, HyperliquidMetrics] = {}

    if not isinstance(meta_resp, list) or len(meta_resp) < 2:
        logger.warning("Unexpected metaAndAssetCtxs format for dex=%s", dex)
        return result

    meta_info = meta_resp[0]
    asset_ctxs = meta_resp[1]
    universe = meta_info.get("universe", [])

    # Predicted funding lookup (same format as crypto)
    pred_lookup: Dict[str, float] = {}
    if isinstance(pred_resp, list):
        for item in pred_resp:
            if isinstance(item, list) and len(item) >= 2:
                coin_name = item[0]
                venues = item[1]
                if isinstance(venues, list):
                    for venue in venues:
                        if isinstance(venue, list) and len(venue) >= 2:
                            if isinstance(venue[1], dict):
                                pred_lookup[coin_name] = float(venue[1].get("fundingRate", 0.0))
                            break
                elif isinstance(venues, dict):
                    pred_lookup[coin_name] = float(venues.get("fundingRate", 0.0))

    for i, ctx in enumerate(asset_ctxs):
        if i >= len(universe):
            break

        coin_info = universe[i]
        raw_name = coin_info.get("name", "")  # e.g., "xyz:GOLD"
        # Strip dex prefix if present
        coin = raw_name.split(":", 1)[1] if ":" in raw_name else raw_name
        # Use /USD suffix for TradFi symbols (not /USDT)
        scanner_symbol = f"{coin}/USD"

        try:
            funding = float(ctx.get("funding", 0.0))
            oi_raw = float(ctx.get("openInterest", 0.0))
            mark = float(ctx.get("markPx", 0.0))
            oracle = float(ctx.get("oraclePx", 0.0))
            vol_24h = float(ctx.get("dayNtlVlm", 0.0))
            oi_usd = oi_raw * mark if mark > 0 else 0.0

            metrics = HyperliquidMetrics(
                coin=coin,
                funding_rate=funding,
                open_interest=oi_usd,
                mark_price=mark,
                oracle_price=oracle,
                volume_24h=vol_24h,
                predicted_funding=pred_lookup.get(raw_name, 0.0),
                timestamp=now,
            )
            result[scanner_symbol] = metrics

        except (ValueError, TypeError) as exc:
            logger.debug("Failed to parse %s DEX data for %s: %s", dex, raw_name, exc)
            continue

    cache.put(result)

    # Log summary
    if result:
        sample = next(iter(result.values()))
        logger.info(
            "Fetched %s DEX metrics: %d instruments (sample: %s funding=%.6f%%, OI=$%.0fK)",
            dex, len(result), sample.coin,
            sample.funding_rate * 100, sample.open_interest / 1e3,
        )

    return result
