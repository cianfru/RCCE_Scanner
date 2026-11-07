"""Stretch at tops: which scaling of the distance from the weekly band marks tops most cleanly
(docs/reviews/stretch-tops-study.md, declared before running).

Everything that decides the result is fixed here and in the declaration before any reading at a top is computed:
the coins and their split, the band, the three scalings (A, B, C), the divergence mark (D), the rule for a top, the
hit window, the episodes, the guides and the bars.

Run from backend/:
    python -m research.stretch_tops check     # data check and counts: coins, days, gaps, tops per half (no readings)
    python -m research.stretch_tops run       # the study
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import urllib.error
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------------------------------------- coins
PRIMARY = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "DOT", "LINK"]
# The 30-coin secondary set of the earlier studies (top Binance quote volume before their first window, listed
# before February 2020; later-delisted or renamed coins kept).
SECONDARY = ["FTM", "MATIC", "FTT", "ATOM", "LTC", "ETC", "TRX", "EOS", "VET", "THETA", "ALGO", "OMG", "XTZ", "CHZ",
             "BCH", "ONE", "CELR", "IOTX", "KAVA", "DENT", "XLM", "BTT", "IOST", "HBAR", "IOTA", "FET", "NEO", "WIN",
             "HOT", "QTUM"]
SEEN = ("BTC", "ETH")              # their tops were looked at on 7 November 2026: reported apart, in neither half

# ---------------------------------------------------------------------------------------------------------- rules
START = "2017-01-01"
END = "2026-11-01"                 # exclusive bar-open bound: the 31 October 2026 close is the last
DAY_S = 86_400
SMA_WEEKS, EMA_WEEKS = 20, 21      # the band (the scanner's heatmap engine and the TradingView script)
RMS_DAYS = 730                     # A: the usual distance over the last two years
MIN_HISTORY = 365                  # evaluation starts once a year of stretch exists (all of A, B, C defined)
VOL_DAYS = 730                     # C: daily volatility over the last two years (a year at least)
GUIDE_Q = 0.95                     # each guide: the 95th percentile of its values on the calibration coins' days
TOP_LOOKBACK = 180                 # a top is the highest close of the 180 days before it, itself included...
FALL = 0.40                        # ...after which the close falls 40% or more...
FALL_WITHIN = 365                  # ...within 365 days, before any close above it
HIT_DAYS = 14                      # a top is caught by an alarm on the top or in the 14 days before
EPISODE_GAP = 7                    # alarm days with up to 7 days between them form one episode
DIV_HIGH = 365                     # D: a new 365-day closing high...
DIV_SKIP = 30                      # ...with an earlier stretched day 30 to 365 days back, and a lower reading now
BAR_TOPS = 25                      # bars, judged on the test coins
BAR_HIT = 0.10
BAR_PRECISION = 0.05
BAR_ALARMS_SCALE = 1.25           # question 1: no more than 1.25 times A's alarm days
BAR_ALARMS = 1.5                   # question 2: no more than 1.5 times the scale's alarm days
MAX_FILLED = 30                    # a coin with more days filled than this is left out (FTT: trading halted after FTX)
SHIFTS, SEED = 200, 20261107       # chance: each coin's alarm days shifted at random in time (reported only)
CANDIDATES = ("A", "B", "C")
REFERENCE = "E"                    # the engine's z today (reported only)


def split(coins: Optional[List[str]] = None) -> Tuple[List[str], List[str]]:
    """Calibration and test halves: the coins other than the seen two, in alphabetical order, alternately."""
    rest = sorted(c for c in (coins or PRIMARY + SECONDARY) if c not in SEEN)
    return rest[0::2], rest[1::2]


# ---------------------------------------------------------------------------------------------------------- data
def day_of(ts_ms: float) -> int:
    return int(ts_ms // 1000 // DAY_S)


def on_grid(days: List[int], closes: List[float]) -> Tuple[np.ndarray, np.ndarray, int]:
    """Closes on every day from the first to the last; a missing day takes the close before it. Returns the days,
    the closes and how many days were filled."""
    by_day = dict(zip(days, closes))
    grid = np.arange(min(by_day), max(by_day) + 1)
    out, last, filled = [], None, 0
    for d in grid:
        if d in by_day:
            last = by_day[d]
        else:
            filled += 1
        out.append(last)
    return grid, np.array(out, dtype=float), filled


def fetch(coin: str) -> Optional[dict]:
    """Binance spot daily closes for COINUSDT (the public market-data mirror; the monthly archive for delisted
    pairs), through the repository's cached loader."""
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
    days, closes, filled = on_grid([day_of(t) for t in data["timestamp"]], list(data["close"]))
    return {"coin": coin, "days": days, "close": closes, "filled": filled, "source": source}


def digest(series: Dict[str, dict]) -> str:
    h = hashlib.sha256()
    for coin in sorted(series):
        s = series[coin]
        h.update(coin.encode())
        h.update(np.asarray(s["days"], dtype=np.int64).tobytes())
        h.update(np.round(np.asarray(s["close"], dtype=float), 10).tobytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------------------- band
def band_mid(days: np.ndarray, close: np.ndarray, sma_n: int = SMA_WEEKS, ema_n: int = EMA_WEEKS) -> np.ndarray:
    """The band's mid each day: the SMA and EMA of weekly closes (Thursday weeks: day 0, 1 January 1970, was a
    Thursday), the week under way counted at the day's close; the EMA seeded with the SMA of its first weeks."""
    k = 2.0 / (ema_n + 1)
    weeks: List[float] = []
    ema_done = None
    mid = np.full(len(close), np.nan)
    for i in range(len(close)):
        if i > 0 and days[i] // 7 != days[i - 1] // 7:
            weeks.append(close[i - 1])
            n = len(weeks)
            if n == ema_n:
                ema_done = sum(weeks) / n
            elif n > ema_n:
                ema_done = close[i - 1] * k + ema_done * (1 - k)
        n = len(weeks)
        if n < sma_n - 1 or n < ema_n - 1:
            continue
        sma = (close[i] + sum(weeks[n - (sma_n - 1):])) / sma_n
        ema = close[i] * k + ema_done * (1 - k) if n >= ema_n else (sum(weeks) + close[i]) / ema_n
        mid[i] = (sma + ema) / 2
    return mid


def _rolling_mean(x: np.ndarray, window: Optional[int]) -> np.ndarray:
    """Mean of the finite values among the last `window` (all of them when None), the day itself included."""
    ok = np.isfinite(x)
    cs = np.cumsum(np.where(ok, x, 0.0))
    cn = np.cumsum(ok.astype(float))
    if window is not None:
        cs = cs - np.concatenate([np.zeros(window), cs[:-window]])[: len(x)]
        cn = cn - np.concatenate([np.zeros(window), cn[:-window]])[: len(x)]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cn > 0, cs / np.maximum(cn, 1), np.nan)


def _count(x: np.ndarray) -> np.ndarray:
    return np.cumsum(np.isfinite(x).astype(int))


def measures(days: np.ndarray, close: np.ndarray) -> dict:
    """The stretch and the three scalings, each from data up to the day only; the engine's z for reference."""
    mid = band_mid(days, close)
    s = np.log(close / mid)                                    # nan before the band exists
    sq = s * s
    rms_a = np.sqrt(_rolling_mean(sq, RMS_DAYS))
    rms_b = np.sqrt(_rolling_mean(sq, None))
    r = np.concatenate([[np.nan], np.diff(np.log(close))])
    vol = np.sqrt(np.maximum(_rolling_mean(r * r, VOL_DAYS) - _rolling_mean(r, VOL_DAYS) ** 2, 0.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = {"stretch": s, "pct": 100 * (close / mid - 1),
               "A": np.where(rms_a > 0, s / rms_a, np.nan),
               "B": np.where(rms_b > 0, s / rms_b, np.nan),
               "C": np.where(vol > 0, s / vol, np.nan)}
    from engines.rcce_engine import _calc_zscore_hybrid, LEN_LONG, LEN_REGRESSION
    z = _calc_zscore_hybrid(close, LEN_LONG, LEN_REGRESSION)
    z[: 2 * LEN_LONG - 1] = np.nan                              # the engine's warm-up
    out["E"] = z
    have_s, have_r = _count(s), _count(r)
    ready = (have_s >= MIN_HISTORY) & (have_r >= MIN_HISTORY) & np.isfinite(out["A"]) & np.isfinite(out["B"]) \
        & np.isfinite(out["C"])
    out["eval_start"] = int(np.argmax(ready)) if ready.any() else None
    return out


# ---------------------------------------------------------------------------------------------------------- tops
def tops(close: np.ndarray) -> List[int]:
    """Days that are the highest close of the TOP_LOOKBACK days before them (itself included, that much data
    before it), after which the close falls FALL or more within FALL_WITHIN days before any close at or above it
    (a later equal close takes the top over, so each fall has one top)."""
    out = []
    for t in range(TOP_LOOKBACK, len(close)):
        if close[t] < close[t - TOP_LOOKBACK: t + 1].max():
            continue
        for j in range(t + 1, min(len(close), t + FALL_WITHIN + 1)):
            if close[j] >= close[t]:
                break
            if close[j] <= (1 - FALL) * close[t]:
                out.append(t)
                break
    return out


def counted_tops(close: np.ndarray, eval_start: Optional[int]) -> List[int]:
    """Tops whose whole hit window lies in the evaluation days."""
    if eval_start is None:
        return []
    return [t for t in tops(close) if t - HIT_DAYS >= eval_start]


# ---------------------------------------------------------------------------------------------------------- alarms
def alarms(x: np.ndarray, guide: float, eval_start: Optional[int]) -> np.ndarray:
    a = np.zeros(len(x), dtype=bool)
    if eval_start is not None:
        seg = x[eval_start:]
        a[eval_start:] = np.isfinite(seg) & (seg >= guide)
    return a


def divergence(close: np.ndarray, x: np.ndarray, guide: float, eval_start: Optional[int]) -> np.ndarray:
    """D on day t: a new DIV_HIGH-day closing high; a day DIV_SKIP to DIV_HIGH days back at or above the guide;
    today's reading above 0 and under the highest reading of those earlier days."""
    d = np.zeros(len(x), dtype=bool)
    if eval_start is None:
        return d
    for t in range(max(eval_start, DIV_HIGH - 1), len(x)):
        if close[t] < close[t - DIV_HIGH + 1: t + 1].max() or not np.isfinite(x[t]) or x[t] <= 0:
            continue
        lo, hi = max(eval_start, t - DIV_HIGH), t - DIV_SKIP
        if hi < lo:
            continue
        w = x[lo: hi + 1]
        w = w[np.isfinite(w)]
        if len(w) and w.max() >= guide and x[t] < w.max():
            d[t] = True
    return d


def episodes(alarm: np.ndarray) -> List[Tuple[int, int]]:
    idx = np.flatnonzero(alarm)
    out: List[Tuple[int, int]] = []
    for i in idx:
        if out and i - out[-1][1] - 1 <= EPISODE_GAP:
            out[-1] = (out[-1][0], int(i))
        else:
            out.append((int(i), int(i)))
    return out


def score_coin(alarm: np.ndarray, top_days: List[int], eval_start: Optional[int],
               all_tops: Optional[List[int]] = None) -> dict:
    """Hits on the counted tops; episodes (those ending at least HIT_DAYS + FALL_WITHIN days before the last close
    count, so any top after them has had its year to be confirmed) and those at a top (any top, counted or not, from
    the episode's first day to HIT_DAYS after its last); alarm days and evaluation days."""
    n = len(alarm)
    every = top_days if all_tops is None else all_tops
    hits = sum(1 for t in top_days if alarm[t - HIT_DAYS: t + 1].any())
    eps = [e for e in episodes(alarm) if e[1] <= n - 1 - (HIT_DAYS + FALL_WITHIN)]
    at_top = sum(1 for a, b in eps if any(a <= t <= b + HIT_DAYS for t in every))
    days = 0 if eval_start is None else n - eval_start
    return {"hits": hits, "tops": len(top_days), "episodes": len(eps), "at_top": at_top,
            "alarm_days": int(alarm.sum()), "days": days}


def pooled(parts: List[dict]) -> dict:
    s = {k: sum(p[k] for p in parts) for k in ("hits", "tops", "episodes", "at_top", "alarm_days", "days")}
    s["hit_rate"] = s["hits"] / s["tops"] if s["tops"] else None
    s["precision"] = s["at_top"] / s["episodes"] if s["episodes"] else None
    s["alarm_rate"] = s["alarm_days"] / s["days"] if s["days"] else None
    return s


def guides(coins: Dict[str, dict], keys=CANDIDATES + (REFERENCE,)) -> Dict[str, float]:
    """Each measure's GUIDE_Q quantile over the calibration coins' evaluation days, pooled."""
    out = {}
    for k in keys:
        vals = np.concatenate([m[k][m["eval_start"]:] for m in coins.values() if m["eval_start"] is not None])
        vals = vals[np.isfinite(vals)]
        out[k] = float(np.quantile(vals, GUIDE_Q))
    return out


def chance(alarm: np.ndarray, top_days: List[int], eval_start: Optional[int], rng: np.random.Generator) -> float:
    """Mean hits when the coin's alarm days are shifted in time at random within its evaluation days."""
    if eval_start is None or not top_days:
        return 0.0
    seg = alarm[eval_start:]
    n = len(seg)
    if n < 2 * HIT_DAYS + 2:
        return 0.0
    total = 0
    for _ in range(SHIFTS):
        sh = np.zeros(len(alarm), dtype=bool)
        sh[eval_start:] = np.roll(seg, int(rng.integers(HIT_DAYS + 1, n - HIT_DAYS)))
        total += sum(1 for t in top_days if sh[t - HIT_DAYS: t + 1].any())
    return total / SHIFTS


# ---------------------------------------------------------------------------------------------------------- verdicts
def beats(cand: dict, base: dict, alarms_cap: Optional[float] = None) -> dict:
    """The bar against the base, on the test coins."""
    ok_tops = cand["tops"] >= BAR_TOPS
    ok_hit = cand["hit_rate"] is not None and base["hit_rate"] is not None \
        and cand["hit_rate"] - base["hit_rate"] >= BAR_HIT - 1e-12
    ok_prec = cand["precision"] is not None and base["precision"] is not None \
        and cand["precision"] >= base["precision"] - BAR_PRECISION - 1e-12
    ok_alarm = True if alarms_cap is None else cand["alarm_days"] <= alarms_cap * base["alarm_days"]
    return {"enough_tops": ok_tops, "hit": ok_hit, "precision": ok_prec, "alarms": ok_alarm,
            "met": bool(ok_tops and ok_hit and ok_prec and ok_alarm)}


def scale_verdict(test: Dict[str, dict]) -> dict:
    """Q1: B or C in place of A. Both met: the higher hit rate; a tie, B."""
    checks = {k: beats(test[k], test["A"], alarms_cap=BAR_ALARMS_SCALE) for k in ("B", "C")}
    passed = [k for k in ("B", "C") if checks[k]["met"]]
    if not passed:
        winner = "A"
    elif len(passed) == 1:
        winner = passed[0]
    else:
        winner = "C" if test["C"]["hit_rate"] > test["B"]["hit_rate"] + 1e-12 else "B"
    return {"checks": checks, "scale": winner}


def mark_verdict(with_d: dict, alone: dict) -> dict:
    """Q2: the divergence mark on the chosen scale, against that scale alone."""
    return beats(with_d, alone, alarms_cap=BAR_ALARMS)


# ---------------------------------------------------------------------------------------------------------- runs
def load_all(keep_all: bool = False) -> Dict[str, dict]:
    """Every coin's closes; without keep_all, those with more than MAX_FILLED filled days are left out."""
    out = {}
    for coin in PRIMARY + SECONDARY:
        s = fetch(coin)
        if s is not None and (keep_all or s["filled"] <= MAX_FILLED):
            out[coin] = s
    return out


def check() -> dict:
    """Data and counts only: coins with data, their span, filled days, evaluation days and tops per half."""
    series = load_all(keep_all=True)
    cal, test = split()
    rows, per_half = {}, {"calibration": 0, "test": 0, "seen": 0}
    for coin, s in series.items():
        m = measures(s["days"], s["close"])
        ct = counted_tops(s["close"], m["eval_start"])
        half = "seen" if coin in SEEN else "calibration" if coin in cal else "test"
        if s["filled"] > MAX_FILLED:
            half = "left out"
        else:
            per_half[half] += len(ct)
        es = m["eval_start"]
        rows[coin] = {"half": half, "source": s["source"], "first": _date(s["days"][0]), "last": _date(s["days"][-1]),
                      "filled": s["filled"], "eval_from": _date(s["days"][es]) if es is not None else None,
                      "eval_days": 0 if es is None else len(s["days"]) - es, "tops": len(ct),
                      "top_dates": [_date(s["days"][t]) for t in ct] if coin in SEEN else None}
    missing = [c for c in PRIMARY + SECONDARY if c not in series]
    used = {c: s for c, s in series.items() if s["filled"] <= MAX_FILLED}
    return {"sha256": digest(used), "sha256_all": digest(series), "coins": len(used), "missing": missing,
            "left_out": sorted(set(series) - set(used)), "tops": per_half, "per_coin": rows}


def run() -> dict:
    series = load_all()
    cal, test = split()
    m = {c: measures(s["days"], s["close"]) for c, s in series.items()}
    g = guides({c: m[c] for c in cal if c in m})
    rng = np.random.default_rng(SEED)
    result: Dict[str, dict] = {"guides": g, "sha256": digest(series)}
    halves = {"calibration": [c for c in cal if c in m], "test": [c for c in test if c in m],
              "seen": [c for c in SEEN if c in m]}
    for half, coins in halves.items():
        res: Dict[str, dict] = {}
        for k in CANDIDATES + (REFERENCE,):
            parts, ch = [], 0.0
            for c in coins:
                ct = counted_tops(series[c]["close"], m[c]["eval_start"])
                a = alarms(m[c][k], g[k], m[c]["eval_start"])
                parts.append(score_coin(a, ct, m[c]["eval_start"], tops(series[c]["close"])))
                ch += chance(a, ct, m[c]["eval_start"], rng)
            res[k] = pooled(parts)
            res[k]["chance_hits"] = round(ch, 1)
            if k in CANDIDATES:
                parts_d = []
                for c in coins:
                    ct = counted_tops(series[c]["close"], m[c]["eval_start"])
                    a = alarms(m[c][k], g[k], m[c]["eval_start"])
                    d = divergence(series[c]["close"], m[c][k], g[k], m[c]["eval_start"])
                    parts_d.append(score_coin(a | d, ct, m[c]["eval_start"], tops(series[c]["close"])))
                res[f"{k}+D"] = pooled(parts_d)
        result[half] = res
    q1 = scale_verdict(result["test"])
    x = q1["scale"]
    q2 = mark_verdict(result["test"][f"{x}+D"], result["test"][x])
    result["verdict"] = {"scale": q1, "mark": {"on": x, **q2}}
    # The seen coins, top by top: each reading's highest value in the hit window.
    seen_tops = {}
    for c in halves["seen"]:
        rows = []
        for t in counted_tops(series[c]["close"], m[c]["eval_start"]):
            w = slice(t - HIT_DAYS, t + 1)
            rows.append({"top": _date(series[c]["days"][t]), "close": round(float(series[c]["close"][t]), 4),
                         "pct": round(float(m[c]["pct"][t]), 1),
                         **{k: round(float(np.nanmax(m[c][k][w])), 2) for k in CANDIDATES + (REFERENCE,)}})
        seen_tops[c] = rows
    result["seen_tops"] = seen_tops
    result["guide_A_share_at_2"] = _share_at(m, halves["calibration"], "A", 2.0)
    return result


def _share_at(m: Dict[str, dict], coins: List[str], key: str, level: float) -> float:
    vals = np.concatenate([m[c][key][m[c]["eval_start"]:] for c in coins if m[c]["eval_start"] is not None])
    vals = vals[np.isfinite(vals)]
    return round(float((vals >= level).mean()), 4)


def _date(day: int) -> str:
    return datetime.fromtimestamp(int(day) * DAY_S, tz=timezone.utc).strftime("%Y-%m-%d")


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("check", "run"))
    args = ap.parse_args(argv)
    out = check() if args.cmd == "check" else run()
    json.dump(out, sys.stdout, indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)
    print()


if __name__ == "__main__":
    main()
