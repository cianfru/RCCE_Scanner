"""
whale_follows.py
~~~~~~~~~~~~~~~~
Persistent store for wallet watchlists — which whale/SM wallets each user
wants to track. Keyed by connected wallet address for privacy.

When followed wallets trade (open/close/flip), the system fires TG
notifications to registered chat IDs.

Stored in: data/whale_follows.json
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence path (same pattern as favorites.py)
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).resolve().parent / "data"

_FOLLOWS_PATH = _PERSIST_DIR / "whale_follows.json"

# In-memory: {user_wallet_lower: [followed_addr_lower, ...]}
_follows: Dict[str, List[str]] = {}

# TG chat IDs linked to user wallets (for sending whale trade alerts)
# {user_wallet_lower: chat_id}
_tg_links: Dict[str, int] = {}

# Recent trade events for followed wallets (ring buffer, newest first)
_followed_events: List[dict] = []
_MAX_EVENTS = 500

# Size threshold: skip tiny trades to reduce noise
MIN_SIZE_USD = 10_000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load() -> None:
    """Load follows from disk. Called once at startup."""
    global _follows, _tg_links
    try:
        if _FOLLOWS_PATH.exists():
            raw = json.loads(_FOLLOWS_PATH.read_text())
            _follows = raw.get("follows", {})
            _tg_links = {k: v for k, v in raw.get("tg_links", {}).items()}
            logger.info(
                "Whale follows loaded: %d users, %d total follows",
                len(_follows),
                sum(len(v) for v in _follows.values()),
            )
    except Exception as e:
        logger.warning("Could not load whale follows: %s", e)
        _follows = {}
        _tg_links = {}


def save() -> None:
    """Persist current follows to disk."""
    try:
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _FOLLOWS_PATH.write_text(json.dumps({
            "follows": _follows,
            "tg_links": _tg_links,
        }, indent=2))
    except Exception as e:
        logger.warning("Could not save whale follows: %s", e)


def get_follows(user: str) -> List[str]:
    """Return list of followed wallet addresses for a user."""
    return _follows.get(user.lower(), [])


def add_follow(user: str, address: str) -> bool:
    """Follow a wallet. Returns True if newly added, False if already following."""
    user_key = user.lower()
    addr = address.lower()
    if user_key not in _follows:
        _follows[user_key] = []
    if addr in _follows[user_key]:
        return False
    _follows[user_key].append(addr)
    save()
    logger.info("Whale follow: %s now follows %s", user_key[:10], addr[:10])
    return True


def remove_follow(user: str, address: str) -> bool:
    """Unfollow a wallet. Returns True if removed, False if wasn't following."""
    user_key = user.lower()
    addr = address.lower()
    if user_key not in _follows or addr not in _follows[user_key]:
        return False
    _follows[user_key].remove(addr)
    if not _follows[user_key]:
        del _follows[user_key]
    save()
    logger.info("Whale unfollow: %s unfollowed %s", user_key[:10], addr[:10])
    return True


def is_following(user: str, address: str) -> bool:
    """Check if a user follows a specific wallet."""
    return address.lower() in _follows.get(user.lower(), [])


def get_all_followed_addresses() -> Set[str]:
    """Return the union of all followed addresses across all users."""
    result: Set[str] = set()
    for addrs in _follows.values():
        result.update(addrs)
    return result


def get_users_following(address: str) -> List[str]:
    """Return list of user wallets that follow a given address."""
    addr = address.lower()
    return [user for user, addrs in _follows.items() if addr in addrs]


# ---------------------------------------------------------------------------
# TG link management
# ---------------------------------------------------------------------------

def link_tg(user: str, chat_id: int) -> None:
    """Link a TG chat ID to a user wallet (for whale trade alerts)."""
    _tg_links[user.lower()] = chat_id
    save()


def get_tg_chat_id(user: str) -> int | None:
    """Get TG chat ID for a user."""
    return _tg_links.get(user.lower())


def get_all_tg_links() -> Dict[str, int]:
    """Return all user → chat_id mappings."""
    return dict(_tg_links)


# ---------------------------------------------------------------------------
# Followed trade events
# ---------------------------------------------------------------------------

def push_event(event: dict) -> None:
    """Add a trade event from a followed wallet to the event buffer."""
    global _followed_events
    _followed_events.insert(0, event)
    if len(_followed_events) > _MAX_EVENTS:
        _followed_events = _followed_events[:_MAX_EVENTS]


def get_events(addresses: Set[str] | None = None, since: float = 0) -> List[dict]:
    """Return recent trade events, optionally filtered by address set and timestamp."""
    result = []
    for ev in _followed_events:
        if ev.get("timestamp", 0) <= since:
            break  # Events are newest-first, so stop when we're past the cutoff
        if addresses and ev.get("wallet", "").lower() not in addresses:
            continue
        result.append(ev)
    return result


# Load on import
load()
