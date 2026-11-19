"""
A coin's ratio to BTC crossing above its weekly band: did the coin keep beating BTC? (docs/reviews/relative-band-study.md)

For each coin of the market history's list (Binance spot daily closes), the ratio coin / BTC and its weekly band
(relative_band.py). On each cross-up day, the ratio's change over the next 30, 60 and 90 days, minus the coin's
usual change over the same horizon (the mean over all its days within ERA_DAYS of the event). Cross-downs are
reported the same way, without a verdict.

    python -m backtest.relative_band_study --end 2026-11-14 --out <result.json>      (from backend/)
"""
from __future__ import annotations

import json
import math
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

import relative_band as rb

ROOT = Path(__file__).resolve().parent.parent
MH_SEED = ROOT / "seeds" / "market_history_seed.json"
HORIZONS = (30, 60, 90)
ERA_DAYS = 365
SPLIT_DAY = 19358                 # 1 January 2023: the two time halves
LEAVE_OUT = {"BTCUSDT", "PAXGUSDT"}

# The bar (fixed in the declaration)
MIN_EVENTS, MIN_COINS = 60, 20
MIN_MEDIAN_60 = 5.0               # percentage points of the ratio
MIN_SHARE_60 = 0.55


def pct(x: float) -> float:
    return 100 * (math.exp(x) - 1)


def events(days: np.ndarray, ratio: np.ndarray, kind: str = "up") -> List[dict]:
    """Each cross of `kind` with a complete 90-day outcome: its day and, per horizon, the excess log change of the
    ratio over the coin's era mean."""
    rd = rb.readings(days, ratio)
    lr = np.log(ratio)
    out = []
    last = len(ratio) - 1
    for i in rb.crosses(rd["state"])[kind]:
        if i + max(HORIZONS) > last:
            continue
        ev = {"day": int(days[i])}
        for h in HORIZONS:
            j0, j1 = max(0, i - ERA_DAYS), min(last - h, i + ERA_DAYS)
            base = float(np.mean(lr[j0 + h:j1 + h + 1] - lr[j0:j1 + 1]))
            ev[h] = float(lr[i + h] - lr[i]) - base
        out.append(ev)
    return out


def stats(evs: List[dict], h: int) -> dict:
    if not evs:
        return {"n": 0, "median": None, "share_positive": None}
    v = np.array([e[h] for e in evs])
    return {"n": int(len(v)), "median": round(pct(float(np.median(v))), 2), "share_positive": round(float((v > 0).mean()), 3)}


def verdict(by_coin: Dict[str, List[dict]]) -> dict:
    coins = sorted(c for c, e in by_coin.items() if e)
    allev = [e for c in coins for e in by_coin[c]]
    half_a = [e for k, c in enumerate(coins) for e in by_coin[c] if k % 2 == 0]
    half_b = [e for k, c in enumerate(coins) for e in by_coin[c] if k % 2 == 1]
    early = [e for e in allev if e["day"] < SPLIT_DAY]
    late = [e for e in allev if e["day"] >= SPLIT_DAY]
    s = {name: {h: stats(ev, h) for h in HORIZONS} for name, ev in
         (("all", allev), ("coins_a", half_a), ("coins_b", half_b), ("before_2023", early), ("from_2023", late))}
    enough = len(allev) >= MIN_EVENTS and len(coins) >= MIN_COINS
    ok = lambda x: x[60]["median"] is not None and x[60]["median"] >= MIN_MEDIAN_60 and x[60]["share_positive"] >= MIN_SHARE_60
    checks = {
        "enough": enough,
        "median_and_share_60": ok(s["all"]),
        "both_coin_halves": ok(s["coins_a"]) and ok(s["coins_b"]),
        "both_time_halves": all(s[k][60]["median"] is not None and s[k][60]["median"] > 0 for k in ("before_2023", "from_2023")),
        "median_90_positive": s["all"][90]["median"] is not None and s["all"][90]["median"] > 0,
    }
    return {"coins": len(coins), "events": len(allev), "stats": s, "checks": checks,
            "verdict": "too few" if not enough else ("met" if all(checks.values()) else "not met")}


def load_ratio(pair: str, btc, end: str):
    from backtest import binance_history as bh
    data = None
    try:
        data = bh.load(pair, "1d", start="2017-01-01", end=end)
    except urllib.error.HTTPError:
        data = None
    if data is None or len(data["close"]) == 0:
        try:
            data = bh.load(pair, "1d", start="2017-01-01", end=end, archive=True)
        except urllib.error.HTTPError:
            data = None
    if data is None or len(data["close"]) == 0:
        return None
    d, c = rb.series(data["timestamp"], data["close"])
    days, ratio = rb.align(d, c, *btc)
    return (days, ratio) if len(days) else None


def main(argv=None):
    import argparse
    from backtest import binance_history as bh
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--end", required=True, help="first day not used (exclusive), YYYY-MM-DD")
    ap.add_argument("--out", required=True)
    ap.add_argument("--counts", action="store_true", help="data check only: coins and days, no outcome")
    args = ap.parse_args(argv)
    pairs = [p for p in json.loads(MH_SEED.read_text())["pairs"] if p not in LEAVE_OUT]
    b = bh.load("BTCUSDT", "1d", start="2017-01-01", end=args.end)
    btc = rb.series(b["timestamp"], b["close"])
    up, down, counts = {}, {}, {}
    for p in pairs:
        r = load_ratio(p, btc, args.end)
        if r is None:
            counts[p] = 0
            continue
        counts[p] = int(len(r[0]))
        if args.counts:
            continue
        up[p] = events(*r, kind="up")
        down[p] = events(*r, kind="down")
    if args.counts:
        print(len([c for c in counts.values() if c]), "pairs with data;", sum(counts.values()), "days; none:", [p for p, c in counts.items() if not c])
        return
    res = {"up": verdict(up), "down": verdict(down), "days_per_pair": counts}
    Path(args.out).write_text(json.dumps(res, indent=1))
    for kind in ("up", "down"):
        v = res[kind]
        print(kind, v["verdict"], v["events"], "events,", v["coins"], "coins", v["checks"])
        for name, s in v["stats"].items():
            print(f"  {name:12}", "  ".join(f"{h}d {s[h]['median']:+.1f} ({100 * s[h]['share_positive']:.0f}% +, n {s[h]['n']})" if s[h]['n'] else f"{h}d -" for h in HORIZONS))


if __name__ == "__main__":
    main()
