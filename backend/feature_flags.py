"""
feature_flags.py
~~~~~~~~~~~~~~~~

Runtime-toggleable feature flags persisted to disk.

Backend background loops read flags via ``get_flag(name)`` on each iteration
so toggles take effect within one cycle without redeploying. Frontend reads
+ writes via ``/api/admin/features``.

Storage: a single JSON file on Railway's persistent volume so settings
survive redeploys. Path is configurable via ``FEATURE_FLAGS_PATH`` env
var; defaults to ``/data/feature_flags.json`` if /data exists, otherwise
falls back to the backend directory for local dev.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage path
# ---------------------------------------------------------------------------

_DEFAULT_DIR = Path("/data") if Path("/data").is_dir() else Path(__file__).parent
_FLAGS_PATH = Path(
    os.environ.get("FEATURE_FLAGS_PATH", str(_DEFAULT_DIR / "feature_flags.json"))
)

# ---------------------------------------------------------------------------
# Flag schema
# ---------------------------------------------------------------------------
# Defaults match the "Sentiment Mode" cost-cut state. Changes from these
# defaults are persisted to disk; missing keys re-fill from defaults.

DEFAULTS: Dict[str, bool] = {
    # HyperLens — slim sentiment aggregator (50 wallets, 10-min poll).
    # Off: pause polling entirely; consensus + roster freeze in last state.
    "hyperlens_enabled": True,
    # Order book / pressure-map polling. Heavy: ~80K calls/day when on.
    "hyperlens_pressure_map": False,
    # On-chain whale tracker (Etherscan/BSCscan/Solscan polling every 2 min)
    "whale_tracker": False,
    # Assistant market monitor — diffs scanner state every 5 min and pushes
    # WebSocket "insight" events. Template-based (no LLM call).
    "market_monitor": False,
}

# Allowed flag keys (extend here when adding new toggles).
ALLOWED_KEYS = set(DEFAULTS.keys())

# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------

_cache: Dict[str, bool] = {}
_lock = threading.Lock()
_loaded = False


def _ensure_loaded() -> None:
    """Lazy-load flags from disk on first access."""
    global _cache, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        if _FLAGS_PATH.exists():
            try:
                with open(_FLAGS_PATH, "r") as f:
                    saved = json.load(f)
                if not isinstance(saved, dict):
                    saved = {}
            except Exception as exc:
                logger.warning("feature_flags: failed to read %s (%s) — using defaults", _FLAGS_PATH, exc)
                saved = {}
        else:
            saved = {}
        # Merge: defaults provide complete schema, saved overrides
        merged = dict(DEFAULTS)
        for k, v in saved.items():
            if k in ALLOWED_KEYS and isinstance(v, bool):
                merged[k] = v
        _cache = merged
        _loaded = True
        logger.info("feature_flags: loaded from %s — %s", _FLAGS_PATH, _cache)


def _save_to_disk() -> None:
    """Persist current cache to disk. Caller holds _lock."""
    try:
        _FLAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_FLAGS_PATH, "w") as f:
            json.dump(_cache, f, indent=2)
    except Exception as exc:
        logger.warning("feature_flags: write failed (%s)", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_flag(name: str) -> bool:
    """Return the current value of a flag. Unknown keys return False."""
    _ensure_loaded()
    return _cache.get(name, False)


def get_all_flags() -> Dict[str, bool]:
    """Return a copy of all flags (for the admin UI)."""
    _ensure_loaded()
    return dict(_cache)


def set_flag(name: str, value: bool) -> bool:
    """Set a flag value and persist. Returns True if accepted."""
    if name not in ALLOWED_KEYS:
        return False
    _ensure_loaded()
    with _lock:
        _cache[name] = bool(value)
        _save_to_disk()
    logger.info("feature_flags: %s = %s", name, value)
    return True


def update_flags(updates: Dict[str, bool]) -> Dict[str, bool]:
    """Bulk update. Ignores unknown keys. Returns full state after update."""
    _ensure_loaded()
    with _lock:
        for k, v in updates.items():
            if k in ALLOWED_KEYS:
                _cache[k] = bool(v)
        _save_to_disk()
    logger.info("feature_flags: bulk update — %s", _cache)
    return dict(_cache)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

PRESETS: Dict[str, Dict[str, bool]] = {
    "idle": {
        "hyperlens_enabled": False,
        "hyperlens_pressure_map": False,
        "whale_tracker": False,
        "market_monitor": False,
    },
    "normal": {
        "hyperlens_enabled": True,
        "hyperlens_pressure_map": False,
        "whale_tracker": False,
        "market_monitor": False,
    },
    "power": {
        "hyperlens_enabled": True,
        "hyperlens_pressure_map": True,
        "whale_tracker": True,
        "market_monitor": True,
    },
}


def apply_preset(name: str) -> Dict[str, bool]:
    """Apply a preset by name. Returns full state. Raises ValueError if unknown."""
    preset = PRESETS.get(name)
    if preset is None:
        raise ValueError(f"unknown preset: {name}")
    return update_flags(preset)
