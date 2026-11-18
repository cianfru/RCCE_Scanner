"""
The entry triggers of the method's cheat sheets, on the swing levels the coin chart draws
(docs/reviews/entry-trigger-study.md, declared before running).

The levels are the chart's dotted lines: each swing high and low of its structure, a level until price trades
beyond it (engines/auction_engine.swing_levels). The sheets do not trade the touch. Once price has traded
through a level they wait for a trigger, and these are the ones not tested here before:

  R1  the 5-minute structure changes: a pullback, a lower high, then a close under the pullback low and back
      inside the level. Trade back into the range.
  R2  the 3rd touch: after a sweep, price leaves the level and comes back to it. A resting order at its price.
  R3  "when not to enter": R1's trades where open interest rose on the retest, against the rest.
  R4  R1's trades with a CVD divergence at the retest, against the rest.
  B   the plain fade at the close of the hour that closed back inside (reported, never deciding: what S4
      tested on the previous day's high and low).

Mirrored at swing lows. On Binance's 5-minute candles of 71 perpetuals (the retracement study's).

Run from backend/:

  python -m research.entry_triggers shape [--holdout] [--out JSON]      (counts only: no trade is scored)
  python -m research.entry_triggers power --shape JSON                   (the bars on made-up outcomes)
  python -m research.entry_triggers run [--holdout] [--out JSON]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from engines import auction_engine as ae
from research import auction_studies as A
from research import fib_zone as F
from research import value_area_rule as V

DAY, HOUR, BAR = V.DAY_MS, V.HOUR_MS, V.BAR_MS
SYMBOLS = F.SYMBOLS                      # the 71 perpetuals of the retracement study
IN_SAMPLE, HOLDOUT = F.IN_SAMPLE, F.HOLDOUT
TURN = 3.0                               # a 5-minute swing: price has come back 3 average 5-minute ranges from it
UNIT_BARS = 288                          # ... the average range of the 288 five-minute candles (a day) before the take
WINDOW_MS = ae.SWEEP_HOURS * HOUR        # a trigger has the 72 hours a sweep has
TRADE_DAYS = 14                          # a trade is closed at the last price after 14 days
MIN_ROOM = 0.005                         # the range's POC is at least 0.5% beyond the entry
GAP = A.GAP                              # R3, R4: one group's mean net return over the other's, at least 0.10%
MIN_TRADES, MIN_MONTHS = 200, 30
MIN_GROUP, MIN_GROUP_MONTHS = 100, 20
ROWS = ("R1", "R2", "B")


def hourly(d: dict) -> dict:
    """Hourly candles from the 5-minute ones, as the chart's engine reads them."""
    hours, start = np.unique(d["ts"] // HOUR, return_index=True)
    stop = np.append(start[1:], len(d["ts"]))
    return {"timestamp": hours * HOUR, "open": d["open"][start], "high": np.maximum.reduceat(d["high"], start),
            "low": np.minimum.reduceat(d["low"], start), "close": d["close"][stop - 1], "volume": np.add.reduceat(d["volume"], start)}


# ---------------------------------------------------------------------------
# The triggers, written for a swing high (a swing low is passed mirrored: highs are -lows, lows are -highs)
# ---------------------------------------------------------------------------

def structure_change(hi, lo, cl, g0: int, end: int, level: float, unit: float):
    """The first 5-minute candle from g0 to end that closes under the pullback low and under the level, after a
    lower high. None without one.

    The high: the highest price since the take; a higher one starts everything after it again.
    The pullback low: the lowest low after the high, once price has bounced TURN units from it.
    The lower high: the highest high after the pullback low, once price has come back TURN units from it.
    Returns the candles of the entry, the high, the pullback low and the lower high, and the high's price."""
    turn = TURN * unit
    top, i_top = -np.inf, None
    low1 = i_low = i_cand = i_re = None
    cand, re, lower = np.inf, -np.inf, False
    for j in range(g0, end):
        if hi[j] > top:
            top, i_top = float(hi[j]), j
            low1 = i_low = i_cand = i_re = None
            cand, re, lower = np.inf, -np.inf, False
            continue
        if low1 is None:
            if lo[j] < cand:
                cand, i_cand = float(lo[j]), j
            if i_cand < j and hi[j] >= cand + turn:
                low1, i_low = cand, i_cand
                i_re = i_low + 1 + int(np.argmax(hi[i_low + 1:j + 1]))
                re = float(hi[i_re])
        elif not lower:
            if hi[j] > re:
                re, i_re = float(hi[j]), j
            if i_re < j and lo[j] <= re - turn:
                lower = True
        if lower and cl[j] < low1 and cl[j] < level:
            return {"entry": j, "top": i_top, "low": i_low, "retest": i_re, "extreme": top}
    return None


def third_touch(hi, lo, g0: int, end: int, level: float, extreme: float, unit: float):
    """After a sweep that closed back inside by candle g0: price moves TURN units away from the level, then a
    later candle comes back to it. Returns that candle and the candle of the low in between. None without one,
    or when price trades beyond the sweep's extreme before it has moved away (the sweep is undone)."""
    turn = TURN * unit
    cand, i_cand, away = np.inf, None, False
    for j in range(g0, end):
        if away and hi[j] >= level:
            return {"fill": j, "low": i_cand}
        if not away and hi[j] > extreme:
            return None
        if lo[j] < cand:
            cand, i_cand = float(lo[j]), j
        if cand <= level - turn:
            away = True
    return None


# ---------------------------------------------------------------------------
# The trades of one coin
# ---------------------------------------------------------------------------

def events(sym: str, d: dict, oi: dict | None, first: str, last: str) -> tuple:
    """(rows, counts): one row per trade of R1, R2 and B at the levels taken from ``first`` to ``last``.

    Each trade goes back into the range: short after a swing high was taken, long after a swing low. Its stop is
    one price row beyond the furthest price reached beyond the level, its exit the POC of the level's range (the
    hourly candles from the swing to the hour before the take). A trade whose POC is less than MIN_ROOM beyond
    the entry is not taken."""
    dd, hr = F.daily(d), hourly(d)
    levels = ae.swing_levels(hr, {"timestamp": dd["day"], "high": dd["high"], "low": dd["low"], "close": dd["close"]})
    first_ms, last_ms = V._ms(first), V._ms(last) + DAY
    ts = d["ts"]
    cvd = np.cumsum(2 * d["taker"] - d["volume"])
    spans = np.concatenate([[0.0], np.cumsum(d["high"] - d["low"])])
    rows = []
    counts = {"taken": 0, "swept": 0, "quick": 0, "broken": 0, **{f"no_room_{r}": 0 for r in ROWS}}
    for e in levels:
        if e["taken"] is None or not first_ms <= e["taken"] * 1000 < last_ms:
            continue
        t_take, s, level = e["taken"] * 1000, (1 if e["side"] == "high" else -1), e["price"]
        hi, lo, cl = (d["high"], d["low"], d["close"]) if s > 0 else (-d["low"], -d["high"], -d["close"])
        a, b = (int(x) for x in np.searchsorted(ts, [t_take, t_take + HOUR]))
        beyond = np.flatnonzero(hi[a:b] > s * level)
        i0, i1 = (int(x) for x in np.searchsorted(hr["timestamp"], [e["time"] * 1000, t_take]))
        if not beyond.size or a + int(beyond[0]) < UNIT_BARS or i1 <= i0 or not hr["volume"][i0:i1].sum() > 0:
            continue
        g0 = a + int(beyond[0])
        unit = float(spans[g0] - spans[g0 - UNIT_BARS]) / UNIT_BARS
        step = ae.nice_step(level * ae.STEP_FRACTION["swing"])
        poc = ae.session_levels(hr["high"][i0:i1], hr["low"][i0:i1], hr["volume"][i0:i1], step)[0]
        swept = e["back"] is not None
        hours = None if not swept else (e["back"] * 1000 - t_take) // HOUR
        counts["taken"] += 1
        counts["swept"] += swept
        counts["quick"] += bool(swept and hours <= 1)
        counts["broken"] += not swept
        read = lambda i: A.reading(oi, int(ts[i]) + BAR)        # open interest at a candle's close

        def add(row: str, g: int, entry: float, extreme: float, fill: bool, i_top: int, i_low: int, i_re: int):
            stop = s * (extreme + step)                          # extreme: mirrored for a low, as hi and lo are
            room, risk = s * (entry - poc) / entry, s * (stop - entry) / entry
            if room < MIN_ROOM or risk <= 0:
                counts[f"no_room_{row}"] += 1
                return
            o_top, o_low, o_re = read(i_top), read(i_low), read(i_re)
            t = int(ts[g])
            rows.append({"sym": sym, "row": row, "side": -s, "g": g, "t": t, "day": int(ae.session_starts([t], "month")[0]),
                         "entry": float(entry), "stop": float(stop), "target": float(poc), "fill": fill,
                         "risk": float(risk), "reward": float(room), "walk": float(risk / (risk + room)),
                         "swept": swept, "quick": bool(swept and hours <= 1), "hours": None if hours is None else int(hours),
                         "wait": (t - t_take) / HOUR,
                         "div": bool(s * (cvd[i_re] - cvd[i_top]) > 0),
                         "oi_rose": None if o_low is None or o_re is None else bool(o_re > o_low),
                         "oi_fell_then_rose": None if None in (o_top, o_low, o_re) else bool(o_low < o_top and o_re > o_low)})

        end = int(np.searchsorted(ts, t_take + WINDOW_MS))
        sc = structure_change(hi, lo, cl, g0, end, s * level, unit)
        if sc:
            add("R1", sc["entry"], float(d["close"][sc["entry"]]), sc["extreme"], False, sc["top"], sc["low"], sc["retest"])
        if swept:
            back = e["back"] * 1000
            gb, end_b = (int(x) for x in np.searchsorted(ts, [back, back + WINDOW_MS]))
            i_top = g0 + int(np.argmax(hi[g0:gb]))               # the candle of the sweep's extreme
            # the plain fade's readings: across the sweep, from the candle before the take to the close back
            add("B", gb - 1, float(d["close"][gb - 1]), s * e["extreme"], False, i_top, g0 - 1, gb - 1)
            tt = third_touch(hi, lo, gb, end_b, s * level, s * e["extreme"], unit)
            if tt:
                add("R2", tt["fill"], level, s * e["extreme"], True, i_top, tt["low"], tt["fill"] - 1)
    return rows, counts


def score(d: dict, row: dict):
    """The trade: out at the stop, at the range's POC, or after TRADE_DAYS at the last price (the stop wins when
    one candle holds both). A resting order (R2) is stopped in the candle that filled it when that candle also
    reached the stop. Net of 10 bps a side. None when the candles end before the trade can."""
    end = row["t"] + TRADE_DAYS * DAY
    if d["ts"][-1] < end - DAY:
        return None
    g, side = row["g"], row["side"]
    if row["fill"] and ((d["high"][g] >= row["stop"]) if side < 0 else (d["low"][g] <= row["stop"])):
        gross = side * (row["stop"] - row["entry"]) / row["entry"]
        return {"gross": gross, "net": gross - V.COST, "r": -1.0, "stopped": True, "reached": False}
    return A.trade(d, g + 1, int(np.searchsorted(d["ts"], end)), side, row["entry"], row["stop"], row["target"])


def gather(first: str, last: str, cache: Path, symbols, outcomes: bool) -> tuple:
    rows, counts = [], {}
    for sym in symbols:
        d = V.load(sym, cache)
        mine, c = events(sym, d, A.load_oi(sym, cache), first, last)
        counts = {k: counts.get(k, 0) + v for k, v in c.items()}
        for r in mine:
            if outcomes:
                t = score(d, r)
                r.update({} if t is None else t)
            rows.append(r)
    return rows, counts


# ---------------------------------------------------------------------------
# Counts, bars, results
# ---------------------------------------------------------------------------

def per_month(rows: list) -> list:
    n: dict = {}
    for r in rows:
        n[r["day"]] = n.get(r["day"], 0) + 1
    return [n[m] for m in sorted(n)]


def pair_per_month(a: list, b: list) -> list:
    """[in a, in b] for each month either has a trade in."""
    months = sorted({r["day"] for r in a} | {r["day"] for r in b})
    return [[sum(r["day"] == m for r in a), sum(r["day"] == m for r in b)] for m in months]


def split(rows: list, key: str) -> tuple:
    """(rows where the flag is true, rows where it is false); rows without a reading are left out."""
    return [r for r in rows if r[key] is True], [r for r in rows if r[key] is False]


def shape(first: str, last: str, cache: Path = V.CACHE_DIR, symbols=SYMBOLS) -> dict:
    """Counts only: levels taken, swept and broken, the trades of each row by side, month and coin, how far the
    stop and the exit are, and how many of R1's trades have each reading. No trade is scored."""
    rows, counts = gather(first, last, cache, symbols, outcomes=False)
    pct = lambda xs, key: {q: round(float(np.percentile([r[key] for r in xs], q)) * 100, 2) for q in (10, 50, 90)} if xs else {}
    out = {"period": [first, last], "candles_sha256": V.data_hash(symbols, cache), **counts,
           "coins_with_open_interest": sum(A.load_oi(s, cache) is not None for s in symbols), "rows": {}}
    for name in ROWS:
        mine = [r for r in rows if r["row"] == name]
        out["rows"][name] = {"trades": len(mine), "shorts": sum(r["side"] < 0 for r in mine), "longs": sum(r["side"] > 0 for r in mine),
                             "months": len({r["day"] for r in mine}), "per_month": per_month(mine),
                             "coins": len({r["sym"] for r in mine}), "risk_pct": pct(mine, "risk"), "reward_pct": pct(mine, "reward"),
                             "walk_share": round(float(np.mean([r["walk"] for r in mine])), 3) if mine else None,
                             "wait_hours": {q: round(float(np.percentile([r["wait"] for r in mine], q)), 1) for q in (10, 50, 90)} if mine else {}}
    r1 = [r for r in rows if r["row"] == "R1"]
    rose, calm = split(r1, "oi_rose")
    div, plain = split(r1, "div")
    for key, a, b in (("oi_rose", calm, rose), ("div", div, plain)):     # first group: the one the sheets prefer
        out[key] = {"first": len(a), "second": len(b), "months_first": len({r["day"] for r in a}), "months_second": len({r["day"] for r in b}),
                    "per_month": pair_per_month(a, b)}
    return out


KEEP = ("n", "days", "value", "low", "high", "first_half", "second_half")
brief = lambda st: {k: st[k] for k in KEEP if k in st}


def trade_bar(st: dict) -> dict:
    """Enough trades over enough months, a mean net return above 0 with its 95% interval above 0, above 0 in each half."""
    c = {"events": st.get("n", 0) >= MIN_TRADES and st.get("days", 0) >= MIN_MONTHS, "mean": st.get("value", -1) > 0,
         "interval": st.get("low", -1) > 0, "halves": min(st.get("first_half") or -9, st.get("second_half") or -9) > 0}
    return {"checks": c, "met": all(c.values()), "confirms": st.get("value", -1) > 0}


def gap_bar(a: dict, b: dict, diff: dict) -> dict:
    """Enough trades in each group over enough months, a gap of GAP or more with its 95% interval above 0, above 0
    in each half."""
    c = {"events": min(a.get("n", 0), b.get("n", 0)) >= MIN_GROUP and min(a.get("days", 0), b.get("days", 0)) >= MIN_GROUP_MONTHS,
         "gap": diff.get("value", -1) >= GAP, "interval": diff.get("low", -1) > 0,
         "halves": min(diff.get("first_half", -9), diff.get("second_half", -9)) > 0}
    return {"checks": c, "met": all(c.values()), "confirms": diff.get("value", -1) > 0}


def run_study(first: str, last: str, cache: Path = V.CACHE_DIR, symbols=SYMBOLS, draws: int = V.DRAWS) -> dict:
    rows, counts = gather(first, last, cache, symbols, outcomes=True)
    trades = [r for r in rows if "net" in r]
    stat = lambda xs, key, n=draws: brief(V.ratio(xs, key, n))
    quick = lambda xs, key: brief(V.ratio(xs, key, 2000))
    of = lambda name: [r for r in trades if r["row"] == name]
    gap = lambda a, b: brief(V.difference(a, b, "net", draws)) if a and b else {}
    r1, r2, base = of("R1"), of("R2"), of("B")
    out = {"period": [first, last], "candles_sha256": V.data_hash(symbols, cache), **counts, "rows": {}}
    for name, mine in (("R1", r1), ("R2", r2)):
        net = stat(mine, "net")
        out["rows"][name] = {"net": net, **trade_bar(net)}
    rose, calm = split(r1, "oi_rose")
    div, plain = split(r1, "div")
    for name, a, b in (("R3", calm, rose), ("R4", div, plain)):      # R3: the trades the rule keeps minus those it skips
        sa, sb, diff = quick(a, "net"), quick(b, "net"), gap(a, b)
        out["rows"][name] = {"first": sa, "second": sb, "gap": diff, **gap_bar(sa, sb, diff)}

    def detail(mine: list) -> dict:
        decided = [{**r, "won": float(r["reached"])} for r in mine if r["reached"] or r["stopped"]]
        shorts, longs = [r for r in mine if r["side"] < 0], [r for r in mine if r["side"] > 0]
        return {"net": quick(mine, "net"), "gross": quick(mine, "gross"), "r_multiple": quick(mine, "r"),
                "stopped": quick(mine, "stopped"), "reached_exit": quick(mine, "reached"),
                "exit_first_of_decided": quick(decided, "won"), "walk_share_of_decided": quick(decided, "walk"),
                "shorts_net": quick(shorts, "net"), "longs_net": quick(longs, "net"),
                "quick_sweep_net": quick([r for r in mine if r["quick"]], "net"),
                "slow_sweep_net": quick([r for r in mine if r["swept"] and not r["quick"]], "net"),
                "not_swept_net": quick([r for r in mine if not r["swept"]], "net"),
                "btc_net": quick([r for r in mine if r["sym"] == "BTCUSDT"], "net"),
                "by_year": {y: quick([r for r in mine if V.iso(r["t"])[:4] == y], "net") for y in sorted({V.iso(r["t"])[:4] for r in mine})},
                "oi_rose_net": quick(split(mine, "oi_rose")[0], "net"), "oi_not_rose_net": quick(split(mine, "oi_rose")[1], "net"),
                "oi_fell_then_rose_net": quick(split(mine, "oi_fell_then_rose")[0], "net"),
                "divergence_net": quick(split(mine, "div")[0], "net"), "no_divergence_net": quick(split(mine, "div")[1], "net"),
                "risk_pct_median": round(float(np.median([r["risk"] for r in mine])) * 100, 2) if mine else None,
                "reward_pct_median": round(float(np.median([r["reward"] for r in mine])) * 100, 2) if mine else None}
    out["reported"] = {"R1": detail(r1), "R2": detail(r2), "B": detail(base)}
    return out


def power(shape_json: dict, reps: int = 2000) -> dict:
    """How often each bar is met on made-up trades with this study's trades per month. A trade's return spreads
    around its mean by the size of a typical win or loss (the root of the median distance to the exit times the
    median distance to the stop). Two cases for the trades of one month: independent, and all sharing one
    outcome (the coins moving as one; for R3 and R4, each group's trades of a month sharing one); the truth is
    between. Normal-approximation intervals."""
    rng = np.random.default_rng(V.RNG_SEED)

    def summary(num, den):
        v = num.sum() / den.sum()
        se = np.sqrt(((num - v * den) ** 2).sum()) / den.sum()
        h = len(num) // 2
        return v, se, num[:h].sum() / den[:h].sum(), num[h:].sum() / den[h:].sum()

    out = {}
    for shared in (False, True):
        block = {}
        for name in ("R1", "R2"):
            r = shape_json["rows"][name]
            per = np.array(r["per_month"], dtype=float)
            spread = float(np.sqrt(r["risk_pct"]["50"] * r["reward_pct"]["50"])) / 100
            draw = (lambda n, m: rng.normal(m, spread, len(n)) * n) if shared else (lambda n, m: rng.normal(m * n, spread * np.sqrt(n)))
            enough = per.sum() >= MIN_TRADES and len(per) >= MIN_MONTHS
            block[name] = {"spread": round(spread, 4)}
            for mean in (0.0, 0.002, 0.005, 0.01):
                met = 0
                for _ in range(reps):
                    v, se, a, b = summary(draw(per, mean), per)
                    met += enough and v > 0 and v - 1.96 * se > 0 and min(a, b) > 0
                block[name][str(mean)] = round(met / reps, 3)
        r1 = shape_json["rows"]["R1"]
        spread = float(np.sqrt(r1["risk_pct"]["50"] * r1["reward_pct"]["50"])) / 100
        for name, key in (("R3", "oi_rose"), ("R4", "div")):
            g = shape_json[key]
            per = np.array(g["per_month"], dtype=float).reshape(-1, 2)   # [first group, second group] a month
            na, nb = per[:, 0], per[:, 1]
            enough = min(g["first"], g["second"]) >= MIN_GROUP and min(g["months_first"], g["months_second"]) >= MIN_GROUP_MONTHS
            h = len(per) // 2
            sums = (lambda n, m: rng.normal(m, spread, len(n)) * n) if shared else (lambda n, m: rng.normal(m * n, spread * np.sqrt(n)))
            block[name] = {}
            for diff in (0.0, 0.002, 0.005, 0.01):
                met = 0
                for _ in range(reps if enough and h else 0):
                    sa, sb = sums(na, diff), sums(nb, 0.0)
                    ma, mb = sa.sum() / na.sum(), sb.sum() / nb.sum()
                    se = np.sqrt((((sa - ma * na) / na.sum() - (sb - mb * nb) / nb.sum()) ** 2).sum())
                    part = lambda sl: sa[sl].sum() / max(na[sl].sum(), 1) - sb[sl].sum() / max(nb[sl].sum(), 1)
                    met += ma - mb >= GAP and ma - mb - 1.96 * se > 0 and min(part(slice(0, h)), part(slice(h, None))) > 0
                block[name][str(diff)] = round(met / reps, 3)
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
        out = power(json.loads(a.shape.read_text()))
    else:
        first, last = HOLDOUT if a.holdout else IN_SAMPLE
        out = (shape if a.cmd == "shape" else run_study)(first, last, a.cache)
    text = json.dumps(out, indent=1)
    if a.out:
        a.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
