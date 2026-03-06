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


async def _periodic_scan():
    """Run scans every 5 minutes."""
    while True:
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


@app.get("/health")
async def health():
    return {"ok": True}
