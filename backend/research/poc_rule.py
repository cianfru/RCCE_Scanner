"""
The POC rule on swing profiles (docs/reviews/poc-rule-study.md, declared before running).

The owner's rule (17 November 2026): "if price goes below VAL, trade from POC. vice versa." On the profile of the
last finished swing, as the coin chart draws it (engines/auction_engine.swing_ranges): once a day has closed
under the swing's value area, sell at its POC if price climbs back to it; once a day has closed over the value
area, buy at its POC if price dips back to it. Does that pay?

Everything is replayed as it stood at each day's close: the swings confirmed by then, the pullbacks merged by
then, the profile of the swing that was then the last finished one. On the candles of the 80% rule study.

Run from backend/:

  python -m research.poc_rule shape [--holdout] [--out JSON]      (counts only: no trade is scored)
  python -m research.poc_rule power --shape JSON                   (the bars on made-up outcomes)
  python -m research.poc_rule run [--holdout] [--out JSON]
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

DAY, HOUR = V.DAY_MS, V.HOUR_MS
SYMBOLS = F.SYMBOLS                      # the 71 perpetuals of the retracement study
IN_SAMPLE, HOLDOUT = F.IN_SAMPLE, F.HOLDOUT
ORDER_DAYS = 30                          # an order rests at the POC for 30 days at most
TRADE_DAYS = 30                          # a trade is closed at the last price after 30 days
MIN_ROOM = 0.005                         # the POC is at least 0.5% from each edge of the value area
MIN_TRADES, MIN_MONTHS = 200, 30
MIN_SIDE, MIN_SIDE_MONTHS = 100, 20


def hourly(d: dict) -> dict:
    """Hourly candles from the 5-minute ones: what the chart's profiles are built from."""
    hours, start = np.unique(d["ts"] // HOUR, return_index=True)
    return {"ts": hours * HOUR, "high": np.maximum.reduceat(d["high"], start), "low": np.minimum.reduceat(d["low"], start),
            "volume": np.add.reduceat(d["volume"], start)}


def structure(piv: list, dd: dict, i: int, known: int) -> list:
    """The chart's swing points at the close of day i: the first ``known`` swings (those confirmed by then), with
    the price furthest from the last one as the running move's reach, and without the pullbacks that did not end
    a move (engines/auction_engine.merge_moves). The running move's reach itself is left out."""
    pts = piv[:known]
    if not pts:
        return []
    kind, _, day, _ = pts[-1]
    if day + 1 > i:
        return ae.merge_moves(pts)
    j = day + 1 + int(np.argmax(dd["high"][day + 1:i + 1]) if kind == "L" else np.argmin(dd["low"][day + 1:i + 1]))
    tail = ("H", float(dd["high"][j]), j, j) if kind == "L" else ("L", float(dd["low"][j]), j, j)
    return ae.merge_moves(pts + [tail])[:-1]


def move_levels(hr: dict, dd: dict, a: tuple, b: tuple, price: float):
    """(POC, VAH, VAL) of the move from swing a to swing b, from the hourly candles between the hour of a's
    extreme and the hour of b's, as the chart profiles it. None without candles."""
    def anchor(p):
        i0, i1 = np.searchsorted(hr["ts"], [dd["day"][p[2]], dd["day"][p[2]] + DAY])
        if i1 <= i0:
            return None
        return int(i0 + (np.argmax(hr["high"][i0:i1]) if p[0] == "H" else np.argmin(hr["low"][i0:i1])))
    ia, ib = anchor(a), anchor(b)
    if ia is None or ib is None or ib <= ia:
        return None
    h, l, v = hr["high"][ia:ib + 1], hr["low"][ia:ib + 1], hr["volume"][ia:ib + 1]
    if not v.sum() > 0:
        return None
    return ae.session_levels(h, l, v, ae.nice_step(price * ae.STEP_FRACTION["swing"]))


def entries(sym: str, d: dict, first: str, last: str) -> tuple:
    """(rows, counts). One row per order filled.

    At each day's close: the last finished move and its profile. The first close under its VAL places a sell order
    at its POC; the first close over its VAH a buy order at its POC (one order per move and side, when the POC is
    MIN_ROOM from both edges, on break days from ``first`` to ``last``). The order rests from the next day, for
    ORDER_DAYS at most and while that move is still the last finished one; it fills in the first 5-minute candle
    whose range holds the POC. The stop is the far edge of the value area, the exit the edge price broke."""
    dd, hr = F.daily(d), hourly(d)
    piv = ae.swings(dd["high"], dd["low"], dd["atr"])
    first_ms, last_ms = V._ms(first), V._ms(last) + DAY
    rows, counts = [], {"moves": 0, "orders": 0}
    levels, used, order = {}, set(), None
    known, seen, merged = 0, None, []
    for i in range(len(dd["day"]) - 1):
        while known < len(piv) and piv[known][3] <= i:
            known += 1
        if not known:
            continue
        last_p = piv[known - 1]
        reach = (float(dd["high"][last_p[2] + 1:i + 1].max()) if last_p[0] == "L" else float(dd["low"][last_p[2] + 1:i + 1].min())) if last_p[2] + 1 <= i else None
        if (known, reach) != seen:                           # the structure only changes with a new swing or a new reach
            seen, merged = (known, reach), structure(piv, dd, i, known)
        if len(merged) < 2:
            order = None
            continue
        a, b = merged[-2], merged[-1]
        key = (a[2], b[2])
        if key not in levels:
            levels[key] = move_levels(hr, dd, a, b, float(dd["close"][i]))
            counts["moves"] += levels[key] is not None
        lv = levels[key]
        if order and (order["key"] != key or i >= order["placed"] + ORDER_DAYS):
            order = None
        if lv is not None and order is None and first_ms <= dd["day"][i] < last_ms:
            poc, vah, val = lv
            close = float(dd["close"][i])
            side = -1 if close < val else 1 if close > vah else 0
            if side and min(poc - val, vah - poc) / poc >= MIN_ROOM and (key, side) not in used:
                used.add((key, side))
                counts["orders"] += 1
                order = {"key": key, "side": side, "poc": poc, "stop": vah if side < 0 else val, "target": val if side < 0 else vah,
                         "placed": i, "direction": 1 if a[0] == "L" else -1}
        if order:
            j0, j1 = int(dd["start"][i + 1]), int(dd["stop"][i + 1])
            off = A.first_touch(d, j0, j1, order["poc"])
            if off is not None:
                g = j0 + off
                t = int(d["ts"][g])
                risk, reward = abs(order["stop"] - order["poc"]) / order["poc"], abs(order["target"] - order["poc"]) / order["poc"]
                rows.append({"sym": sym, "side": order["side"], "direction": order["direction"], "g": g, "t": t,
                             "day": int(ae.session_starts([t], "month")[0]),      # months are the unit
                             "entry": float(order["poc"]), "stop": float(order["stop"]), "target": float(order["target"]),
                             "risk": risk, "reward": reward, "walk": risk / (risk + reward),
                             "wait": i + 1 - order["placed"]})
                order = None
    return rows, counts


def score(d: dict, row: dict):
    """The trade: in at the POC, out at the stop, at the target, or after TRADE_DAYS at the last price (the stop
    wins when one candle holds both). Net of 10 bps a side. None when the candles end before the trade can."""
    end = row["t"] + TRADE_DAYS * DAY
    if d["ts"][-1] < end - DAY:
        return None
    return A.trade(d, row["g"] + 1, int(np.searchsorted(d["ts"], end)), row["side"], row["entry"], row["stop"], row["target"])


def gather(first: str, last: str, cache: Path, symbols, outcomes: bool) -> tuple:
    rows, counts = [], {"moves": 0, "orders": 0}
    for sym in symbols:
        d = V.load(sym, cache)
        mine, c = entries(sym, d, first, last)
        counts = {k: counts[k] + c[k] for k in counts}
        for r in mine:
            if outcomes:
                t = score(d, r)
                r.update({} if t is None else t)
            rows.append(r)
    return rows, counts


def per_month(rows: list) -> list:
    n: dict = {}
    for r in rows:
        n[r["day"]] = n.get(r["day"], 0) + 1
    return [n[m] for m in sorted(n)]


def shape(first: str, last: str, cache: Path = V.CACHE_DIR, symbols=SYMBOLS) -> dict:
    """Counts only: moves, orders placed, orders filled by side, by month and by coin, and how far the POC is from
    the stop and from the exit. No trade is scored."""
    rows, counts = gather(first, last, cache, symbols, outcomes=False)
    pct = lambda key: {q: round(float(np.percentile([r[key] for r in rows], q)) * 100, 2) for q in (10, 50, 90)} if rows else {}
    return {"period": [first, last], "candles_sha256": V.data_hash(symbols, cache), **counts,
            "filled": len(rows), "sells": sum(r["side"] < 0 for r in rows), "buys": sum(r["side"] > 0 for r in rows),
            "months": len({r["day"] for r in rows}), "per_month": per_month(rows),
            "per_month_sells": per_month([r for r in rows if r["side"] < 0]), "per_month_buys": per_month([r for r in rows if r["side"] > 0]),
            "by_coin": {s: sum(r["sym"] == s for r in rows) for s in symbols},
            "risk_pct": pct("risk"), "reward_pct": pct("reward"),
            "walk_share": round(float(np.mean([r["walk"] for r in rows])), 3) if rows else None,
            "wait_days": {q: float(np.percentile([r["wait"] for r in rows], q)) for q in (10, 50, 90)} if rows else {}}


KEEP = ("n", "days", "value", "low", "high", "first_half", "second_half")
brief = lambda st: {k: st[k] for k in KEEP if k in st}


def bars(both: dict, sells: dict, buys: dict) -> dict:
    """Each row: enough trades over enough months, a mean net return above 0 with its 95% interval above 0, and
    above 0 in each half."""
    def row(st, n, m):
        c = {"events": st.get("n", 0) >= n and st.get("days", 0) >= m, "mean": st.get("value", -1) > 0, "interval": st.get("low", -1) > 0,
             "halves": min(st.get("first_half") or -9, st.get("second_half") or -9) > 0}
        return {"checks": c, "met": all(c.values()), "confirms": st.get("value", -1) > 0}
    return {"R1": row(both, MIN_TRADES, MIN_MONTHS), "R2": row(sells, MIN_SIDE, MIN_SIDE_MONTHS), "R3": row(buys, MIN_SIDE, MIN_SIDE_MONTHS)}


def run_study(first: str, last: str, cache: Path = V.CACHE_DIR, symbols=SYMBOLS, draws: int = V.DRAWS) -> dict:
    rows, counts = gather(first, last, cache, symbols, outcomes=True)
    trades = [r for r in rows if "net" in r]
    stat = lambda xs, key, n=draws: brief(V.ratio(xs, key, n))
    quick = lambda xs, key: brief(V.ratio(xs, key, 2000))
    sells, buys = [r for r in trades if r["side"] < 0], [r for r in trades if r["side"] > 0]
    net, net_s, net_b = stat(trades, "net"), stat(sells, "net"), stat(buys, "net")
    decided = [{**r, "won": float(r["reached"])} for r in trades if r["reached"] or r["stopped"]]
    out = {"period": [first, last], "candles_sha256": V.data_hash(symbols, cache), **counts, "filled": len(rows),
           "net": net, "net_sells": net_s, "net_buys": net_b, **bars(net, net_s, net_b)}
    out["reported"] = {
        "gross": stat(trades, "gross"), "r_multiple": quick(trades, "r"),
        "stopped": quick(trades, "stopped"), "reached_exit": quick(trades, "reached"),
        "timed_out": quick([{**r, "late": float(not (r["reached"] or r["stopped"]))} for r in trades], "late"),
        "exit_first_of_decided": quick(decided, "won"), "walk_share_of_decided": quick(decided, "walk"),
        "gross_sells": quick(sells, "gross"), "gross_buys": quick(buys, "gross"),
        "after_a_rise_net": quick([r for r in trades if r["direction"] > 0], "net"),
        "after_a_fall_net": quick([r for r in trades if r["direction"] < 0], "net"),
        "with_the_move_net": quick([r for r in trades if r["side"] == r["direction"]], "net"),
        "against_the_move_net": quick([r for r in trades if r["side"] != r["direction"]], "net"),
        "btc_net": quick([r for r in trades if r["sym"] == "BTCUSDT"], "net"),
        "by_year": {y: quick([r for r in trades if V.iso(r["t"])[:4] == y], "net") for y in sorted({V.iso(r["t"])[:4] for r in trades})},
        "risk_pct_median": round(float(np.median([r["risk"] for r in trades])) * 100, 2) if trades else None,
        "reward_pct_median": round(float(np.median([r["reward"] for r in trades])) * 100, 2) if trades else None,
    }
    return out


def power(shape_json: dict, reps: int = 2000) -> dict:
    """How often each bar is met on made-up trades with this study's fills per month. A trade's return spreads
    around its mean by the size of a typical win or loss (the root of the median distance to the exit times the
    median distance to the stop). Two cases for the trades of one month: independent, and all sharing one
    outcome (the coins moving as one); the truth is between. Normal-approximation intervals."""
    rng = np.random.default_rng(V.RNG_SEED)
    spread = float(np.sqrt(shape_json["risk_pct"]["50"] * shape_json["reward_pct"]["50"])) / 100

    def summary(num, den):
        v = num.sum() / den.sum()
        se = np.sqrt(((num - v * den) ** 2).sum()) / den.sum()
        h = len(num) // 2
        return v, se, num[:h].sum() / den[:h].sum(), num[h:].sum() / den[h:].sum()

    out = {"spread": round(spread, 4)}
    for shared in (False, True):
        rets = (lambda n, m: rng.normal(m, spread, len(n)) * n) if shared else (lambda n, m: rng.normal(m * n, spread * np.sqrt(n)))
        block = {}
        for name, key, need_n, need_m in (("R1", "per_month", MIN_TRADES, MIN_MONTHS), ("R2", "per_month_sells", MIN_SIDE, MIN_SIDE_MONTHS),
                                          ("R3", "per_month_buys", MIN_SIDE, MIN_SIDE_MONTHS)):
            per = np.array(shape_json[key], dtype=float)
            enough = per.sum() >= need_n and len(per) >= need_m
            block[name] = {}
            for mean in (0.0, 0.005, 0.01, 0.02):
                met = 0
                for _ in range(reps):
                    v, se, a, b = summary(rets(per, mean), per)
                    met += enough and v > 0 and v - 1.96 * se > 0 and min(a, b) > 0
                block[name][str(mean)] = round(met / reps, 3)
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
