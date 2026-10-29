"""
Profitable traders at extremes: what followed? (docs/reviews/positioning-extremes-study.md, declared 29 October 2026,
before running). Context, not a signal unless the declared bar is met.

Run from backend/ (no network):

  python -m research.positioning_extremes --live PATH [--feed PATH] [--out JSON]

PATH: a copy of the server's market_history_live.json (BTC's daily closes after the seed). --feed: a saved
/api/market-history/wallets response, for the out-of-sample part (recorded days from 30 October 2026).
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CROWD_SEED = ROOT / "seeds" / "crowd_share_seed.json"
MARKET_SEED = ROOT / "seeds" / "market_history_seed.json"

SHORT_LINE, LONG_LINE = 0.300, 0.860          # the rebuilt year's 10th and 90th percentiles (declared)
REPORTED_LINES = {"short_p05": 0.255, "long_p95": 0.881, "as_short_as_28_oct": 0.285}
GAP = 14                                      # a return inside the line for up to 14 days is the same episode
HORIZONS = (7, 30, 60)
PATH_DAYS = 60
PAST = 30                                     # the past month
MIN_EPISODES = 8
EDGE = 5.0                                    # points over the same-past-month median
DRAWS = 10_000
OOS_FROM = 20756                              # 30 October 2026
_EPOCH = date(1970, 1, 1)


def iso(day: int) -> str:
    return (_EPOCH + timedelta(days=day)).isoformat()


# ---------------------------------------------------------------- data

def readings_from_seed(seed: dict) -> list:
    """[(day, share long)] from the crowd seed ([day, long, short] rows), oldest first."""
    return [(int(r[0]), r[1] / (r[1] + r[2])) for r in seed["rows"] if r[1] + r[2]]


def readings_from_feed(feed: dict, start: int = OOS_FROM) -> tuple:
    """([(day, share long)] of the page's recorded days from `start`, the rebuilt-to-recorded shift in share)."""
    c = feed.get("crowd") or {}
    cols = c.get("columns") or []
    ix = {k: i for i, k in enumerate(cols)}
    rows = [(int(r[ix["day"]]), r[ix["long_share"]]) for r in c.get("rows") or []
            if r[ix["day"]] >= start and not r[ix["rebuilt"]] and r[ix["long_share"]] is not None]
    shift = ((c.get("overlap") or {}).get("offset_pts") or 0.0) / 100
    return rows, shift


def btc_closes(market_seed: dict, live: dict | None) -> dict:
    """{day: BTC close}: the market history seed's days, then the server's record."""
    out = {int(r[0]): r[-1] for r in market_seed["days"] if r[-1]}
    for r in (live or {}).get("days") or []:
        if r[-1]:
            out[int(r[0])] = r[-1]
    return out


# ---------------------------------------------------------------- episodes and outcomes

def episodes(readings: list, beyond, low: bool, gap: int = GAP) -> list:
    """Runs of days beyond a line (beyond(v) is True), a return inside it for up to `gap` days continuing the run.
    Each: {start, end, extreme (day of the lowest reading if `low`, else the highest), back (first day inside after
    the end), days, reading (at the start)}."""
    out = []
    vals = dict(readings)
    for d, v in readings:
        if not beyond(v):
            continue
        if out and d - out[-1]["end"] <= gap:
            e = out[-1]
            e["end"], e["days"] = d, e["days"] + 1
        else:
            out.append({"start": d, "end": d, "days": 1})
    for e in out:
        span = [(d, v) for d, v in readings if e["start"] <= d <= e["end"] and beyond(v)]
        e["extreme"] = (min(span, key=lambda x: x[1]) if low else max(span, key=lambda x: x[1]))[0]
        e["back"] = next((d for d, v in readings if d > e["end"] and not beyond(v)), None)
        e["reading"] = round(vals[e["start"]], 3)
    return out


def change(btc: dict, d: int, h: int):
    """Percent change of BTC's close from day d to d + h; None when either close is missing (censored)."""
    a, b = btc.get(d), btc.get(d + h)
    return None if not a or not b else round(100 * (b / a - 1), 1)


def past_change(btc: dict, d: int, n: int = PAST):
    a, b = btc.get(d - n), btc.get(d)
    return None if not a or not b else 100 * (b / a - 1)


def path(btc: dict, d: int, n: int = PATH_DAYS) -> dict:
    """Within the next n days: the largest fall and rise from day d's close, the day each came, and whether the n
    days are all there."""
    base = btc.get(d)
    later = [(k, btc[d + k]) for k in range(1, n + 1) if btc.get(d + k)]
    if not base or not later:
        return {"fall": None, "fall_day": None, "rise": None, "rise_day": None, "complete": False}
    lo = min(later, key=lambda x: x[1])
    hi = max(later, key=lambda x: x[1])
    return {"fall": round(100 * (lo[1] / base - 1), 1), "fall_day": lo[0], "rise": round(100 * (hi[1] / base - 1), 1),
            "rise_day": hi[0], "complete": later[-1][0] == n}


def fifths(values: list) -> list:
    """The four cut points between the fifths of `values`."""
    xs = sorted(values)
    return [xs[int(len(xs) * k / 5)] for k in (1, 2, 3, 4)]


def fifth(v: float, cuts: list) -> int:
    return sum(v >= c for c in cuts)


# ---------------------------------------------------------------- comparisons

def describe(xs: list) -> dict | None:
    if not xs:
        return None
    q = statistics.quantiles(xs, n=4) if len(xs) >= 2 else [xs[0]] * 3
    return {"n": len(xs), "median": round(statistics.median(xs), 1), "q1": round(q[0], 1), "q3": round(q[2], 1),
            "up": round(sum(x > 0 for x in xs) / len(xs), 2)}


def every_day(btc: dict, days: list, h: int) -> dict | None:
    return describe([c for c in (change(btc, d, h) for d in days) if c is not None])


def same_month_pool(btc: dict, readings: list, h: int) -> tuple:
    """(cut points of the past-month fifths over the window's days, {fifth: [h-day changes of days inside both lines]},
    {fifth: [every window day with a complete outcome]})."""
    days = [d for d, _ in readings]
    pasts = {d: past_change(btc, d) for d in days}
    cuts = fifths([p for p in pasts.values() if p is not None])
    inside, every = {}, {}
    for d, v in readings:
        c, p = change(btc, d, h), pasts[d]
        if c is None or p is None:
            continue
        every.setdefault(fifth(p, cuts), []).append(d)
        if SHORT_LINE < v < LONG_LINE:
            inside.setdefault(fifth(p, cuts), []).append(c)
    return cuts, inside, every


def same_month(btc: dict, d: int, cuts: list, inside: dict):
    p = past_change(btc, d)
    pool = inside.get(fifth(p, cuts), []) if p is not None else []
    return None if not pool else {"fifth": fifth(p, cuts) + 1, "n": len(pool), "median": round(statistics.median(pool), 1)}


def seven_years(btc: dict, d: int, side: str, gap: int = GAP) -> dict:
    """Every run since BTC's first close in the data with a previous-30-day change at or below (short) / at or above
    (long) the change at day d, one case per run from its first day, with what followed."""
    p0 = past_change(btc, d)
    if p0 is None:
        return {"cases": []}
    test = (lambda p: p <= p0) if side == "short" else (lambda p: p >= p0)
    starts, last = [], None
    for k in sorted(btc):
        p = past_change(btc, k)
        if p is None or not test(p):
            continue
        if last is None or k - last > gap:
            starts.append(k)
        last = k
    cases = [{"start": iso(k), **{f"d{h}": change(btc, k, h) for h in HORIZONS}} for k in starts if k < d]
    out = {"past30": round(p0, 1), "cases": cases}
    for h in HORIZONS:
        out[f"d{h}"] = describe([c[f"d{h}"] for c in cases if c[f"d{h}"] is not None])
    return out


def permutation(btc: dict, starts: list, every: dict, cuts: list, h: int, draws: int = DRAWS, seed: int = 20261029):
    """Where the median h-day change of `starts` sits among `draws` random sets of as many window days, each drawn
    from the same past-month fifth as the start it stands for: the share of draws at or below it."""
    obs = [change(btc, d, h) for d in starts]
    if any(c is None for c in obs) or not obs:
        return None
    strata = [every.get(fifth(past_change(btc, d), cuts), []) for d in starts]
    if any(not s for s in strata):
        return None
    m = statistics.median(obs)
    rng = random.Random(seed)
    at_or_below = 0
    for _ in range(draws):
        sample = [change(btc, rng.choice(s), h) for s in strata]
        at_or_below += statistics.median(sample) <= m
    return round(at_or_below / draws, 3)


# ---------------------------------------------------------------- the study

def side_report(btc: dict, readings: list, side: str, line: float, newest: int) -> dict:
    beyond = (lambda v: v <= line) if side == "short" else (lambda v: v >= line)
    eps = episodes(readings, beyond, low=side == "short")
    first_day = readings[0][0]
    window = [d for d, _ in readings]
    cuts, inside, every = same_month_pool(btc, readings, 30)
    rows = []
    for e in eps:
        r = {"start": iso(e["start"]), "end": iso(e["end"]), "days": e["days"], "reading": e["reading"],
             "extreme": iso(e["extreme"]), "back": iso(e["back"]) if e["back"] is not None else None,
             "counted": e["start"] != first_day, "btc": btc.get(e["start"]),
             "past30": None if past_change(btc, e["start"]) is None else round(past_change(btc, e["start"]), 1)}
        for h in HORIZONS:
            r[f"d{h}"] = change(btc, e["start"], h)
        r["path"] = path(btc, e["start"])
        r["since_start"] = change(btc, e["start"], newest - e["start"]) if newest > e["start"] else None
        r["same_month"] = same_month(btc, e["start"], cuts, inside)
        r["seven_years"] = seven_years(btc, e["start"], side)
        r["from_extreme"] = {f"d{h}": change(btc, e["extreme"], h) for h in HORIZONS}
        r["from_back"] = {f"d{h}": change(btc, e["back"], h) for h in HORIZONS} if e["back"] is not None else None
        rows.append(r)
    counted = [e for e, r in zip(eps, rows) if r["counted"] and r["d30"] is not None]
    starts = [e["start"] for e in counted]
    med = statistics.median([change(btc, d, 30) for d in starts]) if starts else None
    sm = [same_month(btc, d, cuts, inside) for d in starts]
    sm_med = statistics.median([s["median"] for s in sm if s]) if any(sm) else None
    perm = permutation(btc, starts, every, cuts, 30) if starts else None
    halves = None
    if len(starts) >= 2:
        k = len(starts) // 2
        a = statistics.median([change(btc, d, 30) for d in starts[:k]])
        b = statistics.median([change(btc, d, 30) for d in starts[k:]])
        halves = [round(a, 1), round(b, 1)]
    want_up = side == "short"
    checks = {
        "episodes": len(starts),
        "enough": len(starts) >= MIN_EPISODES,
        "median_30d": None if med is None else round(med, 1),
        "same_month_median_30d": None if sm_med is None else round(sm_med, 1),
        "edge": None if med is None or sm_med is None else (med - sm_med >= EDGE if want_up else sm_med - med >= EDGE),
        "permutation_share_at_or_below": perm,
        "beyond_random": None if perm is None else (perm >= 0.90 if want_up else perm <= 0.10),
        "halves": halves,
    }
    checks["verdict"] = ("met" if checks["enough"] and checks["edge"] and checks["beyond_random"] and halves
                         and (min(halves) > (sm_med or 0) if want_up else max(halves) < (sm_med or 0))
                         else "not met")
    return {"line": line, "episodes": rows, "checks": checks,
            "every_day": {f"d{h}": every_day(btc, window, h) for h in HORIZONS}}


def run(seed: dict, market_seed: dict, live: dict | None, feed: dict | None = None) -> dict:
    btc = btc_closes(market_seed, live)
    rd = readings_from_seed(seed)
    newest = max(btc)
    out = {"declared": "docs/reviews/positioning-extremes-study.md (29 October 2026)",
           "readings": [iso(rd[0][0]), iso(rd[-1][0]), len(rd)], "btc_through": iso(newest),
           "short": side_report(btc, rd, "short", SHORT_LINE, newest),
           "long": side_report(btc, rd, "long", LONG_LINE, newest),
           "reported": {k: side_report(btc, rd, "short" if k.startswith(("short", "as_short")) else "long", v, newest)["episodes"]
                        for k, v in REPORTED_LINES.items()}}
    if feed:
        rec, shift = readings_from_feed(feed)
        out["out_of_sample"] = {"shift": shift, "days": len(rec),
                                "short": side_report(btc, rec, "short", SHORT_LINE + shift, newest) if rec else None,
                                "long": side_report(btc, rec, "long", LONG_LINE + shift, newest) if rec else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", required=True, help="a copy of the server's market_history_live.json")
    ap.add_argument("--feed", help="a saved /api/market-history/wallets response (out of sample)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(json.loads(CROWD_SEED.read_text()), json.loads(MARKET_SEED.read_text()), json.loads(Path(a.live).read_text()),
              json.loads(Path(a.feed).read_text()) if a.feed else None)
    text = json.dumps(res, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
