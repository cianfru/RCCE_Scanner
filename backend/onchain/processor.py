"""
On-chain data processor — pure functions that classify transfers,
build holder maps, detect accumulation / distribution, and surface
trending tokens.

No I/O in this file — everything operates on in-memory data.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from .config import (
    ACCUMULATION_MIN_BUYS,
    ACCUMULATION_WINDOW,
    DISTRIBUTION_MIN_SELLS,
    LARGE_TX_USD,
    TRENDING_LOOKBACK_HOURS,
    TRENDING_MIN_WHALE_WALLETS,
    WHALE_HOLDING_PCT,
    WHALE_HOLDING_USD,
)

# Burn / zero addresses to ignore
_ZERO_ADDRS = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
    "11111111111111111111111111111111",
}


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class HolderInfo:
    address: str
    label: str
    balance: float
    buy_count: int
    sell_count: int
    net_flow: float          # positive = net buyer
    last_seen: int           # timestamp
    tx_count_24h: int = 0
    net_flow_24h: float = 0.0
    pct_supply: float = 0.0  # % of total supply held
    is_whale: bool = False


@dataclass
class Alert:
    chain: str
    contract: str
    token_symbol: str
    address: str
    label: str
    alert_type: str          # ACCUMULATING | DISTRIBUTING | NEW_WHALE | LARGE_BUY | LARGE_SELL
    value_usd: float
    details: str
    timestamp: float


@dataclass
class TrendingToken:
    chain: str
    contract: str
    symbol: str
    name: str
    whale_tx_count: int
    whale_volume_usd: float
    top_buyer: str
    detected_at: float


# ---------------------------------------------------------------------------
# Transfer classification
# ---------------------------------------------------------------------------

def classify_direction(
    from_addr: str,
    to_addr: str,
    known_dex_routers: Optional[set] = None,
) -> str:
    """Classify a transfer as BUY, SELL, or TRANSFER.

    Heuristic:
    - From a zero/burn address → mint / airdrop → treat as BUY
    - To a zero/burn address → burn → treat as SELL
    - If we know DEX router addresses, from_router = BUY, to_router = SELL
    - Otherwise: TRANSFER (neutral wallet-to-wallet move)
    """
    if from_addr in _ZERO_ADDRS:
        return "BUY"
    if to_addr in _ZERO_ADDRS:
        return "SELL"
    if known_dex_routers:
        if from_addr in known_dex_routers:
            return "BUY"
        if to_addr in known_dex_routers:
            return "SELL"
    return "TRANSFER"


# ---------------------------------------------------------------------------
# Holder map construction
# ---------------------------------------------------------------------------

def build_holder_map(
    transfers: list,
    labels: Dict[str, str],
    token_price_usd: float = 0.0,
    total_supply: float = 0.0,
) -> Dict[str, HolderInfo]:
    """Reconstruct holder balances and activity from transfer history.

    Works for ETH/Base where free-tier Etherscan doesn't provide holder lists.
    For Solana, prefer the native holder endpoint and use this only for
    enrichment with activity data.

    Args:
        transfers: list of transfer records (EtherscanTransfer or SolscanTransfer)
        labels: {address: label} lookup
        token_price_usd: current token price for whale classification
        total_supply: token total supply for %-based whale classification
    """
    holders: Dict[str, HolderInfo] = {}
    now = int(time.time())
    cutoff_24h = now - 86400

    for tx in transfers:
        from_addr = tx.from_addr
        to_addr = tx.to_addr
        value = tx.value
        ts = tx.timestamp

        # --- TO address (receiver / buyer) ---
        if to_addr and to_addr not in _ZERO_ADDRS:
            if to_addr not in holders:
                holders[to_addr] = HolderInfo(
                    address=to_addr,
                    label=labels.get(to_addr, ""),
                    balance=0.0,
                    buy_count=0,
                    sell_count=0,
                    net_flow=0.0,
                    last_seen=ts,
                )
            h = holders[to_addr]
            h.balance += value
            h.buy_count += 1
            h.net_flow += value
            h.last_seen = max(h.last_seen, ts)
            if ts >= cutoff_24h:
                h.tx_count_24h += 1
                h.net_flow_24h += value

        # --- FROM address (sender / seller) ---
        if from_addr and from_addr not in _ZERO_ADDRS:
            if from_addr not in holders:
                holders[from_addr] = HolderInfo(
                    address=from_addr,
                    label=labels.get(from_addr, ""),
                    balance=0.0,
                    buy_count=0,
                    sell_count=0,
                    net_flow=0.0,
                    last_seen=ts,
                )
            h = holders[from_addr]
            h.balance -= value
            h.sell_count += 1
            h.net_flow -= value
            h.last_seen = max(h.last_seen, ts)
            if ts >= cutoff_24h:
                h.tx_count_24h += 1
                h.net_flow_24h -= value

    # Compute supply percentage and classify whales
    for h in holders.values():
        if total_supply > 0:
            h.pct_supply = abs(h.balance) / total_supply * 100
            h.is_whale = h.pct_supply >= WHALE_HOLDING_PCT
        elif token_price_usd > 0:
            # Fallback: USD-based when supply is unknown
            holding_usd = abs(h.balance) * token_price_usd
            h.is_whale = holding_usd >= WHALE_HOLDING_USD

    return holders


# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------

def generate_alerts(
    holders: Dict[str, HolderInfo],
    chain: str,
    contract: str,
    token_symbol: str,
    token_price_usd: float = 0.0,
    transfers: Optional[list] = None,
) -> List[Alert]:
    """Detect accumulation, distribution, new whales, and large transactions."""
    alerts: List[Alert] = []
    now = time.time()

    # --- Per-holder pattern alerts ---
    for addr, h in holders.items():
        total_txns = h.buy_count + h.sell_count
        if total_txns < 3:
            continue

        # Accumulation: heavily buying
        recent_window = min(total_txns, ACCUMULATION_WINDOW)
        if h.buy_count >= ACCUMULATION_MIN_BUYS and h.net_flow > 0:
            buy_ratio = h.buy_count / max(total_txns, 1)
            if buy_ratio >= 0.6:
                alerts.append(Alert(
                    chain=chain,
                    contract=contract,
                    token_symbol=token_symbol,
                    address=addr,
                    label=h.label,
                    alert_type="ACCUMULATING",
                    value_usd=abs(h.net_flow) * token_price_usd,
                    details=f"{h.buy_count} buys / {h.sell_count} sells, net +{h.net_flow:,.0f} tokens",
                    timestamp=now,
                ))

        # Distribution: heavily selling
        if h.sell_count >= DISTRIBUTION_MIN_SELLS and h.net_flow < 0:
            sell_ratio = h.sell_count / max(total_txns, 1)
            if sell_ratio >= 0.6:
                alerts.append(Alert(
                    chain=chain,
                    contract=contract,
                    token_symbol=token_symbol,
                    address=addr,
                    label=h.label,
                    alert_type="DISTRIBUTING",
                    value_usd=abs(h.net_flow) * token_price_usd,
                    details=f"{h.sell_count} sells / {h.buy_count} buys, net {h.net_flow:,.0f} tokens",
                    timestamp=now,
                ))

    # --- Large transaction alerts ---
    if transfers and token_price_usd > 0:
        cutoff = int(now) - 3600  # last hour
        for tx in transfers:
            if tx.timestamp < cutoff:
                continue
            usd_value = tx.value * token_price_usd
            if usd_value >= LARGE_TX_USD:
                from_label = holders.get(tx.from_addr, HolderInfo(
                    address=tx.from_addr, label="", balance=0, buy_count=0,
                    sell_count=0, net_flow=0, last_seen=0,
                )).label
                to_label = holders.get(tx.to_addr, HolderInfo(
                    address=tx.to_addr, label="", balance=0, buy_count=0,
                    sell_count=0, net_flow=0, last_seen=0,
                )).label

                direction = classify_direction(tx.from_addr, tx.to_addr)
                alert_type = "LARGE_BUY" if direction == "BUY" else "LARGE_SELL" if direction == "SELL" else "LARGE_BUY"
                addr = tx.to_addr if direction == "BUY" else tx.from_addr
                label = to_label if direction == "BUY" else from_label

                alerts.append(Alert(
                    chain=chain,
                    contract=contract,
                    token_symbol=token_symbol,
                    address=addr,
                    label=label,
                    alert_type=alert_type,
                    value_usd=usd_value,
                    details=f"${usd_value:,.0f} ({tx.value:,.0f} tokens)",
                    timestamp=tx.timestamp,
                ))

    return alerts


# ---------------------------------------------------------------------------
# Trending detection
# ---------------------------------------------------------------------------

def detect_trending(
    all_transfers: Dict[str, list],
    known_whale_addrs: set,
    token_metas: Dict[str, dict],
) -> List[TrendingToken]:
    """Surface tokens with unusual known-whale activity.

    Args:
        all_transfers: {contract: [transfers]} across all tracked tokens
        known_whale_addrs: set of addresses known to be whales
        token_metas: {contract: {chain, symbol, name}} metadata lookup
    """
    now = time.time()
    cutoff = now - TRENDING_LOOKBACK_HOURS * 3600
    trending: List[TrendingToken] = []

    for contract, transfers in all_transfers.items():
        # Count distinct whale wallets active in lookback window
        whale_wallets: Dict[str, float] = defaultdict(float)
        total_whale_volume = 0.0

        for tx in transfers:
            if tx.timestamp < cutoff:
                continue
            for addr in (tx.from_addr, tx.to_addr):
                if addr in known_whale_addrs:
                    whale_wallets[addr] += tx.value
                    total_whale_volume += tx.value

        if len(whale_wallets) >= TRENDING_MIN_WHALE_WALLETS:
            meta = token_metas.get(contract, {})
            top_buyer = max(whale_wallets, key=whale_wallets.get) if whale_wallets else ""
            trending.append(TrendingToken(
                chain=meta.get("chain", ""),
                contract=contract,
                symbol=meta.get("symbol", ""),
                name=meta.get("name", ""),
                whale_tx_count=sum(1 for _ in whale_wallets),
                whale_volume_usd=total_whale_volume,
                top_buyer=top_buyer,
                detected_at=now,
            ))

    # Sort by whale volume descending
    trending.sort(key=lambda t: t.whale_volume_usd, reverse=True)
    return trending
