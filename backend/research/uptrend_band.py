"""
The Uptrend share against its own weekly band (docs/reviews/uptrend-band-study.md, declared 6 November 2026, before
running). BTC's weekly bull market support band, built the same way on the share of coins in uptrend: does the share
crossing its band say more than the share itself, and do the crossings come before the 55% rule's broad uptrend
starts and ends? Context, not a signal unless a declared bar is met.

Run from backend/:

  python -m research.uptrend_band fetch --out CLOSES.json            (public Binance daily candles of the seed's
                                                                      151 pairs, one request a second)
  python -m research.uptrend_band check --snapshot MH.json --closes CLOSES.json
                                                                     (the typical alt after the seed, rebuilt from
                                                                      CLOSES, against the snapshot's own numbers)
  python -m research.uptrend_band shape --snapshot MH.json           (counts only, no outcome)
  python -m research.uptrend_band power --n-under N --n-over N       (the bar on simulated data, no real outcome)
  python -m research.uptrend_band run --snapshot MH.json --closes CLOSES.json [--out JSON]

MH.json: a saved /api/market-history response. The share is Uptrend + Overheated, as the page reads it.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from backtest.risk_on_cycles import SUNDAY, expand_weekly, weekly_rows
from market_history import DAY_MS, KLINES_URL, SEED_PATH, day_closes, make_alt_ret
from research import late_uptrends as L
from research.late_uptrends import describe, iso

GAP = 5                   # days on one side of the band with gaps of up to 5 days form one stretch (BTC's band breaks)
LOOKBACK = GAP + 1        # a crossing needs the band on the 6 days before it (else its start is unknown)
COOLDOWN = 30             # Part A: a crossing is an event only with no crossing of its kind in the 30 days before
HORIZONS = (30, 60)
DECIDING = 60             # Part A decides on 60 days; 30 days is reported
MATCH = 0.10              # comparison days: the share within 10 points of the event day's...
AFTER = 30                # ...not a crossing of the same kind, nor within 30 days after one
MIN_N = 8                 # events (Part A) or runs with both (Part B)
SAME_WAY = 0.75           # at least 3 of 4 the declared way
EDGE = {30: 5.0, 60: 10.0}            # median excess, points of price change
SHARE_EDGE = 10.0                     # the share's own 30-day change, points (reported)
DRAWS = 10_000
DRAW_P = 0.05             # the events' median beyond all but 5% of the random draws' medians
RNG_SEED = 20261106
LEAD_DAYS = 10            # Part B: median lead of 10 days or more
WINDOW = 60               # Part B: a crossing up to 60 days after the 55% rule's day; false-alarm window
CONFIRM = L.OFF_DAYS - 1  # the 55% rule knows a run's end 4 days after its end day
MIN_BARS = 200            # a coin counts on a day once it has 200 daily candles (market_history.day_closes)
MIN_ALTS = 20
CHECK_TOL = {"alt_recent": 0.5, "episodes": 1.0, "junction_median": 0.5, "junction_max": 1.5}
OOS_FROM = 20764          # 7 November 2026: new crossings from here count out of sample
OOS_A_FROM = 20744        # 18 October 2026: Part A's out-of-sample crossings start here; that crossing had no 60 days
                          # in sample and counts as the first new case (owner, 6 November 2026, after the result)
KINDS = ("under", "over")
SIGN = {"under": -1, "over": +1}


# ---------------------------------------------------------------- data

def load_rows(snap: dict) -> list:
    """Daily rows from a saved /api/market-history response: day, n, uptrend (Uptrend + Overheated, as the page and
    research/export_page_rows.mjs read it) and BTC's close."""
    ix = {c: i for i, c in enumerate(snap["columns"])}
    rows = []
    for r in snap["days"]:
        up = r[ix["uptrend"]]
        rows.append({"day": r[ix["day"]], "n": r[ix["n"]],
                     "uptrend": None if up is None else up + (r[ix["overheated"]] or 0.0), "btc": r[ix["btc"]]})
    return rows


def closes_by_day(fetched: dict, days, last_day: int, min_bars: int = MIN_BARS) -> dict:
    """{day: {pair: close}} from fetched candles ({pair: [[day, close], ...]}), closed days up to last_day only, a
    coin counted once it has min_bars candles: market_history.day_closes, the server's own rule."""
    days = [d for d in days if d <= last_day]
    out = {d: {} for d in days}
    for pair, kl in fetched["pairs"].items():
        rows = [[day * DAY_MS, 0, 0, 0, c] for day, c in kl if day <= last_day]
        for d, c in day_closes(rows, days, min_bars).items():
            out[d][pair] = c
    return {d: v for d, v in out.items() if v}


def alt_change(closes: dict, t: int, e: int):
    """The typical alt from day t's close to day e's: the median simple return of 20+ coins other than BTC with both
    closes, in % (1 dp), as market_history.make_alt_ret does after the seed."""
    a0, a1 = closes.get(t) or {}, closes.get(e) or {}
    rs = [a1[p] / a0[p] - 1 for p in a0 if p != "BTCUSDT" and p in a1 and a0[p] > 0]
    return round(100 * statistics.median(rs), 1) + 0.0 if len(rs) >= MIN_ALTS else None


# ---------------------------------------------------------------- the share's band and its crossings

def share_band(rows: list) -> dict:
    """{day: (lower, upper)}: the share's weekly band by the code behind BTC's band in the app
    (market_history.btc_band): the share on Sundays, the 20-week SMA and 21-week EMA of completed weeks, a Sunday's
    band used from the next day; lower edge the smaller of the two. None until 21 Sundays exist."""
    share = {r["day"]: r["uptrend"] for r in rows if r["uptrend"] is not None}
    return expand_weekly(weekly_rows(share, SUNDAY), share)


def side(s: float, b: tuple) -> str:
    """under: below the lower edge; over: above the upper edge; inside otherwise (an edge itself is inside)."""
    return "under" if s < b[0] else "over" if s > b[1] else "inside"


def stretches(days, flagged, gap: int = GAP) -> list:
    """[[first, last]] of the flagged days, gaps of up to `gap` days joined (risk_on_cycles.band_breaks)."""
    out = []
    for d in sorted(days):
        if d in flagged:
            if out and d - out[-1][1] <= gap + 1:
                out[-1][1] = d
            else:
                out.append([d, d])
    return out


def crossings(rows: list, band: dict) -> dict:
    """{'under': [...], 'over': [...]}, each stretch {first, last, known}. A stretch's first day is a crossing when
    the band existed on the 6 days before it (known); otherwise its start is unknown and it is no crossing."""
    share = {r["day"]: r["uptrend"] for r in rows}
    days = sorted(d for d in band if share.get(d) is not None)
    if not days:
        return {k: [] for k in KINDS}
    first_band = days[0]
    out = {}
    for kind in KINDS:
        flagged = {d for d in days if side(share[d], band[d]) == kind}
        out[kind] = [{"first": f, "last": la, "known": f - LOOKBACK >= first_band}
                     for f, la in stretches(days, flagged)]
    return out


def crossing_days(cx: dict, kind: str) -> list:
    return [s["first"] for s in cx[kind] if s["known"]]


def counted(days: list, cooldown: int = COOLDOWN) -> list:
    """Crossings with no crossing of the same kind (counted or not) in the `cooldown` days before."""
    days = sorted(days)
    return [d for i, d in enumerate(days) if i == 0 or d - days[i - 1] > cooldown]


# ---------------------------------------------------------------- outcomes

class Values:
    """Outcomes from a day's close, cached: alt30/alt60 (typical alt, %), btc30/btc60 (%), share30 (points)."""

    def __init__(self, rows: list, alt_ret):
        self.rows = rows
        self.last = rows[-1]["day"]
        self.out = L.Outcomes(rows, alt_ret, self.last)
        self.share = {r["day"]: r["uptrend"] for r in rows}
        self._c = {}

    def get(self, d: int, key: str):
        k = (d, key)
        if k not in self._c:
            h = int(key[-2:])
            if key.startswith("alt"):
                v = self.out.alt_change(d, h)
            elif key.startswith("btc"):
                v = None if d + h > self.last else self.out.btc(d, h)
            else:
                v = self.out.breadth(d, h)
            self._c[k] = v
        return self._c[k]

    def span_btc(self, a: int, b: int):
        """BTC from day a's close to day b's, in %."""
        x, y = self.out.by.get(a), self.out.by.get(b)
        if x is None or y is None or not x["btc"] or not y["btc"]:
            return None
        return round(100 * (y["btc"] / x["btc"] - 1), 1)


# ---------------------------------------------------------------- Part A: prices after a crossing

def comparison_days(band_days: list, vals: Values, event: int, kind_crossings: list, key: str) -> list:
    """Days with a band, the share within 10 points of the event day's, the outcome known, not a crossing of the same
    kind nor within 30 days after one."""
    s0 = vals.share[event]
    near = set()
    for c in kind_crossings:
        near.update(range(c, c + AFTER + 1))
    return [d for d in band_days if vals.share.get(d) is not None and abs(vals.share[d] - s0) <= MATCH + 1e-9
            and d not in near and vals.get(d, key) is not None]


def price_block(events: list, pools: list, vals: Values, key: str, sign: int, edge: float) -> dict:
    """The declared checks for one kind and one outcome. sign -1: the events should be lower than their comparison
    days; +1: higher. Decided on unrounded values."""
    full = [(e, p) for e, p in zip(events, pools) if vals.get(e, key) is not None and p]
    n = len(full)
    if not n:
        return {"events": 0, "enough": False, "verdict": "not met"}
    ev = [vals.get(e, key) for e, _ in full]
    pv = [[vals.get(d, key) for d in p] for _, p in full]
    meds = [statistics.median(v) for v in pv]
    excess = [v - m for v, m in zip(ev, meds)]
    obs = statistics.median(ev)
    rng = random.Random(RNG_SEED)
    beyond = 0
    for _ in range(DRAWS):
        m = statistics.median([rng.choice(v) for v in pv])
        beyond += (m <= obs) if sign < 0 else (m >= obs)
    p = beyond / DRAWS
    k = n // 2
    halves = [statistics.median(excess[:k]), statistics.median(excess[k:])] if n >= 2 else None
    same = sum(sign * x > 0 for x in excess)
    med_ex = statistics.median(excess)
    checks = {
        "events": n, "enough": n >= MIN_N,
        "same_way": same, "consistent": same >= SAME_WAY * n,
        "median": round(obs, 1), "comparison_median": round(statistics.median(meds), 1),
        "median_excess": round(med_ex, 1), "edge": sign * med_ex >= edge,
        "draws_beyond": round(p, 4), "beyond_random": p <= DRAW_P,
        "halves": None if halves is None else [round(h, 1) for h in halves],
        "halves_agree": halves is not None and all(sign * h > 0 for h in halves),
        "excess": [round(x, 1) for x in excess],
    }
    checks["verdict"] = "met" if all(checks[c] for c in ("enough", "consistent", "edge", "beyond_random",
                                                         "halves_agree")) else "not met"
    return checks


def part_a(rows: list, band: dict, cx: dict, vals: Values, state: dict, oos: bool = False) -> dict:
    band_days = sorted(d for d in band if vals.share.get(d) is not None)
    res = {}
    for kind in KINDS:
        allx = crossing_days(cx, kind)
        events = [d for d in counted(allx) if (d >= OOS_A_FROM) == oos]
        sign = SIGN[kind]
        blocks = {}
        for key in ("alt60", "btc60", "alt30", "btc30", "share30"):
            pools = [comparison_days(band_days, vals, e, allx, key) for e in events]
            edge = SHARE_EDGE if key == "share30" else EDGE[int(key[-2:])]
            blocks[key] = price_block(events, pools, vals, key, sign, edge)
        table = []
        for e in events:
            st = state.get(e, {})
            row = {"day": iso(e), "share": round(100 * vals.share[e], 1),
                   "band": [round(100 * band[e][0], 1), round(100 * band[e][1], 1)],
                   "in_broad_uptrend": bool(st.get("on")), "run_age": st.get("age")}
            for key in ("btc30", "alt30", "btc60", "alt60", "share30"):
                pool = comparison_days(band_days, vals, e, allx, key)
                v = vals.get(e, key)
                row[key] = v
                row[key + "_comparison"] = (round(statistics.median([vals.get(d, key) for d in pool]), 1)
                                            if pool and v is not None else None)
            table.append(row)
        res[kind] = {"crossings": len(allx), "events": len(events), "table": table,
                     "deciding": {k: blocks[k] for k in ("alt60", "btc60")},
                     "reported": {k: blocks[k] for k in ("alt30", "btc30", "share30")},
                     "uncounted": [iso(d) for d in allx if d not in set(counted(allx))]}
    return res


# ---------------------------------------------------------------- Part B: against the 55% rule

def containing(strs: list, day: int):
    return next((s for s in strs if s["first"] <= day <= s["last"]), None)


def end_case(run: dict, unders: list, last: int) -> dict:
    """How the share's band stood at a broad uptrend's end E (the first of its 5 days under 55%)."""
    S, E = run["start"], run["end"]
    u = containing(unders, E)
    if u is not None:
        if not u["known"]:
            return {"case": "start unknown"}
        if u["first"] >= S:
            lead = E - u["first"]
            return {"case": "band first" if lead > 0 else "same day", "cross": u["first"], "lead": lead}
        return {"case": "under since before the run", "cross": u["first"]}
    nxt = next((s for s in unders if s["known"] and E < s["first"] <= E + WINDOW), None)
    if nxt is not None:
        return {"case": "band later", "cross": nxt["first"], "lead": E - nxt["first"]}
    return {"case": "none within 60 days" if E + WINDOW <= last else "not known yet"}


def start_case(run: dict, prev_end, overs: list, last: int) -> dict:
    """How the share's band stood at a broad uptrend's start S, against the previous run's end."""
    S = run["start"]
    o = containing(overs, S)
    if o is not None:
        if not o["known"]:
            return {"case": "start unknown"}
        if prev_end is None or o["first"] >= prev_end:
            lead = S - o["first"]
            return {"case": "band first" if lead > 0 else "same day", "cross": o["first"], "lead": lead}
        return {"case": "over since before the dip", "cross": o["first"]}
    nxt = next((s for s in overs if s["known"] and S < s["first"] <= S + WINDOW), None)
    if nxt is not None:
        return {"case": "band later", "cross": nxt["first"], "lead": S - nxt["first"]}
    return {"case": "none within 60 days" if S + WINDOW <= last else "not known yet"}


def lead_verdict(cases: list) -> dict:
    both = [c for c in cases if c["case"] in ("band first", "same day", "band later")]
    leads = [c["lead"] for c in both]
    first = sum(x > 0 for x in leads)
    return {"runs_with_both": len(both), "band_first": first, "enough": len(both) >= MIN_N,
            "mostly_first": bool(both) and first >= SAME_WAY * len(both),
            "median_lead": None if not leads else statistics.median(leads),
            "long_enough": bool(leads) and statistics.median(leads) >= LEAD_DAYS,
            "leads": leads}


def false_alarms(cross: list, state: dict, runs: list, want_on: bool, last: int, ends: bool,
                 since: int | None = None) -> dict:
    """Crossings on days a broad uptrend was under way (ends) or not (starts), point-in-time; followed by the run's
    end (or a run's start) within 60 days. A run is under way on its 1-4 dip days, so a cross under on one of them
    comes after the end day the rule later names (by up to 3 days) and counts as followed by it."""
    rows = []
    for c in cross:
        st = state.get(c, {})
        if bool(st.get("on")) != want_on or (since is not None and c < since):
            continue
        if ends:
            e = runs[st["run"]]["end"]
            hit = e is not None and e <= c + WINDOW
            known = e is not None or c + WINDOW + CONFIRM <= last
        else:
            nxt = next((r["start"] for r in runs if r["start"] >= c), None)
            hit = nxt is not None and nxt <= c + WINDOW
            known = hit or c + WINDOW <= last
        rows.append({"day": iso(c), "followed": hit if known else None})
    k = [r for r in rows if r["followed"] is not None]
    hits = sum(r["followed"] for r in k)
    return {"crossings": len(rows), "known": len(k), "followed": hits,
            "few_false_alarms": bool(k) and hits >= SAME_WAY * len(k), "rows": rows}


def between(vals: Values, band_day: int, rule_day: int) -> dict:
    """BTC from the earlier of the two signals' days to the later one."""
    if band_day == rule_day:
        return {"earlier": "same day", "btc": 0.0}
    a, b = sorted((band_day, rule_day))
    return {"earlier": "band" if band_day < rule_day else "rule", "btc": vals.span_btc(a, b)}


PAIRED = ("band first", "same day", "band later")
PRICE_KEYS = ("btc30", "alt30", "btc60", "alt60")


def part_b(rows: list, band: dict, cx: dict, vals: Values, state: dict, runs: list, since: int | None = None) -> dict:
    """since: count only starts, ends and crossings on or after this day (the out-of-sample run)."""
    last = vals.last
    first_band = min(band)
    unders, overs = cx["under"], cx["over"]
    counted_runs = [(i, r) for i, r in enumerate(runs) if not r["first"] and r["start"] >= first_band + LOOKBACK]
    table, ends, starts = [], [], []
    for i, r in counted_runs:
        prev_end = runs[i - 1]["end"] if i > 0 else None
        sc = start_case(r, prev_end, overs, last)
        ec = end_case(r, unders, last) if r["end"] is not None else {"case": "run under way"}
        if since is None or r["start"] >= since:
            starts.append(sc)
        if r["end"] is not None and (since is None or r["end"] >= since):
            ends.append(ec)
        row = {"start": iso(r["start"]), "end": iso(r["end"]),
               "length": None if r["end"] is None else r["end"] - r["start"],
               "start_case": sc["case"], "start_cross": iso(sc.get("cross")), "start_lead": sc.get("lead"),
               "end_case": ec["case"], "end_cross": iso(ec.get("cross")), "end_lead": ec.get("lead"),
               "end_lead_vs_known": None if ec.get("lead") is None else ec["lead"] + CONFIRM}
        # Reported: prices from each signal's day. Ends: the band's cross under against the day the 55% rule knows
        # the end (E + 4). Starts: the band's cross over against the start day (known on the day).
        if ec["case"] in PAIRED:
            known = r["end"] + CONFIRM
            row["end_prices"] = {"between": between(vals, ec["cross"], known),
                                 "from_band": {k: vals.get(ec["cross"], k) for k in PRICE_KEYS},
                                 "from_rule": {k: vals.get(known, k) for k in PRICE_KEYS}}
        if sc["case"] in PAIRED:
            row["start_prices"] = {"between": between(vals, sc["cross"], r["start"]),
                                   "from_band": {k: vals.get(sc["cross"], k) for k in PRICE_KEYS},
                                   "from_rule": {k: vals.get(r["start"], k) for k in PRICE_KEYS}}
        table.append(row)
    out = {}
    for name, cases, cross, want_on, is_end in (("ends", ends, crossing_days(cx, "under"), True, True),
                                                ("starts", starts, crossing_days(cx, "over"), False, False)):
        lv = lead_verdict(cases)
        fa = false_alarms(cross, state, runs, want_on, last, is_end, since)
        counts = {}
        for c in cases:
            counts[c["case"]] = counts.get(c["case"], 0) + 1
        met = lv["enough"] and lv["mostly_first"] and lv["long_enough"] and fa["few_false_alarms"]
        out[name] = {"cases": counts, **lv, "false_alarms": fa, "verdict": "met" if met else "not met"}
    out["runs"] = table
    return out


# ---------------------------------------------------------------- reported context

def days_by_side(rows: list, band: dict, vals: Values, state: dict) -> list:
    """Every day with a band by its side and whether a broad uptrend was under way: outcomes (days overlap)."""
    groups = {}
    for d in sorted(band):
        s = vals.share.get(d)
        if s is None:
            continue
        g = (side(s, band[d]), bool(state.get(d, {}).get("on")))
        groups.setdefault(g, []).append(d)
    out = []
    for sd in ("over", "inside", "under"):
        for on in (True, False):
            ds = groups.get((sd, on), [])
            out.append({"side": sd, "broad_uptrend": on, "days": len(ds),
                        **{k: describe([vals.get(d, k) for d in ds]) for k in ("btc30", "alt30", "btc60", "alt60")}})
    allds = [d for d in band if vals.share.get(d) is not None]
    out.append({"side": "every day with a band", "broad_uptrend": None, "days": len(allds),
                **{k: describe([vals.get(d, k) for d in allds]) for k in ("btc30", "alt30", "btc60", "alt60")}})
    return out


def today(rows: list, band: dict, cx: dict, state: dict, runs: list) -> dict:
    d = rows[-1]["day"]
    s = rows[-1]["uptrend"]
    b = band.get(d)
    last_run = runs[-1]
    return {"day": iso(d), "share": round(100 * s, 1), "band": None if b is None else [round(100 * x, 1) for x in b],
            "side": None if b is None else side(s, b),
            "latest_under": iso(max(crossing_days(cx, "under"), default=None)),
            "latest_over": iso(max(crossing_days(cx, "over"), default=None)),
            "broad_uptrend_under_way": bool(state.get(d, {}).get("on")),
            "latest_run": {"start": iso(last_run["start"]), "end": iso(last_run["end"])}}


# ---------------------------------------------------------------- the study

def seed_alt_paths(seed: dict | None = None) -> dict:
    seed = seed or json.loads(Path(SEED_PATH).read_text())
    return seed.get("alt_paths")


def build(snap: dict, closes: dict | None, seed: dict | None = None):
    rows = load_rows(snap)
    alt = make_alt_ret(seed_alt_paths(seed), closes or {})
    vals = Values(rows, alt)
    band = share_band(rows)
    cx = crossings(rows, band)
    state, runs = L.runs(rows)
    return rows, vals, band, cx, state, runs


def shape(snap: dict) -> dict:
    """Counts only, for the declaration: no outcome is read."""
    rows = load_rows(snap)
    band = share_band(rows)
    cx = crossings(rows, band)
    state, runs = L.runs(rows)
    last = rows[-1]["day"]
    first_band = min(band)
    out = {"days": [iso(rows[0]["day"]), iso(last), len(rows)], "band_from": iso(first_band)}
    for kind in KINDS:
        allx = crossing_days(cx, kind)
        ev = counted(allx)
        out[kind] = {"stretches": len(cx[kind]), "unknown_start": sum(not s["known"] for s in cx[kind]),
                     "crossings": len(allx), "events": len(ev),
                     "events_with_60_days": sum(d + 60 <= last for d in ev),
                     "events_with_30_days": sum(d + 30 <= last for d in ev),
                     "in_broad_uptrend": sum(bool(state.get(d, {}).get("on")) for d in allx),
                     "outside": sum(not state.get(d, {}).get("on") for d in allx)}
    counted_runs = [r for r in runs if not r["first"] and r["start"] >= first_band + LOOKBACK]
    out["runs"] = {"all": len(runs), "after_band": len(counted_runs),
                   "ended_after_band": sum(r["end"] is not None for r in counted_runs),
                   "starts": [iso(r["start"]) for r in counted_runs]}
    return out


def run_study(snap: dict, closes: dict | None, seed: dict | None = None, oos: bool = False) -> dict:
    rows, vals, band, cx, state, runs = build(snap, closes, seed)
    if oos:
        return {"declared": "docs/reviews/uptrend-band-study.md (6 November 2026)", "out_of_sample_from": iso(OOS_FROM), "part_a_out_of_sample_from": iso(OOS_A_FROM),
                "days": [iso(rows[0]["day"]), iso(vals.last), len(rows)],
                "part_a": part_a(rows, band, cx, vals, state, oos=True),
                "part_b": part_b(rows, band, cx, vals, state, runs, since=OOS_FROM),
                "today": today(rows, band, cx, state, runs)}
    return {
        "declared": "docs/reviews/uptrend-band-study.md (6 November 2026)",
        "days": [iso(rows[0]["day"]), iso(vals.last), len(rows)], "band_from": iso(min(band)),
        "crossings": {k: [{"first": iso(s["first"]), "last": iso(s["last"]), "known": s["known"],
                           "share": round(100 * vals.share[s["first"]], 1),
                           "in_broad_uptrend": bool(state.get(s["first"], {}).get("on")),
                           "event": s["known"] and s["first"] in set(counted(crossing_days(cx, k)))}
                          for s in cx[k]] for k in KINDS},
        "part_a": part_a(rows, band, cx, vals, state),
        "part_b": part_b(rows, band, cx, vals, state, runs),
        "days_by_side": days_by_side(rows, band, vals, state),
        "today": today(rows, band, cx, state, runs),
    }


# ---------------------------------------------------------------- the typical alt after the seed: fetch and check

def fetch(pairs: list, out_path: Path, pause: float = 1.0) -> dict:
    """Daily candles of each pair from Binance's public data API (the server's own source and URL), one request a
    second. Keeps [day, close] per pair; a pair answering 400/404 (not listed) is recorded as missing."""
    res = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "url": KLINES_URL,
           "pairs": {}, "missing": [], "failed": []}
    for p in pairs:
        url = KLINES_URL.format(pair=p)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = json.loads(r.read())
                res["pairs"][p] = [[int(k[0]) // DAY_MS, float(k[4])] for k in data]
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 404):
                    res["missing"].append(p)
                    break
                time.sleep(5 * (attempt + 1))
            except Exception:
                time.sleep(5 * (attempt + 1))
        else:
            res["failed"].append(p)
        time.sleep(pause)
    out_path.write_text(json.dumps(res, separators=(",", ":")))
    return {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in res.items()}


def check(snap: dict, fetched: dict, seed: dict | None = None) -> dict:
    """The rebuilt typical alt against the snapshot's own numbers. No outcome around a crossing is read.
    1. alt_recent: the last 90 days against the last day, 100 * median(close(d) / close(T)) - 100.
    2. Every scored drawer episode starting after the seed's paths (from 2026-01-29): the typical alt at 10, 30 and
       60 days.
    3. The junction: origins 2025-11-28 to 2026-01-28 at 30 and 60 days, the seed's whole-% paths against the rebuild."""
    seed = seed or json.loads(Path(SEED_PATH).read_text())
    ap = seed["alt_paths"]
    first_after = ap["from"] + len(ap["rows"])
    last = snap["days"][-1][0]
    closes = closes_by_day(fetched, range(first_after - 80, last + 1), last)
    T = last
    now = closes.get(T) or {}
    recent = []
    for d, v in snap.get("alt_recent", []):
        c = closes.get(d) or {}
        rs = [c[p] / now[p] for p in c if p != "BTCUSDT" and p in now and now[p] > 0]
        mine = round(100 * statistics.median(rs) - 100, 1) + 0.0 if len(rs) >= MIN_ALTS else None
        recent.append({"day": iso(d), "snapshot": v, "rebuilt": mine,
                       "diff": None if mine is None else round(abs(mine - v), 2)})
    eps = []
    for b in snap.get("bands", []):
        for e in b.get("episodes", []) + b.get("later", []):
            t = e[0]
            if t < first_after:
                continue
            for i, h in enumerate((10, 30, 60)):
                v = e[4 + 2 * i]
                if v is None:
                    continue
                mine = alt_change(closes, t, t + h)
                eps.append({"day": iso(t), "h": h, "snapshot": v, "rebuilt": mine,
                            "diff": None if mine is None else round(abs(mine - v), 2)})
    junction = []
    ks = {k: i for i, k in enumerate(ap["k"])}
    for t in range(first_after - 62, first_after):
        for h in (30, 60):
            v = ap["rows"][t - ap["from"]][ks[h]]
            mine = alt_change(closes, t, t + h)
            if v is not None:
                junction.append({"day": iso(t), "h": h, "seed": v, "rebuilt": mine,
                                 "diff": None if mine is None else round(abs(mine - v), 2)})
    rd = [x["diff"] for x in recent]
    ed = [x["diff"] for x in eps]
    jd = [x["diff"] for x in junction]
    ok = (bool(rd) and None not in rd and max(rd) <= CHECK_TOL["alt_recent"]
          and bool(ed) and None not in ed and max(ed) <= CHECK_TOL["episodes"]
          and bool(jd) and None not in jd and statistics.median(jd) <= CHECK_TOL["junction_median"]
          and max(jd) <= CHECK_TOL["junction_max"])
    return {"passed": ok, "tolerances": CHECK_TOL, "first_rebuilt_origin": iso(first_after),
            "pairs_fetched": len(fetched["pairs"]), "missing": fetched.get("missing"), "failed": fetched.get("failed"),
            "alt_recent": {"days": len(rd), "max_diff": max((x for x in rd if x is not None), default=None),
                           "missing": rd.count(None)},
            "episodes": {"outcomes": len(ed), "max_diff": max((x for x in ed if x is not None), default=None),
                         "missing": ed.count(None), "rows": eps},
            "junction": {"outcomes": len(jd), "median_diff": statistics.median([x for x in jd if x is not None])
                         if any(x is not None for x in jd) else None,
                         "max_diff": max((x for x in jd if x is not None), default=None), "missing": jd.count(None)}}


# ---------------------------------------------------------------- what the bar can see (simulated, no real outcome)

def power(n: int, spread: float, shifts=(0, 5, 10, 15, 20, 25, 30), reps: int = 4000, edge: float = EDGE[60],
          seed: int = RNG_SEED) -> dict:
    """Part A's bar on simulated events: each event's outcome is shift + noise and its comparison days are noise
    (normal, sd = spread, independent events, large comparison pools). Returns the share of reps meeting the bar."""
    import numpy as np
    rng = np.random.default_rng(seed)
    null_meds = np.sort(np.median(rng.normal(0.0, spread, size=(20_000, n)), axis=1))
    out = {}
    k = n // 2
    for s in shifts:
        ev = rng.normal(-s, spread, size=(reps, n))            # a cross under: lower by s points
        med = np.median(ev, axis=1)
        p = np.searchsorted(null_meds, med, side="right") / len(null_meds)   # draws at or below
        same = (ev < 0).sum(axis=1) >= SAME_WAY * n
        edge_ok = med <= -edge
        halves = (np.median(ev[:, :k], axis=1) < 0) & (np.median(ev[:, k:], axis=1) < 0)
        met = same & edge_ok & (p <= DRAW_P) & halves & (n >= MIN_N)
        out[s] = round(float(met.mean()), 3)
    return out


# ---------------------------------------------------------------- command line

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("fetch", "check", "shape", "power", "run"))
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--closes", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--n-under", type=int)
    ap.add_argument("--n-over", type=int)
    ap.add_argument("--oos", action="store_true", help="count only crossings, starts and ends from 7 November 2026")
    a = ap.parse_args()
    if a.cmd == "fetch":
        seed = json.loads(Path(SEED_PATH).read_text())
        res = fetch(seed["pairs"], a.out)
    elif a.cmd == "power":
        res = {name: {str(sp): power(n, sp) for sp in (26.0, 28.0)}
               for name, n in (("under", a.n_under), ("over", a.n_over)) if n}
    else:
        snap = json.loads(a.snapshot.read_text())
        if a.cmd == "shape":
            res = shape(snap)
        else:
            fetched = json.loads(a.closes.read_text())
            chk = check(snap, fetched)
            if a.cmd == "check":
                res = chk
            else:
                last = snap["days"][-1][0]
                closes = closes_by_day(fetched, range(chk_first(chk), last + 1), last) if chk["passed"] else {}
                res = {"data_check_passed": chk["passed"], **run_study(snap, closes, oos=a.oos)}
    text = json.dumps(res, indent=1)
    if a.out and a.cmd != "fetch":
        a.out.write_text(text)
    print(text)


def chk_first(chk: dict) -> int:
    """The first origin rebuilt from the closes, as a day number (the seed's paths cover the days before)."""
    d = datetime.fromisoformat(chk["first_rebuilt_origin"]).date()
    return (d - datetime(1970, 1, 1).date()).days


if __name__ == "__main__":
    main()
