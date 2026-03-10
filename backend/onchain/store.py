"""
On-chain tracker persistence — JSON file storage for tracked tokens,
wallet labels, and incremental fetch cursors.

Follows the same pattern as portfolio_groups.py:
    - Singleton manager
    - Atomic write via tmp → rename
    - Railway volume mount support
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from .config import KNOWN_WHALE_SEEDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence directory
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).resolve().parent.parent / "data"
_WHALES_FILE = _PERSIST_DIR / "whale_tracker.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TrackedTokenRecord:
    chain: str
    contract: str
    symbol: str = ""
    name: str = ""
    decimals: int = 18
    total_supply: float = 0.0
    added_at: float = 0.0


# ---------------------------------------------------------------------------
# Singleton manager
# ---------------------------------------------------------------------------

class WhaleStoreManager:
    """Manages persisted whale tracking state."""

    _instance: Optional["WhaleStoreManager"] = None

    def __init__(self) -> None:
        self.tracked_tokens: List[TrackedTokenRecord] = []
        self.wallet_labels: Dict[str, Dict[str, str]] = {}   # chain -> {addr: label}
        self.last_seen_blocks: Dict[str, Dict[str, int]] = {}  # chain -> {contract: block}
        self._load()

    # ── Singleton ──────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "WhaleStoreManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Persistence ────────────────────────────────────────────────────────

    def _load(self) -> None:
        if _WHALES_FILE.exists():
            try:
                raw = json.loads(_WHALES_FILE.read_text())
                self.tracked_tokens = [
                    TrackedTokenRecord(**t)
                    for t in raw.get("tracked_tokens", [])
                ]
                self.wallet_labels = raw.get("wallet_labels", {})
                self.last_seen_blocks = raw.get("last_seen_blocks", {})
                logger.info(
                    "Loaded whale store: %d tokens, %d label sets",
                    len(self.tracked_tokens),
                    sum(len(v) for v in self.wallet_labels.values()),
                )
                # Merge known whale seeds (don't overwrite user labels)
                self._merge_known_whales()
                return
            except Exception as exc:
                logger.warning("Failed to load whale store: %s — recreating", exc)

        self._create_defaults()
        self._save()

    def _save(self) -> None:
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _WHALES_FILE.with_suffix(".tmp")
        try:
            payload = {
                "tracked_tokens": [asdict(t) for t in self.tracked_tokens],
                "wallet_labels": self.wallet_labels,
                "last_seen_blocks": self.last_seen_blocks,
            }
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(_WHALES_FILE)
        except Exception as exc:
            logger.error("Failed to save whale store: %s", exc)

    def _create_defaults(self) -> None:
        self.tracked_tokens = []
        self.wallet_labels = {}
        self.last_seen_blocks = {}
        self._merge_known_whales()

    def _merge_known_whales(self) -> None:
        """Seed known whale labels without overwriting user-defined ones."""
        for chain, whales in KNOWN_WHALE_SEEDS.items():
            if chain not in self.wallet_labels:
                self.wallet_labels[chain] = {}
            for addr, label in whales.items():
                addr_lower = addr.lower() if chain != "solana" else addr
                if addr_lower not in self.wallet_labels[chain]:
                    self.wallet_labels[chain][addr_lower] = label

    # ── Token management ───────────────────────────────────────────────────

    def add_token(
        self,
        chain: str,
        contract: str,
        symbol: str = "",
        name: str = "",
        decimals: int = 18,
        total_supply: float = 0.0,
    ) -> TrackedTokenRecord:
        contract_key = contract.lower() if chain != "solana" else contract
        # Check if already tracked
        for t in self.tracked_tokens:
            key = t.contract.lower() if t.chain != "solana" else t.contract
            if t.chain == chain and key == contract_key:
                # Update metadata if provided
                if symbol:
                    t.symbol = symbol
                if name:
                    t.name = name
                if decimals != 18:
                    t.decimals = decimals
                if total_supply > 0:
                    t.total_supply = total_supply
                self._save()
                return t

        record = TrackedTokenRecord(
            chain=chain,
            contract=contract,
            symbol=symbol,
            name=name,
            decimals=decimals,
            total_supply=total_supply,
            added_at=time.time(),
        )
        self.tracked_tokens.append(record)
        self._save()
        logger.info("Now tracking %s/%s on %s", symbol or "?", contract[:12], chain)
        return record

    def remove_token(self, chain: str, contract: str) -> bool:
        contract_key = contract.lower() if chain != "solana" else contract
        before = len(self.tracked_tokens)
        self.tracked_tokens = [
            t for t in self.tracked_tokens
            if not (
                t.chain == chain
                and (t.contract.lower() if t.chain != "solana" else t.contract) == contract_key
            )
        ]
        removed = len(self.tracked_tokens) < before
        if removed:
            # Clean up block cursor
            if chain in self.last_seen_blocks:
                self.last_seen_blocks[chain].pop(contract_key, None)
            self._save()
        return removed

    def get_tracked_tokens(self, chain: Optional[str] = None) -> List[TrackedTokenRecord]:
        if chain is None:
            return list(self.tracked_tokens)
        return [t for t in self.tracked_tokens if t.chain == chain]

    # ── Wallet labels ──────────────────────────────────────────────────────

    def set_wallet_label(self, chain: str, address: str, label: str) -> None:
        addr_key = address.lower() if chain != "solana" else address
        if chain not in self.wallet_labels:
            self.wallet_labels[chain] = {}
        self.wallet_labels[chain][addr_key] = label
        self._save()

    def get_wallet_label(self, chain: str, address: str) -> str:
        addr_key = address.lower() if chain != "solana" else address
        return self.wallet_labels.get(chain, {}).get(addr_key, "")

    def get_all_labels(self, chain: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        if chain is None:
            return dict(self.wallet_labels)
        return {chain: self.wallet_labels.get(chain, {})}

    # ── Block cursors ──────────────────────────────────────────────────────

    def get_last_block(self, chain: str, contract: str) -> int:
        contract_key = contract.lower() if chain != "solana" else contract
        return self.last_seen_blocks.get(chain, {}).get(contract_key, 0)

    def set_last_block(self, chain: str, contract: str, block: int) -> None:
        contract_key = contract.lower() if chain != "solana" else contract
        if chain not in self.last_seen_blocks:
            self.last_seen_blocks[chain] = {}
        self.last_seen_blocks[chain][contract_key] = block
        self._save()
