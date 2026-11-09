"""Live-only context for the replay (docs/reviews/strong-long-replay-study.md): funding and stablecoin supply as the
live scanner reads them, rebuilt from history so the synthesizer's core checks "Funding OK" and "Liquidity" can be
known on every bar, as they are live.

- Funding: live reads Binance's lastFundingRate first and divides it by 8 to get an hourly rate
  (binance_futures_data.py); CROWDED_LONG above +0.0001 an hour (engines/positioning_engine.py). Here: the last
  settled payment of the coin's Binance USDT-M perpetual at or before the bar's close (the public archives, as
  research/band_marks_layers.funding reads them), missing when older than 16 hours.
- Stablecoins: live compares USDT + USDC supply now with a week ago (DefiLlama), EXPANDING above +1%, CONTRACTING
  below -1% (market_data.py). Here: the last completed day against the day 7 before it.
- Open interest, CVD, top traders' long/short and HyperLens stay unavailable, as they are live without CoinGlass
  (they are not core checks).
"""
from __future__ import annotations

import json
from typing import Callable, Dict, Optional, Tuple

import numpy as np

DAY_MS = 86_400_000
FUNDING_MAX_AGE_MS = 16 * 3_600_000
LLAMA = "https://stablecoins.llama.fi/stablecoincharts/all?stablecoin={id}"   # 1 USDT, 2 USDC


def stablecoin_days() -> Dict[int, float]:
    """USDT + USDC circulating supply by day (DefiLlama), cached; days where both are known."""
    from backtest import binance_history as bh
    path = bh.CACHE_DIR / "stablecoins_usdt_usdc.json"
    if not path.exists():
        bh.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        raw = {name: json.loads(bh._get(LLAMA.format(id=i))) for name, i in (("USDT", 1), ("USDC", 2))}
        path.write_text(json.dumps(raw))
    raw = json.loads(path.read_text())
    per = {name: {int(r["date"]) // 86_400: float((r.get("totalCirculating") or {}).get("peggedUSD") or 0)
                  for r in rows} for name, rows in raw.items()}
    return {d: per["USDT"][d] + per["USDC"][d] for d in per["USDT"] if d in per["USDC"] and per["USDT"][d] > 0}


def stablecoin_at(caps: Dict[int, float], close_ms: int) -> Optional[dict]:
    """The live stablecoin context at a bar's close: the last completed day against the day 7 before it."""
    from market_data import _trend_label
    last = int(close_ms) // DAY_MS - 1
    now, week = caps.get(last), caps.get(last - 7)
    if not now or not week:
        return None
    change = round((now - week) / week * 100.0, 2)
    return {"trend": _trend_label(change), "change_7d_pct": change, "total_cap": now}


def funding_series(coin: str) -> np.ndarray:
    """[time ms, the payment's own rate] for COINUSDT's perpetual (the archive's rate, before any per-8-hour scaling)."""
    from research.band_marks_layers import funding
    f = funding(f"{coin}USDT")
    if not len(f):
        return np.zeros((0, 2))
    return np.column_stack([f[:, 0], f[:, 1] * f[:, 2] / 8.0])


def positioning_at(fund: np.ndarray, close_ms: int) -> Optional[dict]:
    """The live positioning context at a bar's close from the last payment, or None (no payment in 16 hours)."""
    from engines.positioning_engine import compute_positioning
    if not len(fund):
        return None
    i = int(np.searchsorted(fund[:, 0], close_ms, side="right")) - 1
    if i < 0 or close_ms - fund[i, 0] > FUNDING_MAX_AGE_MS:
        return None
    hourly = float(fund[i, 1]) / 8.0                       # as live: Binance's rate divided by 8
    pos = compute_positioning(funding_rate=hourly, open_interest=0.0, price_change_pct=0.0)
    return {"funding_regime": pos.funding_regime, "funding_rate": hourly, "oi_trend": "UNKNOWN", "oi_value": 0.0,
            "oi_change_pct": 0.0, "leverage_risk": pos.leverage_risk, "predicted_funding": 0.0, "mark_price": 0.0,
            "volume_24h": 0.0, "source": "binance_archive", "source_map": {"funding": "binance_archive"},
            "liquidation_24h_usd": 0.0, "long_liq_usd": 0.0, "short_liq_usd": 0.0, "liquidation_4h_usd": 0.0,
            "liquidation_1h_usd": 0.0, "long_short_ratio": 1.0, "top_trader_lsr": 1.0, "oi_market_cap_ratio": 0.0,
            "spot_volume_usd": 0.0, "spot_futures_ratio": 0.0, "spot_dominance": "NEUTRAL"}


def make_hook(symbols, funding_of: Callable[[str], np.ndarray] = funding_series,
              caps: Optional[Dict[int, float]] = None) -> Callable[[dict, int], Tuple[dict, dict]]:
    """CONTEXT_HOOK for backtest/replay_engine: per row, the positioning and stablecoin context known at the bar's
    close, with metadata that marks each as just observed (or missing)."""
    fund = {f"{s}/USDT": funding_of(s) for s in symbols}
    caps = stablecoin_days() if caps is None else caps

    def hook(row: dict, close_ms: int):
        pos = positioning_at(fund.get(row.get("symbol"), np.zeros((0, 2))), int(close_ms))
        st = stablecoin_at(caps, int(close_ms))
        t = int(close_ms) / 1000
        return ({"positioning": pos, "stablecoin": st},
                {"funding": {"source": "binance_archive", "observed_at": t if pos else None},
                 "stablecoin": {"source": "defillama_history", "observed_at": t if st else None}})
    return hook
