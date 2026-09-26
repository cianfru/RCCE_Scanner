"""
Who comes first, the traders or the spike? (docs/reviews/traders-vs-spikes-study.md)

    python research/traders_vs_spikes.py <data dir> [--now <epoch s>]

<data dir> holds fills/<address>.json ({"cohorts": [...], "fills": [[coin, time_ms, px, sz,
side, dir, startPosition, twap], ...]}) and candles/<coin>.json ([[t_ms, close], ...], 1h),
pulled from Hyperliquid's public API for today's roster. Nothing here reads the product.

Q1: fresh opens in the spike's direction per 12h bin around +-15%/24h spikes, against each
coin's baseline rate, counting only wallets whose fill history covers the bin.
Q2: the forward test's convergence rule applied to the past, against single opens.
Headline numbers use events older than 30 days (outside the month that picked the wallets).
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import statistics
from collections import defaultdict

H = 3600 * 1000
DAY = 24 * H
SPIKE = 0.15
QUIET = 7 * DAY
BIN = 12 * H
NB = 6                       # six 12h bins = 72h on each side
WINDOW = 180 * DAY
HOLD = 30 * DAY              # headline: older than this
CONV_WINDOW = 24 * H
CONV_MOVE = 0.05
CONV_OTHERS = 2
HORIZONS = (1, 3, 7)


def load(data_dir):
    wallets = {}
    for fn in os.listdir(os.path.join(data_dir, "fills")):
        d = json.load(open(os.path.join(data_dir, "fills", fn)))
        fills = sorted((f for f in d["fills"] if ":" not in f[0] and not f[0].startswith("@")), key=lambda f: f[1])
        reg = [f for f in d["fills"] if not f[7]]
        # Coverage: the regular list is capped at 2,000; before its oldest fill, fills may be missing.
        cover = min(f[1] for f in reg) if len(reg) >= 2000 else 0
        wallets[fn[:-5]] = {"cohorts": set(d["cohorts"]), "fills": fills, "cover": cover}
    candles = {}
    for fn in os.listdir(os.path.join(data_dir, "candles")):
        c = json.load(open(os.path.join(data_dir, "candles", fn)))
        if len(c) > 48:
            candles[fn[:-5]] = ([t for t, _ in c], [p for _, p in c])
    return wallets, candles


def opens_and_holdings(wallets):
    """Fresh opens (flat to position, or a side flip) and each wallet's position after every fill."""
    opens, pos = [], defaultdict(list)          # pos[(addr, coin)] = [(t, size_after)]
    for a, w in wallets.items():
        for coin, t, px, sz, side, d, start, _ in w["fills"]:
            before = float(start or 0)
            after = before + float(sz) * (1 if side == "B" else -1)
            pos[(a, coin)].append((t, after))
            if (before == 0 or (before > 0) != (after > 0)) and after != 0 and t >= w["cover"]:
                opens.append({"addr": a, "coin": coin, "t": t, "px": float(px), "side": "long" if after > 0 else "short",
                              "cohorts": w["cohorts"]})
    return opens, pos


def holding(pos, addr, coin, t):
    xs = pos.get((addr, coin))
    if not xs:
        return 0.0
    i = bisect.bisect_right([x[0] for x in xs], t) - 1
    return xs[i][1] if i >= 0 else 0.0


def spikes(candles, lo, hi):
    out = []
    for coin, (ts, c) in candles.items():
        last = {1: -10 ** 18, -1: -10 ** 18}
        for i in range(24, len(c)):
            if not (lo <= ts[i] <= hi):
                continue
            r = c[i] / c[i - 24] - 1
            for d in (1, -1):
                if (r >= SPIKE if d == 1 else r <= -SPIKE):
                    if ts[i] - last[d] > QUIET:
                        seg = range(i - 24, i + 1)
                        # the extreme close nearest the spike hour (ties: the latest)
                        m = max(seg, key=lambda k: ((-c[k] if d == 1 else c[k]), k))
                        out.append({"coin": coin, "dir": d, "t": ts[i], "start": ts[m]})
                    last[d] = ts[i]
    return out


def q1(wallets, opens, candles, sp, lo, hi, cohort):
    """Observed / expected opens per bin, pooled over spikes; plus before/after shares."""
    covers = {a: w["cover"] for a, w in wallets.items() if cohort in w["cohorts"]}
    by_coin = defaultdict(list)
    for o in opens:
        if o["addr"] in covers:
            by_coin[(o["coin"], o["side"])].append(o["t"])
    near = defaultdict(list)
    for s in sp:
        near[s["coin"]].append((s["start"] - QUIET, s["t"] + QUIET))

    def n_cov(t0):
        return sum(1 for c in covers.values() if c <= t0)

    # Baseline per coin and side: opens per wallet-hour, away from spikes, from covering wallets.
    base = {}
    for coin, (ts, _) in candles.items():
        span = [t for t in ts if lo <= t <= hi and not any(a <= t <= b for a, b in near[coin])]
        if not span:
            continue
        wh = sum(n_cov(t) for t in span[::12]) * 12   # sample every 12h to keep it quick
        for side in ("long", "short"):
            n = sum(1 for t in by_coin[(coin, side)] if lo <= t <= hi and not any(a <= t <= b for a, b in near[coin]))
            base[(coin, side)] = n / wh if wh else None
    labels = [f"-{72 - 12 * k}h" for k in range(NB)] + ["move"] + [f"+{12 * (k + 1)}h" for k in range(NB)]
    obs, exp = defaultdict(float), defaultdict(float)
    before_any = after_only = counted = 0
    for s in sp:
        side = "long" if s["dir"] == 1 else "short"
        rate = base.get((s["coin"], side)) or 0.0
        ts_o = by_coin[(s["coin"], side)]
        bins = [(s["start"] - (NB - k) * BIN, s["start"] - (NB - k - 1) * BIN) for k in range(NB)]
        bins += [(s["start"], s["t"])] + [(s["t"] + k * BIN, s["t"] + (k + 1) * BIN) for k in range(NB)]
        counted += 1
        pre = sum(1 for t in ts_o if bins[0][0] <= t < s["start"])
        post = sum(1 for t in ts_o if s["t"] < t <= bins[-1][1])
        before_any += pre > 0
        after_only += pre == 0 and post > 0
        for lab, (a, b) in zip(labels, bins):
            obs[lab] += sum(1 for t in ts_o if a <= t < b)
            exp[lab] += rate * n_cov(a) * max(b - a, H) / H
    return {"spikes": counted, "ratio": {l: (round(obs[l] / exp[l], 2) if exp[l] else None) for l in labels},
            "opens": {l: int(obs[l]) for l in labels},
            "share_with_open_before": round(before_any / counted, 3) if counted else None,
            "share_with_open_only_after": round(after_only / counted, 3) if counted else None}


def price_at(candles, coin, t):
    ts, c = candles[coin]
    i = bisect.bisect_left(ts, t)
    return c[i] if i < len(c) else None


def fwd(candles, coin, t, side, days):
    p0, p1 = price_at(candles, coin, t), price_at(candles, coin, t + days * DAY)
    if not p0 or not p1 or t + days * DAY > candles[coin][0][-1]:
        return None
    r = p1 / p0 - 1
    return r if side == "long" else -r


def q2(wallets, opens, pos, candles, sp, lo, hi):
    prof = [o for o in opens if "money_printer" in o["cohorts"] and o["coin"] in candles and lo <= o["t"] <= hi]
    prof_addrs = [a for a, w in wallets.items() if "money_printer" in w["cohorts"]]
    by_key = defaultdict(list)
    for o in sorted(prof, key=lambda o: o["t"]):
        by_key[(o["coin"], o["side"])].append(o)
    convs, members = [], set()
    for (coin, side), os_ in by_key.items():
        last_fire = -10 ** 18
        for j, o in enumerate(os_):
            now = o["t"]
            grp = {}
            for p in os_[:j + 1]:
                if now - p["t"] <= CONV_WINDOW:
                    sign = holding(pos, p["addr"], coin, now)
                    if (sign > 0) == (side == "long") and sign != 0:
                        grp.setdefault(p["addr"], p)
            if len(grp) < 2:
                continue
            ms = sorted(grp.values(), key=lambda p: p["t"])
            if abs(ms[-1]["px"] / ms[0]["px"] - 1) > CONV_MOVE:
                continue
            others = sum(1 for a in prof_addrs if a not in grp and
                         ((h := holding(pos, a, coin, now)) != 0) and (h > 0) == (side == "long"))
            if others > CONV_OTHERS or now - last_fire < CONV_WINDOW:
                continue
            last_fire = now
            members.update((m["addr"], m["coin"], m["t"]) for m in ms)
            convs.append({"coin": coin, "side": side, "t": now, "n": len(ms)})
    singles = [o for o in prof if (o["addr"], o["coin"], o["t"]) not in members]
    spike_starts = defaultdict(list)
    for s in sp:
        spike_starts[(s["coin"], "long" if s["dir"] == 1 else "short")].append(s["start"])

    def outcome(evts):
        res = {}
        for d in HORIZONS:
            v = [x for x in (fwd(candles, e["coin"], e["t"], e["side"], d) for e in evts) if x is not None]
            res[f"{d}d"] = {"n": len(v), "median_pct": round(100 * statistics.median(v), 2) if v else None,
                           "positive_pct": round(100 * sum(x > 0 for x in v) / len(v), 1) if v else None}
        return res
    before_spike = sum(1 for c in convs if any(0 <= st - c["t"] <= 72 * H for st in spike_starts[(c["coin"], c["side"])]))
    return {"convergences": len(convs), "of_3_or_more": sum(c["n"] >= 3 for c in convs),
            "before_a_spike_within_72h": before_spike,
            "convergence_outcome": outcome(convs), "single_open_outcome": outcome(singles),
            "convergence_3plus_outcome": outcome([c for c in convs if c["n"] >= 3])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--now", type=float, help="epoch seconds; default: newest candle")
    args = ap.parse_args()
    wallets, candles = load(args.data)
    opens, pos = opens_and_holdings(wallets)
    now = int(args.now * 1000) if args.now else max(ts[-1] for ts, _ in candles.values())
    lo = now - WINDOW
    out = {"wallets": {c: sum(c in w["cohorts"] for w in wallets.values()) for c in ("money_printer", "smart_money")},
           "fresh_opens": len(opens), "coins_with_prices": len(candles)}
    for name, hi in (("older_than_30_days", now - HOLD), ("all", now)):
        sp = spikes(candles, lo + 3 * DAY, hi - 3 * DAY)
        out[name] = {"spikes_up": sum(s["dir"] == 1 for s in sp), "spikes_down": sum(s["dir"] == -1 for s in sp),
                     "q1_profitable": q1(wallets, opens, candles, sp, lo, hi, "money_printer"),
                     "q1_large_accounts": q1(wallets, opens, candles, sp, lo, hi, "smart_money"),
                     "q2": q2(wallets, opens, pos, candles, sp, lo, hi - 7 * DAY)}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
