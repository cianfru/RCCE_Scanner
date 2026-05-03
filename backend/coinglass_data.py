"""
coinglass_data.py
~~~~~~~~~~~~~~~~~
Fetches aggregated positioning data from CoinGlass API v4 (Hobbyist plan).

Available endpoints (empirically verified):
  BULK (1 call each, ~1000 coins):
    GET /api/futures/funding-rate/exchange-list  → per-exchange funding rates
    GET /api/futures/liquidation/coin-list       → 24h/12h/4h/1h liquidations

  PER-COIN (top N scanned coins, cached 30 min):
    GET /api/futures/open-interest/aggregated-history   → OI OHLC
    GET /api/futures/aggregated-taker-buy-sell-volume/history  → futures CVD
    GET /api/spot/aggregated-taker-buy-sell-volume/history     → spot CVD
    GET /api/futures/global-long-short-account-ratio/history   → retail LSR
    GET /api/futures/top-long-short-account-ratio/history      → smart-money LSR

  MACRO (global, cached 1 hr):
    GET /api/coinbase-premium-index              → institutional buy pressure
    GET /api/etf/bitcoin/flow-history            → BTC ETF net flows
    GET /api/index/fear-greed-history            → Fear & Greed Index (in market_data.py)

Auth: Header ``CG-API-KEY``

Not available on Hobbyist:
  /api/futures/coins-markets          (bulk aggregate — requires higher plan)
  /api/futures/cvd/history            (use taker buy-sell instead)
  /api/hyperliquid/whale-alert        (Pro+)
  /api/futures/netflow-list           (Pro+)
  /api/spot/coins-markets             (Pro+)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API config
# ---------------------------------------------------------------------------

_BASE_URL      = "https://open-api-v4.coinglass.com"
_AUTH_HEADER   = "CG-API-KEY"

# Bulk endpoints (all coins in one call)
_PATH_FUNDING_BULK = "/api/futures/funding-rate/exchange-list"
_PATH_LIQ_BULK     = "/api/futures/liquidation/coin-list"

# Per-coin endpoints
_PATH_OI_HIST        = "/api/futures/open-interest/aggregated-history"
_PATH_FUT_TAKER      = "/api/futures/aggregated-taker-buy-sell-volume/history"
_PATH_SPOT_TAKER     = "/api/spot/aggregated-taker-buy-sell-volume/history"
_PATH_LSR_GLOBAL     = "/api/futures/global-long-short-account-ratio/history"
_PATH_LSR_TOP        = "/api/futures/top-long-short-account-ratio/history"

# Macro endpoints
_PATH_CB_PREMIUM     = "/api/coinbase-premium-index"
_PATH_ETF_FLOWS      = "/api/etf/bitcoin/flow-history"

# Timing
_BULK_CACHE_TTL      = 5 * 60        # 5 min  (matches scan interval)
_PER_COIN_CACHE_TTL  = 30 * 60       # 30 min (data changes slowly)
_MACRO_CACHE_TTL     = 60 * 60       # 1 hour

# Concurrency
_REQUEST_SEMAPHORE   = 8             # max simultaneous HTTP requests
_REQUEST_TIMEOUT_S   = 25
_MAX_RETRIES         = 2
_RETRY_DELAY_S       = 3.0

# Per-coin fetch limits
_PER_COIN_LIMIT      = 30            # max coins for one-shot fetch (legacy, used as fallback)
_DRIP_INTERVAL_S     = 1.5           # seconds between per-coin fetches in drip mode
_DRIP_CYCLE_PAUSE_S  = 30            # pause after completing a full rotation

# Rate limiting — Hobbyist plan allows ~30 req/min but empirically
# needs wider gap to avoid 429s across 5 endpoints per coin
_MIN_REQUEST_GAP_S   = 4.5           # ~13 req/min (conservative, avoids 429s)

# Priority symbols — fetched first in drip loop so majors always have data
_PRIORITY_COINS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "MATIC/USDT", "UNI/USDT", "ATOM/USDT", "LTC/USDT", "NEAR/USDT",
    "ARB/USDT", "OP/USDT", "SUI/USDT", "APT/USDT", "HYPE/USDT",
]

# Taker volume exchange lists
_FUTURES_EXCHANGES   = "Binance,OKX,Bybit"
_SPOT_EXCHANGE       = "Binance"


def _get_api_key() -> str:
    key = os.environ.get("COINGLASS_API_KEY", "")
    if not key:
        logger.warning("COINGLASS_API_KEY not set — CoinGlass data will be unavailable")
    return key


# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------

_CG_PREFIX_MAP = {
    "1000PEPE":   "PEPE",
    "1000BONK":   "BONK",
    "1000FLOKI":  "FLOKI",
    "1000SHIB":   "SHIB",
    "1MBABYDOGE": "BABYDOGE",
}

def _scanner_to_coin(scanner_sym: str) -> str:
    """'BTC/USDT' → 'BTC'"""
    return scanner_sym.split("/")[0]

def _coin_to_pair(coin: str) -> str:
    """'BTC' → 'BTCUSDT'  (needed for LSR endpoints)"""
    return f"{coin}USDT"


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class CoinglassMetrics:
    """Per-coin aggregated positioning data from CoinGlass."""
    coin: str = ""
    current_price: float = 0.0

    # Funding rate — Binance preferred, else cross-exchange mean; hourly
    funding_rate: float = 0.0

    # Open interest (aggregated close value from OI history)
    open_interest_usd: float = 0.0
    oi_change_pct_1h: float = 0.0   # estimated from recent bars
    oi_change_pct_4h: float = 0.0   # last 4h bar change
    oi_change_pct_24h: float = 0.0  # 6-bar × 4h window

    # Price changes (populated from CCXT by scanner — not from CoinGlass)
    price_change_pct_1h: float = 0.0
    price_change_pct_4h: float = 0.0
    price_change_pct_24h: float = 0.0

    # Long/short ratios (global account ratio from Binance)
    long_short_ratio_4h: float = 1.0    # most recent bar
    top_trader_lsr: float = 1.0         # smart-money LSR

    # Liquidations (bulk endpoint — all timeframes)
    liquidation_usd_24h: float = 0.0
    long_liquidation_usd_24h: float = 0.0
    short_liquidation_usd_24h: float = 0.0
    liquidation_usd_4h: float = 0.0
    liquidation_usd_1h: float = 0.0

    # Spot dominance (from spot vs futures taker volume)
    spot_volume_usd: float = 0.0
    futures_volume_usd: float = 0.0
    spot_futures_ratio: float = 0.0   # spot / (spot + futures)
    spot_dominance: str = "NEUTRAL"   # SPOT_LED | FUTURES_LED | NEUTRAL

    # OI/market-cap ratio — not available on Hobbyist; kept for compat
    oi_market_cap_ratio: float = 0.0

    timestamp: float = 0.0


@dataclass
class CoinglassCVD:
    """Per-coin CVD derived from taker buy/sell volume history."""
    coin: str = ""
    cvd_trend: str = "NEUTRAL"       # BULLISH | BEARISH | NEUTRAL
    cvd_value: float = 0.0           # net (buy - sell) USD over lookback
    cvd_divergence: bool = False     # price dir ≠ CVD dir
    buy_volume_usd: float = 0.0
    sell_volume_usd: float = 0.0
    buy_sell_ratio: float = 1.0      # buy / sell
    # VPIN — Volume-Synchronized Probability of Informed Trading
    # mean(|buy_i - sell_i| / (buy_i + sell_i)) over last N bars. Range 0..1.
    # 0 = perfectly balanced flow; 1 = fully one-sided (toxic/informed).
    vpin: float = 0.0
    vpin_label: str = "BALANCED"     # BALANCED | ELEVATED | TOXIC
    timestamp: float = 0.0


@dataclass
class CoinglassSpot:
    """Per-coin spot dominance (derived from taker volume comparison)."""
    coin: str = ""
    spot_volume_usd: float = 0.0
    spot_price_change_24h: float = 0.0
    futures_volume_usd: float = 0.0
    spot_futures_ratio: float = 0.0
    spot_dominance: str = "NEUTRAL"  # SPOT_LED | FUTURES_LED | NEUTRAL
    timestamp: float = 0.0


@dataclass
class CoinglassMacro:
    """Global macro signals (BTC ETF flows, Coinbase premium)."""
    coinbase_premium_rate: float = 0.0   # positive = premium (institutional buying)
    coinbase_premium: float = 0.0        # raw premium USD
    etf_flow_usd_7d: float = 0.0        # sum of last 7 daily ETF flows
    etf_flow_usd_1d: float = 0.0        # latest daily flow
    etf_signal: str = "NEUTRAL"          # INFLOW | OUTFLOW | NEUTRAL
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# TTL caches
# ---------------------------------------------------------------------------

@dataclass
class _TTLCache:
    data: Any = None
    expires_at: float = 0.0

    def get(self) -> Any:
        if self.data is not None and time.monotonic() < self.expires_at:
            return self.data
        return None

    def put(self, data: Any, ttl: float) -> None:
        self.data = data
        self.expires_at = time.monotonic() + ttl

    def get_fallback(self) -> Any:
        return self.data


@dataclass
class _PerCoinCacheEntry:
    data: dict = field(default_factory=dict)  # coin → raw per-coin results
    expires_at: float = 0.0


_bulk_cache      = _TTLCache()   # Dict[str, CoinglassMetrics] (funding + liq)
_per_coin_cache  = _TTLCache()   # Dict[str, dict]             (CVD, OI, LSR)
_macro_cache     = _TTLCache()   # CoinglassMacro


# ---------------------------------------------------------------------------
# Low-level HTTP helper
# ---------------------------------------------------------------------------

async def _get_data(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    api_key: str,
    path: str,
    params: dict,
) -> Any:
    """GET a CoinGlass v4 endpoint; returns ``data`` field or [] on failure."""
    async with sem:
        try:
            url = f"{_BASE_URL}{path}"
            headers = {_AUTH_HEADER: api_key, "Accept": "application/json"}
            async with session.get(url, params=params, headers=headers) as resp:
                resp.raise_for_status()
                body = await resp.json()

            code = str(body.get("code", ""))
            if code not in ("0", "200"):
                logger.debug(
                    "CoinGlass %s returned code=%s msg=%s",
                    path, code, body.get("msg", "")[:80],
                )
                return []
            return body.get("data") or []
        except Exception as exc:
            logger.debug("CoinGlass request %s error: %s", path, exc)
            return []


# ---------------------------------------------------------------------------
# Phase 1 — Bulk funding fetch  (1 call → all coins)
# ---------------------------------------------------------------------------

async def _fetch_bulk_funding(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    api_key: str,
) -> Dict[str, CoinglassMetrics]:
    """Build a CoinglassMetrics stub for every coin from the funding bulk call."""
    data = await _get_data(session, sem, api_key, _PATH_FUNDING_BULK, {})
    if not data:
        return {}

    result: Dict[str, CoinglassMetrics] = {}
    for item in data:
        raw_sym = item.get("symbol", "")
        if not raw_sym:
            continue
        coin = _CG_PREFIX_MAP.get(raw_sym, raw_sym)
        scanner_sym = f"{coin}/USDT"

        # Compute hourly funding rate (Binance preferred, else cross-exchange mean)
        rates_hourly: list[float] = []
        binance_hourly: Optional[float] = None

        for ex in item.get("stablecoin_margin_list") or []:
            rate = ex.get("funding_rate")
            if rate is None:
                continue
            interval = float(ex.get("funding_rate_interval") or 8)
            hourly = float(rate) / interval
            rates_hourly.append(hourly)
            if ex.get("exchange", "").lower() == "binance":
                binance_hourly = hourly

        funding_rate = (
            binance_hourly if binance_hourly is not None
            else (sum(rates_hourly) / len(rates_hourly) if rates_hourly else 0.0)
        )

        result[scanner_sym] = CoinglassMetrics(
            coin=coin,
            funding_rate=funding_rate,
            timestamp=time.time(),
        )

    logger.info("CoinGlass funding: %d coins loaded", len(result))
    return result


# ---------------------------------------------------------------------------
# Phase 2 — Bulk liquidation merge  (1 call → all coins)
# ---------------------------------------------------------------------------

async def _fetch_bulk_liquidations(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    api_key: str,
    metrics: Dict[str, CoinglassMetrics],
) -> None:
    """Merge 24h/4h/1h liquidation data into existing metrics dict in-place."""
    data = await _get_data(session, sem, api_key, _PATH_LIQ_BULK, {})
    if not data:
        return

    for item in data:
        raw_sym = item.get("symbol", "")
        if not raw_sym:
            continue
        coin = _CG_PREFIX_MAP.get(raw_sym, raw_sym)
        scanner_sym = f"{coin}/USDT"
        if scanner_sym not in metrics:
            continue

        m = metrics[scanner_sym]
        m.liquidation_usd_24h       = float(item.get("liquidation_usd_24h") or 0.0)
        m.long_liquidation_usd_24h  = float(item.get("long_liquidation_usd_24h") or 0.0)
        m.short_liquidation_usd_24h = float(item.get("short_liquidation_usd_24h") or 0.0)
        m.liquidation_usd_4h        = float(item.get("liquidation_usd_4h") or 0.0)
        m.liquidation_usd_1h        = float(item.get("liquidation_usd_1h") or 0.0)

    liq_count = sum(1 for m in metrics.values() if m.liquidation_usd_24h > 0)
    btc = metrics.get("BTC/USDT")
    logger.info(
        "CoinGlass liquidations: %d coins (BTC 24h liq=$%.1fM long=$%.1fM short=$%.1fM)",
        liq_count,
        (btc.liquidation_usd_24h / 1e6) if btc else 0,
        (btc.long_liquidation_usd_24h / 1e6) if btc else 0,
        (btc.short_liquidation_usd_24h / 1e6) if btc else 0,
    )


# ---------------------------------------------------------------------------
# Phase 3 — Per-coin detail fetch (OI + CVD + LSR + spot dominance)
# ---------------------------------------------------------------------------

_last_req_ts: float = 0.0
_rate_limit_lock = asyncio.Lock()


async def _rate_limited_get(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    api_key: str,
    path: str,
    params: dict,
) -> Any:
    """Rate-limited wrapper around _get_data.

    Enforces a minimum gap of _MIN_REQUEST_GAP_S between consecutive API calls
    to stay within the Hobbyist plan rate limit (~30 req/min).
    Serialized via lock to prevent concurrent coroutines from defeating the gap.
    """
    global _last_req_ts
    async with _rate_limit_lock:
        now = time.monotonic()
        gap = _MIN_REQUEST_GAP_S - (now - _last_req_ts)
        if gap > 0:
            await asyncio.sleep(gap)
        _last_req_ts = time.monotonic()
    return await _get_data(session, sem, api_key, path, params)


async def _fetch_single_coin_detail(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    api_key: str,
    scanner_sym: str,
    price_change_pct: Optional[float] = None,
) -> Tuple[str, dict]:
    """Fetch OI history, futures taker vol, spot taker vol, and LSR for one coin.

    Calls are serialized (not parallel) to respect the API rate limit.
    Returns ``(scanner_sym, detail_dict)`` where detail_dict has keys:
    ``oi``, ``fut_taker``, ``spot_taker``, ``lsr_global``, ``lsr_top``.
    """
    coin = _scanner_to_coin(scanner_sym)
    pair = _coin_to_pair(coin)

    def _safe(v: Any) -> list:
        return v if isinstance(v, list) else []

    oi = await _rate_limited_get(session, sem, api_key, _PATH_OI_HIST, {
        "symbol": coin, "interval": "h4", "limit": 7,
    })
    fut = await _rate_limited_get(session, sem, api_key, _PATH_FUT_TAKER, {
        "symbol": coin, "exchange_list": _FUTURES_EXCHANGES,
        "interval": "h4", "limit": 6,
    })
    spot = await _rate_limited_get(session, sem, api_key, _PATH_SPOT_TAKER, {
        "symbol": coin, "exchange_list": _SPOT_EXCHANGE,
        "interval": "h4", "limit": 6,
    })
    lsr = await _rate_limited_get(session, sem, api_key, _PATH_LSR_GLOBAL, {
        "symbol": pair, "exchange": "Binance", "interval": "h4", "limit": 1,
    })
    top_lsr = await _rate_limited_get(session, sem, api_key, _PATH_LSR_TOP, {
        "symbol": pair, "exchange": "Binance", "interval": "h4", "limit": 1,
    })

    return scanner_sym, {
        "oi":        _safe(oi),
        "fut_taker": _safe(fut),
        "spot_taker": _safe(spot),
        "lsr_global": _safe(lsr),
        "lsr_top":    _safe(top_lsr),
        "price_change_pct": price_change_pct,
    }


def _parse_detail(coin: str, detail: dict) -> Tuple[
    Optional[float], Optional[float], Optional[float],  # OI, oi_4h, oi_24h
    Optional["CoinglassCVD"], Optional["CoinglassSpot"],
    float, float,  # lsr_global, lsr_top
]:
    """Parse raw per-coin detail into structured values."""

    # --- OI ---
    oi_bars = detail.get("oi") or []
    oi_usd: Optional[float] = None
    oi_chg_4h: Optional[float] = None
    oi_chg_24h: Optional[float] = None
    if len(oi_bars) >= 2:
        closes = [float(b.get("close") or 0) for b in oi_bars]
        oi_usd = closes[-1]
        oi_chg_4h = ((closes[-1] - closes[-2]) / closes[-2]) * 100 if closes[-2] else 0.0
        if len(closes) >= 7:
            oi_chg_24h = ((closes[-1] - closes[-7]) / closes[-7]) * 100 if closes[-7] else 0.0

    # --- Futures CVD ---
    fut_bars = detail.get("fut_taker") or []
    cvd: Optional[CoinglassCVD] = None
    if fut_bars:
        total_buy  = sum(float(b.get("aggregated_buy_volume_usd") or 0) for b in fut_bars)
        total_sell = sum(float(b.get("aggregated_sell_volume_usd") or 0) for b in fut_bars)
        cvd_value  = total_buy - total_sell
        bsr = total_buy / total_sell if total_sell > 0 else 1.0

        if cvd_value > 0 and bsr > 1.05:
            cvd_trend = "BULLISH"
        elif cvd_value < 0 and bsr < 0.95:
            cvd_trend = "BEARISH"
        else:
            cvd_trend = "NEUTRAL"

        price_chg = detail.get("price_change_pct")
        divergence = False
        if price_chg is not None:
            if (price_chg > 0 and cvd_trend == "BEARISH") or \
               (price_chg < 0 and cvd_trend == "BULLISH"):
                divergence = True

        # VPIN — volume-synchronized probability of informed trading.
        # Each bar is a volume bucket; imbalance = |buy-sell|/(buy+sell).
        # High VPIN (>0.5) indicates persistent one-sided flow ("toxic" for MMs).
        vpin_window = fut_bars[-20:] if len(fut_bars) >= 20 else fut_bars
        vpin_samples = []
        for b in vpin_window:
            bb = float(b.get("aggregated_buy_volume_usd") or 0)
            ss = float(b.get("aggregated_sell_volume_usd") or 0)
            tot = bb + ss
            if tot > 0:
                vpin_samples.append(abs(bb - ss) / tot)
        vpin_value = sum(vpin_samples) / len(vpin_samples) if vpin_samples else 0.0
        if vpin_value >= 0.55:
            vpin_label = "TOXIC"
        elif vpin_value >= 0.30:
            vpin_label = "ELEVATED"
        else:
            vpin_label = "BALANCED"

        cvd = CoinglassCVD(
            coin=coin,
            cvd_trend=cvd_trend,
            cvd_value=cvd_value,
            cvd_divergence=divergence,
            buy_volume_usd=total_buy,
            sell_volume_usd=total_sell,
            buy_sell_ratio=round(bsr, 3),
            vpin=round(vpin_value, 4),
            vpin_label=vpin_label,
            timestamp=time.time(),
        )

    # --- Spot dominance ---
    spot_bars  = detail.get("spot_taker") or []
    spot_entry: Optional[CoinglassSpot] = None
    if spot_bars or fut_bars:
        spot_vol    = sum(float(b.get("aggregated_buy_volume_usd") or 0) +
                         float(b.get("aggregated_sell_volume_usd") or 0) for b in spot_bars)
        futures_vol = sum(float(b.get("aggregated_buy_volume_usd") or 0) +
                         float(b.get("aggregated_sell_volume_usd") or 0) for b in fut_bars)
        total_vol = spot_vol + futures_vol
        ratio = spot_vol / total_vol if total_vol > 0 else 0.0
        if ratio > 0.55:
            dominance = "SPOT_LED"
        elif futures_vol > 0 and ratio < 0.35:
            dominance = "FUTURES_LED"
        else:
            dominance = "NEUTRAL"

        spot_entry = CoinglassSpot(
            coin=coin,
            spot_volume_usd=spot_vol,
            futures_volume_usd=futures_vol,
            spot_futures_ratio=round(ratio, 4),
            spot_dominance=dominance,
            timestamp=time.time(),
        )

    # --- LSR ---
    lsr_global = 1.0
    lsr_rows = detail.get("lsr_global") or []
    if lsr_rows:
        lsr_global = float(lsr_rows[-1].get("global_account_long_short_ratio") or 1.0)

    top_lsr = 1.0
    top_rows = detail.get("lsr_top") or []
    if top_rows:
        top_lsr = float(top_rows[-1].get("top_account_long_short_ratio") or 1.0)

    return oi_usd, oi_chg_4h, oi_chg_24h, cvd, spot_entry, lsr_global, top_lsr


# ---------------------------------------------------------------------------
# Macro signals
# ---------------------------------------------------------------------------

async def _fetch_macro(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    api_key: str,
) -> CoinglassMacro:
    """Fetch Coinbase premium index and BTC ETF flows."""
    cb_task  = _get_data(session, sem, api_key, _PATH_CB_PREMIUM, {
        "symbol": "BTC", "interval": "h4", "limit": 1,
    })
    # Note: ETF endpoint ignores limit param — returns all data since launch.
    # We slice the last 7 rows after receiving.
    etf_task = _get_data(session, sem, api_key, _PATH_ETF_FLOWS, {
        "interval": "daily",
    })
    cb_data, etf_data = await asyncio.gather(cb_task, etf_task, return_exceptions=True)

    macro = CoinglassMacro(timestamp=time.time())

    # Coinbase premium
    if isinstance(cb_data, list) and cb_data:
        row = cb_data[-1]
        macro.coinbase_premium_rate = float(row.get("premium_rate") or 0.0)
        macro.coinbase_premium      = float(row.get("premium") or 0.0)

    # ETF flows — endpoint ignores limit; slice last 7 trading days
    if isinstance(etf_data, list) and etf_data:
        recent = etf_data[-7:]
        flows = [float(r.get("flow_usd") or 0) for r in recent]
        macro.etf_flow_usd_7d = sum(flows)
        macro.etf_flow_usd_1d = flows[-1] if flows else 0.0
        if macro.etf_flow_usd_7d > 50_000_000:
            macro.etf_signal = "INFLOW"
        elif macro.etf_flow_usd_7d < -50_000_000:
            macro.etf_signal = "OUTFLOW"

    logger.info(
        "CoinGlass macro: CB premium=%.4f%% ETF_7d=$%.0fM signal=%s",
        macro.coinbase_premium_rate * 100,
        macro.etf_flow_usd_7d / 1e6,
        macro.etf_signal,
    )
    return macro


# ---------------------------------------------------------------------------
# Internal caches for per-coin CVD / Spot / macro
# ---------------------------------------------------------------------------

_cvd_store:   Dict[str, CoinglassCVD]   = {}   # coin → latest CVD
_spot_store:  Dict[str, CoinglassSpot]  = {}   # scanner_sym → latest spot

# Per-coin detail store (drip-fed, entries expire after 30 min of no update)
_per_coin_detail: Dict[str, dict] = {}         # scanner_sym → raw detail dict
_per_coin_detail_ts: Dict[str, float] = {}     # scanner_sym → last-updated monotonic ts
_PER_COIN_DETAIL_TTL_S: float = 30 * 60        # 30 minutes


# ---------------------------------------------------------------------------
# Background drip loop — fetches 1 coin every _DRIP_INTERVAL_S
# ---------------------------------------------------------------------------

async def run_coinglass_drip() -> None:
    """Continuously drip-feed per-coin CoinGlass data (OI, CVD, LSR, spot).

    Fetches one coin at a time, with each API call rate-limited to
    ~13 req/min.  Each coin requires 5 calls (~23s per coin).
    Priority coins (BTC, ETH, SOL, etc.) are fetched first.
    A full rotation takes ~75 min but LSR data updates every 4h
    anyway, so this is fine.

    Results are merged into the bulk CoinglassMetrics store so the
    scanner always has the latest available data.
    """
    logger.info("CoinGlass drip loop starting ...")
    api_key = _get_api_key()
    if not api_key:
        logger.warning("CoinGlass drip loop: no API key — exiting")
        return

    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
    sem = asyncio.Semaphore(3)  # low concurrency for drip

    # Wait for first bulk fetch to populate the symbol list
    while _bulk_cache.data is None:
        await asyncio.sleep(5)

    cycle = 0
    while True:
        try:
            bulk = _bulk_cache.get_fallback()
            if not bulk:
                await asyncio.sleep(10)
                continue

            # Expire stale per-coin entries
            now_mono = time.monotonic()
            stale = [s for s, ts in _per_coin_detail_ts.items()
                     if now_mono - ts > _PER_COIN_DETAIL_TTL_S]
            for s in stale:
                _per_coin_detail.pop(s, None)
                _per_coin_detail_ts.pop(s, None)
            if stale:
                logger.info("CoinGlass drip: expired %d stale per-coin entries", len(stale))

            # Sort: priority coins first, then the rest
            all_syms = set(bulk.keys())
            priority = [s for s in _PRIORITY_COINS if s in all_syms]
            rest = sorted(all_syms - set(priority))
            target_syms = priority + rest
            cycle += 1
            fetched = 0

            async with aiohttp.ClientSession(timeout=timeout) as session:
                for sym in target_syms:
                    try:
                        result = await _fetch_single_coin_detail(
                            session, sem, api_key, sym,
                        )
                        if isinstance(result, Exception):
                            continue

                        sym_out, detail = result
                        _per_coin_detail[sym_out] = detail
                        _per_coin_detail_ts[sym_out] = time.monotonic()

                        # Parse and merge immediately
                        coin = _scanner_to_coin(sym_out)
                        oi_usd, oi_4h, oi_24h, cvd, spot, lsr, top_lsr = _parse_detail(coin, detail)

                        # Debug: trace LSR for BTC (downgraded — fires once
                        # per drip rotation per BTC, ~every 4 min)
                        if coin == "BTC":
                            raw_g = detail.get("lsr_global") or []
                            raw_t = detail.get("lsr_top") or []
                            logger.debug(
                                "DRIP LSR BTC: raw_global=%s raw_top=%s lsr=%.4f top=%.4f",
                                raw_g[:1] if raw_g else "EMPTY",
                                raw_t[:1] if raw_t else "EMPTY",
                                lsr, top_lsr,
                            )

                        if cvd is not None:
                            _cvd_store[coin] = cvd
                        if spot is not None:
                            _spot_store[sym_out] = spot

                        if sym_out in bulk:
                            m = bulk[sym_out]
                            if oi_usd is not None:
                                m.open_interest_usd = oi_usd
                            if oi_4h is not None:
                                m.oi_change_pct_4h = round(oi_4h, 2)
                            if oi_24h is not None:
                                m.oi_change_pct_24h = round(oi_24h, 2)
                            if lsr != 1.0:
                                m.long_short_ratio_4h = lsr
                            if top_lsr != 1.0:
                                m.top_trader_lsr = top_lsr
                            if spot is not None:
                                m.spot_volume_usd    = spot.spot_volume_usd
                                m.futures_volume_usd = spot.futures_volume_usd
                                m.spot_futures_ratio = spot.spot_futures_ratio
                                m.spot_dominance     = spot.spot_dominance

                        fetched += 1

                    except Exception as exc:
                        logger.debug("Drip fetch %s failed: %s", sym, exc)

            logger.info(
                "CoinGlass drip cycle %d complete: %d/%d coins fetched",
                cycle, fetched, len(target_syms),
            )

            # Also update the per-coin cache so fetch_coinglass_metrics
            # doesn't re-fetch in burst mode
            _per_coin_cache.put(_per_coin_detail, _PER_COIN_CACHE_TTL * 10)

            await asyncio.sleep(_DRIP_CYCLE_PAUSE_S)

        except Exception as exc:
            logger.error("CoinGlass drip loop error: %s", exc)
            await asyncio.sleep(30)


# ---------------------------------------------------------------------------
# Main public fetch function
# ---------------------------------------------------------------------------

async def fetch_coinglass_metrics(
    symbols: Optional[List[str]] = None,
    price_changes: Optional[Dict[str, float]] = None,
) -> Dict[str, CoinglassMetrics]:
    """Fetch comprehensive positioning data from CoinGlass.

    Two-phase approach:
    1. Bulk calls (all coins, 5 min TTL): funding rates + liquidations.
    2. Per-coin calls (top N, 30 min TTL): OI history, futures/spot CVD, LSR.

    Parameters
    ----------
    symbols : list[str] or None
        Scanner symbols to filter to (e.g. ['BTC/USDT', 'ETH/USDT']).
    price_changes : dict[str, float] or None
        Recent price change % per scanner symbol — used for CVD divergence.

    Returns
    -------
    dict keyed by scanner symbol (e.g. 'BTC/USDT').
    """
    api_key = _get_api_key()
    if not api_key:
        return {}

    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
    sem = asyncio.Semaphore(_REQUEST_SEMAPHORE)

    # --- Check bulk cache ---
    bulk = _bulk_cache.get()
    if bulk is None:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # Phase 1: funding (bulk, all coins)
                    bulk = await _fetch_bulk_funding(session, sem, api_key)
                    if not bulk:
                        raise RuntimeError("Empty funding response")

                    # Phase 2: liquidations (bulk, all coins)
                    await _fetch_bulk_liquidations(session, sem, api_key, bulk)

                _bulk_cache.put(bulk, _BULK_CACHE_TTL)
                break

            except Exception as exc:
                logger.warning("CoinGlass bulk fetch attempt %d/%d failed: %s",
                               attempt + 1, _MAX_RETRIES + 1, exc)
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY_S)
        else:
            bulk = _bulk_cache.get_fallback() or {}
            if bulk:
                logger.warning("Using stale CoinGlass bulk data")

    if not bulk:
        return {}

    # --- Merge drip-loop data into bulk ---
    # The drip loop fetches 1 coin/1.5s and stores parsed data in _per_coin_detail.
    # When the bulk cache is refreshed (new dict), the drip loop's old reference is stale.
    # Re-merge here so the scanner always sees the latest drip-fetched LSR/OI/CVD/spot.
    drip_count = len(_per_coin_detail)
    if drip_count > 0:
        merged = 0
        lsr_populated = 0
        for sym, detail in _per_coin_detail.items():
            if sym not in bulk:
                continue
            coin = _scanner_to_coin(sym)
            oi_usd, oi_4h, oi_24h, cvd, spot, lsr, top_lsr = _parse_detail(coin, detail)

            # Debug: log raw LSR data for BTC to trace the pipeline
            if coin == "BTC":
                raw_lsr_global = detail.get("lsr_global") or []
                raw_lsr_top = detail.get("lsr_top") or []
                logger.info(
                    "DEBUG LSR BTC: raw_global=%s raw_top=%s parsed_lsr=%.4f parsed_top=%.4f",
                    raw_lsr_global[:1] if raw_lsr_global else "EMPTY",
                    raw_lsr_top[:1] if raw_lsr_top else "EMPTY",
                    lsr, top_lsr,
                )

            m = bulk[sym]
            if oi_usd is not None:
                m.open_interest_usd = oi_usd
            if oi_4h is not None:
                m.oi_change_pct_4h = round(oi_4h, 2)
            if oi_24h is not None:
                m.oi_change_pct_24h = round(oi_24h, 2)
            if lsr != 1.0:
                m.long_short_ratio_4h = lsr
                lsr_populated += 1
            if top_lsr != 1.0:
                m.top_trader_lsr = top_lsr
            if cvd is not None:
                _cvd_store[coin] = cvd
            if spot is not None:
                _spot_store[sym] = spot
                m.spot_volume_usd    = spot.spot_volume_usd
                m.futures_volume_usd = spot.futures_volume_usd
                m.spot_futures_ratio = spot.spot_futures_ratio
                m.spot_dominance     = spot.spot_dominance
            merged += 1
        logger.info("CoinGlass per-coin: merged drip data for %d/%d coins into bulk (%d with LSR != 1.0)", merged, drip_count, lsr_populated)
    else:
        logger.info("CoinGlass per-coin: drip loop not yet populated (first cycle)")

    # --- Filter and return ---
    if symbols:
        return {s: bulk[s] for s in symbols if s in bulk}
    return bulk


# ---------------------------------------------------------------------------
# CVD helpers (public API — same interface as before)
# ---------------------------------------------------------------------------

async def fetch_cvd_batch(
    coins: List[str],
    time_type: str = "4h",
    limit: int = 6,
    price_changes: Optional[Dict[str, float]] = None,
) -> Dict[str, CoinglassCVD]:
    """Return CVD data for requested coins.

    CVD is populated as a side-effect of ``fetch_coinglass_metrics``.
    This function returns the latest cached values; if a coin hasn't been
    fetched yet it triggers a fresh fetch for that coin.
    """
    result: Dict[str, CoinglassCVD] = {}
    missing: List[str] = []

    for coin in coins:
        if coin in _cvd_store:
            cvd = _cvd_store[coin]
            # Apply divergence from latest price change if provided
            if price_changes and coin in price_changes and cvd.cvd_trend != "NEUTRAL":
                pct = price_changes[coin]
                cvd.cvd_divergence = (
                    (pct > 0 and cvd.cvd_trend == "BEARISH") or
                    (pct < 0 and cvd.cvd_trend == "BULLISH")
                )
            result[coin] = cvd
        else:
            missing.append(coin)

    if missing:
        api_key = _get_api_key()
        if api_key:
            sem = asyncio.Semaphore(_REQUEST_SEMAPHORE)
            timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    tasks = [
                        _fetch_single_coin_detail(
                            session, sem, api_key, f"{c}/USDT",
                            price_changes.get(c) if price_changes else None,
                        )
                        for c in missing[:_PER_COIN_LIMIT]
                    ]
                    fetched = await asyncio.gather(*tasks, return_exceptions=True)

                for outcome in fetched:
                    if isinstance(outcome, Exception):
                        continue
                    sym, detail = outcome
                    coin = _scanner_to_coin(sym)
                    _, _, _, cvd, spot, _, _ = _parse_detail(coin, detail)
                    if cvd is not None:
                        _cvd_store[coin] = cvd
                        result[coin] = cvd
                    if spot is not None:
                        _spot_store[sym] = spot

            except Exception as exc:
                logger.error("CVD batch fetch error: %s", exc)

    return result


def get_cached_cvd(coin: str) -> Optional[CoinglassCVD]:
    """Return latest cached CVD for a base coin (e.g. 'BTC')."""
    return _cvd_store.get(coin)


# ---------------------------------------------------------------------------
# Spot helpers (public API — same interface as before)
# ---------------------------------------------------------------------------

async def fetch_spot_metrics(
    symbols: Optional[List[str]] = None,
) -> Dict[str, CoinglassSpot]:
    """Return spot dominance data populated by ``fetch_coinglass_metrics``."""
    if symbols:
        return {s: _spot_store[s] for s in symbols if s in _spot_store}
    return dict(_spot_store)


def get_cached_spot(sym: str) -> Optional[CoinglassSpot]:
    """Return latest cached spot dominance for a scanner symbol (e.g. 'BTC/USDT')."""
    return _spot_store.get(sym)


# ---------------------------------------------------------------------------
# Macro helpers
# ---------------------------------------------------------------------------

async def fetch_macro_signals() -> CoinglassMacro:
    """Fetch or return cached Coinbase premium + BTC ETF flow signals."""
    cached = _macro_cache.get()
    if cached is not None:
        return cached

    api_key = _get_api_key()
    if not api_key:
        return CoinglassMacro()

    sem = asyncio.Semaphore(_REQUEST_SEMAPHORE)
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            macro = await _fetch_macro(session, sem, api_key)
        _macro_cache.put(macro, _MACRO_CACHE_TTL)
        return macro
    except Exception as exc:
        logger.error("CoinGlass macro fetch error: %s", exc)
        return _macro_cache.get_fallback() or CoinglassMacro()


def get_cached_macro() -> Optional[CoinglassMacro]:
    """Return latest cached macro signals."""
    return _macro_cache.get_fallback()


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def get_cached_metrics() -> Optional[Dict[str, CoinglassMetrics]]:
    """Return cached CoinGlass metrics (even if expired)."""
    return _bulk_cache.get_fallback()
