"""
Rebuild daily market breadth with the live engine (declared in docs/reviews/market-breadth-study.md).

    python -m backtest.breadth_history rebuild --out breadth_history      (from backend/)

At every closed daily candle compute_rcce runs on each coin's trailing window (up to 600
candles, as the scanner does; coins with fewer than 200 candles are skipped that day).
Output: per coin per day regime and z-score, plus per-day aggregates, written to
data/larsson_runs/<out>.json (gitignored). Recent days are kept for display; the study
itself only measures outcomes up to 2026-03-29.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

from backtest import binance_history as bh
from backtest.larsson_study import RUNS_DIR
from backtest.sector_momentum_study import _pair
from sectors import _S

START = "2019-01-01"
WINDOW = 600
MIN_BARS = 200
DAY_MS = 86_400_000


def coins():
    seen, out = set(), []
    for coin in ["BTC", *_S.keys()]:
        pair = _pair(coin)
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out


def _worker(pair):
    try:
        d = bh.load(pair, "1d", START, None)
    except Exception:
        return pair, None
    if d is None or len(d["close"]) < MIN_BARS + 1:
        return pair, None
    from engines.rcce_engine import compute_rcce
    rows = []
    for i in range(MIN_BARS, len(d["close"]) + 1):
        w = {k: v[max(0, i - WINDOW):i] for k, v in d.items()}     # candles up to and including bar i-1
        r = compute_rcce(w)
        day = int(d["timestamp"][i - 1]) // DAY_MS
        rows.append((day, r.get("regime"), round(float(r.get("z_score") or 0.0), 3), float(d["close"][i - 1])))
    return pair, rows


def rebuild(out_name):
    pairs = coins()
    with ProcessPoolExecutor(max_workers=4) as pool:
        per_coin = {p: rows for p, rows in pool.map(_worker, pairs, chunksize=2) if rows}
    days = defaultdict(list)
    for pair, rows in per_coin.items():
        for day, regime, z, close in rows:
            days[day].append((pair, regime, z))
    agg = []
    for day in sorted(days):
        rs = days[day]
        c = Counter(r for _, r, _ in rs)
        n = len(rs)
        agg.append({"day": day, "n": n, "counts": dict(c),
                    "uptrend": round(c.get("MARKUP", 0) / n, 4), "overheated": round(c.get("BLOWOFF", 0) / n, 4),
                    "downtrend": round(c.get("MARKDOWN", 0) / n, 4),
                    "basing": round((c.get("ACCUM", 0) + c.get("REACC", 0) + c.get("CAP", 0)) / n, 4),
                    "median_z": round(statistics.median(z for _, _, z in rs), 3)})
    closes = {p: {day: close for day, _, _, close in rows} for p, rows in per_coin.items()}
    (RUNS_DIR / f"{out_name}.json").write_text(json.dumps({"coins": len(per_coin), "days": agg, "closes": closes}))
    (RUNS_DIR / f"{out_name}_regimes.json").write_text(json.dumps({p: [(d, r, z) for d, r, z, _ in rows] for p, rows in per_coin.items()}))
    print(f"{len(per_coin)} coins, {len(agg)} days -> {out_name}.json")


END_DAY = 20541                      # 2026-03-29 (end of window 9); outcomes may not reach past it
MIN_COINS = 40
BANDS = [(0, .25, "under 25%"), (.25, .40, "25-40%"), (.40, .55, "40-55%"), (.55, .70, "55-70%"), (.70, .85, "70-85%"), (.85, 1.01, "85% and over")]
HORIZONS = (10, 30, 60)


def _band(b):
    return next(label for lo, hi, label in BANDS if lo <= b < hi)


def study(src, out_name):
    import urllib.request
    data = json.loads((RUNS_DIR / f"{src}.json").read_text())
    days = [d for d in data["days"] if d["n"] >= MIN_COINS]
    closes = data["closes"]
    btc = closes["BTCUSDT"]
    alts = [p for p in closes if p != "BTCUSDT"]
    by_day = {d["day"]: d for d in days}

    def fwd(t, h):
        e = t + h
        if e > END_DAY or str(t) not in btc or str(e) not in btc:
            return None
        rs = [closes[p][str(e)] / closes[p][str(t)] - 1 for p in alts if str(t) in closes[p] and str(e) in closes[p]]
        if len(rs) < MIN_COINS // 2:
            return None
        return {"btc": btc[str(e)] / btc[str(t)] - 1, "alt": statistics.median(rs)}

    def summarize(outs, h):
        o = [x for x in outs if x]
        if not o:
            return None
        def q(v, p): return sorted(v)[int(p * (len(v) - 1))]
        res = {"n": len(o)}
        for k in ("btc", "alt"):
            v = [x[k] for x in o]
            res[k] = {"median": round(100 * statistics.median(v), 1), "q25": round(100 * q(v, .25), 1),
                      "q75": round(100 * q(v, .75), 1), "pos": round(100 * sum(x > 0 for x in v) / len(v))}
        return res

    studied = [d["day"] for d in days if d["day"] <= END_DAY]
    base = {h: summarize([fwd(t, h) for t in studied], h) for h in HORIZONS}

    # Episodes: runs in the same band, gaps of up to 5 days merged; outcome from the first day.
    episodes = defaultdict(list)
    cur = None
    for t in studied:
        b = _band(by_day[t]["uptrend"])
        if cur and cur["band"] == b and t - cur["last"] <= 6:
            cur["last"] = t
            continue
        if cur:
            episodes[cur["band"]].append(cur)
        cur = {"band": b, "start": t, "last": t}
    if cur:
        episodes[cur["band"]].append(cur)

    def ep_rows(eps):
        rows = []
        for e in eps:
            rows.append({"start": e["start"], "end": e["last"], "days": e["last"] - e["start"] + 1,
                         "breadth": by_day[e["start"]]["uptrend"],
                         **{f"h{h}": fwd(e["start"], h) for h in HORIZONS}})
        return rows

    def verdict(rows):
        base30 = base[30]
        ok = [r for r in rows if r["h30"]]
        if len(ok) < 6:
            return {"direction": "too few episodes", "episodes": len(ok)}
        out = {"episodes": len(ok)}
        for k in ("alt", "btc"):
            above = sum(r["h30"][k] * 100 > base30[k]["median"] for r in ok)
            share = above / len(ok)
            out[k] = {"above_base": above, "share": round(share, 2),
                      "direction": "continuation" if share >= .75 else "pullback" if share <= .25 else "mixed"}
        return out

    bands = {}
    for lo, hi, label in BANDS:
        ts = [t for t in studied if lo <= by_day[t]["uptrend"] < hi]
        rows = ep_rows(episodes.get(label, []))
        bands[label] = {"days": len(ts), **{f"h{h}": summarize([fwd(t, h) for t in ts], h) for h in HORIZONS},
                        "episodes": rows, "verdict": verdict(rows)}

    # Thrusts (up 25 points in 10 days) and fades (down 20 from above 70%), 20-day cooldown.
    ups, fades, last_u, last_f = [], [], -99, -99
    for i, t in enumerate(studied):
        win = [by_day[x]["uptrend"] for x in studied[max(0, i - 10):i + 1] if t - x <= 10]
        b = by_day[t]["uptrend"]
        if b - min(win) >= .25 and t - last_u > 20:
            ups.append(t); last_u = t
        if max(win) >= .70 and max(win) - b >= .20 and t - last_f > 20:
            fades.append(t); last_f = t
    events = {name: {"rows": [{"day": t, "breadth": by_day[t]["uptrend"], **{f"h{h}": fwd(t, h) for h in HORIZONS}} for t in ts],
                     **{f"h{h}": summarize([fwd(t, h) for t in ts], h) for h in HORIZONS}}
              for name, ts in (("thrust", ups), ("fade", fades))}

    fg = json.loads(urllib.request.urlopen("https://api.alternative.me/fng/?limit=0&format=json", timeout=30).read())["data"]
    fear_greed = {int(x["timestamp"]) // 86_400: int(x["value"]) for x in fg}
    today = days[-1]
    pct = sum(d["uptrend"] < today["uptrend"] for d in days) / len(days)
    out = {"first_day": days[0]["day"], "last_day": today["day"], "end_day": END_DAY, "base": base, "bands": bands,
           "events": events, "today": {**today, "percentile": round(100 * pct), "band": _band(today["uptrend"])},
           "fear_greed_days": len(fear_greed)}
    (RUNS_DIR / f"{out_name}.json").write_text(json.dumps(out, indent=1, default=float))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rebuild")
    r.add_argument("--out", required=True)
    st = sub.add_parser("study")
    st.add_argument("--src", default="breadth_history")
    st.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "rebuild":
        rebuild(args.out)
    else:
        o = study(args.src, args.out)
        print("today", o["today"]["uptrend"], "percentile", o["today"]["percentile"], "band", o["today"]["band"])
        print("base", json.dumps(o["base"]))
        for k, b in o["bands"].items():
            print(k, "days", b["days"], "h30", json.dumps(b["h30"]), "verdict", json.dumps(b["verdict"]))
        for k, e in o["events"].items():
            print(k, len(e["rows"]), "h30", json.dumps(e["h30"]))


if __name__ == "__main__":
    main()
