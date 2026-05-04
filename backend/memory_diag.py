"""
memory_diag.py
~~~~~~~~~~~~~~

Production-safe memory inventory.

Walks every known in-memory data structure across the backend, deep-sizes
it (with proper numpy.ndarray handling), and reports process RSS so we
can see exactly where the running RAM goes.

Designed to be called from a single admin endpoint. Walks bounded
collections — never iterates lazy generators or unbounded sources.
"""

from __future__ import annotations

import gc
import logging
import sys
from collections import deque
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deep size walker
# ---------------------------------------------------------------------------

def _deep_size(obj: Any, seen: set | None = None, depth_limit: int = 12) -> int:
    """Best-effort recursive object size in bytes.

    - Handles dict / list / tuple / set / frozenset / deque
    - Handles numpy.ndarray (uses .nbytes for accuracy)
    - Walks dataclass / regular class instances via __dict__ / __slots__
    - Cycle-safe via id() set
    - Bounded depth so we don't recurse into the entire heap
    """
    if seen is None:
        seen = set()
    if depth_limit <= 0:
        return sys.getsizeof(obj)

    obj_id = id(obj)
    if obj_id in seen:
        return 0
    seen.add(obj_id)

    # numpy fast path
    try:
        import numpy as _np
        if isinstance(obj, _np.ndarray):
            return obj.nbytes
    except Exception:
        pass

    size = sys.getsizeof(obj)
    next_depth = depth_limit - 1

    if isinstance(obj, dict):
        for k, v in obj.items():
            size += _deep_size(k, seen, next_depth)
            size += _deep_size(v, seen, next_depth)
    elif isinstance(obj, (list, tuple, set, frozenset, deque)):
        for item in obj:
            size += _deep_size(item, seen, next_depth)
    elif hasattr(obj, "__dict__"):
        size += _deep_size(vars(obj), seen, next_depth)
    elif hasattr(obj, "__slots__"):
        for slot in obj.__slots__:
            try:
                size += _deep_size(getattr(obj, slot), seen, next_depth)
            except AttributeError:
                pass

    return size


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{n / 1024 / 1024 / 1024:.2f} GB"


# ---------------------------------------------------------------------------
# Process info
# ---------------------------------------------------------------------------

def process_info() -> Dict[str, Any]:
    """Process-level memory metrics from psutil."""
    info: Dict[str, Any] = {}
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        info["rss_bytes"] = mem.rss
        info["rss"] = _fmt_bytes(mem.rss)
        info["vms_bytes"] = mem.vms
        info["vms"] = _fmt_bytes(mem.vms)
        info["num_threads"] = proc.num_threads()
        try:
            info["num_fds"] = proc.num_fds()
        except Exception:
            pass
        info["pid"] = proc.pid
    except Exception as exc:
        info["error"] = f"psutil unavailable: {exc}"
    return info


def gc_info() -> Dict[str, Any]:
    """Garbage collector statistics."""
    return {
        "object_count": len(gc.get_objects()),
        "stats": gc.get_stats(),
        "thresholds": gc.get_threshold(),
    }


# ---------------------------------------------------------------------------
# Per-module inventory
# ---------------------------------------------------------------------------

def _safe_inventory(label: str, fn) -> Dict[str, Any]:
    """Run a probe; never let it crash the whole report."""
    try:
        return fn()
    except Exception as exc:
        logger.warning("memory_diag: probe %s failed: %s", label, exc)
        return {"error": str(exc)}


def inventory_hyperlens() -> Dict[str, Any]:
    """In-memory state held by hl_intelligence."""
    import hl_intelligence as hl

    out: Dict[str, Any] = {}
    targets: List[Tuple[str, Any]] = [
        ("_snapshots",            hl._snapshots),
        ("_trade_log",            hl._trade_log),
        ("_last_positions",       hl._last_positions),
        ("_position_first_seen",  hl._position_first_seen),
        ("_wallet_orders",        hl._wallet_orders),
        ("_consensus",            hl._consensus),
        ("_roster",               hl._roster),
        ("_roster_money_printers", hl._roster_money_printers),
        ("_roster_smart_money",   hl._roster_smart_money),
        ("_wallet_cohorts",       hl._wallet_cohorts),
        ("_order_books",          hl._order_books),
    ]
    total = 0
    for name, obj in targets:
        try:
            count = len(obj) if obj is not None else 0
        except Exception:
            count = None
        size = _deep_size(obj) if obj is not None else 0
        total += size
        out[name] = {"count": count, "bytes": size, "size": _fmt_bytes(size)}
    out["_total"] = {"bytes": total, "size": _fmt_bytes(total)}
    return out


def inventory_scanner() -> Dict[str, Any]:
    """In-memory state held by the ScanCache singleton."""
    from main import cache  # noqa
    out: Dict[str, Any] = {}
    targets: List[Tuple[str, Any]] = [
        ("symbols",                  getattr(cache, "symbols", [])),
        ("results",                  getattr(cache, "results", {})),
        ("_results_by_sym",          getattr(cache, "_results_by_sym", {})),
        ("consensus",                getattr(cache, "consensus", {})),
        ("alt_season",               getattr(cache, "alt_season", {})),
        ("anomalies",                getattr(cache, "anomalies", [])),
        ("anomaly_hot_symbols",      getattr(cache, "anomaly_hot_symbols", set())),
        ("confluence",               getattr(cache, "confluence", {})),
        ("prev_oi",                  getattr(cache, "prev_oi", {})),
        ("prev_heat",                getattr(cache, "prev_heat", {})),
        ("_engine_cache",            getattr(cache, "_engine_cache", {})),
        ("tradfi_results",           getattr(cache, "tradfi_results", {})),
        ("_last_hl_metrics",         getattr(cache, "_last_hl_metrics", {})),
        ("_last_binance_metrics",    getattr(cache, "_last_binance_metrics", {})),
        ("_last_bybit_metrics",      getattr(cache, "_last_bybit_metrics", {})),
        # History deques
        ("signal_history",           getattr(cache, "signal_history", {})),
        ("confidence_history",       getattr(cache, "confidence_history", {})),
        ("divergence_history",       getattr(cache, "divergence_history", {})),
        ("smoothed_confidence",      getattr(cache, "smoothed_confidence", {})),
        ("signal_inertia",           getattr(cache, "signal_inertia", {})),
        ("funding_history",          getattr(cache, "funding_history", {})),
        ("oi_history",               getattr(cache, "oi_history", {})),
        ("oi_change_history",        getattr(cache, "oi_change_history", {})),
        ("lsr_history",              getattr(cache, "lsr_history", {})),
        ("bsr_history",              getattr(cache, "bsr_history", {})),
        ("spot_ratio_history",       getattr(cache, "spot_ratio_history", {})),
        ("vpin_history",             getattr(cache, "vpin_history", {})),
        ("regime_change_log",        getattr(cache, "regime_change_log", {})),
        ("prev_regime_by_tf",        getattr(cache, "prev_regime_by_tf", {})),
        ("signal_first_seen_at",     getattr(cache, "signal_first_seen_at", {})),
        ("signal_first_seen_label",  getattr(cache, "signal_first_seen_label", {})),
    ]
    total = 0
    for name, obj in targets:
        try:
            count = len(obj)
        except Exception:
            count = None
        size = _deep_size(obj)
        total += size
        out[name] = {"count": count, "bytes": size, "size": _fmt_bytes(size)}
    out["_total"] = {"bytes": total, "size": _fmt_bytes(total)}
    return out


def inventory_ohlcv() -> Dict[str, Any]:
    """OHLCV cache — usually one of the biggest single consumers."""
    from data_fetcher import _ohlcv_store, _cache as _ttl_cache
    out: Dict[str, Any] = {}

    store = getattr(_ohlcv_store, "_store", {})
    by_tf: Dict[str, Dict[str, int]] = {}
    total_bars = 0
    total_bytes = 0
    for key, ohlcv in store.items():
        # key format: "SYMBOL|TF"
        if "|" in key:
            tf = key.split("|", 1)[1]
        else:
            tf = "?"
        bars = len(ohlcv.get("close", [])) if isinstance(ohlcv, dict) else 0
        size = _deep_size(ohlcv)
        b = by_tf.setdefault(tf, {"entries": 0, "total_bars": 0, "bytes": 0})
        b["entries"] += 1
        b["total_bars"] += bars
        b["bytes"] += size
        total_bars += bars
        total_bytes += size

    for tf, b in by_tf.items():
        b["size"] = _fmt_bytes(b["bytes"])

    out["store_summary"] = {
        "total_entries": len(store),
        "total_bars": total_bars,
        "total_size": _fmt_bytes(total_bytes),
        "by_timeframe": by_tf,
    }
    out["ttl_cache"] = {
        "entries": len(getattr(_ttl_cache, "_fetched_at", {})),
        "size": _fmt_bytes(_deep_size(getattr(_ttl_cache, "_fetched_at", {}))),
    }
    out["_total"] = {"bytes": total_bytes, "size": _fmt_bytes(total_bytes)}
    return out


def inventory_signal_log() -> Dict[str, Any]:
    """In-memory bits held by signal_log (SQLite is on disk, not counted)."""
    from signal_log import SignalLog
    sig = SignalLog.get()
    out: Dict[str, Any] = {}
    for name in ("_prev_signals", "_prev_regimes"):
        v = getattr(sig, name, None)
        size = _deep_size(v) if v is not None else 0
        out[name] = {
            "count": (len(v) if hasattr(v, "__len__") else None) if v is not None else 0,
            "bytes": size,
            "size": _fmt_bytes(size),
        }
    return out


def inventory_other() -> Dict[str, Any]:
    """Everything else worth checking — bridge flow cache, executor, etc."""
    out: Dict[str, Any] = {}

    # Bridge flow cache
    try:
        import hl_bridge as hb
        out["hl_bridge"] = {
            "_cache_payload": _fmt_bytes(_deep_size(hb._cache_payload)),
            "cache_age_s": (hb._cache_expires_at - hb.time.time()) if hb._cache_expires_at else None,
        }
    except Exception as exc:
        out["hl_bridge"] = {"error": str(exc)}

    # Executor
    try:
        from executor import _executor_singleton  # noqa
    except Exception:
        pass
    try:
        import executor as ex
        executor = getattr(ex, "_executor", None)
        if executor:
            out["executor"] = {
                "positions": len(getattr(executor, "positions", {})),
                "trade_log": len(getattr(executor, "trade_log", [])),
                "size": _fmt_bytes(_deep_size(executor)),
            }
    except Exception as exc:
        out["executor"] = {"error": str(exc)}

    # Whale follows + on-chain tracker
    try:
        import whale_follows as wf
        out["whale_follows"] = {
            "size": _fmt_bytes(_deep_size(getattr(wf, "_follows", {}))),
            "events": len(getattr(wf, "_followed_events", [])),
        }
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# Top-N largest objects via gc walk
# ---------------------------------------------------------------------------

def top_objects_by_type(limit: int = 15) -> List[Dict[str, Any]]:
    """Aggregate gc-tracked objects by type, sorted by total size.

    Excellent for spotting unexpected memory consumers (e.g. a large
    list/dict being held somewhere we didn't anticipate).
    """
    type_totals: Dict[str, Dict[str, int]] = {}
    for obj in gc.get_objects():
        t_name = type(obj).__name__
        try:
            sz = sys.getsizeof(obj)
        except Exception:
            continue
        slot = type_totals.setdefault(t_name, {"count": 0, "bytes": 0})
        slot["count"] += 1
        slot["bytes"] += sz

    rows = [
        {"type": t, "count": v["count"], "bytes": v["bytes"], "size": _fmt_bytes(v["bytes"])}
        for t, v in type_totals.items()
    ]
    rows.sort(key=lambda r: -r["bytes"])
    return rows[:limit]


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------

def full_report() -> Dict[str, Any]:
    """Full memory snapshot. Single entry point for the admin endpoint."""
    proc = process_info()
    return {
        "process": proc,
        "gc": _safe_inventory("gc", gc_info),
        "hyperlens": _safe_inventory("hyperlens", inventory_hyperlens),
        "scanner": _safe_inventory("scanner", inventory_scanner),
        "ohlcv": _safe_inventory("ohlcv", inventory_ohlcv),
        "signal_log": _safe_inventory("signal_log", inventory_signal_log),
        "other": _safe_inventory("other", inventory_other),
        "top_types": _safe_inventory("top_types", lambda: top_objects_by_type(15)),
    }


# ---------------------------------------------------------------------------
# Active cleanup
# ---------------------------------------------------------------------------

def _malloc_trim() -> bool:
    """Ask glibc to release unused malloc arenas back to the OS.

    Only effective on Linux glibc (Railway containers use Debian which has
    glibc). Returns True if the call succeeded.
    """
    try:
        import ctypes
        # libc.so.6 is the glibc shared library; malloc_trim(0) returns all
        # unused memory at the top of any arena to the OS.
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
        return True
    except Exception as exc:
        logger.debug("malloc_trim unavailable: %s", exc)
        return False


def cleanup() -> Dict[str, Any]:
    """Active memory cleanup. Returns before/after RSS.

    Steps:
      1. Snapshot current RSS
      2. Clear regenerable caches (engine cache, ttl cache, etc.)
      3. Run gc.collect() three times (helps with cycles)
      4. Ask glibc to release unused arenas back to the OS

    Safe to call repeatedly. None of the cleared caches affect signal
    correctness — they're all rebuilt on next access.
    """
    before = process_info()
    cleared: Dict[str, int] = {}

    # 1. Scanner engine cache — regenerated on every scan
    try:
        from main import cache as scan_cache
        ec = getattr(scan_cache, "_engine_cache", None)
        if ec is not None:
            cleared["scanner._engine_cache"] = len(ec)
            ec.clear()
    except Exception as exc:
        logger.warning("cleanup: scanner cache clear failed: %s", exc)

    # 2. OHLCV TTL cache — lightweight timestamp tracker, safe to drop
    try:
        from data_fetcher import _cache as ttl
        cleared["ohlcv.ttl_cache"] = len(ttl)
        ttl.clear()
    except Exception as exc:
        logger.warning("cleanup: ttl cache clear failed: %s", exc)

    # 3. CCXT pool — exchange instances accumulate market data caches
    try:
        from data_fetcher import _exchange_pool
        if isinstance(_exchange_pool, dict):
            cleared["ccxt_pool"] = len(_exchange_pool)
            for ex in _exchange_pool.values():
                if hasattr(ex, "markets"):
                    ex.markets = {}
                if hasattr(ex, "markets_by_id"):
                    ex.markets_by_id = {}
    except Exception as exc:
        logger.debug("cleanup: ccxt pool not present: %s", exc)

    # 4. HyperLens last-poll metrics caches (not the live state)
    try:
        from main import cache as scan_cache
        for attr in ("_last_hl_metrics", "_last_binance_metrics", "_last_bybit_metrics"):
            d = getattr(scan_cache, attr, None)
            if d is not None and len(d) > 0:
                cleared[f"scanner.{attr}"] = len(d)
                # Keep latest values but drop stale entries (best-effort)
                # Actually, these get refreshed on next scan, so safe to clear.
                d.clear()
    except Exception as exc:
        logger.warning("cleanup: metric cache clear failed: %s", exc)

    # 5. Run garbage collector multiple times (helps with cyclic refs)
    gc_runs = []
    for _ in range(3):
        gc_runs.append(gc.collect())

    # 6. Ask glibc to return unused arena memory to OS
    trimmed = _malloc_trim()

    after = process_info()

    rss_before = before.get("rss_bytes", 0) or 0
    rss_after = after.get("rss_bytes", 0) or 0
    delta = rss_before - rss_after

    return {
        "before": before,
        "after": after,
        "freed_bytes": delta,
        "freed": _fmt_bytes(delta) if delta > 0 else "(no reduction)",
        "cleared_caches": cleared,
        "gc_collected_objects": gc_runs,
        "malloc_trimmed": trimmed,
    }
