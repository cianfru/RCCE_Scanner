"""Rebuild the Market page's band-stretch history: on every day since the market history starts, how many of its
coins sat at or above the band-stretch line (band_stretch.py), and their median band z.

    python -m backtest.stretch_history build      # writes seeds/band_stretch_seed.json

Binance spot daily closes for the market history's coin list (seeds/market_history_seed.json), read through the
cached loader (backtest/binance_history.py), each day's readings from closes up to that day only. The server
appends a row each day after the seed's last (market_history.update).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import band_stretch
from backtest import binance_history as bh

ROOT = Path(__file__).resolve().parent.parent
MH_SEED = ROOT / "seeds" / "market_history_seed.json"
OUT = ROOT / "seeds" / "band_stretch_seed.json"


def _closes(pair: str, end: str):
    data = None
    try:
        data = bh.load(pair, "1d", start="2017-01-01", end=end)
    except urllib.error.HTTPError:
        data = None
    if data is None or len(data["close"]) == 0:
        data = bh.load(pair, "1d", start="2017-01-01", end=end, archive=True)
    if data is None or len(data["close"]) == 0:
        return None
    return band_stretch.daily_series(data["timestamp"], data["close"])


def build(end_day: int) -> dict:
    """Rows [day, coins with band z, coins at or above the line, median band z] for the market history's first day
    to end_day (the last closed day)."""
    seed = json.loads(MH_SEED.read_text())
    first = seed["days"][0][0]
    end = datetime.fromtimestamp((end_day + 1) * 86_400, tz=timezone.utc).strftime("%Y-%m-%d")
    per_day = defaultdict(dict)
    used = 0
    for pair in seed["pairs"]:
        s = _closes(pair, end)
        if s is None:
            continue
        days, close = s
        a = band_stretch.readings(days, close)["a"]
        ok = np.isfinite(a) & (days >= first) & (days <= end_day)
        for d, v in zip(days[ok], a[ok]):
            per_day[int(d)][pair] = {"a": float(v)}
        used += 1
    rows = [band_stretch.aggregate(d, per_day[d]) for d in sorted(per_day)]
    return {"version": 1, "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "line": band_stretch.LINE,
            "source": "Binance spot daily closes, the market history's coins (backtest/stretch_history.py)",
            "pairs": len(seed["pairs"]), "pairs_read": used, "columns": ["day", "coins", "above", "median"],
            "rows": [r for r in rows if r]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("build",))
    ap.add_argument("--end-day", type=int, default=None, help="last closed day (default: yesterday, UTC)")
    args = ap.parse_args()
    end_day = args.end_day if args.end_day is not None else int(time.time()) // 86_400 - 1
    out = build(end_day)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(out['rows'])} days, {out['pairs_read']} of {out['pairs']} pairs read, last day {out['rows'][-1][0]}")


if __name__ == "__main__":
    main()
