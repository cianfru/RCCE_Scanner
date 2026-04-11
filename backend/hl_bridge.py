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
    """
    windows = {
        WINDOW_1H: BridgeWindow(),
        WINDOW_6H: BridgeWindow(),
        WINDOW_24H: BridgeWindow(),
        WINDOW_7D: BridgeWindow(),
    }
    last_tx_time = 0

    for tx in transfers:
        if tx.token_contract.lower() != ARB_USDC:
            continue
        age = now_ts - tx.timestamp
        if age < 0 or age > WINDOW_7D:
            continue
        if tx.timestamp > last_tx_time:
            last_tx_time = tx.timestamp

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

    snap = BridgeFlowSnapshot(
        w1h=windows[WINDOW_1H],
        w6h=windows[WINDOW_6H],
        w24h=windows[WINDOW_24H],
        w7d=windows[WINDOW_7D],
        last_tx_time=last_tx_time,
        tx_sample_size=len(transfers),
    )

    # Trend/signal labels keyed off the 24h window
    w24 = snap.w24h
    gross = w24.inflow_usd + w24.outflow_usd
    if gross <= 0:
        snap.trend = "NEUTRAL"
        snap.signal = "BALANCED"
    else:
        net_pct = w24.net_usd / gross  # -1..+1
        if net_pct >= 0.25:
            snap.trend = "INFLOW"
            # Strong inflow with meaningful volume → ACCUMULATING
            snap.signal = "ACCUMULATING" if w24.inflow_usd >= 5_000_000 else "BALANCED"
        elif net_pct <= -0.25:
            snap.trend = "OUTFLOW"
            snap.signal = "DEPLETING" if w24.outflow_usd >= 5_000_000 else "BALANCED"
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
        }
    return {
        "bridge_address": HL_BRIDGE_ADDRESS,
        "chain": "arbitrum",
        "token": "USDC",
        "trend": snap.trend,
        "signal": snap.signal,
        "last_tx_time": snap.last_tx_time,
        "tx_sample_size": snap.tx_sample_size,
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

    # Pull the most recent 300 transfers for the bridge address + USDC. That's
    # usually several hours of activity for a busy bridge.
    try:
        transfers = await asyncio.wait_for(
            fetcher.get_address_transfers(
                address=HL_BRIDGE_ADDRESS,
                contract=ARB_USDC,
                offset=300,
            ),
            timeout=15.0,
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
    logger.info(
        "hl_bridge: sampled %d txs, 24h net=$%s, trend=%s",
        len(transfers),
        f"{snap.w24h.net_usd:,.0f}",
        snap.trend,
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
