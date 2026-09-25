"""
Module D validity study (declared in docs/reviews/larsson-study.md before it was run).

    python -m backtest.pattern_study --out patterns_w1-9      (from backend/)

Measures, on windows 1-9 only:
  1. forming -> outcome rates per pattern type (the historical probability for a
     pattern seen forming);
  2. signed returns after a confirmed break (next open to +10/+20/+40 closes)
     against no-pattern level events and the unconditional drift;
  3. the same split by Larsson Line state at the break.
Intervals: bootstrap over calendar dates (breaks on one day move together).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Dict, List

import numpy as np

from backtest import binance_history as bh
from backtest.larsson_scenarios import universe
from backtest.larsson_study import PRIMARY, RUNS_DIR, windows
from engines.larsson_engine import compute_larsson_series
from engines.levels_engine import LevelConfig, compute_levels
from engines.patterns_engine import NAMES, PatternConfig, detect_patterns

HORIZONS = (10, 20, 40)
BULL_CODES = {10, 11, 12, 13}


def _fwd(d, i, sign) -> Dict[int, float]:
    """Signed return from the next open to the close h bars after the signal bar."""
    o, c = d["open"], d["close"]
    if i + 1 >= len(c):
        return {}
    entry = o[i + 1]
    return {h: sign * (c[i + h] / entry - 1) for h in HORIZONS if i + h < len(c)}


def _boot(events: List[dict], key: str, reps=2000, seed=11, stat=np.mean):
    """Mean and 90% interval, resampling calendar dates."""
    by_day = defaultdict(list)
    for e in events:
        if key in e:
            by_day[e["day"]].append(e[key])
    if not by_day:
        return None
    days = list(by_day)
    vals = [v for d in days for v in by_day[d]]
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(reps):
        pick = rng.integers(len(days), size=len(days))
        boots.append(stat([v for k in pick for v in by_day[days[k]]]))
    return {"n": len(vals), "mean": float(stat(vals)), "lo": float(np.percentile(boots, 5)), "hi": float(np.percentile(boots, 95))}


def _boot_diff(a: List[dict], b: List[dict], key: str, reps=2000, seed=13):
    """Difference in means (a - b) with a date bootstrap run on both groups."""
    da, db = defaultdict(list), defaultdict(list)
    for e in a:
        if key in e:
            da[e["day"]].append(e[key])
    for e in b:
        if key in e:
            db[e["day"]].append(e[key])
    if not da or not db:
        return None
    ka, kb = list(da), list(db)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(reps):
        pa = [v for k in rng.integers(len(ka), size=len(ka)) for v in da[ka[k]]]
        pb = [v for k in rng.integers(len(kb), size=len(kb)) for v in db[kb[k]]]
        out.append(np.mean(pa) - np.mean(pb))
    point = np.mean([v for k in ka for v in da[k]]) - np.mean([v for k in kb for v in db[k]])
    return {"diff": float(point), "lo": float(np.percentile(out, 5)), "hi": float(np.percentile(out, 95))}


def run(symbols: List[str]):
    w1, w9 = windows()[0]["start_ms"], windows()[8]["end_ms"]
    end = windows()[8]["end"]
    outcomes = defaultdict(lambda: defaultdict(int))
    breaks, level_events, drift = [], [], {"bull": [], "bear": []}
    for s in symbols:
        d = bh.load(f"{s}USDT", "1d", "2019-01-01", end)
        if d is None or len(d["close"]) < 300:
            continue
        ts = d["timestamp"]
        ll = compute_larsson_series(d["close"], ts)
        pats = detect_patterns(d, PatternConfig())
        coded_bars = defaultdict(set)
        for p in pats:
            if not (w1 <= ts[p.formed] < w9):
                continue
            if p.resolved is None:
                outcomes[p.kind]["still forming at W9 end"] += 1
                continue
            if ts[p.resolved] >= w9:
                continue
            if p.status == "confirmed":
                label = ("confirmed up" if p.code == 10 else "confirmed down") if p.kind == "rect" else "confirmed"
                outcomes[p.kind][label] += 1
                sign = 1 if p.code in BULL_CODES else -1
                i = p.resolved
                coded_bars[i].add(p.code)
                state = ll["state"][i]
                aligned = (state == "gold") if sign > 0 else (state == "blue")
                ev = {"symbol": s, "code": p.code, "day": int(ts[i]), "aligned": aligned, "state": state}
                ev.update({f"r{h}": v for h, v in _fwd(d, i, sign).items()})
                if "r20" in ev:
                    ev["win20"] = float(ev["r20"] > 0)
                breaks.append(ev)
            else:
                outcomes[p.kind][p.status] += 1
        lv = compute_levels(d, LevelConfig(), ll["state"], start=600)
        for i in range(len(ts)):
            if not (w1 <= ts[i] < w9):
                continue
            for e in lv[i].events:
                if e["event"] not in ("breakout", "breakdown") or coded_bars.get(i):
                    continue
                sign = 1 if e["event"] == "breakout" else -1
                ev = {"symbol": s, "event": e["event"], "day": int(ts[i])}
                ev.update({f"r{h}": v for h, v in _fwd(d, i, sign).items()})
                if "r20" in ev:
                    ev["win20"] = float(ev["r20"] > 0)
                level_events.append(ev)
            for side, sign in (("bull", 1), ("bear", -1)):
                r = _fwd(d, i, sign)
                if 20 in r:
                    drift[side].append({"day": int(ts[i]), "r20": r[20], "win20": float(r[20] > 0)})
    return outcomes, breaks, level_events, drift


def summarise(outcomes, breaks, level_events, drift) -> dict:
    out = {"forming_outcomes": {k: dict(v) for k, v in outcomes.items()}, "breaks": {}, "by_state": {}}
    no_pat = {"bull": [e for e in level_events if e["event"] == "breakout"],
              "bear": [e for e in level_events if e["event"] == "breakdown"]}
    groups = {f"{c} {NAMES[c]}": [e for e in breaks if e["code"] == c] for c in sorted({e["code"] for e in breaks})}
    groups["all bull patterns"] = [e for e in breaks if e["code"] in BULL_CODES]
    groups["all bear patterns"] = [e for e in breaks if e["code"] not in BULL_CODES]
    groups["no-pattern breakouts (Module B)"] = no_pat["bull"]
    groups["no-pattern breakdowns (Module B)"] = no_pat["bear"]
    groups["drift, long every coin-day"] = drift["bull"]
    groups["drift, short every coin-day"] = drift["bear"]
    for name, evs in groups.items():
        row = {h: _boot(evs, f"r{h}") for h in HORIZONS}
        row["win20"] = _boot(evs, "win20")
        side = "bull" if ("bull" in name or "breakout" in name or "long" in name
                          or any(name.startswith(str(c)) for c in BULL_CODES)) else "bear"
        if not name.startswith(("no-pattern", "drift")):
            row["vs_no_pattern_r20"] = _boot_diff(evs, no_pat[side], "r20")
            row["vs_drift_r20"] = _boot_diff(evs, drift[side], "r20")
        out["breaks"][name] = row
    for side, codes in (("bull", BULL_CODES), ("bear", {20, 21, 23})):
        evs = [e for e in breaks if e["code"] in codes]
        for flag in (True, False):
            sub = [e for e in evs if e["aligned"] == flag]
            label = f"{side} patterns, {'aligned' if flag else 'not aligned'} with Larsson state"
            out["by_state"][label] = {"r20": _boot(sub, "r20"), "win20": _boot(sub, "win20")}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    path = RUNS_DIR / args.out
    if path.exists():
        ap.error("results are never overwritten")
    syms = list(PRIMARY) + universe("secondary")
    res = summarise(*run(syms))
    path.mkdir(parents=True)
    (path / "summary.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
