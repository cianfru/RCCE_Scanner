"""
RCCE Scanner API
FastAPI backend for multi-signal crypto scanning
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from scanner import cache, run_scan, get_scan_status
from models import (
    ScanResponse,
    ConsensusResponse,
    StatusResponse,
    WatchlistResponse,
    WatchlistUpdate,
    WatchlistAddRequest,
    GlobalMetricsResponse,
    SymbolSearchResult,
    SentimentResponse,
    StablecoinResponse,
    ConfluenceResponse,
    PositioningResponse,
    BacktestRequest,
    WalkForwardRequest,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exchange symbol cache for search (lazy-loaded)
# ---------------------------------------------------------------------------

_exchange_symbols: Optional[List[dict]] = None
_exchange_symbols_lock = asyncio.Lock()


async def _load_exchange_symbols() -> List[dict]:
    """Load available trading pairs from Binance (primary) + Bybit (fallback)."""
    global _exchange_symbols
    if _exchange_symbols is not None:
        return _exchange_symbols

    async with _exchange_symbols_lock:
        # Double-check after acquiring lock
        if _exchange_symbols is not None:
            return _exchange_symbols

        import ccxt.async_support as ccxt
        symbols = []
        seen = set()

        for exch_id in ("binance", "bybit"):
            try:
                exchange = getattr(ccxt, exch_id)({"enableRateLimit": True})
                await exchange.load_markets()
                for sym, market in exchange.markets.items():
                    if sym not in seen and market.get("quote") == "USDT" and market.get("active", True):
                        seen.add(sym)
                        symbols.append({
                            "symbol": sym,
                            "base": market.get("base", ""),
                            "quote": market.get("quote", ""),
                        })
                await exchange.close()
                logger.info("Loaded %d USDT pairs from %s", len(symbols), exch_id)
            except Exception as exc:
                logger.warning("Failed to load markets from %s: %s", exch_id, exc)

        _exchange_symbols = sorted(symbols, key=lambda x: x["symbol"])
        return _exchange_symbols


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup, trigger an initial scan and start periodic refresh."""
    # Run initial scan in background
    asyncio.create_task(_periodic_scan())
    yield


_backtest_running = False  # Flag to pause scans during backtest


async def _periodic_scan():
    """Run scans every 5 minutes. Pauses while a backtest is fetching data."""
    while True:
        if _backtest_running:
            logger.info("Scan deferred — backtest in progress")
            await asyncio.sleep(30)
            continue
        try:
            logger.info("Starting scheduled scan...")
            await run_scan(cache)
            logger.info("Scan complete.")
        except Exception as e:
            logger.error("Scan failed: %s", e)
        await asyncio.sleep(300)  # 5 minutes


app = FastAPI(title="RCCE Scanner API", version="4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Scan endpoints
# ---------------------------------------------------------------------------

@app.get("/api/scan")
async def scan(
    timeframe: str = Query("4h", description="4h or 1d"),
    regime: Optional[str] = Query(None),
    signal: Optional[str] = Query(None),
):
    """Return cached scan results, filtered by regime/signal."""
    results = cache.get_results(timeframe, regime=regime, signal=signal)
    consensus = cache.consensus.get(timeframe)
    return ScanResponse(
        results=results,
        scan_running=cache.is_scanning,
        cache_age_seconds=cache.get_cache_age(),
        consensus=consensus,
    )


@app.get("/api/consensus")
async def consensus(timeframe: str = Query("4h")):
    """Return market consensus for a timeframe."""
    c = cache.consensus.get(timeframe, {"consensus": "MIXED", "strength": 0})
    return ConsensusResponse(consensus=c["consensus"], strength=c["strength"], timeframe=timeframe)


@app.get("/api/global-metrics")
async def global_metrics():
    """Return latest global market metrics (BTC dominance, market caps)."""
    gm = cache.global_metrics
    if gm is None:
        return GlobalMetricsResponse()
    return GlobalMetricsResponse(**gm)


@app.get("/api/alt-season")
async def alt_season(timeframe: str = Query("4h")):
    """Return alt-season gauge for a timeframe."""
    gauge = cache.alt_season.get(timeframe)
    if gauge is None:
        return {"score": 0.0, "label": "COLD", "alts_up": 0, "total_alts": 0, "btc_dominance": None}
    return gauge


@app.get("/api/status")
async def status():
    return get_scan_status()


@app.post("/api/scan/refresh")
async def trigger_scan():
    """Trigger a manual scan."""
    if cache.is_scanning:
        return {"ok": False, "message": "Scan already in progress"}
    asyncio.create_task(run_scan(cache))
    return {"ok": True, "message": "Scan started"}


# ---------------------------------------------------------------------------
# Watchlist / custom ticker endpoints
# ---------------------------------------------------------------------------

@app.get("/api/watchlist")
async def get_watchlist():
    return WatchlistResponse(symbols=cache.symbols)


@app.post("/api/watchlist")
async def update_watchlist(body: WatchlistUpdate):
    """Replace the entire watchlist."""
    cache.symbols = [s.upper().replace("-", "/") for s in body.symbols]
    return {"ok": True, "count": len(cache.symbols)}


@app.post("/api/watchlist/add")
async def add_to_watchlist(body: WatchlistAddRequest):
    """Add a single symbol to the watchlist."""
    symbol = body.symbol.upper().replace("-", "/")

    # Ensure USDT quote if not specified
    if "/" not in symbol:
        symbol = f"{symbol}/USDT"

    if symbol in cache.symbols:
        return {"ok": True, "message": f"{symbol} already in watchlist", "count": len(cache.symbols)}

    # Validate symbol exists on exchange
    available = await _load_exchange_symbols()
    valid_symbols = {s["symbol"] for s in available}
    if symbol not in valid_symbols:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found on any exchange")

    cache.symbols.append(symbol)
    return {"ok": True, "message": f"Added {symbol}", "count": len(cache.symbols)}


@app.delete("/api/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str):
    """Remove a single symbol from the watchlist."""
    symbol = symbol.upper().replace("-", "/")
    if symbol not in cache.symbols:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")

    cache.symbols.remove(symbol)
    return {"ok": True, "message": f"Removed {symbol}", "count": len(cache.symbols)}


@app.get("/api/watchlist/search")
async def search_symbols(q: str = Query(..., min_length=1, description="Search query")):
    """Search available USDT trading pairs on supported exchanges."""
    available = await _load_exchange_symbols()
    query = q.upper()
    matches = [
        SymbolSearchResult(**s)
        for s in available
        if query in s["symbol"].upper() or query in s["base"].upper()
    ]
    return {"results": matches[:50]}  # Limit to 50 results


@app.post("/api/watchlist/reset")
async def reset_watchlist():
    """Reset watchlist to defaults."""
    from data_fetcher import DEFAULT_SYMBOLS
    cache.symbols = DEFAULT_SYMBOLS.copy()
    return {"ok": True, "count": len(cache.symbols)}


# ---------------------------------------------------------------------------
# New data endpoints (v4.0)
# ---------------------------------------------------------------------------

@app.get("/api/sentiment")
async def sentiment():
    """Return Fear & Greed Index."""
    s = cache.sentiment
    if s is None:
        return SentimentResponse()
    return SentimentResponse(**s)


@app.get("/api/stablecoin")
async def stablecoin():
    """Return stablecoin supply data."""
    sc = cache.stablecoin
    if sc is None:
        return StablecoinResponse()
    return StablecoinResponse(**sc)


@app.get("/api/positioning/{symbol}")
async def positioning(symbol: str):
    """Return Hyperliquid positioning data for a symbol."""
    symbol = symbol.upper().replace("-", "/")
    # Find in latest scan results
    for tf in ("4h", "1d"):
        for r in cache.results.get(tf, []):
            if r.get("symbol") == symbol and r.get("positioning"):
                return PositioningResponse(**r["positioning"])
    return PositioningResponse()


@app.get("/api/confluence/{symbol}")
async def confluence_for_symbol(symbol: str):
    """Return multi-TF confluence for a symbol."""
    symbol = symbol.upper().replace("-", "/")
    c = cache.confluence.get(symbol)
    if c is None:
        return ConfluenceResponse()
    return ConfluenceResponse(**c)


# ---------------------------------------------------------------------------
# Backtest endpoints
# ---------------------------------------------------------------------------

@app.post("/api/backtest")
async def start_backtest(body: BacktestRequest):
    """Launch a backtest in the background. Returns backtest ID for polling."""
    from backtest.runner import run_backtest, get_backtest, BacktestConfig, DEFAULT_BACKTEST_SYMBOLS

    config = BacktestConfig(
        symbols=body.symbols if body.symbols else DEFAULT_BACKTEST_SYMBOLS.copy(),
        start_date=body.start_date,
        end_date=body.end_date,
        initial_capital=body.initial_capital,
        use_confluence=body.use_confluence,
        use_fear_greed=body.use_fear_greed,
        timeframe=body.timeframe,
        leverage=body.leverage,
    )

    # Pause live scanner during backtest to avoid event loop contention
    global _backtest_running
    _backtest_running = True

    # Wait for any in-progress scan to finish before starting
    wait_count = 0
    while cache.is_scanning and wait_count < 300:
        await asyncio.sleep(1)
        wait_count += 1

    bt_id = await run_backtest(config)

    # Monitor and re-enable scanner when backtest finishes
    async def _wait_for_completion():
        global _backtest_running
        while True:
            await asyncio.sleep(5)
            result = get_backtest(bt_id)
            if result is None or result.status in ("complete", "error"):
                _backtest_running = False
                logger.info("Backtest %s finished, resuming live scanner", bt_id)
                break

    asyncio.create_task(_wait_for_completion())
    return {"id": bt_id, "status": "started"}


@app.get("/api/backtest/{bt_id}")
async def get_backtest_status(bt_id: str):
    """Get backtest status and results."""
    from backtest.runner import get_backtest
    from dataclasses import asdict

    result = get_backtest(bt_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest not found")

    # Build response
    resp = {
        "id": result.id,
        "status": result.status,
        "progress": result.progress,
        "error": result.error,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "bar_count": result.bar_count,
        "symbols_loaded": result.symbols_loaded,
        "signal_distribution": result.signal_distribution,
    }

    if result.config:
        resp["config"] = {
            "symbols": result.config.symbols,
            "start_date": result.config.start_date,
            "end_date": result.config.end_date,
            "initial_capital": result.config.initial_capital,
        }

    if result.status == "complete" and result.metrics:
        m = result.metrics
        resp["metrics"] = {
            "total_return_pct": round(m.total_return_pct, 2),
            "btc_return_pct": round(m.btc_return_pct, 2),
            "alpha_pct": round(m.alpha_pct, 2),
            "annualized_return_pct": round(m.annualized_return_pct, 2),
            "max_drawdown_pct": round(m.max_drawdown_pct, 2),
            "sharpe_ratio": round(m.sharpe_ratio, 3),
            "sortino_ratio": round(m.sortino_ratio, 3),
            "calmar_ratio": round(m.calmar_ratio, 3),
            "win_rate": round(m.win_rate, 1),
            "profit_factor": round(m.profit_factor, 2) if m.profit_factor != float("inf") else 999.0,
            "total_trades": m.total_trades,
            "avg_bars_held": round(m.avg_bars_held, 1),
            "avg_trade_return_pct": round(m.avg_trade_return_pct, 2),
            "best_trade_pct": round(m.best_trade_pct, 2),
            "worst_trade_pct": round(m.worst_trade_pct, 2),
            "avg_win_pct": round(m.avg_win_pct, 2),
            "avg_loss_pct": round(m.avg_loss_pct, 2),
        }

        # Signal stats
        resp["signal_stats"] = {
            sig: {
                "count": s.count,
                "wins": s.wins,
                "losses": s.losses,
                "win_rate": round(s.win_rate, 1),
                "avg_return_pct": round(s.avg_return_pct, 2),
                "avg_bars_held": round(s.avg_bars_held, 1),
                "total_pnl_pct": round(s.total_pnl_pct, 2),
            }
            for sig, s in m.signal_stats.items()
        }

        # Condition analysis
        resp["condition_analysis"] = [
            {
                "name": ca.condition_name,
                "times_true": ca.times_true,
                "times_false": ca.times_false,
                "avg_return_true": ca.avg_return_when_true,
                "avg_return_false": ca.avg_return_when_false,
                "predictive_value": ca.predictive_value,
            }
            for ca in result.condition_analysis
        ]

        # Trades (limited to last 200 for payload size)
        resp["trades"] = [
            {
                "symbol": t.symbol,
                "entry_signal": t.entry_signal,
                "exit_signal": t.exit_signal,
                "entry_price": round(t.entry_price, 4),
                "exit_price": round(t.exit_price, 4) if t.exit_price else None,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "pnl_pct": round(t.pnl_pct, 2) if t.pnl_pct is not None else None,
                "pnl_usd": round(t.pnl_usd, 2) if t.pnl_usd is not None else None,
                "bars_held": t.bars_held,
                "size_pct": round(t.size_pct * 100, 0),
                "confluence": t.confluence_at_entry,
            }
            for t in result.trades[-200:]
        ]

        # Equity curves (sample to max ~500 points for chart)
        resp["equity_curve"] = _sample_curve(result.equity_curve, 500)
        resp["btc_equity_curve"] = _sample_curve(result.btc_equity_curve, 500)

    return resp


@app.get("/api/backtests")
async def list_all_backtests():
    """List all backtests (running + completed)."""
    from backtest.runner import list_backtests
    return {"backtests": list_backtests()}


# ---------------------------------------------------------------------------
# Walk-forward validation endpoints
# ---------------------------------------------------------------------------

@app.post("/api/walkforward")
async def start_walkforward(body: WalkForwardRequest):
    """Launch walk-forward validation. Returns ID for polling."""
    from backtest.walkforward import run_walkforward, WalkForwardConfig, get_walkforward
    from backtest.runner import DEFAULT_BACKTEST_SYMBOLS

    config = WalkForwardConfig(
        symbols=body.symbols if body.symbols else DEFAULT_BACKTEST_SYMBOLS.copy(),
        start_date=body.start_date,
        end_date=body.end_date,
        initial_capital=body.initial_capital,
        use_confluence=body.use_confluence,
        use_fear_greed=body.use_fear_greed,
        timeframe=body.timeframe,
        leverage=body.leverage,
        test_window_days=body.test_window_days,
        step_days=body.step_days,
        warmup_days=body.warmup_days,
    )

    # Pause live scanner
    global _backtest_running
    _backtest_running = True

    wait_count = 0
    while cache.is_scanning and wait_count < 300:
        await asyncio.sleep(1)
        wait_count += 1

    wf_id = await run_walkforward(config)

    # Monitor and re-enable scanner when done
    async def _wait_for_completion():
        global _backtest_running
        while True:
            await asyncio.sleep(5)
            result = get_walkforward(wf_id)
            if result is None or result.status in ("complete", "error"):
                _backtest_running = False
                logger.info("Walk-forward %s finished, resuming live scanner", wf_id)
                break

    asyncio.create_task(_wait_for_completion())
    return {"id": wf_id, "status": "started"}


@app.get("/api/walkforward/{wf_id}")
async def get_walkforward_status(wf_id: str):
    """Get walk-forward status and results."""
    from backtest.walkforward import get_walkforward

    result = get_walkforward(wf_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Walk-forward not found")

    resp = {
        "id": result.id,
        "status": result.status,
        "progress": result.progress,
        "current_window": result.current_window,
        "total_windows": result.total_windows,
        "error": result.error,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
    }

    if result.config:
        resp["config"] = {
            "symbols": result.config.symbols,
            "start_date": result.config.start_date,
            "end_date": result.config.end_date,
            "initial_capital": result.config.initial_capital,
            "timeframe": result.config.timeframe,
            "leverage": result.config.leverage,
            "test_window_days": result.config.test_window_days,
            "step_days": result.config.step_days,
        }

    if result.status == "complete":
        # Per-window summaries
        resp["windows"] = []
        for wr in result.window_results:
            w_data = {
                "index": wr.window_index,
                "test_start": wr.test_start,
                "test_end": wr.test_end,
                "warmup_start": wr.warmup_start,
                "bar_count": wr.bar_count,
                "bmsb_blocked_pct": round(wr.bmsb_blocked_pct, 1),
                "signal_distribution": wr.signal_distribution,
            }
            if wr.metrics:
                w_data["metrics"] = _format_metrics(wr.metrics)
            resp["windows"].append(w_data)

        # Aggregate metrics
        if result.aggregate_metrics:
            resp["aggregate_metrics"] = _format_metrics(result.aggregate_metrics)

        # Full-period metrics
        if result.full_period_metrics:
            resp["full_period_metrics"] = _format_metrics(result.full_period_metrics)

        # Overfitting analysis
        resp["overfitting_analysis"] = {
            "overfitting_score": round(result.overfitting_score, 3) if result.overfitting_score is not None else None,
            "consistency_score": round(result.consistency_score, 3) if result.consistency_score is not None else None,
            "sharpe_stability": round(result.sharpe_stability, 3) if result.sharpe_stability is not None else None,
        }

        # Equity curves
        resp["stitched_equity_curve"] = _sample_curve(result.stitched_equity_curve, 500)
        resp["full_equity_curve"] = _sample_curve(result.full_equity_curve, 500)
        resp["btc_equity_curve"] = _sample_curve(result.btc_equity_curve, 500)

    return resp


@app.get("/api/walkforwards")
async def list_all_walkforwards():
    """List all walk-forward runs."""
    from backtest.walkforward import list_walkforwards
    return {"walkforwards": list_walkforwards()}


def _format_metrics(m) -> dict:
    """Format a BacktestMetrics object for JSON response."""
    return {
        "total_return_pct": round(m.total_return_pct, 2),
        "btc_return_pct": round(m.btc_return_pct, 2),
        "alpha_pct": round(m.alpha_pct, 2),
        "annualized_return_pct": round(m.annualized_return_pct, 2),
        "max_drawdown_pct": round(m.max_drawdown_pct, 2),
        "sharpe_ratio": round(m.sharpe_ratio, 3),
        "sortino_ratio": round(m.sortino_ratio, 3),
        "calmar_ratio": round(m.calmar_ratio, 3),
        "win_rate": round(m.win_rate, 1),
        "profit_factor": round(m.profit_factor, 2) if m.profit_factor != float("inf") else 999.0,
        "total_trades": m.total_trades,
        "avg_bars_held": round(m.avg_bars_held, 1),
        "avg_trade_return_pct": round(m.avg_trade_return_pct, 2),
        "best_trade_pct": round(m.best_trade_pct, 2),
        "worst_trade_pct": round(m.worst_trade_pct, 2),
        "avg_win_pct": round(m.avg_win_pct, 2),
        "avg_loss_pct": round(m.avg_loss_pct, 2),
    }


def _sample_curve(curve: list, max_points: int) -> list:
    """Downsample an equity curve to max_points for JSON payload."""
    if len(curve) <= max_points:
        return [[ts, round(eq, 2)] for ts, eq in curve]
    step = max(1, len(curve) // max_points)
    sampled = curve[::step]
    # Always include the last point
    if sampled[-1] != curve[-1]:
        sampled.append(curve[-1])
    return [[ts, round(eq, 2)] for ts, eq in sampled]


@app.get("/health")
async def health():
    return {"ok": True}
