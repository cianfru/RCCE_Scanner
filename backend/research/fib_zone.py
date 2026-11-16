"""
The 0.618 to 0.66 retracement zone of major swings (docs/reviews/fib-zone-study.md, declared before running).

Chart Champions' guides call the band between the 0.618 and 0.66 retracements of a swing their zone, and put
trades where it meets another level. This asks, on the candles of the 80% rule study: does price turn there more
than at other depths of a pullback, does a weekly or monthly POC in the zone add, and does the trade pay?

Run from backend/:

  python -m research.fib_zone shape [--holdout] [--out JSON]      (counts only: no race or trade is scored)
  python -m research.fib_zone power --shape JSON                   (the bars on made-up outcomes)
  python -m research.fib_zone run [--holdout] [--out JSON]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from engines import auction_engine as ae
from engines.levels_engine import wilder_atr
from research import auction_studies as A
from research import value_area_rule as V

DAY = V.DAY_MS
# Every USDT perpetual with a monthly 5-minute archive on data.binance.vision for each month from December 2020
# to October 2026 (71 coins; the DEFI index is left out). Listed 16 November 2026.
SYMBOLS = tuple("""
    1INCHUSDT AAVEUSDT ADAUSDT ALGOUSDT ALPHAUSDT ATOMUSDT AVAXUSDT AXSUSDT BALUSDT BANDUSDT BATUSDT BCHUSDT
    BELUSDT BLZUSDT BNBUSDT BTCUSDT COMPUSDT CRVUSDT CTKUSDT CVCUSDT DASHUSDT DOGEUSDT DOTUSDT EGLDUSDT
    ENJUSDT ETCUSDT ETHUSDT FILUSDT FLMUSDT FTMUSDT GRTUSDT ICXUSDT IOSTUSDT IOTAUSDT KAVAUSDT KNCUSDT KSMUSDT
    LINKUSDT LRCUSDT LTCUSDT MKRUSDT NEARUSDT NEOUSDT OCEANUSDT OMGUSDT ONTUSDT QTUMUSDT RENUSDT RLCUSDT
    RSRUSDT RUNEUSDT SKLUSDT SNXUSDT SOLUSDT STORJUSDT SUSHIUSDT THETAUSDT TRBUSDT TRXUSDT UNIUSDT VETUSDT
    WAVESUSDT XLMUSDT XMRUSDT XRPUSDT XTZUSDT YFIUSDT ZECUSDT ZENUSDT ZILUSDT ZRXUSDT
""".split())
K_REVERSAL = ae.FIB_REVERSAL     # a swing is confirmed when price has come back 3 daily ATRs from it
MIN_LEG = ae.FIB_MIN_LEG         # a leg counts once it is 6 daily ATRs tall
swings = ae.swings               # the swings the coin chart's zone is drawn from
NAMED = (0.382, 0.5, 0.618, 0.786)
UNNAMED = (0.30, 0.45, 0.56, 0.70, 0.85)
DEPTHS = tuple(sorted(NAMED + UNNAMED))
ZONE_TOP, ZONE_END = ae.FIB_ZONE
W = 0.08                   # the race: which comes first, 8% of the leg back up or 8% of it further down
RACE_DAYS, TRADE_DAYS = 60, 90
STOP_DEPTH = 0.786
POC_WEEKS, POC_MONTHS = 12, 6
TOL = 0.0025               # a POC counts as in the zone within 0.25% of its edges
IN_SAMPLE = ("2021-03-01", "2025-07-31")
HOLDOUT = ("2025-11-01", "2026-07-31")

SHARE, EDGE = 0.55, 0.05
MIN_RACES, MIN_MONTHS = 200, 30
MIN_GROUP, MIN_GROUP_MONTHS = 100, 20


# ---------------------------------------------------------------------------
# Daily candles, swings and legs (everything known at the time)
# ---------------------------------------------------------------------------

def daily(d: dict) -> dict:
    """UTC daily candles from the 5-minute ones (days with nearly all their candles), with each day's slice."""
    day = d["ts"] // DAY
    days, start, count = np.unique(day, return_index=True, return_counts=True)
    keep = count >= V.MIN_BARS
    hi, lo = np.maximum.reduceat(d["high"], start), np.minimum.reduceat(d["low"], start)
    close = d["close"][start + count - 1]
    out = {"day": (days * DAY)[keep], "high": hi[keep], "low": lo[keep], "close": close[keep],
           "start": start[keep], "stop": (start + count)[keep]}
    out["atr"] = wilder_atr(out["high"], out["low"], out["close"])
    return out


def leg_touches(hi: np.ndarray, lo: np.ndarray, base: float, top0: float, tall: np.ndarray) -> list:
    """First touches of each depth in an up-leg from ``base``, on 5-minute highs and lows from the leg's first
    candle. The leg's top is the highest price so far (``top0`` before the first candle). A depth is touched when
    a candle that does not make a new top trades down to top - depth x (top - base); one touch per depth each
    time a new top is set. ``tall``: per candle, whether the leg is tall enough. Stops when price trades under
    the base. Returns (depth, candle offset, top at that time)."""
    dead = np.flatnonzero(lo < base)
    n = int(dead[0]) if dead.size else len(hi)
    if not n:
        return []
    hi, lo = hi[:n], lo[:n]
    run = np.maximum.accumulate(np.maximum(hi, top0))
    top = np.concatenate(([top0], run[:-1]))             # the top before each candle
    fresh = hi > top
    episode = np.cumsum(fresh)
    out = []
    for depth in DEPTHS:
        hit = np.flatnonzero((lo <= top - depth * (top - base)) & ~fresh & tall[:n])
        if hit.size:
            _, firsts = np.unique(episode[hit], return_index=True)
            out += [(depth, int(hit[f]), float(top[hit[f]])) for f in firsts]
    return out


def touches(sym: str, d: dict, first: str, last: str) -> list:
    """Every first touch of a depth, in legs up and down, with touch times in [first, last].
    A leg starts the day after its swing is confirmed and lasts until a later swing of the same kind is confirmed
    or price trades beyond its base. direction +1: an up-leg (a pullback down into the level; a turn is back up)."""
    dd = daily(d)
    piv = swings(dd["high"], dd["low"], dd["atr"])
    lo_ms, hi_ms = V._ms(first), V._ms(last) + DAY - 1
    day_of = np.searchsorted(dd["day"], d["ts"] // DAY * DAY, side="left")       # completed days before each candle
    atr_prev = np.where(day_of > 0, dd["atr"][np.maximum(day_of - 1, 0)], np.nan)
    rows = []
    for kind, direction in (("L", 1), ("H", -1)):
        mine = [p for p in piv if p[0] == kind]
        for n, (_, price, at, confirmed) in enumerate(mine):
            if confirmed + 1 >= len(dd["day"]):
                continue
            g0 = int(dd["start"][confirmed + 1])
            nxt = mine[n + 1][3] + 1 if n + 1 < len(mine) else None
            g1 = int(dd["start"][nxt]) if nxt is not None and nxt < len(dd["day"]) else len(d["ts"])
            if g1 <= g0:
                continue
            if direction > 0:
                hi, lo, base = d["high"][g0:g1], d["low"][g0:g1], price
                top0 = float(dd["high"][at:confirmed + 1].max())
            else:                                           # a down-leg is an up-leg of the negated prices
                hi, lo, base = -d["low"][g0:g1], -d["high"][g0:g1], -price
                top0 = float(-dd["low"][at:confirmed + 1].min())
            tall = (np.maximum.accumulate(np.maximum(hi, top0)) - base) >= MIN_LEG * atr_prev[g0:g1]
            for depth, off, top in leg_touches(hi, lo, base, top0, tall):
                g = g0 + off
                t = int(d["ts"][g])
                if not lo_ms <= t <= hi_ms:
                    continue
                height = top - base
                rows.append({"sym": sym, "direction": direction, "depth": depth, "g": g, "t": t,
                             "day": int(ae.session_starts([t], "month")[0]),      # months are the unit
                             "extreme": direction * top, "base": direction * base, "height": height,
                             "level": direction * (top - depth * height), "leg": (sym, kind, at),
                             "height_pct": height / abs(top - depth * height)})
    return rows


# ---------------------------------------------------------------------------
# Weekly and monthly POCs near the zone
# ---------------------------------------------------------------------------

def month_table(d: dict) -> dict:
    """Per calendar month with at least 95% of its candles: its POC."""
    mo = ae.session_starts(d["ts"], "month")
    months, start, count = np.unique(mo, return_index=True, return_counts=True)
    out = {}
    for i in range(len(months)):
        full = (ae.session_end(int(months[i]), "month") - int(months[i])) // V.BAR_MS
        sl = slice(int(start[i]), int(start[i] + count[i]))
        if count[i] < 0.95 * full or not d["volume"][sl].sum() > 0:
            continue
        step = ae.nice_step(float(d["close"][sl][-1]) * ae.STEP_FRACTION["month"])
        out[int(months[i])] = ae.session_levels(d["high"][sl], d["low"][sl], d["volume"][sl], step)[0]
    return out


def pocs_before(t: int, weeks: dict, months: dict) -> list:
    """POCs of the 12 finished weeks and 6 finished months before the week and month of t."""
    week = int(ae.session_starts([t], "week")[0])
    out = [weeks[w]["poc"] for w in (week - k * 7 * DAY for k in range(1, POC_WEEKS + 1)) if w in weeks]
    m = np.datetime64(int(ae.session_starts([t], "month")[0]), "ms").astype("datetime64[M]")
    for k in range(1, POC_MONTHS + 1):
        key = int((m - np.timedelta64(k, "M")).astype("datetime64[ms]").astype(np.int64))
        if key in months:
            out.append(months[key])
    return out


def poc_in_zone(row: dict, pocs: list) -> bool:
    a = row["extreme"] - row["direction"] * ZONE_TOP * row["height"]
    b = row["extreme"] - row["direction"] * ZONE_END * row["height"]
    lo, hi = min(a, b) * (1 - TOL), max(a, b) * (1 + TOL)
    return any(lo <= p <= hi for p in pocs)


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

def race(d: dict, row: dict):
    """After a touch: which comes first within 60 days, W of the leg back towards its extreme ('turn') or W of it
    further ('deeper')? 'tie' when one candle holds both, 'none' when neither, None when candles are missing."""
    i0 = row["g"] + 1
    i1 = int(np.searchsorted(d["ts"], row["t"] + RACE_DAYS * DAY))
    if i1 >= len(d["ts"]) and d["ts"][-1] < row["t"] + RACE_DAYS * DAY - DAY:
        return None
    w, s = W * row["height"], row["direction"]
    hi, lo = d["high"][i0:i1], d["low"][i0:i1]
    back = (hi >= row["level"] + w) if s > 0 else (lo <= row["level"] - w)
    on = (lo <= row["level"] - w) if s > 0 else (hi >= row["level"] + w)
    a = int(np.argmax(back)) if back.any() else None
    b = int(np.argmax(on)) if on.any() else None
    if a is None and b is None:
        return "none"
    if b is None or (a is not None and a < b):
        return "turn"
    if a is None or b < a:
        return "deeper"
    return "tie"


def zone_trade(d: dict, row: dict):
    """In at the 0.618 level when it is touched, with the leg; stop at the 0.786 level; out at the leg's
    extreme, at the stop, or after 90 days at the last price. None when candles are missing."""
    end = row["t"] + TRADE_DAYS * DAY
    if d["ts"][-1] < end - DAY:
        return None
    i1 = int(np.searchsorted(d["ts"], end))
    stop = row["extreme"] - row["direction"] * STOP_DEPTH * row["height"]
    return A.trade(d, row["g"] + 1, i1, row["direction"], row["level"], stop, row["extreme"])


def gather(first: str, last: str, cache: Path, symbols, outcomes: bool) -> list:
    rows = []
    for sym in symbols:
        d = V.load(sym, cache)
        weeks, months = A.week_table(d), month_table(d)
        for r in touches(sym, d, first, last):
            if r["depth"] == ZONE_TOP:
                r["poc"] = poc_in_zone(r, pocs_before(r["t"], weeks, months))
            if outcomes:
                r["outcome"] = race(d, r)
                if r["depth"] == ZONE_TOP:
                    t = zone_trade(d, r)
                    r.update({} if t is None else t)
            rows.append(r)
    return rows


# ---------------------------------------------------------------------------
# Statistics: months are the unit
# ---------------------------------------------------------------------------

def decided(rows: list, depth: float) -> list:
    return [{**r, "turn": float(r["outcome"] == "turn")} for r in rows
            if r["depth"] == depth and r.get("outcome") in ("turn", "deeper")]


def zone_against_unnamed(rows: list, draws: int = V.DRAWS) -> dict:
    """The zone's share of turns minus the mean share at the unnamed depths, resampling months."""
    groups = {dep: decided(rows, dep) for dep in (ZONE_TOP,) + UNNAMED}
    months = sorted({r["day"] for g in groups.values() for r in g})
    at = {m: i for i, m in enumerate(months)}
    num, den = np.zeros((len(groups), len(months))), np.zeros((len(groups), len(months)))
    for k, g in enumerate(groups.values()):
        for r in g:
            num[k, at[r["day"]]] += r["turn"]
            den[k, at[r["day"]]] += 1

    def gap(n, m):
        share = n.sum(-1) / m.sum(-1)
        return share[..., 0] - share[..., 1:].mean(-1)

    rng = np.random.default_rng(V.RNG_SEED)
    sims = []
    for _ in range(0, draws, 500):
        idx = rng.integers(0, len(months), size=(500, len(months)))
        sims.append(gap(np.moveaxis(num[:, idx], 0, 1), np.moveaxis(den[:, idx], 0, 1)))
    sims = np.concatenate(sims)
    half = len(months) // 2
    return {"value": float(gap(num, den)), "low": float(np.nanpercentile(sims, 2.5)), "high": float(np.nanpercentile(sims, 97.5)),
            "first_half": float(gap(num[:, :half], den[:, :half])), "second_half": float(gap(num[:, half:], den[:, half:]))}


def bars(zone: dict, gap: dict, with_poc: dict, without: dict, poc_gap: dict, net: dict) -> dict:
    enough = lambda st, n=MIN_RACES, m=MIN_MONTHS: st.get("n", 0) >= n and st.get("days", 0) >= m
    halves = lambda st, x: min(st.get("first_half") or -9, st.get("second_half") or -9) > x
    r1 = {"events": enough(zone), "share": zone.get("value", 0) >= SHARE, "interval": zone.get("low", 0) > 0.5, "halves": halves(zone, 0.5)}
    r2 = {"events": enough(zone), "gap": gap["value"] >= EDGE, "interval": gap["low"] > 0, "halves": halves(gap, 0)}
    r3 = {"events": enough(with_poc, MIN_GROUP, MIN_GROUP_MONTHS) and enough(without, MIN_GROUP, MIN_GROUP_MONTHS),
          "gap": poc_gap["value"] >= EDGE, "interval": poc_gap["low"] > 0, "halves": halves(poc_gap, 0)}
    r4 = {"events": enough(net), "mean": net.get("value", -1) > 0, "interval": net.get("low", -1) > 0, "halves": halves(net, 0)}
    return {name: {"checks": c, "met": all(c.values())} for name, c in (("R1", r1), ("R2", r2), ("R3", r3), ("R4", r4))}


def per_month(rows: list) -> list:
    n: dict = {}
    for r in rows:
        n[r["day"]] = n.get(r["day"], 0) + 1
    return [n[m] for m in sorted(n)]


def shape(first: str, last: str, cache: Path = V.CACHE_DIR, symbols=SYMBOLS) -> dict:
    """Counts only: touches by depth, the zone's touches by coin, side and POC. No race or trade is scored."""
    rows = gather(first, last, cache, symbols, outcomes=False)
    zone = [r for r in rows if r["depth"] == ZONE_TOP]
    heights = np.array([r["height_pct"] for r in zone]) if zone else np.array([0.0])
    return {"period": [first, last], "candles_sha256": V.data_hash(symbols, cache),
            "legs": len({r["leg"] for r in rows}),
            "touches": {str(dep): sum(1 for r in rows if r["depth"] == dep) for dep in DEPTHS},
            "months": {str(dep): len({r["day"] for r in rows if r["depth"] == dep}) for dep in DEPTHS},
            "zone": {"touches": len(zone), "legs": len({r["leg"] for r in zone}),
                     "up_legs": sum(1 for r in zone if r["direction"] > 0), "down_legs": sum(1 for r in zone if r["direction"] < 0),
                     "poc_in_zone": sum(1 for r in zone if r["poc"]), "no_poc": sum(1 for r in zone if not r["poc"]),
                     "by_coin": {s: sum(1 for r in zone if r["sym"] == s) for s in symbols},
                     "leg_height_pct": {q: round(float(np.percentile(heights, q)) * 100, 1) for q in (10, 50, 90)},
                     "per_month": per_month(zone), "per_month_poc": per_month([r for r in zone if r["poc"]]),
                     "per_month_no_poc": per_month([r for r in zone if not r["poc"]])},
            "per_month_unnamed": per_month([r for r in rows if r["depth"] in UNNAMED])}


KEEP = ("n", "days", "value", "low", "high", "first_half", "second_half")
brief = lambda st: {k: st[k] for k in KEEP if k in st}


def run_study(first: str, last: str, cache: Path = V.CACHE_DIR, symbols=SYMBOLS, draws: int = V.DRAWS) -> dict:
    rows = gather(first, last, cache, symbols, outcomes=True)
    stat = lambda xs, key, n=draws: brief(V.ratio(xs, key, n))
    zone = decided(rows, ZONE_TOP)
    share = stat(zone, "turn")
    gap = zone_against_unnamed(rows, draws)
    yes, no = [r for r in zone if r["poc"]], [r for r in zone if not r["poc"]]
    with_poc, without = stat(yes, "turn"), stat(no, "turn")
    poc_gap = V.difference(yes, no, "turn", draws) if yes and no else {"value": 0, "low": 0, "high": 0, "first_half": 0, "second_half": 0}
    trades = [r for r in rows if r["depth"] == ZONE_TOP and "net" in r]
    net = stat(trades, "net")
    out = {"period": [first, last], "candles_sha256": V.data_hash(symbols, cache),
           "zone": share, "zone_minus_unnamed": gap, "with_poc": with_poc, "without_poc": without, "poc_gap": poc_gap,
           "trade_net": net, **bars(share, gap, with_poc, without, poc_gap, net)}
    quick = lambda xs, key: brief(V.ratio(xs, key, 2000))
    raced = [r for r in rows if r.get("outcome") is not None]
    out["reported"] = {
        "outcomes": {str(dep): {o: sum(1 for r in raced if r["depth"] == dep and r["outcome"] == o) for o in ("turn", "deeper", "tie", "none")}
                     for dep in DEPTHS},
        "by_depth": {str(dep): quick(decided(rows, dep), "turn") for dep in DEPTHS},
        "zone_by_side": {"up_legs": quick([r for r in zone if r["direction"] > 0], "turn"), "down_legs": quick([r for r in zone if r["direction"] < 0], "turn")},
        "zone_by_coin": {s: quick([r for r in zone if r["sym"] == s], "turn") for s in symbols},
        "zone_by_year": {y: quick([r for r in zone if V.iso(r["t"])[:4] == y], "turn") for y in sorted({V.iso(r["t"])[:4] for r in zone})},
        "trade": {"gross": stat(trades, "gross"), "r_multiple": quick(trades, "r"), "stopped": quick(trades, "stopped"),
                  "reached_extreme": quick(trades, "reached"),
                  "with_poc_net": quick([r for r in trades if r["poc"]], "net"), "without_poc_net": quick([r for r in trades if not r["poc"]], "net"),
                  "up_legs_net": quick([r for r in trades if r["direction"] > 0], "net"), "down_legs_net": quick([r for r in trades if r["direction"] < 0], "net"),
                  "btc_net": quick([r for r in trades if r["sym"] == "BTCUSDT"], "net")},
    }
    return out


def power(shape_json: dict, reps: int = 2000, spread: float = 0.15) -> dict:
    """How often each bar is met on made-up outcomes with this study's touches per month. Two cases for the
    touches of one month: independent, and all sharing one outcome (the coins moving as one); the truth is
    between. Trade returns spread by ``spread`` around their mean. Normal-approximation intervals."""
    rng = np.random.default_rng(V.RNG_SEED)
    z = shape_json["zone"]

    def summary(num, den):
        v = num.sum() / den.sum()
        se = np.sqrt(((num - v * den) ** 2).sum()) / den.sum()
        h = len(num) // 2
        return v, se, num[:h].sum() / den[:h].sum(), num[h:].sum() / den[h:].sum()

    per = np.array(z["per_month"], dtype=float)
    pa, pb = np.array(z["per_month_poc"], dtype=float), np.array(z["per_month_no_poc"], dtype=float)
    un = np.array(shape_json["per_month_unnamed"], dtype=float)
    out = {"spread": spread}
    for shared in (False, True):
        wins = (lambda n, p: (rng.random(len(n)) < p) * n) if shared else (lambda n, p: rng.binomial(n.astype(int), p).astype(float))
        rets = (lambda n, m: rng.normal(m, spread, len(n)) * n) if shared else (lambda n, m: rng.normal(m * n, spread * np.sqrt(n)))
        block = {"R1": {}, "R2": {}, "R3": {}, "R4": {}}
        for p in (0.50, 0.53, 0.55, 0.58, 0.60, 0.65):
            met = 0
            for _ in range(reps):
                v, se, a, b = summary(wins(per, p), per)
                met += v >= SHARE and v - 1.96 * se > 0.5 and min(a, b) > 0.5
            block["R1"][p] = round(met / reps, 3)
        for g in (0.0, 0.03, 0.05, 0.08, 0.10, 0.15):
            met2 = met3 = 0
            for _ in range(reps):
                v, se, a, b = summary(wins(per, 0.5 + g), per)
                w, se2, c, e = summary(wins(un, 0.5), un)
                met2 += v - w >= EDGE and v - w - 1.96 * np.hypot(se, se2) > 0 and min(a - c, b - e) > 0
                v, se, a, b = summary(wins(pa, 0.5 + g), pa)
                w, se2, c, e = summary(wins(pb, 0.5), pb)
                met3 += v - w >= EDGE and v - w - 1.96 * np.hypot(se, se2) > 0 and min(a - c, b - e) > 0
            block["R2"][g], block["R3"][g] = round(met2 / reps, 3), round(met3 / reps, 3)
        for mean in (0.0, 0.01, 0.02, 0.04):
            met = 0
            for _ in range(reps):
                v, se, a, b = summary(rets(per, mean), per)
                met += v > 0 and v - 1.96 * se > 0 and min(a, b) > 0
            block["R4"][mean] = round(met / reps, 3)
        out["one outcome a month" if shared else "independent"] = block
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("shape", "power", "run"):
        p = sub.add_parser(name)
        p.add_argument("--cache", type=Path, default=V.CACHE_DIR)
        p.add_argument("--out", type=Path)
        if name == "power":
            p.add_argument("--shape", type=Path, required=True)
        else:
            p.add_argument("--holdout", action="store_true", help="the held-out months instead of the in-sample period")
    a = ap.parse_args()
    if a.cmd == "power":
        res = power(json.loads(a.shape.read_text()))
    else:
        period = HOLDOUT if a.holdout else IN_SAMPLE
        res = shape(*period, cache=a.cache) if a.cmd == "shape" else run_study(*period, cache=a.cache)
    if a.out:
        a.out.write_text(json.dumps(res, indent=1, default=float))
    strip = lambda x: ({str(k): strip(v) for k, v in x.items() if not str(k).startswith("per_month")} if isinstance(x, dict) else x)
    json.dump(strip(res), sys.stdout, indent=1, default=float)
    print()


if __name__ == "__main__":
    main()
