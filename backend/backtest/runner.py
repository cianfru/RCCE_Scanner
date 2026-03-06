"""
runner.py
~~~~~~~~~
Orchestrates a full backtest: fetch data → replay → trades → metrics.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from backtest.data_loader import (
    fetch_historical_batch,
    fetch_historical_fear_greed,
    _date_to_ms,
)
from backtest.replay_engine import run_replay, BarResult
from backtest.position_manager import PositionManager, Trade
from backtest.analytics import (
    compute_metrics,
    compute_condition_analysis,
    BacktestMetrics,
    ConditionAnalysis,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default symbols (smaller set for faster backtests)
# ---------------------------------------------------------------------------

DEFAULT_BACKTEST_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
]

WARMUP_BARS = 400  # RCCE engine warmup


# ---------------------------------------------------------------------------
# Config + Result containers
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    symbols: List[str] = field(default_factory=lambda: DEFAULT_BACKTEST_SYMBOLS.copy())
    start_date: str = "2025-01-01"
    end_date: str = ""  # empty = today
    initial_capital: float = 10000.0
    use_confluence: bool = True
    use_fear_greed: bool = True


@dataclass
class BacktestResult:
    id: str = ""
    config: Optional[BacktestConfig] = None
    status: str = "pending"           # pending / fetching / replaying / complete / error
    progress: float = 0.0
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # Results (populated on completion)
    metrics: Optional[BacktestMetrics] = None
    condition_analysis: List[ConditionAnalysis] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[float, float]] = field(default_factory=list)
    btc_equity_curve: List[Tuple[float, float]] = field(default_factory=list)
    signal_distribution: Dict[str, int] = field(default_factory=dict)
    bar_count: int = 0
    symbols_loaded: int = 0


# ---------------------------------------------------------------------------
# In-memory store for running/completed backtests
# ---------------------------------------------------------------------------

_backtest_store: Dict[str, BacktestResult] = {}


def get_backtest(bt_id: str) -> Optional[BacktestResult]:
    return _backtest_store.get(bt_id)


def list_backtests() -> List[dict]:
    """Return summary of all backtests."""
    return [
        {
            "id": r.id,
            "status": r.status,
            "progress": r.progress,
            "start_date": r.config.start_date if r.config else "",
            "end_date": r.config.end_date if r.config else "",
            "symbols": len(r.config.symbols) if r.config else 0,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
        }
        for r in _backtest_store.values()
    ]


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

async def run_backtest(config: BacktestConfig) -> str:
    """Launch a backtest. Returns the backtest ID immediately.

    The actual work runs as a background asyncio task.
    Poll via get_backtest(bt_id) to check status.
    """
    bt_id = str(uuid4())[:8]

    if not config.end_date:
        config.end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    result = BacktestResult(
        id=bt_id,
        config=config,
        status="fetching",
        started_at=time.time(),
    )
    _backtest_store[bt_id] = result

    asyncio.create_task(_run_backtest_task(bt_id, config, result))
    return bt_id


async def _run_backtest_task(
    bt_id: str, config: BacktestConfig, result: BacktestResult
):
    """Full backtest pipeline (runs in background)."""
    try:
        symbols = config.symbols
        logger.info("Backtest %s: starting (%d symbols, %s to %s)",
                     bt_id, len(symbols), config.start_date, config.end_date)

        # --- Phase A: Fetch historical data ---
        result.status = "fetching"
        result.progress = 5.0

        # Fetch 3 timeframes sequentially to avoid exchange rate limits
        ohlcv_4h = await fetch_historical_batch(
            symbols, "4h", config.start_date, config.end_date, warmup_bars=WARMUP_BARS,
        )
        result.progress = 10.0
        ohlcv_1d = await fetch_historical_batch(
            symbols, "1d", config.start_date, config.end_date, warmup_bars=60,
        )
        result.progress = 18.0
        ohlcv_1w = await fetch_historical_batch(
            symbols, "1w", config.start_date, config.end_date, warmup_bars=15,
        )

        result.symbols_loaded = len(ohlcv_4h)
        result.progress = 25.0

        if not ohlcv_4h:
            result.status = "error"
            result.error = "Failed to fetch any 4h data"
            return

        # Fetch Fear & Greed history
        fear_greed: Dict[str, int] = {}
        if config.use_fear_greed:
            # Calculate days between start and end
            start_ms = _date_to_ms(config.start_date)
            end_ms = _date_to_ms(config.end_date)
            days = max(int((end_ms - start_ms) / (86400 * 1000)) + 30, 365)
            fear_greed = await fetch_historical_fear_greed(days=min(days, 2000))

        result.progress = 30.0

        # --- Phase B: Run replay engine (async, yields to event loop per bar) ---
        result.status = "replaying"
        valid_symbols = [s for s in symbols if s in ohlcv_4h]

        def on_progress(pct: float, msg: str):
            # Map replay progress (0-100) to result progress (30-80)
            result.progress = 30.0 + pct * 0.5

        bar_results = await run_replay(
            symbols=valid_symbols,
            ohlcv_4h=ohlcv_4h,
            ohlcv_1d=ohlcv_1d,
            ohlcv_1w=ohlcv_1w,
            fear_greed=fear_greed,
            warmup_bars=WARMUP_BARS,
            on_progress=on_progress,
        )

        result.bar_count = len(bar_results)
        result.progress = 80.0

        if not bar_results:
            result.status = "error"
            result.error = "Replay produced no results"
            return

        # --- Phase C: Position manager ---
        pm = PositionManager(config.initial_capital, valid_symbols)

        # Also track BTC buy-and-hold
        btc_sym = "BTC/USDT"
        btc_initial_price = None
        btc_equity: List[Tuple[float, float]] = []

        # Build BTC price series from raw OHLCV (more reliable than bar results)
        btc_4h = ohlcv_4h.get(btc_sym)
        btc_price_lookup: Dict[float, float] = {}
        if btc_4h is not None:
            for i in range(len(btc_4h["timestamp"])):
                btc_price_lookup[btc_4h["timestamp"][i]] = btc_4h["close"][i]

        # Group bars by timestamp for mark-to-market
        bars_by_ts: Dict[float, List[BarResult]] = {}
        for b in bar_results:
            bars_by_ts.setdefault(b.timestamp, []).append(b)

        bar_count = 0
        total_bars = len(bars_by_ts)
        for ts in sorted(bars_by_ts.keys()):
            bars = bars_by_ts[ts]

            # Process each symbol's signal
            for bar in bars:
                pm.process_bar(bar)

            # Mark-to-market
            prices = {b.symbol: b.price for b in bars}
            pm.mark_to_market(ts, prices)

            # BTC benchmark (from raw OHLCV data, or from bar results)
            btc_price = btc_price_lookup.get(ts) or prices.get(btc_sym)
            if btc_price:
                if btc_initial_price is None:
                    btc_initial_price = btc_price
                btc_eq = config.initial_capital * (btc_price / btc_initial_price)
                btc_equity.append((ts, btc_eq))

            bar_count += 1
            if bar_count % 100 == 0:
                result.progress = 80.0 + (bar_count / total_bars) * 10.0
                await asyncio.sleep(0)

        # Close remaining positions
        if bar_results:
            last_ts = bar_results[-1].timestamp
            pm.close_all_at_end(last_ts)

        result.trades = pm.trades
        result.equity_curve = pm.equity_curve
        result.btc_equity_curve = btc_equity

        # Signal distribution
        sig_dist: Dict[str, int] = {}
        for b in bar_results:
            sig_dist[b.signal] = sig_dist.get(b.signal, 0) + 1
        result.signal_distribution = sig_dist

        result.progress = 90.0

        # --- Phase D: Compute metrics ---
        start_ms = _date_to_ms(config.start_date)
        end_ms = _date_to_ms(config.end_date)
        test_days = int((end_ms - start_ms) / (86400 * 1000))

        result.metrics = compute_metrics(
            pm.trades, pm.equity_curve, btc_equity, test_days,
        )

        result.condition_analysis = compute_condition_analysis(
            bar_results, pm.trades,
        )

        result.status = "complete"
        result.progress = 100.0
        result.completed_at = time.time()

        elapsed = result.completed_at - result.started_at
        logger.info(
            "Backtest %s complete: %.1f%% return (BTC: %.1f%%), %d trades, %.0fs",
            bt_id,
            result.metrics.total_return_pct,
            result.metrics.btc_return_pct,
            result.metrics.total_trades,
            elapsed,
        )

    except Exception as exc:
        logger.error("Backtest %s failed: %s", bt_id, exc, exc_info=True)
        result.status = "error"
        result.error = str(exc)
        result.completed_at = time.time()
