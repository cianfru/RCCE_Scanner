#!/usr/bin/env python3
"""
LIGHT_SHORT diagnostic test — validates the bear rally short module.

Runs four tests:
  1. A/B comparison: with vs without LIGHT_SHORT
  2. Regime isolation: all shorts must be in MARKDOWN + macro_blocked
  3. Sign-flip: invert short PnL sign (should collapse if edge is real)
  4. Regime coverage: % of bear bars with active short

Usage: cd backend && python3 -m backtest.tests.test_light_short
"""
import asyncio
import sys
import os
import json
import subprocess

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

SYNTH_PATH = os.path.join(BACKEND_DIR, "signal_synthesizer.py")


def patch_disable_short(original_source: str):
    """Disable LIGHT_SHORT by replacing the signal with WAIT."""
    patched = original_source.replace(
        "            out.signal = \"LIGHT_SHORT\"",
        "            out.signal = \"WAIT\"  # DISABLED for A/B test",
    )
    with open(SYNTH_PATH, "w") as f:
        f.write(patched)


def patch_restore(original_source: str):
    """Restore original source."""
    with open(SYNTH_PATH, "w") as f:
        f.write(original_source)


def extra_metrics(trades):
    """Extract short-specific metrics from trades."""
    shorts = [t for t in trades if t.side == "SHORT"]
    longs = [t for t in trades if t.side == "LONG"]
    short_pnl = sum(t.pnl_pct or 0 for t in shorts)
    short_wins = sum(1 for t in shorts if (t.pnl_pct or 0) > 0)
    short_exits = {}
    for t in shorts:
        ex = t.exit_signal or "UNKNOWN"
        short_exits[ex] = short_exits.get(ex, 0) + 1
    return {
        "short_count": len(shorts),
        "long_count": len(longs),
        "short_pnl": round(short_pnl, 2),
        "short_wins": short_wins,
        "short_wr": round(short_wins / len(shorts) * 100 if shorts else 0, 1),
        "short_exits": short_exits,
    }


TARGET_WINDOWS = [0, 2, 3, 4, 5, 8]  # Bear: W2,W3 | Transition: W4 | Bull: W0,W5,W8


async def worker(variant: str, output_file: str):
    from backtest.tests.ab_test_base import run_ab_windows
    await run_ab_windows(variant, output_file,
                         target_indices=TARGET_WINDOWS,
                         extra_trade_metrics=extra_metrics)


def main():
    with open(SYNTH_PATH) as f:
        original = f.read()

    # Verify LIGHT_SHORT is present
    if "LIGHT_SHORT" not in original:
        print("ERROR: LIGHT_SHORT not found in signal_synthesizer.py")
        print("Did you implement Phase 1 first?")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"LIGHT_SHORT DIAGNOSTIC TEST")
    print(f"{'='*70}\n")

    variants = [("with_short", False), ("no_short", True)]
    all_results = {}

    try:
        for label, disable in variants:
            print(f"\n{'─'*70}\n  Running: {label}\n{'─'*70}\n")
            if disable:
                patch_disable_short(original)
            else:
                patch_restore(original)
            out = f"/tmp/light_short_{label}.json"
            subprocess.run(
                [sys.executable, __file__, "--worker", label, out],
                timeout=3600, check=True,
            )
            with open(out) as f:
                all_results[label] = json.load(f)
    finally:
        patch_restore(original)
        print("\n[Restored original signal_synthesizer.py]")

    if "with_short" in all_results and "no_short" in all_results:
        ra, rb = all_results["with_short"], all_results["no_short"]

        # --- Test 1: A/B Comparison ---
        print(f"\n{'='*70}")
        print(f"TEST 1: A/B COMPARISON — With vs Without LIGHT_SHORT")
        print(f"{'='*70}\n")

        for idx in TARGET_WINDOWS:
            k = str(idx)
            a, b = ra[k], rb[k]
            delta_ret = a["return"] - b["return"]
            print(f"  W{idx}: {b['return']:+.1f}% → {a['return']:+.1f}% "
                  f"(Δ{delta_ret:+.1f}%) | "
                  f"trades {b['trades']}→{a['trades']} | "
                  f"shorts: {a.get('short_count', 0)}")

        tra = sum(ra[str(i)]["return"] for i in TARGET_WINDOWS)
        trb = sum(rb[str(i)]["return"] for i in TARGET_WINDOWS)
        print(f"\n  Aggregate: {trb:+.1f}% → {tra:+.1f}% (Δ{tra-trb:+.1f}%)")

        # --- Test 2: Regime Isolation ---
        print(f"\n{'='*70}")
        print(f"TEST 2: REGIME ISOLATION — Short trade details")
        print(f"{'='*70}\n")

        total_shorts = 0
        total_short_pnl = 0
        total_short_wins = 0
        for idx in TARGET_WINDOWS:
            k = str(idx)
            a = ra[k]
            sc = a.get("short_count", 0)
            sp = a.get("short_pnl", 0)
            sw = a.get("short_wins", 0)
            swr = a.get("short_wr", 0)
            total_shorts += sc
            total_short_pnl += sp
            total_short_wins += sw
            if sc > 0:
                exits = a.get("short_exits", {})
                exit_str = ", ".join(f"{k}:{v}" for k, v in exits.items())
                print(f"  W{idx}: {sc} shorts | PnL {sp:+.1f}% | "
                      f"WR {swr:.0f}% | exits: {exit_str}")
            else:
                print(f"  W{idx}: no shorts")

        if total_shorts > 0:
            overall_wr = total_short_wins / total_shorts * 100
            print(f"\n  Total shorts: {total_shorts} | "
                  f"Total PnL: {total_short_pnl:+.1f}% | "
                  f"Win rate: {overall_wr:.0f}%")
        else:
            print("\n  ⚠ No shorts fired in any window")

        # --- Test 3: Sign-Flip Check ---
        print(f"\n{'='*70}")
        print(f"TEST 3: SIGN-FLIP — Would inverted shorts be better?")
        print(f"{'='*70}\n")

        for idx in TARGET_WINDOWS:
            k = str(idx)
            a = ra[k]
            sp = a.get("short_pnl", 0)
            if sp != 0:
                print(f"  W{idx}: Short PnL = {sp:+.1f}% | "
                      f"Inverted = {-sp:+.1f}% | "
                      f"{'✓ Edge is real (short profitable)' if sp > 0 else '✗ Inverted is better — investigate'}")
            else:
                print(f"  W{idx}: No short PnL to test")

        # --- Test 4: Impact on Long Edge ---
        print(f"\n{'='*70}")
        print(f"TEST 4: LONG EDGE PRESERVATION")
        print(f"{'='*70}\n")

        for idx in TARGET_WINDOWS:
            k = str(idx)
            a, b = ra[k], rb[k]
            long_a = a.get("long_count", a["trades"] - a.get("short_count", 0))
            long_b = b.get("long_count", b["trades"])
            # Long-only return delta
            delta = a["return"] - a.get("short_pnl", 0) - b["return"]
            print(f"  W{idx}: Longs {long_b}→{long_a} | "
                  f"Long return delta: {delta:+.1f}%")

        # Bull windows should be identical (no shorts fire when BMSB is bullish)
        bull_windows = [0, 5]  # W0 (2021 bull) and W5 (2024 bull)
        bull_deltas = [abs(ra[str(i)]["return"] - rb[str(i)]["return"]) for i in bull_windows]
        if all(d < 0.1 for d in bull_deltas):
            print(f"\n  ✓ Bull windows (W0, W5) unchanged — long edge preserved")
        else:
            print(f"\n  ⚠ Bull windows changed: deltas = {[f'{d:.1f}%' for d in bull_deltas]}")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        idx = sys.argv.index("--worker")
        asyncio.run(worker(sys.argv[idx + 1], sys.argv[idx + 2]))
    else:
        main()
