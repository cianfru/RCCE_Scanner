"""
RCCE Scanner API
FastAPI backend for multi-signal crypto scanning
"""
import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from scanner import cache, run_scan, get_scan_status
from models import ScanResponse, ConsensusResponse, StatusResponse, WatchlistResponse, WatchlistUpdate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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


app = FastAPI(title="RCCE Scanner API", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/watchlist")
async def get_watchlist():
    return WatchlistResponse(symbols=cache.symbols)


@app.post("/api/watchlist")
async def update_watchlist(body: WatchlistUpdate):
    cache.symbols = [s.upper().replace("-", "/") for s in body.symbols]
    return {"ok": True, "count": len(cache.symbols)}


@app.get("/health")
async def health():
    return {"ok": True}
