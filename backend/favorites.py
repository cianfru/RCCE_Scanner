"""
favorites.py
~~~~~~~~~~~~
Shared, persistent store for user-starred trading pairs.

These are the coins the user has starred (⭐) in the terminal dashboard.
The TG bot uses this set to filter non-held opportunity alerts — only
held positions and starred pairs will trigger TG messages.

Stored in: data/favorites.json
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence path (mirrors the pattern used by position_monitor)
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).resolve().parent / "data"

_FAVORITES_PATH = _PERSIST_DIR / "favorites.json"

# In-memory set — always the source of truth after load()
_favorites: Set[str] = set()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load() -> None:
    """Load favorites from disk.  Called once at startup."""
    global _favorites
    try:
        if _FAVORITES_PATH.exists():
            raw = json.loads(_FAVORITES_PATH.read_text())
            raw = raw if isinstance(raw, list) else []
            # Symbols starred under a ticker Hyperliquid has since renamed move to the current
            # name (once: the file is saved renamed).
            from ticker_renames import rename_list
            current, renamed = rename_list(raw)
            _favorites = set(current)
            if renamed:
                save()
                logger.info("Favorites: %d symbols moved to their current tickers", renamed)
            logger.info("Favorites loaded: %d symbols", len(_favorites))
    except Exception as e:
        logger.warning("Could not load favorites: %s", e)
        _favorites = set()


def save() -> None:
    """Persist current favorites to disk."""
    try:
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _FAVORITES_PATH.write_text(json.dumps(sorted(_favorites)))
    except Exception as e:
        logger.warning("Could not save favorites: %s", e)


def get() -> Set[str]:
    """Return the current set of starred symbols (e.g. {'BTC/USDT', 'ETH/USDT'})."""
    return _favorites


def add(symbol: str) -> None:
    """Star a symbol."""
    _favorites.add(_normalise(symbol))
    save()


def remove(symbol: str) -> None:
    """Un-star a symbol."""
    _favorites.discard(_normalise(symbol))
    save()


def toggle(symbol: str) -> bool:
    """Toggle star state.  Returns True if now starred, False if removed."""
    sym = _normalise(symbol)
    if sym in _favorites:
        _favorites.discard(sym)
        save()
        return False
    else:
        _favorites.add(sym)
        save()
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(symbol: str) -> str:
    from ticker_renames import current_symbol
    sym = symbol.upper().replace("-", "/").strip()
    if "/" not in sym:
        sym = f"{sym}/USDT"
    return current_symbol(sym)


# Load on import so position_monitor / main can use get() immediately
load()
