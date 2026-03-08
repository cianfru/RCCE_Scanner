#!/usr/bin/env python3
"""
A/B test: Scaled exits — 100% TRIM vs 50% TRIM.

Result: Keep 100%. TRIM barely fires (3x in 4 windows). 50% costs -1.5%.

Usage: cd backend && python3 -m backtest.tests.test_scaled_exits
"""
import asyncio
import sys
import os
import json
import subprocess

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

PM_PATH = os.path.join(BACKEND_DIR, "backtest", "position_manager.py")


def patch_pm(enable_scaled: bool, original: str):
    if enable_scaled:
        patched = original.replace(
            '_EXIT_100_SIGNALS = {"TRIM_HARD", "NO_LONG", "TRIM"}',
            '_EXIT_100_SIGNALS = {"TRIM_HARD", "NO_LONG"}',
        ).replace(
            '_EXIT_50_SIGNALS: set = set()  # TRIM moved to 100% for cleaner trade tracking',
            '_EXIT_50_SIGNALS = {"TRIM"}  # A/B test: TRIM exits 50%',
        )
    else:
        patched = original
    with open(PM_PATH, "w") as f:
        f.write(patched)


def extra_metrics(trades):
    return {
        "trim": sum(1 for t in trades if t.exit_signal == "TRIM"),
        "stop_loss": sum(1 for t in trades if t.exit_signal == "STOP_LOSS"),
    }


async def worker(variant: str, output_file: str):
    from backtest.tests.ab_test_base import run_ab_windows
    await run_ab_windows(variant, output_file, extra_trade_metrics=extra_metrics)


def main():
    with open(PM_PATH) as f:
        original = f.read()

    print(f"\n{'='*70}")
    print(f"SCALED EXITS A/B TEST — 100% TRIM vs 50% TRIM")
    print(f"{'='*70}\n")

    variants = [("100%_exit", False), ("50%_TRIM", True)]
    all_results = {}

    try:
        for label, scaled in variants:
            print(f"\n{'─'*70}\n  Running: {label}\n{'─'*70}\n")
            patch_pm(scaled, original)
            out = f"/tmp/scaled_exits_{label}.json"
            subprocess.run(
                [sys.executable, __file__, "--worker", label, out],
                timeout=3600, check=True,
            )
            with open(out) as f:
                all_results[label] = json.load(f)
    finally:
        with open(PM_PATH, "w") as f:
            f.write(original)
        print("\n[Restored original position_manager.py]")

    if "100%_exit" in all_results and "50%_TRIM" in all_results:
        ra, rb = all_results["100%_exit"], all_results["50%_TRIM"]
        print(f"\n{'='*70}\nCOMPARISON: 100% vs 50% TRIM\n{'='*70}\n")
        for idx in [0, 4, 5, 8]:
            k = str(idx)
            a, b = ra[k], rb[k]
            print(f"  W{idx}: {a['return']:+.1f}% → {b['return']:+.1f}% (Δ{b['return']-a['return']:+.1f}%) | "
                  f"trades {a['trades']}→{b['trades']} | TRIM exits {a.get('trim',0)}→{b.get('trim',0)}")
        tra = sum(ra[str(i)]["return"] for i in [0,4,5,8])
        trb = sum(rb[str(i)]["return"] for i in [0,4,5,8])
        print(f"\n  Aggregate: {tra:+.1f}% → {trb:+.1f}% (Δ{trb-tra:+.1f}%)")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        idx = sys.argv.index("--worker")
        asyncio.run(worker(sys.argv[idx+1], sys.argv[idx+2]))
    else:
        main()
