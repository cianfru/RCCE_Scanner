"""
RCCE Scanner — Pydantic response models
"""
from pydantic import BaseModel
from typing import Dict, List, Optional


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
    source: str = ""                # "binance" or "hyperliquid"


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


class ConditionDetail(BaseModel):
    name: str
    label: str
    desc: str = ""
    met: bool


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
    conditions_met: int = 0
    conditions_total: int = 10
    conditions_detail: List[ConditionDetail] = []
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
    # Positioning (Binance Futures primary, Hyperliquid fallback)
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
    timeframe: str = "4h"           # "4h" or "1d"
    leverage: float = 1.0           # 1.0 = no leverage, 2.0 = 2x, etc.


class WalkForwardRequest(BaseModel):
    symbols: List[str] = []         # empty = default 10 symbols
    start_date: str = "2021-01-01"  # wider default for walk-forward
    end_date: str = ""              # empty = today
    initial_capital: float = 10000.0
    use_confluence: bool = True
    use_fear_greed: bool = True
    timeframe: str = "4h"
    leverage: float = 1.0
    # Walk-forward specific
    test_window_days: int = 180     # 6-month windows
    step_days: int = 180            # non-overlapping
    warmup_days: int = 0            # 0 = auto (70 for 4h, 210 for 1d)


# ---------------------------------------------------------------------------
# Executor models
# ---------------------------------------------------------------------------

class ExecutorInitRequest(BaseModel):
    mode: str = "paper"              # "paper" or "live"
    balance: float = 10000.0

class ExecutorStatusResponse(BaseModel):
    mode: str = "disabled"
    enabled: bool = False
    initialized: bool = False
    positions: Dict[str, dict] = {}
    open_position_count: int = 0
    total_trades: int = 0
    total_pnl_pct: float = 0.0
    win_rate: float = 0.0
    last_scan_signals: Dict[str, str] = {}
    last_error: Optional[str] = None
    last_execution_time: Optional[float] = None
    total_executions: int = 0
    available_pairs: int = 0
    paper_balance: float = 0.0
    portfolio: dict = {}

# Whitelist models (same shape as Watchlist)
class WhitelistUpdate(BaseModel):
    symbols: List[str]

class WhitelistAddRequest(BaseModel):
    symbol: str


class ExecutorTradeResponse(BaseModel):
    symbol: str
    kraken_pair: str = ""
    side: str = "LONG"
    entry_price: float = 0.0
    entry_time: float = 0.0
    entry_signal: str = ""
    exit_price: float = 0.0
    exit_time: float = 0.0
    exit_signal: str = ""
    volume: float = 0.0
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0
    order_ids: List[str] = []


# ---------------------------------------------------------------------------
# Portfolio group models
# ---------------------------------------------------------------------------

class PortfolioGroupResponse(BaseModel):
    id: str
    name: str
    symbols: List[str] = []
    color: str = "#22d3ee"
    order: int = 0
    pinned: bool = False


class PortfolioGroupCreate(BaseModel):
    name: str
    symbols: List[str] = []
    color: str = "#22d3ee"


class PortfolioGroupUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class PortfolioGroupAddSymbol(BaseModel):
    symbol: str


class PortfolioGroupReorder(BaseModel):
    order: List[str]  # list of group IDs in desired order
