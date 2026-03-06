"""
RCCE Scanner — Pydantic response models
"""
from pydantic import BaseModel
from typing import List, Optional


class PositioningResponse(BaseModel):
    funding_regime: str = "NEUTRAL"
    funding_rate: float = 0.0
    oi_trend: str = "UNKNOWN"
    oi_value: float = 0.0
    oi_change_pct: float = 0.0
    leverage_risk: str = "UNKNOWN"
    predicted_funding: float = 0.0
    mark_price: float = 0.0
    volume_24h: float = 0.0


class SentimentResponse(BaseModel):
    fear_greed_value: int = 50
    fear_greed_label: str = "Neutral"


class StablecoinResponse(BaseModel):
    usdt_market_cap: float = 0.0
    usdc_market_cap: float = 0.0
    total_cap: float = 0.0
    trend: str = "STABLE"
    change_7d_pct: float = 0.0


class ConfluenceResponse(BaseModel):
    score: int = 0
    label: str = "UNKNOWN"
    regime_aligned: bool = False
    signal_aligned: bool = False
    regime_4h: str = ""
    regime_1d: str = ""
    signal_4h: str = ""
    signal_1d: str = ""


class ScanResult(BaseModel):
    symbol: str
    timeframe: str
    price: float
    regime: str
    confidence: float
    signal: str
    raw_signal: str = "WAIT"
    signal_reason: str = ""
    signal_warnings: List[str] = []
    signal_confidence: int = 0       # conditions_met / conditions_total as %
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
    is_absorption: bool = False
    is_climax: bool = False
    effort: float = 0.0
    rel_vol: float = 0.0
    # Positioning (Hyperliquid)
    positioning: Optional[PositioningResponse] = None
    # Multi-TF confluence
    confluence: Optional[ConfluenceResponse] = None
    # Sparkline data (last 24 close prices)
    sparkline: List[float] = []


class ScanResponse(BaseModel):
    results: List[ScanResult]
    scan_running: bool
    cache_age_seconds: Optional[float] = None
    consensus: Optional[dict] = None


class ConsensusResponse(BaseModel):
    consensus: str
    strength: float
    timeframe: str


class GlobalMetricsResponse(BaseModel):
    btc_dominance: float = 0.0
    eth_dominance: float = 0.0
    total_market_cap: float = 0.0
    alt_market_cap: float = 0.0
    btc_market_cap: float = 0.0
    timestamp: float = 0.0


class StatusResponse(BaseModel):
    is_scanning: bool
    last_scan_time: Optional[float] = None
    symbols_count: int
    cache_age_seconds: Optional[float] = None


class WatchlistResponse(BaseModel):
    symbols: List[str]


class WatchlistUpdate(BaseModel):
    symbols: List[str]


class WatchlistAddRequest(BaseModel):
    symbol: str


class SymbolSearchResult(BaseModel):
    symbol: str
    base: str
    quote: str


# ---------------------------------------------------------------------------
# Backtest models
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    symbols: List[str] = []         # empty = default 10 symbols
    start_date: str = "2025-01-01"
    end_date: str = ""              # empty = today
    initial_capital: float = 10000.0
    use_confluence: bool = True
    use_fear_greed: bool = True
