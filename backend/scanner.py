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
import logging
import time
from typing import Dict, List, Optional

from data_fetcher import fetch_batch, fetch_ohlcv, DEFAULT_SYMBOLS, DataCache
from engines.rcce_engine import compute_rcce
from engines.heatmap_engine import compute_heatmap
from engines.exhaustion_engine import compute_exhaustion
from engines.positioning_engine import compute_positioning
from signal_synthesizer import synthesize_signal
from market_data import (
    fetch_global_metrics, GlobalMetrics,
    fetch_fear_greed, fetch_stablecoin_supply,
)
from binance_futures_data import fetch_binance_futures_metrics
from hyperliquid_data import fetch_hyperliquid_metrics
from confluence import compute_all_confluences

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

def _compute_priority(r: dict) -> float:
    """Compute a composite priority score (0-100) for ranking symbols.

    Factors (total = 100 pts):
        1. Conditions met:     0-25 pts  (% of conditions satisfied)
        2. BMSB proximity:     0-25 pts  (how close to / above BMSB mid)
        3. Floor confirmed:    0 or 15   (binary bonus)
        4. Momentum:           0-15 pts  (normalised -10% .. +10%)
        5. Heat headroom:      0-10 pts  (inverted — low heat = more room)
        6. Volume/absorption:  0-10 pts  (rel_vol + absorption bonus)
    """
    score = 0.0

    # 1. Conditions met: 0-25 pts
    cond = r.get("conditions_met", 0)
    cond_total = max(r.get("conditions_total", 10), 1)
    score += (cond / cond_total) * 25

    # 2. BMSB proximity: 0-25 pts
    dev = r.get("deviation_pct", -50)
    dev_clamped = max(-50.0, min(50.0, dev))
    score += ((dev_clamped + 50) / 100) * 25

    # 3. Floor confirmed: 0 or 15 pts
    if r.get("floor_confirmed", False):
        score += 15

    # 4. Momentum: 0-15 pts
    mom = r.get("momentum", -10)
    mom_clamped = max(-10.0, min(10.0, mom))
    score += ((mom_clamped + 10) / 20) * 15

    # 5. Heat inverted: 0-10 pts (low heat = more upside room)
    heat = r.get("heat", 50)
    score += ((100 - min(heat, 100)) / 100) * 10

    # 6. Volume / absorption: 0-10 pts
    rel_vol = min(r.get("rel_vol", 1.0), 5.0)
    score += (rel_vol / 5.0) * 5
    if r.get("is_absorption", False):
        score += 5

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
        "confidence": round(rcce.get("confidence", 0), 1),
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
    }
    return result


async def _scan_timeframe(
    symbols: List[str],
    tf: str,
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

    # 4. Process each symbol (engines only — no final signal yet)
    results: List[dict] = []
    for symbol in symbols:
        ohlcv = ohlcv_batch.get(symbol)
        if ohlcv is None:
            logger.debug("Skipping %s -- no OHLCV data", symbol)
            continue

        weekly = weekly_batch.get(symbol)

        try:
            result = _process_symbol(
                symbol=symbol,
                timeframe=tf,
                ohlcv=ohlcv,
                weekly=weekly,
                btc_data=btc_data,
                eth_data=eth_data,
            )
            results.append(result)
        except Exception:
            logger.exception("Failed to process %s on %s", symbol, tf)

    logger.info(
        "Processed %d symbols for %s (%.1fs total)",
        len(results), tf, time.time() - t0,
    )

    # 5. Compute consensus (BEFORE signal synthesis — signals need this)
    consensus = compute_consensus(results)
    logger.info(
        "Consensus for %s: %s (strength=%.1f%%)",
        tf, consensus["consensus"], consensus["strength"],
    )

    # 6. Fetch external data in parallel
    #    Binance Futures (primary positioning) + Hyperliquid (fallback) + globals
    gm: Optional[GlobalMetrics] = None
    bf_metrics = {}
    hl_metrics = {}
    sentiment_data = None
    stablecoin_data = None

    try:
        gm, bf_metrics, hl_metrics, sentiment_data, stablecoin_data = await asyncio.gather(
            fetch_global_metrics(),
            fetch_binance_futures_metrics(symbols),
            fetch_hyperliquid_metrics(symbols),
            fetch_fear_greed(),
            fetch_stablecoin_supply(),
        )
    except Exception:
        logger.warning("Some external data fetches failed — proceeding with available data")
        # Individual failures are handled by each fetcher's fallback logic

    if gm:
        logger.info(
            "Global metrics: BTC.D=%.1f%% ALT MCap=$%.0fB",
            gm.btc_dominance, gm.alt_market_cap / 1e9,
        )
    if bf_metrics:
        logger.info("Binance Futures: %d perps with positioning data", len(bf_metrics))
    if hl_metrics:
        logger.info("Hyperliquid: %d perps (fallback positioning)", len(hl_metrics))
    if sentiment_data:
        logger.info("Fear & Greed: %d (%s)", sentiment_data.fear_greed_value, sentiment_data.fear_greed_label)
    if stablecoin_data:
        logger.info("Stablecoin: $%.1fB (%s)", stablecoin_data.total_stablecoin_cap / 1e9, stablecoin_data.trend)

    # 7. Compute positioning per symbol
    #    Primary source: Binance Futures (largest exchange)
    #    Fallback:       Hyperliquid (on-chain, wider alt coverage)
    binance_pos_count = 0
    hl_pos_count = 0

    for r in results:
        symbol = r["symbol"]
        bf = bf_metrics.get(symbol) if bf_metrics else None
        hl = hl_metrics.get(symbol) if hl_metrics else None

        # Pick primary source: Binance > Hyperliquid
        funding_rate = 0.0
        open_interest = 0.0
        predicted_funding = 0.0
        mark_price = 0.0
        oracle_price = 0.0
        volume_24h = 0.0
        source = ""

        if bf is not None and bf.open_interest > 0:
            funding_rate = bf.funding_rate        # already normalised to hourly
            open_interest = bf.open_interest       # already in USD
            mark_price = bf.mark_price
            oracle_price = bf.index_price
            source = "binance"
            binance_pos_count += 1
        elif hl is not None:
            funding_rate = hl.funding_rate
            open_interest = hl.open_interest
            predicted_funding = hl.predicted_funding
            mark_price = hl.mark_price
            oracle_price = hl.oracle_price
            volume_24h = hl.volume_24h
            source = "hyperliquid"
            hl_pos_count += 1

        if source:
            # Get price change from sparkline data
            sparkline = r.get("sparkline", [])
            price_change_pct = 0.0
            if len(sparkline) >= 2 and sparkline[0] > 0:
                price_change_pct = ((sparkline[-1] - sparkline[0]) / sparkline[0]) * 100.0

            # Cold-start fix: if no prev_oi exists, seed it and report STABLE
            # instead of UNKNOWN.  Real OI trend computes from the second scan.
            prev_oi = cache.prev_oi.get(symbol)
            if prev_oi is None and open_interest > 0:
                # First time seeing this symbol — seed and assume stable
                cache.prev_oi[symbol] = open_interest
                prev_oi = open_interest  # OI change will be 0% → STABLE

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
                "source": source,
            }
            # Store OI for next scan's trend calculation
            cache.prev_oi[symbol] = open_interest

    logger.info(
        "Positioning: %d from Binance, %d from Hyperliquid",
        binance_pos_count, hl_pos_count,
    )

    # 8. Detect divergences
    btc_regime = next(
        (r["regime"] for r in results if r["symbol"] == "BTC/USDT"),
        "FLAT",
    )
    for r in results:
        r["divergence"] = detect_divergence(r["regime"], btc_regime)

    divergence_count = sum(1 for r in results if r["divergence"] is not None)
    if divergence_count:
        logger.info("Detected %d divergences on %s", divergence_count, tf)

    # 9. Synthesize final signals (cross-engine Decision Matrix + positioning + sentiment)
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

    for r in results:
        try:
            # Compute macro_blocked from BMSB direction
            heat_direction = r.get("heat_direction", 0)
            deviation_pct = r.get("deviation_pct", 0.0)
            heat_val = r.get("heat", 0)

            # No valid BMSB data (heatmap returned defaults) → block entries
            bmsb_valid = not (heat_val == 0 and heat_direction == 0 and deviation_pct == 0.0)
            if not bmsb_valid:
                macro_blocked = True  # no BMSB = no signal = WAIT
            else:
                macro_blocked = heat_direction < 0  # price below weekly BMSB mid

            # Get prev_heat from cache (for rally stall detection in LIGHT_SHORT)
            symbol = r.get("symbol", "")
            prev_heat = cache.prev_heat.get(symbol, 0) if hasattr(cache, 'prev_heat') else 0

            synth = synthesize_signal(
                r, consensus, gm_dict,
                positioning=r.get("positioning"),
                sentiment=sentiment_dict,
                stablecoin=stablecoin_dict,
                macro_blocked=macro_blocked,
                prev_heat=prev_heat,
                bmsb_valid=bmsb_valid,
            )
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

            # Store current heat for next scan
            if not hasattr(cache, 'prev_heat'):
                cache.prev_heat = {}
            cache.prev_heat[symbol] = r.get("heat", 0)
        except Exception:
            logger.exception("Signal synthesis failed for %s", r.get("symbol"))
            r["signal"] = r.get("raw_signal", "WAIT")
            r["signal_reason"] = "synthesis error — using raw signal"
            r["signal_warnings"] = ["Signal synthesizer encountered an error"]
            r["conditions_detail"] = []
            r["conditions_met"] = 0
            r["conditions_total"] = 10

    # Compute priority score for each result
    for r in results:
        r["priority_score"] = _compute_priority(r)

    signal_summary = {}
    for r in results:
        sig = r["signal"]
        signal_summary[sig] = signal_summary.get(sig, 0) + 1
    logger.info("Signal distribution for %s: %s", tf, signal_summary)

    # 9. Alt-season gauge (using global metrics when available)
    alt_gauge = compute_alt_season_gauge(results, gm)
    logger.info(
        "Alt-season gauge for %s: score=%.1f label=%s btc_dom=%s",
        tf, alt_gauge["score"], alt_gauge["label"],
        f"{gm.btc_dominance:.1f}%" if gm else "N/A",
    )

    return results, consensus, alt_gauge, gm


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
        both timeframes are scanned sequentially.
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

        for tf in timeframes:
            try:
                results, consensus, alt_gauge, gm = await _scan_timeframe(
                    scan_cache.symbols, tf,
                )
                scan_cache.results[tf] = results
                scan_cache.consensus[tf] = consensus
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

    finally:
        scan_cache.is_scanning = False


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
    return {
        "is_scanning": cache.is_scanning,
        "last_scan_time": cache.last_scan_time,
        "symbols_count": len(cache.symbols),
        "cache_age_seconds": cache.get_cache_age(),
    }
