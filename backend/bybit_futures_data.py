"""
bybit_futures_data.py
~~~~~~~~~~~~~~~~~~~~~
Fetches positioning data (OI, funding rates, mark prices) from
Bybit's public v5 tickers endpoint. Acts as fallback for symbols not on Hyperliquid
(e.g. MOG, smaller altcoins).

Bybit funds every 8 hours. ``lastFundingRate`` is per-period (8h);
we normalise to *hourly* to stay consistent with the positioning
engine thresholds.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL = 5 * 60          # 5 minutes
_FUNDING_PERIOD_HOURS = 8     # Bybit funds every 8h

# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class BybitFuturesMetrics:
    """Per-asset positioning data from Bybit."""
    coin: str = ""
    funding_rate: float = 0.0          # Hourly funding rate (normalised)
    funding_rate_raw: float = 0.0      # Raw per-period (8h) rate
    open_interest: float = 0.0         # OI in USD
    mark_price: float = 0.0
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _Cache:
    data: Optional[Dict[str, BybitFuturesMetrics]] = None
    expires_at: float = 0.0

    def get(self) -> Optional[Dict[str, BybitFuturesMetrics]]:
        if self.data and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: Dict[str, BybitFuturesMetrics]) -> None:
        self.data = data
        self.expires_at = time.monotonic() + _CACHE_TTL

    def get_fallback(self) -> Optional[Dict[str, BybitFuturesMetrics]]:
        return self.data


_cache = _Cache()

# One public REST call returns every linear perp (no ccxt: importing it and loading
# Bybit's markets cost ~40-70 MB of RSS for a fallback that rarely has anything to fill).
_TICKERS_URL = "https://api.bybit.com/v5/market/tickers?category=linear"
_PREFIXES = ("1000000", "10000", "1000", "100")   # multiplier prefixes, e.g. 1000PEPEUSDT
_FAIL_BACKOFF_S = 15 * 60                          # unreachable or blocked: retry after 15 min
_failed_at = 0.0


def _scanner_symbol(bybit_symbol: str) -> Optional[str]:
    """'1000PEPEUSDT' -> 'PEPE/USDT'; None for USDC perps and dated futures."""
    if not bybit_symbol.endswith("USDT") or not bybit_symbol.isalnum():
        return None
    base = bybit_symbol[:-4]
    for prefix in _PREFIXES:
        if base.startswith(prefix) and len(base) > len(prefix):
            return f"{base[len(prefix):]}/USDT"
    return f"{base}/USDT" if base else None


def _parse_tickers(rows: list, now: float) -> Dict[str, BybitFuturesMetrics]:
    """Ticker rows -> metrics per scanner symbol; the unprefixed listing wins a clash."""
    out: Dict[str, BybitFuturesMetrics] = {}
    prefixed: Dict[str, bool] = {}
    for row in rows or []:
        sym = _scanner_symbol(str(row.get("symbol", "")))
        if sym is None:
            continue
        is_prefixed = sym.split("/")[0] != row["symbol"][:-4]
        if sym in out and (is_prefixed or not prefixed[sym]):
            continue
        try:
            funding_raw = float(row.get("fundingRate") or 0.0)
            mark = float(row.get("markPrice") or 0.0)
            oi_usd = float(row.get("openInterestValue") or 0.0)
        except (TypeError, ValueError):
            continue
        out[sym] = BybitFuturesMetrics(
            coin=sym.split("/")[0],
            funding_rate=funding_raw / _FUNDING_PERIOD_HOURS,
            funding_rate_raw=funding_raw,
            open_interest=oi_usd if mark > 0 else 0.0,
            mark_price=mark,
            timestamp=now,
        )
        prefixed[sym] = is_prefixed
    return out


async def _fetch_all() -> Optional[Dict[str, BybitFuturesMetrics]]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(_TICKERS_URL) as resp:
            resp.raise_for_status()
            body = await resp.json(content_type=None)
    if not isinstance(body, dict) or body.get("retCode") != 0:
        raise RuntimeError(f"Bybit tickers: retCode {body.get('retCode') if isinstance(body, dict) else '?'}")
    return _parse_tickers((body.get("result") or {}).get("list") or [], time.time())


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

async def fetch_bybit_futures_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, BybitFuturesMetrics]:
    """Fetch OI and funding from Bybit for given scanner symbols.

    Only fetches for symbols not covered by HL — call with the
    gap list, not all symbols. Only '<BASE>/USDT' symbols can map to a Bybit perp,
    so a list of spot pairs returns {} without a request.
    """
    global _failed_at
    wanted = [s for s in symbols or [] if s.endswith("/USDT")]
    cached = _cache.get()
    if cached is not None:
        if symbols:
            return {s: cached[s] for s in wanted if s in cached}
        return cached

    if not wanted:
        return {}
    if time.monotonic() - _failed_at < _FAIL_BACKOFF_S:
        fallback = _cache.get_fallback() or {}
        return {s: fallback[s] for s in wanted if s in fallback}

    try:
        everything = await _fetch_all()
    except Exception as exc:
        _failed_at = time.monotonic()
        logger.warning("Bybit tickers unavailable (retry in %d min): %s", _FAIL_BACKOFF_S // 60, exc)
        fallback = _cache.get_fallback() or {}
        return {s: fallback[s] for s in wanted if s in fallback}

    results = {s: everything[s] for s in wanted if s in everything}
    if everything:
        _cache.put(everything)
    if results:
        logger.info("Bybit positioning: fetched %d/%d symbols", len(results), len(wanted))
    else:
        logger.info("Bybit fallback: no symbols matched from %d requested", len(wanted))
    return results
