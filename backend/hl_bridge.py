"""
Hyperliquid Bridge Flow Tracker
================================

Monitors USDC deposits and withdrawals to/from the Hyperliquid L1 bridge
contract on Arbitrum. High inflows signal new capital arriving
(bullish for HL activity / sometimes preceding market moves), high outflows
signal capital leaving (de-risking / withdrawal cycle).

Data source: Etherscan V2 API (unified across EVM chains). Chain ID 42161.

Aggregates transfers into rolling 1h / 6h / 24h / 7d windows.

Bridge contract (Arbitrum): 0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7
Native USDC (Arbitrum):     0xaf88d065e77c8cC2239327C5EDb3A432268e5831
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from onchain.fetcher_etherscan import EtherscanFetcher, EtherscanTransfer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Divergence signal tuning
# ---------------------------------------------------------------------------
# BTC × bridge flow divergence is a macro positioning signal: price rising
# while flow drains (distribution) or price falling while flow accumulates
# (absorption). Thresholds mirror the VPIN BALANCED/ELEVATED/TOXIC shape.
_DIV_NEUTRAL_MIN_Z      = 0.5   # both legs must move ≥0.5σ to say anything
_DIV_DIVERGING_MIN      = 1.5   # |score| ≥ 1.5 → watch
_DIV_EXHAUSTION_MIN     = 2.5   # |score| ≥ 2.5 → distribution/absorption
_DIV_CONFIRM_MIN        = 1.0   # 1h must also cross this for `confirmed`
_DIV_BASELINE_DAYS      = 7     # rolling baseline window
_DIV_MIN_SAMPLES        = 24    # need ≥24 snapshots (~4h) to trust z-score
_BTC_PAIR_TOLERANCE_S   = 8 * 60  # ±8 min when matching bridge ts → BTC close
_BTC_CLOSES_TTL_S       = 5 * 60  # 5-min cache on BTC kline fetch

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HL_BRIDGE_ADDRESS = "0x2Df1c51E09aECF9cacB7bc98cB1742757f163dF7".lower()
ARB_USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831".lower()
ARB_CHAIN_ID = "42161"

# Windows (seconds)
WINDOW_1H = 3600
WINDOW_6H = 6 * 3600
WINDOW_24H = 24 * 3600
WINDOW_7D = 7 * 24 * 3600

# Cache
_CACHE_TTL_S = 600  # 10 min — bridge flow is a macro indicator, no need for 3-min granularity
_cache_expires_at: float = 0.0
_cache_payload: Optional[dict] = None

# Fetcher singleton
_fetcher: Optional[EtherscanFetcher] = None

# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------
# We reuse HYPERLENS_DB_PATH so the Railway persistent volume covers bridge
# snapshots too. WAL mode makes multi-connection access safe.

_DB_PATH = os.environ.get("HYPERLENS_DB_PATH", str(Path(__file__).parent / "hyperlens.db"))
_db_conn: Optional[sqlite3.Connection] = None

# How long to keep snapshots. 14 days gives room for cross-week analysis.
_SNAPSHOT_RETENTION_DAYS = 14

_BRIDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS bridge_snapshots (
    ts               REAL PRIMARY KEY,
    trend            TEXT NOT NULL,
    signal           TEXT NOT NULL,
    w1h_inflow_usd   REAL,
    w1h_outflow_usd  REAL,
    w1h_net_usd      REAL,
    w6h_inflow_usd   REAL,
    w6h_outflow_usd  REAL,
    w6h_net_usd      REAL,
    w24h_inflow_usd  REAL,
    w24h_outflow_usd REAL,
    w24h_net_usd     REAL,
    w24h_complete    INTEGER NOT NULL DEFAULT 0,
    sample_span_s    INTEGER NOT NULL DEFAULT 0,
    tx_sample_size   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bridge_ts ON bridge_snapshots(ts DESC);
"""


def _get_db() -> sqlite3.Connection:
    global _db_conn
    if _db_conn is None:
        db_dir = os.path.dirname(_DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _db_conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _db_conn.execute("PRAGMA journal_mode=WAL")
        _db_conn.execute("PRAGMA synchronous=NORMAL")
        _db_conn.execute("PRAGMA busy_timeout=5000")
        _db_conn.executescript(_BRIDGE_SCHEMA)
        _db_conn.commit()
        logger.info("hl_bridge: DB opened at %s", _DB_PATH)
    return _db_conn


def _persist_snapshot(payload: dict) -> None:
    """Write the latest bridge snapshot to SQLite. Never raises — logs instead."""
    try:
        conn = _get_db()
        w1 = payload.get("w1h") or {}
        w6 = payload.get("w6h") or {}
        w24 = payload.get("w24h") or {}
        conn.execute(
            """INSERT OR REPLACE INTO bridge_snapshots (
                ts, trend, signal,
                w1h_inflow_usd, w1h_outflow_usd, w1h_net_usd,
                w6h_inflow_usd, w6h_outflow_usd, w6h_net_usd,
                w24h_inflow_usd, w24h_outflow_usd, w24h_net_usd,
                w24h_complete, sample_span_s, tx_sample_size
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                float(payload.get("fetched_at") or time.time()),
                payload.get("trend") or "NEUTRAL",
                payload.get("signal") or "BALANCED",
                w1.get("inflow_usd"),  w1.get("outflow_usd"),  w1.get("net_usd"),
                w6.get("inflow_usd"),  w6.get("outflow_usd"),  w6.get("net_usd"),
                w24.get("inflow_usd"), w24.get("outflow_usd"), w24.get("net_usd"),
                1 if w24.get("complete") else 0,
                int(payload.get("sample_span_seconds") or 0),
                int(payload.get("tx_sample_size") or 0),
            ),
        )
        # Prune old rows
        cutoff = time.time() - (_SNAPSHOT_RETENTION_DAYS * 86400)
        conn.execute("DELETE FROM bridge_snapshots WHERE ts < ?", (cutoff,))
        conn.commit()
    except Exception as exc:
        logger.warning("hl_bridge: persist failed: %s", exc)


def get_bridge_history(hours: int = 24) -> List[dict]:
    """Return the last ``hours`` of bridge snapshots, oldest first.

    Each row is a dict with ts + trend + the three window dicts. Never raises.
    """
    try:
        conn = _get_db()
        since = time.time() - (hours * 3600)
        rows = conn.execute(
            """SELECT ts, trend, signal,
                      w1h_inflow_usd, w1h_outflow_usd, w1h_net_usd,
                      w6h_inflow_usd, w6h_outflow_usd, w6h_net_usd,
                      w24h_inflow_usd, w24h_outflow_usd, w24h_net_usd,
                      w24h_complete, sample_span_s, tx_sample_size
                 FROM bridge_snapshots
                WHERE ts >= ?
                ORDER BY ts ASC""",
            (since,),
        ).fetchall()
    except Exception as exc:
        logger.warning("hl_bridge: history fetch failed: %s", exc)
        return []

    out: List[dict] = []
    for r in rows:
        out.append({
            "ts": r[0],
            "trend": r[1],
            "signal": r[2],
            "w1h":  {"inflow_usd": r[3],  "outflow_usd": r[4],  "net_usd": r[5]},
            "w6h":  {"inflow_usd": r[6],  "outflow_usd": r[7],  "net_usd": r[8]},
            "w24h": {"inflow_usd": r[9],  "outflow_usd": r[10], "net_usd": r[11], "complete": bool(r[12])},
            "sample_span_seconds": r[13],
            "tx_sample_size": r[14],
        })
    return out


# ---------------------------------------------------------------------------
# BTC × bridge flow divergence
# ---------------------------------------------------------------------------
# The hypothesis: bridge net inflow co-moves with BTC price during healthy
# trends, and diverges at local tops/bottoms as smart money exits while late
# retail keeps bidding (or vice versa for bottoms). We quantify this as a
# z-score of BTC return minus a z-score of bridge net flow, both against a
# 7-day rolling baseline. Mirrors how VPIN compares current flow to history.

_btc_closes_cache: Optional[List[tuple]] = None  # list[(ts_s, close_usd)]
_btc_closes_cached_hours: int = 0
_btc_closes_expires_at: float = 0.0


async def _fetch_btc_closes(hours: int = 168) -> List[tuple]:
    """Fetch BTC/USDT 15m closes for the last ``hours`` hours (oldest first).

    Returns a list of (unix_ts_seconds, close_usd) tuples. Uses CCXT via the
    data_fetcher exchange pool. Falls back to the cached series on failure so
    divergence can still be computed stale rather than disappearing. Never
    raises.
    """
    global _btc_closes_cache, _btc_closes_cached_hours, _btc_closes_expires_at

    now = time.time()
    if (
        _btc_closes_cache is not None
        and _btc_closes_cached_hours >= hours
        and _btc_closes_expires_at > now
    ):
        return _btc_closes_cache

    try:
        from data_fetcher import _get_exchange  # late import; avoids cycle
    except Exception as exc:
        logger.debug("hl_bridge: data_fetcher import failed: %s", exc)
        return _btc_closes_cache or []

    # 15m candles → 4/hour → hours*4 candles. Cap at 1000 (most exchanges' limit).
    limit = min(1000, int(hours * 4) + 4)

    # Try Kraken first (matches scanner default), then the usual fallback chain.
    for exch_id in ("kraken", "bybit", "okx", "kucoin"):
        try:
            ex = await _get_exchange(exch_id)
            sym = "BTC/USDT" if "BTC/USDT" in ex.markets else "BTC/USD"
            if sym not in ex.markets:
                continue
            raw = await ex.fetch_ohlcv(sym, "15m", limit=limit)
            if not raw:
                continue
            # CCXT returns [[ts_ms, o, h, l, c, v], …] sorted oldest→newest
            closes = [(int(r[0]) / 1000.0, float(r[4])) for r in raw if r and r[4]]
            if closes:
                _btc_closes_cache = closes
                _btc_closes_cached_hours = hours
                _btc_closes_expires_at = now + _BTC_CLOSES_TTL_S
                return closes
        except Exception as exc:
            logger.debug("hl_bridge: BTC fetch via %s failed: %s", exch_id, exc)
            continue

    return _btc_closes_cache or []


def _btc_close_at(btc_closes: List[tuple], target_ts: float) -> Optional[float]:
    """Return the close price closest to ``target_ts`` within tolerance, or None."""
    if not btc_closes:
        return None
    best = None
    best_diff = _BTC_PAIR_TOLERANCE_S + 1
    # closes are sorted; linear scan is fine for <1000 candles
    for ts, c in btc_closes:
        diff = abs(ts - target_ts)
        if diff < best_diff:
            best_diff = diff
            best = c
        elif ts > target_ts + _BTC_PAIR_TOLERANCE_S:
            break
    if best_diff > _BTC_PAIR_TOLERANCE_S:
        return None
    return best


def _pair_snapshots_with_btc(
    snapshots: List[dict], btc_closes: List[tuple]
) -> List[dict]:
    """Attach BTC close + 1h/6h returns to each snapshot.

    Returns rows with keys: ts, net_1h, net_6h, btc_close, ret_1h, ret_6h.
    Rows without a BTC match or without lookback data are dropped.
    """
    if not snapshots or not btc_closes:
        return []

    # Pre-index closes for O(log n) lookups of lookback prices
    # (plain linear is fine given <1000 candles; keeping simple)
    paired: List[dict] = []
    for snap in snapshots:
        ts = float(snap.get("ts") or 0)
        if ts <= 0:
            continue
        close_now = _btc_close_at(btc_closes, ts)
        close_1h  = _btc_close_at(btc_closes, ts - 3600)
        close_6h  = _btc_close_at(btc_closes, ts - 6 * 3600)
        if close_now is None or close_1h is None or close_6h is None:
            continue
        w1h = snap.get("w1h") or {}
        w6h = snap.get("w6h") or {}
        paired.append({
            "ts": ts,
            "net_1h": float(w1h.get("net_usd") or 0.0),
            "net_6h": float(w6h.get("net_usd") or 0.0),
            "btc_close": close_now,
            "ret_1h": (close_now / close_1h) - 1.0,
            "ret_6h": (close_now / close_6h) - 1.0,
        })
    return paired


def _zscore(value: float, series: List[float]) -> float:
    """Return ``(value - mean) / stdev`` over ``series``. 0.0 on empty/flat."""
    n = len(series)
    if n < 2:
        return 0.0
    mean = sum(series) / n
    var = sum((x - mean) ** 2 for x in series) / n
    if var <= 0:
        return 0.0
    return (value - mean) / (var ** 0.5)


def _classify_divergence(score_6h: float, score_1h: float,
                         btc_z_6h: float, flow_z_6h: float) -> tuple:
    """Return (label, confirmed: bool) for a given score pair."""
    abs_s = abs(score_6h)

    # Not enough movement in either leg → neutral
    if abs(btc_z_6h) < _DIV_NEUTRAL_MIN_Z or abs(flow_z_6h) < _DIV_NEUTRAL_MIN_Z:
        return "NEUTRAL", False

    # Price and flow agree in direction (both up or both down) and score small
    if (btc_z_6h > 0) == (flow_z_6h > 0) and abs_s < _DIV_DIVERGING_MIN:
        return "CONFIRMING", False

    if abs_s >= _DIV_EXHAUSTION_MIN:
        label = "EXHAUSTION"
    elif abs_s >= _DIV_DIVERGING_MIN:
        label = "DIVERGING"
    else:
        return "NEUTRAL", False

    # Confirmed when the 1h score points the same way and also crosses the bar
    confirmed = (
        abs(score_1h) >= _DIV_CONFIRM_MIN
        and ((score_1h > 0) == (score_6h > 0))
    )
    return label, confirmed


def _interpretation(score_6h: float, btc_z: float, flow_z: float, label: str) -> str:
    """Human-readable one-liner for tooltip / alert body."""
    if label == "NEUTRAL":
        return "BTC and bridge flow both near baseline"
    if label == "CONFIRMING":
        direction = "rising" if btc_z > 0 else "falling"
        return f"BTC {direction}, flow agrees (healthy trend)"
    # DIVERGING / EXHAUSTION
    if score_6h > 0:
        # BTC up more than flow → distribution risk
        kind = "distribution" if label == "EXHAUSTION" else "distribution risk"
    else:
        kind = "accumulation" if label == "EXHAUSTION" else "accumulation signal"
    return (
        f"BTC {btc_z:+.1f}\u03c3, flow {flow_z:+.1f}\u03c3 \u2192 {kind}"
    )


def _compute_divergence(paired_rows: List[dict]) -> Optional[dict]:
    """Compute divergence at the latest paired row against the trailing baseline.

    Returns None if we don't have enough samples for a meaningful z-score.
    """
    n = len(paired_rows)
    if n < _DIV_MIN_SAMPLES:
        return None

    latest = paired_rows[-1]
    # Baseline = all rows except the latest (keeps the latest from biasing μ/σ).
    baseline = paired_rows[:-1]

    net_6h_series = [r["net_6h"] for r in baseline]
    net_1h_series = [r["net_1h"] for r in baseline]
    ret_6h_series = [r["ret_6h"] for r in baseline]
    ret_1h_series = [r["ret_1h"] for r in baseline]

    net_6h_z = _zscore(latest["net_6h"], net_6h_series)
    net_1h_z = _zscore(latest["net_1h"], net_1h_series)
    ret_6h_z = _zscore(latest["ret_6h"], ret_6h_series)
    ret_1h_z = _zscore(latest["ret_1h"], ret_1h_series)

    score_6h = ret_6h_z - net_6h_z
    score_1h = ret_1h_z - net_1h_z

    label, confirmed = _classify_divergence(score_6h, score_1h, ret_6h_z, net_6h_z)

    return {
        "score_6h": round(score_6h, 3),
        "score_1h": round(score_1h, 3),
        "btc_return_6h_z": round(ret_6h_z, 3),
        "net_flow_6h_z": round(net_6h_z, 3),
        "btc_return_1h_z": round(ret_1h_z, 3),
        "net_flow_1h_z": round(net_1h_z, 3),
        "label": label,
        "confirmed": confirmed,
        "interpretation": _interpretation(score_6h, ret_6h_z, net_6h_z, label),
        "sample_size": n,
    }


async def _compute_latest_divergence() -> Optional[dict]:
    """Build paired series from the SQLite history + BTC closes and score the latest snapshot.

    Returns None if bridge/BTC history is insufficient. Never raises.
    """
    try:
        hours = _DIV_BASELINE_DAYS * 24
        snapshots = get_bridge_history(hours=hours)
        if len(snapshots) < _DIV_MIN_SAMPLES:
            return None
        btc_closes = await _fetch_btc_closes(hours=hours + 1)
        if not btc_closes:
            return None
        paired = _pair_snapshots_with_btc(snapshots, btc_closes)
        return _compute_divergence(paired)
    except Exception as exc:
        logger.debug("hl_bridge: divergence compute failed: %s", exc)
        return None


async def get_divergence_history(hours: int = 24) -> List[dict]:
    """Return divergence score per historical snapshot over the last ``hours``.

    Each point requires a 7d trailing baseline, so older history is needed
    too. Returns [{ts, score_6h, label, confirmed}, …] oldest-first. Never raises.
    """
    try:
        hours = max(1, min(168, int(hours or 24)))
        # Pull baseline_days + display window so every point has a full baseline.
        total_hours = (_DIV_BASELINE_DAYS * 24) + hours
        snapshots = get_bridge_history(hours=total_hours)
        if len(snapshots) < _DIV_MIN_SAMPLES + 2:
            return []
        btc_closes = await _fetch_btc_closes(hours=total_hours + 1)
        if not btc_closes:
            return []
        paired = _pair_snapshots_with_btc(snapshots, btc_closes)
        if len(paired) < _DIV_MIN_SAMPLES + 2:
            return []

        display_cutoff = time.time() - (hours * 3600)
        out: List[dict] = []
        # For each paired row, compute divergence against its trailing baseline
        for i in range(1, len(paired)):
            row = paired[i]
            if row["ts"] < display_cutoff:
                continue
            trailing = paired[: i + 1]
            if len(trailing) < _DIV_MIN_SAMPLES:
                continue
            div = _compute_divergence(trailing)
            if div is None:
                continue
            out.append({
                "ts": row["ts"],
                "score_6h": div["score_6h"],
                "label": div["label"],
                "confirmed": div["confirmed"],
            })
        return out
    except Exception as exc:
        logger.debug("hl_bridge: divergence history failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BridgeWindow:
    inflow_usd: float = 0.0
    outflow_usd: float = 0.0
    net_usd: float = 0.0
    tx_count: int = 0
    inflow_count: int = 0
    outflow_count: int = 0
    # True when our transfer sample covers this full window, False when the
    # oldest sampled transfer is newer than the window start (i.e. we're only
    # seeing a partial slice of the period).
    complete: bool = False


@dataclass
class BridgeFlowSnapshot:
    w1h: BridgeWindow = field(default_factory=BridgeWindow)
    w6h: BridgeWindow = field(default_factory=BridgeWindow)
    w24h: BridgeWindow = field(default_factory=BridgeWindow)
    w7d: BridgeWindow = field(default_factory=BridgeWindow)
    trend: str = "NEUTRAL"          # INFLOW | OUTFLOW | NEUTRAL
    signal: str = "BALANCED"        # ACCUMULATING | DEPLETING | BALANCED
    last_tx_time: int = 0
    tx_sample_size: int = 0
    sample_span_seconds: int = 0    # age of oldest tx in sample
    fetched_at: float = 0.0


# ---------------------------------------------------------------------------
# Fetcher singleton
# ---------------------------------------------------------------------------

def _get_fetcher() -> Optional[EtherscanFetcher]:
    """Return a cached EtherscanFetcher for Arbitrum, or None if no API key."""
    global _fetcher
    if _fetcher is not None:
        return _fetcher

    key = os.environ.get("ETHERSCAN_API_KEY") or os.environ.get("ARBISCAN_API_KEY")
    if not key:
        logger.warning("hl_bridge: no ETHERSCAN_API_KEY set, bridge tracker disabled")
        return None

    _fetcher = EtherscanFetcher(
        chain_id="arbitrum",
        api_base="https://api.etherscan.io/v2/api",
        api_key=key,
        etherscan_chain_id=ARB_CHAIN_ID,
    )
    return _fetcher


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(transfers: List[EtherscanTransfer], now_ts: int) -> BridgeFlowSnapshot:
    """Bucket transfers into rolling time windows relative to now.

    USDC on Arbitrum is 6 decimals; the fetcher already normalizes ``value``
    to human-readable units (so value == USD).

    Each window is tagged ``complete=True`` only if the oldest transfer in
    our sample is at least as old as the window start — otherwise the window
    is a partial slice and the frontend will show it muted.
    """
    windows = {
        WINDOW_1H: BridgeWindow(),
        WINDOW_6H: BridgeWindow(),
        WINDOW_24H: BridgeWindow(),
        WINDOW_7D: BridgeWindow(),
    }
    last_tx_time = 0
    oldest_tx_time: Optional[int] = None

    for tx in transfers:
        if tx.token_contract.lower() != ARB_USDC:
            continue
        age = now_ts - tx.timestamp
        if age < 0 or age > WINDOW_7D:
            continue
        if tx.timestamp > last_tx_time:
            last_tx_time = tx.timestamp
        if oldest_tx_time is None or tx.timestamp < oldest_tx_time:
            oldest_tx_time = tx.timestamp

        usd = float(tx.value)
        is_inflow = tx.to_addr.lower() == HL_BRIDGE_ADDRESS
        is_outflow = tx.from_addr.lower() == HL_BRIDGE_ADDRESS
        if not (is_inflow or is_outflow):
            continue

        for win_len, bucket in windows.items():
            if age <= win_len:
                bucket.tx_count += 1
                if is_inflow:
                    bucket.inflow_usd += usd
                    bucket.inflow_count += 1
                else:
                    bucket.outflow_usd += usd
                    bucket.outflow_count += 1
                bucket.net_usd = bucket.inflow_usd - bucket.outflow_usd

    # Mark each window complete only if our sample actually reaches back that far
    sample_span = (now_ts - oldest_tx_time) if oldest_tx_time else 0
    for win_len, bucket in windows.items():
        bucket.complete = sample_span >= win_len

    snap = BridgeFlowSnapshot(
        w1h=windows[WINDOW_1H],
        w6h=windows[WINDOW_6H],
        w24h=windows[WINDOW_24H],
        w7d=windows[WINDOW_7D],
        last_tx_time=last_tx_time,
        tx_sample_size=len(transfers),
    )
    snap.sample_span_seconds = sample_span

    # Trend/signal labels prefer the 24h window if we have enough sample,
    # otherwise fall back to 6h so we don't classify off a 1-hour blip.
    decision = snap.w24h if snap.w24h.complete else snap.w6h
    gross = decision.inflow_usd + decision.outflow_usd
    if gross <= 0:
        snap.trend = "NEUTRAL"
        snap.signal = "BALANCED"
    else:
        net_pct = decision.net_usd / gross  # -1..+1
        if net_pct >= 0.25:
            snap.trend = "INFLOW"
            # Strong inflow with meaningful volume → ACCUMULATING
            snap.signal = "ACCUMULATING" if decision.inflow_usd >= 5_000_000 else "BALANCED"
        elif net_pct <= -0.25:
            snap.trend = "OUTFLOW"
            snap.signal = "DEPLETING" if decision.outflow_usd >= 5_000_000 else "BALANCED"
        else:
            snap.trend = "NEUTRAL"
            snap.signal = "BALANCED"

    return snap


def _snapshot_to_dict(snap: BridgeFlowSnapshot) -> dict:
    def _w(b: BridgeWindow) -> dict:
        return {
            "inflow_usd": round(b.inflow_usd, 2),
            "outflow_usd": round(b.outflow_usd, 2),
            "net_usd": round(b.net_usd, 2),
            "tx_count": b.tx_count,
            "inflow_count": b.inflow_count,
            "outflow_count": b.outflow_count,
            "complete": b.complete,
        }
    return {
        "bridge_address": HL_BRIDGE_ADDRESS,
        "chain": "arbitrum",
        "token": "USDC",
        "trend": snap.trend,
        "signal": snap.signal,
        "last_tx_time": snap.last_tx_time,
        "tx_sample_size": snap.tx_sample_size,
        "sample_span_seconds": snap.sample_span_seconds,
        "fetched_at": snap.fetched_at,
        "w1h": _w(snap.w1h),
        "w6h": _w(snap.w6h),
        "w24h": _w(snap.w24h),
        "w7d": _w(snap.w7d),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_bridge_flow(force_refresh: bool = False) -> Optional[dict]:
    """Return cached bridge flow snapshot as a dict, or None if disabled."""
    global _cache_expires_at, _cache_payload

    now = time.time()
    if not force_refresh and _cache_payload is not None and _cache_expires_at > now:
        return _cache_payload

    fetcher = _get_fetcher()
    if fetcher is None:
        return None

    # Pull enough to cover the 24h window without blowing RAM.
    # At ~230 tx/h, 6000 covers ~26h with headroom. Reduced from 10000
    # to cut memory spikes during parsing (~40% less peak allocation).
    try:
        transfers = await asyncio.wait_for(
            fetcher.get_address_transfers(
                address=HL_BRIDGE_ADDRESS,
                contract=ARB_USDC,
                offset=6000,
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.warning("hl_bridge: arbiscan timeout")
        return _cache_payload  # serve stale on timeout
    except Exception as exc:
        logger.warning("hl_bridge: fetch failed: %s", exc)
        return _cache_payload

    if not transfers:
        logger.warning("hl_bridge: empty transfer list from arbiscan")
        # Still emit an empty snapshot so the UI can show "no data"
        snap = BridgeFlowSnapshot()
        snap.fetched_at = now
        payload = _snapshot_to_dict(snap)
        _cache_payload = payload
        _cache_expires_at = now + _CACHE_TTL_S
        return payload

    snap = _aggregate(transfers, int(now))
    snap.fetched_at = now
    payload = _snapshot_to_dict(snap)
    _cache_payload = payload
    _cache_expires_at = now + _CACHE_TTL_S
    span_h = snap.sample_span_seconds / 3600.0 if snap.sample_span_seconds else 0.0
    logger.info(
        "hl_bridge: sampled %d txs (%.1fh span), 24h net=$%s, trend=%s, 24h_complete=%s",
        len(transfers), span_h,
        f"{snap.w24h.net_usd:,.0f}",
        snap.trend,
        snap.w24h.complete,
    )
    # Persist to SQLite for historical sparkline (never raises on failure).
    _persist_snapshot(payload)

    # Merge BTC × flow divergence. Requires ≥24 snapshots of history, so it'll
    # be absent during the first ~4h after a cold start. Never raises.
    divergence = await _compute_latest_divergence()
    if divergence is not None:
        payload["divergence"] = divergence

    return payload


async def close_fetcher() -> None:
    """Close the shared EtherscanFetcher session (call on app shutdown)."""
    global _fetcher
    if _fetcher is not None:
        try:
            await _fetcher.close()
        except Exception:
            pass
        _fetcher = None
