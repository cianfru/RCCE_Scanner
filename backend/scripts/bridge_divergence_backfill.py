#!/usr/bin/env python3
"""
bridge_divergence_backfill.py
=============================

Replay the BTC × HL-bridge divergence signal over the history stored in
``bridge_snapshots`` (SQLite) and print how it would have behaved.

For each historical snapshot, computes the divergence label against its own
trailing 7d baseline (same logic as the live signal), then flags every
transition into DIVERGING or EXHAUSTION and shows BTC's subsequent path:

    +3h / +6h / +12h / +24h return  and  max/min over the next 6h

Outcome rule (rough sanity check — not a strict win/loss):
  - DISTRIBUTION event (score_6h > 0) is "hit" if BTC drew down ≥1% within 6h
  - ACCUMULATION  event (score_6h < 0) is "hit" if BTC rallied ≥1% within 6h

Usage
-----
    # Against the local default DB path (or HYPERLENS_DB_PATH env var)
    python scripts/bridge_divergence_backfill.py

    # Against a specific DB file pulled from Railway
    python scripts/bridge_divergence_backfill.py --db /path/to/hyperlens.db

    # Only show EXHAUSTION events (skip DIVERGING)
    python scripts/bridge_divergence_backfill.py --min-label EXHAUSTION

    # Only confirmed events (1h agrees with 6h)
    python scripts/bridge_divergence_backfill.py --confirmed-only

The script reuses ``_compute_divergence`` from ``hl_bridge.py`` so any tuning
changes to the live signal are reflected here automatically.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Ensure backend/ is importable when running this script directly
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from hl_bridge import (  # noqa: E402
    _compute_divergence,
    _pair_snapshots_with_btc,
    _fetch_btc_closes,
    _DIV_BASELINE_DAYS,
    _DIV_MIN_SAMPLES,
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_snapshots(db_path: str) -> List[dict]:
    """Read every snapshot from bridge_snapshots, oldest first."""
    if not Path(db_path).exists():
        raise SystemExit(
            f"DB not found: {db_path}\n"
            f"Hint: set HYPERLENS_DB_PATH or pass --db. If you're running this "
            f"locally, pull the DB down from Railway first:\n"
            f"    railway run -- bash -c 'cat $HYPERLENS_DB_PATH' > hyperlens.db"
        )
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT ts, trend, signal,
                      w1h_inflow_usd, w1h_outflow_usd, w1h_net_usd,
                      w6h_inflow_usd, w6h_outflow_usd, w6h_net_usd,
                      w24h_inflow_usd, w24h_outflow_usd, w24h_net_usd,
                      w24h_complete, sample_span_s, tx_sample_size
                 FROM bridge_snapshots
                ORDER BY ts ASC"""
        ).fetchall()
    finally:
        conn.close()

    return [{
        "ts": r[0],
        "trend": r[1],
        "signal": r[2],
        "w1h":  {"inflow_usd": r[3],  "outflow_usd": r[4],  "net_usd": r[5]},
        "w6h":  {"inflow_usd": r[6],  "outflow_usd": r[7],  "net_usd": r[8]},
        "w24h": {"inflow_usd": r[9],  "outflow_usd": r[10], "net_usd": r[11], "complete": bool(r[12])},
        "sample_span_seconds": r[13],
        "tx_sample_size": r[14],
    } for r in rows]


# ---------------------------------------------------------------------------
# Outcome lookups — walk forward from event time using BTC closes
# ---------------------------------------------------------------------------

def btc_at(closes: List[tuple], target_ts: float, tol_s: int = 600) -> Optional[float]:
    """Closest BTC close within tolerance, or None."""
    if not closes:
        return None
    best = None
    best_diff = tol_s + 1
    for ts, c in closes:
        diff = abs(ts - target_ts)
        if diff < best_diff:
            best_diff = diff
            best = c
        elif ts > target_ts + tol_s:
            break
    return best if best_diff <= tol_s else None


def btc_extremes_in_window(
    closes: List[tuple], start_ts: float, window_s: int
) -> tuple:
    """Return (min_price, min_ret, max_price, max_ret) over [start_ts, start_ts+window_s]."""
    start_price = btc_at(closes, start_ts)
    if start_price is None:
        return (None, None, None, None)
    end_ts = start_ts + window_s
    lo = hi = start_price
    lo_ts = hi_ts = start_ts
    for ts, c in closes:
        if ts < start_ts:
            continue
        if ts > end_ts:
            break
        if c < lo:
            lo, lo_ts = c, ts
        if c > hi:
            hi, hi_ts = c, ts
    return (lo, (lo / start_price) - 1.0, hi, (hi / start_price) - 1.0)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "   --"
    return f"{v * 100:+5.2f}%"


def fmt_score(v: Optional[float]) -> str:
    if v is None:
        return "    -"
    return f"{v:+5.2f}"


def color(text: str, code: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"\033[{code}m{text}\033[0m"


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

async def run_audit(args) -> int:
    db_path = args.db or os.environ.get(
        "HYPERLENS_DB_PATH", str(BACKEND / "hyperlens.db")
    )
    use_color = sys.stdout.isatty() and not args.no_color

    print(f"loading snapshots from {db_path} …")
    snapshots = load_snapshots(db_path)
    if not snapshots:
        print("no snapshots found — DB is empty.")
        return 1
    oldest, newest = snapshots[0]["ts"], snapshots[-1]["ts"]
    span_h = (newest - oldest) / 3600.0
    print(
        f"  loaded {len(snapshots)} snapshots, "
        f"{fmt_ts(oldest)} → {fmt_ts(newest)}  ({span_h:.1f}h)"
    )

    # Fetch BTC 15m closes covering the full snapshot range + 1 day lookahead
    lookahead_h = 26  # enough for +24h outcome lookups
    needed_h = int(span_h + _DIV_BASELINE_DAYS * 24 + lookahead_h + 1)
    print(f"fetching BTC 15m closes (~{needed_h}h of history) …")
    btc_closes = await _fetch_btc_closes(hours=needed_h)
    if not btc_closes:
        print("failed to fetch BTC closes — check network/CCXT.")
        return 2
    btc_oldest, btc_newest = btc_closes[0][0], btc_closes[-1][0]
    print(
        f"  got {len(btc_closes)} closes, "
        f"{fmt_ts(btc_oldest)} → {fmt_ts(btc_newest)}"
    )

    paired = _pair_snapshots_with_btc(snapshots, btc_closes)
    print(f"paired {len(paired)}/{len(snapshots)} snapshots with BTC closes")
    if len(paired) < _DIV_MIN_SAMPLES + 5:
        print(
            f"  not enough paired data to audit (need ≥{_DIV_MIN_SAMPLES + 5}). "
            f"Likely the DB is younger than ~4h or BTC fetch was partial."
        )
        return 3

    # Replay divergence at every paired snapshot
    print("\nreplaying divergence at every snapshot …")
    events: List[dict] = []
    prev_label: Optional[str] = None
    prev_direction: Optional[str] = None  # "DIST" | "ACCUM" | None
    last_event_ts: float = 0.0
    last_event_direction: Optional[str] = None
    min_label_rank = {
        "DIVERGING": 1, "EXHAUSTION": 2,
    }.get(args.min_label.upper(), 1)
    min_gap_s = max(0, int(args.min_gap_minutes)) * 60

    for i in range(_DIV_MIN_SAMPLES, len(paired)):
        trailing = paired[: i + 1]
        div = _compute_divergence(trailing)
        if div is None:
            continue
        label = div["label"]
        score = div["score_6h"]
        confirmed = bool(div["confirmed"])
        direction = "DIST" if score > 0 else "ACCUM"

        rank = {"DIVERGING": 1, "EXHAUSTION": 2}.get(label, 0)
        ts = trailing[-1]["ts"]

        # Event = transition across threshold OR direction flip inside an active state
        is_transition = (
            rank >= min_label_rank and (
                (prev_label not in ("DIVERGING", "EXHAUSTION"))
                or (prev_direction != direction)
                or (label == "EXHAUSTION" and prev_label == "DIVERGING")
            )
        )

        # Collapse adjacent same-direction events inside min-gap window
        if is_transition and direction == last_event_direction and (ts - last_event_ts) < min_gap_s:
            is_transition = False

        if is_transition and (not args.confirmed_only or confirmed):
            start_price = btc_at(btc_closes, ts)
            outcomes = {}
            for horizon in (3, 6, 12, 24):
                h_ts = ts + horizon * 3600
                h_price = btc_at(btc_closes, h_ts)
                if start_price and h_price:
                    outcomes[horizon] = (h_price / start_price) - 1.0
                else:
                    outcomes[horizon] = None
            _, min_ret_6h, _, max_ret_6h = btc_extremes_in_window(
                btc_closes, ts, 6 * 3600
            )

            last_event_ts = ts
            last_event_direction = direction
            events.append({
                "ts": ts,
                "label": label,
                "direction": direction,
                "confirmed": confirmed,
                "score_6h": score,
                "score_1h": div["score_1h"],
                "btc_z_6h": div["btc_return_6h_z"],
                "flow_z_6h": div["net_flow_6h_z"],
                "btc_price": start_price,
                "ret_3h": outcomes[3],
                "ret_6h": outcomes[6],
                "ret_12h": outcomes[12],
                "ret_24h": outcomes[24],
                "min_ret_6h": min_ret_6h,
                "max_ret_6h": max_ret_6h,
                "interpretation": div["interpretation"],
            })

        prev_label = label
        prev_direction = direction

    if not events:
        print("  no DIVERGING/EXHAUSTION events fired in this history.")
        return 0

    # ── Pretty table ──────────────────────────────────────────────────────
    print()
    print(color(
        f"{'TIME':<19}  {'LABEL':<10} {'DIR':<5} {'CONF':<4} "
        f"{'SCORE':>6} {'BTCz':>6} {'FLOWz':>7} {'PRICE':>10}  "
        f"{'+3h':>7} {'+6h':>7} {'+12h':>7} {'+24h':>7}  "
        f"{'LO6h':>7} {'HI6h':>7}  hit",
        "1;37", use_color,
    ))
    print("-" * 148)

    dist_hits = accum_hits = dist_n = accum_n = 0
    for e in events:
        hit = False
        if e["direction"] == "DIST" and e["min_ret_6h"] is not None:
            hit = e["min_ret_6h"] <= -0.01
            dist_n += 1
            if hit:
                dist_hits += 1
        elif e["direction"] == "ACCUM" and e["max_ret_6h"] is not None:
            hit = e["max_ret_6h"] >= 0.01
            accum_n += 1
            if hit:
                accum_hits += 1

        row_color = (
            "31" if e["label"] == "EXHAUSTION" and e["direction"] == "DIST" else
            "36" if e["label"] == "EXHAUSTION" and e["direction"] == "ACCUM" else
            "33" if e["label"] == "DIVERGING" else
            "37"
        )
        price_s = f"${e['btc_price']:,.0f}" if e["btc_price"] else "     -"
        line = (
            f"{fmt_ts(e['ts']):<19}  "
            f"{e['label']:<10} {e['direction']:<5} "
            f"{'Y' if e['confirmed'] else '-':<4} "
            f"{fmt_score(e['score_6h']):>6} "
            f"{fmt_score(e['btc_z_6h']):>6} "
            f"{fmt_score(e['flow_z_6h']):>7} "
            f"{price_s:>10}  "
            f"{fmt_pct(e['ret_3h']):>7} {fmt_pct(e['ret_6h']):>7} "
            f"{fmt_pct(e['ret_12h']):>7} {fmt_pct(e['ret_24h']):>7}  "
            f"{fmt_pct(e['min_ret_6h']):>7} {fmt_pct(e['max_ret_6h']):>7}  "
            f"{'✓' if hit else ' '}"
        )
        print(color(line, row_color, use_color))

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print(color("SUMMARY", "1;37", use_color))
    print("-" * 40)
    print(f"total events:          {len(events)}")
    print(f"  distribution (DIST): {dist_n}")
    print(f"  accumulation (ACCUM):{accum_n}")
    if dist_n:
        print(
            f"  DIST hit-rate (BTC -≥1% in 6h):   "
            f"{dist_hits}/{dist_n} = {100*dist_hits/dist_n:.0f}%"
        )
    if accum_n:
        print(
            f"  ACCUM hit-rate (BTC +≥1% in 6h):  "
            f"{accum_hits}/{accum_n} = {100*accum_hits/accum_n:.0f}%"
        )
    exh_n = sum(1 for e in events if e["label"] == "EXHAUSTION")
    div_n = sum(1 for e in events if e["label"] == "DIVERGING")
    conf_n = sum(1 for e in events if e["confirmed"])
    print(f"  EXHAUSTION events:   {exh_n}")
    print(f"  DIVERGING events:    {div_n}")
    print(f"  confirmed (1h+6h):   {conf_n}")

    avg_24h_dist = [e["ret_24h"] for e in events if e["direction"] == "DIST" and e["ret_24h"] is not None]
    avg_24h_accum = [e["ret_24h"] for e in events if e["direction"] == "ACCUM" and e["ret_24h"] is not None]
    if avg_24h_dist:
        print(f"  DIST  avg BTC +24h:  {100 * sum(avg_24h_dist) / len(avg_24h_dist):+.2f}%")
    if avg_24h_accum:
        print(f"  ACCUM avg BTC +24h:  {100 * sum(avg_24h_accum) / len(avg_24h_accum):+.2f}%")
    print()
    print(
        "Hit rule is a rough sanity check, not a strict backtest — it only "
        "asks whether BTC moved in the signalled direction within 6h. "
        "Numbers are noisy on small N; use this as a smoke test, not gospel."
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=None, help="Path to hyperlens.db (default: HYPERLENS_DB_PATH env or backend/hyperlens.db)")
    p.add_argument("--min-label", default="DIVERGING", choices=["DIVERGING", "EXHAUSTION"],
                   help="Minimum severity to flag as an event (default: DIVERGING)")
    p.add_argument("--confirmed-only", action="store_true",
                   help="Only show events where 1h score also crossed the bar")
    p.add_argument("--min-gap-minutes", type=int, default=60,
                   help="Suppress same-direction events closer than this many minutes (default: 60)")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = p.parse_args()
    return asyncio.run(run_audit(args))


if __name__ == "__main__":
    sys.exit(main())
