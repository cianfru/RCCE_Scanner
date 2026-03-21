"""
exchange_derivatives_data.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Multi-exchange derivatives analytics fetcher (shadow module).

Replaces CoinGlass with free exchange APIs:
  - Binance:  CVD, retail LSR, top-trader LSR, OI history, spot volume
  - Bybit:    OI (for multi-exchange aggregation)
  - OKX:      OI (for multi-exchange aggregation)

No API keys required — all public endpoints.

Phase 1: shadow mode — runs alongside CoinGlass, logs comparison data.
Phase 2: replaces CoinGlass entirely.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_REQUEST_TIMEOUT_S = 15
_MAX_RETRIES = 2
_RETRY_DELAY_S = 2.0
_CACHE_TTL = 5 * 60  # 5 minutes (matches scan interval)

# Concurrency per exchange
_BINANCE_CONCURRENCY = 50   # 1200 req/min limit → generous headroom
_BYBIT_CONCURRENCY = 30     # 600 req/min limit
_OKX_CONCURRENCY = 30       # 600 req/min limit

# Binance /futures/data/ base
_BINANCE_FAPI_BASE = "https://fapi.binance.com"
_BINANCE_SPOT_BASE = "https://api.binance.com"

# Bybit v5 base
_BYBIT_BASE = "https://api.bybit.com"

# OKX base
_OKX_BASE = "https://www.okx.com"

# Data period — 15m for near-real-time updates (Binance supports 5m/15m/30m/1h/2h/4h)
_DATA_PERIOD = "15m"
_CVD_LOOKBACK = 6     # 6 × 15m = 90 min of CVD context
_OI_LOOKBACK = 7      # 7 × 15m = 105 min for OI change (4h-equivalent window)
_LSR_LOOKBACK = 1     # Latest bar only

# CVD trend thresholds (same as coinglass_data.py)
_CVD_BULLISH_RATIO = 1.05
_CVD_BEARISH_RATIO = 0.95

# Spot dominance thresholds (same as coinglass_data.py)
_SPOT_LED_RATIO = 0.55
_FUTURES_LED_RATIO = 0.35

# Symbol prefix quirks (Binance uses "1000PEPE" etc.)
_BINANCE_PREFIX_MAP = {
    "1000PEPE": "PEPE",
    "1000BONK": "BONK",
    "1000FLOKI": "FLOKI",
    "1000SHIB": "SHIB",
    "1MBABYDOGE": "BABYDOGE",
}

# Priority coins — fetched first for fast initial data
_PRIORITY_COINS = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT",
    "MATIC", "UNI", "NEAR", "OP", "ARB", "SUI", "APT", "FIL", "ATOM", "LTC",
]


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class DerivativesMetrics:
    """Per-coin derivatives data from multi-exchange fetch."""
    coin: str = ""
    # OI (aggregated across exchanges)
    oi_total_usd: float = 0.0
    oi_binance_usd: float = 0.0
    oi_bybit_usd: float = 0.0
    oi_okx_usd: float = 0.0
    oi_change_pct_4h: float = 0.0   # From Binance OI history (most reliable)
    oi_change_pct_24h: float = 0.0
    # LSR (Binance only)
    long_short_ratio_4h: float = 1.0   # Retail
    top_trader_lsr: float = 1.0        # Smart money (top traders)
    # Spot dominance (Binance spot vs futures volume)
    spot_volume_usd: float = 0.0
    futures_volume_usd: float = 0.0
    spot_futures_ratio: float = 0.0
    spot_dominance: str = "NEUTRAL"
    timestamp: float = 0.0


@dataclass
class CVDResult:
    """CVD data from Binance taker buy/sell volume."""
    coin: str = ""
    cvd_trend: str = "NEUTRAL"       # BULLISH | BEARISH | NEUTRAL
    cvd_value: float = 0.0           # Net (buy - sell) USD
    cvd_divergence: bool = False     # Price dir ≠ CVD dir
    buy_volume_usd: float = 0.0
    sell_volume_usd: float = 0.0
    buy_sell_ratio: float = 1.0
    timestamp: float = 0.0


@dataclass
class CBPremium:
    """Self-computed Coinbase premium."""
    premium_rate: float = 0.0        # (CB - Binance) / Binance
    premium_usd: float = 0.0        # Raw difference in USD
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _Cache:
    data: Optional[Dict[str, DerivativesMetrics]] = None
    cvd: Optional[Dict[str, CVDResult]] = None
    cb_premium: Optional[CBPremium] = None
    expires_at: float = 0.0

    def is_valid(self) -> bool:
        return self.data is not None and time.monotonic() < self.expires_at

    def put(
        self,
        data: Dict[str, DerivativesMetrics],
        cvd: Dict[str, CVDResult],
        cb_premium: Optional[CBPremium] = None,
    ) -> None:
        self.data = data
        self.cvd = cvd
        self.cb_premium = cb_premium
        self.expires_at = time.monotonic() + _CACHE_TTL


_cache = _Cache()


# ---------------------------------------------------------------------------
# Symbol helpers
# ---------------------------------------------------------------------------

def _scanner_to_coin(scanner_sym: str) -> str:
    """'BTC/USDT' → 'BTC'"""
    return scanner_sym.split("/")[0]


def _coin_to_binance(coin: str) -> str:
    """'BTC' → 'BTCUSDT'"""
    return f"{coin}USDT"


def _binance_to_coin(binance_sym: str) -> Optional[str]:
    """'BTCUSDT' → 'BTC'. Returns None for non-USDT."""
    if not binance_sym.endswith("USDT"):
        return None
    base = binance_sym[:-4]
    if not base:
        return None
    return _BINANCE_PREFIX_MAP.get(base, base)


# ---------------------------------------------------------------------------
# Binance fetchers
# ---------------------------------------------------------------------------

async def _fetch_binance_taker_ratio(
    session: aiohttp.ClientSession,
    coin: str,
    sem: asyncio.Semaphore,
    limit: int = _CVD_LOOKBACK,
) -> Optional[dict]:
    """Fetch taker buy/sell ratio for CVD computation."""
    url = f"{_BINANCE_FAPI_BASE}/futures/data/takerlongshortRatio"
    params = {"symbol": _coin_to_binance(coin), "period": _DATA_PERIOD, "limit": limit}
    async with sem:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return {"coin": coin, "bars": data}
        except Exception as exc:
            logger.debug("Binance taker ratio failed for %s: %s", coin, exc)
            return None


async def _fetch_binance_retail_lsr(
    session: aiohttp.ClientSession,
    coin: str,
    sem: asyncio.Semaphore,
) -> Optional[dict]:
    """Fetch retail (global) long/short account ratio."""
    url = f"{_BINANCE_FAPI_BASE}/futures/data/globalLongShortAccountRatio"
    params = {"symbol": _coin_to_binance(coin), "period": _DATA_PERIOD, "limit": _LSR_LOOKBACK}
    async with sem:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data:
                    return {"coin": coin, "ratio": float(data[0].get("longShortRatio", 1.0))}
                return None
        except Exception as exc:
            logger.debug("Binance retail LSR failed for %s: %s", coin, exc)
            return None


async def _fetch_binance_top_lsr(
    session: aiohttp.ClientSession,
    coin: str,
    sem: asyncio.Semaphore,
) -> Optional[dict]:
    """Fetch top trader (smart money) long/short position ratio."""
    url = f"{_BINANCE_FAPI_BASE}/futures/data/topLongShortPositionRatio"
    params = {"symbol": _coin_to_binance(coin), "period": _DATA_PERIOD, "limit": _LSR_LOOKBACK}
    async with sem:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data:
                    return {"coin": coin, "ratio": float(data[0].get("longShortRatio", 1.0))}
                return None
        except Exception as exc:
            logger.debug("Binance top LSR failed for %s: %s", coin, exc)
            return None


async def _fetch_binance_oi_history(
    session: aiohttp.ClientSession,
    coin: str,
    sem: asyncio.Semaphore,
) -> Optional[dict]:
    """Fetch OI history (15m bars) for OI change computation."""
    url = f"{_BINANCE_FAPI_BASE}/futures/data/openInterestHist"
    params = {"symbol": _coin_to_binance(coin), "period": _DATA_PERIOD, "limit": _OI_LOOKBACK}
    async with sem:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return {"coin": coin, "bars": data}
        except Exception as exc:
            logger.debug("Binance OI history failed for %s: %s", coin, exc)
            return None


async def _fetch_binance_spot_tickers(
    session: aiohttp.ClientSession,
) -> Dict[str, float]:
    """Fetch spot 24h volume for all symbols (1 bulk call)."""
    url = f"{_BINANCE_SPOT_BASE}/api/v3/ticker/24hr"
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
            result = {}
            for item in data:
                sym = item.get("symbol", "")
                if sym.endswith("USDT"):
                    coin = _binance_to_coin(sym)
                    if coin:
                        result[coin] = float(item.get("quoteVolume", 0.0))
            return result
    except Exception as exc:
        logger.warning("Binance spot tickers failed: %s", exc)
        return {}


async def _fetch_binance_futures_tickers(
    session: aiohttp.ClientSession,
) -> Dict[str, float]:
    """Fetch futures 24h volume for all symbols (1 bulk call)."""
    url = f"{_BINANCE_FAPI_BASE}/fapi/v1/ticker/24hr"
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
            result = {}
            for item in data:
                sym = item.get("symbol", "")
                coin = _binance_to_coin(sym)
                if coin:
                    result[coin] = float(item.get("quoteVolume", 0.0))
            return result
    except Exception as exc:
        logger.warning("Binance futures tickers failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Bybit OI fetcher
# ---------------------------------------------------------------------------

async def _fetch_bybit_oi(
    session: aiohttp.ClientSession,
    coin: str,
    sem: asyncio.Semaphore,
) -> Optional[dict]:
    """Fetch current OI from Bybit v5."""
    url = f"{_BYBIT_BASE}/v5/market/open-interest"
    # Bybit uses "5min"/"15min"/"30min" format, not "5m"/"15m"/"30m"
    params = {"category": "linear", "symbol": f"{coin}USDT", "intervalTime": "5min", "limit": 1}
    async with sem:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                rows = data.get("result", {}).get("list", [])
                if rows:
                    oi_val = float(rows[0].get("openInterest", 0))
                    # Bybit returns OI in base currency — need price for USD
                    # We'll multiply by Binance mark price later
                    return {"coin": coin, "oi_base": oi_val}
                return None
        except Exception as exc:
            logger.debug("Bybit OI failed for %s: %s", coin, exc)
            return None


# ---------------------------------------------------------------------------
# OKX OI fetcher
# ---------------------------------------------------------------------------

async def _fetch_okx_oi(
    session: aiohttp.ClientSession,
    coin: str,
    sem: asyncio.Semaphore,
) -> Optional[dict]:
    """Fetch current OI from OKX."""
    url = f"{_OKX_BASE}/api/v5/public/open-interest"
    params = {"instType": "SWAP", "instId": f"{coin}-USDT-SWAP"}
    async with sem:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                rows = data.get("data", [])
                if rows:
                    # OKX provides oiUsd directly (USD value)
                    oi_usd = float(rows[0].get("oiUsd", 0))
                    return {"coin": coin, "oi_usd": oi_usd}
                return None
        except Exception as exc:
            logger.debug("OKX OI failed for %s: %s", coin, exc)
            return None


# ---------------------------------------------------------------------------
# CVD computation
# ---------------------------------------------------------------------------

def _compute_cvd(
    bars: list,
    price_change_pct: Optional[float] = None,
) -> CVDResult:
    """Compute CVD trend from Binance takerlongshortRatio bars.

    Binance ``takerlongshortRatio`` returns:
      - buySellRatio: float (buy / sell)
      - buyVol: float (taker buy volume USD)
      - sellVol: float (taker sell volume USD)
      - timestamp: int (ms)
    """
    if not bars:
        return CVDResult()

    total_buy = 0.0
    total_sell = 0.0
    for bar in bars:
        total_buy += float(bar.get("buyVol", 0))
        total_sell += float(bar.get("sellVol", 0))

    cvd_value = total_buy - total_sell
    bsr = total_buy / total_sell if total_sell > 0 else 1.0

    if cvd_value > 0 and bsr > _CVD_BULLISH_RATIO:
        trend = "BULLISH"
    elif cvd_value < 0 and bsr < _CVD_BEARISH_RATIO:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    divergence = False
    if price_change_pct is not None:
        if (price_change_pct > 0 and trend == "BEARISH") or \
           (price_change_pct < 0 and trend == "BULLISH"):
            divergence = True

    return CVDResult(
        cvd_trend=trend,
        cvd_value=cvd_value,
        cvd_divergence=divergence,
        buy_volume_usd=total_buy,
        sell_volume_usd=total_sell,
        buy_sell_ratio=round(bsr, 3),
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# OI change computation
# ---------------------------------------------------------------------------

def _compute_oi_change(bars: list) -> tuple:
    """Compute OI change % from Binance openInterestHist bars.

    Returns (oi_usd, change_recent, change_window).

    With 15m bars and limit=7:
      - change_recent: last bar vs previous bar (~15m change)
      - change_window: first vs last bar (~105m / ~1.75h window)

    Binance ``openInterestHist`` returns:
      - sumOpenInterest: str (OI in base currency)
      - sumOpenInterestValue: str (OI in USD)
      - timestamp: int (ms)
    """
    if not bars or len(bars) < 2:
        return 0.0, 0.0, 0.0

    oi_values = [float(b.get("sumOpenInterestValue", 0)) for b in bars]
    oi_usd = oi_values[-1]

    # Recent change (last vs previous bar)
    prev = oi_values[-2]
    chg_recent = ((oi_usd - prev) / prev * 100) if prev > 0 else 0.0

    # Window change (first vs last — full lookback)
    chg_window = 0.0
    first = oi_values[0]
    chg_window = ((oi_usd - first) / first * 100) if first > 0 else 0.0

    return oi_usd, chg_window, chg_recent


# ---------------------------------------------------------------------------
# Main fetch orchestrator
# ---------------------------------------------------------------------------

async def fetch_exchange_derivatives(
    symbols: Optional[List[str]] = None,
    price_changes: Optional[Dict[str, float]] = None,
) -> tuple:
    """Fetch derivatives data from Binance + Bybit + OKX.

    Parameters
    ----------
    symbols : list[str] or None
        Scanner symbols (e.g. ['BTC/USDT', 'ETH/USDT']).
        If None, fetches all available Binance USDT perps.
    price_changes : dict[str, float] or None
        Recent price change % per scanner symbol — for CVD divergence.

    Returns
    -------
    (metrics_dict, cvd_dict, cb_premium)
        metrics_dict: Dict[str, DerivativesMetrics] keyed by scanner symbol
        cvd_dict: Dict[str, CVDResult] keyed by coin base (e.g. 'BTC')
        cb_premium: CBPremium or None
    """
    if _cache.is_valid():
        return _cache.data, _cache.cvd, _cache.cb_premium

    # Determine coins to fetch
    if symbols:
        coins = list({_scanner_to_coin(s) for s in symbols})
    else:
        coins = []  # Will discover from Binance futures tickers

    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
    metrics: Dict[str, DerivativesMetrics] = {}
    cvd_results: Dict[str, CVDResult] = {}

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # --- Phase 0: Discover coins if not provided ---
            if not coins:
                fut_tickers = await _fetch_binance_futures_tickers(session)
                coins = list(fut_tickers.keys())

            # Sort: priority coins first
            priority_set = set(_PRIORITY_COINS)
            coins_sorted = sorted(coins, key=lambda c: (0 if c in priority_set else 1, c))

            # --- Phase 1: Parallel bulk fetches ---
            spot_task = _fetch_binance_spot_tickers(session)
            futures_task = _fetch_binance_futures_tickers(session)
            spot_vols, futures_vols = await asyncio.gather(spot_task, futures_task)

            # --- Phase 2: Per-coin parallel fetches (all exchanges) ---
            bin_sem = asyncio.Semaphore(_BINANCE_CONCURRENCY)
            bybit_sem = asyncio.Semaphore(_BYBIT_CONCURRENCY)
            okx_sem = asyncio.Semaphore(_OKX_CONCURRENCY)

            # Build all tasks
            taker_tasks = {c: _fetch_binance_taker_ratio(session, c, bin_sem) for c in coins_sorted}
            retail_lsr_tasks = {c: _fetch_binance_retail_lsr(session, c, bin_sem) for c in coins_sorted}
            top_lsr_tasks = {c: _fetch_binance_top_lsr(session, c, bin_sem) for c in coins_sorted}
            oi_hist_tasks = {c: _fetch_binance_oi_history(session, c, bin_sem) for c in coins_sorted}
            bybit_oi_tasks = {c: _fetch_bybit_oi(session, c, bybit_sem) for c in coins_sorted}
            okx_oi_tasks = {c: _fetch_okx_oi(session, c, okx_sem) for c in coins_sorted}

            # Run all in parallel
            all_tasks = []
            task_keys = []

            for c in coins_sorted:
                all_tasks.extend([
                    taker_tasks[c], retail_lsr_tasks[c], top_lsr_tasks[c],
                    oi_hist_tasks[c], bybit_oi_tasks[c], okx_oi_tasks[c],
                ])
                task_keys.extend([
                    ("taker", c), ("retail_lsr", c), ("top_lsr", c),
                    ("oi_hist", c), ("bybit_oi", c), ("okx_oi", c),
                ])

            results = await asyncio.gather(*all_tasks, return_exceptions=True)

            # Organize results
            taker_data: Dict[str, dict] = {}
            retail_lsr_data: Dict[str, float] = {}
            top_lsr_data: Dict[str, float] = {}
            oi_hist_data: Dict[str, list] = {}
            bybit_oi_data: Dict[str, float] = {}
            okx_oi_data: Dict[str, float] = {}

            for i, result in enumerate(results):
                if isinstance(result, Exception) or result is None:
                    continue
                kind, coin = task_keys[i]
                if kind == "taker" and isinstance(result, dict):
                    taker_data[coin] = result
                elif kind == "retail_lsr" and isinstance(result, dict):
                    retail_lsr_data[coin] = result["ratio"]
                elif kind == "top_lsr" and isinstance(result, dict):
                    top_lsr_data[coin] = result["ratio"]
                elif kind == "oi_hist" and isinstance(result, dict):
                    oi_hist_data[coin] = result["bars"]
                elif kind == "bybit_oi" and isinstance(result, dict):
                    bybit_oi_data[coin] = result["oi_base"]
                elif kind == "okx_oi" and isinstance(result, dict):
                    okx_oi_data[coin] = result["oi_usd"]

            # --- Phase 3: Assemble metrics per coin ---
            now = time.time()
            price_map = price_changes or {}

            for coin in coins_sorted:
                scanner_sym = f"{coin}/USDT"

                # OI from Binance history
                binance_oi_usd = 0.0
                oi_chg_4h = 0.0
                oi_chg_24h = 0.0
                if coin in oi_hist_data:
                    binance_oi_usd, oi_chg_4h, oi_chg_24h = _compute_oi_change(oi_hist_data[coin])

                # Bybit OI is in base currency — convert to USD using implied price
                # OKX provides oiUsd directly
                bybit_oi_usd = 0.0
                okx_oi_usd = okx_oi_data.get(coin, 0.0)  # Already in USD

                if coin in bybit_oi_data and binance_oi_usd > 0 and coin in oi_hist_data and oi_hist_data[coin]:
                    last_bar = oi_hist_data[coin][-1]
                    oi_base = float(last_bar.get("sumOpenInterest", 0))
                    price_est = binance_oi_usd / oi_base if oi_base > 0 else 0.0
                    bybit_oi_usd = bybit_oi_data[coin] * price_est

                oi_total = binance_oi_usd + bybit_oi_usd + okx_oi_usd

                # Spot dominance
                spot_vol = spot_vols.get(coin, 0.0)
                fut_vol = futures_vols.get(coin, 0.0)
                total_vol = spot_vol + fut_vol
                sf_ratio = spot_vol / total_vol if total_vol > 0 else 0.0

                if sf_ratio > _SPOT_LED_RATIO:
                    dominance = "SPOT_LED"
                elif fut_vol > 0 and sf_ratio < _FUTURES_LED_RATIO:
                    dominance = "FUTURES_LED"
                else:
                    dominance = "NEUTRAL"

                m = DerivativesMetrics(
                    coin=coin,
                    oi_total_usd=oi_total,
                    oi_binance_usd=binance_oi_usd,
                    oi_bybit_usd=bybit_oi_usd,
                    oi_okx_usd=okx_oi_usd,
                    oi_change_pct_4h=round(oi_chg_4h, 2),
                    oi_change_pct_24h=round(oi_chg_24h, 2),
                    long_short_ratio_4h=retail_lsr_data.get(coin, 1.0),
                    top_trader_lsr=top_lsr_data.get(coin, 1.0),
                    spot_volume_usd=spot_vol,
                    futures_volume_usd=fut_vol,
                    spot_futures_ratio=round(sf_ratio, 3),
                    spot_dominance=dominance,
                    timestamp=now,
                )
                metrics[scanner_sym] = m

                # CVD
                if coin in taker_data:
                    price_chg = price_map.get(scanner_sym)
                    cvd = _compute_cvd(taker_data[coin]["bars"], price_chg)
                    cvd.coin = coin
                    cvd_results[coin] = cvd

        # Log summary
        btc = metrics.get("BTC/USDT")
        logger.info(
            "Exchange derivatives: %d coins fetched in shadow mode "
            "(BTC OI total=$%.0fM, BIN=$%.0fM, BYB=$%.0fM, OKX=$%.0fM)",
            len(metrics),
            (btc.oi_total_usd / 1e6) if btc else 0.0,
            (btc.oi_binance_usd / 1e6) if btc else 0.0,
            (btc.oi_bybit_usd / 1e6) if btc else 0.0,
            (btc.oi_okx_usd / 1e6) if btc else 0.0,
        )

        # Cache results
        _cache.put(metrics, cvd_results)
        return metrics, cvd_results, None

    except Exception as exc:
        logger.error("Exchange derivatives fetch failed: %s", exc)
        # Return stale cache if available
        if _cache.data:
            return _cache.data, _cache.cvd or {}, _cache.cb_premium
        return {}, {}, None


# ---------------------------------------------------------------------------
# Comparison helper (for shadow mode logging)
# ---------------------------------------------------------------------------

def compare_with_coinglass(
    exchange_metrics: Dict[str, DerivativesMetrics],
    exchange_cvd: Dict[str, CVDResult],
    cg_metrics: dict,
    cg_cvd: dict,
) -> List[dict]:
    """Compare exchange derivatives data with CoinGlass for logging.

    Returns a list of comparison dicts for JSON serialization.
    """
    comparisons = []
    for sym, ex in exchange_metrics.items():
        coin = ex.coin
        cg = cg_metrics.get(sym)
        if cg is None:
            continue

        comp = {
            "symbol": sym,
            "oi_binance_usd": ex.oi_binance_usd,
            "oi_total_usd": ex.oi_total_usd,
            "oi_cg_usd": getattr(cg, "open_interest_usd", 0),
            "oi_chg_4h_exchange": ex.oi_change_pct_4h,
            "oi_chg_4h_cg": getattr(cg, "oi_change_pct_4h", 0),
            "retail_lsr_exchange": ex.long_short_ratio_4h,
            "retail_lsr_cg": getattr(cg, "long_short_ratio_4h", 0),
            "top_lsr_exchange": ex.top_trader_lsr,
            "top_lsr_cg": getattr(cg, "top_trader_lsr", 0),
            "spot_dominance_exchange": ex.spot_dominance,
            "spot_dominance_cg": getattr(cg, "spot_dominance", "NEUTRAL"),
        }

        # CVD comparison
        ex_cvd = exchange_cvd.get(coin)
        cg_cvd_item = cg_cvd.get(coin)
        if ex_cvd:
            comp["cvd_trend_exchange"] = ex_cvd.cvd_trend
            comp["cvd_bsr_exchange"] = ex_cvd.buy_sell_ratio
        if cg_cvd_item:
            comp["cvd_trend_cg"] = getattr(cg_cvd_item, "cvd_trend", "NEUTRAL")
            comp["cvd_bsr_cg"] = getattr(cg_cvd_item, "buy_sell_ratio", 1.0)

        comparisons.append(comp)

    return comparisons


# ---------------------------------------------------------------------------
# Test endpoint helper
# ---------------------------------------------------------------------------

async def test_binance_connectivity() -> dict:
    """Test if Binance /futures/data/ endpoints are reachable.

    Returns a dict with status and sample data.
    """
    url = f"{_BINANCE_FAPI_BASE}/futures/data/topLongShortPositionRatio"
    params = {"symbol": "BTCUSDT", "period": "4h", "limit": 1}
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                status = resp.status
                body = await resp.json()
                return {
                    "status": "ok" if status == 200 else "error",
                    "http_status": status,
                    "endpoint": "/futures/data/topLongShortPositionRatio",
                    "sample": body[:1] if isinstance(body, list) else body,
                    "timestamp": time.time(),
                }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "endpoint": "/futures/data/topLongShortPositionRatio",
            "timestamp": time.time(),
        }
