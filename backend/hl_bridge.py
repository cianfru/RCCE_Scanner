"""
Hyperliquid Bridge Flow Tracker
================================

Monitors USDC deposits and withdrawals to/from the Hyperliquid L1 bridge
contract on Arbitrum. High inflows signal new capital arriving
(bullish for HL activity / sometimes preceding market moves), high outflows
signal capital leaving (de-risking / withdrawal cycle).

Data source: Etherscan V2 API (unified across EVM chains). Chain ID 42161.

Aggregates transfers into rolling 1h / 6h / 24h / 7d windows.

Bridge contract (Arbitrum): 0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7
Native USDC (Arbitrum):     0xaf88d065e77c8cC2239327C5EDb3A432268e5831
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from onchain.fetcher_etherscan import EtherscanFetcher, EtherscanTransfer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HL_BRIDGE_ADDRESS = "0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7".lower()
ARB_USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831".lower()
ARB_CHAIN_ID = "42161"

# Windows (seconds)
WINDOW_1H = 3600
WINDOW_6H = 6 * 3600
WINDOW_24H = 24 * 3600
WINDOW_7D = 7 * 24 * 3600

# Cache
_CACHE_TTL_S = 180  # 3 min
_cache_expires_at: float = 0.0
_cache_payload: Optional[dict] = None

# Fetcher singleton
_fetcher: Optional[EtherscanFetcher] = None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BridgeWindow:
    inflow_usd: float = 0.0
    outflow_usd: float = 0.0
    net_usd: float = 0.0
    tx_count: int = 0
    inflow_count: int = 0
    outflow_count: int = 0
    # True when our transfer sample covers this full window, False when the
    # oldest sampled transfer is newer than the window start (i.e. we're only
    # seeing a partial slice of the period).
    complete: bool = False


@dataclass
class BridgeFlowSnapshot:
    w1h: BridgeWindow = field(default_factory=BridgeWindow)
    w6h: BridgeWindow = field(default_factory=BridgeWindow)
    w24h: BridgeWindow = field(default_factory=BridgeWindow)
    w7d: BridgeWindow = field(default_factory=BridgeWindow)
    trend: str = "NEUTRAL"          # INFLOW | OUTFLOW | NEUTRAL
    signal: str = "BALANCED"        # ACCUMULATING | DEPLETING | BALANCED
    last_tx_time: int = 0
    tx_sample_size: int = 0
    sample_span_seconds: int = 0    # age of oldest tx in sample
    fetched_at: float = 0.0


# ---------------------------------------------------------------------------
# Fetcher singleton
# ---------------------------------------------------------------------------

def _get_fetcher() -> Optional[EtherscanFetcher]:
    """Return a cached EtherscanFetcher for Arbitrum, or None if no API key."""
    global _fetcher
    if _fetcher is not None:
        return _fetcher

    key = os.environ.get("ETHERSCAN_API_KEY") or os.environ.get("ARBISCAN_API_KEY")
    if not key:
        logger.warning("hl_bridge: no ETHERSCAN_API_KEY set, bridge tracker disabled")
        return None

    _fetcher = EtherscanFetcher(
        chain_id="arbitrum",
        api_base="https://api.etherscan.io/v2/api",
        api_key=key,
        etherscan_chain_id=ARB_CHAIN_ID,
    )
    return _fetcher


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(transfers: List[EtherscanTransfer], now_ts: int) -> BridgeFlowSnapshot:
    """Bucket transfers into rolling time windows relative to now.

    USDC on Arbitrum is 6 decimals; the fetcher already normalizes ``value``
    to human-readable units (so value == USD).

    Each window is tagged ``complete=True`` only if the oldest transfer in
    our sample is at least as old as the window start — otherwise the window
    is a partial slice and the frontend will show it muted.
    """
    windows = {
        WINDOW_1H: BridgeWindow(),
        WINDOW_6H: BridgeWindow(),
        WINDOW_24H: BridgeWindow(),
        WINDOW_7D: BridgeWindow(),
    }
    last_tx_time = 0
    oldest_tx_time: Optional[int] = None

    for tx in transfers:
        if tx.token_contract.lower() != ARB_USDC:
            continue
        age = now_ts - tx.timestamp
        if age < 0 or age > WINDOW_7D:
            continue
        if tx.timestamp > last_tx_time:
            last_tx_time = tx.timestamp
        if oldest_tx_time is None or tx.timestamp < oldest_tx_time:
            oldest_tx_time = tx.timestamp

        usd = float(tx.value)
        is_inflow = tx.to_addr.lower() == HL_BRIDGE_ADDRESS
        is_outflow = tx.from_addr.lower() == HL_BRIDGE_ADDRESS
        if not (is_inflow or is_outflow):
            continue

        for win_len, bucket in windows.items():
            if age <= win_len:
                bucket.tx_count += 1
                if is_inflow:
                    bucket.inflow_usd += usd
                    bucket.inflow_count += 1
                else:
                    bucket.outflow_usd += usd
                    bucket.outflow_count += 1
                bucket.net_usd = bucket.inflow_usd - bucket.outflow_usd

    # Mark each window complete only if our sample actually reaches back that far
    sample_span = (now_ts - oldest_tx_time) if oldest_tx_time else 0
    for win_len, bucket in windows.items():
        bucket.complete = sample_span >= win_len

    snap = BridgeFlowSnapshot(
        w1h=windows[WINDOW_1H],
        w6h=windows[WINDOW_6H],
        w24h=windows[WINDOW_24H],
        w7d=windows[WINDOW_7D],
        last_tx_time=last_tx_time,
        tx_sample_size=len(transfers),
    )
    snap.sample_span_seconds = sample_span

    # Trend/signal labels prefer the 24h window if we have enough sample,
    # otherwise fall back to 6h so we don't classify off a 1-hour blip.
    decision = snap.w24h if snap.w24h.complete else snap.w6h
    gross = decision.inflow_usd + decision.outflow_usd
    if gross <= 0:
        snap.trend = "NEUTRAL"
        snap.signal = "BALANCED"
    else:
        net_pct = decision.net_usd / gross  # -1..+1
        if net_pct >= 0.25:
            snap.trend = "INFLOW"
            # Strong inflow with meaningful volume → ACCUMULATING
            snap.signal = "ACCUMULATING" if decision.inflow_usd >= 5_000_000 else "BALANCED"
        elif net_pct <= -0.25:
            snap.trend = "OUTFLOW"
            snap.signal = "DEPLETING" if decision.outflow_usd >= 5_000_000 else "BALANCED"
        else:
            snap.trend = "NEUTRAL"
            snap.signal = "BALANCED"

    return snap


def _snapshot_to_dict(snap: BridgeFlowSnapshot) -> dict:
    def _w(b: BridgeWindow) -> dict:
        return {
            "inflow_usd": round(b.inflow_usd, 2),
            "outflow_usd": round(b.outflow_usd, 2),
            "net_usd": round(b.net_usd, 2),
            "tx_count": b.tx_count,
            "inflow_count": b.inflow_count,
            "outflow_count": b.outflow_count,
            "complete": b.complete,
        }
    return {
        "bridge_address": HL_BRIDGE_ADDRESS,
        "chain": "arbitrum",
        "token": "USDC",
        "trend": snap.trend,
        "signal": snap.signal,
        "last_tx_time": snap.last_tx_time,
        "tx_sample_size": snap.tx_sample_size,
        "sample_span_seconds": snap.sample_span_seconds,
        "fetched_at": snap.fetched_at,
        "w1h": _w(snap.w1h),
        "w6h": _w(snap.w6h),
        "w24h": _w(snap.w24h),
        "w7d": _w(snap.w7d),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_bridge_flow(force_refresh: bool = False) -> Optional[dict]:
    """Return cached bridge flow snapshot as a dict, or None if disabled."""
    global _cache_expires_at, _cache_payload

    now = time.time()
    if not force_refresh and _cache_payload is not None and _cache_expires_at > now:
        return _cache_payload

    fetcher = _get_fetcher()
    if fetcher is None:
        return None

    # Pull a generous sample — the HL bridge runs ~300 USDC tx/hour during
    # active periods, so 5000 gives us roughly 16h minimum and usually more
    # than 24h. Etherscan V2 tokentx caps at 10000 per call.
    try:
        transfers = await asyncio.wait_for(
            fetcher.get_address_transfers(
                address=HL_BRIDGE_ADDRESS,
                contract=ARB_USDC,
                offset=5000,
            ),
            timeout=25.0,
        )
    except asyncio.TimeoutError:
        logger.warning("hl_bridge: arbiscan timeout")
        return _cache_payload  # serve stale on timeout
    except Exception as exc:
        logger.warning("hl_bridge: fetch failed: %s", exc)
        return _cache_payload

    if not transfers:
        logger.warning("hl_bridge: empty transfer list from arbiscan")
        # Still emit an empty snapshot so the UI can show "no data"
        snap = BridgeFlowSnapshot()
        snap.fetched_at = now
        payload = _snapshot_to_dict(snap)
        _cache_payload = payload
        _cache_expires_at = now + _CACHE_TTL_S
        return payload

    snap = _aggregate(transfers, int(now))
    snap.fetched_at = now
    payload = _snapshot_to_dict(snap)
    _cache_payload = payload
    _cache_expires_at = now + _CACHE_TTL_S
    span_h = snap.sample_span_seconds / 3600.0 if snap.sample_span_seconds else 0.0
    logger.info(
        "hl_bridge: sampled %d txs (%.1fh span), 24h net=$%s, trend=%s, 24h_complete=%s",
        len(transfers), span_h,
        f"{snap.w24h.net_usd:,.0f}",
        snap.trend,
        snap.w24h.complete,
    )
    return payload


async def close_fetcher() -> None:
    """Close the shared EtherscanFetcher session (call on app shutdown)."""
    global _fetcher
    if _fetcher is not None:
        try:
            await _fetcher.close()
        except Exception:
            pass
        _fetcher = None
