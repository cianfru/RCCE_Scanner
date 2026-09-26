"""
Sector tilt inside the signal replay (declared in docs/reviews/sector-momentum-study.md).

    python -m backtest.sector_tilt_study universe
    python -m backtest.sector_tilt_study replay --window 3 --out tilt_w3.pkl     (one per window 1-9)
    python -m backtest.sector_tilt_study score tilt_w*.pkl --out sector_tilt      (from backend/)

The replay is split by walk-forward window so it runs in parallel. Each window
replays the whole universe (cross-market consensus is intact) from 600 4h bars
before the window start, the engines' full rolling history. Every variant is
scored on the same replayed signals; only new entries are filtered.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import math
import pickle
import statistics
import time
from datetime import datetime, timezone

from backtest import binance_history as bh
from backtest.larsson_study import HOLDOUT, RUNS_DIR, _compute_bmsb_filter, _weekly_completed, windows
from backtest.live_logic_check import score
from backtest.live_logic_replay import DATA_END, DATA_START, FIELDS, _fear_greed
from backtest.sector_momentum_study import END, START, _load, _pair
from sectors import _S

PER_SECTOR = 4
LISTED_BEFORE = "2022-07-01"
EXCLUDE = {"PAXG", "XAUT", "USDE", "USDT", "STABLE", "STBL", "USUAL"}   # stablecoins and gold
LOOKBACK = 30
MIN_MEMBERS = 3
BAR_MS = 14_400_000
WARMUP = 600
ENTRY = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE"}


def _day(date: str) -> int:
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp()) // 86_400


def universe():
    """BTC, ETH, then per sector the PER_SECTOR most traded coins listed before LISTED_BEFORE."""
    seen, by_sector = set(), collections.defaultdict(list)
    for coin, (sector, _) in _S.items():
        pair = _pair(coin)
        if pair in seen or sector == "Majors" or pair[:-4] in EXCLUDE:
            continue
        seen.add(pair)
        try:
            d = bh.load(pair, "1d", START, END)
        except Exception:
            d = None
        if d is None or len(d["close"]) < 60 or int(d["timestamp"][0]) // 86_400_000 >= _day(LISTED_BEFORE):
            continue
        by_sector[sector].append((statistics.mean(float(v) * float(c) for v, c in zip(d["volume"], d["close"])), pair[:-4], sector))
    out = [("BTC", "Majors"), ("ETH", "Majors")]
    for sector, rows in sorted(by_sector.items()):
        out += [(base, s) for _, base, s in sorted(rows, reverse=True)[:PER_SECTOR]]
    return out


def sector_strength():
    """{sector: {day: 30-day relative strength ending at that closed day}} from all coins with history."""
    prices, members = {}, collections.defaultdict(list)
    for coin, (sector, _) in _S.items():
        if coin == "BTC" or sector == "Majors" and coin != "ETH":
            continue
        c, d = _load(coin)
        if d and _pair(coin) not in prices:
            prices[_pair(coin)] = d
            members[sector].append(_pair(coin))
    btc = _load("BTC")[1]
    days = sorted(btc)

    def lr(series, d):
        a, b = series.get(d - 1), series.get(d)
        return math.log(b / a) if a and b else None

    out = {}
    for sector, pairs in members.items():
        daily = {}
        for d in days:
            xs = [x for x in (lr(prices[p], d) for p in pairs) if x is not None]
            b = lr(btc, d)
            daily[d] = statistics.median(xs) - b if len(xs) >= MIN_MEMBERS and b is not None else None
        strength = {}
        for d in days:
            xs = [daily.get(k) for k in range(d - LOOKBACK + 1, d + 1)]
            if all(x is not None for x in xs):
                strength[d] = sum(xs)
        out[sector] = strength
    return out


def ranks(strength, day):
    """(top-third sectors, bottom-third sectors) on a closed day."""
    s = sorted(((v[day], k) for k, v in strength.items() if day in v), reverse=True)
    if len(s) < 3:
        return set(), set()
    k = math.ceil(len(s) / 3)
    return {n for _, n in s[:k]}, {n for _, n in s[-k:]}


def replay(window: int, out: str):
    from backtest.replay_engine import run_replay
    w = next(w for w in windows() if w["index"] == window)
    assert window < HOLDOUT, "the holdout window is never replayed"
    coins = universe()
    lo = w["start_ms"] - WARMUP * BAR_MS
    data = {tf: {} for tf in ("4h", "1d", "1w")}
    for base, _ in coins:
        for tf in data:
            d = bh.load(f"{base}USDT", tf, DATA_START if tf != "1w" else "2019-01-07", DATA_END)
            if d is None:
                continue
            if tf == "4h":
                keep = (d["timestamp"] >= lo) & (d["timestamp"] < w["end_ms"])
                d = {k: v[keep] for k, v in d.items()}
                if len(d["timestamp"]) == 0:
                    continue
            data[tf][f"{base}/USDT"] = d
    t0 = time.time()
    res = asyncio.run(run_replay(list(data["4h"]), data["4h"], data["1d"], data["1w"], _fear_greed(), warmup_bars=WARMUP))
    rows = [{k: getattr(r, k, None) for k in FIELDS} for r in res]
    rows = [r for r in rows if w["start_ms"] <= r["timestamp"] < w["end_ms"]]
    with open(out, "wb") as fh:
        pickle.dump(rows, fh)
    print(f"W{window}: {len(rows)} bar results, {len(data['4h'])} coins, {time.time() - t0:.0f}s -> {out}")


def tilt(rows, sector_of, strength, mode):
    """Filter new entries; a skipped entry becomes a neutral signal. Open positions are unaffected
    (the manager only opens on an entry signal when flat, so filtering entries is exact)."""
    out = []
    for r in rows:
        sector = sector_of[r["symbol"]]
        if mode == "B" or r["signal"] not in ENTRY or sector == "Majors":
            out.append(r)
            continue
        top, bottom = ranks(strength, int(r["timestamp"] // 1000) // 86_400 - 1)
        allowed = (sector not in bottom) if mode == "T1" else (sector in top)
        out.append(r if allowed else {**r, "signal": "SECTOR_SKIP"})
    return out


def score_all(paths, out_name):
    rows = []
    for p in paths:
        with open(p, "rb") as fh:
            rows += pickle.load(fh)
    sector_of = {f"{base}/USDT": s for base, s in universe()}
    strength = sector_strength()
    weekly = _weekly_completed("BTC", windows()[HOLDOUT - 2]["end"])
    m = _compute_bmsb_filter(weekly)
    bmsb = (m, sorted(m))
    table = {}
    for mode in ("B", "T1", "T2"):
        variant = tilt(rows, sector_of, strength, mode)
        res = score(variant, bmsb)
        table[mode] = {
            "compounded_pct": round((math.prod(1 + r["total_return_pct"] / 100 for r in res) - 1) * 100, 2),
            "per_window_pct": [round(r["total_return_pct"], 2) for r in res],
            "worst_dd_pct": round(min(r["max_dd_pct"] for r in res), 2),
            "median_sharpe": round(statistics.median(r["sharpe"] for r in res), 2),
            "trades": sum(r["trades"] for r in res),
            "entries_skipped": sum(1 for r in variant if r["signal"] == "SECTOR_SKIP"),
        }
    b = table["B"]
    for mode in ("T1", "T2"):
        t = table[mode]
        t["windows_at_least_B"] = sum(x >= y for x, y in zip(t["per_window_pct"], b["per_window_pct"]))
        t["passes"] = (t["compounded_pct"] > b["compounded_pct"] and t["worst_dd_pct"] >= b["worst_dd_pct"] - 2
                       and t["windows_at_least_B"] >= 6)
    table["universe"] = universe()
    (RUNS_DIR / f"{out_name}.json").write_text(json.dumps(table, indent=1, default=float))
    print(json.dumps({k: v for k, v in table.items() if k != "universe"}, indent=1, default=float))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("universe")
    r = sub.add_parser("replay")
    r.add_argument("--window", type=int, required=True)
    r.add_argument("--out", required=True)
    s = sub.add_parser("score")
    s.add_argument("paths", nargs="+")
    s.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "universe":
        u = universe()
        print(len(u), collections.Counter(s for _, s in u), [b for b, _ in u])
    elif args.cmd == "replay":
        replay(args.window, args.out)
    else:
        score_all(args.paths, args.out)


if __name__ == "__main__":
    main()
