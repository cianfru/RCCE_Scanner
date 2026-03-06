"""
RCCE Scanner API
FastAPI backend — exposes scan results, triggers manual scans, serves status
"""
import logging
import threading
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from scanner import cache, get_all_results, get_scan_status, run_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=run_scan, daemon=True).start()
    scheduler.add_job(run_scan, "cron", minute=5, id="hourly_scan")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="RCCE Scanner API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
def status():
    return get_scan_status()


@app.get("/api/results")
def results():
    return {
        "status": get_scan_status(),
        "data": get_all_results(),
    }


@app.post("/api/scan")
def trigger_scan(background_tasks: BackgroundTasks):
    if cache.is_scanning:
        return {"ok": False, "message": "Scan already in progress"}
    background_tasks.add_task(run_scan)
    return {"ok": True, "message": "Scan started"}


@app.get("/api/watchlist")
def get_watchlist():
    return {"symbols": cache.symbols}


@app.post("/api/watchlist")
def update_watchlist(body: dict):
    symbols = body.get("symbols", [])
    if not isinstance(symbols, list) or len(symbols) == 0:
        return {"ok": False, "message": "Invalid symbol list"}
    cache.symbols = [s.upper().replace("-", "/") for s in symbols]
    return {"ok": True, "count": len(cache.symbols)}


@app.get("/health")
def health():
    return {"ok": True}
