"""
After the spike: how prices come back from extreme z-scores (docs/reviews/after-the-spike-study.md).

    python -m backtest.after_spike_study daily            (from backend/; 151 coins, 1D)
    python -m backtest.after_spike_study 4h <replay.pkl>  (10 primary coins, 4H replay rows)

Windows 1-9 only: bars after 2026-03-29 are dropped before anything is measured.
"""
from __future__ import annotations

import json
import pickle
import statistics as st
import sys
from collections import defaultdict

from backtest.larsson_study import RUNS_DIR

END_DAY = 20541                      # 2026-03-29
END_MS = (END_DAY + 1) * 86_400_000
QUIET = 20                           # bars below T before an event
SPIKE_END_Z = 1.5
HORIZON = 60
REENTRY_Z = 2.0
THRESHOLDS = (2.5, 3.0, 3.5)


def q(v, p):
    s = sorted(v)
    return s[int(p * (len(s) - 1))] if s else None


def summary(v, pct=True):
    v = [x for x in v if x is not None]
    if not v:
        return "n=0"
    f = (lambda x: f"{100 * x:+.0f}%") if pct else (lambda x: f"{x:.1f}")
    return f"median {f(st.median(v))} (q25 {f(q(v, .25))}, q75 {f(q(v, .75))}), n={len(v)}"


def events(series, T):
    """series: list of (close, z, regime). Yields per-event measurements."""
    n = len(series)
    out = []
    i = QUIET
    while i < n:
        z = series[i][1]
        if z is not None and z >= T and all((series[j][1] or 0) < T for j in range(i - QUIET, i)):
            end = i
            while end + 1 < n and end - i < HORIZON and (series[end + 1][1] or 0) >= SPIKE_END_Z:
                end += 1
            pk = max(range(i, end + 1), key=lambda k: series[k][0])
            peak = series[pk][0]
            pre = series[i - QUIET][0]
            after = series[pk + 1: pk + 1 + HORIZON]
            if len(after) < HORIZON:
                i = end + 1
                continue
            trough_k = min(range(len(after)), key=lambda k: after[k][0])
            trough = after[trough_k][0]
            zs = [a[1] for a in after if a[1] is not None]
            below = lambda lvl: next((k + 1 for k, a in enumerate(after) if a[1] is not None and a[1] < lvl), None)
            re = next((k for k in range(pk + 1, min(n, pk + 1 + HORIZON))
                       if series[k][2] == "MARKUP" and series[k][1] is not None and series[k][1] < REENTRY_Z), None)
            fwd = lambda k, h: (series[k + h][0] / series[k][0] - 1) if k is not None and k + h < n else None
            out.append(dict(
                dd=trough / peak - 1, bars_to_trough=trough_k + 1,
                giveback=(peak - trough) / (peak - pre) if peak > pre else None,
                below_pre=trough < pre, min_z=min(zs) if zs else None,
                to_z1=below(1.0), to_z0=below(0.0), rise=peak / pre - 1,
                re_bars=None if re is None else re - pk, re10=fwd(re, 10), re30=fwd(re, 30), spike_end=end))
            i = end + 1
        else:
            i += 1
    return out


def baseline(series, spike_ends):
    """Uptrend bars with 1 <= z < 2 not within HORIZON bars after a spike."""
    near = set()
    for e in spike_ends:
        near.update(range(e, e + HORIZON))
    n = len(series)
    r10, r30 = [], []
    for k, (c, z, reg) in enumerate(series):
        if reg == "MARKUP" and z is not None and 1.0 <= z < 2.0 and k not in near:
            if k + 10 < n:
                r10.append(series[k + 10][0] / c - 1)
            if k + 30 < n:
                r30.append(series[k + 30][0] / c - 1)
    return r10, r30


def report(name, per_coin):
    print(f"\n=== {name}: {len(per_coin)} markets")
    for T in THRESHOLDS:
        ev, ends_by = [], {}
        for sym, s in per_coin.items():
            e = events(s, T)
            ev += e
            ends_by[sym] = [x["spike_end"] for x in e]
        if not ev:
            print(f"z >= {T}: no events")
            continue
        print(f"\nz >= {T}: {len(ev)} spikes on {sum(1 for v in ends_by.values() if v)} markets")
        print("  rise into the peak (from pre-spike level):", summary([e["rise"] for e in ev]))
        print("  deepest drawdown from peak, next 60 bars: ", summary([e["dd"] for e in ev]))
        print("  bars from peak to that low:                ", summary([e["bars_to_trough"] for e in ev], pct=False))
        print("  share of the spike given back:             ", summary([e["giveback"] for e in ev]))
        print(f"  fell below the pre-spike level:            {100 * sum(e['below_pre'] for e in ev) / len(ev):.0f}%")
        print("  lowest z in the 60 bars after the peak:    ", summary([e["min_z"] for e in ev], pct=False))
        print(f"  z back below 1 within 60 bars:             {100 * sum(e['to_z1'] is not None for e in ev) / len(ev):.0f}%  (bars: {summary([e['to_z1'] for e in ev], pct=False)})")
        print(f"  z back below 0 within 60 bars:             {100 * sum(e['to_z0'] is not None for e in ev) / len(ev):.0f}%  (bars: {summary([e['to_z0'] for e in ev], pct=False)})")
        re = [e for e in ev if e["re_bars"] is not None]
        print(f"  re-entry bar (Uptrend, z < 2) after peak:  {100 * len(re) / len(ev):.0f}% of spikes, bars after peak: {summary([e['re_bars'] for e in re], pct=False)}")
        print("    return 10 bars after re-entry:           ", summary([e["re10"] for e in re]))
        print("    return 30 bars after re-entry:           ", summary([e["re30"] for e in re]))
        b10, b30 = [], []
        for sym, s in per_coin.items():
            a, b = baseline(s, ends_by[sym])
            b10 += a
            b30 += b
        print("    baseline Uptrend z 1-2, 10 bars:         ", summary(b10))
        print("    baseline Uptrend z 1-2, 30 bars:         ", summary(b30))
        print(f"    share positive after 30 bars: re-entry {100 * sum(e['re30'] > 0 for e in re if e['re30'] is not None) / max(1, sum(e['re30'] is not None for e in re)):.0f}%, baseline {100 * sum(x > 0 for x in b30) / max(1, len(b30)):.0f}%")


def daily():
    regimes = json.loads((RUNS_DIR / "breadth_history_regimes.json").read_text())
    closes = json.loads((RUNS_DIR / "breadth_history.json").read_text())["closes"]
    per = {}
    for pair, rows in regimes.items():
        c = closes.get(pair, {})
        s = [(c[str(d)], z, reg) for d, reg, z in rows if d <= END_DAY and str(d) in c]
        if len(s) > QUIET + HORIZON:
            per[pair] = s
    report("1D, 151-coin rebuild", per)


def four_hour(path):
    rows = pickle.loads(open(path, "rb").read())
    by = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["timestamp"]):
        if r["timestamp"] < END_MS and r.get("price"):
            by[r["symbol"]].append((r["price"], r.get("zscore"), r.get("regime")))
    report("4H, 10 primary coins (replay of today's logic)", dict(by))


if __name__ == "__main__":
    if sys.argv[1] == "daily":
        daily()
    else:
        four_hour(sys.argv[2])
