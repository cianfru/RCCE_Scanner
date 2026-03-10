"""
WhaleTracker — orchestrator that combines fetchers, processor, and store
into a single interface for periodic polling and on-demand queries.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import aiohttp

from .config import (
    CHAINS,
    COINGECKO_PRICE_URL,
    MAX_ALERTS,
    MAX_TRANSFERS_PER_TOKEN,
    MAX_TRENDING,
    PRICE_CACHE_TTL,
    WHALE_HOLDING_PCT,
)
from .fetcher_etherscan import EtherscanFetcher, EtherscanTransfer
from .fetcher_solscan import SolscanFetcher, SolscanTransfer
from .processor import (
    Alert,
    HolderInfo,
    TrendingToken,
    build_holder_map,
    classify_direction,
    detect_trending,
    generate_alerts,
)
from .store import WhaleStoreManager

logger = logging.getLogger(__name__)


class WhaleTracker:
    """Central orchestrator for on-chain whale tracking."""

    def __init__(self) -> None:
        self.store = WhaleStoreManager.get()
        self._fetchers: Dict[str, Any] = {}          # chain_id -> fetcher
        self._active_chains: List[str] = []

        # In-memory caches (not persisted — rebuilt on each poll)
        self._transfer_cache: Dict[str, list] = {}   # contract -> recent transfers
        self._holder_cache: Dict[str, Dict[str, HolderInfo]] = {}  # contract -> holder map
        self._alerts: List[Alert] = []
        self._trending: List[TrendingToken] = []

        # Price cache for USD estimation
        self._price_cache: Dict[str, float] = {}     # "symbol" -> usd price
        self._price_cache_ts: float = 0.0

        # Poll tracking
        self.last_poll: Optional[float] = None
        self._last_holder_poll: float = 0.0
        self._initialized = False

    # ── Initialization ─────────────────────────────────────────────────────

    def init_fetchers(self) -> Dict[str, bool]:
        """Create fetchers for chains where API keys are configured.

        Returns {chain_id: is_available}.
        """
        available: Dict[str, bool] = {}
        for chain_id, cfg in CHAINS.items():
            key = os.environ.get(cfg["api_key_env"], "")
            if not key:
                logger.warning(
                    "%s API key not set (%s) — %s whale data unavailable",
                    cfg["name"], cfg["api_key_env"], cfg["name"],
                )
                available[chain_id] = False
                continue

            if cfg["api_type"] == "etherscan":
                self._fetchers[chain_id] = EtherscanFetcher(
                    chain_id, cfg["api_base"], key,
                    etherscan_chain_id=cfg.get("chain_id", "1"),
                )
            elif cfg["api_type"] == "solscan":
                self._fetchers[chain_id] = SolscanFetcher(key)

            available[chain_id] = True
            logger.info("%s whale tracking enabled", cfg["name"])

        self._active_chains = [c for c, ok in available.items() if ok]
        self._initialized = True
        return available

    async def shutdown(self) -> None:
        """Close all fetcher sessions."""
        for fetcher in self._fetchers.values():
            try:
                await fetcher.close()
            except Exception:
                pass

    # ── Price estimation ───────────────────────────────────────────────────

    async def _refresh_prices(self, symbols: List[str]) -> None:
        """Fetch USD prices from CoinGecko for symbol list (best-effort)."""
        if time.time() - self._price_cache_ts < PRICE_CACHE_TTL:
            return
        if not symbols:
            return

        # CoinGecko wants lowercase IDs; we do a naive mapping
        # For unlisted tokens this will miss — price stays 0
        ids = ",".join(s.lower() for s in symbols[:25])
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    COINGECKO_PRICE_URL,
                    params={"ids": ids, "vs_currencies": "usd"},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for coin_id, prices in data.items():
                            if "usd" in prices:
                                self._price_cache[coin_id.upper()] = prices["usd"]
                        self._price_cache_ts = time.time()
        except Exception as exc:
            logger.debug("Price fetch failed (non-critical): %s", exc)

    def _get_price(self, symbol: str) -> float:
        """Get cached USD price for a token symbol."""
        return self._price_cache.get(symbol.upper(), 0.0)

    # ── Token management ───────────────────────────────────────────────────

    async def add_token(self, chain: str, contract: str) -> Optional[dict]:
        """Add a token to track. Resolves metadata and does initial fetch."""
        if chain not in self._fetchers:
            logger.warning("Cannot add token — %s fetcher not available", chain)
            return None

        fetcher = self._fetchers[chain]
        meta = None

        # Resolve metadata
        try:
            if isinstance(fetcher, EtherscanFetcher):
                info = await fetcher.get_token_info(contract)
                if info:
                    meta = {
                        "symbol": info.symbol,
                        "name": info.name,
                        "decimals": info.decimals,
                        "total_supply": info.total_supply,
                    }
            elif isinstance(fetcher, SolscanFetcher):
                info = await fetcher.get_token_meta(contract)
                if info:
                    meta = {
                        "symbol": info.symbol,
                        "name": info.name,
                        "decimals": info.decimals,
                        "total_supply": getattr(info, "total_supply", 0.0),
                    }
        except Exception as exc:
            logger.warning("Failed to resolve token metadata for %s: %s", contract, exc)

        if meta is None:
            meta = {"symbol": "", "name": "", "decimals": 18, "total_supply": 0.0}

        record = self.store.add_token(
            chain=chain,
            contract=contract,
            symbol=meta["symbol"],
            name=meta["name"],
            decimals=meta["decimals"],
            total_supply=meta.get("total_supply", 0.0),
        )

        # Do an initial fetch of transfers
        try:
            await self._poll_single_token(chain, contract)
        except Exception as exc:
            logger.warning("Initial transfer fetch failed for %s: %s", contract, exc)

        return asdict(record)

    def remove_token(self, chain: str, contract: str) -> bool:
        """Stop tracking a token."""
        contract_key = contract.lower() if chain != "solana" else contract
        self._transfer_cache.pop(contract_key, None)
        self._holder_cache.pop(contract_key, None)
        return self.store.remove_token(chain, contract)

    # ── Polling ────────────────────────────────────────────────────────────

    async def _poll_single_token(self, chain: str, contract: str) -> None:
        """Fetch transfers for one token and update caches."""
        fetcher = self._fetchers.get(chain)
        if not fetcher:
            return

        contract_key = contract.lower() if chain != "solana" else contract
        start_block = self.store.get_last_block(chain, contract)

        transfers: list = []
        try:
            if isinstance(fetcher, EtherscanFetcher):
                transfers = await fetcher.get_token_transfers(
                    contract, start_block=start_block, offset=200,
                )
            elif isinstance(fetcher, SolscanFetcher):
                transfers = await fetcher.get_token_transfers(
                    contract, page_size=40,
                )
        except Exception as exc:
            logger.warning("Transfer fetch failed for %s/%s: %s", chain, contract[:12], exc)
            return

        if not transfers:
            return

        # Update block cursor (highest block seen)
        max_block = max(t.block_number for t in transfers)
        if max_block > start_block:
            self.store.set_last_block(chain, contract, max_block)

        # Merge into cache (dedup by tx_hash)
        existing = self._transfer_cache.get(contract_key, [])
        seen_hashes = {t.tx_hash for t in existing}
        for t in transfers:
            if t.tx_hash not in seen_hashes:
                existing.append(t)
                seen_hashes.add(t.tx_hash)

        # Sort by timestamp desc, cap size
        existing.sort(key=lambda t: t.timestamp, reverse=True)
        self._transfer_cache[contract_key] = existing[:MAX_TRANSFERS_PER_TOKEN]

        # Rebuild holder map from cached transfers
        labels = self.store.wallet_labels.get(chain, {})
        token_record = next(
            (t for t in self.store.tracked_tokens
             if t.chain == chain and
             (t.contract.lower() if t.chain != "solana" else t.contract) == contract_key),
            None,
        )
        token_symbol = token_record.symbol if token_record else ""
        token_price = self._get_price(token_symbol)

        total_supply = token_record.total_supply if token_record else 0.0
        holder_map = build_holder_map(
            self._transfer_cache[contract_key],
            labels,
            token_price,
            total_supply,
        )
        self._holder_cache[contract_key] = holder_map

        # Generate alerts
        new_alerts = generate_alerts(
            holder_map, chain, contract, token_symbol, token_price,
            transfers=self._transfer_cache[contract_key],
        )
        if new_alerts:
            self._alerts = (new_alerts + self._alerts)[:MAX_ALERTS]

    async def poll_all(self) -> None:
        """Poll all tracked tokens across all active chains."""
        tokens = self.store.get_tracked_tokens()
        if not tokens:
            self.last_poll = time.time()
            return

        # Refresh prices for tracked token symbols
        symbols = list({t.symbol for t in tokens if t.symbol})
        await self._refresh_prices(symbols)

        # Poll each token (sequentially per chain to respect rate limits)
        for token in tokens:
            if token.chain not in self._fetchers:
                continue
            try:
                await self._poll_single_token(token.chain, token.contract)
            except Exception as exc:
                logger.warning(
                    "Poll failed for %s/%s: %s",
                    token.chain, token.symbol or token.contract[:12], exc,
                )
            # Small delay between tokens to avoid rate limit bursts
            await asyncio.sleep(0.3)

        # Auto-enrich: try fetching supply for tokens that are missing it
        await self._enrich_missing_supply(tokens)

        self.last_poll = time.time()

    async def _enrich_missing_supply(self, tokens: list) -> None:
        """Try to fetch total_supply for tokens where it's still 0.

        This runs after each poll cycle so that tokens whose supply wasn't
        available on initial add eventually get enriched automatically.
        """
        for token in tokens:
            if token.total_supply > 0:
                continue  # Already have supply data
            fetcher = self._fetchers.get(token.chain)
            if not fetcher:
                continue

            try:
                supply = 0.0
                if isinstance(fetcher, EtherscanFetcher):
                    # Use the fast tokensupply endpoint
                    supply = await fetcher.get_token_supply(
                        token.contract, token.decimals
                    )
                elif isinstance(fetcher, SolscanFetcher):
                    info = await fetcher.get_token_meta(token.contract)
                    if info:
                        supply = info.total_supply

                if supply > 0:
                    logger.info(
                        "Auto-enriched total_supply for %s/%s: %s",
                        token.chain, token.symbol or token.contract[:12], supply,
                    )
                    self.store.add_token(
                        chain=token.chain,
                        contract=token.contract,
                        total_supply=supply,
                    )
                    # Update in-memory token record
                    token.total_supply = supply
                    # Rebuild holder map with new supply
                    contract_key = (
                        token.contract.lower()
                        if token.chain != "solana"
                        else token.contract
                    )
                    if contract_key in self._holder_cache:
                        labels = self.store.wallet_labels.get(token.chain, {})
                        price = self._get_price(token.symbol)
                        self._holder_cache[contract_key] = build_holder_map(
                            self._transfer_cache.get(contract_key, []),
                            labels,
                            price,
                            supply,
                        )
            except Exception as exc:
                logger.debug(
                    "Supply enrichment failed for %s/%s: %s",
                    token.chain, token.contract[:12], exc,
                )
            await asyncio.sleep(0.2)

    async def poll_holders_solana(self) -> None:
        """Fetch native holder lists for Solana tokens (free tier supported)."""
        fetcher = self._fetchers.get("solana")
        if not isinstance(fetcher, SolscanFetcher):
            return

        tokens = self.store.get_tracked_tokens("solana")
        labels = self.store.wallet_labels.get("solana", {})

        for token in tokens:
            try:
                holders = await fetcher.get_token_holders(token.contract, page_size=40)
                if holders:
                    token_price = self._get_price(token.symbol)
                    contract_key = token.contract
                    total_supply = token.total_supply
                    # Merge with existing holder map
                    existing = self._holder_cache.get(contract_key, {})
                    for h in holders:
                        if h.address not in existing:
                            existing[h.address] = HolderInfo(
                                address=h.address,
                                label=labels.get(h.address, ""),
                                balance=h.amount,
                                buy_count=0, sell_count=0, net_flow=0.0,
                                last_seen=int(time.time()),
                            )
                        else:
                            existing[h.address].balance = h.amount
                        # Supply % and whale classification
                        if total_supply > 0:
                            existing[h.address].pct_supply = (
                                h.amount / total_supply * 100
                            )
                            existing[h.address].is_whale = (
                                existing[h.address].pct_supply >= WHALE_HOLDING_PCT
                            )
                        elif token_price > 0:
                            existing[h.address].is_whale = (
                                h.amount * token_price >= 100_000
                            )
                    self._holder_cache[contract_key] = existing
            except Exception as exc:
                logger.warning("Solana holder fetch failed for %s: %s", token.symbol, exc)
            await asyncio.sleep(0.3)

        self._last_holder_poll = time.time()

    async def poll_trending(self) -> None:
        """Detect tokens with unusual whale activity."""
        known_addrs: set = set()
        for chain_labels in self.store.wallet_labels.values():
            known_addrs.update(chain_labels.keys())

        token_metas: Dict[str, dict] = {}
        for t in self.store.tracked_tokens:
            key = t.contract.lower() if t.chain != "solana" else t.contract
            token_metas[key] = {
                "chain": t.chain,
                "symbol": t.symbol,
                "name": t.name,
            }

        self._trending = detect_trending(
            self._transfer_cache,
            known_addrs,
            token_metas,
        )[:MAX_TRENDING]

    # ── Query interface ────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "active_chains": list(self._active_chains),
            "tracked_token_count": len(self.store.tracked_tokens),
            "transfer_count": sum(len(v) for v in self._transfer_cache.values()),
            "alert_count": len(self._alerts),
            "last_poll": self.last_poll,
        }

    def get_transfers(
        self,
        chain: Optional[str] = None,
        contract: Optional[str] = None,
        limit: int = 50,
    ) -> list:
        """Get recent transfers, optionally filtered."""
        if contract:
            key = contract.lower() if chain != "solana" else contract
            transfers = self._transfer_cache.get(key, [])
        else:
            transfers = []
            for txs in self._transfer_cache.values():
                transfers.extend(txs)
            transfers.sort(key=lambda t: t.timestamp, reverse=True)

        if chain:
            transfers = [t for t in transfers if t.chain == chain]

        result = []
        labels_all = self.store.wallet_labels
        for t in transfers[:limit]:
            chain_labels = labels_all.get(t.chain, {})
            result.append({
                "tx_hash": t.tx_hash,
                "chain": t.chain,
                "token_symbol": t.token_symbol,
                "token_contract": t.token_contract,
                "from_addr": t.from_addr,
                "to_addr": t.to_addr,
                "from_label": chain_labels.get(t.from_addr, ""),
                "to_label": chain_labels.get(t.to_addr, ""),
                "value": t.value,
                "value_usd": t.value * self._get_price(t.token_symbol),
                "timestamp": t.timestamp,
                "direction": classify_direction(t.from_addr, t.to_addr),
            })
        return result

    def get_holders(
        self,
        chain: str,
        contract: str,
        limit: int = 40,
        min_pct: float = 0.0,
    ) -> list:
        """Get holder map for a specific token.

        Args:
            min_pct: minimum % of total supply to include (e.g. 0.4 for whales)
        """
        key = contract.lower() if chain != "solana" else contract
        holder_map = self._holder_cache.get(key, {})

        token_record = next(
            (t for t in self.store.tracked_tokens
             if t.chain == chain and
             (t.contract.lower() if t.chain != "solana" else t.contract) == key),
            None,
        )
        token_symbol = token_record.symbol if token_record else ""
        total_supply = token_record.total_supply if token_record else 0.0
        price = self._get_price(token_symbol)

        # Filter and sort holders
        filtered = [
            h for h in holder_map.values()
            if abs(h.balance) > 0
            and (h.pct_supply >= min_pct if total_supply > 0 and min_pct > 0 else True)
        ]
        filtered.sort(key=lambda h: abs(h.balance), reverse=True)

        return {
            "holders": [
                {
                    "address": h.address,
                    "label": h.label,
                    "balance": h.balance,
                    "pct_supply": h.pct_supply,
                    "net_flow": h.net_flow,
                    "net_flow_24h": h.net_flow_24h,
                    "tx_count_24h": h.tx_count_24h,
                    "buy_count": h.buy_count,
                    "sell_count": h.sell_count,
                    "is_whale": h.is_whale,
                    "last_seen": h.last_seen,
                    "balance_usd": h.balance * price if price > 0 else 0.0,
                }
                for h in filtered[:limit]
            ],
            "total_supply": total_supply,
            "whale_threshold_pct": min_pct if min_pct > 0 else 0.4,
        }

    def get_alerts(
        self,
        chain: Optional[str] = None,
        contract: Optional[str] = None,
        limit: int = 20,
    ) -> list:
        alerts = self._alerts
        if chain:
            alerts = [a for a in alerts if a.chain == chain]
        if contract:
            contract_key = contract.lower()
            alerts = [
                a for a in alerts
                if a.contract.lower() == contract_key
            ]
        return [
            {
                "chain": a.chain,
                "contract": a.contract,
                "token_symbol": a.token_symbol,
                "address": a.address,
                "label": a.label,
                "alert_type": a.alert_type,
                "value_usd": a.value_usd,
                "details": a.details,
                "timestamp": a.timestamp,
            }
            for a in alerts[:limit]
        ]

    def get_trending(self) -> list:
        return [
            {
                "chain": t.chain,
                "contract": t.contract,
                "symbol": t.symbol,
                "name": t.name,
                "whale_tx_count": t.whale_tx_count,
                "whale_volume_usd": t.whale_volume_usd,
                "top_buyer": t.top_buyer,
                "detected_at": t.detected_at,
            }
            for t in self._trending
        ]

    # ── Cross-token wallet intelligence ──────────────────────────────────

    def get_wallet_activity(
        self,
        chain: str,
        address: str,
        limit: int = 50,
    ) -> dict:
        """Get a wallet's activity across ALL tracked tokens on this chain."""
        addr_key = address.lower() if chain != "solana" else address
        labels = self.store.wallet_labels.get(chain, {})

        # 1. Per-token holdings and activity
        token_activity = []
        for token in self.store.get_tracked_tokens(chain):
            contract_key = (
                token.contract.lower() if chain != "solana" else token.contract
            )
            holder_map = self._holder_cache.get(contract_key, {})
            holder = holder_map.get(addr_key)

            if holder and abs(holder.balance) > 0:
                price = self._get_price(token.symbol)
                total_supply = token.total_supply
                pct = (
                    abs(holder.balance) / total_supply * 100
                    if total_supply > 0
                    else 0.0
                )

                # Classify activity pattern
                total_txns = holder.buy_count + holder.sell_count
                if total_txns == 0:
                    activity = "INACTIVE"
                elif holder.buy_count > 0 and holder.sell_count == 0:
                    activity = "ACCUMULATING"
                elif holder.sell_count > 0 and holder.buy_count == 0:
                    activity = "DISTRIBUTING"
                elif holder.buy_count > holder.sell_count * 1.5:
                    activity = "ACCUMULATING"
                elif holder.sell_count > holder.buy_count * 1.5:
                    activity = "DISTRIBUTING"
                else:
                    activity = "MIXED"

                token_activity.append({
                    "chain": chain,
                    "contract": token.contract,
                    "symbol": token.symbol,
                    "name": token.name,
                    "balance": holder.balance,
                    "pct_supply": pct,
                    "balance_usd": holder.balance * price if price > 0 else 0.0,
                    "buy_count": holder.buy_count,
                    "sell_count": holder.sell_count,
                    "net_flow": holder.net_flow,
                    "net_flow_24h": holder.net_flow_24h,
                    "tx_count_24h": holder.tx_count_24h,
                    "activity": activity,
                    "last_seen": holder.last_seen,
                    "is_whale": holder.is_whale,
                })

        # 2. Recent transfers across all tokens
        all_transfers = []
        for token in self.store.get_tracked_tokens(chain):
            contract_key = (
                token.contract.lower() if chain != "solana" else token.contract
            )
            transfers = self._transfer_cache.get(contract_key, [])
            for t in transfers:
                if t.from_addr == addr_key or t.to_addr == addr_key:
                    all_transfers.append(t)

        all_transfers.sort(key=lambda t: t.timestamp, reverse=True)

        # 3. Format transfers
        formatted_transfers = []
        for t in all_transfers[:limit]:
            formatted_transfers.append({
                "tx_hash": t.tx_hash,
                "chain": t.chain,
                "token_symbol": t.token_symbol,
                "token_contract": t.token_contract,
                "from_addr": t.from_addr,
                "to_addr": t.to_addr,
                "from_label": labels.get(t.from_addr, ""),
                "to_label": labels.get(t.to_addr, ""),
                "value": t.value,
                "value_usd": t.value * self._get_price(t.token_symbol),
                "timestamp": t.timestamp,
                "direction": classify_direction(t.from_addr, t.to_addr),
            })

        return {
            "address": address,
            "chain": chain,
            "label": self.store.get_wallet_label(chain, address),
            "token_activity": token_activity,
            "recent_transfers": formatted_transfers,
        }

    async def refresh_token_supply(
        self, chain: str, contract: str
    ) -> float:
        """Re-fetch total_supply for a token and update store."""
        fetcher = self._fetchers.get(chain)
        if not fetcher:
            return 0.0

        # Look up decimals from the tracked token record
        token_record = next(
            (t for t in self.store.tracked_tokens
             if t.chain == chain and
             (t.contract.lower() if t.chain != "solana" else t.contract)
             == (contract.lower() if chain != "solana" else contract)),
            None,
        )
        decimals = token_record.decimals if token_record else 18

        total_supply = 0.0
        try:
            if isinstance(fetcher, EtherscanFetcher):
                # Use the fast dedicated tokensupply endpoint
                total_supply = await fetcher.get_token_supply(contract, decimals)
                # Fall back to full get_token_info if tokensupply returned 0
                if total_supply == 0:
                    info = await fetcher.get_token_info(contract)
                    if info:
                        total_supply = info.total_supply
            elif isinstance(fetcher, SolscanFetcher):
                info = await fetcher.get_token_meta(contract)
                if info:
                    total_supply = info.total_supply
        except Exception as exc:
            logger.warning("Supply refresh failed for %s: %s", contract[:12], exc)

        if total_supply > 0:
            # Update store
            self.store.add_token(
                chain=chain,
                contract=contract,
                total_supply=total_supply,
            )
            # Rebuild holder map with new supply
            try:
                await self._poll_single_token(chain, contract)
            except Exception:
                pass

        return total_supply
