"""
scanner.py
~~~~~~~~~~
Scan orchestrator -- coordinates RCCE, Heatmap, and Exhaustion engines
across 60+ crypto symbols on multiple timeframes (4h, 1d).

Responsibilities
----------------
1. Run scans across all watchlist symbols x timeframes
2. Coordinate three independent engines per symbol
3. Compute market-wide consensus (Module 11)
4. Detect BTC-relative divergences (Module 12)
5. Calculate alt-season gauge
6. Cache results in memory for the API layer

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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Asset classification
# ---------------------------------------------------------------------------

MEME_TOKENS = {"DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "MEME"}


def classify_asset(symbol: str) -> str:
    """Classify a trading pair into BTC / ETH / MEME / ALT."""
    sym = symbol.upper()
    if "BTC" in sym:
        return "BTC"
    if "ETH" in sym:
        return "ETH"
    base = sym.split("/")[0]
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

    # Decision rules (evaluated in priority order)
    if markup_n / total > 0.6:
        consensus = "RISK-ON"
        strength = (markup_n / total) * 100.0
    elif blowoff_n / total > 0.5:
        consensus = "EUPHORIA"
        strength = (blowoff_n / total) * 100.0
    elif markdown_n / total > 0.5:
        consensus = "RISK-OFF"
        strength = (markdown_n / total) * 100.0
    elif accum_n / total > 0.5:
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

    if sym in ("MARKUP", "REACC") and btc in ("MARKDOWN", "BLOWOFF"):
        return "BEAR-DIV"
    if sym in ("MARKDOWN", "CAP") and btc == "MARKUP":
        return "BULL-DIV"
    return None


# ---------------------------------------------------------------------------
# Alt-season gauge
# ---------------------------------------------------------------------------

def compute_alt_season_gauge(results: List[dict]) -> dict:
    """Calculate an alt-season gauge from scan results.

    Methodology:
      - Count ALT + MEME symbols in MARKUP or REACC regimes.
      - Compare against BTC regime strength.
      - Score 0-100 where >75 signals alt-season territory.

    Returns
    -------
    dict
        ``score``   -- 0-100 alt-season score
        ``label``   -- BTC_SEASON / ALT_WARMING / ALT_SEASON / MIXED
        ``alts_up`` -- count of alts in bullish regimes
        ``total_alts`` -- count of alt symbols in scan
    """
    alts = [r for r in results if r.get("asset_class") in ("ALT", "MEME")]
    total_alts = len(alts)
    if total_alts == 0:
        return {"score": 0.0, "label": "MIXED", "alts_up": 0, "total_alts": 0}

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

    # Score: if BTC is bullish but alts are lagging, reduce score
    if btc_bullish and alt_pct < 0.3:
        score = alt_pct * 100.0 * 0.5  # damped
    else:
        score = alt_pct * 100.0

    score = min(100.0, max(0.0, score))

    if score >= 75:
        label = "ALT_SEASON"
    elif score >= 40:
        label = "ALT_WARMING"
    elif btc_bullish and score < 25:
        label = "BTC_SEASON"
    else:
        label = "MIXED"

    return {
        "score": round(score, 1),
        "label": label,
        "alts_up": alts_up,
        "total_alts": total_alts,
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
    """
    # --- RCCE engine -------------------------------------------------------
    rcce: dict = {}
    try:
        rcce = compute_rcce(ohlcv, btc_data, eth_data)
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
        "signal": rcce.get("signal", "WAIT"),
        "zscore": round(rcce.get("z_score", 0), 3),
        "energy": round(rcce.get("energy", 0), 3),
        "vol_state": rcce.get("vol_state", "MID"),
        "momentum": round(rcce.get("momentum", 0), 2),
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
        "effort": round(exhaustion.get("effort", 0), 3),
        "rel_vol": round(exhaustion.get("rel_vol", 0), 2),
    }
    return result


async def _scan_timeframe(
    symbols: List[str],
    tf: str,
) -> tuple[List[dict], dict, dict]:
    """Run a full scan for one timeframe and return (results, consensus, alt_gauge).

    Steps
    -----
    1. Batch-fetch OHLCV data for the requested timeframe.
    2. Batch-fetch weekly data (required by heatmap + exhaustion engines).
    3. Extract BTC and ETH reference data for beta calculations.
    4. Process each symbol through all three engines.
    5. Compute consensus across results.
    6. Detect divergences and apply signal overrides.
    7. Compute alt-season gauge.
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

    # 4. Process each symbol
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

    # 5. Compute consensus
    consensus = compute_consensus(results)
    logger.info(
        "Consensus for %s: %s (strength=%.1f%%)",
        tf, consensus["consensus"], consensus["strength"],
    )

    # 6. Divergences + signal override
    btc_regime = next(
        (r["regime"] for r in results if "BTC" in r["symbol"]),
        "FLAT",
    )

    for r in results:
        # Divergence vs BTC
        r["divergence"] = detect_divergence(r["regime"], btc_regime)

        # Override: MARKDOWN + WAIT -> RISK_OFF when market is RISK-OFF
        if (
            consensus["consensus"] == "RISK-OFF"
            and r["signal"] == "WAIT"
            and r["regime"] == "MARKDOWN"
        ):
            r["signal"] = "RISK_OFF"

    divergence_count = sum(1 for r in results if r["divergence"] is not None)
    if divergence_count:
        logger.info("Detected %d divergences on %s", divergence_count, tf)

    # 7. Alt-season gauge
    alt_gauge = compute_alt_season_gauge(results)
    logger.info(
        "Alt-season gauge for %s: score=%.1f label=%s",
        tf, alt_gauge["score"], alt_gauge["label"],
    )

    return results, consensus, alt_gauge


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
                results, consensus, alt_gauge = await _scan_timeframe(
                    scan_cache.symbols, tf,
                )
                scan_cache.results[tf] = results
                scan_cache.consensus[tf] = consensus
                scan_cache.alt_season[tf] = alt_gauge
            except Exception:
                logger.exception("Scan failed for timeframe %s", tf)

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
    }


def get_scan_status() -> dict:
    """Return lightweight scan metadata."""
    return {
        "is_scanning": cache.is_scanning,
        "last_scan_time": cache.last_scan_time,
        "symbols_count": len(cache.symbols),
        "cache_age_seconds": cache.get_cache_age(),
    }
