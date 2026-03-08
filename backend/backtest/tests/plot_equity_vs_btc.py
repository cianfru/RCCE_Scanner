#!/usr/bin/env python3
"""
Generate equity curve chart: RCCE System vs BTC Buy-and-Hold.

Produces a PNG with:
  - Green line: RCCE system equity curve (full period, compounded)
  - Orange line: BTC buy-and-hold
  - Red shading: BMSB blocked periods
  - Bottom panel: drawdown curve
  - Stats box with key metrics

Usage: cd backend && python3 -m backtest.tests.plot_equity_vs_btc
Output: /tmp/rcce_vs_btc_equity.png
"""
import asyncio
import sys
import os
import time
import numpy as np
from datetime import datetime

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter


async def main():
    from backtest.runner import BacktestConfig, BacktestResult, _run_backtest_task
    from backtest.data_loader import fetch_historical_batch

    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    t0 = time.time()

    config = BacktestConfig(
        symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
                 "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "LINK/USDT"],
        start_date="2021-01-01",
        end_date="2026-03-07",
        initial_capital=10000.0,
        use_confluence=True,
        use_fear_greed=True,
        timeframe="4h",
        leverage=2.0,
    )

    result = BacktestResult()
    result.started_at = time.time()  # Required by runner's elapsed calc

    print("Running full-period backtest (this takes ~80 minutes)...")
    await _run_backtest_task("chart_run", config, result)

    if result.status == "error":
        print(f"ERROR: {result.error}")
        # Check if we still got usable data despite the error
        if not result.equity_curve:
            return

    m = result.metrics
    if m:
        print(f"Return: {m.total_return_pct:+.1f}% | {m.total_trades} trades | "
              f"Sharpe {m.sharpe_ratio:.2f} | DD {m.max_drawdown_pct:.1f}%")

    # --- Extract equity curves ---
    eq_timestamps = [ts for ts, _ in result.equity_curve]
    eq_values = [val for _, val in result.equity_curve]
    eq_dates = [datetime.utcfromtimestamp(ts / 1000) for ts in eq_timestamps]
    eq_return_pct = [(v / config.initial_capital - 1) * 100 for v in eq_values]

    btc_timestamps = [ts for ts, _ in result.btc_equity_curve]
    btc_values = [val for _, val in result.btc_equity_curve]
    btc_dates = [datetime.utcfromtimestamp(ts / 1000) for ts in btc_timestamps]
    btc_return_pct = [(v / config.initial_capital - 1) * 100 for v in btc_values]

    # --- BMSB blocked periods ---
    from backtest.runner import _compute_bmsb_filter
    ohlcv_1w = await fetch_historical_batch(
        ["BTC/USDT"], "1w", "2021-01-01", "2026-03-07", warmup_bars=30,
    )
    btc_weekly = ohlcv_1w.get("BTC/USDT")
    bmsb_map = _compute_bmsb_filter(btc_weekly) if btc_weekly else {}
    bmsb_ts = sorted(bmsb_map.keys())

    bmsb_blocked_periods = []
    blocked_start = None
    for ts in bmsb_ts:
        if bmsb_map.get(ts, False):
            if blocked_start is None:
                blocked_start = datetime.utcfromtimestamp(ts / 1000)
        else:
            if blocked_start is not None:
                bmsb_blocked_periods.append(
                    (blocked_start, datetime.utcfromtimestamp(ts / 1000)))
                blocked_start = None
    if blocked_start is not None:
        bmsb_blocked_periods.append(
            (blocked_start, datetime.utcfromtimestamp(bmsb_ts[-1] / 1000)))

    # --- Drawdown ---
    eq_arr = np.array(eq_values)
    peak = np.maximum.accumulate(eq_arr)
    drawdown_pct = (eq_arr - peak) / peak * 100

    # --- Plot ---
    print("Generating chart...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), dpi=150,
                                    height_ratios=[3, 1],
                                    gridspec_kw={"hspace": 0.08})
    fig.patch.set_facecolor("#0d1117")
    ax1.set_facecolor("#0d1117")
    ax2.set_facecolor("#0d1117")

    # BMSB shading
    for start, end in bmsb_blocked_periods:
        ax1.axvspan(start, end, alpha=0.08, color="#ff4444", zorder=0)
        ax2.axvspan(start, end, alpha=0.08, color="#ff4444", zorder=0)

    # BTC
    ax1.plot(btc_dates, btc_return_pct, color="#f7931a", linewidth=1.5,
             alpha=0.8, label=f"BTC Buy & Hold ({btc_return_pct[-1]:+.0f}%)", zorder=2)
    # System
    ax1.plot(eq_dates, eq_return_pct, color="#00ff88", linewidth=2.0,
             alpha=0.9, label=f"RCCE System ({eq_return_pct[-1]:+.0f}%)", zorder=3)
    ax1.axhline(y=0, color="#888888", linewidth=0.5, alpha=0.5, zorder=1)

    # Key events
    for evt_date, evt_label in [
        (datetime(2021, 4, 14), "BTC $64k"), (datetime(2021, 11, 10), "BTC $69k"),
        (datetime(2022, 6, 18), "Luna crash"), (datetime(2022, 11, 11), "FTX"),
        (datetime(2024, 3, 14), "BTC $73k"), (datetime(2025, 1, 20), "BTC $109k"),
    ]:
        if eq_dates[0] <= evt_date <= eq_dates[-1]:
            ax1.axvline(x=evt_date, color="#555555", linewidth=0.5, alpha=0.4)
            ax1.text(evt_date, max(eq_return_pct) * 0.95, evt_label,
                    fontsize=7, color="#8b949e", alpha=0.7, rotation=90, ha="right", va="top")

    ax1.set_title("RCCE Scanner vs BTC Buy & Hold  —  Jan 2021 to Mar 2026",
                  fontsize=15, fontweight="bold", color="#e6edf3", pad=15, fontfamily="monospace")
    ax1.set_ylabel("Return (%)", fontsize=10, color="#8b949e", fontfamily="monospace")
    ax1.tick_params(colors="#8b949e", labelsize=9)
    ax1.tick_params(axis="x", labelbottom=False)
    for s in ["top", "right"]: ax1.spines[s].set_visible(False)
    for s in ["left", "bottom"]: ax1.spines[s].set_color("#30363d")
    ax1.grid(True, alpha=0.12, color="#30363d")
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:+.0f}%"))
    ax1.legend(loc="upper left", fontsize=11, framealpha=0.1,
               edgecolor="#30363d", facecolor="#0d1117", labelcolor="#e6edf3")

    # Stats box
    if m:
        stats = (f"RCCE System\n  Return:    {eq_return_pct[-1]:+.0f}%\n"
                 f"  Trades:    {m.total_trades}\n  Win Rate:  {m.win_rate:.0f}%\n"
                 f"  Sharpe:    {m.sharpe_ratio:.2f}\n  Max DD:    {m.max_drawdown_pct:.1f}%\n\n"
                 f"BTC Buy & Hold\n  Return:    {btc_return_pct[-1]:+.0f}%\n\n"
                 f"Alpha:       {eq_return_pct[-1] - btc_return_pct[-1]:+.0f}%\n"
                 f"Red = BMSB blocked")
        ax1.text(0.98, 0.02, stats, transform=ax1.transAxes, fontsize=8.5,
                 fontfamily="monospace", color="#e6edf3", va="bottom", ha="right",
                 bbox=dict(boxstyle="round,pad=0.5", facecolor="#161b22",
                          edgecolor="#30363d", alpha=0.9))

    # Drawdown panel
    ax2.fill_between(eq_dates, drawdown_pct, 0, color="#ff4444", alpha=0.3)
    ax2.plot(eq_dates, drawdown_pct, color="#ff4444", linewidth=0.8, alpha=0.7)
    ax2.axhline(y=0, color="#888888", linewidth=0.5, alpha=0.3)
    ax2.set_ylabel("Drawdown (%)", fontsize=10, color="#8b949e", fontfamily="monospace")
    ax2.set_xlabel("Date", fontsize=10, color="#8b949e", fontfamily="monospace")
    ax2.tick_params(colors="#8b949e", labelsize=9)
    for s in ["top", "right"]: ax2.spines[s].set_visible(False)
    for s in ["left", "bottom"]: ax2.spines[s].set_color("#30363d")
    ax2.grid(True, alpha=0.12, color="#30363d")
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    output_path = "/tmp/rcce_vs_btc_equity.png"
    fig.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    print(f"\nChart saved to: {output_path}")
    print(f"Total time: {time.time()-t0:.0f}s ({(time.time()-t0)/60:.1f} min)")


if __name__ == "__main__":
    asyncio.run(main())
