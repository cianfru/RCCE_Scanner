"""
RCCE Scanner API
FastAPI backend for multi-signal crypto scanning
"""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

# Load .env file if present (before any env var reads)
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

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
    ExecutorInitRequest,
    ExecutorStatusResponse,
    ExecutorTradeResponse,
    WhitelistUpdate,
    WhitelistAddRequest,
    PortfolioGroupResponse,
    PortfolioGroupCreate,
    PortfolioGroupUpdate,
    PortfolioGroupAddSymbol,
    PortfolioGroupReorder,
    WhaleTokenAddRequest,
    WhaleWalletLabelRequest,
)
from portfolio_groups import PortfolioGroupManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exchange symbol cache for search (lazy-loaded)
# ---------------------------------------------------------------------------

_exchange_symbols: Optional[List[dict]] = None
_exchange_symbols_lock = asyncio.Lock()


async def _load_exchange_symbols() -> List[dict]:
    """Load available trading pairs from CEXes + Hyperliquid, tracking which exchanges list each."""
    global _exchange_symbols
    if _exchange_symbols is not None:
        return _exchange_symbols

    async with _exchange_symbols_lock:
        # Double-check after acquiring lock
        if _exchange_symbols is not None:
            return _exchange_symbols

        import ccxt.async_support as ccxt

        # {symbol: {symbol, base, quote, exchanges: [...]}}
        sym_map: dict = {}

        # CEX exchanges via CCXT
        for exch_id in ("kraken", "kucoin", "binance", "bybit"):
            try:
                exchange = getattr(ccxt, exch_id)({"enableRateLimit": True})
                await exchange.load_markets()
                for sym, market in exchange.markets.items():
                    quote = market.get("quote", "")
                    if quote in ("USDT", "BTC") and market.get("active", True):
                        if sym in sym_map:
                            sym_map[sym]["exchanges"].append(exch_id)
                        else:
                            sym_map[sym] = {
                                "symbol": sym,
                                "base": market.get("base", ""),
                                "quote": quote,
                                "exchanges": [exch_id],
                            }
                await exchange.close()
                logger.info("Loaded exchange symbols from %s (%d total so far)", exch_id, len(sym_map))
            except Exception as exc:
                logger.warning("Failed to load markets from %s: %s", exch_id, exc)

        # Hyperliquid perps (direct API, no CCXT)
        try:
            from hyperliquid_data import fetch_hyperliquid_metrics
            metrics = await fetch_hyperliquid_metrics()
            hl_added = 0
            for m in metrics.values():
                sym = f"{m.coin}/USDT"
                if sym in sym_map:
                    sym_map[sym]["exchanges"].append("hyperliquid")
                else:
                    sym_map[sym] = {
                        "symbol": sym,
                        "base": m.coin,
                        "quote": "USDT",
                        "exchanges": ["hyperliquid"],
                    }
                    hl_added += 1
            logger.info("Added %d Hyperliquid-only symbols (%d total)", hl_added, len(sym_map))
        except Exception as exc:
            logger.warning("Failed to load Hyperliquid symbols: %s", exc)

        _exchange_symbols = sorted(sym_map.values(), key=lambda x: x["symbol"])
        return _exchange_symbols


def _sync_cache_symbols() -> None:
    """Set cache.symbols to the union of all portfolio groups."""
    mgr = PortfolioGroupManager.get()
    cache.symbols = mgr.get_union_symbols()
    logger.info("Cache symbols synced: %d symbols from %d groups", len(cache.symbols), len(mgr.groups))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup, load portfolio groups and start periodic refresh."""
    _sync_cache_symbols()

    # Initialize signal log DB
    try:
        from signal_log import SignalLog
        await SignalLog.get().init()
    except Exception as e:
        logger.warning("Signal log init failed (non-fatal): %s", e)

    asyncio.create_task(_periodic_scan())
    asyncio.create_task(_periodic_whale_poll())
    yield


_backtest_running = False  # Flag to pause scans during backtest


async def _periodic_scan():
    """Run scans every 5 minutes. Pauses while a backtest is fetching data."""
    global _backtest_running
    _executor_auto_started = False
    _backtest_defer_count = 0
    while True:
        if _backtest_running:
            _backtest_defer_count += 1
            # Safety valve: if deferred 40+ cycles (20 min) with no active backtest, force reset
            if _backtest_defer_count > 40:
                from backtest.runner import list_backtests
                active = any(
                    bt["status"] in ("pending", "fetching", "replaying")
                    for bt in list_backtests()
                )
                if not active:
                    logger.warning("_backtest_running stuck (no active backtest) — force resetting")
                    _backtest_running = False
                    _backtest_defer_count = 0
                    continue
            logger.info("Scan deferred — backtest in progress (defer #%d)", _backtest_defer_count)
            await asyncio.sleep(30)
            continue
        _backtest_defer_count = 0
        try:
            logger.info("Starting scheduled scan...")
            await run_scan(cache)
            logger.info("Scan complete.")

            # Update signal outcomes with current prices
            try:
                from signal_log import SignalLog
                sig_log = SignalLog.get()
                # Build {symbol: price} from latest 4h results
                current_prices = {
                    r["symbol"]: r["price"]
                    for r in cache.results.get("4h", [])
                    if r.get("price")
                }
                if current_prices:
                    await sig_log.update_outcomes(current_prices)
            except Exception:
                logger.debug("Signal outcome update failed (non-fatal)")

            # Auto-initialize executor after first successful scan
            if not _executor_auto_started:
                _executor_auto_started = True
                await _auto_init_executor()
        except Exception as e:
            logger.error("Scan failed: %s", e)
        await asyncio.sleep(300)  # 5 minutes


async def _auto_init_executor():
    """Auto-initialize and enable the executor after first scan.

    This ensures the executor is always running after a Railway redeploy
    without requiring manual "Initialize" button clicks.
    """
    try:
        from executor import init_executor, get_executor

        executor = get_executor()
        if executor and executor.initialized:
            logger.info("Executor already initialized — skipping auto-init")
            return

        logger.info("Auto-initializing executor (paper mode)...")
        executor = await init_executor(
            mode="paper",
            balance=10000.0,
            scanner_symbols=cache.symbols,
        )
        executor.enabled = True
        logger.info(
            "Executor auto-initialized and enabled: %d pairs available",
            len(executor.pair_map),
        )
    except Exception as e:
        logger.warning("Failed to auto-initialize executor: %s (non-fatal)", e)


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
    """Search available USDT and BTC trading pairs on supported exchanges."""
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
    """Reset watchlist to defaults (25 symbols)."""
    from data_fetcher import DEFAULT_SYMBOLS
    cache.symbols = DEFAULT_SYMBOLS.copy()
    return {"ok": True, "count": len(cache.symbols)}


@app.post("/api/watchlist/clear")
async def clear_watchlist():
    """Clear the entire watchlist."""
    cache.symbols = []
    return {"ok": True, "count": 0}


@app.post("/api/watchlist/full")
async def full_watchlist():
    """Load the full 65-symbol preset."""
    from data_fetcher import FULL_SYMBOLS
    cache.symbols = FULL_SYMBOLS.copy()
    return {"ok": True, "count": len(cache.symbols)}


# ---------------------------------------------------------------------------
# Portfolio group endpoints
# ---------------------------------------------------------------------------

@app.get("/api/groups")
async def list_groups():
    """List all portfolio groups."""
    mgr = PortfolioGroupManager.get()
    return [
        PortfolioGroupResponse(**{
            "id": g.id, "name": g.name, "symbols": g.symbols,
            "color": g.color, "order": g.order, "pinned": g.pinned,
        })
        for g in mgr.get_all()
    ]


@app.post("/api/groups")
async def create_group(body: PortfolioGroupCreate):
    """Create a new portfolio group."""
    mgr = PortfolioGroupManager.get()
    group = mgr.create_group(name=body.name, symbols=body.symbols, color=body.color)
    _sync_cache_symbols()
    return PortfolioGroupResponse(**{
        "id": group.id, "name": group.name, "symbols": group.symbols,
        "color": group.color, "order": group.order, "pinned": group.pinned,
    })


@app.put("/api/groups/{group_id}")
async def update_group(group_id: str, body: PortfolioGroupUpdate):
    """Update a group's name and/or color."""
    mgr = PortfolioGroupManager.get()
    group = mgr.update_group(group_id, name=body.name, color=body.color)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return PortfolioGroupResponse(**{
        "id": group.id, "name": group.name, "symbols": group.symbols,
        "color": group.color, "order": group.order, "pinned": group.pinned,
    })


@app.delete("/api/groups/{group_id}")
async def delete_group(group_id: str):
    """Delete a portfolio group. Pinned groups (Main, BTC) cannot be deleted."""
    mgr = PortfolioGroupManager.get()
    group = mgr.get_by_id(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.pinned:
        raise HTTPException(status_code=400, detail="Cannot delete pinned group")
    mgr.delete_group(group_id)
    _sync_cache_symbols()
    return {"ok": True}


@app.post("/api/groups/{group_id}/symbols")
async def add_symbol_to_group(group_id: str, body: PortfolioGroupAddSymbol):
    """Add a symbol to a portfolio group."""
    mgr = PortfolioGroupManager.get()
    group = mgr.add_symbol(group_id, body.symbol)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    _sync_cache_symbols()
    return PortfolioGroupResponse(**{
        "id": group.id, "name": group.name, "symbols": group.symbols,
        "color": group.color, "order": group.order, "pinned": group.pinned,
    })


@app.post("/api/groups/{group_id}/symbols/batch")
async def add_symbols_batch(group_id: str, body: dict):
    """Add multiple symbols to a group in one call."""
    symbols = body.get("symbols", [])
    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")
    mgr = PortfolioGroupManager.get()
    group = mgr.add_symbols_batch(group_id, symbols)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    _sync_cache_symbols()
    return PortfolioGroupResponse(**{
        "id": group.id, "name": group.name, "symbols": group.symbols,
        "color": group.color, "order": group.order, "pinned": group.pinned,
    })


@app.delete("/api/groups/{group_id}/symbols/{symbol:path}")
async def remove_symbol_from_group(group_id: str, symbol: str):
    """Remove a symbol from a portfolio group."""
    mgr = PortfolioGroupManager.get()
    symbol = symbol.upper().replace("-", "/")
    group = mgr.remove_symbol(group_id, symbol)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    _sync_cache_symbols()
    return PortfolioGroupResponse(**{
        "id": group.id, "name": group.name, "symbols": group.symbols,
        "color": group.color, "order": group.order, "pinned": group.pinned,
    })


@app.post("/api/groups/reorder")
async def reorder_groups(body: PortfolioGroupReorder):
    """Reorder portfolio group tabs."""
    mgr = PortfolioGroupManager.get()
    mgr.reorder(body.order)
    return {"ok": True}


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
    """Return positioning data for a symbol (Binance / Hyperliquid)."""
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
# Chart data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/chart/{symbol:path}")
async def chart_data(
    symbol: str,
    timeframe: str = Query("1d", description="4h or 1d"),
    limit: int = Query(365, description="Number of candles"),
):
    """Return OHLCV + BMSB overlay data for charting."""
    from data_fetcher import fetch_ohlcv
    from engines.heatmap_engine import compute_bmsb_series
    from engines.cto_engine import compute_cto_series
    import numpy as np

    symbol = symbol.upper().replace("-", "/")

    # More history: 365 for 1d (~1yr), 500 for 4h (~83 days)
    effective_limit = min(limit, 500)
    ohlcv = await fetch_ohlcv(symbol, timeframe, limit=effective_limit)
    if ohlcv is None:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    # Candle timestamps in unix seconds
    candle_times = [int(ohlcv["timestamp"][i] / 1000) for i in range(len(ohlcv["timestamp"]))]

    # Build candle + volume arrays
    candles = [
        {
            "time": candle_times[i],
            "open": round(float(ohlcv["open"][i]), 6),
            "high": round(float(ohlcv["high"][i]), 6),
            "low": round(float(ohlcv["low"][i]), 6),
            "close": round(float(ohlcv["close"][i]), 6),
        }
        for i in range(len(ohlcv["timestamp"]))
    ]

    volume = [
        {
            "time": candle_times[i],
            "value": round(float(ohlcv["volume"][i]), 2),
            "color": "rgba(52,211,153,0.18)" if float(ohlcv["close"][i]) >= float(ohlcv["open"][i]) else "rgba(248,113,113,0.18)",
        }
        for i in range(len(ohlcv["timestamp"]))
    ]

    # Compute CTO Line overlay on chart-timeframe data
    cto = {"cto_fast": [], "cto_slow": []}
    try:
        cto = compute_cto_series(
            ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["timestamp"],
        )
    except Exception:
        logger.warning("CTO computation failed for %s", symbol)

    # Compute BMSB series from weekly data
    bmsb = {"mid": [], "ema": [], "sma": []}
    try:
        weekly = await fetch_ohlcv(symbol, "1w", limit=250)
        if weekly is not None:
            w_close = np.asarray(weekly["close"], dtype=np.float64)
            w_ts = np.asarray(weekly["timestamp"], dtype=np.float64)
            bmsb = compute_bmsb_series(w_close, w_ts)
    except Exception:
        logger.warning("BMSB computation failed for %s", symbol)

    # Interpolate weekly BMSB to match chart resolution for smooth lines
    def _interpolate(series):
        if not series or len(series) < 2:
            return series
        src_t = [p["time"] for p in series]
        src_v = [p["value"] for p in series]
        result = []
        for ts in candle_times:
            if ts < src_t[0] or ts > src_t[-1]:
                continue
            val = float(np.interp(ts, src_t, src_v))
            result.append({"time": ts, "value": round(val, 6)})
        return result

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": candles,
        "volume": volume,
        "bmsb_mid": _interpolate(bmsb["mid"]),
        "bmsb_ema": _interpolate(bmsb["ema"]),
        "bmsb_sma": _interpolate(bmsb["sma"]),
        "cto_fast": cto["cto_fast"],
        "cto_slow": cto["cto_slow"],
    }


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

    try:
        bt_id = await run_backtest(config)
    except Exception as exc:
        _backtest_running = False
        logger.error("Failed to start backtest: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # Monitor and re-enable scanner when backtest finishes
    async def _wait_for_completion():
        global _backtest_running
        try:
            timeout_count = 0
            while timeout_count < 720:  # 720 × 5s = 60 min max
                await asyncio.sleep(5)
                timeout_count += 1
                result = get_backtest(bt_id)
                if result is None or result.status in ("complete", "error"):
                    break
            else:
                logger.warning("Backtest %s: monitor timed out after 60 min", bt_id)
        except Exception as exc:
            logger.error("Backtest %s: monitor error: %s", bt_id, exc)
        finally:
            _backtest_running = False
            logger.info("Backtest %s: scanner resumed", bt_id)

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


@app.get("/api/backtest/symbols")
async def backtested_symbols():
    """Return all symbols that appear in completed backtests."""
    from backtest.runner import get_backtested_symbols
    return {"symbols": get_backtested_symbols()}


# ---------------------------------------------------------------------------
# Hyperliquid Perpetuals discovery
# ---------------------------------------------------------------------------

_hl_perps: Optional[list] = None
_hl_perps_ts: float = 0.0


@app.get("/api/perpetuals/hyperliquid")
async def hyperliquid_perpetuals():
    """Discover all active Hyperliquid perpetual contracts.

    Returns every listed perp on Hyperliquid mapped to {BASE}/USDT format.
    Also flags which ones are scannable (have OHLCV data on Binance/Bybit).
    Results are cached for 24 hours.
    """
    global _hl_perps, _hl_perps_ts

    # Return cached if fresh (24h)
    if _hl_perps is not None and (time.time() - _hl_perps_ts) < 86400:
        return {"symbols": _hl_perps, "cached": True, "count": len(_hl_perps)}

    try:
        from hyperliquid_data import fetch_hyperliquid_metrics

        # Fetch ALL Hyperliquid perps (no API key needed)
        metrics = await fetch_hyperliquid_metrics()
        symbols = sorted(f"{m.coin}/USDT" for m in metrics.values())

        _hl_perps = symbols
        _hl_perps_ts = time.time()

        logger.info("Hyperliquid perps: %d listed", len(symbols))
        return {"symbols": symbols, "cached": False, "count": len(symbols)}

    except Exception as exc:
        logger.error("Hyperliquid perps discovery failed: %s", exc)
        return {"symbols": [], "error": str(exc), "count": 0}


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

    try:
        wf_id = await run_walkforward(config)
    except Exception as exc:
        _backtest_running = False
        logger.error("Failed to start walk-forward: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # Monitor and re-enable scanner when done
    async def _wait_for_completion():
        global _backtest_running
        try:
            timeout_count = 0
            while timeout_count < 720:  # 60 min max
                await asyncio.sleep(5)
                timeout_count += 1
                result = get_walkforward(wf_id)
                if result is None or result.status in ("complete", "error"):
                    break
            else:
                logger.warning("Walk-forward %s: monitor timed out after 60 min", wf_id)
        except Exception as exc:
            logger.error("Walk-forward %s: monitor error: %s", wf_id, exc)
        finally:
            _backtest_running = False
            logger.info("Walk-forward %s: scanner resumed", wf_id)

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


# ---------------------------------------------------------------------------
# Executor endpoints (Kraken paper/live trading)
# ---------------------------------------------------------------------------

@app.post("/api/executor/init")
async def executor_init(body: ExecutorInitRequest = ExecutorInitRequest()):
    """Initialize the executor (paper or live mode).

    Discovers available Kraken pairs from the current watchlist
    and initializes the paper trading account.
    """
    from executor import init_executor

    try:
        executor = await init_executor(
            mode=body.mode,
            balance=body.balance,
            scanner_symbols=cache.symbols,
        )
        return {
            "status": "initialized",
            "mode": body.mode,
            "balance": body.balance,
            "pairs_available": len(executor.pair_map),
            "pairs": sorted(executor.pair_map.keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/executor/enable")
async def executor_enable():
    """Enable signal execution. Executor must be initialized first."""
    from executor import get_executor

    executor = get_executor()
    if not executor or not executor.initialized:
        raise HTTPException(
            status_code=400,
            detail="Executor not initialized. Call POST /api/executor/init first.",
        )
    executor.enabled = True
    executor._save_state()
    logger.info("Executor ENABLED — signals will be executed via Kraken (%s mode)", executor.mode)
    return {"status": "enabled", "mode": executor.mode}


@app.post("/api/executor/disable")
async def executor_disable():
    """Disable signal execution. Open positions remain."""
    from executor import get_executor

    executor = get_executor()
    if not executor:
        raise HTTPException(status_code=400, detail="Executor not initialized")
    executor.enabled = False
    executor._save_state()
    logger.info("Executor DISABLED — signals will NOT be executed")
    return {"status": "disabled", "open_positions": len(executor.positions)}


@app.get("/api/executor/status")
async def executor_status():
    """Get executor status: mode, positions, PnL, last signals."""
    from executor import get_executor

    executor = get_executor()
    if not executor:
        return ExecutorStatusResponse()

    status = await executor.get_status()
    return status


@app.get("/api/executor/trades")
async def executor_trades():
    """Get trade history from the executor."""
    from executor import get_executor

    executor = get_executor()
    if not executor:
        return {"trades": []}

    return {"trades": executor.get_trades()}


@app.get("/api/executor/portfolio")
async def executor_portfolio():
    """Get current portfolio from trading engine."""
    from executor import get_executor

    executor = get_executor()
    if not executor or not executor.initialized:
        return {"error": "Executor not initialized"}

    try:
        portfolio = executor.engine.get_portfolio() if executor.engine else {}
        recent_trades = executor.get_trades()[-20:]
        return {
            "portfolio": portfolio,
            "recent_trades": recent_trades,
            "mode": executor.mode,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/executor/reset")
async def executor_reset():
    """Reset paper trading account and clear all state."""
    from executor import get_executor

    executor = get_executor()
    if not executor:
        raise HTTPException(status_code=400, detail="Executor not initialized")

    result = await executor.reset()
    return result


# ---------- Executor whitelist ----------

@app.get("/api/executor/whitelist")
async def executor_whitelist():
    """Get current executor whitelist and available pairs."""
    from executor import get_executor

    executor = get_executor()
    if not executor:
        raise HTTPException(status_code=400, detail="Executor not initialized")

    return executor.get_whitelist()


@app.post("/api/executor/whitelist")
async def executor_set_whitelist(body: WhitelistUpdate):
    """Set the full executor whitelist."""
    from executor import get_executor

    executor = get_executor()
    if not executor:
        raise HTTPException(status_code=400, detail="Executor not initialized")

    return executor.set_whitelist(body.symbols)


@app.post("/api/executor/whitelist/add")
async def executor_add_whitelist(body: WhitelistAddRequest):
    """Add a single symbol to the executor whitelist."""
    from executor import get_executor

    executor = get_executor()
    if not executor:
        raise HTTPException(status_code=400, detail="Executor not initialized")

    return executor.add_to_whitelist(body.symbol)


@app.delete("/api/executor/whitelist/{symbol:path}")
async def executor_remove_whitelist(symbol: str):
    """Remove a symbol from the executor whitelist."""
    from executor import get_executor

    executor = get_executor()
    if not executor:
        raise HTTPException(status_code=400, detail="Executor not initialized")

    symbol = symbol.upper().replace("-", "/")
    return executor.remove_from_whitelist(symbol)


# ---------------------------------------------------------------------------
# On-chain whale tracking
# ---------------------------------------------------------------------------

_whale_tracker = None


def _get_whale_tracker():
    global _whale_tracker
    if _whale_tracker is None:
        from onchain import WhaleTracker
        _whale_tracker = WhaleTracker()
        _whale_tracker.init_fetchers()
    return _whale_tracker


async def _ensure_whale_db():
    """Initialize snapshot DB (idempotent — safe to call multiple times)."""
    tracker = _get_whale_tracker()
    if tracker._snapshot_db is None:
        await tracker.init_db()


async def _periodic_whale_poll():
    """Poll on-chain whale data every 2 minutes (separate from main scan)."""
    await asyncio.sleep(30)  # let main scan start first
    tracker = _get_whale_tracker()
    # Initialize snapshot DB on first poll
    await _ensure_whale_db()
    while True:
        try:
            if tracker.store.get_tracked_tokens():
                await tracker.poll_all()
                await tracker.poll_trending()
                # Solana holder lists less frequently (every 10 min)
                if time.time() - tracker._last_holder_poll > 600:
                    await tracker.poll_holders_solana()
                logger.info(
                    "Whale poll complete: %d tokens, %d transfers cached",
                    len(tracker.store.tracked_tokens),
                    sum(len(v) for v in tracker._transfer_cache.values()),
                )
        except Exception as e:
            logger.error("Whale poll failed: %s", e)
        await asyncio.sleep(120)  # 2 minutes


# ---------------------------------------------------------------------------
# Signal Log endpoints
# ---------------------------------------------------------------------------

@app.get("/api/signals/history")
async def signal_history(
    timeframe: str = Query("4h"),
    symbol: Optional[str] = Query(None),
    signal: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated signal event history."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    events = await sig_log.get_history(
        timeframe=timeframe,
        symbol=symbol,
        signal_type=signal,
        limit=limit,
        offset=offset,
    )
    total = await sig_log.get_history_count(
        timeframe=timeframe,
        symbol=symbol,
        signal_type=signal,
    )
    return {"events": events, "total": total, "limit": limit, "offset": offset}


@app.get("/api/signals/scorecard")
async def signal_scorecard(
    timeframe: str = Query("4h"),
):
    """Per-signal-type win-rate scorecard."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    cards = await sig_log.get_scorecard(timeframe=timeframe)
    return {"cards": cards, "timeframe": timeframe}


@app.get("/api/signals/recent")
async def signal_recent_changes(
    timeframe: str = Query("4h"),
    limit: int = Query(20, ge=1, le=100),
):
    """Latest signal transitions."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    changes = await sig_log.get_recent_changes(timeframe=timeframe, limit=limit)
    return {"changes": changes, "timeframe": timeframe}


# ---------------------------------------------------------------------------
# AIXBT Entry Confirmation
# ---------------------------------------------------------------------------

@app.get("/api/aixbt/status")
async def aixbt_status():
    """Check AIXBT integration status: key availability, wallet, expiry."""
    from aixbt_client import _get_api_key, _KEY_FILE
    import json as _json

    has_env_key = bool(os.environ.get("AIXBT_API_KEY", "").strip())
    has_wallet = bool(os.environ.get("AIXBT_WALLET_KEY", "").strip())

    key_file_info = None
    if _KEY_FILE.exists():
        try:
            data = _json.loads(_KEY_FILE.read_text())
            key_file_info = {
                "expires_at": data.get("expires_at"),
                "duration": data.get("duration"),
                "cost": data.get("cost"),
                "valid": data.get("expires_ts", 0) > time.time() * 1000,
            }
        except Exception:
            pass

    active_key = _get_api_key()

    # x402 diagnostics
    x402_diag = {}
    if has_wallet and not active_key:
        try:
            from eth_account import Account
            x402_diag["eth_account"] = "ok"
        except ImportError as e:
            x402_diag["eth_account"] = f"MISSING: {e}"
        try:
            from x402 import x402ClientSync
            x402_diag["x402_client"] = "ok"
        except ImportError as e:
            x402_diag["x402_client"] = f"MISSING: {e}"
        try:
            from x402.mechanisms.evm import EthAccountSigner
            from x402.mechanisms.evm.exact.register import register_exact_evm_client
            x402_diag["x402_evm"] = "ok"
        except ImportError as e:
            x402_diag["x402_evm"] = f"MISSING: {e}"
        try:
            from x402.http.clients import x402_requests
            x402_diag["x402_requests"] = "ok"
        except ImportError as e:
            x402_diag["x402_requests"] = f"MISSING: {e}"

    return {
        "connected": bool(active_key),
        "auth_method": "api_key" if has_env_key else ("x402" if has_wallet else "none"),
        "has_env_key": has_env_key,
        "has_wallet": has_wallet,
        "key_file": key_file_info,
        "x402_diagnostics": x402_diag or None,
        "setup_instructions": (
            "Set AIXBT_WALLET_KEY in .env with a Base wallet private key funded with USDC. "
            "Run: cd backend/x402 && node buy-key.js --generate-wallet"
        ) if not active_key else None,
    }


@app.get("/api/confirm/{symbol}")
async def confirm_entry(
    symbol: str,
    timeframe: str = Query("4h"),
):
    """
    Entry confirmation: combines scanner signal + AIXBT social intelligence.
    Returns a GO / LEAN_GO / WAIT / NO / EXIT verdict.
    Used by the rcce-entry-confirm Claude Skill.
    """
    from aixbt_client import build_confirmation_report

    # Find scanner data for this symbol
    scanner_data = None
    results = cache.results.get(timeframe, [])
    # Normalize input: "BTC" → match "BTC/USDT", "SOL" → "SOL/USDT"
    sym_upper = symbol.upper().replace("/USDT", "").replace("USDT", "")
    for r in results:
        r_base = r.get("symbol", "").replace("/USDT", "")
        if r_base == sym_upper:
            scanner_data = r
            break

    if not scanner_data:
        # Still run AIXBT even without scanner data
        report = await build_confirmation_report(symbol)
        report["scanner"] = None
        report["verdict"]["reason"] = (
            f"Symbol {symbol} not in current scan — AIXBT only. "
            + report["verdict"].get("reason", "")
        )
        return report

    return await build_confirmation_report(symbol, scanner_data=scanner_data)


@app.get("/api/confirm")
async def confirm_entry_list(
    timeframe: str = Query("4h"),
    signals_only: bool = Query(True),
):
    """
    Batch confirmation for all symbols with active entry signals.
    If signals_only=True, only confirms symbols with entry signals.
    """
    from aixbt_client import build_confirmation_report

    results = cache.results.get(timeframe, [])
    entry_signals = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}

    targets = []
    for r in results:
        if signals_only and r.get("signal") not in entry_signals:
            continue
        targets.append(r)

    if not targets:
        return {"confirmations": [], "message": "No active entry signals"}

    # Run confirmations concurrently
    tasks = [
        build_confirmation_report(t["symbol"], scanner_data=t)
        for t in targets[:10]  # Cap at 10 to stay within rate limits
    ]
    reports = await asyncio.gather(*tasks, return_exceptions=True)

    confirmations = []
    for report in reports:
        if isinstance(report, Exception):
            continue
        confirmations.append(report)

    return {"confirmations": confirmations, "count": len(confirmations)}


# ---------------------------------------------------------------------------
# Whale tracker endpoints
# ---------------------------------------------------------------------------

@app.get("/api/whales/status")
async def whale_status():
    """Whale tracker health and chain availability."""
    return _get_whale_tracker().get_status()


@app.get("/api/whales/tokens")
async def whale_tokens():
    """List all tracked tokens."""
    from dataclasses import asdict
    tracker = _get_whale_tracker()
    return [asdict(t) for t in tracker.store.get_tracked_tokens()]


@app.post("/api/whales/tokens")
async def whale_add_token(body: WhaleTokenAddRequest):
    """Add a token to track by chain + contract address."""
    tracker = _get_whale_tracker()
    if body.chain not in tracker._active_chains:
        available = tracker._active_chains or ["none — set API keys"]
        raise HTTPException(
            status_code=400,
            detail=f"Chain '{body.chain}' not available. Active: {available}",
        )
    result = await tracker.add_token(body.chain, body.contract)
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to resolve token metadata")
    return result


@app.delete("/api/whales/tokens/{chain}/{contract:path}")
async def whale_remove_token(chain: str, contract: str):
    """Stop tracking a token."""
    tracker = _get_whale_tracker()
    removed = tracker.remove_token(chain, contract)
    return {"removed": removed}


@app.get("/api/whales/transfers")
async def whale_transfers(
    chain: Optional[str] = Query(None),
    contract: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get recent transfers, optionally filtered by chain/contract."""
    return _get_whale_tracker().get_transfers(chain, contract, limit)


@app.get("/api/whales/holders/{chain}/{contract:path}")
async def whale_holders(
    chain: str,
    contract: str,
    limit: int = Query(40, ge=1, le=100),
    min_pct: float = Query(0.0, ge=0.0, le=100.0),
):
    """Get holder data for a tracked token, enriched with balance changes."""
    await _ensure_whale_db()
    return await _get_whale_tracker().get_holders(chain, contract, limit, min_pct)


@app.get("/api/whales/alerts")
async def whale_alerts(
    chain: Optional[str] = Query(None),
    contract: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Get recent whale alerts (accumulation, distribution, large txns)."""
    return _get_whale_tracker().get_alerts(chain, contract, limit)


@app.get("/api/whales/trending")
async def whale_trending():
    """Get auto-detected trending tokens with whale activity."""
    return _get_whale_tracker().get_trending()


@app.post("/api/whales/wallet/label")
async def whale_wallet_label(body: WhaleWalletLabelRequest):
    """Tag a wallet address with a custom label."""
    tracker = _get_whale_tracker()
    tracker.store.set_wallet_label(body.chain, body.address, body.label)
    return {"ok": True}


@app.get("/api/whales/wallet/{chain}/{address}")
async def whale_wallet_activity(
    chain: str,
    address: str,
    limit: int = Query(50, ge=1, le=200),
):
    """Get a wallet's cross-token activity across all tracked tokens."""
    tracker = _get_whale_tracker()
    return tracker.get_wallet_activity(chain, address, limit)


@app.post("/api/whales/tokens/{chain}/{contract:path}/refresh-supply")
async def whale_refresh_supply(chain: str, contract: str):
    """Re-fetch total_supply for a token (useful when initial fetch failed)."""
    tracker = _get_whale_tracker()
    new_supply = await tracker.refresh_token_supply(chain, contract)
    return {"total_supply": new_supply}


@app.get("/api/whales/labels")
async def whale_labels(chain: Optional[str] = Query(None)):
    """Get all wallet labels, optionally filtered by chain."""
    return _get_whale_tracker().store.get_all_labels(chain)


@app.get("/api/whales/history/{chain}/{contract}/{address}")
async def whale_address_history(
    chain: str,
    contract: str,
    address: str,
    days: int = Query(14, ge=1, le=90),
):
    """Balance history time series for a wallet on a specific token."""
    await _ensure_whale_db()
    tracker = _get_whale_tracker()
    return await tracker.get_address_history(chain, contract, address, days)


@app.get("/health")
async def health():
    return {"ok": True}
