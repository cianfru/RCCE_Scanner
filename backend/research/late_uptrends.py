"""
Late broad uptrends: how long until the market rolls over, do the Cooling arrows come before coins leave their
uptrend, and how did longs do late in a broad uptrend with greed and the crowd long?
(docs/reviews/late-uptrends-study.md, declared 29 October 2026, before running). Context, not a signal unless the
declared bar is met.

Run from backend/ (no network):

  node research/export_page_rows.mjs MH.json WALLETS.json ROWS.json   (the page's own daily inputs)
  python -m research.late_uptrends --rows ROWS.json --live LIVE.json [--shape] [--out JSON]

LIVE.json: a copy of the server's market_history_live.json (per-coin closes after the seed, for the typical alt).
--shape prints only the counts quoted in the declaration (no outcome).
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from datetime import date, timedelta
from pathlib import Path

from market_history import SEED_PATH, make_alt_ret

ON = 0.55                 # risk-on line (the page's 55%)
OFF_DAYS = 5              # the 5th day in a row below the line ends a run
ROLL = 0.20               # roll-over: 20 points under the run's high so far (the market-breadth study's fade size)
LATE = 60                 # the owner's day 60
GREED = 70                # Fear & Greed at or above: the engine's own line (its Not greedy check fails)
GREED_REPORTED = 80       # the dial's top band, reported only
CROWD = 0.86              # profitable traders' share long at or above: the positioning study's extreme-long line
HOT, COLD, TURN, TURN_DAYS = 75, 25, 10, 21   # Market heat, as frontend/src/utils/marketHeat.js
HORIZONS = (30, 60)
CHANGE_H = (14, 30)
STEPS = tuple(range(5, 61, 5))
MATCH = 0.10              # Part 2's comparison: share within 10 points of the turn day's
AFTER = 30                # ... and not within 30 days after a turn of the same kind
EDGE = 10.0               # points of breadth change beyond the comparison
MIN_TURNS = 8
MIN_RUNS = 8
PAIRED_SHARE = 0.75      # Part 3: late weaker than early in at least 3 of 4 paired runs
DRAWS = 10_000
OOS_FROM = 20756          # 30 October 2026
_EPOCH = date(1970, 1, 1)


def iso(day):
    return None if day is None else (_EPOCH + timedelta(days=day)).isoformat()


def median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def describe(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    q = statistics.quantiles(xs, n=4) if len(xs) >= 2 else [xs[0]] * 3
    return {"n": len(xs), "median": round(statistics.median(xs), 1), "q1": round(q[0], 1), "q3": round(q[2], 1),
            "up": round(sum(x > 0 for x in xs) / len(xs), 2)}


# ---------------------------------------------------------------- data

def load_rows(page: dict) -> list:
    ix = {c: i for i, c in enumerate(page["columns"])}
    return [{c: r[i] for c, i in ix.items()} for r in page["rows"]]


def closes_from_live(live: dict) -> dict:
    return {int(k): v for k, v in (live or {}).get("closes", {}).items()}


# ---------------------------------------------------------------- broad uptrends (risk-on runs)

def runs(rows: list) -> tuple:
    """Point-in-time run state per day and the runs. Per day: {on, run, age, high}. Each run: {start, end (first day
    of the 5-day stretch below the line, None while on), first (began on the data's first day: start unknown),
    days: [day...] while on}. The state turns on at the first day at or above the line and off on the 5th day in a
    row below it; dip days 1-4 stay in the run."""
    state, out = {}, []
    cur, below = None, 0
    for i, r in enumerate(rows):
        d, s = r["day"], r["uptrend"]
        if cur is None:
            if s is not None and s >= ON:
                cur = {"start": d, "end": None, "first": i == 0, "days": [], "high": s}
                below = 0
        else:
            below = below + 1 if s is None or s < ON else 0
            if below >= OFF_DAYS:
                cur["end"] = rows[i - OFF_DAYS + 1]["day"]
                out.append(cur)
                cur = None
                state[d] = {"on": False}
                continue
        if cur is not None:
            if s is not None:
                cur["high"] = max(cur["high"], s)
            cur["days"].append(d)
            state[d] = {"on": True, "run": len(out), "age": d - cur["start"], "high": cur["high"]}
        else:
            state.setdefault(d, {"on": False})
    if cur is not None:
        out.append(cur)
    return state, out


def roll_over(run: dict, share: dict):
    """First day of the run with the share 20 points or more under the run's high so far, or None."""
    high = None
    for d in run["days"]:
        s = share.get(d)
        if s is None:
            continue
        high = s if high is None else max(high, s)
        if high - s >= ROLL - 1e-9:
            return d
    return None


# ---------------------------------------------------------------- Market heat (as the page)

def heat_series(rows: list) -> list:
    out = []
    for r in rows:
        if r["uptrend"] is None:
            continue
        parts = [100 * r["uptrend"], r["fg"], None if r["traders"] is None else 100 * r["traders"]]
        vals = [v for v in parts if v is not None]
        if len(vals) >= 2:
            out.append((r["day"], sum(vals) / len(vals)))
    return out


def heat_turns(series: list) -> list:
    """[(day, kind, from_day, from_heat)], the page's rule (marketHeat.js heatTurns)."""
    out, peak, trough = [], None, None
    for d, h in series:
        if h >= HOT and (peak is None or h > peak[1]):
            peak = (d, h)
        if h <= COLD and (trough is None or h < trough[1]):
            trough = (d, h)
        if peak and d - peak[0] > TURN_DAYS and h < HOT:
            peak = None
        if trough and d - trough[0] > TURN_DAYS and h > COLD:
            trough = None
        if peak and h <= peak[1] - TURN:
            out.append((d, "cooling", peak[0], peak[1]))
            peak = None
        if trough and h >= trough[1] + TURN:
            out.append((d, "lifting", trough[0], trough[1]))
            trough = None
    return out


# ---------------------------------------------------------------- outcomes

class Outcomes:
    def __init__(self, rows: list, alt_ret, last: int):
        self.by = {r["day"]: r for r in rows}
        self.alt, self.last = alt_ret, last

    def share(self, d):
        r = self.by.get(d)
        return None if r is None else r["uptrend"]

    def breadth(self, d, h):
        a, b = self.share(d), self.share(d + h)
        return None if a is None or b is None or d + h > self.last else round(100 * (b - a), 1)

    def alt_change(self, d, h):
        if d + h > self.last:
            return None
        v = self.alt(d, d + h)
        return None if v is None else float(v)

    def alt_low(self, d):
        vals = [self.alt_change(d, k) for k in STEPS]
        return None if any(v is None for v in vals) else min(vals)

    def btc(self, d, h):
        a, b = self.by.get(d), self.by.get(d + h)
        if a is None or b is None or not a["btc"] or not b["btc"]:
            return None
        return round(100 * (b["btc"] / a["btc"] - 1), 1)

    def all(self, d):
        o = {f"alt{h}": self.alt_change(d, h) for h in HORIZONS}
        o.update({f"btc{h}": self.btc(d, h) for h in HORIZONS})
        o.update({f"breadth{h}": self.breadth(d, h) for h in CHANGE_H})
        o["alt_low60"] = self.alt_low(d)
        return o


# ---------------------------------------------------------------- Part 1: how long until it rolls over

def part1(rows, state, rs, out: Outcomes) -> dict:
    share = {r["day"]: r["uptrend"] for r in rows}
    fg = {r["day"]: r["fg"] for r in rows}
    shares = {r["day"]: (r["downtrend"], r["basing"]) for r in rows}
    table = []
    for run in rs:
        days = [d for d in run["days"] if share.get(d) is not None]
        peak = max(days, key=lambda d: (share[d], -d))
        ro = roll_over(run, share)
        fgs = [(d, fg[d]) for d in days if fg.get(d) is not None]
        top_fg = max(fgs, key=lambda x: (x[1], -x[0])) if fgs else None
        greedy = next((d for d, v in fgs if v >= GREED), None)
        after = ro + 30 if ro is not None else None
        row = {
            "start": iso(run["start"]), "end": iso(run["end"]), "counted": not run["first"],
            "length": None if run["end"] is None else run["end"] - run["start"],
            "ongoing_days": None if run["end"] is not None else run["days"][-1] - run["start"] + 1,
            "peak": round(100 * share[peak], 1), "peak_day": iso(peak), "peak_age": peak - run["start"],
            "roll_over": iso(ro), "roll_over_age": None if ro is None else ro - run["start"],
            "share_at_roll_over": None if ro is None else round(100 * share[ro], 1),
            "fg_at_peak": fg.get(peak), "top_fg": top_fg and top_fg[1], "top_fg_age": top_fg and top_fg[0] - run["start"],
            "first_greedy_age": None if greedy is None else greedy - run["start"],
            "from_roll_over": None if ro is None else out.all(ro),
            "from_peak": {f"alt{h}": out.alt_change(peak, h) for h in HORIZONS},
            "where_they_went": None if after is None or after not in shares or after > out.last else {
                "downtrend": [round(100 * shares[peak][0], 1), round(100 * shares[after][0], 1)],
                "basing": [round(100 * shares[peak][1], 1), round(100 * shares[after][1], 1)],
                "uptrend": [round(100 * share[peak], 1), round(100 * share[after], 1)]},
        }
        table.append(row)
    counted = [t for t in table if t["counted"]]
    ro_ages = [t["roll_over_age"] for t in counted if t["roll_over_age"] is not None]
    return {
        "runs": table,
        "summary": {
            "runs": len(counted), "ended": sum(t["end"] is not None for t in counted),
            "peak_age": describe([t["peak_age"] for t in counted]),
            "roll_over_age": describe(ro_ages),
            "rolled_over": len(ro_ages),
            "roll_over_age_bands": {"under 30": sum(a < 30 for a in ro_ages), "30-59": sum(30 <= a < 60 for a in ro_ages),
                                    "60+": sum(a >= 60 for a in ro_ages)},
            "ended_without_roll_over": sum(t["end"] is not None and t["roll_over"] is None for t in counted),
        },
    }


# ---------------------------------------------------------------- Part 2: arrows and breadth

def matched_days(rows, out: Outcomes, turn_day: int, turns_of_kind: list) -> list:
    s0 = out.share(turn_day)
    near = set()
    for t in turns_of_kind:
        near.update(range(t, t + AFTER + 1))
    return [r["day"] for r in rows if r["uptrend"] is not None and abs(r["uptrend"] - s0) <= MATCH + 1e-9
            and r["day"] not in near and out.breadth(r["day"], 30) is not None]


def part2_kind(rows, out: Outcomes, turns: list, kind: str, rs, state, oos: bool = False) -> dict:
    share = {r["day"]: r["uptrend"] for r in rows}
    days = [t[0] for t in turns if t[1] == kind]
    pick = [d for d in days if (d >= OOS_FROM) == oos]
    events = []
    for d in pick:
        st = state.get(d, {})
        ro = None
        if st.get("on"):
            ro = roll_over(rs[st["run"]], share)
        pool = matched_days(rows, out, d, days)
        events.append({"day": iso(d), "share": round(100 * share[d], 1), "in_run": bool(st.get("on")),
                       "run_age": st.get("age"), "rolled_over_before": ro is not None and ro <= d,
                       "roll_over_within_30": ro is not None and d < ro <= d + 30,
                       **out.all(d), "matched_n": len(pool),
                       "matched_median30": median([out.breadth(x, 30) for x in pool]), "_pool": pool, "_day": d})
    full = [e for e in events if e["breadth30"] is not None and e["_pool"]]
    sign = -1 if kind == "cooling" else 1
    excess = [e["breadth30"] - e["matched_median30"] for e in full]
    med = statistics.median([e["breadth30"] for e in full]) if full else None
    perm = None
    if full:
        rng = random.Random(20261029)
        at_or_below = 0
        for _ in range(DRAWS):
            at_or_below += statistics.median([out.breadth(rng.choice(e["_pool"]), 30) for e in full]) <= med
        perm = round(at_or_below / DRAWS, 3)
    halves = None
    if len(full) >= 2:
        k = len(full) // 2
        halves = [round(statistics.median(excess[:k]), 1), round(statistics.median(excess[k:]), 1)]
    med_excess = round(statistics.median(excess), 1) if excess else None
    checks = {
        "turns": len(full), "enough": len(full) >= MIN_TURNS, "median_breadth30": None if med is None else round(med, 1),
        "median_excess": med_excess,
        "edge": None if med_excess is None else sign * med_excess >= EDGE,
        "draws_at_or_below": perm,
        "beyond_random": None if perm is None else (perm <= 0.10 if kind == "cooling" else perm >= 0.90),
        "halves": halves,
        "halves_agree": None if halves is None else all(sign * h > 0 for h in halves),
    }
    checks["verdict"] = "met" if all(checks[k] for k in ("enough", "edge", "beyond_random", "halves_agree")) else "not met"
    for e in events:
        e.pop("_pool"), e.pop("_day")
    return {"events": events, "checks": checks,
            "reported": {"alt30": describe([e["alt30"] for e in full]), "breadth14": describe([e["breadth14"] for e in full]),
                         "rolled_over_before": sum(e["rolled_over_before"] for e in full),
                         "roll_over_within_30": sum(e["roll_over_within_30"] for e in full)}}


# ---------------------------------------------------------------- Part 3: late, greedy, crowded

CELLS = ("early", "early_greedy", "late", "late_greedy")


def cell_of(st, r):
    if not st.get("on") or r["uptrend"] is None or r["uptrend"] < ON:
        return None
    late = st["age"] >= LATE
    greedy = r["fg"] is not None and r["fg"] >= GREED
    return ("late" if late else "early") + ("_greedy" if greedy else "")


def part3(rows, state, rs, out: Outcomes) -> dict:
    cells = {c: [] for c in CELLS}
    for r in rows:
        c = cell_of(state.get(r["day"], {}), r)
        if c:
            cells[c].append(r["day"])
    crowded = {r["day"] for r in rows if r["traders"] is not None and r["traders"] >= CROWD}
    pooled = {}
    for c, ds in cells.items():
        pooled[c] = {"days": len(ds), "crowded_days": sum(d in crowded for d in ds),
                     **{k: describe([out.all(d)[k] for d in ds]) for k in ("alt30", "alt60", "alt_low60", "breadth30", "btc30")}}
    cases = []
    for i, run in enumerate(rs):
        if run["first"]:
            continue
        row = {"start": iso(run["start"]), "end": iso(run["end"])}
        for c in CELLS:
            d = next((x for x in cells[c] if state[x].get("run") == i), None)
            row[c] = None if d is None else {"day": iso(d), "age": d - run["start"], "fg": out.by[d]["fg"],
                                             "share": round(100 * out.share(d), 1), "crowded": d in crowded, **out.all(d)}
        cr = next((x for x in cells["late_greedy"] if state[x].get("run") == i and x in crowded), None)
        row["late_greedy_crowded"] = None if cr is None else {"day": iso(cr), "age": cr - run["start"], **out.all(cr)}
        cases.append(row)
    with_late_greedy = [c for c in cases if c["late_greedy"]]
    paired = [c for c in with_late_greedy if c["early_greedy"] and c["late_greedy"]["alt60"] is not None
              and c["early_greedy"]["alt60"] is not None]
    gaps = [c["late_greedy"]["alt60"] - c["early_greedy"]["alt60"] for c in paired]
    weaker = sum(g < 0 for g in gaps)
    enough = len(paired) >= MIN_RUNS
    met = enough and weaker >= PAIRED_SHARE * len(paired) and statistics.median(gaps) <= -EDGE
    return {
        "pooled_days": pooled, "cases": cases,
        "runs_reaching_late": sum(any(c[k] for k in ("late", "late_greedy")) for c in cases),
        "runs_with_late_greedy": len(with_late_greedy),
        "paired": {"runs": len(paired), "late_weaker_alt60": weaker, "median_gap_alt60": median(gaps)},
        "verdict": "met" if met else ("not met" if enough else "too few to read (a case list: fewer than 8 paired runs)"),
    }


# ---------------------------------------------------------------- the study

def build(page: dict, live: dict, seed: dict | None = None):
    rows = load_rows(page)
    seed = seed or json.loads(Path(SEED_PATH).read_text())
    alt = make_alt_ret(seed.get("alt_paths"), closes_from_live(live))
    last = rows[-1]["day"]
    return rows, Outcomes(rows, alt, last)


def shape(page: dict, live: dict, seed: dict | None = None) -> dict:
    """Counts only, for the declaration: no outcome is read."""
    rows, out = build(page, live, seed)
    state, rs = runs(rows)
    series = heat_series(rows)
    turns = heat_turns(series)
    share = {r["day"]: r["uptrend"] for r in rows}
    counted = [r for r in rs if not r["first"]]
    reached = [r for r in counted if r["days"] and r["days"][-1] - r["start"] >= LATE]
    lg = {state[r["day"]]["run"] for r in rows if cell_of(state.get(r["day"], {}), r) == "late_greedy"}
    eg = {state[r["day"]]["run"] for r in rows if cell_of(state.get(r["day"], {}), r) == "early_greedy"}
    crowd_days = [r["day"] for r in rows if r["traders"] is not None]
    return {
        "days": [iso(rows[0]["day"]), iso(out.last), len(rows)],
        "runs": {"all": len(rs), "counted": len(counted), "ongoing": sum(r["end"] is None for r in rs),
                 "starts": [iso(r["start"]) for r in rs], "reached_day_60": len(reached),
                 "with_late_greedy_day": len(lg), "with_early_greedy_day": len(eg),
                 "with_a_roll_over": sum(roll_over(r, share) is not None for r in counted)},
        "turns": {"cooling": sum(t[1] == "cooling" for t in turns), "lifting": sum(t[1] == "lifting" for t in turns),
                  "cooling_with_30_days": sum(t[1] == "cooling" and t[0] + 30 <= out.last for t in turns),
                  "lifting_with_30_days": sum(t[1] == "lifting" and t[0] + 30 <= out.last for t in turns)},
        "traders": [iso(crowd_days[0]), iso(crowd_days[-1]), len(crowd_days)] if crowd_days else None,
    }


def run_study(page: dict, live: dict, seed: dict | None = None) -> dict:
    rows, out = build(page, live, seed)
    state, rs = runs(rows)
    series = heat_series(rows)
    turns = heat_turns(series)
    every = [r["day"] for r in rows]
    return {
        "declared": "docs/reviews/late-uptrends-study.md (29 October 2026)",
        "days": [iso(rows[0]["day"]), iso(out.last), len(rows)],
        "turns": [{"day": iso(d), "kind": k, "from": iso(fd), "from_heat": round(fh, 1)} for d, k, fd, fh in turns],
        "part1": part1(rows, state, rs, out),
        "part2": {"cooling": part2_kind(rows, out, turns, "cooling", rs, state),
                  "lifting": part2_kind(rows, out, turns, "lifting", rs, state)},
        "part3": part3(rows, state, rs, out),
        "every_day": {k: describe([out.all(d)[k] for d in every]) for k in ("alt30", "alt60", "alt_low60", "breadth30")},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True, help="the page's daily inputs (research/export_page_rows.mjs)")
    ap.add_argument("--live", required=True, help="a copy of the server's market_history_live.json")
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
