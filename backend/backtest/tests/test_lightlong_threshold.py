#!/usr/bin/env python3
"""
A/B test: LIGHT_LONG threshold — 5/10 vs 6/10 conditions.

Result: Keep 5/10. Only 2 trades differ; 6/10 costs -2% return.

Usage: cd backend && python3 -m backtest.tests.test_lightlong_threshold
"""
import asyncio
import sys
import os
import re
import json
import subprocess

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

SYNTH_PATH = os.path.join(BACKEND_DIR, "signal_synthesizer.py")


def patch_threshold(threshold: int, original_source: str):
    patched = re.sub(
        r'conditions_met >= \d+ and regime in \("MARKUP", "REACC", "ACCUM"\)',
        f'conditions_met >= {threshold} and regime in ("MARKUP", "REACC", "ACCUM")',
        original_source,
    )
    with open(SYNTH_PATH, "w") as f:
        f.write(patched)


async def worker(threshold: int, output_file: str):
    # Verify patch
    with open(SYNTH_PATH) as f:
        src = f.read()
    match = re.search(r'conditions_met >= (\d+)', src)
    if match and int(match.group(1)) != threshold:
        print(f"ERROR: Expected threshold={threshold}, got {match.group(1)}")
        sys.exit(1)

    from backtest.tests.ab_test_base import run_ab_windows
    await run_ab_windows(f"T={threshold}", output_file)


def main():
    with open(SYNTH_PATH) as f:
        original = f.read()

    print(f"\n{'='*70}")
    print(f"LIGHT_LONG THRESHOLD A/B TEST — 5/10 vs 6/10 conditions")
    print(f"{'='*70}\n")

    all_results = {}
    try:
        for threshold in [5, 6]:
            print(f"\n{'─'*70}\n  Running: {threshold}/10\n{'─'*70}\n")
            patch_threshold(threshold, original)
            out = f"/tmp/lightlong_{threshold}.json"
            subprocess.run(
                [sys.executable, __file__, "--worker", str(threshold), out],
                timeout=3600, check=True,
            )
            with open(out) as f:
                all_results[threshold] = json.load(f)
    finally:
        with open(SYNTH_PATH, "w") as f:
            f.write(original)
        print("\n[Restored original signal_synthesizer.py]")

    # Comparison
    if 5 in all_results and 6 in all_results:
        r5, r6 = all_results[5], all_results[6]
        print(f"\n{'='*70}\nCOMPARISON: 5/10 vs 6/10\n{'='*70}\n")
        for idx in [0, 4, 5, 8]:
            k = str(idx)
            a, b = r5[k], r6[k]
            print(f"  W{idx}: {a['return']:+.1f}% → {b['return']:+.1f}% (Δ{b['return']-a['return']:+.1f}%) | "
                  f"trades {a['trades']}→{b['trades']} | Sharpe {a['sharpe']:.2f}→{b['sharpe']:.2f}")
        tr5 = sum(r5[str(i)]["return"] for i in [0,4,5,8])
        tr6 = sum(r6[str(i)]["return"] for i in [0,4,5,8])
        print(f"\n  Aggregate: {tr5:+.1f}% → {tr6:+.1f}% (Δ{tr6-tr5:+.1f}%)")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        idx = sys.argv.index("--worker")
        asyncio.run(worker(int(sys.argv[idx+1]), sys.argv[idx+2]))
    else:
        main()
