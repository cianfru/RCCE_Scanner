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
import ccxt.async_support as ccxt
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
    "FET/USDT", "RNDR/USDT", "TAO/USDT",
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
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "MATIC/USDT",
    "NEAR/USDT", "UNI/USDT", "ATOM/USDT", "FIL/USDT", "APT/USDT",
    # L2 / New L1
    "ARB/USDT", "OP/USDT", "SUI/USDT", "SEI/USDT", "INJ/USDT",
    "TIA/USDT",
    # Meme
    "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "WIF/USDT", "BONK/USDT",
    "FLOKI/USDT", "MEME/USDT",
    # AI / Compute
    "FET/USDT", "RNDR/USDT", "TAO/USDT",
    # DeFi
    "AAVE/USDT", "SKY/USDT", "LDO/USDT", "CRV/USDT", "SNX/USDT",
    "COMP/USDT", "RUNE/USDT",
    # Infrastructure / Misc
    "STX/USDT", "ICP/USDT", "HBAR/USDT", "VET/USDT", "ALGO/USDT",
    "FTM/USDT", "SAND/USDT", "MANA/USDT", "AXS/USDT", "GMT/USDT",
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

# Minimum candle counts per timeframe for full z-score warm-up.
# Z-score needs 2 × LEN_LONG (400) bars; we add margin for the
# inner SMA/stdev to normalise over a representative window.
_DEFAULT_LIMIT: Dict[str, int] = {
    "4h": 250,     # ~42 days — z-score needs 200 (LEN_LONG), 50 margin
    "1d": 300,     # ~10 months — full warmup + margin, was 600
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

# Hyperliquid coin name mapping — handles rebrands and HL-specific names.
# Key: CCXT base (from "BASE/USDT"), Value: HL coin name.
_HL_COIN_MAP: Dict[str, str] = {
    "MATIC": "POL",       # Polygon rebrand
    "SHIB":  "kSHIB",     # HL uses kSHIB
    "PEPE":  "kPEPE",     # HL uses kPEPE
    "BONK":  "kBONK",     # HL uses kBONK
    "FLOKI": "kFLOKI",    # HL uses kFLOKI
    "RNDR":  "RENDER",    # Render rebrand
    "FTM":   "S",         # Sonic rebrand
}


# ---------------------------------------------------------------------------
# DataCache -- simple in-memory TTL cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    data: dict
    expires_at: float


class DataCache:
    """Thread-unsafe, in-memory TTL cache keyed by (symbol, timeframe)."""

    def __init__(self) -> None:
        self._store: Dict[str, _CacheEntry] = {}

    @staticmethod
    def _key(symbol: str, timeframe: str) -> str:
        return f"{symbol}|{timeframe}"

    def get(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Return cached OHLCV dict or *None* if missing / expired."""
        key = self._key(symbol, timeframe)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.data

    def put(self, symbol: str, timeframe: str, data: dict, ttl: Optional[int] = None) -> None:
        """Store *data* with a TTL derived from the timeframe (or explicit)."""
        if ttl is None:
            ttl = _CACHE_TTL.get(timeframe, 300)
        key = self._key(symbol, timeframe)
        self._store[key] = _CacheEntry(data=data, expires_at=time.monotonic() + ttl)

    def invalidate(self, symbol: str, timeframe: str) -> None:
        """Remove a single entry."""
        self._store.pop(self._key(symbol, timeframe), None)

    def clear(self) -> None:
        """Drop every cached entry."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# Module-level cache instance shared across calls
_cache = DataCache()


# ---------------------------------------------------------------------------
# OHLCVStore -- persistent OHLCV cache (append-only, no TTL expiration)
# ---------------------------------------------------------------------------

# Maximum age before forcing a full refetch (handles restarts / gaps)
_STALENESS_LIMIT: Dict[str, float] = {
    "4h": 24 * 3600,     # 24 hours
    "1d": 7 * 86400,     # 7 days
    "1w": 30 * 86400,    # 30 days
}

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


class OHLCVStore:
    """Persistent in-memory OHLCV cache. Stores full history arrays and
    updates them incrementally by appending new bars.

    Unlike DataCache (TTL-based), this store never expires. On each scan:
    - If no cache exists: full fetch (cold start)
    - If cache exists: fetch only 2 latest bars, merge into cached array
    """

    def __init__(self) -> None:
        self._store: Dict[str, dict] = {}       # key: "SYMBOL|TF" → OHLCV dict
        self._updated_at: Dict[str, float] = {}  # key → monotonic time

    @staticmethod
    def _key(symbol: str, timeframe: str) -> str:
        return f"{symbol}|{timeframe}"

    def get(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Return cached OHLCV arrays or None if not stored."""
        return self._store.get(self._key(symbol, timeframe))

    def invalidate(self, symbol: str, timeframe: str) -> None:
        """Remove a single entry, forcing a full refetch next call."""
        key = self._key(symbol, timeframe)
        self._store.pop(key, None)
        self._updated_at.pop(key, None)

    def needs_full_fetch(self, symbol: str, timeframe: str) -> bool:
        """True if no cache or cache is stale (too old for incremental update)."""
        key = self._key(symbol, timeframe)
        if key not in self._store:
            return True
        updated = self._updated_at.get(key, 0.0)
        max_age = _STALENESS_LIMIT.get(timeframe, 24 * 3600)
        if time.monotonic() - updated > max_age:
            return True
        # Also check minimum bar count
        cached = self._store[key]
        bar_count = len(cached.get("close", []))
        min_bars = _MIN_BARS.get(timeframe, 100)
        return bar_count < min_bars

    def update(self, symbol: str, timeframe: str, new_data: dict,
               max_bars: Optional[int] = None) -> dict:
        """Merge new bars into cached array. Returns the full updated array.

        Logic:
        1. No cache → store as-is (cold start)
        2. New latest timestamp == cached latest → update last bar in-place
        3. New latest timestamp > cached latest → append new closed bars
        """
        key = self._key(symbol, timeframe)
        if max_bars is None:
            max_bars = _DEFAULT_LIMIT.get(timeframe, 500)

        new_ts = new_data.get("timestamp")
        if new_ts is None or len(new_ts) == 0:
            # Empty new data — return existing cache or None
            return self._store.get(key, new_data)

        cached = self._store.get(key)

        if cached is None or len(cached.get("timestamp", [])) == 0:
            # Cold start — store full array
            self._store[key] = new_data
            self._updated_at[key] = time.monotonic()
            return new_data

        cached_ts = cached["timestamp"]
        new_latest_ts = float(new_ts[-1])
        cached_latest_ts = float(cached_ts[-1])

        fields = ["timestamp", "open", "high", "low", "close", "volume"]

        if new_latest_ts == cached_latest_ts:
            # Same candle — update last bar in-place (live candle update)
            for f in fields:
                if f in new_data and f in cached:
                    cached[f][-1] = new_data[f][-1]
            self._updated_at[key] = time.monotonic()
            return cached

        if new_latest_ts > cached_latest_ts:
            # New bar(s) have closed — find which bars to append
            # Filter new_data to only bars newer than cached latest
            mask = new_ts > cached_latest_ts
            if not np.any(mask):
                # Edge case: timestamps don't overlap as expected
                # Update last bar and return
                for f in fields:
                    if f in new_data and f in cached:
                        cached[f][-1] = new_data[f][-1]
                self._updated_at[key] = time.monotonic()
                return cached

            # First, update the last cached bar with the matching bar from new_data
            # (in case the previously-live candle has now closed with final values)
            match_mask = new_ts == cached_latest_ts
            if np.any(match_mask):
                idx = np.where(match_mask)[0][0]
                for f in fields:
                    if f in new_data and f in cached:
                        cached[f][-1] = new_data[f][idx]

            # Append truly new bars
            new_bars_mask = new_ts > cached_latest_ts
            for f in fields:
                if f in new_data and f in cached:
                    new_slice = new_data[f][new_bars_mask]
                    cached[f] = np.concatenate([cached[f], new_slice])

            # Trim to max_bars (drop oldest)
            total = len(cached["timestamp"])
            if total > max_bars:
                trim = total - max_bars
                for f in fields:
                    if f in cached:
                        cached[f] = cached[f][trim:]

            self._store[key] = cached
            self._updated_at[key] = time.monotonic()
            return cached

        # new_latest_ts < cached_latest_ts — stale fetch, ignore
        return cached

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
            # Convert numpy arrays to lists for safe pickling across numpy versions
            serializable = {}
            for key, ohlcv in self._store.items():
                serializable[key] = {
                    field: arr.tolist() if hasattr(arr, "tolist") else arr
                    for field, arr in ohlcv.items()
                }

            # Atomic write: write to temp file then rename
            tmp_path = path.with_suffix(".pkl.tmp")
            with open(tmp_path, "wb") as f:
                pickle.dump({
                    "version": 1,
                    "store": serializable,
                    "saved_at": time.time(),  # wall clock for staleness checks
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
        are discarded (they'll trigger a full refetch on next scan).
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
            age_secs = time.time() - saved_at

            loaded = 0
            skipped = 0
            for key, ohlcv_lists in store_data.items():
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

                # Convert lists back to numpy arrays
                ohlcv = {
                    field: np.array(values, dtype=np.float64)
                    for field, values in ohlcv_lists.items()
                }

                # Validate minimum bar count
                bar_count = len(ohlcv.get("close", []))
                min_bars = _MIN_BARS.get(tf, 100)
                if bar_count < min_bars:
                    skipped += 1
                    continue

                # One-time purge: cross-quoted pairs (BASE/BTC, BASE/ETH) had
                # USD-price data cached due to the XMR/BTC=344 bug before the
                # ratio-fetch fix. Reject so they refetch cleanly.
                sym = parts[0]
                if "/" in sym:
                    sym_quote = sym.split("/", 1)[1]
                    if sym_quote not in ("USDT", "USD"):
                        closes = ohlcv.get("close", [])
                        if len(closes) > 0 and float(closes[-1]) >= 1.0:
                            # Real BASE/BTC or BASE/ETH ratios are almost
                            # always < 1. A value ≥ 1 means we cached the
                            # buggy USD price. Discard this entry.
                            skipped += 1
                            continue

                self._store[key] = ohlcv
                self._updated_at[key] = time.monotonic()
                loaded += 1

            logger.info(
                "OHLCVStore loaded from disk: %d entries restored, %d skipped "
                "(stale/invalid), file age %.1f min",
                loaded, skipped, age_secs / 60,
            )
            return loaded > 0
        except Exception:
            logger.warning("OHLCVStore load failed (will cold start)", exc_info=True)
            return False


# Module-level persistent OHLCV store — load from disk on startup
_ohlcv_store = OHLCVStore()
_ohlcv_store.load_from_disk()


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

# Timeframe → milliseconds per candle (for calculating startTime)
_TF_MS: Dict[str, int] = {
    "4h": 4 * 3600 * 1000,
    "1d": 86400 * 1000,
    "1w": 7 * 86400 * 1000,
}


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


async def _fetch_hl_candles(
    session: aiohttp.ClientSession,
    coin: str,
    timeframe: str,
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch candles from Hyperliquid using a shared session.

    Parameters
    ----------
    session : shared aiohttp session (avoids per-call overhead)
    coin : HL coin name (e.g. "BTC", "xyz:GOLD")
    timeframe : "4h", "1d", or "1w"
    limit : number of candles
    """
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

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session.post(
                _HL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status == 429:
                    # Rate limited — back off and retry
                    wait = 1.0 * (attempt + 1)
                    logger.debug("HL 429 for %s/%s, retry %d in %.1fs", coin, timeframe, attempt + 1, wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status != 200:
                    return None
                candles = await resp.json()
            return _parse_hl_candles(candles)
        except Exception as exc:
            logger.debug("HL candle fetch failed for %s/%s: %s", coin, timeframe, exc)
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
                continue
            return None
    return None


def _hl_coin_name(symbol: str) -> str:
    """Convert scanner symbol 'BASE/USDT' → HL coin name, applying renames."""
    base = symbol.split("/")[0]
    return _HL_COIN_MAP.get(base, base)


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
    except Exception as exc:
        logger.debug("Hyperliquid candle fetch failed for %s: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# CCXT exchange pool — reuse instances instead of creating per call
# ---------------------------------------------------------------------------
_exchange_pool: Dict[str, ccxt.Exchange] = {}
_exchange_pool_lock = asyncio.Lock()

# Symbols already deepened via CCXT — skip on subsequent scan cycles
_ccxt_deepened: Dict[str, set] = {}  # timeframe → set of symbols


async def _get_exchange(exchange_id: str) -> ccxt.Exchange:
    """Get or create a cached CCXT exchange with markets pre-loaded."""
    if exchange_id in _exchange_pool:
        return _exchange_pool[exchange_id]

    async with _exchange_pool_lock:
        if exchange_id in _exchange_pool:
            return _exchange_pool[exchange_id]

        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unknown exchange: {exchange_id}")
        exchange = exchange_class({"enableRateLimit": True})
        await exchange.load_markets()
        _exchange_pool[exchange_id] = exchange
        logger.info("CCXT pool: loaded %s (%d markets)", exchange_id, len(exchange.markets))
        return exchange


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch OHLCV data for a single *symbol*.

    Uses OHLCVStore for incremental updates:
    - Cold start: full fetch (500 bars)
    - Subsequent: fetch 2 bars, merge into cached array

    Tries Hyperliquid first (primary), then CCXT exchanges as fallback.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        logger.error("Unsupported timeframe '%s'. Use one of %s", timeframe, SUPPORTED_TIMEFRAMES)
        return None

    # Determine fetch limit: full history or incremental update
    is_incremental = not _ohlcv_store.needs_full_fetch(symbol, timeframe)
    fetch_limit = 2 if is_incremental else (limit or _DEFAULT_LIMIT.get(timeframe, 500))

    # Check TTL cache for very recent fetches (avoids redundant calls within same cycle)
    cached = _cache.get(symbol, timeframe)
    if cached is not None:
        return cached

    # Fetch from source
    data = None
    if symbol in _ccxt_only:
        data = await _fetch_ohlcv_ccxt(symbol, timeframe, exchange_id, fetch_limit)
    else:
        data = await _fetch_ohlcv_hyperliquid(symbol, timeframe, fetch_limit)
        if data is None:
            data = await _fetch_ohlcv_ccxt(symbol, timeframe, exchange_id, fetch_limit)
            if data is not None:
                _ccxt_only.add(symbol)
                logger.info("Learned CCXT-only: %s (total %d)", symbol, len(_ccxt_only))

    if data is None:
        # Return stale OHLCVStore data if available
        return _ohlcv_store.get(symbol, timeframe)

    # Merge into persistent store
    merged = _ohlcv_store.update(symbol, timeframe, data)

    # Also put in TTL cache to prevent re-fetching within same scan cycle
    _cache.put(symbol, timeframe, merged)

    return merged


async def _fetch_ohlcv_ccxt(
    symbol: str,
    timeframe: str,
    exchange_id: str = "kraken",
    limit: Optional[int] = None,
) -> Optional[dict]:
    """Fetch OHLCV via CCXT exchange fallback chain."""
    if limit is None:
        limit = _DEFAULT_LIMIT.get(timeframe, 500)

    exchanges_to_try = [exchange_id]
    # Fallback chain: Bybit/OKX/KuCoin/Gate have broad coverage and no geo-blocking
    _FALLBACK_CHAIN = ["bybit", "okx", "kucoin", "gate", "kraken"]
    for exch in _FALLBACK_CHAIN:
        if exch != exchange_id:
            exchanges_to_try.append(exch)

    last_error: Optional[Exception] = None

    for exch_id in exchanges_to_try:
        try:
            exchange = await _get_exchange(exch_id)
            if symbol not in exchange.markets:
                continue
            raw = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not raw:
                continue
            data = _parse_ohlcv(raw)
            _cache.put(symbol, timeframe, data)
            logger.debug("Fetched %d bars for %s (%s) from %s", len(raw), symbol, timeframe, exch_id)
            return data
        except (ccxt.BadSymbol, ccxt.NetworkError, ccxt.ExchangeError) as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            logger.error("Unexpected error fetching %s from %s: %s", symbol, exch_id, exc)
            continue

    if last_error:
        logger.warning("All CCXT exchanges failed for %s: %s", symbol, last_error)
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

        if quote in ("USDT", "USD"):
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
            merged = _ohlcv_store.update(sym, timeframe, data)
            _cache.put(sym, timeframe, merged)
            results[sym] = merged
            return sym
        raise ValueError(f"HL returned no data for {sym}")

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        # Fetch incremental symbols first (fast — only 2 bars each)
        if incr_fetch_syms:
            for i in range(0, len(incr_fetch_syms), _WAVE_SIZE):
                wave = incr_fetch_syms[i : i + _WAVE_SIZE]
                tasks = [asyncio.create_task(_hl_fetch(session, s, limit=2)) for s in wave]
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
                    rt_limit = 2 if not _ohlcv_store.needs_full_fetch(sym, timeframe) else _DEFAULT_LIMIT.get(timeframe, 500)
                    data = await _fetch_hl_candles(s, coin, timeframe, limit=rt_limit)
                    if data is not None:
                        merged = _ohlcv_store.update(sym, timeframe, data)
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
        for sym in uncached:
            if sym in deepened:
                continue  # Already tried CCXT for this symbol+timeframe
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
                if data is not None:
                    hl_count = len(results.get(sym, {}).get("close", [])) if results.get(sym) else 0
                    ccxt_count = len(data.get("close", []))
                    # Only replace if CCXT has more data
                    if ccxt_count > hl_count:
                        merged = _ohlcv_store.update(sym, timeframe, data)
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
    }


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
    if timeframe == "4h":
        # yfinance max for hourly data is 730 days; fetch 2 years
        return "2y", "1h"
    elif timeframe == "1d":
        return "5y", "1d"
    elif timeframe == "1w":
        return "10y", "1wk"
    return "5y", "1d"


def _parse_yf_to_ohlcv(df, timeframe: str) -> Optional[dict]:
    """Convert a yfinance DataFrame into the standard OHLCV dict.

    For 4h timeframe: yfinance only supports 1h, so we resample to 4h.
    """
    if df is None or df.empty:
        return None

    # yfinance returns columns: Open, High, Low, Close, Volume
    # Drop rows with NaN close
    df = df.dropna(subset=["Close"])
    if df.empty:
        return None

    # Resample 1h → 4h if needed
    if timeframe == "4h":
        df = df.resample("4h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna(subset=["Close"])
        if df.empty:
            return None

    timestamps = np.array([int(ts.timestamp() * 1000) for ts in df.index], dtype=np.float64)
    return {
        "timestamp": timestamps,
        "open":      df["Open"].values.astype(np.float64),
        "high":      df["High"].values.astype(np.float64),
        "low":       df["Low"].values.astype(np.float64),
        "close":     df["Close"].values.astype(np.float64),
        "volume":    df["Volume"].values.astype(np.float64),
    }


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

    loop = asyncio.get_running_loop()
    try:
        import yfinance as yf
        period, interval = _yf_period_for_timeframe(timeframe)

        def _download_all():
            return yf.download(
                uncached_tickers,
                period=period,
                interval=interval,
                group_by="ticker",
                threads=True,
            )

        df_all = await loop.run_in_executor(None, _download_all)

        for symbol, yf_ticker in zip(uncached_symbols, uncached_tickers):
            try:
                if len(uncached_tickers) == 1:
                    # Single ticker: yf.download returns flat DataFrame
                    df = df_all
                else:
                    df = df_all[yf_ticker]
                data = _parse_yf_to_ohlcv(df, timeframe)
                if data is not None:
                    _cache.put(symbol, timeframe, data)
                    results[symbol] = data
                else:
                    results[symbol] = None
            except Exception as exc:
                logger.debug("yfinance parse failed for %s: %s", symbol, exc)
                results[symbol] = None

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

    if session is not None:
        data = await _fetch_hl_candles(session, hl_coin, timeframe, limit)
    else:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            data = await _fetch_hl_candles(s, hl_coin, timeframe, limit)

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
