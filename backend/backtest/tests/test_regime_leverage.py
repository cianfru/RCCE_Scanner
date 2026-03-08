#!/usr/bin/env python3
"""
A/B test: Regime-aware leverage — flat 2x vs regime-scaled.

Regime scales: MARKUP/REACC→1.0x, ACCUM/BLOWOFF/others→0.5x of base.

Result: Keep flat 2x. Regime scaling improves drawdown (-33%→-30%) but
costs -13.5% aggregate return. ACCUM entries get penalized too harshly.

Usage: cd backend && python3 -m backtest.tests.test_regime_leverage
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

REGIME_BLOCK = '''
# Regime-aware leverage scaling (multiplied against size_pct at entry)
_REGIME_LEVERAGE_SCALE = {
    "MARKUP":   1.0,   # Full size — confirmed trend
    "REACC":    1.0,   # Full size — re-accumulation is bullish
    "ACCUM":    0.5,   # Half size — early stage, lower conviction
    "BLOWOFF":  0.5,   # Half size — overextended, reduce risk
    "MARKDOWN": 0.5,   # Half size — unlikely to enter (BMSB blocks)
    "CAP":      0.5,   # Half size — capitulation zone
}
'''


def patch_pm(enable_regime: bool, original: str):
    if enable_regime:
        patched = original.replace(
            '_STOP_LOSS_PCT = -0.08        # -8% stop-loss per position',
            '_STOP_LOSS_PCT = -0.08        # -8% stop-loss per position' + REGIME_BLOCK,
        ).replace(
            '        size_pct = size_table.get(confluence, size_table.get("UNKNOWN", 0.0))\n'
            '\n'
            '        if size_pct <= 0:',
            '        size_pct = size_table.get(confluence, size_table.get("UNKNOWN", 0.0))\n'
            '\n'
            '        # Regime-aware leverage scaling\n'
            '        regime = getattr(bar, "regime", "UNKNOWN")\n'
            '        regime_scale = _REGIME_LEVERAGE_SCALE.get(regime, 0.5)\n'
            '        size_pct *= regime_scale\n'
            '\n'
            '        if size_pct <= 0:',
        )
    else:
        patched = original
    with open(PM_PATH, "w") as f:
        f.write(patched)


def extra_metrics(trades):
    return {
        "avg_size": sum(t.size_pct for t in trades) / len(trades) if trades else 0,
    }


async def worker(variant: str, output_file: str):
    from backtest.tests.ab_test_base import run_ab_windows
    await run_ab_windows(variant, output_file, extra_trade_metrics=extra_metrics)


def main():
    with open(PM_PATH) as f:
        original = f.read()

    print(f"\n{'='*70}")
    print(f"REGIME-AWARE LEVERAGE A/B TEST — Flat 2x vs Regime-Scaled")
    print(f"{'='*70}\n")

    variants = [("flat_2x", False), ("regime_scaled", True)]
    all_results = {}

    try:
        for label, regime in variants:
            print(f"\n{'─'*70}\n  Running: {label}\n{'─'*70}\n")
            patch_pm(regime, original)
            out = f"/tmp/regime_leverage_{label}.json"
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

    if "flat_2x" in all_results and "regime_scaled" in all_results:
        ra, rb = all_results["flat_2x"], all_results["regime_scaled"]
        print(f"\n{'='*70}\nCOMPARISON: Flat 2x vs Regime-Scaled\n{'='*70}\n")
        for idx in [0, 4, 5, 8]:
            k = str(idx)
            a, b = ra[k], rb[k]
            print(f"  W{idx}: {a['return']:+.1f}% → {b['return']:+.1f}% (Δ{b['return']-a['return']:+.1f}%) | "
                  f"Sharpe {a['sharpe']:.2f}→{b['sharpe']:.2f} | DD {a['dd']:.1f}%→{b['dd']:.1f}%")
        tra = sum(ra[str(i)]["return"] for i in [0,4,5,8])
        trb = sum(rb[str(i)]["return"] for i in [0,4,5,8])
        print(f"\n  Aggregate: {tra:+.1f}% → {trb:+.1f}% (Δ{trb-tra:+.1f}%)")
        print(f"  Worst DD:  {min(ra[str(i)]['dd'] for i in [0,4,5,8]):.1f}% → "
              f"{min(rb[str(i)]['dd'] for i in [0,4,5,8]):.1f}%")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        idx = sys.argv.index("--worker")
        asyncio.run(worker(sys.argv[idx+1], sys.argv[idx+2]))
    else:
        main()
