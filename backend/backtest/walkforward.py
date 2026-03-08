"""
walkforward.py
~~~~~~~~~~~~~~
Walk-forward validation: splits the backtest period into non-overlapping
windows, runs each independently with fresh capital, and aggregates
results to measure robustness vs overfitting.

Reuses the same engine pipeline (replay_engine, position_manager, analytics)
without modifying them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

from backtest.data_loader import (
    fetch_historical_batch,
    fetch_historical_fear_greed,
    _date_to_ms,
    _ms_to_date,
)
from backtest.replay_engine import run_replay, BarResult
from backtest.position_manager import PositionManager, Trade
from backtest.analytics import compute_metrics, BacktestMetrics
from backtest.runner import (
    _compute_bmsb_filter,
    _is_bmsb_blocked,
    DEFAULT_BACKTEST_SYMBOLS,
    WARMUP_BARS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config + Result containers
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardConfig:
    symbols: List[str] = field(default_factory=lambda: DEFAULT_BACKTEST_SYMBOLS.copy())
    start_date: str = "2021-01-01"
    end_date: str = ""  # empty = today
    initial_capital: float = 10000.0
    use_confluence: bool = True
    use_fear_greed: bool = True
    timeframe: str = "4h"
    leverage: float = 1.0
    # Walk-forward specific
    test_window_days: int = 180   # 6 months per window
    step_days: int = 180          # non-overlapping
    warmup_days: int = 0          # 0 = auto-calculate


@dataclass
class WindowResult:
    """Results for a single test window."""
    window_index: int
    test_start: str
    test_end: str
    warmup_start: str
    metrics: Optional[BacktestMetrics] = None
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[float, float]] = field(default_factory=list)
    btc_equity_curve: List[Tuple[float, float]] = field(default_factory=list)
    signal_distribution: Dict[str, int] = field(default_factory=dict)
    bar_count: int = 0
    bmsb_blocked_pct: float = 0.0


@dataclass
class WalkForwardResult:
    id: str
    config: Optional[WalkForwardConfig] = None
    status: str = "pending"
    progress: float = 0.0
    current_window: int = 0
    total_windows: int = 0
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Per-window results
    window_results: List[WindowResult] = field(default_factory=list)

    # Aggregated metrics (trade-concatenated across all windows)
    aggregate_metrics: Optional[BacktestMetrics] = None

    # Full-period single-pass for overfitting comparison
    full_period_metrics: Optional[BacktestMetrics] = None

    # Overfitting analysis
    overfitting_score: Optional[float] = None   # WF return / full return
    consistency_score: Optional[float] = None   # % of windows profitable
    sharpe_stability: Optional[float] = None    # std of per-window Sharpe

    # Stitched equity curve (chains windows sequentially)
    stitched_equity_curve: List[Tuple[float, float]] = field(default_factory=list)
    full_equity_curve: List[Tuple[float, float]] = field(default_factory=list)
    btc_equity_curve: List[Tuple[float, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_walkforward_store: Dict[str, WalkForwardResult] = {}


def get_walkforward(wf_id: str) -> Optional[WalkForwardResult]:
    return _walkforward_store.get(wf_id)


def list_walkforwards() -> List[dict]:
    return [
        {
            "id": r.id,
            "status": r.status,
            "progress": r.progress,
            "current_window": r.current_window,
            "total_windows": r.total_windows,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
        }
        for r in _walkforward_store.values()
    ]


# ---------------------------------------------------------------------------
# Window generation
# ---------------------------------------------------------------------------

def _generate_windows(config: WalkForwardConfig) -> List[dict]:
    """Generate non-overlapping test windows with warmup periods."""
    start_ms = _date_to_ms(config.start_date)
    end_ms = _date_to_ms(config.end_date)

    # Auto-calculate warmup days from timeframe
    warmup_days = config.warmup_days
    if warmup_days <= 0:
        warmup_days = 70 if config.timeframe == "4h" else 210

    test_ms = config.test_window_days * 86400 * 1000
    step_ms = config.step_days * 86400 * 1000
    warmup_ms = warmup_days * 86400 * 1000

    windows = []
    test_start = start_ms
    idx = 0

    while test_start + test_ms <= end_ms:
        warmup_start = test_start - warmup_ms
        test_end = test_start + test_ms

        windows.append({
            "index": idx,
            "warmup_start_ms": warmup_start,
            "test_start_ms": test_start,
            "test_end_ms": test_end,
            "warmup_start": _ms_to_date(warmup_start),
            "test_start": _ms_to_date(test_start),
            "test_end": _ms_to_date(test_end),
        })

        test_start += step_ms
        idx += 1

    return windows


# ---------------------------------------------------------------------------
# Data slicing helpers
# ---------------------------------------------------------------------------

def _slice_ohlcv_by_time(
    ohlcv_all: Dict[str, dict],
    start_ms: float,
    end_ms: float,
) -> Dict[str, dict]:
    """Slice per-symbol OHLCV data to [start_ms, end_ms]."""
    sliced = {}
    for sym, data in ohlcv_all.items():
        ts = np.asarray(data["timestamp"], dtype=np.float64)
        mask = (ts >= start_ms) & (ts <= end_ms)
        count = int(np.sum(mask))
        if count > 0:
            sliced[sym] = {k: np.asarray(v)[mask] for k, v in data.items()}
    return sliced


def _count_warmup_bars(ohlcv: dict, test_start_ms: float, ref_sym: str) -> int:
    """Count how many bars fall before the test start (= warmup bars)."""
    if ref_sym not in ohlcv:
        return 0
    ts = np.asarray(ohlcv[ref_sym]["timestamp"], dtype=np.float64)
    return int(np.sum(ts < test_start_ms))


# ---------------------------------------------------------------------------
# Single window execution
# ---------------------------------------------------------------------------

async def _run_window(
    window: dict,
    ohlcv_4h_all: Dict[str, dict],
    ohlcv_1d_all: Dict[str, dict],
    ohlcv_1w_all: Dict[str, dict],
    fear_greed: Dict[str, int],
    bmsb_blocked_map: Dict[float, bool],
    bmsb_weekly_ts: List[float],
    config: WalkForwardConfig,
    valid_symbols: List[str],
) -> WindowResult:
    """Run a single walk-forward window."""
    w_idx = window["index"]
    warmup_start_ms = window["warmup_start_ms"]
    test_start_ms = window["test_start_ms"]
    test_end_ms = window["test_end_ms"]

    logger.info(
        "Window %d: warmup=%s, test=%s → %s",
        w_idx, window["warmup_start"], window["test_start"], window["test_end"],
    )

    # Slice data for this window (warmup + test period)
    sliced_4h = _slice_ohlcv_by_time(ohlcv_4h_all, warmup_start_ms, test_end_ms)
    sliced_1d = _slice_ohlcv_by_time(ohlcv_1d_all, warmup_start_ms, test_end_ms)
    sliced_1w = _slice_ohlcv_by_time(ohlcv_1w_all, warmup_start_ms, test_end_ms)

    # Determine warmup bar count from reference symbol
    btc_sym = "BTC/USDT"
    ref_sym = btc_sym if btc_sym in sliced_4h else (valid_symbols[0] if valid_symbols else None)
    if ref_sym is None or ref_sym not in sliced_4h:
        logger.warning("Window %d: no reference data, skipping", w_idx)
        return WindowResult(
            window_index=w_idx,
            test_start=window["test_start"],
            test_end=window["test_end"],
            warmup_start=window["warmup_start"],
        )

    warmup_bars = _count_warmup_bars(sliced_4h, test_start_ms, ref_sym)

    # Need at least some warmup
    if warmup_bars < 50:
        logger.warning("Window %d: insufficient warmup (%d bars), skipping", w_idx, warmup_bars)
        return WindowResult(
            window_index=w_idx,
            test_start=window["test_start"],
            test_end=window["test_end"],
            warmup_start=window["warmup_start"],
        )

    # Run replay engine (with BMSB data for LIGHT_SHORT signals)
    bar_results = await run_replay(
        symbols=valid_symbols,
        ohlcv_4h=sliced_4h,
        ohlcv_1d=sliced_1d,
        ohlcv_1w=sliced_1w,
        fear_greed=fear_greed,
        warmup_bars=warmup_bars,
        bmsb_blocked_map=bmsb_blocked_map,
        bmsb_weekly_ts=bmsb_weekly_ts,
    )

    if not bar_results:
        logger.info("Window %d: no bar results", w_idx)
        return WindowResult(
            window_index=w_idx,
            test_start=window["test_start"],
            test_end=window["test_end"],
            warmup_start=window["warmup_start"],
        )

    # Fresh position manager for this window
    pm = PositionManager(config.initial_capital, valid_symbols, leverage=config.leverage)

    # BTC buy-and-hold for this window
    btc_initial_price = None
    btc_equity: List[Tuple[float, float]] = []

    # BTC price lookup from raw OHLCV
    btc_price_lookup: Dict[float, float] = {}
    btc_4h = sliced_4h.get(btc_sym)
    if btc_4h is not None:
        for i in range(len(btc_4h["timestamp"])):
            ts_val = float(btc_4h["timestamp"][i])
            btc_price_lookup[ts_val] = float(btc_4h["close"][i])

    # Group bars by timestamp
    bars_by_ts: Dict[float, List[BarResult]] = {}
    for b in bar_results:
        bars_by_ts.setdefault(b.timestamp, []).append(b)

    # Track BMSB blocking for stats
    bmsb_blocked_count = 0
    total_ts_count = 0
    prev_macro_blocked = False

    for ts in sorted(bars_by_ts.keys()):
        bars = bars_by_ts[ts]

        # BMSB macro filter
        current_macro_blocked = _is_bmsb_blocked(bmsb_blocked_map, bmsb_weekly_ts, ts)
        pm.macro_blocked = current_macro_blocked
        if current_macro_blocked:
            bmsb_blocked_count += 1
        total_ts_count += 1

        # Macro flip: bearish → bullish → close ALL shorts globally
        if prev_macro_blocked and not current_macro_blocked:
            pm.close_all_shorts(ts, "MACRO_FLIP")
        prev_macro_blocked = current_macro_blocked

        for bar in bars:
            pm.process_bar(bar)

        prices = {b.symbol: b.price for b in bars}
        pm.mark_to_market(ts, prices)

        # BTC benchmark
        btc_price = btc_price_lookup.get(ts) or prices.get(btc_sym)
        if btc_price:
            if btc_initial_price is None:
                btc_initial_price = btc_price
            btc_eq = config.initial_capital * (btc_price / btc_initial_price)
            btc_equity.append((ts, btc_eq))

    # Close remaining positions
    if bar_results:
        last_ts = bar_results[-1].timestamp
        pm.close_all_at_end(last_ts)

    # Signal distribution
    sig_dist: Dict[str, int] = {}
    for b in bar_results:
        sig_dist[b.signal] = sig_dist.get(b.signal, 0) + 1

    # Compute metrics
    test_days = int((test_end_ms - test_start_ms) / (86400 * 1000))
    metrics = compute_metrics(pm.trades, pm.equity_curve, btc_equity, test_days)

    bmsb_pct = (bmsb_blocked_count / max(total_ts_count, 1)) * 100

    logger.info(
        "Window %d complete: %.1f%% return, %d trades, BMSB blocked %.0f%%",
        w_idx, metrics.total_return_pct, metrics.total_trades, bmsb_pct,
    )

    return WindowResult(
        window_index=w_idx,
        test_start=window["test_start"],
        test_end=window["test_end"],
        warmup_start=window["warmup_start"],
        metrics=metrics,
        trades=pm.trades,
        equity_curve=pm.equity_curve,
        btc_equity_curve=btc_equity,
        signal_distribution=sig_dist,
        bar_count=len(bar_results),
        bmsb_blocked_pct=bmsb_pct,
    )


# ---------------------------------------------------------------------------
# Equity curve stitching
# ---------------------------------------------------------------------------

def _stitch_equity_curves(
    window_results: List[WindowResult],
    initial_capital: float,
) -> List[Tuple[float, float]]:
    """Chain window equity curves so each starts where the previous ended."""
    stitched: List[Tuple[float, float]] = []
    running_capital = initial_capital

    for wr in window_results:
        if not wr.equity_curve:
            continue

        window_initial = wr.equity_curve[0][1]
        if window_initial <= 0:
            continue

        scale = running_capital / window_initial
        for ts, eq in wr.equity_curve:
            stitched.append((ts, eq * scale))

        # Next window starts where this one ended
        running_capital = wr.equity_curve[-1][1] * scale

    return stitched


# ---------------------------------------------------------------------------
# Overfitting analysis
# ---------------------------------------------------------------------------

def _compute_overfitting_analysis(
    window_results: List[WindowResult],
    aggregate_metrics: Optional[BacktestMetrics],
    full_period_metrics: Optional[BacktestMetrics],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Compute overfitting score, consistency, and Sharpe stability."""

    # Consistency: % of windows with positive return
    windows_with_metrics = [w for w in window_results if w.metrics is not None]
    if not windows_with_metrics:
        return None, None, None

    profitable = sum(1 for w in windows_with_metrics if w.metrics.total_return_pct > 0)
    consistency = profitable / len(windows_with_metrics)

    # Overfitting score: WF aggregate return / full-period return
    overfitting = None
    if (
        aggregate_metrics is not None
        and full_period_metrics is not None
        and full_period_metrics.total_return_pct != 0
    ):
        overfitting = aggregate_metrics.total_return_pct / full_period_metrics.total_return_pct

    # Sharpe stability: std dev of per-window Sharpe ratios
    sharpe_values = [w.metrics.sharpe_ratio for w in windows_with_metrics]
    sharpe_std = float(np.std(sharpe_values)) if len(sharpe_values) > 1 else 0.0

    return overfitting, consistency, sharpe_std


# ---------------------------------------------------------------------------
# Main walk-forward runner
# ---------------------------------------------------------------------------

async def run_walkforward(config: WalkForwardConfig) -> str:
    """Launch a walk-forward validation. Returns ID immediately."""
    wf_id = uuid4().hex[:8]
    result = WalkForwardResult(id=wf_id, config=config, started_at=time.time())
    _walkforward_store[wf_id] = result

    asyncio.create_task(_run_walkforward_task(wf_id, config, result))
    return wf_id


async def _run_walkforward_task(
    wf_id: str,
    config: WalkForwardConfig,
    result: WalkForwardResult,
) -> None:
    """Async task: fetch data once, run all windows, aggregate results."""
    try:
        # Fill in end date if empty
        if not config.end_date:
            config.end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Generate windows
        windows = _generate_windows(config)
        if not windows:
            result.status = "error"
            result.error = "Date range too short for even one window"
            result.completed_at = time.time()
            return

        result.total_windows = len(windows)
        logger.info("Walk-forward: %d windows, %s → %s", len(windows), config.start_date, config.end_date)

        # --- Phase A: Fetch ALL data once ---
        result.status = "fetching"
        result.progress = 2.0

        # Earliest warmup extends before start_date
        earliest_warmup_ms = min(w["warmup_start_ms"] for w in windows)
        earliest_warmup_date = _ms_to_date(earliest_warmup_ms)

        symbols = config.symbols if config.symbols else DEFAULT_BACKTEST_SYMBOLS.copy()

        # Determine warmup bars for each timeframe
        warmup_4h = WARMUP_BARS  # 400
        warmup_1d = 200
        warmup_1w = 30

        logger.info("Fetching data: %s → %s (warmup from %s)", config.start_date, config.end_date, earliest_warmup_date)

        ohlcv_4h = await fetch_historical_batch(
            symbols, "4h" if config.timeframe == "4h" else "1d",
            earliest_warmup_date, config.end_date, warmup_bars=warmup_4h,
        )
        result.progress = 10.0

        ohlcv_1d = await fetch_historical_batch(
            symbols, "1d", earliest_warmup_date, config.end_date, warmup_bars=warmup_1d,
        )
        result.progress = 18.0

        ohlcv_1w = await fetch_historical_batch(
            symbols, "1w", earliest_warmup_date, config.end_date, warmup_bars=warmup_1w,
        )
        result.progress = 22.0

        # Fear & Greed
        total_days_ms = _date_to_ms(config.end_date) - earliest_warmup_ms
        total_days = min(int(total_days_ms / (86400 * 1000)) + 30, 2000)
        fear_greed = await fetch_historical_fear_greed(total_days)
        result.progress = 25.0

        # Valid symbols (those with primary data)
        primary_ohlcv = ohlcv_4h  # same as runner.py logic
        valid_symbols = [s for s in symbols if s in primary_ohlcv]
        if not valid_symbols:
            result.status = "error"
            result.error = "No valid symbols with data"
            result.completed_at = time.time()
            return

        # BMSB filter — compute once from full BTC weekly data
        btc_sym = "BTC/USDT"
        bmsb_blocked_map: Dict[float, bool] = {}
        bmsb_weekly_ts: List[float] = []
        btc_weekly_data = ohlcv_1w.get(btc_sym)
        if btc_weekly_data is not None and len(btc_weekly_data.get("close", [])) >= 21:
            bmsb_blocked_map = _compute_bmsb_filter(btc_weekly_data)
            bmsb_weekly_ts = sorted(bmsb_blocked_map.keys())

        logger.info("Data ready: %d symbols, BMSB computed", len(valid_symbols))

        # --- Phase B: Run each window ---
        result.status = "running_window"
        window_progress_share = 50.0 / len(windows)  # 25% → 75% for windows

        for w in windows:
            result.current_window = w["index"] + 1
            result.progress = 25.0 + w["index"] * window_progress_share

            wr = await _run_window(
                window=w,
                ohlcv_4h_all=primary_ohlcv,
                ohlcv_1d_all=ohlcv_1d,
                ohlcv_1w_all=ohlcv_1w,
                fear_greed=fear_greed,
                bmsb_blocked_map=bmsb_blocked_map,
                bmsb_weekly_ts=bmsb_weekly_ts,
                config=config,
                valid_symbols=valid_symbols,
            )
            result.window_results.append(wr)

            # Yield control
            await asyncio.sleep(0)

        result.progress = 75.0

        # --- Phase C: Full-period single-pass (for comparison) ---
        logger.info("Running full-period pass for overfitting comparison...")

        # Determine warmup bars for full period
        full_warmup = warmup_4h if config.timeframe == "4h" else warmup_1d

        # Slice to just the test range (start_date → end_date) + warmup
        full_start_ms = _date_to_ms(config.start_date)
        full_end_ms = _date_to_ms(config.end_date)

        # The full data already includes warmup (fetched from earliest_warmup_date)
        # For the full-period pass, use data from start_date minus warmup
        auto_warmup_days = 70 if config.timeframe == "4h" else 210
        full_warmup_start_ms = full_start_ms - (auto_warmup_days * 86400 * 1000)
        sliced_4h_full = _slice_ohlcv_by_time(primary_ohlcv, full_warmup_start_ms, full_end_ms)
        sliced_1d_full = _slice_ohlcv_by_time(ohlcv_1d, full_warmup_start_ms, full_end_ms)
        sliced_1w_full = _slice_ohlcv_by_time(ohlcv_1w, full_warmup_start_ms, full_end_ms)

        full_warmup_bars = _count_warmup_bars(sliced_4h_full, full_start_ms, btc_sym)

        full_bar_results = await run_replay(
            symbols=valid_symbols,
            ohlcv_4h=sliced_4h_full,
            ohlcv_1d=sliced_1d_full,
            ohlcv_1w=sliced_1w_full,
            fear_greed=fear_greed,
            warmup_bars=max(full_warmup_bars, 50),
            bmsb_blocked_map=bmsb_blocked_map,
            bmsb_weekly_ts=bmsb_weekly_ts,
        )
        result.progress = 85.0

        if full_bar_results:
            full_pm = PositionManager(config.initial_capital, valid_symbols, leverage=config.leverage)

            # BTC benchmark for full period
            full_btc_initial = None
            full_btc_equity: List[Tuple[float, float]] = []
            btc_4h_data = sliced_4h_full.get(btc_sym)
            full_btc_lookup: Dict[float, float] = {}
            if btc_4h_data is not None:
                for i in range(len(btc_4h_data["timestamp"])):
                    full_btc_lookup[float(btc_4h_data["timestamp"][i])] = float(btc_4h_data["close"][i])

            full_bars_by_ts: Dict[float, List[BarResult]] = {}
            for b in full_bar_results:
                full_bars_by_ts.setdefault(b.timestamp, []).append(b)

            full_prev_macro = False
            for ts in sorted(full_bars_by_ts.keys()):
                bars = full_bars_by_ts[ts]
                full_macro = _is_bmsb_blocked(bmsb_blocked_map, bmsb_weekly_ts, ts)
                full_pm.macro_blocked = full_macro

                # Macro flip: close all shorts when BMSB turns bullish
                if full_prev_macro and not full_macro:
                    full_pm.close_all_shorts(ts, "MACRO_FLIP")
                full_prev_macro = full_macro

                for bar in bars:
                    full_pm.process_bar(bar)
                prices = {b.symbol: b.price for b in bars}
                full_pm.mark_to_market(ts, prices)

                btc_price = full_btc_lookup.get(ts) or prices.get(btc_sym)
                if btc_price:
                    if full_btc_initial is None:
                        full_btc_initial = btc_price
                    full_btc_equity.append((ts, config.initial_capital * (btc_price / full_btc_initial)))

            if full_bar_results:
                full_pm.close_all_at_end(full_bar_results[-1].timestamp)

            full_test_days = int((full_end_ms - full_start_ms) / (86400 * 1000))
            result.full_period_metrics = compute_metrics(
                full_pm.trades, full_pm.equity_curve, full_btc_equity, full_test_days,
            )
            result.full_equity_curve = full_pm.equity_curve
            result.btc_equity_curve = full_btc_equity

        result.progress = 90.0

        # --- Phase D: Aggregate metrics ---
        logger.info("Computing aggregate metrics...")

        # Concatenate all trades from all windows
        all_trades: List[Trade] = []
        for wr in result.window_results:
            all_trades.extend(wr.trades)

        # Stitch equity curves
        result.stitched_equity_curve = _stitch_equity_curves(
            result.window_results, config.initial_capital,
        )

        # Build a stitched BTC equity curve too
        stitched_btc: List[Tuple[float, float]] = []
        btc_running = config.initial_capital
        for wr in result.window_results:
            if not wr.btc_equity_curve:
                continue
            btc_window_initial = wr.btc_equity_curve[0][1]
            if btc_window_initial <= 0:
                continue
            scale = btc_running / btc_window_initial
            for ts, eq in wr.btc_equity_curve:
                stitched_btc.append((ts, eq * scale))
            btc_running = wr.btc_equity_curve[-1][1] * scale

        # Compute aggregate metrics from stitched curves
        total_test_days = sum(
            int((_date_to_ms(wr.test_end) - _date_to_ms(wr.test_start)) / (86400 * 1000))
            for wr in result.window_results
        )

        if all_trades or result.stitched_equity_curve:
            result.aggregate_metrics = compute_metrics(
                all_trades,
                result.stitched_equity_curve,
                stitched_btc,
                total_test_days,
            )

        # Overfitting analysis
        overfitting, consistency, sharpe_std = _compute_overfitting_analysis(
            result.window_results,
            result.aggregate_metrics,
            result.full_period_metrics,
        )
        result.overfitting_score = overfitting
        result.consistency_score = consistency
        result.sharpe_stability = sharpe_std

        # --- Done ---
        result.status = "complete"
        result.progress = 100.0
        result.completed_at = time.time()

        elapsed = result.completed_at - result.started_at

        # Log summary
        agg = result.aggregate_metrics
        full = result.full_period_metrics
        logger.info(
            "Walk-forward %s complete in %.0fs: %d windows",
            wf_id, elapsed, len(result.window_results),
        )
        if agg:
            logger.info(
                "  Aggregate: %.1f%% return, Sharpe %.2f, %d trades, %.1f%% WR",
                agg.total_return_pct, agg.sharpe_ratio, agg.total_trades, agg.win_rate,
            )
        if full:
            logger.info(
                "  Full-period: %.1f%% return, Sharpe %.2f, %d trades",
                full.total_return_pct, full.sharpe_ratio, full.total_trades,
            )
        if overfitting is not None:
            logger.info(
                "  Overfitting: score=%.2f, consistency=%.0f%%, Sharpe stability=%.2f",
                overfitting, (consistency or 0) * 100, sharpe_std or 0,
            )

    except Exception as exc:
        logger.error("Walk-forward %s failed: %s", wf_id, exc, exc_info=True)
        result.status = "error"
        result.error = str(exc)
        result.completed_at = time.time()
