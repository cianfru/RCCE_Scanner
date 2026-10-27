"""
data_fetcher.py
~~~~~~~~~~~~~~~
Fetches OHLCV data from Hyperliquid (primary) with CCXT exchange fallback.

Primary source  : Hyperliquid candleSnapshot API (all crypto + HIP-3)
Fallback (CCXT) : Kraken → KuCoin → Binance → Bybit (only for HL failures)

Concurrency is throttled with an asyncio.Semaphore.  Results are cached
in memory with a configurable TTL (5 min for 4h candles, 30 min for
daily candles).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp
_ccxt_mod = None

def _get_ccxt():
    global _ccxt_mod
    if _ccxt_mod is None:
        import ccxt.async_support as _ccxt
        _ccxt_mod = _ccxt
    return _ccxt_mod


async def _create_exchange(exchange_id: str):
    """Create an unshared public-data client; the caller owns and closes it."""
    exchange_class = getattr(_get_ccxt(), exchange_id)
    return exchange_class({"enableRateLimit": True, "timeout": 30000})


import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default watchlist (25 high-priority symbols, CCXT pair format)
# ---------------------------------------------------------------------------

DEFAULT_SYMBOLS: List[str] = [
    # Large caps
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "NEAR/USDT",
    # L2 / New L1
    "ARB/USDT", "OP/USDT", "SUI/USDT", "INJ/USDT", "TIA/USDT",
    # Meme
    "DOGE/USDT", "PEPE/USDT", "WIF/USDT",
    # AI / Compute
    "FET/USDT", "RENDER/USDT", "TAO/USDT",
    # DeFi
    "AAVE/USDT", "RUNE/USDT",
    # Infra
    "TON/USDT", "HBAR/USDT",
]

# ---------------------------------------------------------------------------
# Full list (65 symbols, available as preset)
# ---------------------------------------------------------------------------

FULL_SYMBOLS: List[str] = [
    # Large caps
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "POL/USDT",
    "NEAR/USDT", "UNI/USDT", "ATOM/USDT", "FIL/USDT", "APT/USDT",
    # L2 / New L1
    "ARB/USDT", "OP/USDT", "SUI/USDT", "SEI/USDT", "INJ/USDT",
    "TIA/USDT",
    # Meme
    "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "WIF/USDT", "BONK/USDT",
    "FLOKI/USDT", "MEME/USDT",
    # AI / Compute
    "FET/USDT", "RENDER/USDT", "TAO/USDT",
    # DeFi
    "AAVE/USDT", "SKY/USDT", "LDO/USDT", "CRV/USDT", "SNX/USDT",
    "COMP/USDT", "RUNE/USDT",
    # Infrastructure / Misc
    "STX/USDT", "ICP/USDT", "HBAR/USDT", "VET/USDT", "ALGO/USDT",
    "S/USDT", "SAND/USDT", "MANA/USDT", "AXS/USDT", "GMT/USDT",
    "IMX/USDT", "GALA/USDT",
    # Newer listings
    "BLUR/USDT", "JTO/USDT", "JUP/USDT", "PYTH/USDT", "W/USDT",
    "WLD/USDT", "STRK/USDT", "ORDI/USDT",
    # Additional
    "TRX/USDT", "TON/USDT", "CAKE/USDT", "DYDX/USDT", "ENS/USDT",
    "GRT/USDT", "OCEAN/USDT",
]

# ---------------------------------------------------------------------------
# Supported timeframes and their cache TTLs (seconds)
# ---------------------------------------------------------------------------

_CACHE_TTL: Dict[str, int] = {
    "4h": 5 * 60,      # 5 minutes
    "1d": 30 * 60,     # 30 minutes
    "1w": 60 * 60,     # 1 hour
}

SUPPORTED_TIMEFRAMES = list(_CACHE_TTL.keys())

# Timeframe → milliseconds per candle (for calculating startTime, and Hyperliquid's candle grid)
_TF_MS: Dict[str, int] = {
    "4h": 4 * 3600 * 1000,
    "1d": 86400 * 1000,
    "1w": 7 * 86400 * 1000,
}

# Minimum candle counts per timeframe for full z-score warm-up.
# Z-score needs a 300-bar regression followed by 200 bars of normalization;
# keep extra history for regime persistence beyond that warm-up.
_DEFAULT_LIMIT: Dict[str, int] = {
    "4h": 600,     # 300-bar regression + 200-bar normalization + persistence margin
    "1d": 600,     # same engine warm-up requirements as 4h
    "1w": 200,     # ~3.8 years — enough for weekly regime detection
}

# Concurrency knobs — tuned for Hyperliquid rate limits.
# HL returns 429 when hit too hard; 10 concurrent + 50ms stagger
# keeps us under the limit even at 200+ symbols × 2 timeframes.
_MAX_CONCURRENT_FETCHES = 10
_INTER_REQUEST_DELAY_S = 0.05  # 50 ms stagger

# Symbols known to need CCXT (HL candleSnapshot fails).
# Populated at runtime; most symbols work fine on HL.
_ccxt_only: set = set()

# Minimum bar thresholds — if HL returns fewer than this, try CCXT for deeper history.
# Based on engine requirements: heatmap needs 21 weekly bars, RCCE needs ~200 daily bars.
_MIN_BARS: Dict[str, int] = {
    "4h": 200,    # ~33 days minimum for 4h z-score
    "1d": 200,    # ~6.5 months minimum for daily
    "1w": 21,     # ~5 months — heatmap BMSB threshold
}

# Symbols known to exist on Binance.  Populated once on first batch fetch
# via load_markets(), then reused.  Symbols on this set are fetched from
# Binance (fast, generous rate limits); the rest go to HL.
_binance_symbols: Optional[set] = None
_binance_symbols_lock = asyncio.Lock()


async def _ensure_binance_symbols() -> set:
    """Lazy-load the set of Binance-listed symbols (cached for process life).

    Retries once on failure. If both attempts fail, returns empty set and
    logs a warning so we know all symbols will be routed to HL.
    """
    global _binance_symbols
    if _binance_symbols is not None:
        return _binance_symbols

    async with _binance_symbols_lock:
        if _binance_symbols is not None:
            return _binance_symbols

        for attempt in range(2):
            try:
                exchange = await _create_exchange("binance")
                try:
                    await exchange.load_markets()
                    _binance_symbols = set(exchange.markets.keys())
                    logger.info("Binance market list loaded: %d symbols", len(_binance_symbols))
                    return _binance_symbols
                finally:
                    await exchange.close()
            except Exception as exc:
                logger.warning(
                    "Binance load_markets attempt %d failed: %s", attempt + 1, exc
                )
                if attempt == 0:
                    await asyncio.sleep(2)

        logger.error(
            "Binance markets unavailable after 2 attempts — ALL symbols routed to HL. "
            "Expect slower fetches and possible 429 rate limits."
        )
        _binance_symbols = set()
        return _binance_symbols

# Hyperliquid's "k" markets (quoted per 1,000 tokens) are keyed KPEPE/USDT, Hyperliquid's name
# kPEPE (ticker_renames.hl_name). The bare PEPE/USDT is not mapped to kPEPE: its candles would be
# per 1,000 tokens under a 1-token key. Renamed tickers (MATIC, RNDR, FTM) are keyed by their
# current names everywhere (ticker_renames.py), so they need no mapping.


# ---------------------------------------------------------------------------
# DataCache -- simple in-memory TTL cache
# ---------------------------------------------------------------------------

class DataCache:
    """Lightweight fetch-throttle: tracks when each symbol+TF was last fetched.

    Stores only timestamps (not data) — reads go through OHLCVStore.
    Saves ~20-40MB vs the old design which duplicated all OHLCV arrays.
    """

    def __init__(self) -> None:
        self._fetched_at: Dict[str, float] = {}
        self._fetched_wall: Dict[str, float] = {}

    @staticmethod
    def _key(symbol: str, timeframe: str) -> str:
        return f"{symbol}|{timeframe}"

    @staticmethod
    def _last_close(timeframe: str, wall: float) -> float:
        """Most recent candle close for *timeframe* (UTC). Hyperliquid's candles sit on the epoch grid,
        so its weeks open and close Thursday 00:00 (the epoch began on a Thursday), not Monday."""
        bar = {"4h": 14_400, "1d": 86_400, "1w": 604_800}.get(timeframe)
        if bar is None:
            return float("-inf")
        return wall // bar * bar

    def get(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Return OHLCVStore data if recently fetched, else None."""
        key = self._key(symbol, timeframe)
        fetched = self._fetched_at.get(key)
        if fetched is None:
            return None
        ttl = _CACHE_TTL.get(timeframe, 300)
        # A candle close invalidates the entry even inside its TTL, otherwise a fetch
        # just before the close would hand back the previous candle for up to 30 min.
        closed_since = self._fetched_wall.get(key, float("-inf")) < self._last_close(timeframe, time.time())
        if time.monotonic() - fetched > ttl or closed_since:
            del self._fetched_at[key]
            self._fetched_wall.pop(key, None)
            return None
        return _ohlcv_store.get(symbol, timeframe)

    def put(self, symbol: str, timeframe: str, data: dict, ttl: Optional[int] = None) -> None:
        """Record that this symbol+TF was just fetched (data is in OHLCVStore)."""
        key = self._key(symbol, timeframe)
        self._fetched_at[key] = time.monotonic()
        self._fetched_wall[key] = time.time()

    def seed(self, symbol: str, timeframe: str, observed_wall: float) -> None:
        """Count a stored series read at ``observed_wall`` (before a restart) as fetched then, so the
        usual TTL and candle-close rules decide whether it is read again."""
        key = self._key(symbol, timeframe)
        age = max(0.0, time.time() - observed_wall)
        self._fetched_at[key] = time.monotonic() - age
        self._fetched_wall[key] = observed_wall

    def invalidate(self, symbol: str, timeframe: str) -> None:
        """Remove a single entry."""
        self._fetched_at.pop(self._key(symbol, timeframe), None)
        self._fetched_wall.pop(self._key(symbol, timeframe), None)

    def clear(self) -> None:
        """Drop every cached entry."""
        self._fetched_at.clear()
        self._fetched_wall.clear()

    def __len__(self) -> int:
        return len(self._fetched_at)


# Module-level cache instance shared across calls
_cache = DataCache()


# ---------------------------------------------------------------------------
# OHLCVStore -- persistent OHLCV cache (append-only, no TTL expiration)
# ---------------------------------------------------------------------------

# Maximum age before forcing a full refetch (handles restarts / gaps). Below it, an incremental
# read fetches exactly the bars missing since the last stored one (bars_to_fetch).
_STALENESS_LIMIT: Dict[str, float] = {
    "4h": 24 * 3600,     # 24 hours
    "1d": 7 * 86400,     # 7 days
    "1w": 30 * 86400,    # 30 days
}

# A closed candle is taken as final once it was read this long after its close.
_CLOSE_SETTLE_S = 60

# Persistence path — Railway persistent volume at /data, local fallback
_DATA_DIR = Path("/data") if Path("/data").is_dir() else Path(__file__).parent
_OHLCV_CACHE_PATH = Path(os.environ.get(
    "OHLCV_CACHE_PATH",
    str(_DATA_DIR / "ohlcv_cache.pkl"),
))

# Minimum interval between disk saves (seconds) — debounce rapid cycles.
# Bumped from 120s → 600s to reduce kernel page-cache pressure on Railway.
# Pickle is also force-saved on shutdown via lifespan hook, so worst-case
# restart loses 10 min of cached bars (which scanner refetches anyway).
_SAVE_DEBOUNCE_SECS = 600


_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")

# Where a stored series' bars come from. A series holds bars of one source only: Hyperliquid
# ("hl") or the Binance/Bybit fallback ("cex"). Their weeks start on different days (Hyperliquid
# Thursday 00:00 UTC, the exchanges Monday 00:00), and even on 4h/1d their prices are another
# instrument's (spot, or another venue's perp), so a fallback bar never enters a Hyperliquid series
# except as older history before its first bar on 4h/1d (see OHLCVStore.update).
SOURCE_HL = "hl"
SOURCE_CEX = "cex"


def on_hl_grid(timestamps, timeframe: str) -> np.ndarray:
    """Which bar opens lie on Hyperliquid's candle grid (epoch-aligned: weeks open Thursday 00:00 UTC)."""
    tf_ms = _TF_MS.get(timeframe)
    ts = np.asarray(timestamps, dtype=np.float64)
    if tf_ms is None:
        return np.ones(len(ts), dtype=bool)
    return np.mod(ts, tf_ms) == 0


def _sorted_unique(data: dict) -> dict:
    """The bars ordered by open time, one per timestamp (the last one given wins)."""
    ts = np.asarray(data["timestamp"], dtype=np.float64)
    _, rev = np.unique(ts[::-1], return_index=True)
    idx = len(ts) - 1 - rev
    return {f: np.asarray(data[f], dtype=np.float64)[idx] for f in _FIELDS}


class OHLCVStore:
    """Persistent in-memory OHLCV cache. Stores full history arrays and
    updates them incrementally by appending new bars.

    Unlike DataCache (TTL-based), this store never expires. On each scan:
    - If no cache exists: full fetch (cold start)
    - If cache exists: fetch only 2 latest bars, merge into cached array

    A fetched range is authoritative: stored bars inside it are replaced by the fetched ones, and
    stored bars inside it that the fetch does not have are dropped (``stats`` counts both).
    """

    def __init__(self) -> None:
        self._store: Dict[str, dict] = {}       # key: "SYMBOL|TF" → OHLCV dict
        self._history_targets: Dict[str, int] = {}
        self._updated_at: Dict[str, float] = {}  # key → monotonic time
        self._sources: Dict[str, str] = {}       # key → SOURCE_HL / SOURCE_CEX
        self._refetch: set = set()               # keys whose next read must be a full one
        self._verified_at: Dict[str, float] = {}  # key → wall time of the last full check against Hyperliquid
        self.stats: Dict[str, int] = {"bars_revised": 0, "bars_dropped": 0, "fallback_bars_refused": 0}

    @staticmethod
    def _key(symbol: str, timeframe: str) -> str:
        return f"{symbol}|{timeframe}"

    def get(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Return cached OHLCV arrays or None if not stored."""
        return self._store.get(self._key(symbol, timeframe))

    def source(self, symbol: str, timeframe: str) -> Optional[str]:
        """SOURCE_HL or SOURCE_CEX for a stored series, None when nothing is stored."""
        key = self._key(symbol, timeframe)
        return self._sources.get(key, SOURCE_HL) if key in self._store else None

    def observed_at(self, symbol: str, timeframe: str) -> Optional[float]:
        updated = self._updated_at.get(self._key(symbol, timeframe))
        return time.time() - (time.monotonic() - updated) if updated is not None else None

    def invalidate(self, symbol: str, timeframe: str) -> None:
        """Remove a single entry, forcing a full refetch next call."""
        key = self._key(symbol, timeframe)
        self._store.pop(key, None)
        self._updated_at.pop(key, None)
        self._history_targets.pop(key, None)
        self._sources.pop(key, None)
        self._refetch.discard(key)
        self._verified_at.pop(key, None)

    def clean_weekly(self, key: str) -> int:
        """A weekly series holding bars on Hyperliquid's grid and off it (exchange weeks merged in
        before the fallback was kept out): drop the off-grid bars and read the series in full next
        time, which also fills weeks only the exchange bars covered. Returns the bars dropped."""
        data = self._store.get(key)
        if data is None or not key.endswith("|1w") or not len(data["timestamp"]):
            return 0
        grid = on_hl_grid(data["timestamp"], "1w")
        if grid.all():
            self._sources.setdefault(key, SOURCE_HL)
            return 0
        if not grid.any():                       # an exchange-only series: consistent, keep it
            self._sources[key] = SOURCE_CEX
            return 0
        self._store[key] = {f: np.asarray(data[f])[grid] for f in _FIELDS}
        self._sources[key] = SOURCE_HL
        self._refetch.add(key)
        dropped = int((~grid).sum())
        self.stats["bars_dropped"] += dropped
        return dropped

    def bars_missing(self, symbol: str, timeframe: str, now_ms: Optional[float] = None) -> Optional[int]:
        """Bars opened since the last stored bar opened (0: the last stored bar is the open one).
        None when nothing is stored."""
        cached = self._store.get(self._key(symbol, timeframe))
        tf_ms = _TF_MS.get(timeframe)
        if cached is None or tf_ms is None or not len(cached.get("timestamp", [])):
            return None
        now_ms = time.time() * 1000 if now_ms is None else now_ms
        return max(0, int((now_ms - float(cached["timestamp"][-1])) // tf_ms))

    def bars_to_fetch(self, symbol: str, timeframe: str, now_ms: Optional[float] = None) -> int:
        """Bars an incremental read asks for: the last stored bar (it may have been open when read)
        and every bar since, at least 2 (what every incremental read asked for before)."""
        missing = self.bars_missing(symbol, timeframe, now_ms)
        if missing is None:
            return _DEFAULT_LIMIT.get(timeframe, 500)
        return max(2, missing + 1)

    def complete(self, symbol: str, timeframe: str, now: Optional[float] = None) -> bool:
        """The stored series holds every closed bar: it was read after the latest close settled."""
        key = self._key(symbol, timeframe)
        if key not in self._store or key not in self._updated_at or key in self._refetch:
            return False
        observed = self.observed_at(symbol, timeframe)
        close = DataCache._last_close(timeframe, time.time() if now is None else now)
        return observed is not None and observed >= close + _CLOSE_SETTLE_S

    def needs_full_fetch(self, symbol: str, timeframe: str, source: str = SOURCE_HL) -> bool:
        """True if no cache or cache is stale (too old for incremental update), or the next read
        comes from another source than the stored bars (which it then replaces), or a repair asked
        for a full read."""
        key = self._key(symbol, timeframe)
        if key not in self._store:
            return True
        if key in self._refetch or self._sources.get(key, SOURCE_HL) != source:
            return True
        updated = self._updated_at.get(key, 0.0)
        max_age = _STALENESS_LIMIT.get(timeframe, 24 * 3600)
        if time.monotonic() - updated > max_age:
            return True
        # Backfill once when the configured history target increases.
        cached = self._store[key]
        bar_count = len(cached.get("close", []))
        target = _DEFAULT_LIMIT.get(timeframe, 500)
        return bar_count < target and self._history_targets.get(key, 0) < target

    def update(self, symbol: str, timeframe: str, new_data: dict,
               max_bars: Optional[int] = None, full_fetch_target: Optional[int] = None,
               source: str = SOURCE_HL) -> dict:
        """Merge new bars into cached array. Returns the full updated array.

        Preserve older backfills and newer cached bars. The fetched range is authoritative: its
        bars replace the stored ones at the same timestamps, and stored bars inside the range
        that the fetch does not have are dropped (bars from another source or grid). Record
        successful full requests so short listings do not trigger another backfill on every scan.

        ``source``: where the bars come from (SOURCE_HL or SOURCE_CEX). Fallback bars never enter
        a Hyperliquid series, except older history before its first bar on 4h/1d (exchange weeks
        start on another day, so never on 1w); Hyperliquid bars replace a fallback series.
        """
        key = self._key(symbol, timeframe)
        if max_bars is None:
            max_bars = _DEFAULT_LIMIT.get(timeframe, 500)

        new_ts = new_data.get("timestamp")
        if new_ts is None or len(new_ts) == 0:
            # Empty new data — return existing cache or None
            return self._store.get(key, new_data)

        new = _sorted_unique(new_data)
        if source == SOURCE_HL and timeframe == "1w":
            grid = on_hl_grid(new["timestamp"], timeframe)
            if not grid.all():
                new = {f: v[grid] for f, v in new.items()}
                if not len(new["timestamp"]):
                    return self._store.get(key, new_data)
        tf_ms = _TF_MS.get(timeframe, 0)
        cached = self._store.get(key)
        cached_source = self._sources.get(key, SOURCE_HL) if cached is not None else None

        if cached is not None and cached_source == SOURCE_HL and source != SOURCE_HL:
            # Fallback bars for a Hyperliquid series: only history older than its first bar.
            first = float(cached["timestamp"][0]) if len(cached["timestamp"]) else float("inf")
            older = (new["timestamp"] + tf_ms <= first) if timeframe != "1w" else np.zeros(len(new["timestamp"]), bool)
            self.stats["fallback_bars_refused"] += int((~older).sum())
            if not older.any():
                return cached
            merged = {f: np.concatenate([new[f][older], cached[f]])[-max_bars:] for f in _FIELDS}
            self._store[key] = merged
            if full_fetch_target is not None:
                self._history_targets[key] = max(full_fetch_target, self._history_targets.get(key, 0))
            return merged

        if cached is None:
            merged = {f: v[-max_bars:].copy() for f, v in new.items()}
        else:
            lo, hi = float(new["timestamp"][0]), float(new["timestamp"][-1])
            c_ts = np.asarray(cached["timestamp"], dtype=np.float64)
            if cached_source != source:
                # Hyperliquid replaces a fallback series: keep only older 4h/1d history before it.
                keep = (c_ts + tf_ms <= lo) if timeframe != "1w" else np.zeros(len(c_ts), bool)
                self._history_targets.pop(key, None)
            else:
                inside = (c_ts >= lo) & (c_ts <= hi)
                keep = ~inside
                self._count_revisions(cached, inside, new)
            merged = {f: np.concatenate([np.asarray(cached[f], dtype=np.float64)[keep], new[f]]) for f in _FIELDS}
            order = np.argsort(merged["timestamp"], kind="stable")[-max_bars:]
            merged = {f: v[order] for f, v in merged.items()}
            if source == SOURCE_HL and timeframe == "1w":
                grid = on_hl_grid(merged["timestamp"], timeframe)
                if not grid.all():
                    self.stats["bars_dropped"] += int((~grid).sum())
                    merged = {f: v[grid] for f, v in merged.items()}
        self._store[key] = merged
        self._sources[key] = source
        self._updated_at[key] = time.monotonic()
        if full_fetch_target is not None:
            self._history_targets[key] = max(full_fetch_target, self._history_targets.get(key, 0))
            self._refetch.discard(key)
        return merged

    def _count_revisions(self, cached: dict, inside: np.ndarray, new: dict) -> None:
        """Count stored bars inside a fetched range that the fetch changed or does not have."""
        if not inside.any():
            return
        c_ts = np.asarray(cached["timestamp"], dtype=np.float64)[inside]
        pos = np.searchsorted(new["timestamp"], c_ts)
        pos_ok = np.minimum(pos, len(new["timestamp"]) - 1)
        present = new["timestamp"][pos_ok] == c_ts
        dropped = int((~present).sum())
        # The newest stored bar may have been open when read: a changed value there is the candle
        # completing, not a revision.
        last_open = c_ts == float(cached["timestamp"][-1])
        changed = np.zeros(len(c_ts), dtype=bool)
        for f in ("open", "high", "low", "close"):
            old = np.asarray(cached[f], dtype=np.float64)[inside]
            changed |= present & ~np.isclose(old, new[f][pos_ok], rtol=1e-9, atol=0.0)
        revised = int((changed & ~last_open).sum())
        if dropped or revised:
            self.stats["bars_dropped"] += dropped
            self.stats["bars_revised"] += revised

    def count(self) -> int:
        """Number of cached symbol/timeframe pairs."""
        return len(self._store)

    def symbols_cached(self, timeframe: str) -> List[str]:
        """Return list of symbols that have cache for this timeframe."""
        suffix = f"|{timeframe}"
        return [k.split("|")[0] for k in self._store if k.endswith(suffix)]

    # --- Persistence (pickle) ---

    def save_to_disk(self, path: Optional[Path] = None, force: bool = False) -> bool:
        """Serialize store to disk as pickle. Returns True if saved.

        Debounces saves to avoid I/O on every scan cycle (every 60s).
        Use force=True to bypass debounce (e.g., on shutdown).
        """
        path = path or _OHLCV_CACHE_PATH
        if not force and hasattr(self, "_last_save_ts"):
            elapsed = time.monotonic() - self._last_save_ts
            if elapsed < _SAVE_DEBOUNCE_SECS:
                return False

        if not self._store:
            return False

        try:
            # Atomic write: write to temp file then rename.
            # Version 2: pickle numpy arrays directly (no .tolist() copy).
            tmp_path = path.with_suffix(".pkl.tmp")
            with open(tmp_path, "wb") as f:
                pickle.dump({
                    "version": 3,
                    "history_targets": self._history_targets,
                    "observed_at": {key: time.time() - (time.monotonic() - updated) for key, updated in self._updated_at.items()},
                    "sources": self._sources,
                    "refetch": sorted(self._refetch),
                    "verified_at": self._verified_at,
                    "store": self._store,
                    "saved_at": time.time(),
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
            tmp_path.rename(path)

            self._last_save_ts = time.monotonic()
            logger.info(
                "OHLCVStore saved to disk: %d entries, %.1f KB",
                len(self._store),
                path.stat().st_size / 1024,
            )
            return True
        except Exception:
            logger.warning("OHLCVStore save failed", exc_info=True)
            return False

    def load_from_disk(self, path: Optional[Path] = None) -> bool:
        """Load store from pickle file on disk. Returns True if loaded.

        Applies staleness checks: entries older than _STALENESS_LIMIT
        are discarded (they'll trigger a full refetch on next scan). Every
        other entry is kept, and only the bars missing since its last bar are read.
        """
        path = path or _OHLCV_CACHE_PATH
        if not path.exists():
            logger.info("OHLCVStore: no cache file at %s (cold start)", path)
            return False

        try:
            with open(path, "rb") as f:
                payload = pickle.load(f)

            if not isinstance(payload, dict) or "store" not in payload:
                logger.warning("OHLCVStore: invalid cache file format, ignoring")
                return False

            version = payload.get("version", 0)
            saved_at = payload.get("saved_at", 0)
            store_data = payload["store"]
            self._history_targets = payload.get("history_targets", {})
            refetch = set(payload.get("refetch", ()))
            verified = payload.get("verified_at", {})
            cleaned = 0
            age_secs = time.time() - saved_at

            # Markets Hyperliquid renamed (ticker_renames): series stored under the old name
            # load under the current one; when both are stored the current one is kept.
            from ticker_renames import current_symbol
            renamed_keys = {}
            for key in store_data:
                sym, sep, rest = key.partition("|")
                new_key = f"{current_symbol(sym)}{sep}{rest}"
                if new_key != key:
                    renamed_keys[key] = new_key
                    target = self._history_targets.pop(key, None)
                    if target is not None and new_key not in store_data:
                        self._history_targets[new_key] = target
            if renamed_keys:
                logger.info("OHLCVStore: %d series stored under renamed tickers load under their current names",
                            len(renamed_keys))

            loaded = 0
            skipped = 0
            for key, ohlcv_lists in store_data.items():
                stored_key = key
                if key in renamed_keys:
                    if renamed_keys[key] in store_data:
                        skipped += 1
                        continue
                    key = renamed_keys[key]
                # Determine timeframe from key ("SYMBOL|TF")
                parts = key.split("|")
                if len(parts) != 2:
                    skipped += 1
                    continue
                tf = parts[1]

                # Skip if entire cache file is too old for this timeframe
                max_age = _STALENESS_LIMIT.get(tf, 24 * 3600)
                if age_secs > max_age:
                    skipped += 1
                    continue

                # v1 stored lists, v2 stores numpy arrays directly
                if version <= 1:
                    ohlcv = {
                        field: np.array(values, dtype=np.float64)
                        for field, values in ohlcv_lists.items()
                    }
                else:
                    ohlcv = {
                        field: np.asarray(values, dtype=np.float64)
                        for field, values in ohlcv_lists.items()
                    }

                # Validate minimum bar count
                bar_count = len(ohlcv.get("close", []))
                min_bars = _MIN_BARS.get(tf, 100)
                if bar_count == 0 or (bar_count < min_bars and self._history_targets.get(key, 0) < _DEFAULT_LIMIT.get(tf, 500)):
                    skipped += 1
                    continue

                # One-time purge: cross-quoted pairs (BASE/BTC, BASE/ETH) had
                # USD-price data cached due to the XMR/BTC=344 bug before the
                # ratio-fetch fix. Reject so they refetch cleanly.
                sym = parts[0]
                if "/" in sym:
                    sym_quote = sym.split("/", 1)[1]
                    if sym_quote in ("BTC", "ETH"):
                        closes = ohlcv.get("close", [])
                        if len(closes) > 0 and float(closes[-1]) >= 1.0:
                            # Real BASE/BTC or BASE/ETH ratios are almost
                            # always < 1. A value ≥ 1 means we cached the
                            # buggy USD price. Discard this entry.
                            skipped += 1
                            continue

                self._store[key] = ohlcv
                observed_at = payload.get("observed_at", {}).get(stored_key, saved_at)
                self._updated_at[key] = time.monotonic() - max(0, time.time() - observed_at)
                stored_source = payload.get("sources", {}).get(stored_key)
                if stored_source is not None:
                    self._sources[key] = stored_source
                if stored_key in refetch:
                    self._refetch.add(key)
                if stored_key in verified:
                    self._verified_at[key] = verified[stored_key]
                cleaned += self.clean_weekly(key)
                loaded += 1

            logger.info(
                "OHLCVStore loaded from disk: %d entries restored, %d skipped "
                "(stale/invalid), file age %.1f min",
                loaded, skipped, age_secs / 60,
            )
            if cleaned:
                logger.warning("OHLCVStore: dropped %d weekly bars off Hyperliquid's Thursday grid "
                               "(exchange weeks); %d weekly series will be read in full",
                               cleaned, sum(1 for k in self._refetch if k.endswith("|1w")))
            return loaded > 0
        except Exception:
            logger.warning("OHLCVStore load failed (will cold start)", exc_info=True)
            return False


# Module-level persistent OHLCV store — load from disk on startup
_ohlcv_store = OHLCVStore()
_ohlcv_store.load_from_disk()


def _seed_cache_from_store() -> int:
    """After a restart, count each stored series as fetched when it was last read, so the scanner
    does not read it again before its TTL or the next candle close (it did, for every market)."""
    n = 0
    for key in list(_ohlcv_store._updated_at):
        if key in _ohlcv_store._refetch:          # cleaned on load: read in full at the first chance
            continue
        symbol, _, timeframe = key.partition("|")
        observed = _ohlcv_store.observed_at(symbol, timeframe)
        if observed is not None:
            _cache.seed(symbol, timeframe, observed)
            n += 1
    return n


_seed_cache_from_store()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_ohlcv(raw: list) -> dict:
    """Convert the list-of-lists returned by CCXT into a dict of numpy arrays.

    Each sub-list is ``[timestamp, open, high, low, close, volume]``.
    """
    arr = np.array(raw, dtype=np.float64)
    return {
        "timestamp": arr[:, 0],
        "open":      arr[:, 1],
        "high":      arr[:, 2],
        "low":       arr[:, 3],
        "close":     arr[:, 4],
        "volume":    arr[:, 5],
    }


# ---------------------------------------------------------------------------
# Hyperliquid candle fallback (direct REST, no CCXT)
# ---------------------------------------------------------------------------

_HL_API_URL = "https://api.hyperliquid.xyz/info"


def _parse_hl_candles(candles: list) -> Optional[dict]:
    """Parse Hyperliquid candle JSON into numpy arrays."""
    if not candles or not isinstance(candles, list):
        return None
    rows = []
    for c in candles:
        try:
            rows.append([
                float(c["t"]),
                float(c["o"]),
                float(c["h"]),
                float(c["l"]),
                float(c["c"]),
                float(c["v"]),
            ])
        except (KeyError, ValueError, TypeError):
            continue
    if not rows:
        return None
    arr = np.array(rows, dtype=np.float64)
    return {
        "timestamp": arr[:, 0],
        "open":      arr[:, 1],
        "high":      arr[:, 2],
        "low":       arr[:, 3],
        "close":     arr[:, 4],
        "volume":    arr[:, 5],
    }


class HLRateLimited(Exception):
    """Hyperliquid kept answering 429 after every retry."""


# A 429 is retried after hl_calls.backoff_delay(attempt): 1-2 s, 2-4 s, 4-8 s, 8-16 s, and each
# retry waits for the shared budget again (which a 429 slows down for every consumer).
_HL_429_ATTEMPTS = 5
_HL_ERROR_ATTEMPTS = 3


async def _fetch_hl_candles(
    session: aiohttp.ClientSession,
    coin: str,
    timeframe: str,
    limit: Optional[int] = None,
    consumer: str = "scanner",
) -> Optional[dict]:
    """Fetch candles from Hyperliquid using a shared session.

    Parameters
    ----------
    session : shared aiohttp session (avoids per-call overhead)
    coin : HL coin name (e.g. "BTC", "xyz:GOLD")
    timeframe : "4h", "1d", or "1w"
    limit : number of candles
    consumer : whose share of the Hyperliquid weight budget pays for it (hl_calls)

    Raises HLRateLimited when every attempt was answered 429.
    """
    import hl_calls
    tf_ms = _TF_MS.get(timeframe)
    if tf_ms is None:
        return None

    if limit is None:
        limit = _DEFAULT_LIMIT.get(timeframe, 500)

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (limit * tf_ms)

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": timeframe,
            "startTime": start_ms,
            "endTime": now_ms,
        },
    }

    expected = hl_calls.candle_weight(limit)
    limited = errors = 0
    while True:
        await hl_calls.acquire(consumer, "candleSnapshot", expected)
        try:
            async with session.post(
                _HL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status == 429:
                    hl_calls.rate_limited(consumer)
                    limited += 1
                    if limited >= _HL_429_ATTEMPTS:
                        raise HLRateLimited(f"{coin} {timeframe}")
                    wait = hl_calls.backoff_delay(limited - 1)
                    logger.debug("HL 429 for %s/%s, retry %d in %.1fs", coin, timeframe, limited, wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    return None
                candles = await resp.json()
            if isinstance(candles, list):
                hl_calls.settle(consumer, "candleSnapshot", hl_calls.candle_weight(len(candles)) - expected)
            return _parse_hl_candles(candles)
        except HLRateLimited:
            raise
        except Exception as exc:
            logger.debug("HL candle fetch failed for %s/%s: %s", coin, timeframe, exc)
            errors += 1
            if errors < _HL_ERROR_ATTEMPTS:
                await asyncio.sleep(0.5)
                continue
            return None


def _hl_coin_name(symbol: str) -> str:
    """Convert scanner symbol 'BASE/USDT' → HL coin name, applying renames."""
    from hyperliquid_universe import MARKETS
    if symbol in MARKETS:
        return MARKETS[symbol]["coin"]
    from ticker_renames import hl_name
    return hl_name(symbol.split("/")[0])


def _ratio_ohlcv(base: Optional[dict], quote: Optional[dict]) -> Optional[dict]:
    """Compose OHLCV for BASE/QUOTE from two USD-denominated legs.

    Used to resolve cross-quoted pairs like XMR/BTC where Hyperliquid only
    offers USD candles. We align on timestamp, then divide: ohlc_ratio =
    ohlc_base / ohlc_quote. Volume is base-leg volume (quote-leg volume is
    in different units and can't be meaningfully combined).

    Returns None if either leg failed, was empty, or had no overlap.
    """
    if not isinstance(base, dict) or not isinstance(quote, dict):
        return None
    b_ts = base.get("timestamp")
    q_ts = quote.get("timestamp")
    if b_ts is None or q_ts is None:
        return None
    b_ts_arr = np.asarray(b_ts)
    q_ts_arr = np.asarray(q_ts)
    if len(b_ts_arr) == 0 or len(q_ts_arr) == 0:
        return None

    # Intersect timestamps so both legs have a value at every bar
    common, b_idx, q_idx = np.intersect1d(b_ts_arr, q_ts_arr, return_indices=True)
    if len(common) < 2:
        return None

    fields = ("open", "high", "low", "close")
    out: Dict[str, np.ndarray] = {"timestamp": common}
    for f in fields:
        b_arr = np.asarray(base.get(f, []))[b_idx] if f in base else None
        q_arr = np.asarray(quote.get(f, []))[q_idx] if f in quote else None
        if b_arr is None or q_arr is None or len(b_arr) != len(common):
            return None
        # Guard against zero in the quote leg (would produce inf)
        safe_q = np.where(q_arr == 0, np.nan, q_arr)
        out[f] = b_arr / safe_q

    # Volume: use base-leg volume; quote-leg is in different denomination
    if "volume" in base:
        b_vol = np.asarray(base["volume"])[b_idx]
        out["volume"] = b_vol
    else:
        out["volume"] = np.zeros_like(common, dtype=float)

    # Drop any bars that ended up with NaN (zero quote price)
    mask = np.isfinite(out["close"])
    if not np.all(mask):
        for k in out:
            out[k] = out[k][mask]
    if len(out["timestamp"]) < 2:
        return None

    return out


async def _fetch_ohlcv_hyperliquid(
    symbol: str,
    timeframe: str,
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch OHLCV from Hyperliquid (creates its own session — for single calls)."""
    coin = _hl_coin_name(symbol)
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            return await _fetch_hl_candles(session, coin, timeframe, limit)
    except HLRateLimited:
        raise
    except Exception as exc:
        logger.debug("Hyperliquid candle fetch failed for %s: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# Lightweight CEX OHLCV fallback — direct REST, no ccxt, no load_markets()
# ---------------------------------------------------------------------------

# Symbols already deepened via CEX fallback — skip on subsequent scan cycles
_ccxt_deepened: Dict[str, set] = {}  # timeframe → set of symbols

# Kept for memory_diag cleanup compat (now always empty)
_exchange_pool: Dict[str, "object"] = {}

_BINANCE_TF_MAP = {"4h": "4h", "1d": "1d", "1w": "1w"}
_BYBIT_TF_MAP = {"4h": "240", "1d": "D", "1w": "W"}


async def _fetch_ohlcv_binance(
    session: aiohttp.ClientSession, symbol: str, timeframe: str, limit: int,
) -> Optional[dict]:
    """Fetch OHLCV from Binance public API (no auth, no ccxt)."""
    pair = symbol.replace("/", "")  # BTC/USDT → BTCUSDT
    interval = _BINANCE_TF_MAP.get(timeframe)
    if not interval:
        return None
    url = f"https://api.binance.com/api/v3/klines?symbol={pair}&interval={interval}&limit={limit}"
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            raw = await resp.json()
        if not raw:
            return None
        timestamps = [float(r[0]) for r in raw]
        opens = [float(r[1]) for r in raw]
        highs = [float(r[2]) for r in raw]
        lows = [float(r[3]) for r in raw]
        closes = [float(r[4]) for r in raw]
        volumes = [float(r[5]) for r in raw]
        return {
            "timestamp": np.array(timestamps, dtype=np.float64),
            "open": np.array(opens, dtype=np.float64),
            "high": np.array(highs, dtype=np.float64),
            "low": np.array(lows, dtype=np.float64),
            "close": np.array(closes, dtype=np.float64),
            "volume": np.array(volumes, dtype=np.float64),
        }
    except Exception as exc:
        logger.debug("Binance OHLCV failed for %s: %s", symbol, exc)
        return None


async def _fetch_ohlcv_bybit(
    session: aiohttp.ClientSession, symbol: str, timeframe: str, limit: int,
) -> Optional[dict]:
    """Fetch OHLCV from Bybit public API (no auth, no ccxt)."""
    pair = symbol.replace("/", "")
    interval = _BYBIT_TF_MAP.get(timeframe)
    if not interval:
        return None
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={pair}&interval={interval}&limit={limit}"
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            body = await resp.json()
        rows = body.get("result", {}).get("list", [])
        if not rows:
            return None
        rows.reverse()  # Bybit returns newest-first
        timestamps = [float(r[0]) for r in rows]
        opens = [float(r[1]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        volumes = [float(r[5]) for r in rows]
        return {
            "timestamp": np.array(timestamps, dtype=np.float64),
            "open": np.array(opens, dtype=np.float64),
            "high": np.array(highs, dtype=np.float64),
            "low": np.array(lows, dtype=np.float64),
            "close": np.array(closes, dtype=np.float64),
            "volume": np.array(volumes, dtype=np.float64),
        }
    except Exception as exc:
        logger.debug("Bybit OHLCV failed for %s: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    limit: Optional[int] = None,
    *,
    offline: bool = False,
    closed_only: bool = False,
) -> Optional[dict]:
    """Fetch OHLCV data for a single *symbol*.

    Uses OHLCVStore for incremental updates:
    - Cold start: full fetch (600 bars)
    - Subsequent: fetch the bars missing since the last stored one (at least 2), merge

    Tries Hyperliquid first (primary), then CCXT exchanges as fallback.

    offline: the stored series only, no request (the first scan pass after a restart).
    closed_only: the caller reads closed bars only, so a series that already holds every closed
    bar is not read again (the scanner's weekly input).
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        logger.error("Unsupported timeframe '%s'. Use one of %s", timeframe, SUPPORTED_TIMEFRAMES)
        return None

    if offline:
        return _ohlcv_store.get(symbol, timeframe)

    # Determine fetch limit: full history or incremental update
    is_incremental = not _ohlcv_store.needs_full_fetch(symbol, timeframe)
    if closed_only and is_incremental and _ohlcv_store.complete(symbol, timeframe):
        return _ohlcv_store.get(symbol, timeframe)
    fetch_limit = (_ohlcv_store.bars_to_fetch(symbol, timeframe) if is_incremental
                   else max(limit or 0, _DEFAULT_LIMIT.get(timeframe, 500)))

    # Check TTL cache for very recent fetches (avoids redundant calls within same cycle)
    cached = _cache.get(symbol, timeframe)
    if cached is not None and is_incremental:
        return cached

    # Fetch from source
    data = None
    source = SOURCE_HL
    from hyperliquid_universe import MARKETS
    # The Binance/Bybit fallback is for markets Hyperliquid does not have. For a Hyperliquid market
    # (or a series already holding Hyperliquid bars) a failed read keeps the stored series: the
    # fallback's bars are another instrument's, and its weeks start on Monday instead of Thursday,
    # so merged in they corrupted the weekly band (two "weeks" per week, never replaced).
    cex_allowed = (MARKETS.get(symbol, {}).get("kind") is None
                   and _ohlcv_store.source(symbol, timeframe) != SOURCE_HL)
    if not cex_allowed:
        _ccxt_only.discard(symbol)
    if symbol in _ccxt_only and cex_allowed:
        source = SOURCE_CEX
        is_incremental = not _ohlcv_store.needs_full_fetch(symbol, timeframe, SOURCE_CEX)
        fetch_limit = (_ohlcv_store.bars_to_fetch(symbol, timeframe) if is_incremental
                       else max(limit or 0, _DEFAULT_LIMIT.get(timeframe, 500)))
        data = await _fetch_ohlcv_ccxt(symbol, timeframe, exchange_id, fetch_limit)
        if data is not None and not fallback_consistent(symbol, timeframe, data):
            # Back to Hyperliquid on the next call; keep the stored series meanwhile.
            _ccxt_only.discard(symbol)
            data = None
    else:
        try:
            data = await _fetch_ohlcv_hyperliquid(symbol, timeframe, fetch_limit)
        except HLRateLimited:
            # Hyperliquid is limiting this IP, not missing the market: keep the stored series
            # (no CEX fallback, which would also mark the symbol CCXT-only).
            return _ohlcv_store.get(symbol, timeframe)
        if data is None and cex_allowed:
            source = SOURCE_CEX
            is_incremental = not _ohlcv_store.needs_full_fetch(symbol, timeframe, SOURCE_CEX)
            fetch_limit = (_ohlcv_store.bars_to_fetch(symbol, timeframe) if is_incremental
                           else max(limit or 0, _DEFAULT_LIMIT.get(timeframe, 500)))
            data = await _fetch_ohlcv_ccxt(symbol, timeframe, exchange_id, fetch_limit)
            if data is not None and not fallback_consistent(symbol, timeframe, data):
                data = None
            if data is not None:
                _ccxt_only.add(symbol)
                logger.info("Learned CCXT-only: %s (total %d)", symbol, len(_ccxt_only))

    if data is None:
        # Return stale OHLCVStore data if available
        return _ohlcv_store.get(symbol, timeframe)

    # Merge into persistent store
    merged = _ohlcv_store.update(symbol, timeframe, data, full_fetch_target=fetch_limit if not is_incremental else None,
                                 source=source)

    # Also put in TTL cache to prevent re-fetching within same scan cycle
    _cache.put(symbol, timeframe, merged)

    return merged


def fallback_consistent(symbol: str, timeframe: str, data: dict,
                        reference: Optional[dict] = None) -> bool:
    """Whether Binance/Bybit bars may stand in for this symbol's Hyperliquid series.

    The REST fallback matches markets by ticker text alone ("PURR" + "USDT"), so it
    can return a different instrument, or the same one in another unit. For a
    Hyperliquid market the bars are accepted only when their closes agree with the
    series we already hold (within PRICE_SANITY_MAX_RATIO); with nothing to compare
    they are refused and Hyperliquid is tried again on the next cycle.
    """
    from hyperliquid_universe import MARKETS
    from price_sanity import series_consistent, within
    if reference is None:
        reference = _ohlcv_store.get(symbol, timeframe)
    verdict = series_consistent(reference, data)
    if verdict is None and reference is not None and len(reference.get("close", [])) and len(data.get("close", [])):
        verdict = within(data["close"][-1], reference["close"][-1])
    if verdict is None:
        verdict = symbol not in MARKETS
    if not verdict:
        logger.warning(
            "Rejected CEX fallback bars for %s (%s): they do not match the stored Hyperliquid series "
            "(last fallback close %s)", symbol, timeframe,
            data["close"][-1] if len(data.get("close", [])) else None,
        )
    return bool(verdict)


async def _fetch_ohlcv_ccxt(
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch OHLCV via lightweight direct REST calls (Binance → Bybit).

    No ccxt import, no load_markets() — saves ~50-80MB of RAM.
    """
    if limit is None:
        limit = _DEFAULT_LIMIT.get(timeframe, 500)

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Try Binance first (broadest coverage)
        data = await _fetch_ohlcv_binance(session, symbol, timeframe, limit)
        if data is not None:
            logger.debug("Fetched %d bars for %s (%s) from binance-rest",
                         len(data["close"]), symbol, timeframe)
            return data

        # Bybit fallback
        data = await _fetch_ohlcv_bybit(session, symbol, timeframe, limit)
        if data is not None:
            logger.debug("Fetched %d bars for %s (%s) from bybit-rest",
                         len(data["close"]), symbol, timeframe)
            return data

    logger.warning("CEX REST fallback failed for %s (%s)", symbol, timeframe)
    return None


async def fetch_batch(
    symbols: Optional[List[str]] = None,
    timeframe: str = "4h",
    skip_ccxt_fallback: bool = False,
) -> Dict[str, Optional[dict]]:
    """Fetch OHLCV data for many symbols concurrently.

    HL-first strategy in batches:
      - All symbols fetched from Hyperliquid in waves of 20 with pauses.
      - Any HL failures get a retry pass after cooldown.
      - Symbols with insufficient history are deepened via CCXT.
      - Remaining failures fall back to CCXT (Bybit → OKX → KuCoin → Gate).
    """
    if symbols is None:
        symbols = DEFAULT_SYMBOLS

    results: Dict[str, Optional[dict]] = {}

    # ── Phase 1: Check TTL cache + partition into full vs incremental ──
    uncached: List[str] = []
    full_fetch_syms: List[str] = []
    incr_fetch_syms: List[str] = []

    for sym in symbols:
        cached = _cache.get(sym, timeframe)
        if cached is not None:
            results[sym] = cached
        else:
            uncached.append(sym)
            if _ohlcv_store.needs_full_fetch(sym, timeframe):
                full_fetch_syms.append(sym)
            else:
                incr_fetch_syms.append(sym)

    logger.info(
        "Batch fetch %s: %d total, %d TTL-cached, %d full-fetch, %d incremental (2 bars)",
        timeframe, len(symbols), len(results), len(full_fetch_syms), len(incr_fetch_syms),
    )

    if not uncached:
        return results

    full_fetch_set = set(full_fetch_syms)

    # ── Phase 2: Fetch from HL in waves ──
    _WAVE_SIZE = 20
    _WAVE_PAUSE_S = 1.5  # 1.5s between waves — conservative for Railway
    hl_failures: List[str] = []

    timeout = aiohttp.ClientTimeout(total=180)
    connector = aiohttp.TCPConnector(limit=_MAX_CONCURRENT_FETCHES, keepalive_timeout=30)

    async def _hl_fetch(session: aiohttp.ClientSession, sym: str, limit: int) -> str:
        """Returns sym on success, raises on failure.

        For cross-quoted pairs (e.g. XMR/BTC, ETH/BTC) where HL only offers
        USD-denominated candles, fetch both legs and compute the ratio so
        the price stream reflects the true BASE/QUOTE value — not the
        BASE/USD price, which was the XMR/BTC=344 bug.
        """
        parts = sym.split("/")
        base = parts[0]
        quote = parts[1] if len(parts) > 1 else "USDT"

        from hyperliquid_universe import MARKETS
        if quote in ("USDT", "USD", "USDC", "USDH") or sym in MARKETS:
            # Direct USD fetch — HL native
            coin = _hl_coin_name(sym)
            data = await _fetch_hl_candles(session, coin, timeframe, limit=limit)
        else:
            # Cross-quote — fetch both legs vs USD and ratio them
            base_coin = _hl_coin_name(f"{base}/USDT")
            quote_coin = _hl_coin_name(f"{quote}/USDT")
            base_data, quote_data = await asyncio.gather(
                _fetch_hl_candles(session, base_coin, timeframe, limit=limit),
                _fetch_hl_candles(session, quote_coin, timeframe, limit=limit),
                return_exceptions=True,
            )
            data = _ratio_ohlcv(base_data, quote_data)

        if data is not None:
            # Merge into persistent store
            full = sym in full_fetch_set
            merged = _ohlcv_store.update(sym, timeframe, data, full_fetch_target=limit if full else None)
            _cache.put(sym, timeframe, merged)
            results[sym] = merged
            return sym
        raise ValueError(f"HL returned no data for {sym}")

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        # Fetch incremental symbols first (fast — only 2 bars each)
        if incr_fetch_syms:
            for i in range(0, len(incr_fetch_syms), _WAVE_SIZE):
                wave = incr_fetch_syms[i : i + _WAVE_SIZE]
                tasks = [asyncio.create_task(_hl_fetch(session, s, limit=_ohlcv_store.bars_to_fetch(s, timeframe)))
                         for s in wave]
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                for sym, outcome in zip(wave, outcomes):
                    if isinstance(outcome, Exception):
                        hl_failures.append(sym)
                if i + _WAVE_SIZE < len(incr_fetch_syms):
                    await asyncio.sleep(_WAVE_PAUSE_S * 0.5)  # Faster for small fetches

        # Then full-fetch symbols (cold start — 500 bars each)
        for i in range(0, len(full_fetch_syms), _WAVE_SIZE):
            wave = full_fetch_syms[i : i + _WAVE_SIZE]
            tasks = [asyncio.create_task(_hl_fetch(session, s, limit=_DEFAULT_LIMIT.get(timeframe, 500))) for s in wave]
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, outcome in zip(wave, outcomes):
                if isinstance(outcome, Exception):
                    hl_failures.append(sym)
            wave_ok = sum(1 for s in wave if s in results)
            logger.info(
                "HL full-fetch wave %d/%d: %d/%d OK",
                i // _WAVE_SIZE + 1,
                (len(full_fetch_syms) + _WAVE_SIZE - 1) // _WAVE_SIZE,
                wave_ok, len(wave),
            )
            if i + _WAVE_SIZE < len(full_fetch_syms):
                await asyncio.sleep(_WAVE_PAUSE_S)

    # ── Phase 3: Retry HL failures after cooldown ──
    if hl_failures:
        logger.warning(
            "HL failures (%d), retrying after 3s: %s",
            len(hl_failures), hl_failures[:10],
        )
        await asyncio.sleep(3.0)
        retry_fails: List[str] = []
        async with aiohttp.ClientSession(timeout=timeout) as session:
            _RT_WAVE = 10
            for i in range(0, len(hl_failures), _RT_WAVE):
                wave = hl_failures[i : i + _RT_WAVE]

                async def _rt_fetch(s: aiohttp.ClientSession, sym: str) -> str:
                    coin = _hl_coin_name(sym)
                    # Retry with appropriate limit
                    full = _ohlcv_store.needs_full_fetch(sym, timeframe)
                    rt_limit = _DEFAULT_LIMIT.get(timeframe, 500) if full else _ohlcv_store.bars_to_fetch(sym, timeframe)
                    data = await _fetch_hl_candles(s, coin, timeframe, limit=rt_limit)
                    if data is not None:
                        merged = _ohlcv_store.update(sym, timeframe, data, full_fetch_target=rt_limit if full else None)
                        _cache.put(sym, timeframe, merged)
                        results[sym] = merged
                        return sym
                    raise ValueError(f"HL retry failed for {sym}")

                tasks = [asyncio.create_task(_rt_fetch(session, sym)) for sym in wave]
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                for sym, outcome in zip(wave, outcomes):
                    if isinstance(outcome, Exception):
                        retry_fails.append(sym)
                if i + _RT_WAVE < len(hl_failures):
                    await asyncio.sleep(1.0)

        if retry_fails:
            logger.warning("Final HL failures (%d): %s", len(retry_fails), retry_fails[:10])

    # ── Phase 4: CCXT fallback for failures + shallow HL data ──
    # Only check symbols we haven't already deepened in a previous cycle.
    if not skip_ccxt_fallback:
        min_bars = _MIN_BARS.get(timeframe, 100)
        deepened = _ccxt_deepened.setdefault(timeframe, set())

        # Collect symbols that failed OR have insufficient HL history
        need_ccxt: List[str] = []
        from hyperliquid_universe import MARKETS
        for sym in uncached:
            if MARKETS.get(sym, {}).get("kind") == "spot":
                continue
            if sym in deepened:
                continue  # Already tried CCXT for this symbol+timeframe
            # A Hyperliquid market takes fallback bars only as older 4h/1d history before its first
            # Hyperliquid bar (OHLCVStore.update): not for a failed read, and never weekly.
            hl_market = sym in MARKETS or _ohlcv_store.source(sym, timeframe) == SOURCE_HL
            if hl_market and (timeframe == "1w" or sym not in results):
                continue
            if sym not in results:
                need_ccxt.append(sym)
            elif results[sym] is not None:
                bar_count = len(results[sym].get("close", []))
                if bar_count < min_bars:
                    need_ccxt.append(sym)
                    logger.info("Shallow HL data for %s (%d bars < %d min), trying CCXT", sym, bar_count, min_bars)

        if need_ccxt:
            logger.info("CCXT fallback for %d symbols (failures + shallow)", len(need_ccxt))
            for sym in need_ccxt:
                data = await _fetch_ohlcv_ccxt(sym, timeframe, "bybit")
                deepened.add(sym)  # Mark as tried regardless of outcome
                if data is not None and not fallback_consistent(sym, timeframe, data, results.get(sym)):
                    data = None
                if data is not None:
                    hl_count = len(results.get(sym, {}).get("close", [])) if results.get(sym) else 0
                    ccxt_count = len(data.get("close", []))
                    # Only replace if CCXT has more data
                    if ccxt_count > hl_count:
                        merged = _ohlcv_store.update(sym, timeframe, data, full_fetch_target=_DEFAULT_LIMIT.get(timeframe, 500),
                                                     source=SOURCE_CEX)
                        _cache.put(sym, timeframe, merged)
                        results[sym] = merged
                        logger.info("CCXT deepened %s: %d → %d bars", sym, hl_count, ccxt_count)

    # Fill None for any remaining
    missing = []
    for sym in symbols:
        if sym not in results:
            results[sym] = None
            missing.append(sym)

    success = sum(1 for v in results.values() if v is not None)
    logger.info(
        "Batch %s complete: %d/%d success. Missing: %s",
        timeframe, success, len(symbols), missing[:10] if missing else "none",
    )

    return results


def get_cache() -> DataCache:
    """Return the module-level cache (useful for inspection / testing)."""
    return _cache


def get_data_source_info() -> dict:
    """Return diagnostic info about data source routing."""
    return {
        "binance_loaded": _binance_symbols is not None and len(_binance_symbols) > 0,
        "binance_symbol_count": len(_binance_symbols) if _binance_symbols else 0,
        "ccxt_only_count": len(_ccxt_only),
        "ccxt_only_symbols": sorted(list(_ccxt_only))[:20],
        "cache_entries": len(_cache),
        "ohlcv_store_entries": _ohlcv_store.count(),
        # Bars a fresh read replaced or dropped, fallback bars kept out of Hyperliquid series, and
        # the background check of stored series against Hyperliquid (verify_store).
        "ohlcv_store_repairs": dict(_ohlcv_store.stats),
        "ohlcv_store_full_reads_pending": len(_ohlcv_store._refetch),
        "ohlcv_store_verification": dict(_verify_status),
    }


# ---------------------------------------------------------------------------
# Stored series checked against Hyperliquid
# ---------------------------------------------------------------------------
# Each stored Hyperliquid series is read in full once per VERIFY_INTERVAL_S and merged; the fetched
# range is authoritative (OHLCVStore.update), so bars from another source or grid are dropped,
# revised bars replaced and missing weeks filled. It runs in the background on the lowest-priority
# share of the shared weight budget (hl_calls "cohorts"), weekly series first. The time of each
# series' last check is saved with the store: a restart resumes where it stopped, and a checked
# series is not read again before the interval, so the first pass after a deploy is the one-time
# repair and later passes are the ongoing check.

VERIFY_INTERVAL_S = 7 * 86400
VERIFY_CONSUMER = "cohorts"
_VERIFY_START_DELAY_S = 180      # after the first scan passes
_VERIFY_IDLE_S = 3600
_verify_status: Dict[str, object] = {"running": False, "checked": 0, "changed": 0, "due": 0,
                                     "last_pass_at": None}


def verify_due(now: Optional[float] = None) -> List[str]:
    """Stored Hyperliquid-market series not checked within VERIFY_INTERVAL_S (weekly, then 1d, then 4h)."""
    from hyperliquid_universe import MARKETS
    now = time.time() if now is None else now
    due = []
    for tf in ("1w", "1d", "4h"):
        for key in sorted(k for k in _ohlcv_store._store if k.endswith("|" + tf)):
            symbol = key.partition("|")[0]
            if _ohlcv_store.source(symbol, tf) != SOURCE_HL or MARKETS.get(symbol, {}).get("kind") is None:
                continue
            if now - _ohlcv_store._verified_at.get(key, 0.0) >= VERIFY_INTERVAL_S:
                due.append(key)
    return due


async def verify_store(consumer: str = VERIFY_CONSUMER, max_series: Optional[int] = None) -> dict:
    """One pass over the series due for a check. Returns {"checked", "changed", "due"}."""
    keys = verify_due()
    if max_series is not None:
        keys = keys[:max_series]
    checked = changed = 0
    _verify_status.update(running=True, due=len(keys))
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for key in keys:
                symbol, _, tf = key.partition("|")
                stored = _ohlcv_store.get(symbol, tf)
                if stored is None:
                    continue
                limit = max(len(stored["timestamp"]), _DEFAULT_LIMIT.get(tf, 500))
                try:
                    data = await _fetch_hl_candles(session, _hl_coin_name(symbol), tf, limit, consumer=consumer)
                except HLRateLimited:
                    break                               # the next pass resumes here
                if data is None:
                    continue
                before = _ohlcv_store.stats["bars_revised"] + _ohlcv_store.stats["bars_dropped"]
                n_before = len(stored["timestamp"])
                merged = _ohlcv_store.update(symbol, tf, data, full_fetch_target=limit)
                _ohlcv_store._verified_at[key] = time.time()
                diff = (_ohlcv_store.stats["bars_revised"] + _ohlcv_store.stats["bars_dropped"] - before
                        + max(0, len(merged["timestamp"]) - n_before))
                checked += 1
                if diff:
                    changed += 1
                    logger.info("Stored %s %s checked against Hyperliquid: %d bars replaced, dropped or added",
                                symbol, tf, diff)
                _verify_status.update(checked=_verify_status["checked"] + 1,
                                      changed=_verify_status["changed"] + (1 if diff else 0))
    finally:
        _verify_status.update(running=False, last_pass_at=time.time())
    if checked:
        logger.info("OHLCVStore check against Hyperliquid: %d series read, %d changed", checked, changed)
        _ohlcv_store.save_to_disk()
    return {"checked": checked, "changed": changed, "due": len(keys)}


async def run_store_verification() -> None:
    """Background loop for verify_store (OHLCV_VERIFY_ENABLED=0 turns it off)."""
    if os.environ.get("OHLCV_VERIFY_ENABLED", "1").lower() in ("0", "false", "no"):
        return
    await asyncio.sleep(_VERIFY_START_DELAY_S)
    while True:
        try:
            await verify_store()
        except Exception:
            logger.warning("OHLCVStore check against Hyperliquid failed", exc_info=True)
        await asyncio.sleep(_VERIFY_IDLE_S)


# ---------------------------------------------------------------------------
# TradFi / HIP-3 symbols (trade.xyz on Hyperliquid)
# ---------------------------------------------------------------------------

_DEFAULT_TRADFI_SYMBOLS: List[dict] = [
    # Macro indicators only — crypto context signals
    {"coin": "GOLD",      "symbol": "GOLD/USD",      "name": "Gold",              "category": "Commodities",  "yf": "GC=F"},
    {"coin": "SILVER",    "symbol": "SILVER/USD",     "name": "Silver",            "category": "Commodities",  "yf": "SI=F"},
    {"coin": "SP500",     "symbol": "SP500/USD",      "name": "S&P 500",           "category": "Indices",      "yf": "ES=F"},
    {"coin": "DXY",       "symbol": "DXY/USD",        "name": "US Dollar Index",   "category": "Indices",      "yf": "DX-Y.NYB"},
    {"coin": "VIX",       "symbol": "VIX/USD",        "name": "Volatility Index",  "category": "Indices",      "yf": "^VIX"},
    {"coin": "CL",        "symbol": "CL/USD",         "name": "WTI Crude Oil",     "category": "Commodities",  "yf": "CL=F"},
    {"coin": "BRENTOIL",  "symbol": "BRENTOIL/USD",   "name": "Brent Crude Oil",   "category": "Commodities",  "yf": "BZ=F"},
]

_TRADFI_JSON = Path(__file__).parent / "tradfi_symbols.json"


def _load_tradfi_symbols() -> List[dict]:
    """Load TradFi symbols from JSON file, falling back to defaults.

    If the JSON file has fewer symbols than defaults (e.g., after an update
    that added new instruments), merge missing defaults into the loaded list.
    """
    if _TRADFI_JSON.exists():
        try:
            with open(_TRADFI_JSON) as f:
                loaded = json.load(f)
            # Merge any new defaults that aren't in the saved file
            existing_coins = {s["coin"] for s in loaded}
            new_defaults = [s for s in _DEFAULT_TRADFI_SYMBOLS if s["coin"] not in existing_coins]
            if new_defaults:
                loaded.extend(new_defaults)
                logger.info("TradFi: merged %d new default symbols into saved list", len(new_defaults))
                _save_tradfi_symbols(loaded)
            return loaded
        except Exception:
            pass
    return list(_DEFAULT_TRADFI_SYMBOLS)


def _save_tradfi_symbols(symbols: List[dict]) -> None:
    """Persist TradFi symbols to JSON (atomic write)."""
    tmp = _TRADFI_JSON.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(symbols, f, indent=2)
    tmp.rename(_TRADFI_JSON)


def _rebuild_tradfi_lookups() -> None:
    """Rebuild all module-level lookup dicts from current TRADFI_SYMBOLS."""
    global TRADFI_COIN_MAP, TRADFI_SYMBOL_LIST, TRADFI_COIN_TO_SYMBOL
    global TRADFI_SYMBOL_TO_COIN, TRADFI_SYMBOL_TO_YF
    TRADFI_COIN_MAP = {s["coin"]: s for s in TRADFI_SYMBOLS}
    TRADFI_SYMBOL_LIST = [s["symbol"] for s in TRADFI_SYMBOLS]
    TRADFI_COIN_TO_SYMBOL = {s["coin"]: s["symbol"] for s in TRADFI_SYMBOLS}
    TRADFI_SYMBOL_TO_COIN = {s["symbol"]: s["coin"] for s in TRADFI_SYMBOLS}
    TRADFI_SYMBOL_TO_YF = {s["symbol"]: s["yf"] for s in TRADFI_SYMBOLS}


TRADFI_SYMBOLS: List[dict] = _load_tradfi_symbols()

# Quick lookups
TRADFI_COIN_MAP: Dict[str, dict] = {s["coin"]: s for s in TRADFI_SYMBOLS}
TRADFI_SYMBOL_LIST: List[str] = [s["symbol"] for s in TRADFI_SYMBOLS]
TRADFI_COIN_TO_SYMBOL: Dict[str, str] = {s["coin"]: s["symbol"] for s in TRADFI_SYMBOLS}
TRADFI_SYMBOL_TO_COIN: Dict[str, str] = {s["symbol"]: s["coin"] for s in TRADFI_SYMBOLS}
TRADFI_SYMBOL_TO_YF: Dict[str, str] = {s["symbol"]: s["yf"] for s in TRADFI_SYMBOLS}


def add_tradfi_symbol(coin: str, name: str, category: str, yf_ticker: str) -> dict:
    """Add a TradFi symbol and persist. Returns the new entry."""
    import re
    coin = re.sub(r'[/-](?:USDC?|USDT|USD)$', '', coin.strip(), flags=re.IGNORECASE).upper()
    if any(s["coin"] == coin for s in TRADFI_SYMBOLS):
        raise ValueError(f"{coin} already exists")
    entry = {
        "coin": coin,
        "symbol": f"{coin}/USD",
        "name": name,
        "category": category,
        "yf": yf_ticker,
    }
    TRADFI_SYMBOLS.append(entry)
    _save_tradfi_symbols(TRADFI_SYMBOLS)
    _rebuild_tradfi_lookups()
    return entry


def remove_tradfi_symbol(coin: str) -> bool:
    """Remove a TradFi symbol by coin ticker. Returns True if removed."""
    coin = coin.upper()
    before = len(TRADFI_SYMBOLS)
    TRADFI_SYMBOLS[:] = [s for s in TRADFI_SYMBOLS if s["coin"] != coin]
    if len(TRADFI_SYMBOLS) == before:
        return False
    _save_tradfi_symbols(TRADFI_SYMBOLS)
    _rebuild_tradfi_lookups()
    return True


def get_tradfi_symbols() -> List[dict]:
    """Return the current TradFi symbol list."""
    return list(TRADFI_SYMBOLS)


# ---------------------------------------------------------------------------
# yfinance — TradFi data with deep history
# ---------------------------------------------------------------------------

def _yf_period_for_timeframe(timeframe: str) -> tuple[str, str]:
    """Return (yfinance period, yfinance interval) for a scanner timeframe."""
    import yf_source
    return yf_source.period_for(timeframe)


def _parse_yf_to_ohlcv(df, timeframe: str) -> Optional[dict]:
    """Convert a yfinance DataFrame into the standard OHLCV dict (yf_source.parse)."""
    import yf_source
    return yf_source.parse(df, timeframe)


_YF_CHILD_TIMEOUT_S = 180


class _YFDownloadFailed(Exception):
    """The download itself failed (Yahoo down or slow): reported, not retried in this process."""


def _yf_failure_lines(stderr: bytes) -> str:
    lines = [ln.strip() for ln in stderr.decode(errors="replace").splitlines()
             if ("Failed" in ln or "Error" in ln) and "Warning" not in ln]
    return " | ".join(lines[-3:])[:300]


async def _yf_download(tickers: List[str], timeframe: str) -> Dict[str, Optional[dict]]:
    """yf_source.download_batch in a short-lived child process, so yfinance and pandas (~65 MB
    of RSS for the life of a process) never load here, and the pages of the files the child read
    are dropped once it exits. In-process only if the child cannot be started or crashes.
    Raises _YFDownloadFailed when the download itself failed or timed out."""
    import sys
    import yf_source
    if os.environ.get("YF_SUBPROCESS", "1").strip().lower() not in ("0", "false", "no", "off"):
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(Path(__file__).with_name("yf_source.py")), timeframe, *tickers,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=_YF_CHILD_TIMEOUT_S)
            except asyncio.TimeoutError:
                raise _YFDownloadFailed(f"no answer within {_YF_CHILD_TIMEOUT_S} s")
            if proc.returncode == 0:
                answer = yf_source.decode(out.decode())
                await asyncio.to_thread(_drop_cached_pages, answer.get("files") or [])
                failures = _yf_failure_lines(err)
                if not answer.get("ok"):
                    raise _YFDownloadFailed(answer.get("error") or failures or "download failed")
                if failures:
                    logger.warning("yfinance: %s", failures)
                return answer["bars"]
            if proc.returncode < 0:
                raise _YFDownloadFailed(f"child killed by signal {-proc.returncode}")
            logger.warning("yfinance child exited with %s (%s); downloading in-process",
                           proc.returncode, _yf_failure_lines(err) or "no error text")
        except _YFDownloadFailed:
            raise
        except Exception as exc:
            logger.warning("yfinance child could not run (%r); downloading in-process", exc)
        finally:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, yf_source.download_batch, tickers, timeframe)


def _drop_cached_pages(paths: List[str]) -> None:
    try:
        import memlog
        for p in paths:
            memlog.drop_file_cache(p)
    except Exception as exc:
        logger.debug("yfinance child: page-cache drop failed: %s", exc)


async def fetch_ohlcv_yfinance(
    symbol: str,
    timeframe: str,
) -> Optional[dict]:
    """Fetch OHLCV for a TradFi symbol using yfinance.

    Runs the blocking yfinance call in a thread executor.
    """
    cached = _cache.get(symbol, timeframe)
    if cached is not None:
        return cached

    yf_ticker = TRADFI_SYMBOL_TO_YF.get(symbol)
    if yf_ticker is None:
        logger.warning("No yfinance ticker for %s", symbol)
        return None

    loop = asyncio.get_running_loop()
    try:
        import yfinance as yf
        period, interval = _yf_period_for_timeframe(timeframe)

        def _download():
            t = yf.Ticker(yf_ticker)
            return t.history(period=period, interval=interval)

        df = await loop.run_in_executor(None, _download)
        data = _parse_yf_to_ohlcv(df, timeframe)
        if data is not None:
            _cache.put(symbol, timeframe, data)
            logger.debug("yfinance: %s (%s) → %d bars", symbol, timeframe, len(data["close"]))
        return data
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s (%s): %s", symbol, timeframe, exc)
        return None


async def fetch_batch_yfinance(
    timeframe: str = "1d",
) -> Dict[str, Optional[dict]]:
    """Fetch OHLCV for all TradFi symbols using yfinance.

    Downloads all tickers in a single yf.download() call for efficiency,
    then parses each into the standard OHLCV dict format.
    """
    results: Dict[str, Optional[dict]] = {}

    # Check cache first
    uncached_symbols: List[str] = []
    uncached_tickers: List[str] = []
    for sym_info in TRADFI_SYMBOLS:
        symbol = sym_info["symbol"]
        cached = _cache.get(symbol, timeframe)
        if cached is not None:
            results[symbol] = cached
        else:
            uncached_symbols.append(symbol)
            uncached_tickers.append(sym_info["yf"])

    if not uncached_symbols:
        return results

    logger.info("yfinance batch: fetching %d/%d symbols for %s", len(uncached_symbols), len(TRADFI_SYMBOLS), timeframe)

    try:
        downloaded = await _yf_download(uncached_tickers, timeframe)
        for symbol, yf_ticker in zip(uncached_symbols, uncached_tickers):
            data = downloaded.get(yf_ticker)
            if data is not None:
                _cache.put(symbol, timeframe, data)
            results[symbol] = data

    except Exception as exc:
        logger.error("yfinance batch download failed: %s", exc)

    # Fill None for missing
    for sym_info in TRADFI_SYMBOLS:
        if sym_info["symbol"] not in results:
            results[sym_info["symbol"]] = None

    ok = sum(1 for v in results.values() if v is not None)
    logger.info("yfinance batch %s: %d/%d success", timeframe, ok, len(TRADFI_SYMBOLS))
    return results


# Keep HIP-3 functions for backward compatibility (live price, single fetch)
async def fetch_ohlcv_hip3(
    symbol: str,
    timeframe: str,
    limit: Optional[int] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[dict]:
    """Fetch OHLCV from Hyperliquid for a HIP-3 (trade.xyz) asset."""
    cached = _cache.get(symbol, timeframe)
    if cached is not None:
        return cached

    if limit is None:
        limit = _DEFAULT_LIMIT.get(timeframe, 500)

    coin = TRADFI_SYMBOL_TO_COIN.get(symbol)
    if coin is None:
        coin = symbol.split("/")[0]

    hl_coin = f"xyz:{coin}"

    try:
        if session is not None:
            data = await _fetch_hl_candles(session, hl_coin, timeframe, limit)
        else:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                data = await _fetch_hl_candles(s, hl_coin, timeframe, limit)
    except HLRateLimited:
        data = None

    if data is not None:
        _cache.put(symbol, timeframe, data)
    return data


async def fetch_batch_hip3(
    timeframe: str = "4h",
) -> Dict[str, Optional[dict]]:
    """Fetch OHLCV data for all TradFi HIP-3 symbols concurrently.

    Uses a single shared aiohttp session for all requests.
    """
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)
    results: Dict[str, Optional[dict]] = {}
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=_MAX_CONCURRENT_FETCHES, keepalive_timeout=30)

    async def _guarded_fetch(session: aiohttp.ClientSession, sym: str) -> None:
        async with semaphore:
            results[sym] = await fetch_ohlcv_hip3(sym, timeframe, session=session)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [
            asyncio.create_task(_guarded_fetch(session, sym))
            for sym in TRADFI_SYMBOL_LIST
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results
