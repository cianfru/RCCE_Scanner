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
        load_dotenv(_env_file, override=True)
except ImportError:
    pass

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from scanner import cache, run_scan, run_rolling_scan, run_tradfi_scan, get_scan_status, \
    run_drip_scan, _run_synthesis_pass
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
    HLLeverageRequest,
    TradeLogRequest,
    TradeCloseLogRequest,
    PortfolioGroupResponse,
    PortfolioGroupCreate,
    PortfolioGroupUpdate,
    PortfolioGroupAddSymbol,
    PortfolioGroupReorder,
    WhaleTokenAddRequest,
    WhaleWalletLabelRequest,
    ChatRequest,
    ChatResponse,
    BriefingResponse,
    ModelsResponse,
    SetModelRequest,
    SetModelResponse,
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

    # Start Telegram bot (if configured)
    try:
        from telegram_bot import get_telegram_bot
        bot = get_telegram_bot()
        await bot.start()
    except Exception as e:
        logger.warning("Telegram bot init failed (non-fatal): %s", e)

    # Initialize position monitor (loads registry from disk)
    try:
        from position_monitor import PositionMonitor
        monitor = PositionMonitor.get()
        logger.info("Position monitor loaded (%d watchers)", len(monitor.watchers))
    except Exception as e:
        logger.warning("Position monitor init failed (non-fatal): %s", e)

    # Start drip scan loop (1 symbol/1s continuous) + synthesis pass (every 60s)
    asyncio.create_task(run_drip_scan(cache))
    asyncio.create_task(_periodic_scan())
    asyncio.create_task(_periodic_whale_poll())

    # Start CoinGlass drip loop (1 coin every 1.5s instead of 150 calls at once)
    try:
        from coinglass_data import run_coinglass_drip
        asyncio.create_task(run_coinglass_drip())
    except Exception as e:
        logger.warning("CoinGlass drip loop init failed (non-fatal): %s", e)

    # Start exchange derivatives shadow fetch (runs alongside CoinGlass for comparison)
    asyncio.create_task(_shadow_derivatives_loop())

    # Start HyperLens smart-money tracking loop
    try:
        from hl_intelligence import run_hyperlens_loop
        asyncio.create_task(run_hyperlens_loop())
    except Exception as e:
        logger.warning("HyperLens init failed (non-fatal): %s", e)

    yield

    # Force-save OHLCV cache on shutdown (survives redeploys)
    try:
        from data_fetcher import _ohlcv_store
        _ohlcv_store.save_to_disk(force=True)
    except Exception:
        logger.debug("OHLCV cache shutdown save failed")

    # Shutdown Telegram bot
    try:
        from telegram_bot import get_telegram_bot
        bot = get_telegram_bot()
        await bot.stop()
    except Exception:
        pass


_backtest_running = False  # Flag to pause scans during backtest


def _set_backtest_running(val: bool):
    """Set backtest flag + mirror on cache for drip loop access."""
    global _backtest_running
    _backtest_running = val
    cache._backtest_running = val


async def _shadow_derivatives_loop():
    """Shadow fetch exchange derivatives every 5 min (alongside CoinGlass).

    Logs comparison data for validation before switching from CoinGlass.
    """
    await asyncio.sleep(30)  # Wait for initial scan to populate price data
    while True:
        try:
            from exchange_derivatives_data import fetch_exchange_derivatives
            metrics, cvd, _ = await fetch_exchange_derivatives()
            logger.info(
                "Shadow derivatives: fetched %d coins, %d CVD entries",
                len(metrics), len(cvd),
            )
        except Exception as exc:
            logger.warning("Shadow derivatives fetch failed: %s", exc)
        await asyncio.sleep(5 * 60)  # Every 5 minutes


async def _periodic_scan():
    """Synthesis pass every 60s + TradFi + housekeeping.

    The drip loop (run_drip_scan) continuously populates _results_by_sym
    with raw engine results. This loop runs every 60s to:
    1. Synthesize signals (positioning, consensus, divergence, agent layer)
    2. Run TradFi scans (every 15th cycle)
    3. Update signal outcomes, position monitor, OHLCV cache
    """
    global _backtest_running
    _executor_auto_started = False
    _backtest_defer_count = 0
    _cycle = 0
    _TRADFI_EVERY = 15

    # Wait for drip loop to populate some results
    await asyncio.sleep(15)

    while True:
        if _backtest_running:
            _backtest_defer_count += 1
            if _backtest_defer_count > 40:
                from backtest.runner import list_backtests
                active = any(
                    bt["status"] in ("pending", "fetching", "replaying")
                    for bt in list_backtests()
                )
                if not active:
                    logger.warning("_backtest_running stuck (no active backtest) — force resetting")
                    _set_backtest_running(False)
                    _backtest_defer_count = 0
                    continue
            logger.info("Scan deferred — backtest in progress (defer #%d)", _backtest_defer_count)
            await asyncio.sleep(30)
            continue
        _backtest_defer_count = 0
        _cycle += 1

        try:
            # Synthesis pass — cross-symbol signals from drip results
            logger.info("Synthesis pass #%d ...", _cycle)
            await _run_synthesis_pass(cache)

            # TradFi scan (first cycle + every 15th cycle)
            if _cycle == 1 or _cycle % _TRADFI_EVERY == 0:
                try:
                    await run_tradfi_scan(cache)
                except Exception:
                    logger.warning("TradFi scan failed (non-fatal)", exc_info=True)

            # Update signal outcomes with current prices
            try:
                from signal_log import SignalLog
                sig_log = SignalLog.get()
                current_prices = {
                    r["symbol"]: r["price"]
                    for r in cache.results.get("4h", [])
                    if r.get("price")
                }
                if current_prices:
                    await sig_log.update_outcomes(current_prices)
            except Exception:
                logger.debug("Signal outcome update failed (non-fatal)")

            # Notify position watchers about regime/signal changes
            try:
                from position_monitor import PositionMonitor
                monitor = PositionMonitor.get()
                await monitor.on_scan_complete(cache.results)
            except Exception:
                logger.debug("Position monitor notification failed (non-fatal)")

            # Auto-initialize executor after first successful scan
            if not _executor_auto_started:
                _executor_auto_started = True
                await _auto_init_executor()

            # Persist OHLCV cache to disk (debounced — saves at most every 2 min)
            try:
                from data_fetcher import _ohlcv_store
                _ohlcv_store.save_to_disk()
            except Exception:
                logger.debug("OHLCV cache save failed (non-fatal)")
        except Exception as e:
            logger.error("Synthesis pass #%d failed: %s", _cycle, e)
        await asyncio.sleep(60)


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


@app.get("/api/tradfi")
async def tradfi_scan(
    timeframe: str = Query("4h", description="4h or 1d"),
    regime: Optional[str] = Query(None),
    signal: Optional[str] = Query(None),
):
    """Return cached TradFi (HIP-3) scan results."""
    items = cache.tradfi_results.get(timeframe, [])
    if regime is not None:
        regime_upper = regime.upper()
        items = [r for r in items if r.get("regime", "").upper() == regime_upper]
    if signal is not None:
        signal_upper = signal.upper()
        items = [r for r in items if r.get("signal", "").upper() == signal_upper]
    return {
        "results": items,
        "scan_running": cache.is_scanning,
        "cache_age_seconds": cache.get_cache_age(),
    }


# ── TradFi symbol management ──────────────────────────────────────────────

@app.get("/api/tradfi/symbols")
async def list_tradfi_symbols():
    """Return the current TradFi symbol list."""
    from data_fetcher import get_tradfi_symbols
    return {"symbols": get_tradfi_symbols()}


@app.post("/api/tradfi/symbols")
async def add_tradfi_sym(body: dict):
    """Add a TradFi symbol. Body: {coin, name, category, yf}"""
    from data_fetcher import add_tradfi_symbol
    coin = body.get("coin", "").strip()
    name = body.get("name", "").strip()
    category = body.get("category", "Equities").strip()
    yf = body.get("yf", "").strip()
    if not coin or not name or not yf:
        return JSONResponse({"error": "coin, name, and yf are required"}, status_code=400)
    try:
        entry = add_tradfi_symbol(coin, name, category, yf)
        return {"ok": True, "entry": entry}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


@app.delete("/api/tradfi/symbols/{coin}")
async def remove_tradfi_sym(coin: str):
    """Remove a TradFi symbol by coin ticker."""
    from data_fetcher import remove_tradfi_symbol
    removed = remove_tradfi_symbol(coin)
    if not removed:
        return JSONResponse({"error": f"{coin} not found"}, status_code=404)
    return {"ok": True}


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


@app.get("/api/ohlcv-cache/status")
async def ohlcv_cache_status():
    """Return OHLCVStore status: entries per timeframe, disk file info."""
    from data_fetcher import _ohlcv_store, _OHLCV_CACHE_PATH
    import os

    disk_info = {}
    if _OHLCV_CACHE_PATH.exists():
        stat = _OHLCV_CACHE_PATH.stat()
        disk_info = {
            "path": str(_OHLCV_CACHE_PATH),
            "size_kb": round(stat.st_size / 1024, 1),
            "age_min": round((time.time() - stat.st_mtime) / 60, 1),
        }

    tf_counts = {}
    for tf in ("4h", "1d", "1w"):
        syms = _ohlcv_store.symbols_cached(tf)
        if syms:
            # Sample bar counts
            bars = []
            for s in syms[:5]:
                cached = _ohlcv_store.get(s, tf)
                if cached:
                    bars.append(len(cached.get("close", [])))
            tf_counts[tf] = {
                "symbols": len(syms),
                "sample_bars": bars,
            }

    return {
        "total_entries": _ohlcv_store.count(),
        "timeframes": tf_counts,
        "disk": disk_info,
    }


@app.get("/api/debug/sm-test")
async def debug_sm_test():
    """Debug: test HyperLens consensus attachment."""
    try:
        from hl_intelligence import get_all_consensus
        hl = get_all_consensus()
        # Check BTC
        btc = hl.get("BTC")
        # Check what scan results have
        results_4h = cache.results.get("4h", [])
        btc_result = next((r for r in results_4h if r.get("symbol") == "BTC/USDT"), None)
        return {
            "consensus_count": len(hl),
            "consensus_keys_sample": list(hl.keys())[:10],
            "btc_consensus": {
                "trend": btc.trend if btc else None,
                "total_tracked": btc.total_tracked if btc else 0,
            } if btc else None,
            "btc_result_has_sm": "smart_money" in btc_result if btc_result else False,
            "btc_result_keys": sorted(btc_result.keys())[:10] if btc_result else [],
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/scan/refresh")
async def trigger_scan():
    """Trigger a manual scan."""
    if cache.is_scanning:
        return {"ok": False, "message": "Scan already in progress"}
    asyncio.create_task(run_scan(cache))
    return {"ok": True, "message": "Scan started"}


# ---------------------------------------------------------------------------
# Starred Favorites — TG alert filter (separate from scanner watchlist)
# ---------------------------------------------------------------------------

import favorites as fav_store  # noqa: E402 (after env/logging setup)


@app.get("/api/favorites")
async def get_favorites_endpoint():
    """Return the user's starred pairs (used to filter TG alerts)."""
    return {"symbols": sorted(fav_store.get())}


@app.post("/api/favorites/{symbol:path}")
async def add_favorite_endpoint(symbol: str):
    """Star a symbol — TG will alert on it even when not held."""
    fav_store.add(symbol)
    return {"ok": True, "symbols": sorted(fav_store.get())}


@app.delete("/api/favorites/{symbol:path}")
async def remove_favorite_endpoint(symbol: str):
    """Un-star a symbol."""
    fav_store.remove(symbol)
    return {"ok": True, "symbols": sorted(fav_store.get())}


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


@app.get("/api/coinglass/status")
async def coinglass_status():
    """Return current CoinGlass cache status (for debugging).

    Plan: Hobbyist v3.  Available: funding rates + OI for top coins.
    Unavailable: CVD, spot dominance, liquidations, long/short ratios.
    """
    from coinglass_data import get_cached_metrics
    metrics = get_cached_metrics()
    btc = metrics.get("BTC/USDT") if metrics else None
    return {
        "plan": "hobbyist_v3",
        "available": ["funding_rates", "open_interest", "oi_change_pct"],
        "unavailable": ["cvd", "spot_dominance", "liquidations", "long_short_ratio"],
        "funding_rates": {
            "cached": metrics is not None,
            "count": len(metrics) if metrics else 0,
            "btc_funding_8h_pct": round(btc.funding_rate * 100 * 8, 4) if btc else None,
            "btc_funding_regime": (
                "CROWDED_LONG"  if btc and btc.funding_rate > 0.0001 else
                "CROWDED_SHORT" if btc and btc.funding_rate < -0.0001 else
                "NEUTRAL"
            ) if btc else None,
        },
        "open_interest": {
            "btc_oi_usd_b": round(btc.open_interest_usd / 1e9, 2) if btc else None,
            "btc_oi_change_4h_pct": btc.oi_change_pct_4h if btc else None,
            "btc_oi_change_24h_pct": btc.oi_change_pct_24h if btc else None,
        },
        "api_key_set": bool(os.environ.get("COINGLASS_API_KEY")),
    }


@app.get("/api/coinglass/macro")
async def coinglass_macro():
    """Return global macro signals: BTC ETF flows + Coinbase premium index.

    Cached 1 hour.  Returns null values when CoinGlass key not set.
    """
    from coinglass_data import get_cached_macro, fetch_macro_signals
    macro = get_cached_macro()
    if macro is None:
        try:
            macro = await asyncio.wait_for(fetch_macro_signals(), timeout=10.0)
        except Exception:
            from coinglass_data import CoinglassMacro
            macro = CoinglassMacro()
    return {
        "coinbase_premium_rate": macro.coinbase_premium_rate,
        "coinbase_premium":      macro.coinbase_premium,
        "etf_flow_usd_7d":       macro.etf_flow_usd_7d,
        "etf_flow_usd_1d":       macro.etf_flow_usd_1d,
        "etf_signal":            macro.etf_signal,
        "timestamp":             macro.timestamp,
    }


@app.get("/api/market-pulse")
async def market_pulse(timeframe: str = Query("4h")):
    """One-glance market narrative: consensus + BTC regime + funding mood + ETF direction.

    Aggregates from scan cache, CoinGlass bulk metrics, and macro cache into
    a single object with a human-readable ``narrative`` string.
    """
    from coinglass_data import get_cached_macro, get_cached_metrics

    # Consensus
    cons = cache.consensus.get(timeframe, {"consensus": "MIXED", "strength": 0, "counts": {}})
    counts = cons.get("counts", {})
    total = counts.get("total", 0)
    bullish = counts.get("markup", 0) + counts.get("accum", 0)

    # BTC regime + z-score from scan results
    btc_regime, btc_zscore = "UNKNOWN", None
    for r in cache.results.get(timeframe, []):
        if r.get("symbol") in ("BTC/USDT", "BTC/USD"):
            btc_regime = r.get("regime", "UNKNOWN")
            btc_zscore = r.get("zscore")
            break

    # Funding mood: most common regime from CoinGlass bulk
    funding_mood = "UNKNOWN"
    cg_metrics = get_cached_metrics()
    if cg_metrics:
        regimes = {}
        for m in cg_metrics.values():
            fr = getattr(m, "funding_regime", None) or "NEUTRAL"
            regimes[fr] = regimes.get(fr, 0) + 1
        if regimes:
            funding_mood = max(regimes, key=regimes.get)

    # ETF + CB premium from macro cache
    macro = get_cached_macro()
    etf_7d = macro.etf_flow_usd_7d if macro else None
    cb_premium = macro.coinbase_premium_rate if macro else None

    # Build narrative parts
    parts = []
    if total > 0:
        parts.append(f"{bullish}/{total} bullish")
    if btc_regime != "UNKNOWN":
        z_str = f" z={btc_zscore:.1f}" if btc_zscore is not None else ""
        parts.append(f"BTC {btc_regime}{z_str}")
    if funding_mood != "UNKNOWN":
        parts.append(f"Funding {funding_mood.replace('_', ' ').lower()}")
    if etf_7d is not None:
        sign = "+" if etf_7d >= 0 else ""
        parts.append(f"ETF {sign}${abs(etf_7d) / 1e6:.0f}M 7d")

    return {
        "consensus": cons.get("consensus", "MIXED"),
        "strength": cons.get("strength", 0),
        "narrative": " · ".join(parts) if parts else "No data",
        "btc_regime": btc_regime,
        "btc_zscore": round(btc_zscore, 2) if btc_zscore is not None else None,
        "regime_counts": counts,
        "funding_mood": funding_mood,
        "etf_7d_net": etf_7d,
        "cb_premium": round(cb_premium, 4) if cb_premium is not None else None,
    }


@app.get("/api/signals/recent-unified")
async def signal_recent_unified(
    timeframe: str = Query("4h"),
    limit: int = Query(15, ge=1, le=50),
):
    """Unified recent changes: signal transitions + regime changes interleaved."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    events = await sig_log.get_recent_unified(timeframe=timeframe, limit=limit)
    return {"events": events, "timeframe": timeframe}


@app.get("/api/signals/heatmap")
async def signal_heatmap(
    timeframe: str = Query("4h"),
    days: int = Query(14, ge=1, le=30),
    limit: int = Query(30, ge=1, le=100),
):
    """14-day signal heatmap grid: signal state + conditions per symbol per day."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()

    # Get top N symbols by priority from current scan cache
    results = cache.results.get(timeframe, [])
    top_symbols = [
        r["symbol"]
        for r in sorted(results, key=lambda x: x.get("priority_score", 0), reverse=True)
        if r.get("symbol")
    ][:limit]

    data = await sig_log.get_signal_heatmap(
        timeframe=timeframe, days=days,
        symbols=top_symbols if top_symbols else None,
    )

    # Re-sort grid symbols by the priority order
    if top_symbols:
        ordered = [s for s in top_symbols if s in data["grid"]]
        data["symbols"] = ordered

    return data


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
    from data_fetcher import fetch_ohlcv, _ohlcv_store, _cache
    from engines.heatmap_engine import compute_bmsb_series
    from engines.cto_engine import compute_cto_series
    import numpy as np

    symbol = symbol.upper().replace("-", "/")

    # More history: 365 for 1d (~1yr), 500 for 4h (~83 days)
    effective_limit = min(limit, 500)
    ohlcv = await fetch_ohlcv(symbol, timeframe, limit=effective_limit)

    # If cache returned too few candles (e.g. cold-start with sparse data),
    # invalidate both caches and force a full refetch
    min_chart_bars = 50  # Chart needs at least 50 candles to be useful
    if ohlcv is not None and len(ohlcv.get("timestamp", [])) < min_chart_bars:
        logger.warning(
            "Chart %s/%s: only %d candles (need %d), forcing full refetch",
            symbol, timeframe, len(ohlcv.get("timestamp", [])), min_chart_bars,
        )
        _ohlcv_store.invalidate(symbol, timeframe)
        _cache.invalidate(symbol, timeframe)
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

    # Dynamic precision for sub-penny assets (MOG, SHIB etc)
    sample_price = float(candles[-1]["close"]) if candles else 1.0
    if sample_price > 0 and sample_price < 0.01:
        interp_prec = max(6, int(np.ceil(-np.log10(sample_price))) + 3)
    else:
        interp_prec = 6

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
            result.append({"time": ts, "value": round(val, interp_prec)})
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
    _set_backtest_running(True)

    # Wait for any in-progress scan to finish before starting
    wait_count = 0
    while cache.is_scanning and wait_count < 300:
        await asyncio.sleep(1)
        wait_count += 1

    try:
        bt_id = await run_backtest(config)
    except Exception as exc:
        _set_backtest_running(False)
        logger.error("Failed to start backtest: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # Monitor and re-enable scanner when backtest finishes
    async def _wait_for_completion():
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
            _set_backtest_running(False)
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

    # Return cached if fresh (1h) and has a reasonable count (>100)
    if _hl_perps is not None and len(_hl_perps) > 100 and (time.time() - _hl_perps_ts) < 3600:
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


@app.get("/api/perpetuals/hyperliquid/debug")
async def hyperliquid_perpetuals_debug():
    """Debug: bypass all caches, return raw HL perp count."""
    import aiohttp
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "metaAndAssetCtxs"},
                headers={"Content-Type": "application/json"},
            ) as resp:
                data = await resp.json()
                universe = data[0].get("universe", []) if isinstance(data, list) and len(data) >= 2 else []
                asset_ctxs = data[1] if isinstance(data, list) and len(data) >= 2 else []
                coins = [u.get("name", "") for u in universe]
                return {
                    "universe_count": len(universe),
                    "asset_ctxs_count": len(asset_ctxs),
                    "coins_sample": coins[:10],
                    "coins_total": len(coins),
                    "cached_perps_count": len(_hl_perps) if _hl_perps else 0,
                }
    except Exception as exc:
        return {"error": str(exc)}


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
    _set_backtest_running(True)

    wait_count = 0
    while cache.is_scanning and wait_count < 300:
        await asyncio.sleep(1)
        wait_count += 1

    try:
        wf_id = await run_walkforward(config)
    except Exception as exc:
        _set_backtest_running(False)
        logger.error("Failed to start walk-forward: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # Monitor and re-enable scanner when done
    async def _wait_for_completion():
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
            _set_backtest_running(False)
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
# Hyperliquid live-mode endpoints
# ---------------------------------------------------------------------------

@app.get("/api/executor/hl/account")
async def hl_account():
    """Get Hyperliquid account summary (equity, margin, positions count)."""
    from executor import get_executor
    import asyncio

    executor = get_executor()
    if not executor or not executor.initialized or executor.mode != "live":
        raise HTTPException(
            status_code=400,
            detail="Executor not in live mode. Init with mode='live' first.",
        )
    try:
        summary = await asyncio.to_thread(executor.engine.get_account_summary)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/executor/hl/positions")
async def hl_positions():
    """Get real-time Hyperliquid positions (bypasses executor state)."""
    from executor import get_executor
    import asyncio

    executor = get_executor()
    if not executor or not executor.initialized or executor.mode != "live":
        raise HTTPException(
            status_code=400,
            detail="Executor not in live mode.",
        )
    try:
        positions = await asyncio.to_thread(executor.engine.get_positions)
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/executor/hl/fills")
async def hl_fills(limit: int = Query(50, ge=1, le=500)):
    """Get recent Hyperliquid fill history."""
    from executor import get_executor
    import asyncio

    executor = get_executor()
    if not executor or not executor.initialized or executor.mode != "live":
        raise HTTPException(
            status_code=400,
            detail="Executor not in live mode.",
        )
    try:
        fills = await asyncio.to_thread(executor.engine.get_fills, limit)
        return {"fills": fills, "count": len(fills)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/executor/hl/leverage")
async def hl_set_leverage(body: HLLeverageRequest):
    """Set leverage for a specific coin on Hyperliquid."""
    from executor import get_executor
    import asyncio

    executor = get_executor()
    if not executor or not executor.initialized or executor.mode != "live":
        raise HTTPException(
            status_code=400,
            detail="Executor not in live mode.",
        )
    try:
        result = await asyncio.to_thread(
            executor.engine.set_leverage, body.coin, body.leverage, body.is_cross,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Manual Trading endpoints (wallet-signed — no private key on server)
# ---------------------------------------------------------------------------

# Standalone HL Info for read-only queries (no private key needed)
_hl_info = None

def _get_hl_info():
    global _hl_info
    if _hl_info is None:
        from hyperliquid.info import Info
        from hyperliquid.utils import constants
        _hl_info = Info(constants.MAINNET_API_URL, skip_ws=True)
    return _hl_info


@app.get("/api/trade/account")
async def trade_account(address: str = Query(..., min_length=10)):
    """Get Hyperliquid account summary for a wallet address."""
    try:
        info = _get_hl_info()
        state = await asyncio.to_thread(info.user_state, address)
        summary = state.get("marginSummary", {})
        positions = state.get("assetPositions", [])
        active = [p for p in positions if abs(float(p.get("position", {}).get("szi", 0))) > 1e-12]
        return {
            "address": address,
            "account_value": float(summary.get("accountValue", 0)),
            "total_margin_used": float(summary.get("totalMarginUsed", 0)),
            "total_ntl_pos": float(summary.get("totalNtlPos", 0)),
            "total_raw_usd": float(summary.get("totalRawUsd", 0)),
            "positions_count": len(active),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/trade/positions")
async def trade_positions(address: str = Query(..., min_length=10)):
    """Get current Hyperliquid positions for a wallet address."""
    try:
        info = _get_hl_info()
        state = await asyncio.to_thread(info.user_state, address)
        raw_positions = state.get("assetPositions", [])
        positions = []
        for ap in raw_positions:
            pos = ap.get("position", {})
            szi = float(pos.get("szi", 0))
            if abs(szi) < 1e-12:
                continue
            positions.append({
                "coin": pos.get("coin", ""),
                "side": "LONG" if szi > 0 else "SHORT",
                "size": abs(szi),
                "entry_price": float(pos.get("entryPx", 0)),
                "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                "margin_used": float(pos.get("marginUsed", 0)),
                "liquidation_px": float(pos.get("liquidationPx", 0)) if pos.get("liquidationPx") else None,
                "leverage_type": pos.get("leverage", {}).get("type", "cross"),
                "leverage_value": int(pos.get("leverage", {}).get("value", 1)),
                "return_on_equity": float(pos.get("returnOnEquity", 0)),
            })
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/trade/fills")
async def trade_fills(
    address: str = Query(..., min_length=10),
    limit: int = Query(50, ge=1, le=500),
):
    """Get recent Hyperliquid fills for a wallet address."""
    try:
        info = _get_hl_info()
        raw_fills = await asyncio.to_thread(info.user_fills, address)
        fills = []
        for f in raw_fills[:limit]:
            fills.append({
                "coin": f.get("coin", ""),
                "side": f.get("side", ""),
                "price": float(f.get("px", 0)),
                "size": float(f.get("sz", 0)),
                "time": f.get("time", 0),
                "fee": float(f.get("fee", 0)),
                "oid": f.get("oid", 0),
                "crossed": f.get("crossed", False),
            })
        return {"fills": fills, "count": len(fills)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/trade/history")
async def trade_history():
    """Get manual trade journal with stats."""
    from manual_trader import get_trade_journal
    journal = get_trade_journal()
    trades = journal.get_trade_history()
    stats = journal.get_stats()
    return {"trades": trades, "stats": stats}


@app.post("/api/trade/log")
async def trade_log(body: TradeLogRequest):
    """Log a completed trade reported by the frontend wallet."""
    from manual_trader import get_trade_journal
    journal = get_trade_journal()

    # Capture scanner signal/regime at trade time
    signal_at_trade = ""
    regime_at_trade = ""
    for r in (cache.results_4h or []):
        if r.get("symbol") == body.symbol:
            signal_at_trade = r.get("signal", "")
            regime_at_trade = r.get("regime", "")
            break

    trade = journal.log_trade(
        address=body.address,
        symbol=body.symbol,
        coin=body.coin,
        side=body.side,
        size_usd=body.size_usd,
        volume=body.volume,
        leverage=body.leverage,
        entry_price=body.entry_price,
        order_id=body.order_id,
        signal_at_trade=signal_at_trade,
        regime_at_trade=regime_at_trade,
    )
    return {"status": "ok", "trade": trade.to_dict()}


@app.post("/api/trade/log-close")
async def trade_log_close(body: TradeCloseLogRequest):
    """Log a position closure reported by the frontend wallet."""
    from manual_trader import get_trade_journal
    journal = get_trade_journal()

    trade = journal.log_close(
        symbol=body.symbol,
        exit_price=body.exit_price,
        close_order_id=body.close_order_id,
    )
    if not trade:
        raise HTTPException(status_code=404, detail=f"No open trade found for {body.symbol}")
    return {"status": "closed", "trade": trade.to_dict()}


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


@app.get("/api/signals/timeline")
async def signal_timeline(
    timeframe: str = Query("4h"),
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Unified timeline: signal + regime events interleaved by timestamp."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    events = await sig_log.get_timeline(
        timeframe=timeframe, symbol=symbol,
        limit=limit, offset=offset,
    )
    total = await sig_log.get_timeline_count(
        timeframe=timeframe, symbol=symbol,
    )
    return {"events": events, "total": total, "limit": limit, "offset": offset}


@app.get("/api/signals/regime-history")
async def signal_regime_history(
    timeframe: str = Query("4h"),
    symbol: Optional[str] = Query(None),
    regime: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated regime transition history."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    events = await sig_log.get_regime_history(
        timeframe=timeframe, symbol=symbol, regime=regime,
        limit=limit, offset=offset,
    )
    total = await sig_log.get_regime_history_count(
        timeframe=timeframe, symbol=symbol, regime=regime,
    )
    return {"events": events, "total": total, "limit": limit, "offset": offset}


@app.get("/api/signals/upgrade-scorecard")
async def signal_upgrade_scorecard(
    timeframe: str = Query("4h"),
):
    """Per-transition-type win-rate scorecard (UPGRADE/DOWNGRADE/ENTRY/EXIT)."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    data = await sig_log.get_upgrade_scorecard(timeframe=timeframe)
    return data


@app.get("/api/signals/regime-durations")
async def signal_regime_durations(
    timeframe: str = Query("4h"),
    symbol: Optional[str] = Query(None),
):
    """Average regime durations by regime type."""
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    durations = await sig_log.get_regime_durations(
        timeframe=timeframe, symbol=symbol,
    )
    return {"durations": durations, "timeframe": timeframe}


# ---------------------------------------------------------------------------
# Notifications feed (frontend toast / bell)
# ---------------------------------------------------------------------------

@app.get("/api/notifications")
async def notifications_feed(
    since: Optional[int] = Query(None),
    limit: int = Query(30, ge=1, le=100),
):
    """Recent signal + regime transitions for the notification bell.

    Parameters
    ----------
    since : int, optional
        Unix timestamp (seconds).  Only return events newer than this.
    limit : int
        Max events to return (default 30).
    """
    from signal_log import SignalLog
    sig_log = SignalLog.get()
    db = sig_log._ensure_db()

    since_filter = ""
    params: list = []
    if since is not None:
        since_filter = " AND timestamp > ?"
        params.append(since)

    # Signal transitions (exclude INITIAL — first-ever scan noise)
    sig_params = ["4h"] + params + ["4h"] + params + [limit]
    cursor = await db.execute(
        f"""SELECT * FROM (
            SELECT 'signal' AS event_type, symbol, signal AS label,
                   prev_signal AS prev_label, regime, price,
                   transition_type, timestamp
            FROM signal_events
            WHERE timeframe = ?{since_filter}
              AND transition_type IS NOT NULL
              AND transition_type != 'INITIAL'
              AND transition_type != 'LATERAL'

            UNION ALL

            SELECT 'regime' AS event_type, symbol, regime AS label,
                   prev_regime AS prev_label, regime, price,
                   NULL AS transition_type, timestamp
            FROM regime_events
            WHERE timeframe = ?{since_filter}
        )
        ORDER BY timestamp DESC
        LIMIT ?""",
        sig_params,
    )
    rows = await cursor.fetchall()
    events = [dict(r) for r in rows]
    return {"events": events, "count": len(events)}


@app.get("/api/notifications/position-warnings")
async def position_warnings(address: Optional[str] = Query(None)):
    """Real-time position warnings for the notification bell.

    Cross-references the user's HL positions against scanner data and
    generates warnings for: heat, divergence, OI trend, crowded funding,
    liquidation proximity, exhaustion, and signal conflicts.
    """
    if not address:
        return {"warnings": [], "count": 0}

    try:
        from hyperliquid_data import fetch_clearinghouse_state, parse_open_positions

        state = await fetch_clearinghouse_state(address)
        if not state:
            return {"warnings": [], "count": 0}

        positions = parse_open_positions(state)
        if not positions:
            return {"warnings": [], "count": 0}

        # Build lookup from scan cache
        results_by_symbol = {}
        for tf in ("4h", "1d"):
            for r in cache.results.get(tf, []):
                sym = r.get("symbol", "")
                if sym not in results_by_symbol:
                    results_by_symbol[sym] = r

        warnings = []
        now = int(time.time())

        for pos in positions:
            sym = pos["symbol"]
            scan = results_by_symbol.get(sym)
            if not scan:
                continue

            coin = pos["coin"]
            side = pos["side"]
            pnl = pos["unrealized_pnl"]
            heat = scan.get("heat", 0)
            signal = scan.get("signal", "WAIT")
            regime = scan.get("regime", "?")
            divergence = scan.get("divergence")
            positioning = scan.get("positioning") or {}
            oi_trend = positioning.get("oi_trend", "")
            funding_regime = positioning.get("funding_regime", "")
            exh_state = scan.get("exhaustion_state", "")
            price = scan.get("price", 0)
            liq = pos.get("liq_px", 0)

            base_info = {
                "coin": coin, "side": side, "size_usd": pos["size_usd"],
                "leverage": pos["leverage"], "pnl": pnl,
                "signal": signal, "regime": regime,
            }

            # Signal conflict
            if side == "LONG" and signal in ("TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"):
                warnings.append({
                    "type": "signal_conflict", "severity": "high",
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: {signal} signal on your LONG",
                    "detail": f"Scanner says {signal} but you're LONG ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x. PnL: ${pnl:+,.2f}",
                    **base_info,
                })

            # Heat danger
            if side == "LONG" and heat >= 85:
                warnings.append({
                    "type": "heat_danger", "severity": "high",
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: Heat {heat}/100 — blow-off risk",
                    "detail": f"Extreme heat on your LONG. Consider trimming. PnL: ${pnl:+,.2f}",
                    **base_info,
                })
            elif side == "LONG" and heat >= 70:
                warnings.append({
                    "type": "heat_warning", "severity": "medium",
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: Heat {heat}/100 — watch for trim",
                    "detail": f"Heat rising on your LONG position",
                    **base_info,
                })

            # OI adverse trend
            if side == "LONG" and oi_trend in ("SQUEEZE", "LIQUIDATING", "DECLINING"):
                sev = "high" if oi_trend in ("SQUEEZE", "LIQUIDATING") else "medium"
                warnings.append({
                    "type": "oi_warning", "severity": sev,
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: OI {oi_trend} — conviction weakening",
                    "detail": f"Open interest declining while you hold LONG. Possible reversal risk",
                    **base_info,
                })

            # Divergence
            if divergence and side == "LONG" and "BEAR" in str(divergence).upper():
                warnings.append({
                    "type": "divergence", "severity": "high",
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: Bear divergence from BTC",
                    "detail": f"{coin} in {regime} but BTC bearish. Your LONG is against the tide",
                    **base_info,
                })

            # Crowded funding
            if side == "LONG" and funding_regime == "CROWDED_LONG":
                warnings.append({
                    "type": "crowded", "severity": "medium",
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: Crowded long funding",
                    "detail": f"Extreme bullish funding = squeeze risk on your LONG",
                    **base_info,
                })

            # Liquidation proximity
            if liq > 0 and price > 0:
                liq_dist = abs(price - liq) / price * 100
                if liq_dist < 15:
                    warnings.append({
                        "type": "liquidation", "severity": "critical",
                        "symbol": sym, "timestamp": now,
                        "title": f"{coin}: Liquidation {liq_dist:.1f}% away!",
                        "detail": f"Price: ${price:.6g} | Liq: ${liq:.6g}. Add margin or reduce!",
                        **base_info,
                    })

            # Exhaustion climax (exit warning for LONG holders)
            if side == "LONG" and exh_state == "CLIMAX":
                warnings.append({
                    "type": "exhaustion", "severity": "high",
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: Exhaustion climax detected",
                    "detail": f"Volume climax on your LONG — consider taking profits",
                    **base_info,
                })

            # Floor confirmed on LONG → positive: your thesis is supported
            floor_conf = scan.get("floor_confirmed", False)
            if side == "LONG" and floor_conf:
                warnings.append({
                    "type": "floor_confirmed", "severity": "positive",
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: Exhaustion floor confirmed",
                    "detail": f"Absorption cluster + volume dry-up below BMSB. Sellers exhausted — LONG thesis supported",
                    **base_info,
                })

            # Absorption forming on LONG in bear zone → early positive signal
            is_absorb = scan.get("is_absorption", False)
            if side == "LONG" and is_absorb and exh_state == "BEAR_ZONE":
                warnings.append({
                    "type": "absorbing", "severity": "positive",
                    "symbol": sym, "timestamp": now,
                    "title": f"{coin}: Absorption forming",
                    "detail": f"Early absorption signals below BMSB. Not yet confirmed — watch for floor confirmation",
                    **base_info,
                })

        # Sort: critical > high > medium > low > positive
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "positive": 4}
        warnings.sort(key=lambda w: sev_order.get(w.get("severity", "low"), 3))

        return {"warnings": warnings, "count": len(warnings)}

    except Exception as e:
        logger.warning("Position warnings failed: %s", e)
        return {"warnings": [], "count": 0}


@app.get("/api/notifications/exhaustion-opportunities")
async def exhaustion_opportunities(address: Optional[str] = Query(None)):
    """Return coins with exhaustion-based entry signals NOT currently held.

    Fires for:
    - EXHAUSTED_FLOOR (floor_confirmed): absorption cluster + volume dry-up
    - CLIMAX on coins NOT in markdown/cap regime (capitulation reversal)
    - ABSORBING when signal is also constructive (ACCUMULATE or better)
    """
    try:
        held_syms: set = set()
        if address:
            from hyperliquid_data import fetch_clearinghouse_state, parse_open_positions
            state = await fetch_clearinghouse_state(address)
            if state:
                positions = parse_open_positions(state)
                held_syms = {p["symbol"] for p in positions}

        results_by_symbol: dict = {}
        for tf in ("4h", "1d"):
            for r in cache.results.get(tf, []):
                sym = r.get("symbol", "")
                if sym not in results_by_symbol:
                    results_by_symbol[sym] = r

        opportunities = []
        now = int(time.time())

        for sym, scan in results_by_symbol.items():
            if sym in held_syms:
                continue  # already covered by position-warnings

            exh_state    = scan.get("exhaustion_state", "")
            floor_conf   = scan.get("floor_confirmed", False)
            is_climax    = scan.get("is_climax", False)
            is_absorb    = scan.get("is_absorption", False)
            signal       = scan.get("signal", "WAIT")
            regime       = scan.get("regime", "")
            heat         = scan.get("heat", 0)
            price        = scan.get("price", 0)
            met          = scan.get("conditions_met", 0)
            total        = scan.get("conditions_total", 10)
            base_coin    = sym.split("/")[0]

            adverse_signals = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}

            if floor_conf and signal not in adverse_signals:
                opportunities.append({
                    "type": "exhaustion_floor",
                    "severity": "positive",
                    "symbol": sym, "coin": base_coin,
                    "timestamp": now,
                    "title": f"{base_coin}: Exhaustion floor confirmed",
                    "detail": (
                        f"Absorption cluster + volume dry-up below weekly BMSB. "
                        f"Signal: {signal} | Heat: {heat} | Conditions: {met}/{total}"
                    ),
                    "signal": signal, "regime": regime, "heat": heat, "price": price,
                })
            elif is_climax and regime not in ("MARKDOWN", "CAP"):
                opportunities.append({
                    "type": "climax_reversal",
                    "severity": "low",
                    "symbol": sym, "coin": base_coin,
                    "timestamp": now,
                    "title": f"{base_coin}: Downside climax bar",
                    "detail": (
                        f"Capitulation candle: wide range + long lower wick. "
                        f"Regime: {regime} | Signal: {signal} — wait for confirmation"
                    ),
                    "signal": signal, "regime": regime, "heat": heat, "price": price,
                })
            elif is_absorb and signal in ("ACCUMULATE", "REVIVAL_SEED", "LIGHT_LONG", "STRONG_LONG"):
                opportunities.append({
                    "type": "absorbing",
                    "severity": "low",
                    "symbol": sym, "coin": base_coin,
                    "timestamp": now,
                    "title": f"{base_coin}: Absorption forming",
                    "detail": (
                        f"Early exhaustion absorptions below BMSB. "
                        f"Signal: {signal} | Regime: {regime} | Not yet confirmed floor"
                    ),
                    "signal": signal, "regime": regime, "heat": heat, "price": price,
                })

        # Sort: floor_confirmed first (strongest), then climax, then absorbing
        type_order = {"exhaustion_floor": 0, "climax_reversal": 1, "absorbing": 2}
        opportunities.sort(key=lambda o: type_order.get(o["type"], 9))

        return {"opportunities": opportunities, "count": len(opportunities)}

    except Exception as e:
        logger.warning("Exhaustion opportunities failed: %s", e)
        return {"opportunities": [], "count": 0}


# ---------------------------------------------------------------------------
# OI / Price Divergence — Market Setups (coins NOT held)
# ---------------------------------------------------------------------------

@app.get("/api/notifications/market-setups")
async def market_setups(address: Optional[str] = Query(None), min_score: int = Query(2)):
    """Detect OI/price divergence setups on coins the user does NOT hold.

    OI trend semantics (from positioning engine):
      BUILDING   — OI ↑ + price ↑  (momentum confirmation)
      SQUEEZE    — OI ↓ + price ↑  (shorts forced out)
      LIQUIDATING— OI ↓ + price ↓  (long capitulation)
      SHORTING   — OI ↑ + price ↓  (shorts piling in / distribution)
      STABLE     — minimal movement

    Alpha patterns:
      1. SQUEEZE SETUP   — SHORTING + constructive regime → shorts piling against trend
      2. CROWDED_SHORT   — extreme negative funding + bullish signal → squeeze incoming
      3. OI FRONT-RUN    — BUILDING + pre-signal (WAIT/ACCUM, heat < 50) → smart money loading
      4. CAPITULATION    — LIQUIDATING + low heat + ACCUM/REACC regime → near washout bottom
      5. SHORTS INTO FLOOR — SHORTING + floor_confirmed → shorts loading into exhausted sellers
    """
    try:
        held_syms: set = set()
        if address:
            from hyperliquid_data import fetch_clearinghouse_state, parse_open_positions
            state = await fetch_clearinghouse_state(address)
            if state:
                positions = parse_open_positions(state)
                held_syms = {p["symbol"] for p in positions}

        results_by_symbol: dict = {}
        for tf in ("4h", "1d"):
            for r in cache.results.get(tf, []):
                sym = r.get("symbol", "")
                if sym not in results_by_symbol:
                    results_by_symbol[sym] = r

        setups = []
        now = int(time.time())

        _adverse   = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}
        _entry     = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED"}
        _pre_entry = {"ACCUMULATE", "REVIVAL_SEED", "WAIT"}
        _bullish_regimes = {"MARKUP", "REACC", "ACCUM"}

        for sym, scan in results_by_symbol.items():
            if sym in held_syms:
                continue

            positioning    = scan.get("positioning") or {}
            if not positioning:
                continue  # no OI data for this coin

            oi_trend       = positioning.get("oi_trend", "UNKNOWN")
            funding_regime = positioning.get("funding_regime", "NEUTRAL")
            funding_rate   = positioning.get("funding_rate", 0.0)
            oi_change_pct  = positioning.get("oi_change_pct", 0.0)

            signal         = scan.get("signal", "WAIT")
            regime         = scan.get("regime", "")
            heat           = scan.get("heat", 0)
            price          = scan.get("price", 0)
            met            = scan.get("conditions_met", 0)
            total          = scan.get("conditions_total", 10)
            floor_conf     = scan.get("floor_confirmed", False)
            is_climax      = scan.get("is_climax", False)
            base_coin      = sym.split("/")[0]

            # ── 1. SQUEEZE SETUP: shorts loading into a bullish regime ──────────
            # OI rising while price falls (SHORTING), but regime is still constructive
            # → crowd is wrong, the dip is being absorbed, potential squeeze
            if (oi_trend == "SHORTING"
                    and regime in _bullish_regimes
                    and signal not in _adverse
                    and heat < 70):
                intensity = "high" if funding_regime == "CROWDED_SHORT" else "medium"
                funding_str = f" | Funding: {funding_rate*100:.4f}%/8h" if funding_rate != 0 else ""
                setups.append({
                    "type": "squeeze_setup",
                    "severity": intensity,
                    "symbol": sym, "coin": base_coin, "timestamp": now,
                    "title": f"{base_coin}: Shorts piling into {regime} regime",
                    "detail": (
                        f"OI ↑ + price ↓ (SHORTING) but regime is {regime} and signal is {signal}. "
                        f"Crowd shorting against the trend{funding_str}. "
                        f"Any bounce = forced covering | Conditions: {met}/{total}"
                    ),
                    "signal": signal, "regime": regime, "heat": heat,
                    "oi_trend": oi_trend, "funding_regime": funding_regime,
                })

            # ── 2. CROWDED SHORT + ENTRY SIGNAL: textbook squeeze ───────────────
            elif (funding_regime == "CROWDED_SHORT"
                      and signal in _entry
                      and regime not in ("MARKDOWN", "CAP")):
                setups.append({
                    "type": "crowded_short_entry",
                    "severity": "high",
                    "symbol": sym, "coin": base_coin, "timestamp": now,
                    "title": f"{base_coin}: Crowded short + entry signal",
                    "detail": (
                        f"Funding: {funding_rate*100:.4f}%/8h (shorts paying premium). "
                        f"Signal: {signal} | Regime: {regime}. "
                        f"Shorts trapped — squeeze setup with bullish confirmation"
                    ),
                    "signal": signal, "regime": regime, "heat": heat,
                    "oi_trend": oi_trend, "funding_regime": funding_regime,
                })

            # ── 3. OI FRONT-RUN: smart money building before signal confirms ────
            # OI confirming (BUILDING, decent change) but signal not at entry yet
            # Heat must be low — this is accumulation, not chase
            elif (oi_trend == "BUILDING"
                      and oi_change_pct >= 5.0
                      and signal in _pre_entry
                      and heat < 50
                      and regime not in ("MARKDOWN", "CAP")):
                setups.append({
                    "type": "oi_front_run",
                    "severity": "medium",
                    "symbol": sym, "coin": base_coin, "timestamp": now,
                    "title": f"{base_coin}: OI building before signal confirms",
                    "detail": (
                        f"OI +{oi_change_pct:.1f}% with price (BUILDING) but signal still {signal}. "
                        f"Regime: {regime} | Heat: {heat}/100. "
                        f"Smart money positioning ahead of signal upgrade — watch for entry"
                    ),
                    "signal": signal, "regime": regime, "heat": heat,
                    "oi_trend": oi_trend, "oi_change_pct": oi_change_pct,
                })

            # ── 4. SHORTS INTO EXHAUSTION FLOOR: ultimate contrarian long setup ─
            # OI rising + price falling, but the exhaustion engine says floor is in
            # Crowd is shorting into exhausted sellers — extremely asymmetric setup
            elif (oi_trend == "SHORTING"
                      and (floor_conf or is_climax)
                      and signal not in _adverse):
                label = "floor confirmed" if floor_conf else "downside climax"
                setups.append({
                    "type": "shorts_into_floor",
                    "severity": "high",
                    "symbol": sym, "coin": base_coin, "timestamp": now,
                    "title": f"{base_coin}: Shorts into exhaustion {label}",
                    "detail": (
                        f"OI rising (shorts loading) while exhaustion engine shows {label}. "
                        f"Sellers exhausted + crowd shorting = high-conviction reversal setup. "
                        f"Signal: {signal} | Regime: {regime} | Heat: {heat}"
                    ),
                    "signal": signal, "regime": regime, "heat": heat,
                    "oi_trend": oi_trend, "floor_confirmed": floor_conf,
                })

            # ── 5. CAPITULATION WATCH: longs getting washed out, near bottom ───
            elif (oi_trend == "LIQUIDATING"
                      and heat < 35
                      and regime in ("MARKDOWN", "ACCUM", "CAP")):
                setups.append({
                    "type": "capitulation_watch",
                    "severity": "low",
                    "symbol": sym, "coin": base_coin, "timestamp": now,
                    "title": f"{base_coin}: Long liquidations underway",
                    "detail": (
                        f"OI ↓ + price ↓ (LIQUIDATING) | Regime: {regime} | Heat: {heat}/100. "
                        f"Forced selling in progress — watch for exhaustion floor + signal upgrade before entry. "
                        f"Do NOT catch falling knife"
                    ),
                    "signal": signal, "regime": regime, "heat": heat,
                    "oi_trend": oi_trend,
                })

            # ── 6. CVD BULLISH DIVERGENCE: price falling but buyers dominating taker flow ──
            # = smart money absorbing — not showing in price yet
            elif (scan.get("cvd_trend") == "BULLISH"
                      and scan.get("cvd_divergence")       # price going DOWN but CVD BULLISH
                      and signal not in _adverse
                      and regime not in ("CAP",)
                      and heat < 65):
                bsr = scan.get("buy_sell_ratio", 1.0)
                setups.append({
                    "type": "cvd_bullish_div",
                    "severity": "high",
                    "symbol": sym, "coin": base_coin, "timestamp": now,
                    "title": f"{base_coin}: CVD/price bullish divergence",
                    "detail": (
                        f"Price falling but taker buy flow dominant (BSR: {bsr:.2f}x). "
                        f"Smart money absorbing into weakness. "
                        f"Signal: {signal} | Regime: {regime} | Heat: {heat}/100. "
                        f"Watch for reversal — buyers not visible in price yet"
                    ),
                    "signal": signal, "regime": regime, "heat": heat,
                    "cvd_trend": "BULLISH", "buy_sell_ratio": bsr,
                })

            # ── 7. SPOT-LED DEMAND + constructive signal: organic buying ────────
            elif (positioning.get("spot_dominance") == "SPOT_LED"
                      and signal in _entry
                      and regime in _bullish_regimes
                      and heat < 70):
                ratio = positioning.get("spot_futures_ratio", 0)
                setups.append({
                    "type": "spot_led_breakout",
                    "severity": "medium",
                    "symbol": sym, "coin": base_coin, "timestamp": now,
                    "title": f"{base_coin}: Spot-led demand + entry signal",
                    "detail": (
                        f"Spot volume dominating ({ratio*100:.0f}% of total). "
                        f"Organic demand — not leverage-driven. "
                        f"Signal: {signal} | Regime: {regime}. "
                        f"Spot-led moves are more sustainable than futures-led"
                    ),
                    "signal": signal, "regime": regime, "heat": heat,
                    "spot_futures_ratio": ratio,
                })

        # Compute confluence score per setup (0–7)
        # Each independent confirming factor adds 1 point:
        #   1. RCCE conditions ≥ 60%  2. OI confirms  3. Heat zone correct
        #   4. Exhaustion confirms     5. Priority score ≥ 60
        #   6. CVD confirms direction  7. Spot dominance confirms
        def _confluence(s: dict, r: dict) -> int:
            pos    = r.get("positioning") or {}
            oi     = pos.get("oi_trend", "")
            fr     = pos.get("funding_regime", "NEUTRAL")
            met    = r.get("conditions_met", 0)
            total  = max(r.get("conditions_total", 10), 1)
            h      = r.get("heat", 50)
            score  = 0
            is_exit_setup = s.get("type") == "capitulation_watch"
            # 1. RCCE conditions strength
            if met / total >= 0.6: score += 1
            # 2. OI confirms
            if not is_exit_setup:
                if oi in ("BUILDING", "STABLE") or fr == "CROWDED_SHORT": score += 1
            else:
                if oi in ("LIQUIDATING", "SQUEEZE"): score += 1
            # 3. Heat zone
            if is_exit_setup:
                if h < 35: score += 1  # extremely depressed = near capitulation
            else:
                if h < 60: score += 1
            # 4. Exhaustion confirmation
            if r.get("floor_confirmed") or r.get("is_absorption"): score += 1
            # 5. Priority score
            if r.get("priority_score", 0) >= 60: score += 1
            # 6. CVD confirms direction
            cvd_t = r.get("cvd_trend", "NEUTRAL")
            if not is_exit_setup:
                if cvd_t == "BULLISH": score += 1
            else:
                if cvd_t == "BEARISH": score += 1
            # 7. Spot dominance confirms (organic demand)
            pos_r = r.get("positioning") or {}
            if pos_r.get("spot_dominance") == "SPOT_LED": score += 1
            return score

        # Attach confluence and apply min_score filter
        sym_map = {r.get("symbol", ""): r for tf in ("4h", "1d")
                   for r in cache.results.get(tf, [])}
        scored = []
        for s in setups:
            raw = sym_map.get(s["symbol"], {})
            c = _confluence(s, raw)
            s["confluence_score"] = c
            if c >= min_score:
                scored.append(s)

        # Sort: high severity first, then confluence desc
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        scored.sort(key=lambda s: (sev_order.get(s.get("severity", "low"), 3), -s.get("confluence_score", 0)))

        return {"setups": scored, "count": len(scored), "filtered_out": len(setups) - len(scored)}

    except Exception as e:
        logger.warning("Market setups failed: %s", e)
        return {"setups": [], "count": 0}


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


# ---------------------------------------------------------------------------
# LLM Assistant endpoints
# ---------------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """LLM-powered trading assistant chat."""
    try:
        from assistant import get_assistant
        assistant = get_assistant()
        reply, detected = await assistant.chat(
            session_id=req.session_id,
            user_message=req.message,
            symbol=req.symbol,
            wallet_address=req.wallet_address,
        )
        return ChatResponse(
            reply=reply,
            session_id=req.session_id,
            detected_symbol=detected,
            model=assistant.get_current_model(),
        )
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models", response_model=ModelsResponse)
async def get_models():
    """List available LLM models and current selection."""
    try:
        from assistant import get_assistant
        assistant = get_assistant()
        return ModelsResponse(
            models=await assistant.get_available_models(),
            current=assistant.get_current_model(),
            mode=assistant.get_mode(),
        )
    except Exception as e:
        logger.error("Models list error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/models", response_model=SetModelResponse)
async def set_model(req: SetModelRequest):
    """Switch the active LLM model."""
    try:
        from assistant import get_assistant
        assistant = get_assistant()
        success = assistant.set_model(req.model_id)
        return SetModelResponse(
            success=success,
            current=assistant.get_current_model(),
        )
    except Exception as e:
        logger.error("Model switch error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/briefing", response_model=BriefingResponse)
async def briefing_endpoint():
    """Generate a daily market briefing."""
    try:
        from assistant import get_assistant
        assistant = get_assistant()
        briefing = await assistant.daily_briefing()
        return BriefingResponse(briefing=briefing, timestamp=time.time())
    except Exception as e:
        logger.error("Briefing error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/explain/{symbol:path}")
async def explain_endpoint(symbol: str, timeframe: str = Query("4h")):
    """Explain the current signal for a symbol."""
    try:
        from assistant import get_assistant
        assistant = get_assistant()
        explanation = await assistant.explain_signal(symbol, timeframe)
        return {"symbol": symbol, "timeframe": timeframe, "explanation": explanation}
    except Exception as e:
        logger.error("Explain error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"ok": True, "build": "2026-03-17-multi-source"}


@app.get("/api/data-sources")
async def data_sources():
    """Diagnostic endpoint: shows data source routing info."""
    from data_fetcher import get_data_source_info
    info = get_data_source_info()

    # Positioning: Binance (primary) → Hyperliquid → Bybit (fallback)
    info["positioning_source"] = "binance+hyperliquid+bybit"

    try:
        from scanner import _scan_cache
        last_4h = _scan_cache.get("4h", {}).get("results", [])
        with_pos = sum(1 for r in last_4h if r.get("positioning"))
        info["positioning_count"] = with_pos
        info["total_symbols"] = len(last_4h)
    except Exception:
        pass

    return info


@app.get("/api/geo-test")
async def geo_test():
    """Test if Binance/Bybit/CoinGlass are reachable from current Railway region."""
    import httpx, asyncio

    async def test_binance():
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
                data = r.json()
                if "symbol" in data:
                    return {"status": "ok", "funding": data.get("lastFundingRate"), "code": r.status_code}
                else:
                    return {"status": "blocked", "response": data, "code": r.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def test_bybit():
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get("https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT")
                data = r.json()
                if data.get("retCode") == 0:
                    return {"status": "ok", "code": r.status_code}
                else:
                    return {"status": "blocked", "response": data, "code": r.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def test_coinglass():
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get("https://open-api-v3.coinglass.com/api/futures/openInterest/chart?symbol=BTC&range=4h",
                                headers={"accept": "application/json"})
                return {"status": "reachable", "code": r.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    b, by, cg = await asyncio.gather(test_binance(), test_bybit(), test_coinglass())
    return {"binance": b, "bybit": by, "coinglass": cg}


# ---------------------------------------------------------------------------
# Exchange Derivatives Shadow Module
# ---------------------------------------------------------------------------

@app.get("/api/test-binance-derivatives")
async def test_binance_derivatives():
    """Test if Binance /futures/data/ analytics endpoints are reachable."""
    from exchange_derivatives_data import test_binance_connectivity
    return await test_binance_connectivity()


@app.get("/api/derivatives-shadow")
async def derivatives_shadow():
    """Run the shadow exchange derivatives fetch and return results."""
    from exchange_derivatives_data import fetch_exchange_derivatives
    metrics, cvd, cb = await fetch_exchange_derivatives()
    # Return summary for top 20 coins
    summary = []
    for sym, m in sorted(metrics.items(), key=lambda x: x[1].oi_total_usd, reverse=True)[:20]:
        entry = {
            "symbol": sym,
            "oi_total": round(m.oi_total_usd / 1e6, 1),
            "oi_binance": round(m.oi_binance_usd / 1e6, 1),
            "oi_bybit": round(m.oi_bybit_usd / 1e6, 1),
            "oi_okx": round(m.oi_okx_usd / 1e6, 1),
            "oi_chg_4h": m.oi_change_pct_4h,
            "retail_lsr": m.long_short_ratio_4h,
            "top_lsr": m.top_trader_lsr,
            "spot_dominance": m.spot_dominance,
        }
        coin_cvd = cvd.get(m.coin)
        if coin_cvd:
            entry["cvd_trend"] = coin_cvd.cvd_trend
            entry["cvd_bsr"] = coin_cvd.buy_sell_ratio
        summary.append(entry)
    return {"count": len(metrics), "top_20": summary}


@app.get("/api/derivatives-comparison")
async def derivatives_comparison():
    """Compare exchange derivatives data with CoinGlass side-by-side."""
    from exchange_derivatives_data import fetch_exchange_derivatives, compare_with_coinglass
    from coinglass_data import fetch_coinglass_metrics, _cvd_store

    # Fetch both in parallel
    ex_task = fetch_exchange_derivatives()
    cg_task = fetch_coinglass_metrics()
    (ex_metrics, ex_cvd, _), cg_metrics = await asyncio.gather(ex_task, cg_task)

    comparisons = compare_with_coinglass(ex_metrics, ex_cvd, cg_metrics, _cvd_store)

    # Sort by OI for readability
    comparisons.sort(key=lambda x: x.get("oi_total_usd", 0), reverse=True)

    return {"count": len(comparisons), "comparisons": comparisons[:30]}


# ---------------------------------------------------------------------------
# HyperLens endpoints — smart-money wallet tracking
# ---------------------------------------------------------------------------

@app.get("/api/hyperlens/status")
async def hyperlens_status():
    """HyperLens module status."""
    from hl_intelligence import get_status
    return get_status()


@app.get("/api/hyperlens/roster")
async def hyperlens_roster(cohort: Optional[str] = Query(None)):
    """Current tracked wallet roster with stats.
    Optional ?cohort=money_printers|smart_money|elite to filter by cohort."""
    from hl_intelligence import get_roster
    roster = get_roster(cohort=cohort)
    return {"count": len(roster), "wallets": roster}


@app.get("/api/hyperlens/consensus")
async def hyperlens_consensus(
    symbol: Optional[str] = Query(None),
    cohort: Optional[str] = Query(None),
):
    """Per-symbol smart-money consensus.

    Optional ?symbol=BTC filter, otherwise returns all symbols sorted by
    number of positioned wallets.
    Optional ?cohort=money_printers|smart_money|elite to filter by cohort.
    """
    from hl_intelligence import get_consensus, get_all_consensus

    def _consensus_to_dict(c):
        d = {
            "symbol": c.symbol,
            "trend": c.trend,
            "confidence": round(c.confidence, 3),
            "long_count": c.long_count,
            "short_count": c.short_count,
            "net_ratio": round(c.net_ratio, 3),
            "long_notional": round(c.long_notional, 2),
            "short_notional": round(c.short_notional, 2),
            "total_tracked": c.total_tracked,
            # Per-cohort consensus
            "money_printer": {
                "trend": c.money_printer_trend,
                "net_ratio": c.money_printer_net_ratio,
                "long_count": c.money_printer_long_count,
                "short_count": c.money_printer_short_count,
            },
            "smart_money": {
                "trend": c.smart_money_trend,
                "net_ratio": c.smart_money_net_ratio,
                "long_count": c.smart_money_long_count,
                "short_count": c.smart_money_short_count,
            },
        }
        return d

    if symbol:
        c = get_consensus(symbol.upper())
        if c is None:
            return {"symbol": symbol.upper(), "trend": "NO_DATA", "wallets": 0}
        return _consensus_to_dict(c)

    all_c = get_all_consensus()
    results = [_consensus_to_dict(c) for c in all_c.values()]
    # Sort by total positioned wallets
    results.sort(key=lambda x: x["long_count"] + x["short_count"], reverse=True)
    return {"count": len(results), "consensus": results}


@app.get("/api/hyperlens/positions/{symbol}")
async def hyperlens_symbol_positions(symbol: str):
    """Per-wallet position breakdown for a symbol."""
    from hl_intelligence import get_symbol_positions
    positions = get_symbol_positions(symbol.upper())
    return {"symbol": symbol.upper(), "count": len(positions), "positions": positions}


@app.get("/api/hyperlens/wallet/{address}")
async def hyperlens_wallet(address: str):
    """Get comprehensive wallet profile with positions, trades, and stats."""
    from hl_intelligence import get_wallet_profile
    result = get_wallet_profile(address)
    if result is None:
        raise HTTPException(status_code=404, detail="Wallet not tracked or no data yet")
    return result


@app.get("/api/hyperlens/wallet/{address}/trades")
async def hyperlens_wallet_trades(
    address: str,
    limit: int = Query(50, ge=1, le=200),
):
    """Get reconstructed trade history for a wallet."""
    from hl_intelligence import get_wallet_trades
    trades = get_wallet_trades(address, limit=limit)
    return {"address": address.lower(), "count": len(trades), "trades": trades}


@app.get("/api/hyperlens/changes/{symbol}")
async def hyperlens_changes(
    symbol: str,
    window: int = Query(30, ge=5, le=1440, description="Window in minutes"),
):
    """Detect position changes for a symbol over recent window."""
    from hl_intelligence import get_position_changes
    return get_position_changes(symbol.upper(), window_minutes=window)


@app.get("/api/hyperlens/pressure")
async def hyperlens_pressure(symbol: Optional[str] = Query(None)):
    """Get pressure map — stops, TPs, limits, book walls, liq clusters.
    Pass ?symbol=BTC for a specific coin, or omit for all with significant smart money activity."""
    try:
        from hl_intelligence import get_pressure
        sym = symbol.upper() if symbol else None
        return get_pressure(sym)
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/hyperlens/orderbook/{symbol}")
async def hyperlens_orderbook(symbol: str):
    """Get order book walls for a symbol."""
    try:
        from hl_intelligence import get_order_book_walls
        return get_order_book_walls(symbol.upper())
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/hyperlens/smart-orders")
async def hyperlens_smart_orders(symbol: Optional[str] = Query(None)):
    """Get aggregated smart money orders (stops/TPs/limits).
    Pass ?symbol=BTC to filter by coin, or omit for all."""
    try:
        from hl_intelligence import get_smart_money_orders
        sym = symbol.upper() if symbol else None
        return {"orders": get_smart_money_orders(sym)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/hyperlens/wallet/{address}/equity")
async def hyperlens_wallet_equity(
    address: str,
    days: int = Query(7, ge=1, le=30, description="Days of equity history"),
):
    """Get extended equity curve from DB (up to 30 days)."""
    from hl_persistence import load_equity_history
    history = load_equity_history(address.lower(), days=days)
    return {"address": address.lower(), "days": days, "points": len(history), "history": history}


# ── Whale Wallet Follow / Watchlist ──────────────────────────────────────────

@app.get("/api/hyperlens/follows")
async def get_follows(user: str = Query(..., description="Connected wallet address")):
    """List followed whale wallets for a user."""
    import whale_follows as wf
    from hl_intelligence import get_wallet_profile
    addresses = wf.get_follows(user)
    wallets = []
    for addr in addresses:
        try:
            profile = get_wallet_profile(addr)
            wallets.append({
                "address": addr,
                "account_value": profile.get("account_value", 0),
                "roi": profile.get("roi", 0),
                "cohorts": profile.get("cohorts", []),
                "positions_count": len(profile.get("positions", [])),
            })
        except Exception:
            wallets.append({"address": addr, "account_value": 0, "roi": 0, "cohorts": [], "positions_count": 0})
    return {"user": user.lower(), "count": len(wallets), "wallets": wallets}


@app.post("/api/hyperlens/follows")
async def add_follow(body: dict):
    """Follow a whale wallet. Body: {user, address}"""
    import whale_follows as wf
    user = body.get("user", "")
    address = body.get("address", "")
    if not user or not address:
        raise HTTPException(status_code=400, detail="user and address required")
    added = wf.add_follow(user, address)
    return {"ok": True, "added": added, "count": len(wf.get_follows(user))}


@app.delete("/api/hyperlens/follows/{address}")
async def remove_follow(address: str, user: str = Query(...)):
    """Unfollow a whale wallet."""
    import whale_follows as wf
    removed = wf.remove_follow(user, address)
    return {"ok": True, "removed": removed, "count": len(wf.get_follows(user))}


@app.get("/api/hyperlens/follows/events")
async def get_follow_events(
    user: str = Query(..., description="Connected wallet address"),
    since: float = Query(0, description="Unix timestamp — only return events after this"),
):
    """Get recent trade events from followed wallets."""
    import whale_follows as wf
    addresses = set(wf.get_follows(user))
    events = wf.get_events(addresses, since=since)
    return {"user": user.lower(), "count": len(events), "events": events}


@app.get("/api/hyperlens/follows/check/{address}")
async def check_follow(address: str, user: str = Query(...)):
    """Check if a user follows a specific wallet."""
    import whale_follows as wf
    return {"following": wf.is_following(user, address)}
