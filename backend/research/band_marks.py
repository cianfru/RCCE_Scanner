"""Band model marks: do the marks of tradingview/reflex_band_model.pine point the right way, more often than ordinary
days on the same coins? (docs/reviews/band-model-marks-study.md, declared before running.)

Everything that decides the result is fixed here and in the declaration before any outcome after a mark is computed:
the coins and the parts they are judged in, the script's rules on daily candles (its default settings), the horizon,
what "the right way" is for each mark, the chance it is compared with and the bars.

Run from backend/:
    python -m research.band_marks check     # data check and counts: coins, days, marks per kind (no outcomes)
    python -m research.band_marks run       # the study
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import urllib.error
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from research.stretch_tops import PRIMARY, SECONDARY, MAX_FILLED, band_mid, day_of, split as tops_split

# ---------------------------------------------------------------------------------------------------------- coins
SEEN = ("BTC", "ETH", "SOL")       # their marks were listed or shown on 9 November 2026: reported apart
START = "2017-01-01"
END = "2026-11-01"                 # exclusive bar-open bound: the 31 October 2026 close is the last
DAY_S = 86_400

# ---------------------------------------------------------------------------------------------------------- the script
# tradingview/reflex_band_model.pine's default settings, on daily candles (one bar a day).
PARAMS = dict(zone_lo=-0.3, zone_hi=0.8, stretch_line=1.6, speed_line=2.0, slope_days=28, turn_drop=0.5,
              turn_days=10, leg_level=1.2, leg_days=60, gap_days=30, speed_days=20, vol_days=365, norm_days=730,
              reclaim_days=60, min_loc_days=180, min_side=30, year=365, skip=30)

# The marks as the script draws them; +1 a mark to buy on (right way: a higher close after the horizon), -1 a mark
# to sell or stay out on (right way: a lower close).
KINDS = {
    "buy": ("Buy", +1),
    "take_profit": ("Take profit", -1),          # Exhausting or second leg: the one orange mark
    "cap_turn": ("Capitulation turn", +1),
    "reclaim": ("Reclaim", +1),
    "top_div": ("Top divergence", -1),
    "bot_div": ("Bottom divergence", +1),
    "lost": ("Lost the band", -1),
}
PARTS_OF = {"exh": ("Take profit: exhausting", -1), "leg": ("Take profit: second leg", -1)}   # reported only

# ---------------------------------------------------------------------------------------------------------- the test
HORIZON = 90                       # the right way: the close 90 days after the mark against the mark's close
SHORT = 30                         # reported: the close 30 days after, and the worst (best) close in those 30 days
TIMING_BEFORE = 30                 # reported: where the mark's close sits between the lowest and highest close
ERA_SPLIT = "2022-01-01"           # eras: marks before 2022, marks from 2022
BAR_MARKS = 30                     # bars, judged on the unseen coins pooled
BAR_MARGIN = 0.10
BAR_PART_MARKS = 5


# ---------------------------------------------------------------------------------------------------------- data
def fetch(coin: str) -> Optional[dict]:
    """Binance spot daily candles for COINUSDT (the public market-data mirror; the monthly archive for delisted
    pairs), through the repository's cached loader, on every day from the first to the last; a missing day takes the
    close before it as its high, low and close."""
    from backtest import binance_history as bh
    pair = f"{coin}USDT"
    data, source = None, "api"
    try:
        data = bh.load(pair, "1d", start=START, end=END)
    except urllib.error.HTTPError:
        data = None
    if data is None or len(data["close"]) == 0:
        data, source = bh.load(pair, "1d", start=START, end=END, archive=True), "archive"
    if data is None or len(data["close"]) == 0:
        return None
    by_day = {day_of(t): (float(h), float(lo), float(c))
              for t, h, lo, c in zip(data["timestamp"], data["high"], data["low"], data["close"])}
    days = np.arange(min(by_day), max(by_day) + 1)
    hi, lo, cl, filled, last = [], [], [], 0, None
    for d in days:
        if d in by_day:
            last = by_day[d]
            hi.append(last[0]); lo.append(last[1]); cl.append(last[2])
        else:
            filled += 1
            hi.append(last[2]); lo.append(last[2]); cl.append(last[2])
    return {"coin": coin, "days": days, "high": np.array(hi), "low": np.array(lo), "close": np.array(cl),
            "filled": filled, "source": source}


def digest(series: Dict[str, dict]) -> str:
    h = hashlib.sha256()
    for coin in sorted(series):
        s = series[coin]
        h.update(coin.encode())
        h.update(np.asarray(s["days"], dtype=np.int64).tobytes())
        for f in ("high", "low", "close"):
            h.update(np.round(np.asarray(s[f], dtype=float), 10).tobytes())
    return h.hexdigest()


def load_all(keep_all: bool = False) -> Dict[str, dict]:
    out = {}
    for coin in PRIMARY + SECONDARY:
        s = fetch(coin)
        if s is not None and (keep_all or s["filled"] <= MAX_FILLED):
            out[coin] = s
    return out


def parts() -> Dict[str, List[str]]:
    """The unseen coins in the two halves of the stretch-at-tops study (SOL, seen here, taken out of its half)."""
    cal, test = tops_split()
    return {"calibration": [c for c in cal if c not in SEEN], "test": [c for c in test if c not in SEEN]}


# ---------------------------------------------------------------------------------------------------------- the model
def _since(m: np.ndarray) -> np.ndarray:
    """Bars since m was last true (the bar itself 0); a large number before the first (Pine: na, never <=)."""
    out = np.full(len(m), 10 ** 9, dtype=np.int64)
    last = None
    for i, v in enumerate(m):
        if v:
            last = i
        if last is not None:
            out[i] = i - last
    return out


def _roll(f, x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(len(x)):
        w = x[max(0, i - k + 1): i + 1]
        w = w[np.isfinite(w)]
        if len(w):
            out[i] = f(w)
    return out


def model(days: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray, p: Optional[dict] = None) -> dict:
    """The script on daily candles: location, speed, the states and every mark, bar by bar as Pine runs it."""
    p = {**PARAMS, **(p or {})}
    days = np.asarray(days, dtype=np.int64)
    high, close = np.asarray(high, dtype=float), np.asarray(close, dtype=float)
    n = len(close)
    mid = band_mid(days, close)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.log(close / mid)
    # location: each side over the root mean square of the stretch on that side, over the last norm_days values
    loc = np.full(n, np.nan)
    q: deque = deque()
    su = sd = 0.0
    cu = cd = 0
    for i in range(n):
        x = s[i]
        if not np.isfinite(x):
            continue
        q.append(x)
        if x > 0:
            su += x * x; cu += 1
        elif x < 0:
            sd += x * x; cd += 1
        if len(q) > p["norm_days"]:
            o = q.popleft()
            if o > 0:
                su -= o * o; cu -= 1
            elif o < 0:
                sd -= o * o; cd -= 1
        r_all = math.sqrt(max(su + sd, 0.0) / len(q))
        r_up = math.sqrt(max(su, 0.0) / cu) if cu >= p["min_side"] else r_all
        r_dn = math.sqrt(max(sd, 0.0) / cd) if cd >= p["min_side"] else r_all
        if len(q) >= p["min_loc_days"]:
            loc[i] = x / r_up if x >= 0 else x / r_dn
    # speed: the last speed_days' log move over the daily volatility of the last vol_days, scaled to speed_days
    r1 = np.concatenate([[np.nan], np.diff(np.log(close))])
    speed = np.full(n, np.nan)
    nv, ns = p["vol_days"], p["speed_days"]
    if n > nv:
        sig = np.lib.stride_tricks.sliding_window_view(r1[1:], nv).std(axis=1)     # windows ending at nv .. n-1
        for j, i in enumerate(range(nv, n)):
            if sig[j] > 0 and i >= ns:
                speed[i] = math.log(close[i] / close[i - ns]) / (sig[j] * math.sqrt(ns))
    sl = p["slope_days"]
    rising = np.zeros(n, bool)
    rising[sl:] = mid[sl:] > mid[:-sl]
    with np.errstate(invalid="ignore"):
        in_zone = (loc >= p["zone_lo"]) & (loc <= p["zone_hi"])
        stretched = loc >= p["stretch_line"]
        deep = loc <= -p["stretch_line"]
        hot = stretched & (speed >= p["speed_line"])
        cold = deep & (speed <= -p["speed_line"])
    since_hot, since_cold = _since(hot), _since(cold)
    hi_loc, lo_loc = _roll(np.max, loc, p["turn_days"]), _roll(np.min, loc, p["turn_days"])
    with np.errstate(invalid="ignore"):
        exhausting = ~hot & (since_hot <= p["turn_days"]) & (loc <= hi_loc - p["turn_drop"])
        basing = ~cold & (since_cold <= p["turn_days"]) & (loc >= lo_loc + p["turn_drop"])
        lost = (close < mid) & ~rising
        above = close > mid
    yr, sk, line = p["year"], p["skip"], p["stretch_line"]
    top_div = np.zeros(n, bool)
    bot_div = np.zeros(n, bool)
    for i in range(yr - 1, n):
        if not np.isfinite(loc[i]):
            continue
        hot_back = hot[i - yr + 1: i - sk + 1].any()
        cold_back = cold[i - yr + 1: i - sk + 1].any()
        win = close[i - yr + 1: i + 1]
        if hot_back and close[i] >= win.max() and 0 < loc[i] < line:
            top_div[i] = True
        if cold_back and close[i] <= win.min() and -line < loc[i] < 0:
            bot_div[i] = True
    reclaim = np.zeros(n, bool)
    reclaim[1:] = (since_cold[1:] <= p["reclaim_days"]) & above[1:] & (close[:-1] <= mid[:-1])
    keys = ("buy", "exh", "leg", "cap_turn", "reclaim", "top_div", "bot_div", "lost")
    marks = {k: np.zeros(n, bool) for k in keys}
    last = {k: None for k in keys}
    last_top_cand = None
    armed = True
    gap = p["gap_days"]
    for i in range(n):
        prev = i - 1
        exh_start = exhausting[i] and not (i > 0 and exhausting[prev])
        base_start = basing[i] and not (i > 0 and basing[prev])
        lost_start = lost[i] and not (i > 0 and lost[prev])
        cross = i > 0 and np.isfinite(loc[i]) and np.isfinite(loc[prev]) and loc[i] > p["leg_level"] \
            and loc[prev] <= p["leg_level"]
        leg_cand = cross and last_top_cand is not None and i - last_top_cand <= p["leg_days"]
        cands = {"exh": exh_start, "cap_turn": base_start, "top_div": top_div[i], "bot_div": bot_div[i],
                 "leg": leg_cand, "lost": lost_start, "reclaim": reclaim[i]}
        for k, v in cands.items():
            marks[k][i] = bool(v) and (last[k] is None or i - last[k] > gap)
        turn_up = i > 0 and close[i] > high[prev]
        marks["buy"][i] = bool(in_zone[i] and rising[i] and turn_up and armed)
        for k, v in cands.items():
            if v:
                last[k] = i
        if top_div[i]:
            last_top_cand = i
        if marks["buy"][i]:
            armed = False
        if not in_zone[i]:
            armed = True
    marks["take_profit"] = marks["exh"] | marks["leg"]
    ready = np.isfinite(loc) & np.isfinite(speed) & (np.arange(n) >= yr - 1)
    return {"mid": mid, "loc": loc, "speed": speed, "rising": rising, "in_zone": in_zone, "hot": hot, "cold": cold,
            "eval_start": int(np.argmax(ready)) if ready.any() else None, **marks}


# ---------------------------------------------------------------------------------------------------------- outcomes
def eligible(n: int, eval_start: Optional[int]) -> range:
    """Days a mark is counted on: evaluation days with HORIZON days after them."""
    return range(0, 0) if eval_start is None else range(eval_start, n - HORIZON)


def outcome(close: np.ndarray, t: int, side: int) -> dict:
    c0 = close[t]
    r = close[t + HORIZON] / c0 - 1
    nxt = close[t + 1: t + SHORT + 1]
    w = close[max(0, t - TIMING_BEFORE): t + HORIZON + 1]
    span = w.max() - w.min()
    return {"r": float(r), "r_short": float(close[t + SHORT] / c0 - 1),
            "adverse": float((nxt.min() if side > 0 else nxt.max()) / c0 - 1),
            "timing": float((c0 - w.min()) / span) if span > 0 else 0.5,
            "right": bool(r > 0) if side > 0 else bool(r < 0)}


def _wmedian(values: np.ndarray, weights: np.ndarray) -> Optional[float]:
    if not len(values) or weights.sum() <= 0:
        return None
    o = np.argsort(values, kind="stable")
    v, w = values[o], weights[o]
    cw = np.cumsum(w)
    return float(v[int(np.searchsorted(cw, cw[-1] / 2.0))])


def summarize(rows: List[dict], days_by_coin: Dict[str, dict], side: int) -> dict:
    """Marks and their chance: each coin's eligible days in the same era, each weighted by that coin's marks in the
    era over its eligible days in the era (the expected result of putting each coin's marks on its days at random)."""
    out = {"marks": len(rows)}
    if not rows:
        return {**out, "right": None, "chance": None, "margin": None, "median": None, "chance_median": None,
                "median_short": None, "adverse": None, "timing": None}
    rate_w, w_tot, vals, wts = 0.0, 0.0, [], []
    groups: Dict[tuple, int] = {}
    for r in rows:
        groups[(r["coin"], r["era"])] = groups.get((r["coin"], r["era"]), 0) + 1
    for (coin, era), m in groups.items():
        ret = days_by_coin[coin][era]
        if not len(ret):
            continue
        right = (ret > 0) if side > 0 else (ret < 0)
        rate_w += m * float(right.mean())
        w_tot += m
        vals.append(ret)
        wts.append(np.full(len(ret), m / len(ret)))
    right_rate = float(np.mean([r["right"] for r in rows]))
    chance = rate_w / w_tot if w_tot else None
    return {**out, "right": right_rate, "chance": chance,
            "margin": None if chance is None else right_rate - chance,
            "median": float(np.median([r["r"] for r in rows])),
            "chance_median": _wmedian(np.concatenate(vals), np.concatenate(wts)) if vals else None,
            "median_short": float(np.median([r["r_short"] for r in rows])),
            "adverse": float(np.median([r["adverse"] for r in rows])),
            "timing": float(np.median([r["timing"] for r in rows]))}


def verdict(pooled: dict, by_part: Dict[str, dict], side: int) -> dict:
    """The bars: enough marks; the right way at least BAR_MARGIN more often than chance; the median return on the
    right side of chance's; and the right way more often than chance in every part (each with BAR_PART_MARKS)."""
    enough = pooled["marks"] >= BAR_MARKS
    margin = pooled["margin"] is not None and pooled["margin"] >= BAR_MARGIN - 1e-12
    med = pooled["median"] is not None and pooled["chance_median"] is not None and \
        (pooled["median"] > pooled["chance_median"] if side > 0 else pooled["median"] < pooled["chance_median"])
    each = {k: bool(v["marks"] >= BAR_PART_MARKS and v["margin"] is not None and v["margin"] > 0)
            for k, v in by_part.items()}
    return {"enough_marks": enough, "margin": margin, "median": med, "parts": each,
            "met": bool(enough and margin and med and all(each.values()))}


# ---------------------------------------------------------------------------------------------------------- runs
def _date(day: int) -> str:
    return datetime.fromtimestamp(int(day) * DAY_S, tz=timezone.utc).strftime("%Y-%m-%d")


_ERA_DAY = int(datetime.strptime(ERA_SPLIT, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) // DAY_S


def _era_of(day: int) -> str:
    return "to 2021" if day < _ERA_DAY else "from 2022"


def collect(series: Dict[str, dict], coins: List[str], m: Dict[str, dict]):
    """Every counted mark of every kind on the coins (with its outcome), and each coin's eligible days' returns by
    era."""
    marks = {k: [] for k in list(KINDS) + list(PARTS_OF)}
    days_by_coin: Dict[str, dict] = {}
    for c in coins:
        s, mc = series[c], m[c]
        el = eligible(len(s["close"]), mc["eval_start"])
        ret = {"to 2021": [], "from 2022": []}
        for t in el:
            ret[_era_of(s["days"][t])].append(s["close"][t + HORIZON] / s["close"][t] - 1)
        days_by_coin[c] = {k: np.array(v) for k, v in ret.items()}
        for k in marks:
            side = (KINDS.get(k) or PARTS_OF[k])[1]
            for t in el:
                if mc[k][t]:
                    marks[k].append({"coin": c, "t": t, "day": _date(s["days"][t]), "era": _era_of(s["days"][t]),
                                     "close": float(s["close"][t]), **outcome(s["close"], t, side)})
    return marks, days_by_coin


def check() -> dict:
    """Data and counts only: coins, span, filled days, evaluation days and counted marks per kind (no outcomes)."""
    series = load_all(keep_all=True)
    used = {c: s for c, s in series.items() if s["filled"] <= MAX_FILLED}
    pt = parts()
    rows, counts = {}, {"unseen": {k: 0 for k in KINDS}, "seen": {k: 0 for k in KINDS}}
    for coin, s in series.items():
        mc = model(s["days"], s["high"], s["low"], s["close"])
        el = eligible(len(s["close"]), mc["eval_start"])
        group = "left out" if coin not in used else "seen" if coin in SEEN else \
            "calibration" if coin in pt["calibration"] else "test"
        n_marks = {k: int(sum(mc[k][t] for t in el)) for k in KINDS}
        if group in ("calibration", "test", "seen"):
            g = "seen" if group == "seen" else "unseen"
            for k in KINDS:
                counts[g][k] += n_marks[k]
        es = mc["eval_start"]
        rows[coin] = {"group": group, "source": s["source"], "first": _date(s["days"][0]),
                      "last": _date(s["days"][-1]), "filled": s["filled"],
                      "eval_from": _date(s["days"][es]) if es is not None else None, "counted_days": len(el),
                      "marks": n_marks}
    return {"sha256": digest(used), "coins": len(used), "left_out": sorted(set(series) - set(used)),
            "missing": [c for c in PRIMARY + SECONDARY if c not in series], "parts": pt,
            "counted_days": {g: sum(r["counted_days"] for r in rows.values() if r["group"] == g)
                             for g in ("calibration", "test", "seen")},
            "marks": counts, "per_coin": rows}


def run() -> dict:
    series = load_all()
    pt = parts()
    unseen = [c for c in pt["calibration"] + pt["test"] if c in series]
    seen = [c for c in SEEN if c in series]
    m = {c: model(s["days"], s["high"], s["low"], s["close"]) for c, s in series.items()}
    marks, days_by_coin = collect(series, unseen, m)
    smarks, sdays = collect(series, seen, m)
    out: Dict[str, dict] = {"sha256": digest(series), "coins": {"unseen": len(unseen), "seen": seen}, "kinds": {}}
    for k, (name, side) in list(KINDS.items()) + list(PARTS_OF.items()):
        rows = marks[k]
        pooled = summarize(rows, days_by_coin, side)
        by_part = {}
        for half in ("calibration", "test"):
            by_part[half] = summarize([r for r in rows if r["coin"] in pt[half]], days_by_coin, side)
        for era in ("to 2021", "from 2022"):
            by_part[era] = summarize([r for r in rows if r["era"] == era], days_by_coin, side)
        entry = {"name": name, "side": side, "unseen": pooled, "parts": by_part,
                 "seen": summarize(smarks[k], sdays, side)}
        if k in KINDS:
            entry["verdict"] = verdict(pooled, by_part, side)
        if k in ("top_div", "bot_div", "cap_turn", "reclaim"):
            entry["seen_list"] = [{kk: r[kk] for kk in ("coin", "day", "close", "r", "right")} for r in smarks[k]]
        out["kinds"][k] = entry
    return out


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("check", "run"))
    args = ap.parse_args(argv)
    out = check() if args.cmd == "check" else run()
    json.dump(out, sys.stdout, indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)
    print()


if __name__ == "__main__":
    main()
