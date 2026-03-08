#!/usr/bin/env python3
"""
Standalone walk-forward runner — bypasses the web server for reliability.

Runs 10 non-overlapping 6-month windows from Jan 2021 to Mar 2026,
then a full-period pass for overfitting comparison.

Usage: cd backend && python3 -m backtest.tests.run_walkforward
Output: /tmp/walkforward_results.json
"""
import asyncio
import sys
import os
import time
import json

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)


async def main():
    from backtest.walkforward import WalkForwardConfig, _generate_windows, _run_window
    from backtest.data_loader import (
        fetch_historical_batch, fetch_historical_fear_greed,
        _date_to_ms, _ms_to_date,
    )
    from backtest.runner import _compute_bmsb_filter, WARMUP_BARS

    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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
    print(f"Generated {len(windows)} windows")

    # Fetch all data once
    earliest_ms = min(w["warmup_start_ms"] for w in windows)
    earliest_date = _ms_to_date(earliest_ms)

    print(f"Fetching data ({earliest_date} → {config.end_date})...")
    ohlcv_4h = await fetch_historical_batch(
        config.symbols, "4h", earliest_date, config.end_date, warmup_bars=WARMUP_BARS)
    ohlcv_1d = await fetch_historical_batch(
        config.symbols, "1d", earliest_date, config.end_date, warmup_bars=200)
    ohlcv_1w = await fetch_historical_batch(
        config.symbols, "1w", earliest_date, config.end_date, warmup_bars=30)
    total_days = min(int((_date_to_ms(config.end_date) - earliest_ms) / (86400*1000)) + 30, 2000)
    fear_greed = await fetch_historical_fear_greed(total_days)

    valid_symbols = [s for s in config.symbols if s in ohlcv_4h]
    btc_weekly = ohlcv_1w.get("BTC/USDT")
    bmsb_map = (_compute_bmsb_filter(btc_weekly)
                if btc_weekly and len(btc_weekly.get("close", [])) >= 21 else {})
    bmsb_ts = sorted(bmsb_map.keys())

    print(f"Data ready in {time.time()-t0:.0f}s\n")

    # Run all windows
    all_results = []
    for w in windows:
        t1 = time.time()
        idx = w["index"]
        print(f"W{idx} ({w['test_start']} → {w['test_end']}): ", end="", flush=True)

        wr = await _run_window(
            window=w, ohlcv_4h_all=ohlcv_4h, ohlcv_1d_all=ohlcv_1d,
            ohlcv_1w_all=ohlcv_1w, fear_greed=fear_greed,
            bmsb_blocked_map=bmsb_map, bmsb_weekly_ts=bmsb_ts,
            config=config, valid_symbols=valid_symbols,
        )
        m = wr.metrics
        elapsed = time.time() - t1
        if m:
            print(f"{m.total_return_pct:+.1f}% | {m.total_trades} trades | "
                  f"WR {m.win_rate:.0f}% | Sharpe {m.sharpe_ratio:.2f} | "
                  f"DD {m.max_drawdown_pct:.1f}% | Alpha {m.alpha_pct:+.1f}% | {elapsed:.0f}s")
            all_results.append({
                "window": idx, "return": m.total_return_pct, "trades": m.total_trades,
                "wr": m.win_rate, "sharpe": m.sharpe_ratio, "dd": m.max_drawdown_pct,
                "alpha": m.alpha_pct,
            })
        else:
            print(f"No trades | {elapsed:.0f}s")
            all_results.append({"window": idx, "return": 0, "trades": 0})

    # Summary
    profitable = sum(1 for r in all_results if r["return"] > 0)
    total_ret = sum(r["return"] for r in all_results)
    avg_sharpe = sum(r.get("sharpe", 0) for r in all_results) / len(all_results)

    print(f"\n{'='*60}")
    print(f"WALK-FORWARD SUMMARY")
    print(f"{'='*60}")
    print(f"Windows: {len(all_results)} ({profitable} profitable, {len(all_results)-profitable} losing)")
    print(f"Consistency: {profitable/len(all_results)*100:.0f}%")
    print(f"Sum return: {total_ret:+.1f}%")
    print(f"Avg Sharpe: {avg_sharpe:.2f}")
    print(f"Total time: {time.time()-t0:.0f}s ({(time.time()-t0)/60:.1f} min)")

    # Save
    output_path = "/tmp/walkforward_results.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
