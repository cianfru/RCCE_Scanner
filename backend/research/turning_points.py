"""
Turning points in the market: does the median z-score turn before coins leave (or re-enter) their uptrends, and what
were the signs of a bottom? (docs/reviews/turning-points-study.md, declared 29 October 2026, before running).
Context, not a signal unless a declared bar is met.

Run from backend/ (no network):

  node research/export_page_rows.mjs MH.json WALLETS.json ROWS.json
  python -m research.turning_points --rows ROWS.json --live LIVE.json [--shape] [--out JSON]

Broad uptrends, roll-overs, Market heat's turns and the outcomes come from research/late_uptrends.py.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

from research import late_uptrends as L
from research.late_uptrends import describe, iso, median

Z_TURN = 0.75             # median z this far off the run's high (or the downturn's low) so far: a z-turn
Z_REPORTED = (0.5, 1.0)   # reported, never deciding
LIFT = 0.20               # turn-up: the share 20 points over the downturn's low so far (mirror of the roll-over)
WASHED = 0.15             # washed out: 15% or fewer coins in uptrend (the risk-on cycles study's level)
FEAR = 25                 # Fear & Greed at or below: extreme fear (alternative.me's band)...
FEAR_GATE = 40            # ...the engine's fear gate, reported
LOOKBACK = 30             # ...at some point in the last 30 days
SHORT = 0.30              # profitable traders' share long at or below: the positioning study's extreme-short line
LEAD_SHARE = 0.75         # z first in at least 3 of 4 runs...
LEAD_DAYS = 10            # ...with a median lead of 10 days or more
PRICE_EDGE = 5.0          # points of typical-coin change beyond the comparison
DEEP_EDGE = 10.0          # points over 60 days for the washed-out, fearful days
MIN_N = 8
DRAWS = 10_000
AFTER = 30


# ---------------------------------------------------------------- downturns

def downturns(rows: list, rs: list, state: dict) -> list:
    """The stretches between broad uptrends: from a run's end (the first of its 5 days under 55%) to the next run's
    start (exclusive), or to the last day (ongoing). Each: {start, end (next run's start or None), days (point-in-time
    off days, the 5th day under on), all_days (every day from start)}. The stretch before the first run is left out."""
    out = []
    for i, run in enumerate(rs):
        if run["end"] is None:
            continue
        nxt = rs[i + 1]["start"] if i + 1 < len(rs) else None
        span = [r["day"] for r in rows if r["day"] >= run["end"] and (nxt is None or r["day"] < nxt)]
        out.append({"start": run["end"], "end": nxt, "all_days": span,
                    "days": [d for d in span if not state.get(d, {}).get("on")]})
    return out


def lows_so_far(days: list, val: dict, low: bool = True) -> dict:
    """{day: lowest (or highest) value from the first day to this one}."""
    out, best = {}, None
    for d in days:
        v = val.get(d)
        if v is not None:
            best = v if best is None else (min(best, v) if low else max(best, v))
        out[d] = best
    return out


def first_move(days: list, val: dict, size: float, up: bool):
    """First day whose value is `size` or more above the lowest so far (up) or below the highest so far (down)."""
    best = None
    for d in days:
        v = val.get(d)
        if v is None:
            continue
        best = v if best is None else (min(best, v) if up else max(best, v))
        if (v - best if up else best - v) >= size - 1e-9:
            return d
    return None


# ---------------------------------------------------------------- comparisons

def matched(pool_days: list, out: L.Outcomes, day: int, events: list, key: str, h: int, share_tol: float = 0.10) -> list:
    """Days of the pool with the share within 10 points of `day`'s, an outcome, and not within 30 days after an event."""
    s0 = out.share(day)
    near = set()
    for e in events:
        near.update(range(e, e + AFTER + 1))
    return [d for d in pool_days if out.share(d) is not None and abs(out.share(d) - s0) <= share_tol + 1e-9
            and d not in near and out.all(d)[key] is not None]


def verdict_block(out: L.Outcomes, events: list, pools: list, key: str, edge: float, sign: int) -> dict:
    """Median excess of the events' outcome over each one's comparison median, random draws (one comparison day per
    event), halves by date. sign -1: the events should be lower; +1: higher."""
    full = [(e, p) for e, p in zip(events, pools) if out.all(e)[key] is not None and p]
    if not full:
        return {"n": 0, "verdict": "not met"}
    vals = [out.all(e)[key] for e, _ in full]
    meds = [statistics.median([out.all(d)[key] for d in p]) for _, p in full]
    excess = [v - m for v, m in zip(vals, meds)]
    obs = statistics.median(vals)
    rng = random.Random(20261029)
    at_or_below = sum(statistics.median([out.all(rng.choice(p))[key] for _, p in full]) <= obs for _ in range(DRAWS)) / DRAWS
    k = len(full) // 2
    halves = [round(statistics.median(excess[:k]), 1), round(statistics.median(excess[k:]), 1)] if len(full) >= 2 else None
    med_ex = round(statistics.median(excess), 1)
    checks = {"n": len(full), "enough": len(full) >= MIN_N, "median": round(obs, 1), "median_excess": med_ex,
              "beyond_others_by": f"{sum(sign * x > 0 for x in excess)} of {len(excess)}",
              "edge": sign * med_ex >= edge, "draws_at_or_below": round(at_or_below, 3),
              "beyond_random": at_or_below <= 0.10 if sign < 0 else at_or_below >= 0.90,
              "halves": halves, "halves_agree": halves is not None and all(sign * h > 0 for h in halves)}
    checks["verdict"] = "met" if all(checks[c] for c in ("enough", "edge", "beyond_random", "halves_agree")) else "not met"
    return checks


def lead_block(pairs: list) -> dict:
    """pairs: [(z day, other day)]: z first (strictly earlier) share and the median lead in days."""
    both = [(z, o) for z, o in pairs if z is not None and o is not None]
    leads = [o - z for z, o in both]
    first = sum(x > 0 for x in leads)
    out = {"runs": len(both), "z_first": f"{first} of {len(both)}", "same_day": sum(x == 0 for x in leads),
           "median_lead": median(leads), "leads": leads}
    out["verdict"] = ("met" if len(both) >= MIN_N and first >= LEAD_SHARE * len(both) and statistics.median(leads) >= LEAD_DAYS
                      else "not met")
    return out


# ---------------------------------------------------------------- the study

def build(page: dict, live: dict, seed: dict | None = None):
    rows, out = L.build(page, live, seed)
    state, rs = L.runs(rows)
    turns = L.heat_turns(L.heat_series(rows))
    return rows, out, state, rs, turns


def z_of(rows):
    return {r["day"]: r["median_z"] for r in rows}


def part_a(rows, out, state, rs, turns, size=Z_TURN) -> dict:
    """Tops: the median z turning down inside broad uptrends."""
    z, share = z_of(rows), {r["day"]: r["uptrend"] for r in rows}
    table, events = [], []
    for run in rs:
        if run["first"]:
            continue
        zt = first_move(run["days"], z, size, up=False)
        ro = L.roll_over(run, share)
        cool = next((d for d, k, _, _ in turns if k == "cooling" and run["start"] <= d <= run["days"][-1]), None)
        if zt is not None:
            events.append(zt)
        table.append({"start": iso(run["start"]), "end": iso(run["end"]), "z_turn": iso(zt),
                      "z_turn_age": None if zt is None else zt - run["start"],
                      "share_at_z_turn": None if zt is None else round(100 * share[zt], 1),
                      "roll_over": iso(ro), "lead_over_roll_over": None if zt is None or ro is None else ro - zt,
                      "first_cooling": iso(cool), "lead_over_cooling": None if zt is None or cool is None else cool - zt,
                      "lead_over_end": None if zt is None or run["end"] is None else run["end"] - zt,
                      "outcomes": None if zt is None else out.all(zt),
                      "roll_over_outcomes": None if ro is None else out.all(ro)})
    on_days = [r["day"] for r in rows if state.get(r["day"], {}).get("on")]
    pools30 = [matched(on_days, out, e, events, "alt30", 30) for e in events]
    pools_b = [matched(on_days, out, e, events, "breadth30", 30) for e in events]
    pairs = [(next((e for e in events if run["start"] <= e <= run["days"][-1]), None), L.roll_over(run, share))
             for run in rs if not run["first"]]
    return {"size": size, "runs": table,
            "lead_over_roll_over": lead_block(pairs),
            "typical_coin_30": verdict_block(out, events, pools30, "alt30", PRICE_EDGE, -1),
            "share_30": verdict_block(out, events, pools_b, "breadth30", L.EDGE, -1),
            "after_z_turn": {k: describe([out.all(e)[k] for e in events]) for k in ("alt30", "alt60", "alt_low60", "breadth30")}}


def part_b(rows, out, state, rs, turns, size=Z_TURN) -> dict:
    """Bottoms: downturns, their low, the median z turning up, and the washed-out, fearful days."""
    z, share = z_of(rows), {r["day"]: r["uptrend"] for r in rows}
    fg = {r["day"]: r["fg"] for r in rows}
    traders = {r["day"]: r["traders"] for r in rows}
    by = {r["day"]: r for r in rows}

    def fear_lately(d, line=FEAR):
        v = [fg.get(d - k) for k in range(LOOKBACK) if fg.get(d - k) is not None]
        return bool(v) and min(v) <= line

    def below_band(d):
        r = by.get(d)
        return bool(r and r["btc"] and r["band_lo"] and r["btc"] < r["band_lo"])

    dts = downturns(rows, rs, state)
    table, z_events, deep_events = [], [], []
    for dt in dts:
        span = dt["all_days"]
        if not span:
            continue
        low = min((d for d in span if share.get(d) is not None), key=lambda d: (share[d], d))
        lift = first_move(span, share, L.ROLL, up=True)
        zt = first_move(span, z, size, up=True)
        zlow = min((d for d in span if z.get(d) is not None), key=lambda d: (z[d], d))
        lifting = next((d for d, k, _, _ in turns if k == "lifting" and span[0] <= d <= span[-1]), None)
        deep = next((d for d in dt["days"] if share.get(d) is not None and share[d] <= WASHED + 1e-9 and fear_lately(d)), None)
        fgs = [(d, fg[d]) for d in span if fg.get(d) is not None]
        fg_low = min(fgs, key=lambda x: (x[1], x[0])) if fgs else None
        if zt is not None:
            z_events.append(zt)
        if deep is not None:
            deep_events.append(deep)
        tr = [(d, traders[d]) for d in span if traders.get(d) is not None]
        table.append({
            "start": iso(dt["start"]), "end": iso(dt["end"]), "length": None if dt["end"] is None else dt["end"] - dt["start"],
            "low": round(100 * share[low], 1), "low_day": iso(low), "low_age": low - dt["start"],
            "turn_up": iso(lift), "turn_up_age": None if lift is None else lift - dt["start"],
            "z_low_day": iso(zlow), "z_turn_up": iso(zt), "z_turn_up_age": None if zt is None else zt - dt["start"],
            "lead_over_turn_up": None if zt is None or lift is None else lift - zt,
            "lead_over_next_run": None if zt is None or dt["end"] is None else dt["end"] - zt,
            "first_lifting": iso(lifting),
            "fg_low": fg_low and fg_low[1], "fg_low_day": iso(fg_low and fg_low[0]),
            "fg_low_age": None if not fg_low else fg_low[0] - dt["start"],
            "traders_low": None if not tr else round(100 * min(t for _, t in tr), 1),
            "washed_out_with_fear": iso(deep), "washed_out_with_fear_age": None if deep is None else deep - dt["start"],
            "btc_below_band_then": None if deep is None else below_band(deep),
            "traders_short_then": None if deep is None or traders.get(deep) is None else traders[deep] <= SHORT,
            "from_low": out.all(low), "from_turn_up": None if lift is None else out.all(lift),
            "from_z_turn_up": None if zt is None else out.all(zt), "from_washed_out": None if deep is None else out.all(deep),
        })
    off_days = [d for dt in dts for d in dt["days"]]
    pools_z = [matched(off_days, out, e, z_events, "alt30", 30) for e in z_events]
    pools_zb = [matched(off_days, out, e, z_events, "breadth30", 30) for e in z_events]
    every_off = [d for d in off_days if out.all(d)["alt60"] is not None]
    pairs = []
    for dt in dts:
        span = dt["all_days"]
        pairs.append((next((e for e in z_events if span and span[0] <= e <= span[-1]), None),
                      first_move(span, share, L.ROLL, up=True)))
    return {
        "size": size, "downturns": table,
        "lead_over_turn_up": lead_block(pairs),
        "typical_coin_30": verdict_block(out, z_events, pools_z, "alt30", PRICE_EDGE, +1),
        "share_30": verdict_block(out, z_events, pools_zb, "breadth30", L.EDGE, +1),
        "washed_out_fear_60": verdict_block(out, deep_events, [every_off] * len(deep_events), "alt60", DEEP_EDGE, +1),
        "every_downturn_day": {k: describe([out.all(d)[k] for d in off_days]) for k in ("alt30", "alt60", "alt_low60", "breadth30")},
        "exploratory": exploratory(rows, out, dts, fear_lately, traders),
    }


def exploratory(rows, out, dts, fear_lately, traders) -> list:
    """Reported, never deciding (the owner: not strict): downturn days by age and extreme fear in the last 30 days."""
    edges = [(0, 30), (30, 60), (60, 90), (90, 150), (150, 10_000)]
    cells = {}
    for i, dt in enumerate(dts):
        for d in dt["days"]:
            age = d - dt["start"]
            b = next(f"{lo}-{hi - 1}" if hi < 10_000 else f"{lo}+" for lo, hi in edges if lo <= age < hi)
            cells.setdefault((b, fear_lately(d)), []).append((d, i))
    rowsout = []
    for lo, hi in edges:
        b = f"{lo}-{hi - 1}" if hi < 10_000 else f"{lo}+"
        for fear in (False, True):
            ds = cells.get((b, fear), [])
            rowsout.append({"age": b, "fear_lately": fear, "days": len(ds), "downturns": len({i for _, i in ds}),
                            "traders_short_days": sum(traders.get(d) is not None and traders[d] <= SHORT for d, _ in ds),
                            **{k: describe([out.all(d)[k] for d, _ in ds]) for k in ("alt30", "alt60", "breadth30")}})
    return rowsout


def shape(page: dict, live: dict, seed: dict | None = None) -> dict:
    """Counts only, for the declaration: no outcome is read."""
    rows, out, state, rs, turns = build(page, live, seed)
    z, share = z_of(rows), {r["day"]: r["uptrend"] for r in rows}
    fg = {r["day"]: r["fg"] for r in rows}
    counted = [r for r in rs if not r["first"]]
    zt_down = {s: sum(first_move(r["days"], z, s, up=False) is not None for r in counted) for s in (Z_TURN, *Z_REPORTED)}
    both_down = sum(first_move(r["days"], z, Z_TURN, up=False) is not None and L.roll_over(r, share) is not None for r in counted)
    dts = downturns(rows, rs, state)
    lifts = sum(first_move(d["all_days"], share, L.ROLL, up=True) is not None for d in dts)
    zt_up = {s: sum(first_move(d["all_days"], z, s, up=True) is not None for d in dts) for s in (Z_TURN, *Z_REPORTED)}
    both_up = sum(first_move(d["all_days"], z, Z_TURN, up=True) is not None
                  and first_move(d["all_days"], share, L.ROLL, up=True) is not None for d in dts)

    def fear_lately(d):
        v = [fg.get(d - k) for k in range(LOOKBACK) if fg.get(d - k) is not None]
        return bool(v) and min(v) <= FEAR
    washed = sum(any(share.get(d) is not None and share[d] <= WASHED for d in dt["days"]) for dt in dts)
    deep = sum(any(share.get(d) is not None and share[d] <= WASHED and fear_lately(d) for d in dt["days"]) for dt in dts)
    return {
        "runs_counted": len(counted), "z_turn_down_runs": zt_down, "runs_with_z_turn_and_roll_over": both_down,
        "downturns": len(dts), "ongoing": sum(d["end"] is None for d in dts),
        "starts": [iso(d["start"]) for d in dts], "lengths": [None if d["end"] is None else d["end"] - d["start"] for d in dts],
        "with_turn_up": lifts, "z_turn_up_downturns": zt_up, "with_z_turn_up_and_turn_up": both_up,
        "washed_out": washed, "washed_out_with_extreme_fear": deep,
        "median_z_days": sum(r["median_z"] is not None for r in rows),
    }


def run_study(page: dict, live: dict, seed: dict | None = None) -> dict:
    rows, out, state, rs, turns = build(page, live, seed)
    return {
        "declared": "docs/reviews/turning-points-study.md (29 October 2026)",
        "days": [iso(rows[0]["day"]), iso(out.last), len(rows)],
        "a_tops": part_a(rows, out, state, rs, turns),
        "b_bottoms": part_b(rows, out, state, rs, turns),
        "reported_sizes": {str(s): {"a": {k: v for k, v in part_a(rows, out, state, rs, turns, s).items() if k != "runs"},
                                    "b": {k: v for k, v in part_b(rows, out, state, rs, turns, s).items()
                                          if k in ("lead_over_turn_up", "typical_coin_30", "share_30")}}
                           for s in Z_REPORTED},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--live", required=True)
    ap.add_argument("--shape", action="store_true", help="counts only, no outcome")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    page, live = json.loads(Path(a.rows).read_text()), json.loads(Path(a.live).read_text())
    res = shape(page, live) if a.shape else run_study(page, live)
    text = json.dumps(res, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
