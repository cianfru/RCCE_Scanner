"""
portfolio_groups.py
~~~~~~~~~~~~~~~~~~~
Server-side persistence for portfolio groups (tab-based symbol organization).

Each group holds a curated list of symbols.  The scanner always scans
the **union** of all groups; the frontend filters by the active group.

Persistence uses a JSON file (same pattern as executor_state.json).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence directory (Railway volume or local ./data)
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).parent / "data"
_GROUPS_FILE = _PERSIST_DIR / "portfolio_groups.json"

# ---------------------------------------------------------------------------
# Default symbols for the Main group (same 10 used in backtesting)
# ---------------------------------------------------------------------------

DEFAULT_MAIN_SYMBOLS: List[str] = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PortfolioGroup:
    id: str
    name: str
    symbols: List[str] = field(default_factory=list)
    color: str = "#22d3ee"   # cyan accent by default
    order: int = 0
    pinned: bool = False     # pinned groups can't be deleted


# ---------------------------------------------------------------------------
# Manager (singleton)
# ---------------------------------------------------------------------------

class PortfolioGroupManager:
    """Manages portfolio groups with JSON persistence."""

    _instance: Optional["PortfolioGroupManager"] = None

    def __init__(self) -> None:
        self.groups: List[PortfolioGroup] = []
        self._load()

    # ── Singleton access ──────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "PortfolioGroupManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load groups from JSON file, or create defaults if missing."""
        if _GROUPS_FILE.exists():
            try:
                raw = json.loads(_GROUPS_FILE.read_text())
                self.groups = [
                    PortfolioGroup(**g) for g in raw.get("groups", [])
                ]
                logger.info(
                    "Loaded %d portfolio groups from %s", len(self.groups), _GROUPS_FILE
                )
                return
            except Exception as exc:
                logger.warning("Failed to load portfolio groups: %s — recreating", exc)

        self._create_defaults()
        self._save()

    def _save(self) -> None:
        """Persist groups to JSON (atomic write via tmp → rename)."""
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _GROUPS_FILE.with_suffix(".tmp")
        try:
            payload = {"groups": [asdict(g) for g in self.groups]}
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(_GROUPS_FILE)
        except Exception as exc:
            logger.error("Failed to save portfolio groups: %s", exc)

    def _create_defaults(self) -> None:
        """Create the two default pinned groups: Main and BTC."""
        self.groups = [
            PortfolioGroup(
                id=uuid.uuid4().hex[:8],
                name="Main",
                symbols=DEFAULT_MAIN_SYMBOLS.copy(),
                color="#22d3ee",
                order=0,
                pinned=True,
            ),
            PortfolioGroup(
                id=uuid.uuid4().hex[:8],
                name="BTC",
                symbols=[],
                color="#fb923c",
                order=1,
                pinned=True,
            ),
        ]
        logger.info("Created default portfolio groups (Main + BTC)")

    # ── Query helpers ─────────────────────────────────────────────────────

    def get_all(self) -> List[PortfolioGroup]:
        """Return all groups sorted by order."""
        return sorted(self.groups, key=lambda g: g.order)

    def get_by_id(self, group_id: str) -> Optional[PortfolioGroup]:
        for g in self.groups:
            if g.id == group_id:
                return g
        return None

    def get_union_symbols(self) -> List[str]:
        """Return deduplicated union of all groups' symbols."""
        seen: set = set()
        result: List[str] = []
        for g in self.groups:
            for sym in g.symbols:
                if sym not in seen:
                    seen.add(sym)
                    result.append(sym)
        return result

    # ── Mutations ─────────────────────────────────────────────────────────

    def create_group(
        self, name: str, symbols: List[str] = None, color: str = "#22d3ee"
    ) -> PortfolioGroup:
        """Create a new group and persist."""
        max_order = max((g.order for g in self.groups), default=-1)
        group = PortfolioGroup(
            id=uuid.uuid4().hex[:8],
            name=name,
            symbols=symbols or [],
            color=color,
            order=max_order + 1,
            pinned=False,
        )
        self.groups.append(group)
        self._save()
        return group

    def update_group(self, group_id: str, name: str = None, color: str = None) -> Optional[PortfolioGroup]:
        """Update group name and/or color."""
        g = self.get_by_id(group_id)
        if g is None:
            return None
        if name is not None:
            g.name = name
        if color is not None:
            g.color = color
        self._save()
        return g

    def delete_group(self, group_id: str) -> bool:
        """Delete a group. Returns False if pinned or not found."""
        g = self.get_by_id(group_id)
        if g is None or g.pinned:
            return False
        self.groups.remove(g)
        self._save()
        return True

    def add_symbol(self, group_id: str, symbol: str) -> Optional[PortfolioGroup]:
        """Add a symbol to a group. No-op if already present."""
        g = self.get_by_id(group_id)
        if g is None:
            return None
        symbol = symbol.upper().replace("-", "/")
        if symbol not in g.symbols:
            g.symbols.append(symbol)
            self._save()
        return g

    def remove_symbol(self, group_id: str, symbol: str) -> Optional[PortfolioGroup]:
        """Remove a symbol from a group."""
        g = self.get_by_id(group_id)
        if g is None:
            return None
        symbol = symbol.upper().replace("-", "/")
        if symbol in g.symbols:
            g.symbols.remove(symbol)
            self._save()
        return g

    def reorder(self, group_ids: List[str]) -> None:
        """Set group order based on list position."""
        id_to_group = {g.id: g for g in self.groups}
        for idx, gid in enumerate(group_ids):
            if gid in id_to_group:
                id_to_group[gid].order = idx
        self._save()

    def migrate_from_watchlist(self, symbols: List[str]) -> None:
        """One-time migration: put existing watchlist symbols into Main group."""
        main = next((g for g in self.groups if g.pinned and g.name == "Main"), None)
        if main is None:
            return
        # Only migrate if Main still has the exact defaults (not user-modified)
        if set(main.symbols) == set(DEFAULT_MAIN_SYMBOLS):
            # Add any extra symbols from the old watchlist
            for sym in symbols:
                if sym not in main.symbols:
                    main.symbols.append(sym)
            self._save()
            logger.info("Migrated %d watchlist symbols into Main group", len(symbols))
