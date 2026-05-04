"""
scanner.py
~~~~~~~~~~
Scan orchestrator -- coordinates RCCE, Heatmap, and Exhaustion engines
across crypto symbols on multiple timeframes (4h, 1d).

Responsibilities
----------------
1. Run scans across all watchlist symbols x timeframes
2. Coordinate three independent engines per symbol
3. Compute market-wide consensus (Module 11)
4. Detect BTC-relative divergences (Module 12)
5. Synthesize final signals via cross-engine Decision Matrix
6. Fetch global market data (BTC dominance, alt market cap)
7. Calculate alt-season gauge (with real market cap when available)
8. Cache results in memory for the API layer

Public API (imported by main.py)
--------------------------------
    cache       -- module-level ScanCache instance
    run_scan    -- async function; also exposes a sync wrapper
    get_scan_status
    get_all_results
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import time
from functools import partial
from typing import Dict, List, Optional


def _malloc_trim():
    """Ask glibc/jemalloc to release unused memory back to the OS."""
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass

# Thread pool for CPU-bound engine work (symbol processing + signal synthesis)
_CPU_WORKERS = int(os.environ.get("ENGINE_WORKERS", min(2, os.cpu_count() or 2)))
_engine_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=_CPU_WORKERS,
    thread_name_prefix="rcce-engine",
)

from data_fetcher import fetch_batch, fetch_ohlcv, DEFAULT_SYMBOLS, \
    fetch_batch_hip3, fetch_batch_yfinance, TRADFI_SYMBOLS, TRADFI_SYMBOL_LIST, TRADFI_COIN_MAP, \
    _ohlcv_store
from engines.rcce_engine import compute_rcce
from engines.heatmap_engine import compute_heatmap
from engines.exhaustion_engine import compute_exhaustion
from engines.positioning_engine import compute_positioning, OI_CHANGE_THRESHOLD, interpret_oi_context
from signal_synthesizer import synthesize_signal
from market_data import (
    fetch_global_metrics, GlobalMetrics,
    fetch_fear_greed, fetch_stablecoin_supply,
)
# binance_futures_data removed — Binance geo-blocked on Railway
from hyperliquid_data import fetch_hyperliquid_metrics
from confluence import compute_all_confluences
import favorites as fav_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Asset classification
# ---------------------------------------------------------------------------

MEME_TOKENS = {"DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "MEME"}


def classify_asset(symbol: str) -> str:
    """Classify a trading pair into BTC / ETH / MEME / ALT.

    Matches on the *base* currency only so that ALT/BTC pairs
    (e.g. XMR/BTC) are correctly classified as ALT, not BTC.
    """
    base = symbol.upper().split("/")[0]
    if base == "BTC":
        return "BTC"
    if base == "ETH":
        return "ETH"
    if base in MEME_TOKENS:
        return "MEME"
    return "ALT"


# ---------------------------------------------------------------------------
# Consensus (Module 11)
# ---------------------------------------------------------------------------

# Regimes that count as accumulation-family for consensus purposes
_ACCUM_FAMILY = {"ACCUM", "CAP", "REACC"}


def compute_consensus(results: List[dict]) -> dict:
    """Compute the market-wide consensus from all scan results.

    Counts each symbol's regime into four buckets:
        markup, blowoff, markdown, accum (ACCUM + CAP + REACC).

    Decision rules:
        markup  / total > 0.6  ->  RISK-ON
        blowoff / total > 0.5  ->  EUPHORIA
        markdown/ total > 0.5  ->  RISK-OFF
        accum   / total > 0.5  ->  ACCUMULATION
        else                   ->  MIXED

    Returns
    -------
    dict
        ``consensus``  -- label string (RISK-ON, EUPHORIA, RISK-OFF,
                          ACCUMULATION, MIXED)
        ``strength``   -- 0-100 float indicating how dominant the winning
                          bucket is
        ``counts``     -- raw regime bucket counts
    """
    total = len(results)
    if total == 0:
        return {"consensus": "MIXED", "strength": 0.0, "counts": {}}

    markup_n = 0
    blowoff_n = 0
    markdown_n = 0
    accum_n = 0

    for r in results:
        regime = r.get("regime", "FLAT").upper()
        if regime == "MARKUP":
            markup_n += 1
        elif regime == "BLOWOFF":
            blowoff_n += 1
        elif regime == "MARKDOWN":
            markdown_n += 1
        elif regime in _ACCUM_FAMILY:
            accum_n += 1
        # FLAT and unknown regimes are not counted in any bucket

    counts = {
        "markup": markup_n,
        "blowoff": blowoff_n,
        "markdown": markdown_n,
        "accum": accum_n,
        "total": total,
    }

    # Decision rules (evaluated in priority order, uniform 55% threshold)
    if markup_n / total > 0.55:
        consensus = "RISK-ON"
        strength = (markup_n / total) * 100.0
    elif blowoff_n / total > 0.55:
        consensus = "EUPHORIA"
        strength = (blowoff_n / total) * 100.0
    elif markdown_n / total > 0.55:
        consensus = "RISK-OFF"
        strength = (markdown_n / total) * 100.0
    elif accum_n / total > 0.55:
        consensus = "ACCUMULATION"
        strength = (accum_n / total) * 100.0
    else:
        consensus = "MIXED"
        # Strength = dominance of the largest bucket
        max_bucket = max(markup_n, blowoff_n, markdown_n, accum_n)
        strength = (max_bucket / total) * 100.0

    return {
        "consensus": consensus,
        "strength": round(strength, 1),
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Divergence detection (Module 12)
# ---------------------------------------------------------------------------

def detect_divergence(symbol_regime: str, btc_regime: str) -> Optional[str]:
    """Compare a symbol's regime against BTC's regime.

    Returns
    -------
    str or None
        ``"BEAR-DIV"`` -- symbol is in MARKUP/REACC while BTC is in
                          MARKDOWN/BLOWOFF (bearish divergence)
        ``"BULL-DIV"`` -- symbol is in MARKDOWN/CAP while BTC is in MARKUP
                          (bullish divergence)
        ``None``       -- no divergence detected
    """
    sym = symbol_regime.upper()
    btc = btc_regime.upper()

    if sym in ("MARKUP", "REACC") and btc == "MARKDOWN":
        return "BEAR-DIV"
    if sym in ("MARKDOWN", "CAP") and btc == "MARKUP":
        return "BULL-DIV"
    return None


# ---------------------------------------------------------------------------
# Alt-season gauge (upgraded with real market cap data)
# ---------------------------------------------------------------------------

def compute_alt_season_gauge(
    results: List[dict],
    global_metrics: Optional[GlobalMetrics] = None,
) -> dict:
    """Calculate an alt-season gauge from scan results and global market data.

    When global_metrics is available (from CoinGecko), the score blends
    real alt market cap dominance with regime-based analysis.  Falls back
    to pure regime counting when global data is unavailable.

    Returns
    -------
    dict
        ``score``        -- 0-100 alt-season score
        ``label``        -- HOT / ACTIVE / NEUTRAL / WEAK / COLD
        ``alts_up``      -- count of alts in bullish regimes
        ``total_alts``   -- count of alt symbols in scan
        ``btc_dominance``-- BTC.D percentage (if available)
    """
    alts = [r for r in results if r.get("asset_class") in ("ALT", "MEME")]
    total_alts = len(alts)
    btc_dom = global_metrics.btc_dominance if global_metrics else None

    if total_alts == 0:
        return {
            "score": 0.0,
            "label": "COLD",
            "alts_up": 0,
            "total_alts": 0,
            "btc_dominance": btc_dom,
        }

    alts_up = sum(
        1 for r in alts
        if r.get("regime", "").upper() in ("MARKUP", "REACC")
    )
    alt_pct = alts_up / total_alts

    # BTC status
    btc_results = [r for r in results if r.get("asset_class") == "BTC"]
    btc_bullish = any(
        r.get("regime", "").upper() in ("MARKUP", "REACC")
        for r in btc_results
    )

    # --- Compute score ---
    if global_metrics is not None and global_metrics.total_market_cap > 0:
        # Blend real dominance data with regime analysis
        # Alt dominance = 100 - BTC dominance (rough proxy)
        alt_dominance = 100.0 - global_metrics.btc_dominance

        # Regime-based component (how many alts are actually in markup)
        regime_score = alt_pct * 100.0

        # Blend: 40% dominance-based, 60% regime-based
        # Alt dominance > 60% is historically alt-season territory
        dominance_score = min(100.0, max(0.0, (alt_dominance - 40.0) / 30.0 * 100.0))
        score = dominance_score * 0.4 + regime_score * 0.6

        # Dampen if BTC is bullish but alts are lagging
        if btc_bullish and alt_pct < 0.3:
            score *= 0.6
    else:
        # Fallback: pure regime-counting
        if btc_bullish and alt_pct < 0.3:
            score = alt_pct * 100.0 * 0.5  # damped
        else:
            score = alt_pct * 100.0

    score = min(100.0, max(0.0, score))

    # Labels aligned with User Guide
    if score >= 75:
        label = "HOT"
    elif score >= 50:
        label = "ACTIVE"
    elif score >= 25:
        label = "NEUTRAL"
    elif score >= 10:
        label = "WEAK"
    else:
        label = "COLD"

    return {
        "score": round(score, 1),
        "label": label,
        "alts_up": alts_up,
        "total_alts": total_alts,
        "btc_dominance": btc_dom,
    }


# ---------------------------------------------------------------------------
# ScanCache
# ---------------------------------------------------------------------------

    # Tier-1 symbols: scanned every cycle (1 min)
TIER1_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "NEAR/USDT",
    "DOGE/USDT", "SUI/USDT", "ARB/USDT", "OP/USDT", "TIA/USDT",
    "PEPE/USDT", "WIF/USDT", "FET/USDT", "RNDR/USDT", "TAO/USDT",
    "AAVE/USDT", "RUNE/USDT", "TON/USDT", "HBAR/USDT", "INJ/USDT",
]

# How many tier-2 symbols to scan per rolling cycle
TIER2_CHUNK_SIZE = 40


class ScanCache:
    """In-memory store for the most recent scan results.

    Keyed by timeframe so the API can serve 4h and 1d results
    independently.
    """

    def __init__(self) -> None:
        self.results: Dict[str, List[dict]] = {}       # timeframe -> results
        self.consensus: Dict[str, dict] = {}            # timeframe -> consensus
        self.alt_season: Dict[str, dict] = {}           # timeframe -> alt gauge
        self.global_metrics: Optional[dict] = None      # latest global metrics
        self.sentiment: Optional[dict] = None           # Fear & Greed
        self.stablecoin: Optional[dict] = None          # Stablecoin supply
        self.confluence: Dict[str, dict] = {}           # symbol -> confluence
        self.prev_oi: Dict[str, float] = {}             # symbol -> previous OI (seeded on first scan)
        self.last_scan_time: Optional[float] = None
        self.is_scanning: bool = False
        self.symbols: List[str] = DEFAULT_SYMBOLS.copy()
        # TradFi (HIP-3) results — separate from crypto
        self.tradfi_results: Dict[str, List[dict]] = {}  # timeframe -> results
        # Rolling scan state
        self._rotation_offset: int = 0
        self._results_by_sym: Dict[str, Dict[str, dict]] = {}  # symbol -> {tf -> result}
        # Engine cache: stores only the last-closed-candle timestamp per (symbol, tf).
        # On hit, reuses result from _results_by_sym instead of storing a full copy.
        self._engine_cache: Dict[tuple, int] = {}
        # Anomaly detection results (served by /api/notifications/anomalies)
        self.anomalies: List[dict] = []
        # Symbols with active anomalies — promoted to "hot" tier in drip scan
        self.anomaly_hot_symbols: set = set()
        # Latest exchange metrics (for anomaly cross-exchange confirmation
        # + cross-exchange funding/OI widget served to CoinPage)
        self._last_hl_metrics: dict = {}
        self._last_binance_metrics: dict = {}
        self._last_bybit_metrics: dict = {}
        # Signal-age tracking: when did each (symbol, tf) enter its current
        # signal? Reset on every transition. Exposed via scan result so the
        # UI can show "fired 2.1d ago" without hitting the DB.
        self.signal_first_seen_at: Dict[tuple, float] = {}
        self.signal_first_seen_label: Dict[tuple, str] = {}

    # -- query helpers -----------------------------------------------------

    def get_results(
        self,
        timeframe: str,
        regime: Optional[str] = None,
        signal: Optional[str] = None,
        asset_class: Optional[str] = None,
    ) -> List[dict]:
        """Return cached results for *timeframe*, optionally filtered."""
        items = self.results.get(timeframe, [])
        if regime is not None:
            regime_upper = regime.upper()
            items = [r for r in items if r.get("regime", "").upper() == regime_upper]
        if signal is not None:
            signal_upper = signal.upper()
            items = [r for r in items if r.get("signal", "").upper() == signal_upper]
        if asset_class is not None:
            ac_upper = asset_class.upper()
            items = [r for r in items if r.get("asset_class", "").upper() == ac_upper]
        return items

    def get_cache_age(self) -> Optional[float]:
        """Seconds since the last successful scan, or *None*."""
        if self.last_scan_time is None:
            return None
        return time.time() - self.last_scan_time


# ---------------------------------------------------------------------------
# Module-level cache instance
# ---------------------------------------------------------------------------

cache = ScanCache()


# ---------------------------------------------------------------------------
# Priority score (composite 0-100 ranking)
# ---------------------------------------------------------------------------

def _compute_priority(r: dict, anomaly_symbols: set = None) -> float:
    """Compute a composite priority score (0-100) for ranking symbols.

    Signal strength is the primary driver — STRONG_LONG and LIGHT_LONG
    coins should always rank above WAIT/neutral coins regardless of
    anomaly status. Anomalies still surface in the alert system.

    Factors (total = 100 pts):
        1. Signal tier:        0-40 pts  (STRONG_LONG=40, LIGHT_LONG=30, ACCUMULATE=20, etc.)
        2. Conditions met:     0-20 pts  (% of conditions satisfied)
        3. BMSB proximity:     0-10 pts  (above BMSB = positive structure)
        4. Floor confirmed:    0 or  8   (binary bonus for ACCUM/CAP)
        5. Momentum:           0- 7 pts  (normalised)
        6. Heat headroom:      0- 5 pts  (low heat = more room to run)
        7. CVD / spot confirm: 0- 5 pts  (directional confirmation)
        8. Volume/absorption:  0- 5 pts  (rel_vol + absorption)
    """
    score = 0.0

    # 1. Signal tier: 0-40 pts — this is the dominant factor
    signal = r.get("signal", "WAIT")
    _SIGNAL_TIER = {
        "STRONG_LONG": 40,
        "LIGHT_LONG": 30,
        "ACCUMULATE": 22,
        "REVIVAL_SEED_CONFIRMED": 20,
        "REVIVAL_SEED": 18,
        "LIGHT_SHORT": 15,
        "TRIM": 10,
        "TRIM_HARD": 10,
        "RISK_OFF": 8,
        "NO_LONG": 5,
        "WAIT": 0,
    }
    score += _SIGNAL_TIER.get(signal, 0)

    # 2. Conditions met: 0-20 pts
    cond = r.get("conditions_met", 0)
    cond_total = max(r.get("conditions_total", 10), 1)
    score += (cond / cond_total) * 20

    # 3. BMSB proximity: 0-10 pts (above BMSB = bullish structure)
    dev = r.get("deviation_pct", -50)
    dev_clamped = max(-50.0, min(50.0, dev))
    score += ((dev_clamped + 50) / 100) * 10

    # 4. Floor confirmed: 0 or 8 pts
    if r.get("floor_confirmed", False):
        score += 8

    # 5. Momentum: 0-7 pts
    mom = r.get("momentum", -10)
    mom_clamped = max(-10.0, min(10.0, mom))
    score += ((mom_clamped + 10) / 20) * 7

    # 6. Heat inverted: 0-5 pts (low heat = more upside room)
    heat = r.get("heat", 50)
    score += ((100 - min(heat, 100)) / 100) * 5

    # 7. CVD / spot dominance confirmation: 0-5 pts
    cvd_trend_val = r.get("cvd_trend", "NEUTRAL")
    positioning_val = r.get("positioning") or {}
    _exit_sigs = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}
    if signal not in _exit_sigs and cvd_trend_val == "BULLISH":
        score += 3
    elif signal in _exit_sigs and cvd_trend_val == "BEARISH":
        score += 3
    if positioning_val.get("spot_dominance") == "SPOT_LED":
        score += 2

    # 8. Volume / absorption: 0-5 pts
    rel_vol = min(r.get("rel_vol", 1.0), 5.0)
    score += (rel_vol / 5.0) * 2.5
    if r.get("is_absorption", False):
        score += 2.5

    return round(min(100.0, max(0.0, score)), 1)


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------

def _process_symbol(
    symbol: str,
    timeframe: str,
    ohlcv: dict,
    weekly: Optional[dict],
    btc_data: Optional[dict],
    eth_data: Optional[dict],
) -> dict:
    """Run all three engines for a single symbol and merge into one result dict.

    Each engine call is independently guarded -- if one fails the others
    still contribute.

    NOTE: This produces a ``raw_signal`` from the RCCE engine.  The final
    ``signal`` is set to "WAIT" here and overwritten by the signal
    synthesizer after consensus and divergence are computed.
    """
    # --- RCCE engine -------------------------------------------------------
    # Skip beta calculation for /BTC pairs (currency mismatch with USD reference)
    quote = symbol.split("/")[1] if "/" in symbol else "USDT"
    is_btc_quoted = quote == "BTC"

    rcce: dict = {}
    try:
        rcce = compute_rcce(
            ohlcv,
            None if is_btc_quoted else btc_data,
            None if is_btc_quoted else eth_data,
        )
    except Exception:
        logger.exception("RCCE engine failed for %s (%s)", symbol, timeframe)

    # --- Heatmap engine ----------------------------------------------------
    heatmap: dict = {}
    if weekly is not None:
        try:
            heatmap = compute_heatmap(ohlcv, weekly)
        except Exception:
            logger.exception("Heatmap engine failed for %s (%s)", symbol, timeframe)

    # --- Exhaustion engine -------------------------------------------------
    exhaustion: dict = {}
    if weekly is not None:
        try:
            exhaustion = compute_exhaustion(ohlcv, weekly)
        except Exception:
            logger.exception("Exhaustion engine failed for %s (%s)", symbol, timeframe)

    # --- Merge into ScanResult shape ---------------------------------------
    result: dict = {
        "symbol": symbol,
        "timeframe": timeframe,
        "price": float(ohlcv["close"][-1]),
        # RCCE fields
        "regime": rcce.get("regime", "FLAT"),
        "confidence": round(rcce.get("confidence", 0), 1),  # RCCE regime probability (legacy name kept for compat)
        "regime_probability": round(rcce.get("confidence", 0), 1),
        "raw_signal": rcce.get("raw_signal", "WAIT"),
        "signal": "WAIT",               # placeholder — synthesizer fills this
        "signal_reason": "",             # synthesizer fills
        "signal_warnings": [],           # synthesizer fills
        "zscore": round(rcce.get("z_score", 0), 3),
        "energy": round(rcce.get("energy", 0), 3),
        "vol_state": rcce.get("vol_state", "MID"),
        "momentum": round(rcce.get("momentum", 0), 2),
        "vol_scale": rcce.get("vol_scale", 1.0),
        "divergence": None,  # populated after consensus pass
        "asset_class": classify_asset(symbol),
        # Heatmap fields
        "heat": heatmap.get("heat", 0),
        "heat_direction": heatmap.get("direction", 0),
        "heat_phase": heatmap.get("phase", "Neutral"),
        "atr_regime": heatmap.get("atr_regime", "Normal"),
        "deviation_pct": round(heatmap.get("deviation_pct", 0), 2),
        # Exhaustion fields
        "exhaustion_state": exhaustion.get("state", "NEUTRAL"),
        "floor_confirmed": exhaustion.get("floor_confirmed", False),
        "is_absorption": exhaustion.get("is_absorption", False),
        "is_climax": exhaustion.get("is_climax", False),
        "effort": round(exhaustion.get("effort", 0), 3),
        "rel_vol": round(exhaustion.get("rel_vol", 0), 2),
        # Sparkline: last 24 close prices
        "sparkline": [round(float(c), 6) for c in ohlcv["close"][-24:]],
        # Extra engine fields (persisted via context JSON in signal_log)
        "deviation_abs": round(heatmap.get("deviation_abs", 0), 4),
        "bmsb_mid": round(heatmap.get("bmsb_mid", 0), 4),
        "r3": round(heatmap.get("r3", 0), 4),
        "dist_pct": round(exhaustion.get("dist_pct", 0), 4),
        "w_bmsb": round(exhaustion.get("w_bmsb", 0), 4),
        "beta_btc": round(rcce.get("beta_btc", 0), 4),
        "beta_eth": round(rcce.get("beta_eth", 0), 4),
        "atr_ratio": round(rcce.get("atr_ratio", 0), 3),
        "regime_probabilities": rcce.get("regime_probabilities", {}),
    }
    return result


# ---------------------------------------------------------------------------
# Extracted helpers -- shared by _scan_timeframe and drip scan
# ---------------------------------------------------------------------------

def _attach_positioning(
    result: dict,
    hl_metrics: dict,
    binance_metrics: dict,
    bybit_metrics: dict,
    cg_metrics: dict,
    scan_cache: "ScanCache",
) -> str:
    """Attach positioning data to a scan result (mutates in-place).

    Priority: Binance → Hyperliquid → Bybit.
    CoinGlass overlays (liq, LSR, spot) applied when available.
    Returns the source string ("binance", "hyperliquid", "bybit", or "").
    """
    symbol = result["symbol"]
    bn = binance_metrics.get(symbol) if binance_metrics else None
    hl = hl_metrics.get(symbol) if hl_metrics else None
    by = bybit_metrics.get(symbol) if bybit_metrics else None

    funding_rate = 0.0
    open_interest = 0.0
    predicted_funding = 0.0
    mark_price = 0.0
    oracle_price = 0.0
    volume_24h = 0.0
    source = ""

    if bn is not None and bn.open_interest > 0:
        funding_rate = bn.funding_rate
        open_interest = bn.open_interest
        mark_price = bn.mark_price
        source = "binance"
        if hl is not None:
            volume_24h = hl.volume_24h
            predicted_funding = hl.predicted_funding
            oracle_price = hl.oracle_price
    elif hl is not None and hl.open_interest > 0:
        funding_rate = hl.funding_rate
        open_interest = hl.open_interest
        predicted_funding = hl.predicted_funding
        mark_price = hl.mark_price
        oracle_price = hl.oracle_price
        volume_24h = hl.volume_24h
        source = "hyperliquid"
    elif by is not None and by.open_interest > 0:
        funding_rate = by.funding_rate
        open_interest = by.open_interest
        mark_price = by.mark_price
        source = "bybit"

    if not source:
        return ""

    sparkline = result.get("sparkline", [])
    price_change_pct = 0.0
    if len(sparkline) >= 2 and sparkline[0] > 0:
        price_change_pct = ((sparkline[-1] - sparkline[0]) / sparkline[0]) * 100.0

    prev_oi = scan_cache.prev_oi.get(symbol)
    if prev_oi is None and open_interest > 0:
        scan_cache.prev_oi[symbol] = open_interest
        prev_oi = open_interest

    pos = compute_positioning(
        funding_rate=funding_rate,
        open_interest=open_interest,
        price_change_pct=price_change_pct,
        prev_oi=prev_oi,
        predicted_funding=predicted_funding,
        mark_price=mark_price,
        oracle_price=oracle_price,
        volume_24h=volume_24h,
    )

    source_map = {}
    if source == "binance":
        source_map["funding"] = "binance"
        source_map["oi"] = "binance"
        source_map["volume"] = "hyperliquid" if (hl is not None and hl.volume_24h > 0) else ""
        source_map["pred_funding"] = "hyperliquid" if (hl is not None and hl.predicted_funding != 0) else ""
    elif source == "hyperliquid":
        source_map["funding"] = "hyperliquid"
        source_map["oi"] = "hyperliquid"
        source_map["volume"] = "hyperliquid"
        source_map["pred_funding"] = "hyperliquid"
    elif source == "bybit":
        source_map["funding"] = "bybit"
        source_map["oi"] = "bybit"
        source_map["volume"] = ""
        source_map["pred_funding"] = ""

    result["positioning"] = {
        "funding_regime": pos.funding_regime,
        "funding_rate": pos.funding_rate,
        "oi_trend": pos.oi_trend,
        "oi_value": pos.oi_value,
        "oi_change_pct": pos.oi_change_pct,
        "leverage_risk": pos.leverage_risk,
        "predicted_funding": pos.predicted_funding,
        "mark_price": pos.mark_price,
        "volume_24h": pos.volume_24h,
        "source": source,
        "source_map": source_map,
        "liquidation_24h_usd": 0.0,
        "long_liq_usd": 0.0,
        "short_liq_usd": 0.0,
        "liquidation_4h_usd": 0.0,
        "liquidation_1h_usd": 0.0,
        "long_short_ratio": 1.0,
        "top_trader_lsr": 1.0,
        "oi_market_cap_ratio": 0.0,
        "spot_volume_usd": 0.0,
        "spot_futures_ratio": 0.0,
        "spot_dominance": "NEUTRAL",
    }
    scan_cache.prev_oi[symbol] = open_interest

    cg = cg_metrics.get(symbol) if cg_metrics else None
    if cg is not None:
        if cg.oi_change_pct_4h != 0:
            result["positioning"]["oi_change_pct"] = cg.oi_change_pct_4h
            _chg = cg.oi_change_pct_4h
            _p_up = price_change_pct > 0
            if   _chg >  OI_CHANGE_THRESHOLD and _p_up:       result["positioning"]["oi_trend"] = "BUILDING"
            elif _chg < -OI_CHANGE_THRESHOLD and _p_up:       result["positioning"]["oi_trend"] = "SQUEEZE"
            elif _chg < -OI_CHANGE_THRESHOLD and not _p_up:   result["positioning"]["oi_trend"] = "LIQUIDATING"
            elif _chg >  OI_CHANGE_THRESHOLD and not _p_up:   result["positioning"]["oi_trend"] = "SHORTING"
            else:                                              result["positioning"]["oi_trend"] = "STABLE"
            result["positioning"]["source_map"]["oi_trend"] = "coinglass"
        result["positioning"]["liquidation_24h_usd"] = cg.liquidation_usd_24h
        result["positioning"]["long_liq_usd"] = cg.long_liquidation_usd_24h
        result["positioning"]["short_liq_usd"] = cg.short_liquidation_usd_24h
        result["positioning"]["liquidation_4h_usd"] = cg.liquidation_usd_4h
        result["positioning"]["liquidation_1h_usd"] = cg.liquidation_usd_1h
        result["positioning"]["long_short_ratio"] = cg.long_short_ratio_4h
        result["positioning"]["top_trader_lsr"] = cg.top_trader_lsr
        result["positioning"]["oi_market_cap_ratio"] = cg.oi_market_cap_ratio
        result["positioning"]["source_map"]["oi_change"] = "coinglass"
        result["positioning"]["source_map"]["liq"] = "coinglass"
        if cg.spot_dominance != "NEUTRAL" or cg.spot_volume_usd > 0:
            result["positioning"]["spot_volume_usd"] = cg.spot_volume_usd
            result["positioning"]["spot_futures_ratio"] = cg.spot_futures_ratio
            result["positioning"]["spot_dominance"] = cg.spot_dominance
            result["positioning"]["source_map"]["spot"] = "coinglass"

    return source


async def _synthesize_and_enrich(
    results: List[dict],
    tf: str,
    consensus: dict,
    gm: Optional[GlobalMetrics],
    sentiment_data,
    stablecoin_data,
    macro_data,
    cg_metrics: dict,
    scan_cache: "ScanCache",
) -> dict:
    """Run divergence detection, signal synthesis, agent layer, and priority scoring.

    Mutates results in-place. Returns alt_gauge dict.
    """
    loop = asyncio.get_running_loop()

    # Divergences
    btc_regime = next(
        (r["regime"] for r in results if r["symbol"] == "BTC/USDT"),
        "FLAT",
    )
    for r in results:
        r["divergence"] = detect_divergence(r["regime"], btc_regime)

    # Prepare shared data for synthesis
    gm_dict = None
    if gm is not None:
        gm_dict = {
            "btc_dominance": gm.btc_dominance,
            "eth_dominance": gm.eth_dominance,
            "total_market_cap": gm.total_market_cap,
            "alt_market_cap": gm.alt_market_cap,
        }

    sentiment_dict = None
    if sentiment_data is not None:
        sentiment_dict = {
            "fear_greed_value": sentiment_data.fear_greed_value,
            "fear_greed_label": sentiment_data.fear_greed_label,
        }

    stablecoin_dict = None
    if stablecoin_data is not None:
        stablecoin_dict = {
            "trend": stablecoin_data.trend,
            "change_7d_pct": stablecoin_data.change_7d_pct,
            "total_cap": stablecoin_data.total_stablecoin_cap,
        }

    if not hasattr(scan_cache, 'prev_heat'):
        scan_cache.prev_heat = {}
    prev_heat_snapshot = dict(scan_cache.prev_heat)

    # Regime instability tracking — lazily init per-symbol timestamp lists.
    # A symbol with ≥3 regime changes in 7 days is classified as "chop" and
    # cannot produce STRONG_LONG (data shows this is noise, not regime).
    if not hasattr(scan_cache, 'regime_change_log'):
        scan_cache.regime_change_log = {}  # tf_key → List[float] of change timestamps
    if not hasattr(scan_cache, 'prev_regime_by_tf'):
        scan_cache.prev_regime_by_tf = {}  # tf_key → last seen regime
    _REGIME_INSTABILITY_WINDOW_S = 7 * 24 * 3600  # 7 days
    _REGIME_INSTABILITY_MIN_CHANGES = 3

    _etf_flow = macro_data.etf_flow_usd_7d if macro_data else 0.0
    _cb_premium = macro_data.coinbase_premium_rate if macro_data else 0.0
    _cg_symbols = set(cg_metrics.keys()) if cg_metrics else set()

    # Fetch HyperLens whale consensus (thread-safe read of in-memory dict)
    try:
        from hl_intelligence import get_all_consensus as _hl_get_all, _normalize_coin as _hl_norm
        _hl_consensus = _hl_get_all()  # Dict[str, SymbolConsensus]
    except Exception:
        _hl_consensus = {}

    def _synth_one(r):
        heat_direction = r.get("heat_direction", 0)
        deviation_pct = r.get("deviation_pct", 0.0)
        heat_val = r.get("heat", 0)
        bmsb_valid = not (heat_val == 0 and heat_direction == 0 and deviation_pct == 0.0)
        macro_blocked = True if not bmsb_valid else heat_direction < 0
        symbol = r.get("symbol", "")
        prev_heat = prev_heat_snapshot.get(symbol, 0)

        # Regime instability: record changes, count how many happened in the
        # last 7 days. Symbols with ≥3 changes are classified as chop.
        current_regime = r.get("regime", "FLAT").upper()
        tf_key = f"{symbol}:{tf}"
        now_ts = time.time()
        prev_regime_seen = scan_cache.prev_regime_by_tf.get(tf_key)
        if prev_regime_seen is not None and prev_regime_seen != current_regime:
            log = scan_cache.regime_change_log.setdefault(tf_key, [])
            log.append(now_ts)
            # Prune anything older than the window
            cutoff = now_ts - _REGIME_INSTABILITY_WINDOW_S
            scan_cache.regime_change_log[tf_key] = [t for t in log if t >= cutoff]
        scan_cache.prev_regime_by_tf[tf_key] = current_regime

        recent_changes = len(scan_cache.regime_change_log.get(tf_key, []))
        regime_unstable = recent_changes >= _REGIME_INSTABILITY_MIN_CHANGES
        r["regime_changes_7d"] = recent_changes
        r["regime_unstable"] = regime_unstable

        # Look up HyperLens consensus for this symbol
        hl_coin = _hl_norm(symbol) if _hl_consensus else None
        hl_data = _hl_consensus.get(hl_coin) if hl_coin else None

        return synthesize_signal(
            r, consensus, gm_dict,
            positioning=r.get("positioning"),
            sentiment=sentiment_dict,
            stablecoin=stablecoin_dict,
            macro_blocked=macro_blocked,
            prev_heat=prev_heat,
            bmsb_valid=bmsb_valid,
            cvd_trend=r.get("cvd_trend", "NEUTRAL"),
            cvd_divergence=r.get("cvd_divergence", False),
            spot_dominance=(r.get("positioning") or {}).get("spot_dominance", "NEUTRAL"),
            long_short_ratio=(r.get("positioning") or {}).get("long_short_ratio", 1.0),
            liquidation_24h_usd=(r.get("positioning") or {}).get("liquidation_24h_usd", 0.0),
            etf_flow_usd=_etf_flow,
            cb_premium=_cb_premium,
            has_coinglass=symbol in _cg_symbols,
            hl_consensus_trend=hl_data.trend if hl_data else "NEUTRAL",
            hl_consensus_confidence=hl_data.confidence if hl_data else 0.0,
            hl_consensus_net_ratio=hl_data.net_ratio if hl_data else 0.0,
            has_hyperlens=hl_data is not None,
        )

    synth_futures = [
        loop.run_in_executor(_engine_pool, _synth_one, r)
        for r in results
    ]
    synth_results = await asyncio.gather(*synth_futures, return_exceptions=True)

    for r, synth in zip(results, synth_results):
        if isinstance(synth, Exception):
            logger.exception("Signal synthesis failed for %s: %s", r.get("symbol"), synth)
            r["signal"] = r.get("raw_signal", "WAIT")
            r["signal_reason"] = "synthesis error — using raw signal"
            r["signal_warnings"] = ["Signal synthesizer encountered an error"]
            r["conditions_detail"] = []
            r["conditions_met"] = 0
            r["conditions_total"] = 10
        else:
            r["signal"] = synth.signal
            r["signal_reason"] = synth.reason
            r["signal_warnings"] = synth.warnings
            r["signal_confidence"] = (
                round(synth.conditions_met / synth.conditions_total * 100)
                if synth.conditions_total > 0 else 0
            )
            r["conditions_detail"] = synth.conditions_detail
            r["conditions_met"] = synth.conditions_met
            r["conditions_total"] = synth.conditions_total
            r["effective_conditions"] = synth.effective_conditions
            r["vol_scale"] = synth.vol_scale
            # Signed conviction score -100..+100 (bullish/bearish magnitude)
            from signal_synthesizer import compute_signal_score
            r["signal_score"] = compute_signal_score(
                synth.signal, synth.effective_conditions, synth.conditions_total,
            )
            oi_trend = (r.get("positioning") or {}).get("oi_trend", "STABLE")
            r["oi_context"] = interpret_oi_context(oi_trend, synth.signal)
            scan_cache.prev_heat[r.get("symbol", "")] = r.get("heat", 0)

            # Signal age — reset timestamp whenever the signal changes so the
            # UI can show "fired Nd ago" without querying the DB.
            sym = r.get("symbol", "")
            age_key = (sym, tf)
            prev_label = scan_cache.signal_first_seen_label.get(age_key)
            if prev_label != synth.signal:
                scan_cache.signal_first_seen_at[age_key] = time.time()
                scan_cache.signal_first_seen_label[age_key] = synth.signal
            r["signal_first_seen_at"] = scan_cache.signal_first_seen_at.get(age_key)
            r["signal_age_seconds"] = (
                int(time.time() - scan_cache.signal_first_seen_at[age_key])
                if age_key in scan_cache.signal_first_seen_at else 0
            )

            # Attach HyperLens smart money data for frontend divergence display
            symbol = r.get("symbol", "")
            hl_coin = _hl_norm(symbol) if _hl_consensus else None
            hl_data = _hl_consensus.get(hl_coin) if hl_coin else None
            if hl_data:
                r["smart_money"] = {
                    "trend": hl_data.trend,
                    "confidence": round(hl_data.confidence, 2),
                    "net_ratio": round(hl_data.net_ratio, 2),
                    "long_count": hl_data.long_count,
                    "short_count": hl_data.short_count,
                    "long_notional": round(hl_data.long_notional),
                    "short_notional": round(hl_data.short_notional),
                }

    # Agent layer
    try:
        from agent_layer import process as _agent_process
        _open_positions: list = []
        agent_override_count = 0
        for r in results:
            try:
                ao = _agent_process(r, _open_positions, scan_cache)
                if ao.alerts:
                    existing = r.get("signal_warnings", [])
                    r["signal_warnings"] = existing + [f"[Agent] {a}" for a in ao.alerts]
                if ao.adjusted_signal != ao.original_signal:
                    r["signal"] = ao.adjusted_signal
                    agent_override_count += 1
                # Attach confidence history for frontend sparkline (timeframe-scoped)
                sym = r.get("symbol", "")
                tf_key = f"{sym}:{tf}"
                conf_hist = scan_cache.confidence_history.get(tf_key, [])
                if conf_hist:
                    r["confidence_history"] = list(conf_hist)
                # Attach smoothed confidence
                if hasattr(scan_cache, "smoothed_confidence"):
                    r["smoothed_confidence"] = scan_cache.smoothed_confidence.get(tf_key)
                # Attach positioning metric histories for sparklines
                for hist_attr, result_key in (
                    ("funding_history",    "funding_history"),
                    ("oi_history",         "oi_history"),
                    ("oi_change_history",  "oi_change_history"),
                    ("lsr_history",        "lsr_history"),
                    ("bsr_history",        "bsr_history"),
                    ("spot_ratio_history", "spot_ratio_history"),
                    ("vpin_history",       "vpin_history"),
                ):
                    hist = getattr(scan_cache, hist_attr, {}).get(tf_key, [])
                    if hist:
                        r[result_key] = list(hist)
            except Exception as _ae:
                logger.debug("Agent layer skipped for %s: %s", r.get("symbol"), _ae)
        if agent_override_count:
            logger.info("Agent layer: %d signal overrides on %s", agent_override_count, tf)
    except ImportError:
        pass

    # Priority scores (signal strength is the primary factor)
    _anom_syms = getattr(scan_cache, "anomaly_hot_symbols", set())
    for r in results:
        r["priority_score"] = _compute_priority(r)
        # Flag anomaly symbols so the frontend can show an anomaly tier dot
        if r.get("symbol") in _anom_syms:
            r["has_anomaly"] = True

    signal_summary = {}
    for r in results:
        sig = r["signal"]
        signal_summary[sig] = signal_summary.get(sig, 0) + 1
    logger.info("Signal distribution for %s: %s", tf, signal_summary)

    alt_gauge = compute_alt_season_gauge(results, gm)
    return alt_gauge


async def _scan_timeframe(
    symbols: List[str],
    tf: str,
    scan_cache: Optional["ScanCache"] = None,
) -> tuple[List[dict], dict, dict, Optional[GlobalMetrics]]:
    """Run a full scan for one timeframe.

    Returns (results, consensus, alt_gauge, global_metrics).

    Pipeline
    --------
    1. Batch-fetch OHLCV data for the requested timeframe.
    2. Batch-fetch weekly data (required by heatmap + exhaustion engines).
    3. Extract BTC and ETH reference data for beta calculations.
    4. Process each symbol through all three engines (raw_signal only).
    5. Compute consensus across results.
    6. Fetch global market metrics (BTC dominance, alt market cap).
    7. Detect divergences.
    8. Synthesize final signals using cross-engine Decision Matrix.
    9. Compute alt-season gauge (using global metrics when available).
    """
    logger.info("Starting scan for timeframe=%s (%d symbols)", tf, len(symbols))
    t0 = time.time()

    # 1. Fetch OHLCV for all symbols at this timeframe
    ohlcv_batch = await fetch_batch(symbols, tf)
    fetched = sum(1 for v in ohlcv_batch.values() if v is not None)
    logger.info(
        "Fetched %d/%d symbols for %s (%.1fs)",
        fetched, len(symbols), tf, time.time() - t0,
    )

    # 2. Fetch weekly data for heatmap + exhaustion
    weekly_batch = await fetch_batch(symbols, "1w")
    weekly_fetched = sum(1 for v in weekly_batch.values() if v is not None)
    logger.info(
        "Fetched %d/%d weekly series (%.1fs total)",
        weekly_fetched, len(symbols), time.time() - t0,
    )

    # 3. BTC and ETH reference data
    btc_data = ohlcv_batch.get("BTC/USDT")
    eth_data = ohlcv_batch.get("ETH/USDT")

    # 4. Process each symbol through engines (parallel via thread pool)
    #    Skip engine recomputation when the last closed candle hasn't changed.
    #    OHLCV data only meaningfully changes when a new candle closes (every
    #    4h / 1d), so we cache engine results keyed by last-closed-candle
    #    timestamp and only rerun numpy when new bar data appears.
    loop = asyncio.get_running_loop()
    engine_futures = []
    engine_symbols = []
    cache_hits = 0
    cache_results: List[dict] = []  # results served from cache

    for symbol in symbols:
        ohlcv = ohlcv_batch.get(symbol)
        if ohlcv is None:
            logger.debug("Skipping %s -- no OHLCV data", symbol)
            continue

        # Determine the last closed candle timestamp
        timestamps = ohlcv.get("timestamp", [])
        # Last element is the live (still-forming) candle; second-to-last is
        # the most recently *closed* candle.
        last_closed_ts = int(timestamps[-2]) if len(timestamps) >= 2 else 0

        cache_key = (symbol, tf)
        cached_ts = scan_cache._engine_cache.get(cache_key) if scan_cache else None

        if cached_ts and cached_ts == last_closed_ts:
            # No new candle — reuse result from _results_by_sym
            prev = scan_cache._results_by_sym.get(symbol, {}).get(tf)
            if prev is not None:
                prev["price"] = float(ohlcv["close"][-1])
                cache_results.append(prev)
                cache_hits += 1
                continue

        weekly = weekly_batch.get(symbol)
        engine_symbols.append(symbol)
        engine_futures.append(
            loop.run_in_executor(
                _engine_pool,
                partial(
                    _process_symbol,
                    symbol=symbol,
                    timeframe=tf,
                    ohlcv=ohlcv,
                    weekly=weekly,
                    btc_data=btc_data,
                    eth_data=eth_data,
                ),
            )
        )

    results: List[dict] = list(cache_results)
    settled = await asyncio.gather(*engine_futures, return_exceptions=True)
    for symbol, outcome in zip(engine_symbols, settled):
        if isinstance(outcome, Exception):
            logger.exception("Failed to process %s on %s: %s", symbol, tf, outcome)
        else:
            results.append(outcome)
            if scan_cache:
                ohlcv = ohlcv_batch.get(symbol)
                timestamps = ohlcv.get("timestamp", []) if ohlcv else []
                last_closed_ts = int(timestamps[-2]) if len(timestamps) >= 2 else 0
                scan_cache._engine_cache[(symbol, tf)] = last_closed_ts

    logger.info(
        "Processed %d symbols for %s (%.1fs total, %d cache hits, %d recomputed)",
        len(results), tf, time.time() - t0, cache_hits, len(engine_symbols),
    )

    # 5. Compute consensus (BEFORE signal synthesis — signals need this)
    consensus = compute_consensus(results)
    logger.info(
        "Consensus for %s: %s (strength=%.1f%%)",
        tf, consensus["consensus"], consensus["strength"],
    )

    # 6. Fetch external data in parallel
    #    Binance (primary positioning) + Hyperliquid + globals + CoinGlass
    from binance_futures_data import fetch_binance_futures_metrics
    from bybit_futures_data import fetch_bybit_futures_metrics
    from coinglass_data import fetch_coinglass_metrics, fetch_macro_signals

    gm: Optional[GlobalMetrics] = None
    hl_metrics = {}
    binance_metrics = {}
    sentiment_data = None
    stablecoin_data = None
    cg_metrics: dict = {}
    macro_data = None

    results = await asyncio.gather(
        fetch_global_metrics(),
        fetch_hyperliquid_metrics(symbols),
        fetch_binance_futures_metrics(symbols),
        fetch_fear_greed(),
        fetch_stablecoin_supply(),
        fetch_coinglass_metrics(symbols),
        fetch_macro_signals(),
        return_exceptions=True,
    )
    _names = ["global_metrics", "hl_metrics", "binance_metrics", "sentiment", "stablecoin", "coinglass", "macro"]
    _defaults = [None, {}, {}, None, None, {}, None]
    for i, (name, res) in enumerate(zip(_names, results)):
        if isinstance(res, Exception):
            logger.warning("Fetch %s failed: %s", name, res)
            results[i] = _defaults[i]
    gm, hl_metrics, binance_metrics, sentiment_data, stablecoin_data, cg_metrics, macro_data = results

    if gm:
        logger.info(
            "Global metrics: BTC.D=%.1f%% ALT MCap=$%.0fB",
            gm.btc_dominance, gm.alt_market_cap / 1e9,
        )
    if binance_metrics:
        logger.info("Binance Futures: %d perps (positioning)", len(binance_metrics))
    if hl_metrics:
        logger.info("Hyperliquid: %d perps (positioning)", len(hl_metrics))
    if sentiment_data:
        logger.info("Fear & Greed: %d (%s)", sentiment_data.fear_greed_value, sentiment_data.fear_greed_label)
    if stablecoin_data:
        logger.info("Stablecoin: $%.1fB (%s)", stablecoin_data.total_stablecoin_cap / 1e9, stablecoin_data.trend)
    if cg_metrics:
        btc_cg = cg_metrics.get("BTC/USDT")
        logger.info(
            "CoinGlass: %d coins (BTC fund=%.3f%%/8h OI=$%.1fB liq24h=$%.0fM dom=%s)",
            len(cg_metrics),
            (btc_cg.funding_rate * 100 * 8) if btc_cg else 0,
            (btc_cg.open_interest_usd / 1e9) if btc_cg else 0,
            (btc_cg.liquidation_usd_24h / 1e6) if btc_cg else 0,
            btc_cg.spot_dominance if btc_cg else "N/A",
        )

    if macro_data:
        logger.info(
            "Macro: ETF 7d=$%.0fM 1d=$%.0fM CB premium=%.4f%% signal=%s",
            macro_data.etf_flow_usd_7d / 1e6,
            macro_data.etf_flow_usd_1d / 1e6,
            macro_data.coinbase_premium_rate * 100,
            macro_data.etf_signal,
        )

    # 6b. Fetch Bybit for symbols not covered by Binance or HL
    covered_symbols = set()
    if binance_metrics:
        covered_symbols.update(binance_metrics.keys())
    if hl_metrics:
        covered_symbols.update(s for s, m in hl_metrics.items() if m.open_interest > 0)
    gap_symbols = [s for s in symbols if s not in covered_symbols]

    bybit_metrics = {}
    if gap_symbols:
        try:
            bybit_metrics = await fetch_bybit_futures_metrics(gap_symbols)
            if bybit_metrics:
                logger.info("Bybit fallback: %d/%d gap symbols filled", len(bybit_metrics), len(gap_symbols))
        except Exception as exc:
            logger.warning("Bybit fallback fetch failed: %s", exc)
    if bybit_metrics:
        cache._last_bybit_metrics = bybit_metrics

    # 7. Compute positioning per symbol (using extracted helper)
    pos_counts = {"binance": 0, "hyperliquid": 0, "bybit": 0}
    for r in results:
        src = _attach_positioning(r, hl_metrics, binance_metrics, bybit_metrics, cg_metrics, cache)
        if src:
            pos_counts[src] = pos_counts.get(src, 0) + 1

    logger.info(
        "Positioning: %d Binance, %d Hyperliquid, %d Bybit (%d total)",
        pos_counts.get("binance", 0), pos_counts.get("hyperliquid", 0),
        pos_counts.get("bybit", 0), sum(pos_counts.values()),
    )

    # 7b. CVD batch fetch — dual-source strategy:
    #   Primary:  CoinGlass fetch_cvd_batch (multi-exchange: Binance+OKX+Bybit)
    #   Fallback: exchange_derivatives_data (free Binance API, no key required)
    #   Both run concurrently; CoinGlass result wins per-coin when available.

    # Build price_changes dict once — used by both sources
    price_changes_dict: dict = {}
    for r in results:
        sym = r.get("symbol", "")
        base_coin = sym.split("/")[0] if "/" in sym else sym
        sparkline = r.get("sparkline", [])
        if len(sparkline) >= 2 and sparkline[0] > 0:
            price_changes_dict[base_coin] = ((sparkline[-1] - sparkline[0]) / sparkline[0]) * 100.0

    # Use top 50 coins by OI from cg_metrics, fallback to watchlist
    if cg_metrics:
        sorted_by_oi = sorted(
            cg_metrics.values(),
            key=lambda m: m.open_interest_usd,
            reverse=True,
        )
        top_coins = [m.coin for m in sorted_by_oi[:50]]
    else:
        top_coins = [s.split("/")[0] for s in symbols if "/" in s]

    cvd_by_coin: dict = {}

    # --- source A: CoinGlass (multi-exchange, requires API key) ---
    cg_cvd: dict = {}
    try:
        from coinglass_data import fetch_cvd_batch
        cg_cvd = await asyncio.wait_for(
            fetch_cvd_batch(top_coins, price_changes=price_changes_dict),
            timeout=10.0,
        )
        logger.info("CVD CoinGlass: %d coins", len(cg_cvd))
    except asyncio.TimeoutError:
        logger.warning("CVD CoinGlass timed out — will use exchange fallback")
    except Exception as exc:
        logger.warning("CVD CoinGlass failed (%s) — will use exchange fallback", exc)

    # --- source B: exchange_derivatives_data (Binance free API) ---
    ex_cvd: dict = {}
    try:
        from exchange_derivatives_data import fetch_exchange_derivatives
        _, ex_cvd_raw, _ = await asyncio.wait_for(
            fetch_exchange_derivatives(symbols, price_changes_dict),
            timeout=12.0,
        )
        # ex_cvd_raw is keyed by coin base (e.g. "BTC"), same as cg_cvd
        ex_cvd = ex_cvd_raw or {}
        logger.info("CVD exchange (Binance/Bybit/OKX): %d coins", len(ex_cvd))
    except asyncio.TimeoutError:
        logger.warning("CVD exchange fetch timed out")
    except Exception as exc:
        logger.warning("CVD exchange fetch failed: %s", exc)

    # --- merge: CoinGlass wins per-coin, exchange fills gaps ---
    if cg_cvd or ex_cvd:
        # Start with exchange data (broader coin coverage at lower latency)
        cvd_by_coin.update(ex_cvd)
        # Override with CoinGlass where available (multi-exchange aggregation)
        cvd_by_coin.update(cg_cvd)

        # Attach CVD data to result rows
        for r in results:
            sym = r.get("symbol", "")
            base_coin = sym.split("/")[0] if "/" in sym else sym
            cvd = cvd_by_coin.get(base_coin)
            if cvd is not None:
                r["cvd_trend"] = cvd.cvd_trend
                r["cvd_divergence"] = cvd.cvd_divergence
                r["cvd_value"] = getattr(cvd, "cvd_value", 0.0)
                r["buy_sell_ratio"] = cvd.buy_sell_ratio
                r["vpin"] = getattr(cvd, "vpin", 0.0)
                r["vpin_label"] = getattr(cvd, "vpin_label", "BALANCED")
                r["cvd_source"] = "coinglass" if base_coin in cg_cvd else "exchange"

        logger.info(
            "CVD merged: %d total (%d CoinGlass, %d exchange)",
            len(cvd_by_coin), len(cg_cvd), len(ex_cvd),
        )
    else:
        logger.warning("CVD: all sources failed — marking as UNAVAILABLE")
        for r in results:
            r["cvd_trend"] = "UNAVAILABLE"

    # 8-9. Divergence + Signal synthesis + Agent layer + Priority (extracted helper)
    alt_gauge = await _synthesize_and_enrich(
        results, tf, consensus, gm,
        sentiment_data, stablecoin_data, macro_data,
        cg_metrics, cache,
    )
    logger.info(
        "Alt-season gauge for %s: score=%.1f label=%s btc_dom=%s",
        tf, alt_gauge["score"], alt_gauge["label"],
        f"{gm.btc_dominance:.1f}%" if gm else "N/A",
    )

    return results, consensus, alt_gauge, gm


# ---------------------------------------------------------------------------
# Drip scan — continuous per-symbol processing (PR2)
# ---------------------------------------------------------------------------

_drip_rotation_count: int = 0
_backtest_running_ref = None  # set by main.py to share the flag


async def _drip_one_symbol(
    symbol: str,
    scan_cache: ScanCache,
) -> int:
    """Fetch OHLCV + run engines for one symbol on both timeframes.

    Stores raw engine results (no signal) into scan_cache._results_by_sym.
    Returns number of timeframes actually processed (0, 1, or 2).
    """
    loop = asyncio.get_running_loop()
    processed = 0

    # Fetch weekly data once (shared by both TFs for heatmap/exhaustion)
    weekly = await fetch_ohlcv(symbol, "1w")

    for tf in ("4h", "1d"):
        ohlcv = await fetch_ohlcv(symbol, tf)
        if ohlcv is None:
            continue

        # Engine cache check — skip recomputation if candle unchanged
        timestamps = ohlcv.get("timestamp", [])
        last_closed_ts = int(timestamps[-2]) if len(timestamps) >= 2 else 0
        cache_key = (symbol, tf)
        cached_ts = scan_cache._engine_cache.get(cache_key)

        prev = scan_cache._results_by_sym.get(symbol, {}).get(tf)
        if cached_ts and cached_ts == last_closed_ts and prev is not None:
            # No new candle — reuse previous result, update live price
            prev["price"] = float(ohlcv["close"][-1])
            result = prev
        else:
            # New candle — run engines
            btc_data = _ohlcv_store.get("BTC/USDT", tf)
            eth_data = _ohlcv_store.get("ETH/USDT", tf)
            result = await loop.run_in_executor(
                _engine_pool,
                partial(
                    _process_symbol,
                    symbol=symbol,
                    timeframe=tf,
                    ohlcv=ohlcv,
                    weekly=weekly,
                    btc_data=btc_data,
                    eth_data=eth_data,
                ),
            )
            scan_cache._engine_cache[cache_key] = last_closed_ts

        scan_cache._results_by_sym.setdefault(symbol, {})[tf] = result
        processed += 1

    # Push to WebSocket clients (skip if nobody's listening)
    if processed > 0:
        try:
            from ws_hub import WebSocketHub
            hub = WebSocketHub.get()
            if hub.client_count > 0:
                entry = scan_cache._results_by_sym.get(symbol, {})
                await hub.push_symbol_update(
                    symbol,
                    entry.get("4h"),
                    entry.get("1d"),
                )
        except Exception:
            pass

    return processed


_DEEP_COLD_DEVIATION_PCT = -10.0   # >10% below BMSB → deep cold


def _classify_drip_tier(
    symbol: str,
    scan_cache: "ScanCache",
) -> str:
    """Classify a symbol into a drip scan tier.

    Tiers
    -----
    - **hot**:       Favorited (starred) — always scanned at full speed.
    - **active**:    Above BMSB (heat_direction == +1) — tradeable, full speed.
    - **cold**:      Below BMSB, within 10% — scanned every 20th rotation (~7 min).
    - **deep_cold**: Below BMSB by >10% — scanned every 60th rotation (~20 min).
                     These coins are deeply underwater and BMSB crossover is distant.

    On the first rotation (no cached results yet), all symbols default to
    "active" so they get an initial scan.
    """
    # Favorites always get priority regardless of BMSB
    if symbol in fav_store.get():
        return "hot"

    # Symbols with active anomalies get promoted to hot tier
    if symbol in scan_cache.anomaly_hot_symbols:
        return "hot"

    # Check cached engine results for BMSB direction
    sym_results = scan_cache._results_by_sym.get(symbol, {})
    if not sym_results:
        # No results yet — treat as active so it gets scanned on first pass
        return "active"

    # Use 1d direction if available, fallback to 4h
    for tf in ("1d", "4h"):
        r = sym_results.get(tf)
        if r is not None:
            direction = r.get("heat_direction", 0)
            if direction > 0:
                return "active"
            if direction < 0:
                deviation = r.get("deviation_pct", 0.0)
                if deviation <= _DEEP_COLD_DEVIATION_PCT:
                    return "deep_cold"
                return "cold"

    # No valid BMSB data — treat as active
    return "active"


async def run_drip_scan(
    scan_cache: Optional[ScanCache] = None,
) -> None:
    """Continuous drip scan with four-tier adaptive frequency.

    Tier behavior:
    - **hot** (favorites):      scanned every rotation (~1.0s per symbol)
    - **active** (above BMSB):  scanned every rotation (~1.0s per symbol)
    - **cold** (<10% below):    scanned every 20th rotation (~7 min)
    - **deep_cold** (>10% below): scanned every 60th rotation (~20 min)

    In a bear market with 90% of coins below BMSB, this cuts per-rotation
    API calls dramatically. Deep-cold coins (>10% below BMSB) are far from
    a crossover and barely need checking.

    Runs as a long-lived background task. Never returns.
    Stores raw engine results into scan_cache._results_by_sym.
    The synthesis pass (_run_synthesis_pass) runs separately every 60s.
    """
    global _drip_rotation_count

    if scan_cache is None:
        scan_cache = cache

    DRIP_INTERVAL = 1.0           # seconds between symbols (hot + active)
    COLD_EVERY_N = 20             # cold symbols every 20th rotation (~7 min)
    DEEP_COLD_EVERY_N = 60        # deep cold every 60th rotation (~20 min)

    # Wait briefly for initial data to be available
    await asyncio.sleep(5)

    while True:
        symbols = list(scan_cache.symbols)
        if not symbols:
            await asyncio.sleep(5)
            continue

        # Check backtest flag (accessed via scan_cache to avoid circular import)
        if getattr(scan_cache, '_backtest_running', False):
            logger.debug("Drip scan paused — backtest in progress")
            await asyncio.sleep(10)
            continue

        # --- Tier classification ---
        hot_syms: List[str] = []
        active_syms: List[str] = []
        cold_syms: List[str] = []
        deep_cold_syms: List[str] = []

        for s in symbols:
            tier = _classify_drip_tier(s, scan_cache)
            if tier == "hot":
                hot_syms.append(s)
            elif tier == "active":
                active_syms.append(s)
            elif tier == "deep_cold":
                deep_cold_syms.append(s)
            else:
                cold_syms.append(s)

        # Decide whether cold / deep-cold symbols are included this rotation
        include_cold = (_drip_rotation_count % COLD_EVERY_N == 0)
        include_deep_cold = (_drip_rotation_count % DEEP_COLD_EVERY_N == 0)

        # Build ordered list: BTC/ETH first, then hot, active, then cold tiers if due
        priority = ["BTC/USDT", "ETH/USDT"]
        ordered: List[str] = []

        # Priority symbols first (may overlap with hot/active)
        for s in priority:
            if s in symbols:
                ordered.append(s)

        # Hot symbols (excluding already-added priority)
        seen = set(ordered)
        for s in hot_syms:
            if s not in seen:
                ordered.append(s)
                seen.add(s)

        # Active symbols
        for s in active_syms:
            if s not in seen:
                ordered.append(s)
                seen.add(s)

        # Cold symbols (every 20th rotation)
        cold_this_rotation = 0
        if include_cold:
            for s in cold_syms:
                if s not in seen:
                    ordered.append(s)
                    seen.add(s)
                    cold_this_rotation += 1

        # Deep cold symbols (every 60th rotation)
        deep_cold_this_rotation = 0
        if include_deep_cold:
            for s in deep_cold_syms:
                if s not in seen:
                    ordered.append(s)
                    seen.add(s)
                    deep_cold_this_rotation += 1

        rotation_start = time.time()
        total_processed = 0

        for symbol in ordered:
            t0 = time.monotonic()

            try:
                n = await _drip_one_symbol(symbol, scan_cache)
                total_processed += n
            except Exception:
                logger.warning("Drip failed for %s", symbol, exc_info=True)

            # Pace to ~1.0s per symbol
            elapsed = time.monotonic() - t0
            if elapsed < DRIP_INTERVAL:
                await asyncio.sleep(DRIP_INTERVAL - elapsed)

        _drip_rotation_count += 1
        elapsed_total = time.time() - rotation_start

        cold_status = f"{cold_this_rotation} cold" if include_cold else "cold [skip]"
        deep_status = f"{deep_cold_this_rotation} deep" if include_deep_cold else "deep [skip]"
        # Per-rotation log demoted to DEBUG (fires every ~4 min, fills the
        # log buffer / kernel page cache). Status visible via /api/status.
        logger.debug(
            "=== Drip rotation #%d: %d symbols (%d hot, %d active, %s, %s), "
            "%d TF results in %.1fs ===",
            _drip_rotation_count,
            len(ordered),
            len(hot_syms),
            len(active_syms),
            cold_status,
            deep_status,
            total_processed,
            elapsed_total,
        )


async def _run_synthesis_pass(
    scan_cache: Optional[ScanCache] = None,
) -> None:
    """Cross-symbol synthesis: positioning, consensus, signals, confluences.

    Reads raw results from _results_by_sym (populated by drip loop),
    applies positioning from cached exchange metrics, synthesizes signals,
    and publishes to cache.results.

    Designed to run every 60s from _periodic_scan.
    """
    if scan_cache is None:
        scan_cache = cache

    # Need at least some results before we can synthesize
    if not scan_cache._results_by_sym:
        logger.info("Synthesis pass skipped — no results yet")
        return

    t0 = time.time()

    # Fetch external data (reads from 5-min caches, refreshes if stale)
    from binance_futures_data import fetch_binance_futures_metrics
    from bybit_futures_data import fetch_bybit_futures_metrics
    from coinglass_data import fetch_coinglass_metrics, fetch_macro_signals

    all_symbols = list(scan_cache._results_by_sym.keys())

    gm: Optional[GlobalMetrics] = None
    hl_metrics = {}
    binance_metrics = {}
    sentiment_data = None
    stablecoin_data = None
    cg_metrics: dict = {}
    macro_data = None

    try:
        gm, hl_metrics, binance_metrics, sentiment_data, stablecoin_data, cg_metrics, macro_data = await asyncio.gather(
            fetch_global_metrics(),
            fetch_hyperliquid_metrics(all_symbols),
            fetch_binance_futures_metrics(all_symbols),
            fetch_fear_greed(),
            fetch_stablecoin_supply(),
            fetch_coinglass_metrics(all_symbols),
            fetch_macro_signals(),
        )
    except Exception:
        logger.warning("Synthesis pass: some external data fetches failed")

    # Store exchange metrics for anomaly cross-exchange confirmation
    if hl_metrics:
        scan_cache._last_hl_metrics = hl_metrics
    if binance_metrics:
        scan_cache._last_binance_metrics = binance_metrics

    # Bybit for gaps
    covered_symbols = set()
    if binance_metrics:
        covered_symbols.update(binance_metrics.keys())
    if hl_metrics:
        covered_symbols.update(s for s, m in hl_metrics.items() if m.open_interest > 0)
    gap_symbols = [s for s in all_symbols if s not in covered_symbols]

    bybit_metrics = {}
    if gap_symbols:
        try:
            bybit_metrics = await fetch_bybit_futures_metrics(gap_symbols)
        except Exception:
            pass
    if bybit_metrics:
        scan_cache._last_bybit_metrics = bybit_metrics

    # CVD batch fetch (dual-source)
    price_changes_dict: dict = {}
    for tf in ("4h", "1d"):
        for entry in scan_cache._results_by_sym.values():
            r = entry.get(tf)
            if r:
                sym = r.get("symbol", "")
                base_coin = sym.split("/")[0] if "/" in sym else sym
                sparkline = r.get("sparkline", [])
                if len(sparkline) >= 2 and sparkline[0] > 0:
                    price_changes_dict[base_coin] = ((sparkline[-1] - sparkline[0]) / sparkline[0]) * 100.0

    # CVD from CoinGlass + exchange fallback
    cvd_by_coin: dict = {}
    try:
        from coinglass_data import fetch_cvd_batch
        cg_cvd = await asyncio.wait_for(
            fetch_cvd_batch(list(price_changes_dict.keys())[:50], price_changes=price_changes_dict),
            timeout=10.0,
        )
        cvd_by_coin.update(cg_cvd)
    except Exception:
        pass

    try:
        from exchange_derivatives_data import fetch_exchange_derivatives
        _, ex_cvd_raw, _ = await asyncio.wait_for(
            fetch_exchange_derivatives(all_symbols, price_changes_dict),
            timeout=12.0,
        )
        if ex_cvd_raw:
            # Exchange fills gaps, CoinGlass wins where both exist
            merged = dict(ex_cvd_raw)
            merged.update(cvd_by_coin)
            cvd_by_coin = merged
    except Exception:
        pass

    # Process each timeframe
    for tf in ("4h", "1d"):
        results = []
        for entry in scan_cache._results_by_sym.values():
            r = entry.get(tf)
            if r:
                results.append(r)

        if not results:
            continue

        # Attach positioning
        pos_counts = {"binance": 0, "hyperliquid": 0, "bybit": 0}
        for r in results:
            src = _attach_positioning(r, hl_metrics, binance_metrics, bybit_metrics, cg_metrics, scan_cache)
            if src:
                pos_counts[src] = pos_counts.get(src, 0) + 1

        # Attach CVD
        for r in results:
            sym = r.get("symbol", "")
            base_coin = sym.split("/")[0] if "/" in sym else sym
            cvd = cvd_by_coin.get(base_coin)
            if cvd is not None:
                r["cvd_trend"] = cvd.cvd_trend
                r["cvd_divergence"] = cvd.cvd_divergence
                r["cvd_value"] = getattr(cvd, "cvd_value", 0.0)
                r["buy_sell_ratio"] = cvd.buy_sell_ratio
                r["vpin"] = getattr(cvd, "vpin", 0.0)
                r["vpin_label"] = getattr(cvd, "vpin_label", "BALANCED")

        # Attach HyperLens smart money consensus (display-only, not in signal scoring)
        try:
            from hl_intelligence import get_all_consensus
            hl_consensus = get_all_consensus()
            hl_attached = 0
            for r in results:
                sym = r.get("symbol", "")
                base = sym.split("/")[0] if "/" in sym else sym
                sc = hl_consensus.get(base)
                if sc and sc.total_tracked > 0:
                    r["smart_money"] = {
                        "trend": sc.trend,
                        "confidence": round(sc.confidence, 2),
                        "long_count": sc.long_count,
                        "short_count": sc.short_count,
                        "net_ratio": round(sc.net_ratio, 2),
                        "mp_trend": sc.money_printer_trend,
                        "sm_trend": sc.smart_money_trend,
                    }
                    hl_attached += 1
            logger.info("HyperLens SM: %d/%d symbols attached (%d consensus available)",
                        hl_attached, len(results), len(hl_consensus))
        except Exception as exc:
            logger.warning("HyperLens consensus attachment failed: %s", exc)

        # Compute consensus
        consensus = compute_consensus(results)

        # Synthesize signals, divergences, agent, priority
        alt_gauge = await _synthesize_and_enrich(
            results, tf, consensus, gm,
            sentiment_data, stablecoin_data, macro_data,
            cg_metrics, scan_cache,
        )

        # Publish
        scan_cache.results[tf] = results
        scan_cache.consensus[tf] = consensus
        scan_cache.alt_season[tf] = alt_gauge

        # Signal logging + trade alerts
        try:
            from signal_log import SignalLog
            sig_log = SignalLog.get()
            # Capture prev signals BEFORE logging (log_signals updates them)
            prev_sigs = dict(sig_log._prev_signals.get(tf, {}))
            logged = await sig_log.log_signals(results, tf, consensus.get("consensus", "MIXED"))

            # Push trade alerts to Telegram for high-conviction entries
            if logged > 0 and tf == "4h":
                try:
                    from telegram_bot import get_telegram_bot
                    from signal_log import _classify_transition, _build_context
                    bot = get_telegram_bot()
                    transitions = []
                    for r in results:
                        sym = r.get("symbol", "")
                        sig = r.get("signal", "WAIT")
                        prev = prev_sigs.get(sym)
                        if sig == prev:
                            continue
                        tt = _classify_transition(prev, sig)
                        r_copy = dict(r)
                        r_copy["transition_type"] = tt
                        r_copy["context"] = _build_context(r, consensus.get("consensus", "MIXED"))
                        transitions.append(r_copy)
                    if transitions:
                        await bot.push_trade_alerts(transitions)
                        # Push to WebSocket clients
                        try:
                            from ws_hub import WebSocketHub
                            await WebSocketHub.get().push_signal_transition(transitions)
                        except Exception:
                            pass
                except Exception as exc:
                    logger.debug("TG trade alert push failed: %s", exc)
        except Exception:
            pass

        # --- Anomaly detection (cross-sectional z-score + time-series spike) ---
        try:
            from anomaly_detector import detect_anomalies, get_active_anomalies
            for tf_key in ("4h", "1d"):
                tf_results = scan_cache.results.get(tf_key, [])
                if tf_results:
                    new_anomalies = detect_anomalies(tf_results, scan_cache, tf_key)
                    if new_anomalies:
                        # Promote anomaly symbols to hot tier for immediate scanning
                        for a in new_anomalies:
                            scan_cache.anomaly_hot_symbols.add(a.symbol)
                        # Push critical anomalies to Telegram
                        critical = [a for a in new_anomalies if a.is_critical]
                        if critical and tf_key == "4h":
                            try:
                                from telegram_bot import get_telegram_bot
                                bot = get_telegram_bot()
                                await bot.push_anomaly_alerts(critical)
                            except Exception as exc:
                                logger.debug("TG anomaly alert failed: %s", exc)
                            # Push to WebSocket clients
                            try:
                                from ws_hub import WebSocketHub
                                await WebSocketHub.get().push_anomaly(critical)
                            except Exception:
                                pass
            scan_cache.anomalies = get_active_anomalies()
            # Prune anomaly_hot_symbols that are no longer active
            active_syms = {a["symbol"] for a in scan_cache.anomalies}
            scan_cache.anomaly_hot_symbols &= active_syms
            # Patch has_anomaly + priority onto already-published results
            # (anomaly detection runs after results are published)
            if scan_cache.anomaly_hot_symbols:
                for tf_key2 in ("4h", "1d"):
                    for r in scan_cache.results.get(tf_key2, []):
                        sym = r.get("symbol", "")
                        if sym in scan_cache.anomaly_hot_symbols:
                            r["has_anomaly"] = True
        except Exception:
            logger.debug("Anomaly detection skipped", exc_info=True)

        # --- Bridge × BTC divergence alerts (macro, single-asset) --------
        # Reuses the 10-min cached bridge snapshot — no extra API calls. Fires
        # Telegram only on confirmed EXHAUSTION transitions (cooldown-gated).
        try:
            from hl_bridge import get_bridge_flow
            from hl_bridge_alerts import check_and_alert as _bridge_check_alert
            bridge_payload = await get_bridge_flow()
            if bridge_payload:
                await _bridge_check_alert(bridge_payload.get("divergence"))
        except Exception:
            logger.debug("Bridge divergence alert skipped", exc_info=True)

        if gm is not None:
            scan_cache.global_metrics = {
                "btc_dominance": gm.btc_dominance,
                "eth_dominance": gm.eth_dominance,
                "total_market_cap": gm.total_market_cap,
                "alt_market_cap": gm.alt_market_cap,
                "btc_market_cap": gm.btc_market_cap,
                "timestamp": gm.timestamp,
            }

    # Sentiment + stablecoin cache update
    from market_data import get_cached_sentiment, get_cached_stablecoin
    s = get_cached_sentiment()
    if s:
        scan_cache.sentiment = {
            "fear_greed_value": s.fear_greed_value,
            "fear_greed_label": s.fear_greed_label,
        }
    sc = get_cached_stablecoin()
    if sc:
        scan_cache.stablecoin = {
            "usdt_market_cap": sc.usdt_market_cap,
            "usdc_market_cap": sc.usdc_market_cap,
            "total_cap": sc.total_stablecoin_cap,
            "trend": sc.trend,
            "change_7d_pct": sc.change_7d_pct,
        }

    # Confluences
    if "4h" in scan_cache.results and "1d" in scan_cache.results:
        try:
            confluences = compute_all_confluences(
                scan_cache.results["4h"],
                scan_cache.results["1d"],
            )
            scan_cache.confluence = {
                sym: {
                    "score": c.score,
                    "label": c.label,
                    "regime_aligned": c.regime_aligned,
                    "signal_aligned": c.signal_aligned,
                    "regime_4h": c.regime_4h,
                    "regime_1d": c.regime_1d,
                    "signal_4h": c.signal_4h,
                    "signal_1d": c.signal_1d,
                }
                for sym, c in confluences.items()
            }
            for tf_key in ("4h", "1d"):
                for r in scan_cache.results.get(tf_key, []):
                    sym = r.get("symbol", "")
                    if sym in scan_cache.confluence:
                        r["confluence"] = scan_cache.confluence[sym]
        except Exception:
            logger.exception("Confluence computation failed")

    # Unified cross-TF signal — regime-aware confluence
    # Rules (priority order):
    #   1. Either TF firing exit → use stronger exit (safety override)
    #   2. Both regimes bullish family (MARKUP/REACC/ACCUM):
    #      - Both entry → use weaker
    #      - One entry, other WAIT → use the entry (trust the TF that fired)
    #      - Both WAIT → WAIT
    #   3. Either regime bearish family (MARKDOWN/CAP/BLOWOFF) → WAIT
    #   4. FLAT/unknown → strict confluence (both must fire entry)
    _ENTRY_SIGS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}
    _EXIT_SIGS = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}
    _BULLISH_REGIMES = {"MARKUP", "REACC", "ACCUM"}
    _BEARISH_REGIMES = {"MARKDOWN", "CAP", "BLOWOFF"}
    # Lower rank = weaker entry; higher rank = stronger exit
    _ENTRY_RANK = {"REVIVAL_SEED": 0, "REVIVAL_SEED_CONFIRMED": 0, "ACCUMULATE": 1, "LIGHT_LONG": 2, "STRONG_LONG": 3}
    _EXIT_RANK = {"NO_LONG": 0, "TRIM": 1, "TRIM_HARD": 2, "RISK_OFF": 3}

    if "4h" in scan_cache.results and "1d" in scan_cache.results:
        r1d_map = {r.get("symbol", ""): r for r in scan_cache.results["1d"]}
        unified_count = {"entry": 0, "exit": 0, "wait": 0}

        for r4 in scan_cache.results["4h"]:
            sym = r4.get("symbol", "")
            r1 = r1d_map.get(sym)
            if not r1:
                r4["unified_signal"] = r4["signal"]
                continue

            sig4 = r4["signal"]
            sig1 = r1["signal"]
            regime4 = r4.get("regime", "")
            regime1 = r1.get("regime", "")

            # Priority 1: Safety override — either TF firing exit signal
            if sig4 in _EXIT_SIGS or sig1 in _EXIT_SIGS:
                # Use the stronger exit signal (most urgent)
                candidates = [s for s in (sig4, sig1) if s in _EXIT_SIGS]
                unified = max(candidates, key=lambda s: _EXIT_RANK.get(s, 0))
                unified_count["exit"] += 1

            # Priority 2: Both regimes in bullish family → trust any entry signal
            elif regime4 in _BULLISH_REGIMES and regime1 in _BULLISH_REGIMES:
                has4 = sig4 in _ENTRY_SIGS
                has1 = sig1 in _ENTRY_SIGS
                if has4 and has1:
                    # Both fire entry → weaker wins
                    rank4 = _ENTRY_RANK.get(sig4, 0)
                    rank1 = _ENTRY_RANK.get(sig1, 0)
                    unified = sig4 if rank4 <= rank1 else sig1
                    unified_count["entry"] += 1
                elif has4:
                    unified = sig4
                    unified_count["entry"] += 1
                elif has1:
                    unified = sig1
                    unified_count["entry"] += 1
                else:
                    # Both WAIT in bullish structure → nothing to trade yet
                    unified = "WAIT"
                    unified_count["wait"] += 1

            # Priority 3: Either regime bearish → WAIT (block entries)
            elif regime4 in _BEARISH_REGIMES or regime1 in _BEARISH_REGIMES:
                unified = "WAIT"
                unified_count["wait"] += 1

            # Priority 4: FLAT or unknown regime → strict confluence
            else:
                if sig4 in _ENTRY_SIGS and sig1 in _ENTRY_SIGS:
                    rank4 = _ENTRY_RANK.get(sig4, 0)
                    rank1 = _ENTRY_RANK.get(sig1, 0)
                    unified = sig4 if rank4 <= rank1 else sig1
                    unified_count["entry"] += 1
                else:
                    unified = "WAIT"
                    unified_count["wait"] += 1

            r4["unified_signal"] = unified
            r1["unified_signal"] = unified

        logger.info(
            "Unified signals (regime-aware): %d entry, %d exit, %d wait",
            unified_count["entry"], unified_count["exit"], unified_count["wait"],
        )

        # Track unified signal outcomes (MFE/MAE)
        try:
            from signal_outcomes import update_outcomes
            update_outcomes(scan_cache.results["4h"])
        except Exception as exc:
            logger.debug("Signal outcome tracking error: %s", exc)

    # Executor
    try:
        from executor import get_executor
        executor = get_executor()
        if executor and executor.enabled:
            exec_results = scan_cache.results.get("4h", [])
            if exec_results:
                await executor.process_scan_results(exec_results)
    except (ImportError, Exception):
        pass

    scan_cache.last_scan_time = time.time()
    elapsed = time.time() - t0
    n_syms = len(scan_cache._results_by_sym)

    # Broadcast full state to WebSocket clients
    try:
        from ws_hub import WebSocketHub
        hub = WebSocketHub.get()
        if hub.client_count > 0:
            await hub.push_synthesis(
                scan_cache.results.get("4h", []),
                scan_cache.results.get("1d", []),
                scan_cache.consensus.get("4h"),
                scan_cache.consensus.get("1d"),
                {"cache_age": 0, "timestamp": time.time(), "symbols": n_syms},
            )
    except Exception:
        pass

    logger.info(
        "=== Synthesis pass complete: %d symbols in %.1fs (rotation #%d) ===",
        n_syms, elapsed, _drip_rotation_count,
    )


# ---------------------------------------------------------------------------
# Batch scan (preserved for backtester / manual refresh)
# ---------------------------------------------------------------------------

async def run_scan(
    scan_cache: Optional[ScanCache] = None,
    timeframe: Optional[str] = None,
) -> None:
    """Run a full scan.  If *timeframe* is ``None``, scan both 4h and 1d.

    Parameters
    ----------
    scan_cache : ScanCache or None
        Cache to store results in.  Defaults to the module-level ``cache``.
    timeframe : str or None
        Single timeframe to scan (``"4h"`` or ``"1d"``).  When ``None``
        both timeframes are scanned concurrently.
    """
    if scan_cache is None:
        scan_cache = cache

    if scan_cache.is_scanning:
        logger.warning("Scan already in progress -- skipping")
        return

    scan_cache.is_scanning = True
    scan_start = time.time()
    logger.info("=== Scan started ===")

    try:
        timeframes = [timeframe] if timeframe else ["4h", "1d"]

        async def _run_one_tf(tf):
            results, consensus, alt_gauge, gm = await _scan_timeframe(
                scan_cache.symbols, tf, scan_cache=scan_cache,
            )
            scan_cache.results[tf] = results
            scan_cache.consensus[tf] = consensus
            scan_cache.alt_season[tf] = alt_gauge
            # Sync per-symbol store so rolling scan picks up full-scan data
            for r in results:
                sym = r.get("symbol", "")
                if sym:
                    scan_cache._results_by_sym.setdefault(sym, {})[tf] = r

            # Log signal transitions
            try:
                from signal_log import SignalLog
                sig_log = SignalLog.get()
                await sig_log.log_signals(
                    results, tf,
                    consensus.get("consensus", "MIXED"),
                )
            except Exception:
                logger.debug("Signal logging failed for %s (non-fatal)", tf)

            # Store latest global metrics (shared across timeframes)
            if gm is not None:
                scan_cache.global_metrics = {
                    "btc_dominance": gm.btc_dominance,
                    "eth_dominance": gm.eth_dominance,
                    "total_market_cap": gm.total_market_cap,
                    "alt_market_cap": gm.alt_market_cap,
                    "btc_market_cap": gm.btc_market_cap,
                    "timestamp": gm.timestamp,
                }

        # Run timeframes sequentially to avoid double-hammering HL
        for tf in timeframes:
            try:
                await _run_one_tf(tf)
            except Exception:
                logger.exception("Scan failed for timeframe %s", tf)

        # Store sentiment & stablecoin data from latest fetch
        from market_data import get_cached_sentiment, get_cached_stablecoin
        s = get_cached_sentiment()
        if s:
            scan_cache.sentiment = {
                "fear_greed_value": s.fear_greed_value,
                "fear_greed_label": s.fear_greed_label,
            }
        sc = get_cached_stablecoin()
        if sc:
            scan_cache.stablecoin = {
                "usdt_market_cap": sc.usdt_market_cap,
                "usdc_market_cap": sc.usdc_market_cap,
                "total_cap": sc.total_stablecoin_cap,
                "trend": sc.trend,
                "change_7d_pct": sc.change_7d_pct,
            }

        # Compute multi-TF confluence (requires both timeframes)
        if "4h" in scan_cache.results and "1d" in scan_cache.results:
            try:
                confluences = compute_all_confluences(
                    scan_cache.results["4h"],
                    scan_cache.results["1d"],
                )
                # Store and inject into results
                scan_cache.confluence = {
                    sym: {
                        "score": c.score,
                        "label": c.label,
                        "regime_aligned": c.regime_aligned,
                        "signal_aligned": c.signal_aligned,
                        "regime_4h": c.regime_4h,
                        "regime_1d": c.regime_1d,
                        "signal_4h": c.signal_4h,
                        "signal_1d": c.signal_1d,
                    }
                    for sym, c in confluences.items()
                }
                # Inject confluence into each result for API response
                for tf_key in ("4h", "1d"):
                    for r in scan_cache.results.get(tf_key, []):
                        sym = r.get("symbol", "")
                        if sym in scan_cache.confluence:
                            r["confluence"] = scan_cache.confluence[sym]
            except Exception:
                logger.exception("Confluence computation failed")

        # 11. Execute signals via Kraken (if executor is enabled)
        try:
            from executor import get_executor
            executor = get_executor()
            if executor and executor.enabled:
                # Use 4h results as the primary signal source
                exec_results = scan_cache.results.get("4h", [])
                if exec_results:
                    exec_summary = await executor.process_scan_results(exec_results)
                    actions = exec_summary.get("actions", [])
                    if actions:
                        logger.info("Executor: %d actions — %s", len(actions), actions)
        except ImportError:
            pass  # executor module not available
        except Exception:
            logger.exception("Executor processing failed (scan unaffected)")

        scan_cache.last_scan_time = time.time()
        elapsed = time.time() - scan_start
        logger.info("=== Scan completed in %.1fs ===", elapsed)
        _malloc_trim()

    finally:
        scan_cache.is_scanning = False


async def run_rolling_scan(
    scan_cache: Optional[ScanCache] = None,
) -> None:
    """Rolling scan: tier-1 every cycle + rotating chunk of tier-2.

    Instead of scanning all ~229 symbols every 5 min, this scans
    ~65 symbols every 60s.  Tier-1 (top 25 majors) is refreshed
    every cycle; tier-2 symbols rotate through in chunks of 40,
    completing a full rotation every ~5 cycles.

    Results are merged incrementally into ``scan_cache`` so the
    API always has data for every symbol that has been scanned at
    least once.
    """
    if scan_cache is None:
        scan_cache = cache

    if scan_cache.is_scanning:
        logger.warning("Rolling scan skipped -- scan already in progress")
        return

    scan_cache.is_scanning = True
    scan_start = time.time()

    try:
        # ── Build this cycle's symbol batch ──
        all_symbols = scan_cache.symbols
        tier1 = [s for s in TIER1_SYMBOLS if s in all_symbols]
        tier2 = [s for s in all_symbols if s not in TIER1_SYMBOLS]

        # Rotate through tier-2
        offset = scan_cache._rotation_offset
        chunk = tier2[offset : offset + TIER2_CHUNK_SIZE]
        # Wrap around if we've reached the end
        if len(chunk) < TIER2_CHUNK_SIZE and tier2:
            remaining = TIER2_CHUNK_SIZE - len(chunk)
            chunk += tier2[:remaining]
        # Advance offset
        next_offset = offset + TIER2_CHUNK_SIZE
        if next_offset >= len(tier2):
            next_offset = 0
        scan_cache._rotation_offset = next_offset

        batch = list(dict.fromkeys(tier1 + chunk))  # deduplicate, preserve order

        logger.info(
            "=== Rolling scan: %d symbols (T1=%d, T2=%d, offset=%d→%d) ===",
            len(batch), len(tier1), len(chunk), offset, next_offset,
        )

        # ── Scan both timeframes sequentially ──
        for tf in ("4h", "1d"):
            try:
                results, consensus, alt_gauge, gm = await _scan_timeframe(batch, tf, scan_cache=scan_cache)

                # Merge results into per-symbol store
                for r in results:
                    sym = r.get("symbol", "")
                    if sym:
                        scan_cache._results_by_sym.setdefault(sym, {})[tf] = r

                # Rebuild full result list from per-symbol store
                full_results = [
                    entry[tf]
                    for entry in scan_cache._results_by_sym.values()
                    if tf in entry
                ]
                scan_cache.results[tf] = full_results

                # Recompute consensus from ALL symbols, not just this batch
                scan_cache.consensus[tf] = compute_consensus(full_results)
                scan_cache.alt_season[tf] = alt_gauge

                # Log signal transitions
                try:
                    from signal_log import SignalLog
                    sig_log = SignalLog.get()
                    await sig_log.log_signals(
                        results, tf,
                        consensus.get("consensus", "MIXED"),
                    )
                except Exception:
                    logger.debug("Signal logging failed for %s (non-fatal)", tf)

                if gm is not None:
                    scan_cache.global_metrics = {
                        "btc_dominance": gm.btc_dominance,
                        "eth_dominance": gm.eth_dominance,
                        "total_market_cap": gm.total_market_cap,
                        "alt_market_cap": gm.alt_market_cap,
                        "btc_market_cap": gm.btc_market_cap,
                        "timestamp": gm.timestamp,
                    }
            except Exception:
                logger.exception("Rolling scan failed for timeframe %s", tf)

        # ── Sentiment & stablecoin ──
        from market_data import get_cached_sentiment, get_cached_stablecoin
        s = get_cached_sentiment()
        if s:
            scan_cache.sentiment = {
                "fear_greed_value": s.fear_greed_value,
                "fear_greed_label": s.fear_greed_label,
            }
        sc = get_cached_stablecoin()
        if sc:
            scan_cache.stablecoin = {
                "usdt_market_cap": sc.usdt_market_cap,
                "usdc_market_cap": sc.usdc_market_cap,
                "total_cap": sc.total_stablecoin_cap,
                "trend": sc.trend,
                "change_7d_pct": sc.change_7d_pct,
            }

        # ── Recompute confluence across ALL symbols (not just this batch) ──
        if "4h" in scan_cache.results and "1d" in scan_cache.results:
            try:
                confluences = compute_all_confluences(
                    scan_cache.results["4h"],
                    scan_cache.results["1d"],
                )
                scan_cache.confluence = {
                    sym: {
                        "score": c.score,
                        "label": c.label,
                        "regime_aligned": c.regime_aligned,
                        "signal_aligned": c.signal_aligned,
                        "regime_4h": c.regime_4h,
                        "regime_1d": c.regime_1d,
                        "signal_4h": c.signal_4h,
                        "signal_1d": c.signal_1d,
                    }
                    for sym, c in confluences.items()
                }
                for tf_key in ("4h", "1d"):
                    for r in scan_cache.results.get(tf_key, []):
                        sym = r.get("symbol", "")
                        if sym in scan_cache.confluence:
                            r["confluence"] = scan_cache.confluence[sym]
            except Exception:
                logger.exception("Confluence computation failed")

        # ── Executor ──
        try:
            from executor import get_executor
            executor = get_executor()
            if executor and executor.enabled:
                exec_results = scan_cache.results.get("4h", [])
                if exec_results:
                    exec_summary = await executor.process_scan_results(exec_results)
                    actions = exec_summary.get("actions", [])
                    if actions:
                        logger.info("Executor: %d actions — %s", len(actions), actions)
        except ImportError:
            pass
        except Exception:
            logger.exception("Executor processing failed (scan unaffected)")

        scan_cache.last_scan_time = time.time()
        elapsed = time.time() - scan_start
        logger.info(
            "=== Rolling scan completed in %.1fs (%d symbols) ===",
            elapsed, len(batch),
        )
        _malloc_trim()

    finally:
        scan_cache.is_scanning = False


async def run_tradfi_scan(
    scan_cache: Optional[ScanCache] = None,
) -> None:
    """Scan TradFi/HIP-3 assets (commodities, indices, equities).

    Uses the same RCCE + Heatmap + Exhaustion engines as crypto, but:
    - Data comes from Hyperliquid HIP-3 candleSnapshot API only
    - No BTC divergence (irrelevant for commodities/equities)
    - No crypto consensus (separate market dynamics)
    - Signals synthesized with neutral consensus context
    """
    if scan_cache is None:
        scan_cache = cache

    logger.info("=== TradFi scan started (%d symbols) ===", len(TRADFI_SYMBOL_LIST))
    t0 = time.time()
    loop = asyncio.get_running_loop()

    # Fetch xyz DEX metrics (funding, OI, volume) — shared across both TFs
    xyz_metrics: dict = {}
    try:
        from hyperliquid_data import fetch_hyperliquid_dex_metrics
        xyz_metrics = await fetch_hyperliquid_dex_metrics("xyz")
        logger.info("TradFi: fetched xyz DEX metrics for %d instruments", len(xyz_metrics))
    except Exception as exc:
        logger.warning("TradFi: xyz DEX metrics fetch failed: %s", exc)

    async def _tradfi_one_tf(tf):
        # 1. Fetch OHLCV — HIP-3 native candles (primary), yfinance fallback
        ohlcv_batch = await fetch_batch_hip3(tf)
        fetched = sum(1 for v in ohlcv_batch.values() if v is not None)
        logger.info("TradFi: fetched %d/%d for %s (HIP-3)", fetched, len(TRADFI_SYMBOL_LIST), tf)

        # Fill gaps with yfinance for symbols that HIP-3 didn't return
        if fetched < len(TRADFI_SYMBOL_LIST):
            try:
                yf_batch = await fetch_batch_yfinance(tf)
                yf_filled = 0
                for sym, data in yf_batch.items():
                    if data is not None and ohlcv_batch.get(sym) is None:
                        ohlcv_batch[sym] = data
                        yf_filled += 1
                if yf_filled:
                    fetched += yf_filled
                    logger.info("TradFi: yfinance fallback filled %d gaps for %s", yf_filled, tf)
            except Exception:
                pass

        if fetched == 0:
            logger.warning("TradFi: no data for %s — skipping", tf)
            return

        # 2. Fetch weekly data for heatmap + exhaustion
        weekly_batch = await fetch_batch_hip3("1w")
        # Fill weekly gaps with yfinance
        try:
            yf_weekly = await fetch_batch_yfinance("1w")
            for sym, data in yf_weekly.items():
                if data is not None and weekly_batch.get(sym) is None:
                    weekly_batch[sym] = data
        except Exception:
            pass

        # 3. Process each symbol through engines (parallel via thread pool)
        sym_info_map = {}
        engine_futures = []
        for sym_info in TRADFI_SYMBOLS:
            symbol = sym_info["symbol"]
            ohlcv = ohlcv_batch.get(symbol)
            if ohlcv is None:
                continue
            weekly = weekly_batch.get(symbol)
            sym_info_map[symbol] = sym_info
            engine_futures.append(
                loop.run_in_executor(
                    _engine_pool,
                    partial(
                        _process_symbol,
                        symbol=symbol,
                        timeframe=tf,
                        ohlcv=ohlcv,
                        weekly=weekly,
                        btc_data=None,
                        eth_data=None,
                    ),
                )
            )

        settled = await asyncio.gather(*engine_futures, return_exceptions=True)
        results: List[dict] = []
        for outcome in settled:
            if isinstance(outcome, Exception):
                logger.exception("TradFi engine error: %s", outcome)
                continue
            sym_info = sym_info_map[outcome["symbol"]]
            outcome["asset_class"] = sym_info["category"]
            outcome["tradfi_name"] = sym_info["name"]
            outcome["tradfi_coin"] = sym_info["coin"]
            results.append(outcome)

        if not results:
            return

        # 4. Attach positioning from xyz DEX metrics (OI, funding, volume)
        for r in results:
            coin = r.get("tradfi_coin", r.get("symbol", "").split("/")[0])
            xyz_key = f"{coin}/USD"
            xyz = xyz_metrics.get(xyz_key)
            if xyz and xyz.open_interest > 0:
                sparkline = r.get("sparkline", [])
                price_change_pct = 0.0
                if len(sparkline) >= 2 and sparkline[0] > 0:
                    price_change_pct = ((sparkline[-1] - sparkline[0]) / sparkline[0]) * 100.0

                prev_oi = scan_cache.prev_oi.get(r["symbol"])
                if prev_oi is None:
                    scan_cache.prev_oi[r["symbol"]] = xyz.open_interest
                    prev_oi = xyz.open_interest

                pos = compute_positioning(
                    funding_rate=xyz.funding_rate,
                    open_interest=xyz.open_interest,
                    price_change_pct=price_change_pct,
                    prev_oi=prev_oi,
                    predicted_funding=xyz.predicted_funding,
                    mark_price=xyz.mark_price,
                    oracle_price=xyz.oracle_price,
                    volume_24h=xyz.volume_24h,
                )
                r["positioning"] = {
                    "funding_regime": pos.funding_regime,
                    "funding_rate": pos.funding_rate,
                    "oi_trend": pos.oi_trend,
                    "oi_value": pos.oi_value,
                    "oi_change_pct": pos.oi_change_pct,
                    "leverage_risk": pos.leverage_risk,
                    "predicted_funding": pos.predicted_funding,
                    "mark_price": pos.mark_price,
                    "volume_24h": pos.volume_24h,
                    "source": "hyperliquid_xyz",
                    "source_map": {"funding": "xyz_dex", "oi": "xyz_dex", "volume": "xyz_dex"},
                    "liquidation_24h_usd": 0.0, "long_liq_usd": 0.0, "short_liq_usd": 0.0,
                    "liquidation_4h_usd": 0.0, "liquidation_1h_usd": 0.0,
                    "long_short_ratio": 1.0, "top_trader_lsr": 1.0,
                    "oi_market_cap_ratio": 0.0, "spot_volume_usd": 0.0,
                    "spot_futures_ratio": 0.0, "spot_dominance": "NEUTRAL",
                }
                scan_cache.prev_oi[r["symbol"]] = xyz.open_interest

        pos_count = sum(1 for r in results if r.get("positioning"))
        logger.info("TradFi: %d/%d with xyz positioning", pos_count, len(results))

        # 5. Compute TradFi-specific consensus
        tradfi_consensus = compute_consensus(results)

        # 6. Synthesize signals in parallel via thread pool
        def _tradfi_synth_one(r):
            heat_direction = r.get("heat_direction", 0)
            deviation_pct = r.get("deviation_pct", 0.0)
            heat_val = r.get("heat", 0)
            bmsb_valid = not (heat_val == 0 and heat_direction == 0 and deviation_pct == 0.0)
            macro_blocked = heat_direction < 0 if bmsb_valid else True
            return synthesize_signal(
                result=r,
                consensus=tradfi_consensus,
                global_metrics=None,
                positioning=r.get("positioning"),
                sentiment=None,
                stablecoin=None,
                macro_blocked=macro_blocked,
                prev_heat=r.get("heat", 0),
                bmsb_valid=bmsb_valid,
            )

        synth_futures = [
            loop.run_in_executor(_engine_pool, _tradfi_synth_one, r)
            for r in results
        ]
        synth_results = await asyncio.gather(*synth_futures, return_exceptions=True)
        for r, synth in zip(results, synth_results):
            if isinstance(synth, Exception):
                logger.debug("TradFi signal synthesis failed for %s: %s", r.get("symbol"), synth)
            else:
                r["signal"] = synth.signal
                r["signal_reason"] = synth.reason
                r["signal_warnings"] = synth.warnings
                r["signal_confidence"] = (
                    round(synth.conditions_met / synth.conditions_total * 100)
                    if synth.conditions_total > 0 else 0
                )
                r["conditions_met"] = synth.conditions_met
                r["conditions_total"] = synth.conditions_total
                r["conditions_detail"] = synth.conditions_detail
                r["effective_conditions"] = synth.effective_conditions
                from signal_synthesizer import compute_signal_score
                r["signal_score"] = compute_signal_score(
                    synth.signal, synth.effective_conditions, synth.conditions_total,
                )

        # 6. Compute priority scores
        for r in results:
            r["priority_score"] = _compute_priority(r)

        results.sort(key=lambda r: r.get("priority_score", 0), reverse=True)
        scan_cache.tradfi_results[tf] = results
        logger.info("TradFi scan %s: %d results in %.1fs", tf, len(results), time.time() - t0)

        # Log signal transitions for TradFi
        try:
            from signal_log import SignalLog
            sig_log = SignalLog.get()
            await sig_log.log_signals(
                results, f"tradfi_{tf}",
                tradfi_consensus.get("consensus", "MIXED"),
            )
        except Exception:
            logger.debug("TradFi signal logging failed (non-fatal)")

    # Run both timeframes concurrently
    tf_results = await asyncio.gather(
        _tradfi_one_tf("4h"), _tradfi_one_tf("1d"),
        return_exceptions=True,
    )
    for tf, outcome in zip(("4h", "1d"), tf_results):
        if isinstance(outcome, Exception):
            logger.exception("TradFi scan failed for %s: %s", tf, outcome)

    # Compute TradFi multi-TF confluence
    if "4h" in scan_cache.tradfi_results and "1d" in scan_cache.tradfi_results:
        try:
            confluences = compute_all_confluences(
                scan_cache.tradfi_results["4h"],
                scan_cache.tradfi_results["1d"],
            )
            for tf_key in ("4h", "1d"):
                for r in scan_cache.tradfi_results.get(tf_key, []):
                    sym = r.get("symbol", "")
                    if sym in confluences:
                        c = confluences[sym]
                        r["confluence"] = {
                            "score": c.score,
                            "label": c.label,
                            "regime_aligned": c.regime_aligned,
                            "signal_aligned": c.signal_aligned,
                            "regime_4h": c.regime_4h,
                            "regime_1d": c.regime_1d,
                            "signal_4h": c.signal_4h,
                            "signal_1d": c.signal_1d,
                        }
        except Exception:
            logger.debug("TradFi confluence computation failed (non-fatal)")

    elapsed = time.time() - t0
    logger.info("=== TradFi scan completed in %.1fs ===", elapsed)


def run_scan_sync(
    scan_cache: Optional[ScanCache] = None,
    timeframe: Optional[str] = None,
) -> None:
    """Synchronous wrapper around :func:`run_scan`.

    Creates a new event loop if none is running (safe to call from a
    plain thread or a BackgroundScheduler job).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # We are inside an existing event loop -- schedule as a task
        asyncio.ensure_future(run_scan(scan_cache, timeframe))
    else:
        asyncio.run(run_scan(scan_cache, timeframe))


# ---------------------------------------------------------------------------
# Public helpers (imported by main.py)
# ---------------------------------------------------------------------------

def get_all_results() -> dict:
    """Return all cached results keyed by timeframe."""
    return {
        "results": cache.results,
        "consensus": cache.consensus,
        "alt_season": cache.alt_season,
        "global_metrics": cache.global_metrics,
        "sentiment": cache.sentiment,
        "stablecoin": cache.stablecoin,
        "confluence": cache.confluence,
    }


def get_scan_status() -> dict:
    """Return lightweight scan metadata."""
    # Compute tier breakdown
    hot = active = cold = deep_cold = 0
    for s in cache.symbols:
        tier = _classify_drip_tier(s, cache)
        if tier == "hot":
            hot += 1
        elif tier == "active":
            active += 1
        elif tier == "deep_cold":
            deep_cold += 1
        else:
            cold += 1
    return {
        "is_scanning": cache.is_scanning,
        "last_scan_time": cache.last_scan_time,
        "symbols_count": len(cache.symbols),
        "cache_age_seconds": cache.get_cache_age(),
        "mode": "drip",
        "drip_rotation": _drip_rotation_count,
        "symbols_scanned": len(cache._results_by_sym),
        "drip_tiers": {"hot": hot, "active": active, "cold": cold, "deep_cold": deep_cold},
    }
