"""
A crowd of profitable traders, nearly all long, in greed: what followed? (docs/reviews/crowd-size-study.md,
declared 6 November 2026, before running). The owner's reading of September and October 2026: many profitable-trader
positions open, nearly all long, Fear & Greed high and a broad uptrend under way, and the market rolled over soon
after. Did that combination come before roll-overs more often than other greedy days in a broad uptrend? Context, not
a signal unless the declared bar is met.

Run from backend/:

  python -m research.crowd_size check --feed WALLETS.json            (rebuilt against recorded counts, no outcome)
  python -m research.crowd_size shape --snapshot MH.json --feed WALLETS.json
                                                                     (counts only, no outcome)
  python -m research.crowd_size run --snapshot MH.json --feed WALLETS.json --closes CLOSES.json [--oos] [--out JSON]

MH.json: a saved /api/market-history response. WALLETS.json: a saved /api/market-history/wallets response (its
`crowd` rows: recorded days carry the counts). CLOSES.json: the public daily candles the uptrend-band study fetched
(research.uptrend_band fetch), for the typical alt after the market seed.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

from research import late_uptrends as L
from research import uptrend_band as U
from research.late_uptrends import iso

ROOT = Path(__file__).resolve().parent.parent
CROWD_SEED = ROOT / "seeds" / "crowd_share_seed.json"

TRAIL = 90                 # a day's crowd is measured against the 90 days to it (itself included)...
MIN_TRAIL = 60             # ...with at least 60 of them read
TOP = 0.80                 # crowded: at least 80% of those days at or below it, for the long positions and the share
GREED = L.GREED            # Fear & Greed at or above 70: the engine's own line
GAP = 5                    # hot-crowd days with gaps of up to 5 days form one stretch
LOOKBACK = GAP + 1         # a stretch's first day needs its 6 days before readable (else its start is unknown)
COOLDOWN = 30              # an episode needs no stretch start in the 30 days before it
HORIZON = 30               # roll-over within 30 days; the deciding price outcome is the typical alt over 30 days
ROLL_EDGE = 0.25           # the episodes' roll-over rate at least 25 points over the comparison days'
ALT_EDGE = 5.0             # the typical alt at least 5 points under the comparison days' median
MIN_N = U.MIN_N            # 8 episodes
SAME_WAY = U.SAME_WAY      # 75%
DRAWS = U.DRAWS            # 10,000
DRAW_P = U.DRAW_P          # 5%
RNG_SEED = 20261106
CHECK_RHO = 0.6            # the data check: rebuilt and recorded daily counts rank alike over the overlap
CHECK_MIN_DAYS = 14
SEEN_FROM = 20725          # 29 September 2026: the recorded days the owner and this declaration have seen
OOS_FROM = 20764           # 7 November 2026: episodes from here count out of sample
PRICE_KEYS = ("alt30", "btc30", "alt14", "btc14")
PRICE_EDGE = {"alt30": ALT_EDGE, "btc30": 5.0, "alt14": 3.0, "btc14": 3.0}   # only alt30 decides


# ---------------------------------------------------------------- positions: rebuilt, recorded, joined

def rebuilt_counts(seed: dict) -> dict:
    """{day: (long, short)} from the crowd seed (weighted counts, backtest.crowd_history_rebuild)."""
    ix = {c: i for i, c in enumerate(seed["columns"])}
    return {int(r[ix["day"]]): (r[ix["long"]], r[ix["short"]]) for r in seed["rows"] if r[ix["long"]] + r[ix["short"]]}


def recorded_counts(feed: dict) -> dict:
    """{day: (long, short)} of the recorded days in a /api/market-history/wallets response."""
    c = feed["crowd"]
    ix = {k: i for i, k in enumerate(c["columns"])}
    return {int(r[ix["day"]]): (r[ix["long"]], r[ix["short"]]) for r in c["rows"]
            if not r[ix["rebuilt"]] and r[ix["long"]] is not None and r[ix["long"]] + r[ix["short"]]}


def ranks(xs: list) -> list:
    """Average ranks (ties share their mean rank)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a: list, b: list):
    if len(a) < 3:
        return None
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return None if not den else num / den


def check(reb: dict, rec: dict) -> dict:
    """Rebuilt against recorded on the days both have: how alike they rank (long positions, all positions), and the
    factors that put the rebuilt days on the recorded level (the median ratio of long positions; the mean difference
    of the share long, as the page shifts it). Passed: 14+ days and both rank correlations at 0.6 or more."""
    both = sorted(d for d in reb if d in rec)
    if not both:
        return {"days": 0, "passed": False}
    lr = [reb[d][0] for d in both]
    lc = [rec[d][0] for d in both]
    tr = [sum(reb[d]) for d in both]
    tc = [sum(rec[d]) for d in both]
    share = lambda x: x[0] / (x[0] + x[1])
    ratios = sorted(c / r for r, c in zip(lr, lc) if r)
    q = statistics.quantiles(ratios, n=4) if len(ratios) >= 4 else None
    rho_long, rho_all = spearman(lr, lc), spearman(tr, tc)
    passed = (len(both) >= CHECK_MIN_DAYS and rho_long is not None and rho_all is not None
              and rho_long >= CHECK_RHO and rho_all >= CHECK_RHO)
    return {"days": len(both), "from": iso(both[0]), "to": iso(both[-1]),
            "rho_long": None if rho_long is None else round(rho_long, 3),
            "rho_all": None if rho_all is None else round(rho_all, 3),
            "long_ratio": round(statistics.median(ratios), 3) if ratios else None,
            "long_ratio_quartiles": None if q is None else [round(q[0], 3), round(q[2], 3)],
            "share_offset": round(statistics.fmean(share(rec[d]) - share(reb[d]) for d in both), 4),
            "passed": passed}


def joined(reb: dict, rec: dict, chk: dict, oos: bool = False) -> dict:
    """{day: (long positions, share long)}: recorded days as they are; with the check passed, the rebuilt days before
    the first recorded day on the recorded level (long positions times the median ratio, the share plus the mean
    difference, held in 0-1). Without it the two are kept apart: the rebuilt days alone in sample, the recorded days
    alone out of sample."""
    share = lambda x: x[0] / (x[0] + x[1])
    if not chk.get("passed"):
        return {d: (x[0], share(x)) for d, x in (rec if oos else reb).items()}
    first = min(rec) if rec else None
    out = {d: (x[0] * chk["long_ratio"], min(1.0, max(0.0, share(x) + chk["share_offset"])))
           for d, x in reb.items() if first is None or d < first}
    out.update({d: (x[0], share(x)) for d, x in rec.items()})
    return out


# ---------------------------------------------------------------- crowded, hot, episodes

def top_of(values: list, v: float) -> float:
    """The share of `values` at or below v."""
    return sum(x <= v for x in values) / len(values)


def crowd_state(series: dict) -> dict:
    """{day: True/False} for days with 60+ readings in their 90 days: crowded when both the long positions and the
    share long are at or above 80% of the window's days (itself included). Days without enough readings are absent."""
    out = {}
    days = sorted(series)
    for d in days:
        win = [series[x] for x in range(d - TRAIL + 1, d + 1) if x in series]
        if len(win) < MIN_TRAIL:
            continue
        lo, sh = series[d]
        out[d] = top_of([w[0] for w in win], lo) >= TOP and top_of([w[1] for w in win], sh) >= TOP
    return out


def fear_greed(snap: dict) -> dict:
    return {int(d): v for d, v in snap.get("fear_greed") or [] if v is not None}


def hot_state(rows: list, fg: dict, state: dict) -> dict:
    """{day: True/False}: Fear & Greed at 70 or more and a broad uptrend under way (the 55% rule's own state that day,
    its 1-4 dip days included). Days without a Fear & Greed reading are absent."""
    return {r["day"]: bool(fg[r["day"]] >= GREED and state.get(r["day"], {}).get("on"))
            for r in rows if r["day"] in fg}


def uptrend_state(rows: list, state: dict) -> dict:
    """{day: True/False}: a broad uptrend under way (the reported, wider layer: no greed needed)."""
    return {r["day"]: bool(state.get(r["day"], {}).get("on")) for r in rows}


def episodes(crowd: dict, hot: dict) -> list:
    """Stretches of hot crowded days (gaps of up to 5 days joined): [{first, last, known}]. Known: the 6 days before
    the first day all have both readings. Returns them oldest first."""
    days = sorted(d for d in crowd if d in hot)
    flagged = {d for d in days if crowd[d] and hot[d]}
    readable = set(days)
    return [{"first": f, "last": la, "known": all(f - k in readable for k in range(1, LOOKBACK + 1))}
            for f, la in U.stretches(days, flagged, GAP)]


def split(stretches: list, oos: bool) -> tuple:
    """(counted episodes, seen ones). In sample: episodes whose stretch ends before 29 September 2026; the ones
    reaching into the days seen before declaring (29 September to 6 November 2026: the owner's own episode) are
    reported apart, never counted. Out of sample: episodes starting from 7 November 2026."""
    ev = set(counted(stretches))
    if oos:
        return [s["first"] for s in stretches if s["first"] in ev and s["first"] >= OOS_FROM], []
    keep = [s["first"] for s in stretches if s["first"] in ev and s["last"] < SEEN_FROM]
    seen = [s["first"] for s in stretches if s["first"] in ev and s["last"] >= SEEN_FROM and s["first"] < OOS_FROM]
    return keep, seen


def counted(stretches: list) -> list:
    """Known stretch starts with no stretch start (known or not) in the 30 days before."""
    firsts = sorted(s["first"] for s in stretches)
    keep = set(U.counted(firsts, COOLDOWN))
    return [s["first"] for s in stretches if s["known"] and s["first"] in keep]


# ---------------------------------------------------------------- outcomes

def rolled_within(d: int, state: dict, runs: list, share: dict, last: int, h: int = HORIZON):
    """True when the broad uptrend under way on day d rolled over or ended in the h days after d; False when neither
    and d + h is in the data; None when not known yet or no run is on. Its roll-over is the page's mark, once per
    run: the first day the share is 20 points under the run's high so far (L.roll_over). A run that rolled over on or
    before d counts only its end."""
    st = state.get(d, {})
    if not st.get("on"):
        return None
    run = runs[st["run"]]
    roll = L.roll_over(run, share)
    hit = [x for x in (roll, run["end"]) if x is not None and d < x <= d + h]
    if hit:
        return True
    return False if d + h <= last else None


def comparison_days(hot: dict, crowd: dict, starts: list, rolled: dict) -> list:
    """Hot days whose crowd is readable and not crowded, not within 30 days after a stretch start, outcome known."""
    near = set()
    for s in starts:
        near.update(range(s, s + COOLDOWN + 1))
    return [d for d in sorted(hot) if hot[d] and d in crowd and not crowd[d] and d not in near
            and rolled.get(d) is not None]


def roll_block(events: list, pool: list, rolled: dict) -> dict:
    """The declared checks for the roll-over outcome."""
    ev = [e for e in events if rolled.get(e) is not None]
    n = len(ev)
    base = sum(rolled[d] for d in pool) / len(pool) if pool else None
    if not n or base is None:
        return {"events": n, "comparison_days": len(pool), "verdict": "not met"}
    k = sum(rolled[e] for e in ev)
    rng = random.Random(RNG_SEED)
    beyond = sum(sum(rolled[rng.choice(pool)] for _ in range(n)) >= k for _ in range(DRAWS)) / DRAWS
    half = n // 2
    rate = lambda xs: sum(rolled[x] for x in xs) / len(xs) if xs else None
    halves = [rate(ev[:half]), rate(ev[half:])] if n >= 2 else None
    out = {"events": n, "rolled": k, "rate": round(k / n, 3), "comparison_days": len(pool),
           "comparison_rate": round(base, 3), "enough": n >= MIN_N, "consistent": k >= SAME_WAY * n,
           "edge": k / n - base >= ROLL_EDGE, "draws_at_or_beyond": round(beyond, 4), "beyond_random": beyond <= DRAW_P,
           "halves": None if halves is None else [round(x, 3) for x in halves],
           "halves_agree": halves is not None and all(x > base for x in halves)}
    out["verdict"] = "met" if all(out[c] for c in ("enough", "consistent", "edge", "beyond_random", "halves_agree")) \
        else "not met"
    return out


# ---------------------------------------------------------------- the study

def build(snap: dict, feed: dict, closes: dict | None, seed: dict | None = None, oos: bool = False):
    seed = seed or json.loads(CROWD_SEED.read_text())
    reb, rec = rebuilt_counts(seed), recorded_counts(feed)
    chk = check(reb, rec)
    rows = U.load_rows(snap)
    alt = U.make_alt_ret(U.seed_alt_paths(), closes or {})
    vals = U.Values(rows, alt)
    state, runs = L.runs(rows)
    hot = hot_state(rows, fear_greed(snap), state)
    series = joined(reb, rec, chk, oos)
    crowd = crowd_state(series)
    return reb, rec, chk, rows, vals, state, runs, hot, series, crowd


def shape(snap: dict, feed: dict, seed: dict | None = None) -> dict:
    """Counts only, for the declaration: no outcome is read."""
    reb, rec, chk, rows, vals, state, runs, hot, series, crowd = build(snap, feed, None, seed)
    st = episodes(crowd, hot)
    ev = counted(st)
    last = vals.last
    in_sample, seen = split(st, False)
    return {"check": chk, "series": [iso(min(series)), iso(max(series)), len(series)],
            "crowd_readable": [iso(min(crowd)), iso(max(crowd)), len(crowd)] if crowd else None,
            "crowded_days": sum(crowd.values()), "hot_days": sum(v for d, v in hot.items() if d in crowd),
            "hot_crowded_days": sum(1 for d in crowd if crowd[d] and hot.get(d)),
            "stretches": [{"first": iso(s["first"]), "last": iso(s["last"]), "known": s["known"]} for s in st],
            "episodes": [iso(d) for d in ev], "in_sample": len(in_sample),
            "in_sample_with_30_days": sum(d + HORIZON <= last for d in in_sample),
            "seen": [iso(d) for d in seen],
            "wider": _wider_shape(rows, state, crowd, last)}


def _wider_shape(rows, state, crowd, last) -> dict:
    up = uptrend_state(rows, state)
    st = episodes(crowd, up)
    keep, seen = split(st, False)
    days = [d for d in crowd if up.get(d)]
    return {"uptrend_days_readable": len(days), "crowded_uptrend_days": sum(crowd[d] for d in days),
            "stretches": len(st), "episodes": [iso(d) for d in keep], "seen": [iso(d) for d in seen],
            "in_sample_with_30_days": sum(d + HORIZON <= last for d in keep)}


def episode_rows(events: list, vals, series, hot_fg, state, rolled) -> list:
    out = []
    for d in events:
        lo, sh = series[d]
        st = state.get(d, {})
        out.append({"day": iso(d), "long_positions": round(lo), "share_long": round(100 * sh, 1), "fear_greed": hot_fg.get(d),
                    "uptrend_share": round(100 * vals.share[d], 1), "run_day": st.get("age", -1) + 1 if st.get("on") else None,
                    "rolled_within_30": rolled.get(d), **{k: vals.get(d, k) for k in PRICE_KEYS}})
    return out


def by_tercile(days: list, series: dict, crowd_rank: dict, vals, rolled: dict) -> list:
    """Broad-uptrend days with greed, by where their long positions sat in their 90 days (lower, middle, upper third):
    the roll-over rate within 30 days and the medians of the price outcomes. The days overlap: description only."""
    out = []
    for name, lo, hi in (("lower third", 0, 1 / 3), ("middle third", 1 / 3, 2 / 3), ("upper third", 2 / 3, 1.01)):
        ds = [d for d in days if lo <= crowd_rank[d] < hi and rolled.get(d) is not None]
        row = {"third": name, "days": len(ds), "rolled_within_30": round(sum(rolled[d] for d in ds) / len(ds), 3) if ds else None}
        for k in PRICE_KEYS:
            xs = [vals.get(d, k) for d in ds if vals.get(d, k) is not None]
            row[k] = round(statistics.median(xs), 1) if xs else None
        out.append(row)
    return out


def run_study(snap: dict, feed: dict, closes: dict | None, seed: dict | None = None, oos: bool = False) -> dict:
    reb, rec, chk, rows, vals, state, runs, hot, series, crowd = build(snap, feed, closes, seed, oos)
    share = {r["day"]: r["uptrend"] for r in rows}
    rolled = {d: rolled_within(d, state, runs, share, vals.last) for d in hot}
    st = episodes(crowd, hot)
    starts = [s["first"] for s in st]
    events, seen = split(st, oos)
    pool = comparison_days(hot, crowd, starts, rolled)
    fg = fear_greed(snap)
    res = {"declared": "docs/reviews/crowd-size-study.md (6 November 2026)", "out_of_sample": oos,
           "days": [iso(rows[0]["day"]), iso(vals.last)], "check": chk,
           "episodes": episode_rows(events, vals, series, fg, state, rolled),
           "roll_over": roll_block(events, pool, rolled)}
    for k in PRICE_KEYS:
        pools = [[d for d in pool if vals.get(d, k) is not None]] * len(events)
        blk = U.price_block(events, pools, vals, k, -1, PRICE_EDGE[k])
        blk["deciding"] = k == "alt30"
        res[k] = blk
    res["verdict"] = "met" if res["roll_over"]["verdict"] == "met" and res["alt30"]["verdict"] == "met" else "not met"
    res["wider"] = wider(rows, state, runs, crowd, series, vals, fg, share, oos)
    if not oos:
        res["seen_before_declaring"] = episode_rows(seen, vals, series, fg, state, rolled)
        rank = {}
        for d in crowd:
            win = [series[x][0] for x in range(d - TRAIL + 1, d + 1) if x in series]
            rank[d] = top_of(win, series[d][0])
        up_days = [d for d in sorted(crowd) if state.get(d, {}).get("on") and d < SEEN_FROM]
        rolled_up = {d: rolled_within(d, state, runs, share, vals.last) for d in up_days}
        res["uptrend_days_by_long_positions"] = by_tercile(up_days, series, rank, vals, rolled_up)
        greedy = [d for d in up_days if hot.get(d)]
        res["greedy_uptrend_days_by_long_positions"] = by_tercile(greedy, series, rank, vals, rolled_up)
        res["stretches"] = [{"first": iso(s["first"]), "last": iso(s["last"]), "known": s["known"]} for s in st]
    return res


def wider(rows, state, runs, crowd, series, vals, fg, share, oos: bool) -> dict:
    """Reported, never deciding: crowded episodes in any broad uptrend (no greed needed) against the broad-uptrend
    days that were not crowded, with the same outcomes and checks."""
    up = uptrend_state(rows, state)
    rolled = {d: rolled_within(d, state, runs, share, vals.last) for d in up if up[d]}
    st = episodes(crowd, up)
    events, seen = split(st, oos)
    pool = comparison_days(up, crowd, [s["first"] for s in st], rolled)
    out = {"episodes": episode_rows(events, vals, series, fg, state, rolled), "roll_over": roll_block(events, pool, rolled),
           "seen_before_declaring": episode_rows(seen, vals, series, fg, state, rolled)}
    for k in PRICE_KEYS:
        pools = [[d for d in pool if vals.get(d, k) is not None]] * len(events)
        out[k] = U.price_block(events, pools, vals, k, -1, PRICE_EDGE[k])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("check", "shape", "run"))
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--feed", type=Path, required=True)
    ap.add_argument("--closes", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--oos", action="store_true", help="count only episodes from 7 November 2026")
    a = ap.parse_args()
    feed = json.loads(a.feed.read_text())
    if a.cmd == "check":
        seed = json.loads(CROWD_SEED.read_text())
        res = check(rebuilt_counts(seed), recorded_counts(feed))
    else:
        snap = json.loads(a.snapshot.read_text())
        if a.cmd == "shape":
            res = shape(snap, feed)
        else:
            fetched = json.loads(a.closes.read_text())
            chk = U.check(snap, fetched)
            last = snap["days"][-1][0]
            closes = U.closes_by_day(fetched, range(U.chk_first(chk), last + 1), last) if chk["passed"] else {}
            res = {"alt_check_passed": chk["passed"], **run_study(snap, feed, closes, oos=a.oos)}
    text = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
