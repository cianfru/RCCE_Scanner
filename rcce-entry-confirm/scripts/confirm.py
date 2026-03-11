#!/usr/bin/env python3
"""
RCCE Entry Confirmation Script
Fetches scanner + AIXBT data and prints a structured confirmation report.

Usage:
    python confirm.py ETH              # Confirm ETH entry (4h default)
    python confirm.py BTC --tf 1d      # Confirm BTC on daily timeframe
    python confirm.py --all            # Confirm all active entry signals
    python confirm.py SOL --json       # Raw JSON output

Environment:
    SCANNER_URL  — Base URL of the RCCE Scanner API (default: http://localhost:8000)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

SCANNER_URL = os.environ.get("SCANNER_URL", "https://rccescanner-production.up.railway.app")


def fetch_json(url: str) -> dict:
    """Fetch JSON from URL."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def format_report(data: dict) -> str:
    """Format confirmation data into a readable report."""
    lines = []

    symbol = data.get("symbol", "?")
    verdict = data.get("verdict", {})
    scanner = data.get("scanner")
    aixbt = data.get("aixbt", {})

    action = verdict.get("action", "UNKNOWN")
    reason = verdict.get("reason", "")

    # Verdict emoji
    emoji = {
        "GO": "+", "LEAN_GO": "~", "WAIT": ".",
        "NO": "X", "EXIT": "!", "MANUAL": "?",
    }.get(action, "?")

    lines.append(f"={'=' * 60}")
    lines.append(f"  ENTRY CONFIRMATION: {symbol}")
    lines.append(f"  VERDICT: [{emoji}] {action}")
    lines.append(f"  {reason}")
    lines.append(f"={'=' * 60}")
    lines.append("")

    # Scanner section
    if scanner:
        lines.append("  SCANNER ANALYSIS")
        lines.append(f"  ----------------")
        signal = scanner.get("signal", "?")
        regime = scanner.get("regime", "?")
        conf = scanner.get("confidence", 0)
        cond = scanner.get("conditions_met", 0)
        total = scanner.get("conditions_total", 0)
        eff = scanner.get("effective_conditions", 0)
        heat = scanner.get("heat", 0)
        hp = scanner.get("heat_phase", "")
        zs = scanner.get("zscore", 0)
        exh = scanner.get("exhaustion_state", "")
        floor = scanner.get("floor_confirmed", False)
        absorb = scanner.get("is_absorption", False)
        div = scanner.get("divergence") or "None"
        price = scanner.get("price", 0)
        vs = scanner.get("vol_scale", 1.0)
        warnings = scanner.get("signal_warnings", [])

        lines.append(f"  Signal:     {signal} ({cond}/{total} conditions, {eff} effective)")
        lines.append(f"  Regime:     {regime} | Confidence: {conf:.0f}%")
        lines.append(f"  Price:      ${price:,.2f}" if price else "  Price:      N/A")
        lines.append(f"  Heat:       {heat}/100 ({hp})")
        lines.append(f"  Z-Score:    {zs:.2f} (vol_scale: {vs:.2f})")
        lines.append(f"  Exhaustion: {exh} | Floor: {'YES' if floor else 'no'} | Absorption: {'YES' if absorb else 'no'}")
        lines.append(f"  Divergence: {div}")
        if warnings:
            lines.append(f"  Warnings:   {'; '.join(warnings)}")
        lines.append("")
    else:
        lines.append("  SCANNER: Not in current scan (AIXBT only)")
        lines.append("")

    # AIXBT section
    lines.append("  AIXBT SOCIAL INTELLIGENCE")
    lines.append(f"  -------------------------")
    if aixbt.get("error"):
        lines.append(f"  Error: {aixbt['error']}")
    elif not aixbt.get("found", False):
        lines.append(f"  Project '{aixbt.get('project_name', '?')}' not found on AIXBT")
    else:
        ns = aixbt.get("narrative_strength", "?")
        rl = aixbt.get("risk_level", "?")
        mom = aixbt.get("momentum_score", 0)
        pop = aixbt.get("popularity_score", 0)
        bull = aixbt.get("bullish_signal_count", 0)
        whale = aixbt.get("whale_signals", 0)
        risk_ct = aixbt.get("risk_alert_count", 0)
        conf_status = aixbt.get("confirmation", "?")
        top = aixbt.get("top_signals", [])

        lines.append(f"  Narrative:  {ns} (momentum: {mom:.1f}, popularity: {pop:.0f}h/24h)")
        lines.append(f"  Risk:       {rl} ({risk_ct} alerts)")
        lines.append(f"  Bullish:    {bull} signals | Whale Activity: {whale}")
        lines.append(f"  AIXBT says: {conf_status}")

        if top:
            lines.append("")
            lines.append("  Recent Signals:")
            for i, s in enumerate(top[:3], 1):
                cat = s.get("category", "?")
                desc = s.get("description", "")[:80]
                clusters = s.get("clusters", 0)
                lines.append(f"    {i}. [{cat}] {desc} ({clusters} clusters)")

    lines.append("")
    lines.append(f"  * Not financial advice. Always manage risk with proper position sizing.")
    lines.append(f"={'=' * 60}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RCCE Entry Confirmation")
    parser.add_argument("symbol", nargs="?", help="Symbol to confirm (e.g. ETH, BTC, SOL)")
    parser.add_argument("--tf", default="4h", help="Timeframe: 4h or 1d (default: 4h)")
    parser.add_argument("--all", action="store_true", help="Confirm all active entry signals")
    parser.add_argument("--json", action="store_true", dest="raw_json", help="Output raw JSON")
    parser.add_argument("--url", default=None, help="Override SCANNER_URL")
    args = parser.parse_args()

    base = args.url or SCANNER_URL

    if args.all:
        url = f"{base}/api/confirm?timeframe={args.tf}&signals_only=true"
        data = fetch_json(url)
        if "error" in data:
            print(f"Error: {data['error']}", file=sys.stderr)
            sys.exit(1)
        if args.raw_json:
            print(json.dumps(data, indent=2))
        else:
            confirmations = data.get("confirmations", [])
            if not confirmations:
                print("No active entry signals to confirm.")
            for c in confirmations:
                print(format_report(c))
                print()
    elif args.symbol:
        url = f"{base}/api/confirm/{args.symbol}?timeframe={args.tf}"
        data = fetch_json(url)
        if "error" in data:
            print(f"Error: {data['error']}", file=sys.stderr)
            sys.exit(1)
        if args.raw_json:
            print(json.dumps(data, indent=2))
        else:
            print(format_report(data))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
