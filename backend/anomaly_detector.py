"""
anomaly_detector.py
~~~~~~~~~~~~~~~~~~~
Cross-sectional z-score + time-series spike detector for unusual
OI, funding, volume, LSR, and CVD activity.

Runs at the tail of each synthesis pass (~60s).  All metrics come from
exchange-direct APIs (Binance/HL/Bybit via CCXT) -- no CoinGlass dependency.

Public API
----------
    detect_anomalies(results, scan_cache, tf)  -> List[Anomaly]
    get_active_anomalies()                     -> List[dict]
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds — statistical (relative to market)
# ---------------------------------------------------------------------------

# Cross-sectional z-score thresholds
Z_HIGH = 3.0
Z_CRITICAL = 5.0

# Time-series (own-history) sigma thresholds
SIGMA_HIGH = 3.0
SIGMA_CRITICAL = 5.0

# Minimum history ticks before time-series check kicks in
MIN_HISTORY_TICKS = 5

# Dedup cooldown (seconds) -- same anomaly won't re-fire within this window
DEDUP_COOLDOWN = 30 * 60  # 30 min

# How long to keep anomalies visible after last detection
ANOMALY_TTL = 45 * 60  # 45 min

# ---------------------------------------------------------------------------
# Thresholds — absolute floors (fire regardless of z-score)
# These catch anomalies even when the whole market is volatile and z-scores
# are compressed.  Values chosen so normal conditions never trigger.
# ---------------------------------------------------------------------------

# Funding: annualized % — ±20% is normal in calm markets, ±30-50% in bull trends
ABS_FUNDING_HIGH = 60.0           # ±60% annualized → high
ABS_FUNDING_CRITICAL = 200.0      # ±200% annualized → critical

# OI change %: 4h window — ±2% is typical, ±10% is extreme
ABS_OI_CHANGE_HIGH = 10.0         # ±10% in 4h → high
ABS_OI_CHANGE_CRITICAL = 20.0     # ±20% in 4h → critical

# Relative volume: 1.0 is normal — 4x+ is extreme
ABS_REL_VOL_HIGH = 4.0            # 4x normal → high
ABS_REL_VOL_CRITICAL = 8.0        # 8x normal → critical

# LSR: 1.0 is balanced — extreme crowd lean
ABS_LSR_HIGH = 2.5                # 2.5 (very one-sided) → high
ABS_LSR_CRITICAL = 4.0            # 4.0 (extreme lean) → critical
ABS_LSR_LOW_HIGH = 0.4            # <0.4 (crowd short) → high
ABS_LSR_LOW_CRITICAL = 0.25       # <0.25 (extreme short lean) → critical

# Buy/sell ratio: 1.0 is balanced
ABS_BSR_HIGH = 2.0                # 2.0 (heavy buying) → high
ABS_BSR_CRITICAL = 3.5            # 3.5 (extreme) → critical
ABS_BSR_LOW_HIGH = 0.5            # <0.5 → high
ABS_BSR_LOW_CRITICAL = 0.3        # <0.3 → critical


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Anomaly:
    symbol: str
    anomaly_type: str       # EXTREME_FUNDING | OI_SURGE | VOLUME_SPIKE | LSR_EXTREME | CVD_EXTREME
    severity: str           # critical | high
    direction: str          # LONG | SHORT | NEUTRAL
    current_value: float
    z_score: float          # cross-sectional z
    historical_sigma: float # time-series sigma (0 if insufficient history)
    context: str            # human-readable explanation
    timestamp: float
    dedup_key: str          # "SYMBOL:TYPE:DIR" for dedup
    # Multi-exchange confirmation
    exchanges_confirmed: List[str] = None   # e.g. ["hyperliquid", "binance"]
    exchange_values: Dict[str, float] = None  # e.g. {"hyperliquid": -0.005, "binance": -0.003}

    def __post_init__(self):
        if self.exchanges_confirmed is None:
            self.exchanges_confirmed = []
        if self.exchange_values is None:
            self.exchange_values = {}

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"

    @property
    def is_cross_exchange_confirmed(self) -> bool:
        return len(self.exchanges_confirmed) >= 2


# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

# dedup_key -> first_seen_ts (prevents re-firing within cooldown)
_dedup_map: Dict[str, float] = {}

# dedup_key -> Anomaly dict (active anomalies visible to API)
_active: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _zscore_array(values: np.ndarray) -> np.ndarray:
    """Compute z-scores.  Returns zeros if std ~ 0."""
    std = np.std(values)
    if std < 1e-12:
        return np.zeros_like(values)
    return (values - np.mean(values)) / std


def _time_series_sigma(current: float, history: list) -> float:
    """How many sigma is `current` from the mean of `history`."""
    if len(history) < MIN_HISTORY_TICKS:
        return 0.0
    arr = np.array(history, dtype=float)
    std = np.std(arr)
    if std < 1e-12:
        return 0.0
    return (current - np.mean(arr)) / std


def _severity(z: float, sigma: float, abs_severity: Optional[str] = None) -> Optional[str]:
    """Map z/sigma + absolute threshold to severity.  Returns None if below all thresholds."""
    peak = max(abs(z), abs(sigma))
    stat_sev = None
    if peak >= Z_CRITICAL:
        stat_sev = "critical"
    elif peak >= Z_HIGH:
        stat_sev = "high"

    # Return the more severe of statistical vs absolute
    if stat_sev == "critical" or abs_severity == "critical":
        return "critical"
    if stat_sev == "high" or abs_severity == "high":
        return "high"
    return None


def _abs_severity_funding(val: float) -> Optional[str]:
    """Absolute threshold check for funding rate (hourly decimal -> annualized %)."""
    ann = abs(_annualized_funding(val))
    if ann >= ABS_FUNDING_CRITICAL:
        return "critical"
    if ann >= ABS_FUNDING_HIGH:
        return "high"
    return None


def _abs_severity_oi(val: float) -> Optional[str]:
    """Absolute threshold for OI change %."""
    if abs(val) >= ABS_OI_CHANGE_CRITICAL:
        return "critical"
    if abs(val) >= ABS_OI_CHANGE_HIGH:
        return "high"
    return None


def _abs_severity_volume(val: float) -> Optional[str]:
    """Absolute threshold for relative volume."""
    if val >= ABS_REL_VOL_CRITICAL:
        return "critical"
    if val >= ABS_REL_VOL_HIGH:
        return "high"
    return None


def _abs_severity_lsr(val: float) -> Optional[str]:
    """Absolute threshold for LSR (bidirectional)."""
    if val >= ABS_LSR_CRITICAL or val <= ABS_LSR_LOW_CRITICAL:
        return "critical"
    if val >= ABS_LSR_HIGH or val <= ABS_LSR_LOW_HIGH:
        return "high"
    return None


def _abs_severity_bsr(val: float) -> Optional[str]:
    """Absolute threshold for buy/sell ratio (bidirectional)."""
    if val >= ABS_BSR_CRITICAL or val <= ABS_BSR_LOW_CRITICAL:
        return "critical"
    if val >= ABS_BSR_HIGH or val <= ABS_BSR_LOW_HIGH:
        return "high"
    return None


def _direction_from_value(value: float) -> str:
    if value > 0:
        return "LONG"
    if value < 0:
        return "SHORT"
    return "NEUTRAL"


def _annualized_funding(hourly_rate: float) -> float:
    return hourly_rate * 24 * 365 * 100  # percentage


def _get_positioning_field(result: dict, field: str, default=0.0):
    """Safely extract a field from the nested positioning dict."""
    pos = result.get("positioning")
    if pos is None:
        return default
    if isinstance(pos, dict):
        return pos.get(field, default) or default
    return getattr(pos, field, default) or default


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

_METRIC_EXTRACTORS = {
    "EXTREME_FUNDING": {
        "extract": lambda r: _get_positioning_field(r, "funding_rate"),
        "history_key": "funding_history",
        "context_fn": lambda sym, val, z, sig: (
            f"{_annualized_funding(val):+.0f}% annualized funding "
            f"(z={z:.1f}, {abs(sig):.1f}\u03c3 vs history)"
        ),
        "direction_fn": lambda val: "SHORT" if val < 0 else "LONG",
        "filter_zero": True,
        "abs_fn": _abs_severity_funding,
        "exchange_field": "funding_rate",  # field name on exchange metric objects
    },
    "OI_SURGE": {
        "extract": lambda r: _get_positioning_field(r, "oi_change_pct"),
        "history_key": "oi_change_history",
        "context_fn": lambda sym, val, z, sig: (
            f"OI {'+' if val > 0 else ''}{val:.1f}% change (4h) "
            f"(z={z:.1f}, {abs(sig):.1f}\u03c3 vs history)"
        ),
        "direction_fn": _direction_from_value,
        "filter_zero": True,
        "abs_fn": _abs_severity_oi,
        "exchange_field": "open_interest",  # for confirmation (existence check, not value)
    },
    "VOLUME_SPIKE": {
        "extract": lambda r: r.get("rel_vol", 0.0) or 0.0,
        "history_key": None,
        "context_fn": lambda sym, val, z, sig: (
            f"Relative volume {val:.1f}x normal (z={z:.1f})"
        ),
        "direction_fn": lambda val: "NEUTRAL",
        "filter_zero": True,
        "abs_fn": _abs_severity_volume,
        "exchange_field": None,
    },
    "LSR_EXTREME": {
        "extract": lambda r: _get_positioning_field(r, "long_short_ratio"),
        "history_key": "lsr_history",
        "context_fn": lambda sym, val, z, sig: (
            f"LSR {val:.2f} "
            f"({'crowd long' if val > 1.0 else 'crowd short'}, "
            f"z={z:.1f}, {abs(sig):.1f}\u03c3 vs history)"
        ),
        "direction_fn": lambda val: "LONG" if val > 1.0 else "SHORT",
        "filter_zero": True,
        "abs_fn": _abs_severity_lsr,
        "exchange_field": None,
    },
    "CVD_EXTREME": {
        "extract": lambda r: r.get("buy_sell_ratio", 0.0) or 0.0,
        "history_key": "bsr_history",
        "context_fn": lambda sym, val, z, sig: (
            f"Buy/sell ratio {val:.2f} "
            f"({'takers buying' if val > 1.0 else 'takers selling'}, "
            f"z={z:.1f}, {abs(sig):.1f}\u03c3 vs history)"
        ),
        "direction_fn": lambda val: "LONG" if val > 1.0 else "SHORT",
        "filter_zero": True,
        "abs_fn": _abs_severity_bsr,
        "exchange_field": None,
    },
}


# ---------------------------------------------------------------------------
# Multi-exchange confirmation
# ---------------------------------------------------------------------------

def _check_exchange_confirmation(
    symbol: str,
    anomaly_type: str,
    exchange_field: Optional[str],
    scan_cache,
) -> tuple:
    """Check if multiple exchanges confirm the anomaly.

    Returns (exchanges_confirmed: list[str], exchange_values: dict[str, float]).
    """
    if not exchange_field or not scan_cache:
        return [], {}

    hl_store = getattr(scan_cache, "_last_hl_metrics", None) or {}
    bn_store = getattr(scan_cache, "_last_binance_metrics", None) or {}

    confirmed = []
    values = {}

    # Check HL
    hl = hl_store.get(symbol)
    if hl is not None:
        val = getattr(hl, exchange_field, 0.0) or 0.0
        if val != 0:
            confirmed.append("hyperliquid")
            if exchange_field == "funding_rate":
                values["hyperliquid"] = round(_annualized_funding(val), 1)
            elif exchange_field == "open_interest":
                values["hyperliquid"] = round(val, 0)

    # Check Binance
    bn = bn_store.get(symbol)
    if bn is not None:
        val = getattr(bn, exchange_field, 0.0) or 0.0
        if val != 0:
            confirmed.append("binance")
            if exchange_field == "funding_rate":
                values["binance"] = round(_annualized_funding(val), 1)
            elif exchange_field == "open_interest":
                values["binance"] = round(val, 0)

    return confirmed, values


def detect_anomalies(
    results: List[dict],
    scan_cache,
    tf: str = "4h",
) -> List[Anomaly]:
    """Run anomaly detection on the latest scan results.

    Returns newly detected anomalies (respects dedup cooldown).
    Also updates the module-level _active store for get_active_anomalies().
    """
    if not results or len(results) < 3:
        return []

    now = time.time()
    new_anomalies: List[Anomaly] = []

    for atype, cfg in _METRIC_EXTRACTORS.items():
        extract_fn = cfg["extract"]
        history_key = cfg["history_key"]
        context_fn = cfg["context_fn"]
        direction_fn = cfg["direction_fn"]

        # 1. Build cross-sectional vector
        sym_vals = []
        for r in results:
            val = extract_fn(r)
            if cfg.get("filter_zero") and (val is None or val == 0):
                continue
            sym_vals.append((r.get("symbol", ""), val))

        if len(sym_vals) < 3:
            continue

        symbols, values = zip(*sym_vals)
        values_arr = np.array(values, dtype=float)
        z_scores = _zscore_array(values_arr)

        abs_fn = cfg.get("abs_fn")
        exchange_field = cfg.get("exchange_field")

        # 2. Check each symbol
        for i, (sym, val) in enumerate(sym_vals):
            z = z_scores[i]

            # Time-series sigma
            sigma = 0.0
            if history_key and scan_cache:
                hist_store = getattr(scan_cache, history_key, {})
                tf_key = f"{sym}:{tf}"
                hist = hist_store.get(tf_key, [])
                if hist:
                    sigma = _time_series_sigma(val, hist)

            # Absolute threshold check
            abs_sev = abs_fn(val) if abs_fn else None

            sev = _severity(z, sigma, abs_sev)
            if sev is None:
                continue

            direction = direction_fn(val)
            dedup_key = f"{sym}:{atype}:{direction}"

            # Multi-exchange confirmation
            exchanges, ex_values = _check_exchange_confirmation(
                sym, atype, exchange_field, scan_cache,
            )

            # Dedup check
            last_seen = _dedup_map.get(dedup_key, 0)
            is_new = (now - last_seen) > DEDUP_COOLDOWN

            # Build context with exchange info
            base_ctx = context_fn(sym, val, z, sigma)
            if abs_sev and abs(z) < Z_HIGH and abs(sigma) < SIGMA_HIGH:
                base_ctx += " [absolute threshold]"
            if len(exchanges) >= 2:
                ex_detail = ", ".join(
                    f"{ex}: {ex_values.get(ex, '?')}" for ex in exchanges
                )
                base_ctx += f" | confirmed: {ex_detail}"
            elif len(exchanges) == 1:
                base_ctx += f" | {exchanges[0]} only"

            anomaly = Anomaly(
                symbol=sym,
                anomaly_type=atype,
                severity=sev,
                direction=direction,
                current_value=round(val, 8),
                z_score=round(z, 2),
                historical_sigma=round(sigma, 2),
                context=base_ctx,
                timestamp=now,
                dedup_key=dedup_key,
                exchanges_confirmed=exchanges,
                exchange_values=ex_values,
            )

            # Always update active store (refreshes TTL)
            _active[dedup_key] = {**asdict(anomaly), "age_seconds": 0}

            if is_new:
                _dedup_map[dedup_key] = now
                new_anomalies.append(anomaly)

    # Prune stale entries from _active
    stale_keys = [k for k, v in _active.items() if now - v["timestamp"] > ANOMALY_TTL]
    for k in stale_keys:
        _active.pop(k, None)

    # Prune old dedup entries
    stale_dedup = [k for k, ts in _dedup_map.items() if now - ts > DEDUP_COOLDOWN * 2]
    for k in stale_dedup:
        _dedup_map.pop(k, None)

    if new_anomalies:
        logger.info(
            "Anomaly detector [%s]: %d new anomalies -- %s",
            tf,
            len(new_anomalies),
            ", ".join(f"{a.symbol} {a.anomaly_type} ({a.severity})" for a in new_anomalies),
        )

    return new_anomalies


def get_active_anomalies() -> List[dict]:
    """Return currently active anomalies sorted by severity then z-score."""
    now = time.time()
    result = []
    for v in _active.values():
        entry = dict(v)
        entry["age_seconds"] = int(now - entry["timestamp"])
        result.append(entry)

    # Sort: critical first, then by abs(z_score) desc
    sev_rank = {"critical": 0, "high": 1}
    result.sort(key=lambda x: (sev_rank.get(x["severity"], 9), -abs(x["z_score"])))
    return result
