"""
replay_engine.py
~~~~~~~~~~~~~~~~
Causal bar-close replay through the scanner engines and signal synthesizer.

Feeds historical OHLCV data through RCCE, Heatmap, and Exhaustion engines,
computes consensus and divergence, then synthesizes signals — producing
a technical baseline through the shared decision and agent pipeline. Historical
external feeds remain unavailable unless replaying recorded decision snapshots.
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
from scanner import _process_symbol, compute_consensus, detect_divergence, classify_asset, _compute_priority
from signal_synthesizer import synthesize_signal
from confluence import compute_confluence
from candle_snapshot import closed_candles, TF_MS
from decision_pipeline import evaluate_decision, new_state

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
    structure: dict = field(default_factory=dict)
    input_quality: dict = field(default_factory=dict)
    signal_score: int = 0
    priority_score: float = 0
    signal_status: str = "ready"
    cto: dict = field(default_factory=dict)
    cto_shadow: dict = field(default_factory=dict)
    regime_changes_7d: int = 0
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

_ROLLING_WINDOW = 600  # Max bars to pass to engines (they need ~200 max)


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
    mask = ts + TF_MS["1w"] <= timestamp_ms
    count = np.sum(mask)
    if count < 10:
        return None
    return {k: v[:count] for k, v in ohlcv_weekly.items()}


def _find_daily_index(ohlcv_1d: dict, timestamp_ms: float) -> int:
    """Number of daily bars completed by the decision timestamp."""
    if ohlcv_1d is None:
        return 0
    ts = ohlcv_1d["timestamp"]
    # Daily OHLCV is observable only after its close.
    mask = ts + TF_MS["1d"] <= timestamp_ms
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
    as_of_ms: Optional[float] = None,
    on_decision_bar: Optional[Callable] = None,
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
    decision_state = new_state()
    available_at = time.time() * 1000 if as_of_ms is None else as_of_ms

    # Filter to symbols that have primary data
    valid_symbols = [s for s in symbols if s in ohlcv_4h]
    if not valid_symbols:
        logger.error("No valid symbols with primary data")
        return []

    # Reference data (BTC/ETH) for RCCE beta calculations and timeline
    btc_sym = "BTC/USDT"
    eth_sym = "ETH/USDT"

    # Use the reference symbol (BTC) to drive the replay timeline.
    # Other symbols join when their data becomes available.
    ref_sym = btc_sym if btc_sym in ohlcv_4h else valid_symbols[0]
    ref_data = ohlcv_4h[ref_sym]
    ref_bars = len(ref_data["timestamp"])

    if ref_bars <= warmup_bars:
        logger.error("Insufficient ref bars (%d) for warmup (%d)", ref_bars, warmup_bars)
        return []

    # Build timestamp → local index mapping for each symbol.
    # This allows symbols with different start dates (e.g. SUI, JUP)
    # to be included only when they have sufficient data.
    sym_ts_to_idx: Dict[str, Dict[float, int]] = {}
    for sym in valid_symbols:
        ts_arr = ohlcv_4h[sym]["timestamp"]
        mapping: Dict[float, int] = {}
        for i in range(len(ts_arr)):
            t = float(ts_arr[i]) if isinstance(ts_arr, np.ndarray) else ts_arr[i]
            mapping[t] = i
        sym_ts_to_idx[sym] = mapping

    # Log per-symbol bar counts
    for sym in valid_symbols:
        sym_bars = len(ohlcv_4h[sym]["timestamp"])
        logger.info("  %s: %d bars (active after warmup=%d)", sym, sym_bars, warmup_bars)
    logger.info("Replay: %d symbols, ref=%s with %d bars, warmup=%d",
                len(valid_symbols), ref_sym, ref_bars, warmup_bars)

    total_replay_bars = ref_bars - warmup_bars
    all_results: List[BarResult] = []

    # Cache for 1d results (updated every ~6 bars)
    cached_1d_results: Dict[str, dict] = {}
    last_1d_update_idx = -6  # Force first update

    # Track consecutive WAIT signals per symbol for decay
    wait_counts: Dict[str, int] = {s: 0 for s in valid_symbols}

    for bar_idx in range(warmup_bars, ref_bars):
        progress = (bar_idx - warmup_bars) / total_replay_bars * 100.0

        # Current timestamp from the reference symbol
        bar_open_ts = float(ref_data["timestamp"][bar_idx])
        current_ts = bar_open_ts + TF_MS["4h"]
        if current_ts > available_at:
            break  # Providers may include an unfinished final historical candle.
        current_date = datetime.fromtimestamp(current_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

        # Yield to event loop every 5 bars to keep server responsive
        if bar_idx % 5 == 0:
            await asyncio.sleep(0)

        if on_progress and bar_idx % 50 == 0:
            on_progress(progress, f"Bar {bar_idx - warmup_bars}/{total_replay_bars} ({current_date})")

        # --- Step 1: Run engines on all symbols with data at this timestamp ---
        bar_results_raw: List[dict] = []

        for symbol in valid_symbols:
            # Look up this symbol's local index for the current timestamp
            local_idx = sym_ts_to_idx.get(symbol, {}).get(bar_open_ts)
            if local_idx is None or local_idx < warmup_bars:
                continue  # Symbol has no data or insufficient warmup at this time

            data_primary = ohlcv_4h[symbol]

            # Slice symbol's data using its LOCAL index (not the ref bar_idx)
            slice_primary = _slice_ohlcv(data_primary, local_idx + 1, rolling=True)

            # Get weekly slice for heatmap/exhaustion
            weekly = _find_weekly_slice(ohlcv_1w.get(symbol), current_ts) if symbol in ohlcv_1w else None

            # BTC/ETH reference slices use the REF bar_idx (they're always aligned)
            # Skip beta for /BTC pairs (currency mismatch with USD reference)
            quote = symbol.split("/")[1] if "/" in symbol else "USDT"
            is_btc_quoted = quote == "BTC"

            btc_slice = None if is_btc_quoted else (
                closed_candles(ohlcv_4h[btc_sym], "4h", current_ts) if btc_sym in ohlcv_4h else None
            )
            eth_slice = None if is_btc_quoted else (
                closed_candles(ohlcv_4h[eth_sym], "4h", current_ts) if eth_sym in ohlcv_4h else None
            )

            try:
                result = _process_symbol(
                    symbol=symbol,
                    timeframe="4h",
                    ohlcv=slice_primary,
                    weekly=weekly,
                    btc_data=btc_slice,
                    eth_data=eth_slice,
                    as_of_ms=current_ts,
                )
                bar_results_raw.append(result)
            except Exception:
                logger.debug("Engine failed for %s at bar %d (local=%d)", symbol, bar_idx, local_idx)
                continue

        if not bar_results_raw:
            continue

        # --- Step 2: Compute consensus ---
        consensus = compute_consensus(bar_results_raw)

        # --- Step 3: Detect divergences ---
        btc_regime = next(
            (r["regime"] for r in bar_results_raw if r["symbol"] == "BTC/USDT"),
            "FLAT",
        )
        for r in bar_results_raw:
            r["divergence"] = detect_divergence(r["regime"], btc_regime)

        # --- Step 4: Update 1d results every ~6 bars for confluence ---
        if int(current_ts // TF_MS["1d"]) != last_1d_update_idx:
            last_1d_update_idx = int(current_ts // TF_MS["1d"])
            for symbol in valid_symbols:
                if symbol not in ohlcv_1d:
                    continue
                daily_idx = _find_daily_index(ohlcv_1d[symbol], current_ts)
                if daily_idx < 50:
                    continue
                slice_1d = _slice_ohlcv(ohlcv_1d[symbol], daily_idx, rolling=True)
                weekly = _find_weekly_slice(ohlcv_1w.get(symbol), current_ts) if symbol in ohlcv_1w else None
                # Skip BTC/ETH reference for /BTC pairs (currency mismatch)
                sym_quote = symbol.split("/")[1] if "/" in symbol else "USDT"
                sym_is_btc_quoted = sym_quote == "BTC"
                btc_1d = None if sym_is_btc_quoted else (
                    closed_candles(ohlcv_1d[btc_sym], "1d", current_ts) if btc_sym in ohlcv_1d else None
                )
                eth_1d = None if sym_is_btc_quoted else (
                    closed_candles(ohlcv_1d[eth_sym], "1d", current_ts) if eth_sym in ohlcv_1d else None
                )

                try:
                    cached_1d_results[symbol] = _process_symbol(
                        symbol=symbol, timeframe="1d",
                        ohlcv=slice_1d, weekly=weekly,
                        btc_data=btc_1d, eth_data=eth_1d,
                        as_of_ms=current_ts,
                    )
                except Exception:
                    pass

        # --- Step 6: Look up Fear & Greed ---
        sentiment_date = datetime.fromtimestamp((current_ts - TF_MS["1d"]) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        known_fng = fear_greed.get(sentiment_date)
        sentiment_dict = {"fear_greed_value": known_fng} if known_fng is not None else None

        # Synthesize both timeframes before comparing signal direction.
        daily_consensus = compute_consensus(list(cached_1d_results.values()))
        btc_daily_regime = cached_1d_results.get("BTC/USDT", {}).get("regime", "FLAT")
        for daily in cached_1d_results.values():
            daily["divergence"] = detect_divergence(daily["regime"], btc_daily_regime)
            try:
                evaluate_decision(daily, {"consensus": daily_consensus, "sentiment": sentiment_dict}, decision_state,
                                  as_of=current_ts / 1000, metadata={"sentiment": {"source": "historical_fear_greed",
                                  "observed_at": (current_ts - TF_MS["1d"]) / 1000 if sentiment_dict else None}}, synthesizer=synthesize_signal)
            except Exception:
                daily["signal"] = "WAIT"
                logger.exception("Daily synthesis unavailable for %s", daily.get("symbol"))

        # --- Step 7: Synthesize signals ---
        import engines.rcce_engine as _rcce
        daily_cool = _rcce.COOL_OFF_RELEASE_Z is not None and _rcce.COOL_OFF_SOURCE == "daily"
        for r in bar_results_raw:
            if daily_cool:   # 4H entries wait while the daily chart is still unwinding its spike
                r["cool_off"] = (cached_1d_results.get(r["symbol"]) or {}).get("cool_off", {"active": False})
            try:
                evaluate_decision(r, {"consensus": consensus, "sentiment": sentiment_dict}, decision_state,
                                  as_of=current_ts / 1000, metadata={"sentiment": {"source": "historical_fear_greed",
                                  "observed_at": (current_ts - TF_MS["1d"]) / 1000 if sentiment_dict else None}},
                                  synthesizer=synthesize_signal)
                sym = r["symbol"]
                c = compute_confluence(r, cached_1d_results.get(sym))
                conf = {"score": c.score, "label": c.label}

                bar_result = BarResult(
                    timestamp=current_ts,
                    date=current_date,
                    symbol=sym,
                    price=r["price"],
                    signal=r["signal"],
                    raw_signal=r["raw_signal"],
                    regime=r["regime"],
                    confidence=r["confidence"],
                    zscore=r["zscore"],
                    heat=r.get("heat", 0),
                    conditions_met=r["conditions_met"],
                    conditions_total=r["conditions_total"],
                    signal_reason=r["signal_reason"],
                    signal_warnings=r["signal_warnings"],
                    condition_flags=[c["met"] for c in r["conditions_detail"]],
                    structure=r.get("structure", {}), input_quality=r.get("input_quality", {}),
                    signal_score=r.get("signal_score", 0), priority_score=_compute_priority(r),
                    signal_status=r.get("signal_status", "unavailable"),
                    cto=r.get("cto", {}), cto_shadow=r.get("cto_shadow", {}),
                    regime_changes_7d=r.get("regime_changes_7d", 0),
                    confluence_score=conf.get("score", 0),
                    confluence_label=conf.get("label", "UNKNOWN"),
                    divergence=r.get("divergence"),
                    exhaustion_state=r.get("exhaustion_state", "NEUTRAL"),
                    vol_state=r.get("vol_state", "MID"),
                )
                all_results.append(bar_result)

                # Track WAIT count for signal decay
                if r["signal"] == "WAIT":
                    wait_counts[sym] = wait_counts.get(sym, 0) + 1
                else:
                    wait_counts[sym] = 0

            except Exception:
                logger.debug("Signal synthesis failed for %s at bar %d", r.get("symbol"), bar_idx)

        # Read-only research observer, outside exception suppression: failures must
        # abort a study, not silently remove inconvenient historical decisions.
        if on_decision_bar:
            import copy
            on_decision_bar(current_ts / 1000, copy.deepcopy(bar_results_raw),
                            copy.deepcopy(list(cached_1d_results.values())))

    elapsed = time.time() - t0
    logger.info(
        "Replay complete: %d results in %.1fs (%d bars × %d symbols)",
        len(all_results), elapsed, total_replay_bars, len(valid_symbols),
    )

    if on_progress:
        on_progress(100.0, "Replay complete")

    return all_results
