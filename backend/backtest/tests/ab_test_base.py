#!/usr/bin/env python3
"""
Shared infrastructure for A/B testing via walk-forward windows.

All A/B tests use subprocess isolation to ensure clean module state
between variants. This module provides the common data-fetching and
window-running logic.

Usage: import from your test script and call run_ab_windows().
"""
import asyncio
import sys
import os
import time
import json
from typing import Dict, List, Callable, Any, Optional

# Ensure backend/ is on the path regardless of where we're invoked from
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
os.chdir(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


async def run_ab_windows(
    variant_label: str,
    output_file: str,
    target_indices: Optional[List[int]] = None,
    extra_trade_metrics: Optional[Callable] = None,
):
    """
    Run target walk-forward windows and write results JSON.

    Parameters
    ----------
    variant_label : str
        Label for logging (e.g. "5/10", "flat_2x").
    output_file : str
        Path to write JSON results.
    target_indices : list[int], optional
        Window indices to test. Defaults to [0, 4, 5, 8].
    extra_trade_metrics : callable, optional
        fn(trades) -> dict of extra metrics to include per window.
    """
    from backtest.walkforward import WalkForwardConfig, _generate_windows, _run_window
    from backtest.data_loader import (
        fetch_historical_batch, fetch_historical_fear_greed,
        _date_to_ms, _ms_to_date,
    )
    from backtest.runner import _compute_bmsb_filter, WARMUP_BARS

    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if target_indices is None:
        target_indices = [0, 4, 5, 8]

    t0 = time.time()

    config = WalkForwardConfig(
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
                 "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "LINK/USDT"],
        start_date="2021-01-01",
        end_date="2026-03-07",
        initial_capital=10000.0,
        timeframe="4h",
        leverage=2.0,
        test_window_days=180,
        step_days=180,
    )

    windows = _generate_windows(config)
    target_windows = [windows[i] for i in target_indices]

    earliest_ms = min(w["warmup_start_ms"] for w in target_windows)
    earliest_date = _ms_to_date(earliest_ms)

    print(f"[{variant_label}] Fetching data ({earliest_date} → {config.end_date})...", flush=True)
    ohlcv_4h = await fetch_historical_batch(
        config.symbols, "4h", earliest_date, config.end_date, warmup_bars=WARMUP_BARS,
    )
    ohlcv_1d = await fetch_historical_batch(
        config.symbols, "1d", earliest_date, config.end_date, warmup_bars=200,
    )
    ohlcv_1w = await fetch_historical_batch(
        config.symbols, "1w", earliest_date, config.end_date, warmup_bars=30,
    )
    total_days = min(
        int((_date_to_ms(config.end_date) - earliest_ms) / (86400 * 1000)) + 30, 2000,
    )
    fear_greed = await fetch_historical_fear_greed(total_days)

    valid_symbols = [s for s in config.symbols if s in ohlcv_4h]
    btc_weekly = ohlcv_1w.get("BTC/USDT")
    bmsb_map = (_compute_bmsb_filter(btc_weekly)
                if btc_weekly and len(btc_weekly.get("close", [])) >= 21
                else {})
    bmsb_ts = sorted(bmsb_map.keys())

    print(f"[{variant_label}] Data ready in {time.time()-t0:.0f}s", flush=True)

    results = {}
    for w in target_windows:
        t1 = time.time()
        idx = w["index"]
        print(f"\n[{variant_label}] W{idx} ({w['test_start']} → {w['test_end']}): running...", flush=True)

        wr = await _run_window(
            window=w, ohlcv_4h_all=ohlcv_4h, ohlcv_1d_all=ohlcv_1d,
            ohlcv_1w_all=ohlcv_1w, fear_greed=fear_greed,
            bmsb_blocked_map=bmsb_map, bmsb_weekly_ts=bmsb_ts,
            config=config, valid_symbols=valid_symbols,
        )
        m = wr.metrics
        if m:
            sl = sum(1 for t in wr.trades if t.entry_signal == "STRONG_LONG")
            ll = sum(1 for t in wr.trades if t.entry_signal == "LIGHT_LONG")
            elapsed = time.time() - t1

            entry = {
                "return": m.total_return_pct,
                "trades": m.total_trades,
                "sl": sl, "ll": ll,
                "wr": m.win_rate,
                "sharpe": m.sharpe_ratio,
                "dd": m.max_drawdown_pct,
                "alpha": m.alpha_pct,
            }

            if extra_trade_metrics:
                entry.update(extra_trade_metrics(wr.trades))

            print(f"[{variant_label}] W{idx}: {m.total_return_pct:+.1f}% | "
                  f"{m.total_trades} trades (SL:{sl} LL:{ll}) | "
                  f"WR {m.win_rate:.0f}% | Sharpe {m.sharpe_ratio:.2f} | "
                  f"DD {m.max_drawdown_pct:.1f}% | Alpha {m.alpha_pct:+.1f}% | "
                  f"{elapsed:.0f}s", flush=True)

            results[str(idx)] = entry
        else:
            print(f"[{variant_label}] W{idx}: No trades | {time.time()-t1:.0f}s", flush=True)
            results[str(idx)] = {"return": 0, "trades": 0, "sl": 0, "ll": 0,
                                  "wr": 0, "sharpe": 0, "dd": 0, "alpha": 0}

    total = time.time() - t0
    print(f"\n[{variant_label}] Done in {total:.0f}s ({total/60:.1f} min)", flush=True)

    with open(output_file, "w") as f:
        json.dump(results, f)
