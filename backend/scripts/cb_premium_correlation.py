#!/usr/bin/env python3
"""
cb_premium_correlation.py
=========================

Historical correlation analysis between the Coinbase premium index (CoinGlass)
and BTC price returns. Designed to run against the live CoinGlass + CCXT data
so you can see how tightly the premium tracks BTC over a real multi-month
sample before investing in any signal built on it.

Runs contemporaneous + lead/lag Pearson, regime-split correlation, and an
event study on extreme-premium days. Also runs the same treatment on BTC
ETF net flows as a comparison (the user's prior is that ETF flows lag — the
cross-correlation peak will tell us definitively).

Usage
-----
    # On Railway (has network + API keys):
    railway run python scripts/cb_premium_correlation.py

    # Or locally if you have COINGLASS_API_KEY set and exchange access:
    export COINGLASS_API_KEY=...
    python scripts/cb_premium_correlation.py

Flags
-----
    --interval h1|h4|d1    CB premium granularity (default: h4)
    --limit N              candles to pull (default: 1000, CoinGlass max)
    --no-color             plain-text output
    --etf                  also run the ETF-flows vs BTC analysis (daily)
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

# Make `backend/` importable when run from scripts/
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# ─── CoinGlass config ──────────────────────────────────────────────────────
COINGLASS_BASE = "https://open-api-v4.coinglass.com"
COINGLASS_AUTH_HEADER = "CG-API-KEY"
COINGLASS_CB_PATH = "/api/coinbase-premium-index"
COINGLASS_ETF_PATH = "/api/etf/bitcoin/flow-history"


# ─── Statistics helpers ────────────────────────────────────────────────────

def pearson(xs: List[float], ys: List[float]) -> float:
    """Pearson correlation. NaN if too few samples or zero variance."""
    n = min(len(xs), len(ys))
    if n < 5:
        return float("nan")
    sx = sum(xs[:n]); sy = sum(ys[:n])
    mx = sx / n; my = sy / n
    num = dx = dy = 0.0
    for i in range(n):
        a = xs[i] - mx; b = ys[i] - my
        num += a * b; dx += a * a; dy += b * b
    if dx <= 0 or dy <= 0:
        return float("nan")
    return num / math.sqrt(dx * dy)


def zscore_series(xs: List[float]) -> List[float]:
    """Return z-scored version of the series (NaN if flat)."""
    n = len(xs)
    if n < 2:
        return [float("nan")] * n
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / n
    if var <= 0:
        return [0.0] * n
    s = math.sqrt(var)
    return [(x - m) / s for x in xs]


# ─── Data fetchers ─────────────────────────────────────────────────────────

async def fetch_cb_premium(api_key: str, interval: str, limit: int) -> List[dict]:
    """Fetch CoinGlass coinbase-premium-index history.

    Returns list of dicts with keys depending on API version; typically
    each row has ``time`` (ms), ``premium_rate``, ``premium``, ``price``.
    """
    async with aiohttp.ClientSession() as sess:
        url = f"{COINGLASS_BASE}{COINGLASS_CB_PATH}"
        params = {"symbol": "BTC", "interval": interval, "limit": int(limit)}
        headers = {COINGLASS_AUTH_HEADER: api_key, "Accept": "application/json"}
        async with sess.get(url, params=params, headers=headers, timeout=30) as r:
            r.raise_for_status()
            body = await r.json()
    if str(body.get("code", "")) not in ("0", "200"):
        raise RuntimeError(f"CoinGlass error: {body}")
    return body.get("data") or []


async def fetch_etf_flows(api_key: str) -> List[dict]:
    """Fetch BTC ETF daily net-flow history (endpoint ignores limit param)."""
    async with aiohttp.ClientSession() as sess:
        url = f"{COINGLASS_BASE}{COINGLASS_ETF_PATH}"
        params = {"interval": "daily"}
        headers = {COINGLASS_AUTH_HEADER: api_key, "Accept": "application/json"}
        async with sess.get(url, params=params, headers=headers, timeout=30) as r:
            r.raise_for_status()
            body = await r.json()
    if str(body.get("code", "")) not in ("0", "200"):
        raise RuntimeError(f"CoinGlass error: {body}")
    return body.get("data") or []


async def fetch_btc_ohlcv(interval: str, limit: int) -> List[tuple]:
    """Fetch BTC/USDT OHLCV via CCXT. Returns [(ts_s, close), …]."""
    try:
        from data_fetcher import _get_exchange  # late import; avoids cycles
    except Exception as exc:
        raise RuntimeError(f"could not import data_fetcher: {exc}")

    # CCXT timeframe string
    ccxt_tf = {"h1": "1h", "h4": "4h", "d1": "1d"}.get(interval, interval)
    for exch_id in ("kraken", "bybit", "okx", "kucoin"):
        try:
            ex = await _get_exchange(exch_id)
            sym = "BTC/USDT" if "BTC/USDT" in ex.markets else "BTC/USD"
            if sym not in ex.markets:
                continue
            raw = await ex.fetch_ohlcv(sym, ccxt_tf, limit=int(limit))
            if not raw:
                continue
            return [(int(row[0]) // 1000, float(row[4])) for row in raw if row]
        except Exception:
            continue
    raise RuntimeError("all CCXT exchanges failed for BTC/USDT")


# ─── Alignment ─────────────────────────────────────────────────────────────

def align_series(
    a: List[Tuple[float, float]],
    b: List[Tuple[float, float]],
    tol_s: int,
) -> List[Tuple[float, float, float]]:
    """Pair (ts, va) with the nearest (ts, vb) within ``tol_s``. Returns
    [(ts, va, vb), …] ascending by ts.
    """
    a = sorted(a); b = sorted(b)
    out: List[Tuple[float, float, float]] = []
    j = 0
    for ta, va in a:
        while j + 1 < len(b) and abs(b[j + 1][0] - ta) < abs(b[j][0] - ta):
            j += 1
        if j < len(b) and abs(b[j][0] - ta) <= tol_s:
            out.append((ta, va, b[j][1]))
    return out


# ─── Analyses ──────────────────────────────────────────────────────────────

def returns_from_closes(closes: List[float]) -> List[float]:
    return [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]


def lead_lag_correlation(
    premium: List[float],
    returns: List[float],
    max_lag: int,
) -> List[Tuple[int, float, int]]:
    """Cross-correlation: corr(premium[t], returns[t + lag]) for lag ∈ [-max_lag, +max_lag].

    Positive lag → premium leads price (premium at t correlates with
    future return).  Negative lag → premium lags price.
    """
    out = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            xs = premium[: len(premium) - lag]
            ys = returns[lag: lag + len(xs)]
        else:
            xs = premium[-lag:]
            ys = returns[: len(xs)]
        n = min(len(xs), len(ys))
        if n < 10:
            continue
        r = pearson(xs[:n], ys[:n])
        out.append((lag, r, n))
    return out


def regime_split(
    premium: List[float],
    returns: List[float],
    lookback: int = 20,
    trend_threshold: float = 0.02,
) -> Dict[str, Tuple[float, int]]:
    """Split the sample by the rolling BTC trend and compute corr within each.

    Uses trailing ``lookback`` returns to classify each point:
      - MARKUP:    trailing return > +threshold
      - MARKDOWN:  trailing return < -threshold
      - RANGE:     |trailing return| <= threshold
    """
    n = min(len(premium), len(returns))
    if n <= lookback:
        return {}

    by_regime: Dict[str, Tuple[List[float], List[float]]] = {
        "MARKUP": ([], []), "MARKDOWN": ([], []), "RANGE": ([], []),
    }
    for i in range(lookback, n):
        window_ret = 1.0
        for j in range(i - lookback, i):
            window_ret *= (1.0 + returns[j])
        window_ret -= 1.0
        if window_ret > trend_threshold:
            regime = "MARKUP"
        elif window_ret < -trend_threshold:
            regime = "MARKDOWN"
        else:
            regime = "RANGE"
        by_regime[regime][0].append(premium[i])
        by_regime[regime][1].append(returns[i])

    return {r: (pearson(xs, ys), len(xs)) for r, (xs, ys) in by_regime.items()}


def event_study(
    paired: List[Tuple[float, float, float]],
    z_threshold: float,
    horizons: List[int],
) -> Dict[int, Tuple[float, int, float]]:
    """For each event where premium z-score >= threshold, compute mean BTC
    return at each forward horizon (number of bars).

    Returns {horizon_bars: (mean_return, n, hit_rate)} where hit_rate is
    the fraction that moved in the "expected" direction (up if premium
    was positive, down if negative).
    """
    if len(paired) < 30:
        return {}
    premiums = [p[1] for p in paired]
    closes = [p[2] for p in paired]
    zs = zscore_series(premiums)

    events: List[Tuple[int, float]] = []  # (index, sign)
    for i in range(len(zs)):
        if abs(zs[i]) >= z_threshold:
            events.append((i, 1 if zs[i] > 0 else -1))

    results: Dict[int, Tuple[float, int, float]] = {}
    for h in horizons:
        forward_returns = []
        hits = 0
        for idx, sign in events:
            if idx + h >= len(closes):
                continue
            ret = (closes[idx + h] / closes[idx]) - 1.0
            forward_returns.append(ret)
            if (ret > 0 and sign > 0) or (ret < 0 and sign < 0):
                hits += 1
        if forward_returns:
            mean = sum(forward_returns) / len(forward_returns)
            hit_rate = hits / len(forward_returns)
            results[h] = (mean, len(forward_returns), hit_rate)
    return results


# ─── Formatting ────────────────────────────────────────────────────────────

def color(text: str, code: str, use_color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if use_color else text


def print_lead_lag(rows: List[Tuple[int, float, int]], use_color: bool) -> None:
    print(f"  {'lag (bars)':>12}  {'n':>5}  {'corr':>8}  {'strength':>12}")
    print("  " + "-" * 48)
    best = max(rows, key=lambda r: abs(r[1]) if not math.isnan(r[1]) else -1)
    for lag, r, n in rows:
        if math.isnan(r):
            continue
        bar_len = int(min(20, abs(r) * 40))
        bar = ("▎" * bar_len) if r >= 0 else ("▎" * bar_len)
        marker = " ←" if (lag, r, n) == best else ""
        c = "32" if abs(r) > 0.2 else ("33" if abs(r) > 0.1 else "37")
        print(color(f"  {lag:>+12d}  {n:>5d}  {r:>+8.3f}  {bar:<12}{marker}", c, use_color))
    lag, r, n = best
    print(f"\n  ↑ peak |corr|: {r:+.3f} at lag={lag:+d} bars (n={n})")
    direction = (
        "premium LEADS price (predictive potential)"  if lag > 0 else
        "premium LAGS price (reactive)"                 if lag < 0 else
        "coincident (moves with price in same bar)"
    )
    print(f"    {direction}")


def print_regime(split: Dict[str, Tuple[float, int]], use_color: bool) -> None:
    print(f"  {'regime':<10}  {'n':>5}  {'corr':>8}")
    print("  " + "-" * 30)
    for regime in ("MARKUP", "RANGE", "MARKDOWN"):
        if regime not in split:
            continue
        r, n = split[regime]
        if math.isnan(r):
            continue
        c = "32" if abs(r) > 0.2 else ("33" if abs(r) > 0.1 else "37")
        print(color(f"  {regime:<10}  {n:>5d}  {r:>+8.3f}", c, use_color))


def print_event_study(
    name: str, study: Dict[int, Tuple[float, int, float]], use_color: bool,
) -> None:
    print(f"  {name}:")
    print(f"    {'horizon (bars)':>14}  {'n':>5}  {'mean ret':>10}  {'hit rate':>10}")
    print("    " + "-" * 48)
    for h in sorted(study.keys()):
        mean, n, hr = study[h]
        c = "32" if hr > 0.55 else ("33" if hr > 0.50 else "37")
        print(color(
            f"    {h:>14d}  {n:>5d}  {mean * 100:>+9.2f}%  {hr * 100:>9.0f}%",
            c, use_color,
        ))


# ─── Main analyses ─────────────────────────────────────────────────────────

async def run_cb_analysis(api_key: str, interval: str, limit: int, use_color: bool) -> None:
    print(color(f"\n━━ COINBASE PREMIUM vs BTC — {interval} interval, up to {limit} bars ━━",
                "1;36", use_color))

    cb_rows = await fetch_cb_premium(api_key, interval, limit)
    if not cb_rows:
        print(color("  No CB premium data returned.", "31", use_color))
        return
    # Normalize timestamps to seconds
    def pick_ts(row):
        for k in ("time", "t", "timestamp", "ts"):
            if k in row:
                v = row[k]
                return int(v) // 1000 if v > 1e11 else int(v)
        return None
    def pick_rate(row):
        for k in ("premium_rate", "premiumRate", "rate", "premium"):
            if k in row:
                return float(row[k] or 0.0)
        return 0.0
    cb_series = [(pick_ts(r), pick_rate(r)) for r in cb_rows if pick_ts(r)]
    cb_series.sort()
    print(f"  CB premium points: {len(cb_series)}")

    # Fetch BTC OHLCV at same interval; tolerance = half the bar length
    bar_s = {"h1": 3600, "h4": 14400, "d1": 86400}.get(interval, 3600)
    btc = await fetch_btc_ohlcv(interval, min(1000, limit + 8))
    print(f"  BTC OHLCV points: {len(btc)}")

    paired = align_series(cb_series, btc, tol_s=bar_s // 2)
    print(f"  Paired bars:      {len(paired)}")
    if len(paired) < 50:
        print(color("  Too few paired points to compute meaningful stats.", "31", use_color))
        return

    premiums = [p[1] for p in paired]
    closes = [p[2] for p in paired]
    returns = returns_from_closes(closes)
    premiums_r = premiums[1:]  # align with returns (one fewer after diff)

    print(f"\n  Date range: {time.strftime('%Y-%m-%d', time.gmtime(paired[0][0]))}"
          f" → {time.strftime('%Y-%m-%d', time.gmtime(paired[-1][0]))}")

    print(color("\n  Contemporaneous corr (premium vs same-bar BTC return):", "1;37", use_color))
    r0 = pearson(premiums_r, returns)
    print(f"    r = {r0:+.3f}   (n={len(returns)})")

    print(color("\n  Lead / lag cross-correlation (premium vs BTC return at offset):", "1;37", use_color))
    max_lag = min(24, len(returns) // 10)
    rows = lead_lag_correlation(premiums_r, returns, max_lag)
    print_lead_lag(rows, use_color)

    print(color("\n  Correlation by BTC regime (classified by trailing 20-bar trend):", "1;37", use_color))
    split = regime_split(premiums_r, returns, lookback=20, trend_threshold=0.02)
    print_regime(split, use_color)

    print(color("\n  Event study — BTC forward returns after extreme premium (|z| ≥ 1.5):", "1;37", use_color))
    h_bars = [1, 3, 6, 12, 24]
    study = event_study(paired, z_threshold=1.5, horizons=h_bars)
    print_event_study("CB premium events", study, use_color)


async def run_etf_analysis(api_key: str, use_color: bool) -> None:
    print(color(f"\n━━ BTC ETF NET FLOW vs BTC — daily ━━", "1;36", use_color))
    etf_rows = await fetch_etf_flows(api_key)
    if not etf_rows:
        print(color("  No ETF flow data returned.", "31", use_color))
        return

    def pick_ts(row):
        for k in ("time", "t", "timestamp", "ts", "date"):
            if k in row:
                v = row[k]
                try:
                    return int(v) // 1000 if int(v) > 1e11 else int(v)
                except (TypeError, ValueError):
                    return None
        return None
    def pick_flow(row):
        for k in ("flow_usd", "flowUsd", "net_flow_usd", "flow"):
            if k in row:
                try:
                    return float(row[k] or 0)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    etf_series = [(pick_ts(r), pick_flow(r)) for r in etf_rows if pick_ts(r)]
    etf_series.sort()
    print(f"  ETF flow days: {len(etf_series)}")

    btc = await fetch_btc_ohlcv("d1", 1000)
    print(f"  BTC daily bars: {len(btc)}")

    paired = align_series(etf_series, btc, tol_s=86400 // 2)
    print(f"  Paired days:   {len(paired)}")
    if len(paired) < 30:
        print(color("  Too few paired days.", "31", use_color))
        return

    flows = [p[1] for p in paired]
    closes = [p[2] for p in paired]
    returns = returns_from_closes(closes)
    flows_r = flows[1:]

    print(color("\n  Lead / lag cross-correlation (ETF flow vs BTC return at offset):", "1;37", use_color))
    rows = lead_lag_correlation(flows_r, returns, max_lag=7)
    print_lead_lag(rows, use_color)


# ─── Entry ─────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--interval", default="h4", choices=["h1", "h4", "d1"])
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--etf", action="store_true", help="Also run ETF flows vs BTC analysis")
    args = p.parse_args()

    api_key = os.environ.get("COINGLASS_API_KEY") or os.environ.get("COINGLASS_KEY")
    if not api_key:
        print("ERROR: set COINGLASS_API_KEY in the environment.", file=sys.stderr)
        return 1

    use_color = sys.stdout.isatty() and not args.no_color

    async def _main():
        await run_cb_analysis(api_key, args.interval, args.limit, use_color)
        if args.etf:
            await run_etf_analysis(api_key, use_color)

    try:
        asyncio.run(_main())
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
