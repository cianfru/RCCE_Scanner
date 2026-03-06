"""
replay_engine.py
~~~~~~~~~~~~~~~~
Bar-by-bar replay through the exact same engine pipeline as the live scanner.

Feeds historical OHLCV data through RCCE, Heatmap, and Exhaustion engines,
computes consensus and divergence, then synthesizes signals — producing
identical results to the live scanner by construction.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import numpy as np

# Import the same engine functions used by the live scanner
from engines.rcce_engine import compute_rcce
from engines.heatmap_engine import compute_heatmap
from engines.exhaustion_engine import compute_exhaustion
from scanner import _process_symbol, compute_consensus, detect_divergence, classify_asset
from signal_synthesizer import synthesize_signal
from confluence import compute_confluence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------

@dataclass
class BarResult:
    """Result for a single symbol at a single bar."""
    timestamp: float
    date: str
    symbol: str
    price: float
    signal: str
    raw_signal: str
    regime: str
    confidence: float
    zscore: float
    heat: int
    conditions_met: int
    conditions_total: int
    signal_reason: str
    signal_warnings: List[str]
    confluence_score: int = 0
    confluence_label: str = "UNKNOWN"
    divergence: Optional[str] = None
    exhaustion_state: str = "NEUTRAL"
    vol_state: str = "MID"
    # For condition analysis
    condition_flags: List[bool] = field(default_factory=list)


# ---------------------------------------------------------------------------
# OHLCV slicing helpers
# ---------------------------------------------------------------------------

_ROLLING_WINDOW = 500  # Max bars to pass to engines (they need ~200 max)


def _slice_ohlcv(ohlcv: dict, end_idx: int, rolling: bool = False) -> dict:
    """Slice OHLCV arrays up to end_idx (exclusive).

    If rolling=True, only keep the last _ROLLING_WINDOW bars to avoid
    O(n²) cost from expanding windows.
    """
    if rolling:
        start = max(0, end_idx - _ROLLING_WINDOW)
        return {k: v[start:end_idx] for k, v in ohlcv.items()}
    return {k: v[:end_idx] for k, v in ohlcv.items()}


def _find_weekly_slice(ohlcv_weekly: dict, timestamp_ms: float) -> Optional[dict]:
    """Return weekly OHLCV up to the given timestamp."""
    if ohlcv_weekly is None:
        return None
    ts = ohlcv_weekly["timestamp"]
    mask = ts <= timestamp_ms
    count = np.sum(mask)
    if count < 10:
        return None
    return {k: v[:count] for k, v in ohlcv_weekly.items()}


def _find_daily_index(ohlcv_1d: dict, timestamp_ms: float) -> int:
    """Find the 1d bar index that contains the given 4h timestamp."""
    if ohlcv_1d is None:
        return 0
    ts = ohlcv_1d["timestamp"]
    # Find last 1d timestamp <= current 4h timestamp
    mask = ts <= timestamp_ms
    return int(np.sum(mask))


# ---------------------------------------------------------------------------
# Main replay function
# ---------------------------------------------------------------------------

async def run_replay(
    symbols: List[str],
    ohlcv_4h: Dict[str, dict],
    ohlcv_1d: Dict[str, dict],
    ohlcv_1w: Dict[str, dict],
    fear_greed: Dict[str, int],
    warmup_bars: int = 400,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> List[BarResult]:
    """Run bar-by-bar replay through all engines.

    Parameters
    ----------
    symbols : list[str]
        Symbols to replay.
    ohlcv_4h, ohlcv_1d, ohlcv_1w : dict[str, dict]
        Historical OHLCV per symbol per timeframe.
    fear_greed : dict[str, int]
        {date_str: F&G value} for sentiment lookup.
    warmup_bars : int
        Number of bars to skip at the start for engine warmup.
    on_progress : callable or None
        Called with (progress_pct, status_msg) for UI updates.

    Returns
    -------
    list[BarResult]
        All signal results across all bars and symbols.
    """
    t0 = time.time()

    # Filter to symbols that have 4h data
    valid_symbols = [s for s in symbols if s in ohlcv_4h]
    if not valid_symbols:
        logger.error("No valid symbols with 4h data")
        return []

    # Find the common bar range (intersection of available timestamps)
    # Use the symbol with the fewest bars to determine range
    min_bars = min(len(ohlcv_4h[s]["timestamp"]) for s in valid_symbols)
    logger.info("Replay: %d symbols, %d total bars, warmup=%d", len(valid_symbols), min_bars, warmup_bars)

    if min_bars <= warmup_bars:
        logger.error("Insufficient bars (%d) for warmup (%d)", min_bars, warmup_bars)
        return []

    # Reference data (BTC/ETH) for RCCE beta calculations
    btc_sym = "BTC/USDT"
    eth_sym = "ETH/USDT"

    total_replay_bars = min_bars - warmup_bars
    all_results: List[BarResult] = []

    # Cache for 1d results (updated every ~6 bars)
    cached_1d_results: Dict[str, dict] = {}
    last_1d_update_idx = -6  # Force first update

    # Track consecutive WAIT signals per symbol for decay
    wait_counts: Dict[str, int] = {s: 0 for s in valid_symbols}

    for bar_idx in range(warmup_bars, min_bars):
        progress = (bar_idx - warmup_bars) / total_replay_bars * 100.0

        # Current timestamp from BTC (or first available symbol)
        ref_sym = btc_sym if btc_sym in ohlcv_4h else valid_symbols[0]
        current_ts = ohlcv_4h[ref_sym]["timestamp"][bar_idx]
        current_date = datetime.fromtimestamp(current_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

        # Yield to event loop every 5 bars to keep server responsive
        # (~500ms between yields — fast enough for HTTP polls)
        if bar_idx % 5 == 0:
            await asyncio.sleep(0)

        if on_progress and bar_idx % 50 == 0:
            on_progress(progress, f"Bar {bar_idx - warmup_bars}/{total_replay_bars} ({current_date})")

        # --- Step 1: Run 4h engines on all symbols ---
        bar_results_raw: List[dict] = []

        for symbol in valid_symbols:
            data_4h = ohlcv_4h[symbol]
            if bar_idx >= len(data_4h["timestamp"]):
                continue

            # Slice 4h data up to current bar (rolling window for performance)
            slice_4h = _slice_ohlcv(data_4h, bar_idx + 1, rolling=True)

            # Get weekly slice for heatmap/exhaustion
            weekly = _find_weekly_slice(ohlcv_1w.get(symbol), current_ts) if symbol in ohlcv_1w else None

            # Get BTC/ETH reference slices (rolling)
            btc_slice = _slice_ohlcv(ohlcv_4h[btc_sym], bar_idx + 1, rolling=True) if btc_sym in ohlcv_4h else None
            eth_slice = _slice_ohlcv(ohlcv_4h[eth_sym], bar_idx + 1, rolling=True) if eth_sym in ohlcv_4h else None

            try:
                result = _process_symbol(
                    symbol=symbol,
                    timeframe="4h",
                    ohlcv=slice_4h,
                    weekly=weekly,
                    btc_data=btc_slice,
                    eth_data=eth_slice,
                )
                bar_results_raw.append(result)
            except Exception:
                logger.debug("Engine failed for %s at bar %d", symbol, bar_idx)
                continue

        if not bar_results_raw:
            continue

        # --- Step 2: Compute consensus ---
        consensus = compute_consensus(bar_results_raw)

        # --- Step 3: Detect divergences ---
        btc_regime = next(
            (r["regime"] for r in bar_results_raw if "BTC" in r["symbol"]),
            "FLAT",
        )
        for r in bar_results_raw:
            r["divergence"] = detect_divergence(r["regime"], btc_regime)

        # --- Step 4: Update 1d results every ~6 bars for confluence ---
        if bar_idx - last_1d_update_idx >= 6:
            last_1d_update_idx = bar_idx
            for symbol in valid_symbols:
                if symbol not in ohlcv_1d:
                    continue
                daily_idx = _find_daily_index(ohlcv_1d[symbol], current_ts)
                if daily_idx < 50:
                    continue
                slice_1d = _slice_ohlcv(ohlcv_1d[symbol], daily_idx, rolling=True)
                weekly = _find_weekly_slice(ohlcv_1w.get(symbol), current_ts) if symbol in ohlcv_1w else None
                btc_1d = _slice_ohlcv(ohlcv_1d[btc_sym], daily_idx, rolling=True) if btc_sym in ohlcv_1d else None
                eth_1d = _slice_ohlcv(ohlcv_1d[eth_sym], daily_idx, rolling=True) if eth_sym in ohlcv_1d else None

                try:
                    cached_1d_results[symbol] = _process_symbol(
                        symbol=symbol, timeframe="1d",
                        ohlcv=slice_1d, weekly=weekly,
                        btc_data=btc_1d, eth_data=eth_1d,
                    )
                except Exception:
                    pass

        # --- Step 5: Compute confluence per symbol ---
        confluences: Dict[str, dict] = {}
        for r in bar_results_raw:
            sym = r["symbol"]
            if sym in cached_1d_results:
                c = compute_confluence(r, cached_1d_results[sym])
                confluences[sym] = {
                    "score": c.score,
                    "label": c.label,
                    "regime_aligned": c.regime_aligned,
                    "signal_aligned": c.signal_aligned,
                }

        # --- Step 6: Look up Fear & Greed ---
        fng_value = fear_greed.get(current_date, 50)
        sentiment_dict = {"fear_greed_value": fng_value, "fear_greed_label": ""}

        # --- Step 7: Synthesize signals ---
        for r in bar_results_raw:
            try:
                synth = synthesize_signal(
                    r, consensus,
                    global_metrics=None,
                    positioning=None,
                    sentiment=sentiment_dict,
                    stablecoin=None,
                )
                sym = r["symbol"]
                conf = confluences.get(sym, {})

                bar_result = BarResult(
                    timestamp=current_ts,
                    date=current_date,
                    symbol=sym,
                    price=r["price"],
                    signal=synth.signal,
                    raw_signal=synth.raw_signal,
                    regime=r["regime"],
                    confidence=r["confidence"],
                    zscore=r["zscore"],
                    heat=r.get("heat", 0),
                    conditions_met=synth.conditions_met,
                    conditions_total=synth.conditions_total,
                    signal_reason=synth.reason,
                    signal_warnings=synth.warnings,
                    confluence_score=conf.get("score", 0),
                    confluence_label=conf.get("label", "UNKNOWN"),
                    divergence=r.get("divergence"),
                    exhaustion_state=r.get("exhaustion_state", "NEUTRAL"),
                    vol_state=r.get("vol_state", "MID"),
                )
                all_results.append(bar_result)

                # Track WAIT count for signal decay
                if synth.signal == "WAIT":
                    wait_counts[sym] = wait_counts.get(sym, 0) + 1
                else:
                    wait_counts[sym] = 0

            except Exception:
                logger.debug("Signal synthesis failed for %s at bar %d", r.get("symbol"), bar_idx)

    elapsed = time.time() - t0
    logger.info(
        "Replay complete: %d results in %.1fs (%d bars × %d symbols)",
        len(all_results), elapsed, total_replay_bars, len(valid_symbols),
    )

    if on_progress:
        on_progress(100.0, "Replay complete")

    return all_results
