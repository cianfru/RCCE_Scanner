"""
RCCE Scanner — Pydantic response models
"""
from pydantic import BaseModel
from typing import List, Optional


class ScanResult(BaseModel):
    symbol: str
    timeframe: str
    price: float
    regime: str
    confidence: float
    signal: str
    zscore: float
    energy: float
    vol_state: str
    momentum: float
    divergence: Optional[str] = None
    asset_class: str
    heat: int = 0
    heat_direction: int = 0
    heat_phase: str = "Neutral"
    atr_regime: str = "Normal"
    deviation_pct: float = 0.0
    exhaustion_state: str = "NEUTRAL"
    floor_confirmed: bool = False
    effort: float = 0.0
    rel_vol: float = 0.0


class ScanResponse(BaseModel):
    results: List[ScanResult]
    scan_running: bool
    cache_age_seconds: Optional[float] = None
    consensus: Optional[dict] = None


class ConsensusResponse(BaseModel):
    consensus: str
    strength: float
    timeframe: str


class StatusResponse(BaseModel):
    is_scanning: bool
    last_scan_time: Optional[float] = None
    symbols_count: int
    cache_age_seconds: Optional[float] = None


class WatchlistResponse(BaseModel):
    symbols: List[str]


class WatchlistUpdate(BaseModel):
    symbols: List[str]
