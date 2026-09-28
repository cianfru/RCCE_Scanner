"""
Risk-on and risk-off cycles in market breadth: market context, not a signal
(declared in docs/reviews/risk-on-cycles-study.md, 28 September 2026, before running).

    python -m backtest.risk_on_cycles insample --out in.json                  (from backend/; = --sample in)
    python -m backtest.risk_on_cycles oos --insample in.json --out oos.json   (= --sample out; only after the
                                                                               in-sample results are committed)
    python -m backtest.risk_on_cycles --sample all --insample in.json         (every case to 2026-09-25,
                                                                               descriptive, no verdicts)

Breadth is the Uptrend + Overheated share of the market-history rebuild (data/larsson_runs/breadth_history.json,
days with 40+ coins). A risk-on run starts on the first day at 55% or more after 5+ days below, and ends on the
first day of a stretch of 5+ days below; the days in between are a risk-off run. BTC's weekly bull market support
band is the 20-week SMA and 21-week EMA of Sunday weekly closes, completed weeks only (as declared; note that
market_history.btc_band's weekday filter selects Wednesdays, see `weekly_band`).

The in-sample stage sees days up to 2026-03-29 only. The one exception, as declared: today's Uptrend share, BTC's
side of its band and the current run's start, read from the production API to pick the analog buckets.
Frequencies are historical counts ("k of n past cases") with Wilson 90% intervals, never forecasts.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import urllib.request
from bisect import bisect_right
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "larsson_runs"
API_URL = "https://rccescanner-production.up.railway.app/api/market-history"

END_DAY = 20541            # 2026-03-29: last in-sample day; no in-sample window reaches past it
OOS_END_DAY = 20721        # 2026-09-25: last rebuilt day, where the out-of-sample stage's data end
MIN_COINS = 40
THR = 0.55                 # RISK-ON bar
OFF_DAYS = 5               # a stretch of 5+ days below THR ends a risk-on run
CONFIRM = OFF_DAYS - 1     # days after an end day needed to confirm it
BREAK_GAP = 5              # below-band days with gaps of up to 5 days form one break stretch
MIN_ALTS = 20
Z90 = 1.645
FEW = 6                    # fewer independent cases than this: "too few to read"
SURVIVAL_D = (10, 20, 30, 45, 60, 90, 120)
SURVIVAL_MORE = 30
AGE_EDGES = (0, 15, 30, 60, 120)
HORIZONS = (30, 60)
CHANGE_H = (10, 30)
AFTER_END = 60             # 3b: a band break within 60 days after a run's end
SUNDAY, WEDNESDAY = 3, 6   # day % 7 (day 3 = 1970-01-04 was a Sunday)
AGREE = 0.01               # rebuild and API must agree within 1 point of Uptrend share


# ---------------------------------------------------------------------------
# Small statistics
# ---------------------------------------------------------------------------

def q(v: List[float], p: float) -> float:
    """Quartile as in the market-breadth study: the value at position floor(p*(n-1)) of the sorted list."""
    return sorted(v)[int(p * (len(v) - 1))]


def wilson(k: int, n: int, z: float = Z90):
    if n == 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def freq(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "share": None if n == 0 else round(k / n, 3),
            "lo": None if lo is None else round(lo, 3), "hi": None if hi is None else round(hi, 3), "few": n < FEW}


def dist(values: Iterable[Optional[float]]) -> dict:
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0, "few": True}
    return {"n": len(v), "median": round(statistics.median(v), 1), "q25": round(q(v, .25), 1),
            "q75": round(q(v, .75), 1), "few": len(v) < FEW}


def day_share(k: int, n: int) -> dict:
    """A share over overlapping days: no interval."""
    return {"k": k, "n": n, "share": None if n == 0 else round(k / n, 3)}


def pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(100 * x, 1)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def weekly_band(btc: Dict[int, float], weekday: int = SUNDAY) -> Dict[int, tuple]:
    """BTC's weekly bull market support band per day: (lower, upper) = min/max of the 20-week SMA and the
    21-week EMA of completed weeks, used from the day after the week's close. Same arithmetic as
    market_history.btc_band, with the weekly close on `weekday` (day % 7). The declared band closes weeks on
    Sundays; market_history.btc_band's filter ((d + 4) % 7 == 3) equals weekday=WEDNESDAY."""
    days = sorted(btc)
    bands, closes, ema = [], [], None
    for w in (d for d in days if d % 7 == weekday):
        c = btc[w]
        closes.append(c)
        ema = c if ema is None else (2 / 22) * c + (1 - 2 / 22) * ema
        sma = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        bands.append((w, None if sma is None or len(closes) < 21 else (min(sma, ema), max(sma, ema))))
    out: Dict[int, tuple] = {}
    wi = -1
    for d in days:
        while wi + 1 < len(bands) and bands[wi + 1][0] < d:          # completed weeks only
            wi += 1
        if wi >= 0 and bands[wi][1]:
            out[d] = bands[wi][1]
    return out


def band_breaks(btc: Dict[int, float], band: Dict[int, tuple], gap: int = BREAK_GAP) -> List[int]:
    """First days of below-band stretches (daily close under the lower edge; gaps of up to `gap` days merged)."""
    out, last = [], None
    for d in sorted(btc):
        if d in band and btc[d] < band[d][0]:
            if last is None or d - last > gap + 1:
                out.append(d)
            last = d
    return out


class Market:
    """The rebuild (breadth, BTC and per-coin closes) plus the API's days after it."""

    def __init__(self, share: Dict[int, float], btc: Dict[int, float], alt_closes: Dict[str, Dict[int, float]],
                 weekday: int = SUNDAY, api: Optional[dict] = None):
        self.share, self.btc = dict(share), dict(btc)
        self.rebuild_last = max(share)
        self.api_info = None
        if api is not None:
            self.api_info = merge_api(self.share, self.btc, api)
        self.band = weekly_band(self.btc, weekday)
        self.weekday = weekday
        self.pairs = sorted(alt_closes)
        lo, hi = min(btc), max(btc)
        self.d0 = lo
        self.alts = np.full((len(self.pairs), hi - lo + 1), np.nan)
        for i, p in enumerate(self.pairs):
            for d, c in alt_closes[p].items():
                if lo <= d <= hi:
                    self.alts[i, d - lo] = c

    @classmethod
    def load(cls, path: Optional[str] = None, weekday: int = SUNDAY, api: Optional[dict] = None) -> "Market":
        data = json.loads(Path(path or RUNS_DIR / "breadth_history.json").read_text())
        share = {x["day"]: round(x["uptrend"] + x["overheated"], 4) for x in data["days"] if x["n"] >= MIN_COINS}
        btc = {int(d): c for d, c in data["closes"]["BTCUSDT"].items()}
        alts = {p: {int(d): c for d, c in v.items()} for p, v in data["closes"].items() if p != "BTCUSDT"}
        return cls(share, btc, alts, weekday, api)


def merge_api(share: Dict[int, float], btc: Dict[int, float], api: dict) -> dict:
    """Append the API's days after the rebuild; stop if the overlap disagrees by more than 1 point."""
    cols = api["columns"]
    iu, io, ib = cols.index("uptrend"), cols.index("overheated"), cols.index("btc")
    last = max(share)
    worst, overlap, added = 0.0, 0, []
    for r in api["days"]:
        x = round(r[iu] + r[io], 4)
        if r[0] in share:
            overlap += 1
            worst = max(worst, abs(x - share[r[0]]))
        elif r[0] > last:
            share[r[0]] = x
            if r[ib]:
                btc[r[0]] = r[ib]
            added.append(r[0])
    if worst > AGREE:
        raise SystemExit(f"Rebuild and API disagree by {100 * worst:.1f} points of Uptrend share: stopping")
    return {"overlap_days": overlap, "max_difference": round(worst, 4), "added": added,
            "last_day": api["days"][-1][0], "drawer_percentile": (api.get("today") or {}).get("percentile")}


class Sample:
    """The market cut at `last`: nothing after it is read, except through `Market` for today's state."""

    def __init__(self, m: Market, last: int, first: Optional[int] = None):
        self.last = last
        self.days = [d for d in sorted(m.share) if d <= last and (first is None or d >= first)]
        if any(b - a != 1 for a, b in zip(self.days, self.days[1:])):
            raise SystemExit("Missing days in the breadth series")
        self.share = {d: m.share[d] for d in self.days}
        self.btc = {d: c for d, c in m.btc.items() if d <= last}
        self.band = {d: b for d, b in m.band.items() if d <= last}
        self.breaks = band_breaks(self.btc, self.band)
        self._m = m

    def side(self, d: int) -> Optional[str]:
        if d not in self.band or d not in self.btc:
            return None
        lo, hi = self.band[d]
        c = self.btc[d]
        return "below" if c < lo else "above" if c > hi else "inside"

    def holding_days(self, d: int) -> int:
        """Consecutive days up to and including d with BTC holding its band (0 if below on d)."""
        n = 0
        while self.side(d - n) not in (None, "below"):
            n += 1
        return n

    def btc_ret(self, t: int, e: int) -> Optional[float]:
        if e > self.last or t not in self.btc or e not in self.btc:
            return None
        return self.btc[e] / self.btc[t] - 1

    def alt_ret(self, t: int, e: int) -> Optional[float]:
        m = self._m
        if e > self.last or t < m.d0 or e - m.d0 >= m.alts.shape[1]:
            return None
        a, b = m.alts[:, t - m.d0], m.alts[:, e - m.d0]
        ok = ~np.isnan(a) & ~np.isnan(b) & (a > 0)
        if ok.sum() < MIN_ALTS:
            return None
        return float(np.median(b[ok] / a[ok] - 1))


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def detect_runs(days: List[int], share: Dict[int, float]) -> List[dict]:
    """Risk-on ('on') and risk-off ('off') runs over consecutive days. A risk-on run starts on the first day at
    THR or more after OFF_DAYS+ days below, and ends on the first day of a stretch of OFF_DAYS+ days below
    (dips of up to OFF_DAYS-1 days stay inside). The first run's start is unknown (the days before are taken
    to be of its type). The last run has no confirmed end (end None): it is censored at the last day."""
    state = "on" if share[days[0]] >= THR else "off"
    cur = {"type": state, "start": days[0], "first": True}
    runs, below = [], 0
    for d in days:
        if share[d] >= THR:
            below = 0
            if state == "off":
                runs.append({**cur, "end": d})
                cur, state = {"type": "on", "start": d, "first": False}, "on"
        else:
            below += 1
            if state == "on" and below == OFF_DAYS:
                e = d - CONFIRM
                runs.append({**cur, "end": e})
                cur, state = {"type": "off", "start": e, "first": False}, "off"
    runs.append({**cur, "end": None})
    last = days[-1]
    for r in runs:
        if r["end"] is not None:
            r["length"] = r["end"] - r["start"]
        elif r["type"] == "on":
            r["min_length"] = max(d for d in range(r["start"], last + 1) if share[d] >= THR) - r["start"] + 1
        else:
            r["min_length"] = last - r["start"] + 1
    return runs


def run_length(r: dict) -> int:
    return r["length"] if "length" in r else r["min_length"]


def how_ended(r: dict, s: Sample) -> dict:
    """3b: the first case that applies to an ended risk-on run."""
    st, e = r["start"], r["end"]
    inside = [b for b in s.breaks if st <= b <= e]
    if inside:
        return {"case": "btc_first", "lead": e - inside[-1]}
    if s.side(e) == "below":
        return {"case": "already_below"}
    after = [b for b in s.breaks if e < b <= e + AFTER_END]
    if after:
        return {"case": "breadth_first", "lag": after[0] - e}
    if e + AFTER_END <= s.last:
        return {"case": "no_break_60d"}
    return {"case": "not_known_yet"}


def run_fields(r: dict, s: Sample) -> dict:
    ended = r["end"] is not None
    stop = r["end"] if ended else s.last                 # end day, or the censor day
    span = list(range(r["start"], r["end"] if ended else s.last + 1))
    vals = [s.share[d] for d in span]
    out = {"type": r["type"], "start": r["start"], "end": r["end"], "first": r["first"], "censored": not ended}
    out["length" if ended else "min_length"] = run_length(r)
    if r["type"] == "on":
        ext = max(vals)
        out.update(peak=ext, reached85=ext >= .85, reached95=ext >= .95)
    else:
        ext = min(vals)
        out.update(low=ext, reached15=ext <= .15, reached5=ext <= .05)
    ext_day = span[vals.index(ext)]
    out.update(extreme_day=ext_day, days_to_extreme=ext_day - r["start"],
               btc=pct(s.btc_ret(r["start"], stop)), alt=pct(s.alt_ret(r["start"], stop)),
               btc_from_extreme=pct(s.btc_ret(ext_day, stop)), alt_from_extreme=pct(s.alt_ret(ext_day, stop)),
               btc_at_start=s.side(r["start"]))
    if r["type"] == "on":
        brk = [b for b in s.breaks if r["start"] <= b <= stop]
        out.update(band_breaks=len(brk), first_break_to_end=stop - brk[0] if brk else None,
                   last_break_to_end=stop - brk[-1] if brk else None, below_at_end=s.side(stop) == "below")
        if ended:
            out["how_ended"] = how_ended(r, s)
    else:
        out.update(btc_at_end=s.side(stop), holding_days_at_end=s.holding_days(stop))
    return out


def survival_row(rows: List[dict], d: int, more: int = SURVIVAL_MORE) -> dict:
    """Of risk-on runs that lasted at least d days, the share that lasted at least d + more. A censored run
    is at risk if it lasted d; it counts only if it already lasted d + more (else it is left out)."""
    at_risk = known = lasted = left_out = 0
    for r in rows:
        if r["type"] != "on" or r["first"]:
            continue
        n = run_length(r)
        if n < d:
            continue
        at_risk += 1
        if not r["censored"]:
            known += 1
            lasted += n >= d + more
        elif n >= d + more:
            known += 1
            lasted += 1
        else:
            left_out += 1
    return {"d": d, "more": more, "at_risk": at_risk, "left_out": left_out, "lasted": lasted, **freq(lasted, known)}


# ---------------------------------------------------------------------------
# Today and analogs
# ---------------------------------------------------------------------------

def breadth_bucket(x: float) -> int:
    """10-point bucket index: 8 = 80-90%. 100% joins 90-100%."""
    return min(int(round(x * 10000)) // 1000, 9)


def age_bucket(a: int) -> int:
    return max(i for i, lo in enumerate(AGE_EDGES) if a >= lo)


def age_label(i: int) -> str:
    return f"{AGE_EDGES[i]}-{AGE_EDGES[i + 1]} days" if i + 1 < len(AGE_EDGES) else f"{AGE_EDGES[i]} days or more"


def stretch_starts(days: List[int], share: Dict[int, float], above: bool) -> Dict[int, Optional[int]]:
    """Age reference per day. Above THR: the start of its risk-on run (None in the first run, start unknown).
    Below THR: the first day of its stretch below THR (None if the stretch starts the series)."""
    out: Dict[int, Optional[int]] = {}
    if above:
        for r in detect_runs(days, share):
            if r["type"] == "on":
                stop = r["end"] if r["end"] is not None else days[-1] + 1
                for d in range(r["start"], stop):
                    if share[d] >= THR:
                        out[d] = None if r["first"] else r["start"]
    else:
        start = None
        for i, d in enumerate(days):
            if share[d] < THR:
                if i == 0 or share[days[i - 1]] >= THR:
                    start = None if i == 0 else d
                out[d] = start
    return out


def today_state(m: Market) -> dict:
    """Today's reading (the latest day, API included): share, BTC side, current run start. Nothing else from
    after the in-sample end is read here."""
    days = sorted(m.share)
    t = days[-1]
    x = m.share[t]
    above = x >= THR
    start = stretch_starts(days, m.share, above)[t]
    if start is None:
        raise SystemExit("Today's stretch began before the series: its age is unknown")
    lo, hi = m.band[t]
    side = "below" if m.btc[t] < lo else "above" if m.btc[t] > hi else "inside"
    age = t - start
    return {"day": t, "share": x, "above": above, "bucket": breadth_bucket(x), "start": start, "age": age,
            "age_bucket": age_bucket(age), "btc_side": side, "btc_holding": side != "below",
            "btc": m.btc[t], "band": [round(lo, 2), round(hi, 2)]}


def analog_days(s: Sample, today: dict):
    """Set A (one episode per run: its first full-match day) and set B (same breadth bucket, gaps of up to 5
    days merged). Returns two lists of first days."""
    ref = stretch_starts(s.days, s.share, today["above"])
    a, seen = [], set()
    for d in s.days:
        st = ref.get(d)
        if st is None or (s.share[d] >= THR) != today["above"] or breadth_bucket(s.share[d]) != today["bucket"]:
            continue
        side = s.side(d)
        if side is None or (side != "below") != today["btc_holding"] or age_bucket(d - st) != today["age_bucket"]:
            continue
        if st not in seen:
            seen.add(st)
            a.append(d)
    b, last = [], None
    for d in s.days:
        if breadth_bucket(s.share[d]) == today["bucket"]:
            if last is None or d - last > BREAK_GAP + 1:
                b.append(d)
            last = d
    return a, b


def run_ends(runs: List[dict], above: bool) -> List[int]:
    """Days a run of today's type ended (risk-on: end days; risk-off: the next start)."""
    kind = "on" if above else "off"
    return sorted(r["end"] for r in runs if r["type"] == kind and r["end"] is not None)


def ended_within(ends: List[int], t: int, h: int) -> bool:
    i = bisect_right(ends, t)
    return i < len(ends) and ends[i] <= t + h


def forward(s: Sample, t: int, ends: List[int]) -> dict:
    """Outcomes from day t's close over 30 and 60 days (window plus 4 days inside the sample)."""
    out = {}
    for h in HORIZONS:
        if t + h + CONFIRM > s.last:
            out[str(h)] = None
            continue
        out[str(h)] = {"reached90": max(s.share[t + i] for i in range(1, h + 1)) >= .90,
                       "ended": ended_within(ends, t, h),
                       "btc": pct(s.btc_ret(t, t + h)), "alt": pct(s.alt_ret(t, t + h))}
    return out


def summarize_forward(rows: List[dict], intervals: bool = True) -> dict:
    out = {}
    f = freq if intervals else day_share
    for h in map(str, HORIZONS):
        o = [r["fwd"][h] for r in rows if r["fwd"].get(h)]
        out[h] = {"n": len(o), "reached90": f(sum(x["reached90"] for x in o), len(o)),
                  "ended": f(sum(x["ended"] for x in o), len(o)),
                  "btc": dist(x["btc"] for x in o), "alt": dist(x["alt"] for x in o)}
    return out


# ---------------------------------------------------------------------------
# Band events (3c)
# ---------------------------------------------------------------------------

def break_event(s: Sample, t: int, on_ends: List[int]) -> dict:
    row = {"day": t, "share": s.share[t]}
    for h in CHANGE_H:
        ok = t + h + CONFIRM <= s.last
        row[f"change{h}"] = round(100 * (s.share[t + h] - s.share[t]), 1) if ok else None
    for h in HORIZONS:
        ok = t + h + CONFIRM <= s.last
        row[f"ended{h}"] = ended_within(on_ends, t, h) if ok else None
        row[f"btc{h}"] = pct(s.btc_ret(t, t + h)) if ok else None
        row[f"alt{h}"] = pct(s.alt_ret(t, t + h)) if ok else None
    return row


def summarize_events(rows: List[dict]) -> dict:
    out = {"n": len(rows)}
    for h in CHANGE_H:
        out[f"change{h}"] = dist(r[f"change{h}"] for r in rows)
    for h in HORIZONS:
        v = [r[f"ended{h}"] for r in rows if r[f"ended{h}"] is not None]
        out[f"ended{h}"] = freq(sum(v), len(v))
        out[f"btc{h}"] = dist(r[f"btc{h}"] for r in rows)
        out[f"alt{h}"] = dist(r[f"alt{h}"] for r in rows)
    return out


# ---------------------------------------------------------------------------
# The study on one sample
# ---------------------------------------------------------------------------

def summarize_runs(rows: List[dict]) -> dict:
    out = {}
    for kind in ("on", "off"):
        mine = [r for r in rows if r["type"] == kind]
        ended = [r for r in mine if not r["censored"] and not r["first"]]
        o = {"runs": len(mine), "ended": len(ended), "censored": sum(r["censored"] for r in mine),
             "first_unknown_start": sum(r["first"] for r in mine), "length": dist(r["length"] for r in ended)}
        if kind == "on":
            long_ = [r for r in ended if r["length"] >= 30]
            o.update(reached85=freq(sum(r["reached85"] for r in ended), len(ended)),
                     reached95=freq(sum(r["reached95"] for r in ended), len(ended)),
                     reached85_30d=freq(sum(r["reached85"] for r in long_), len(long_)),
                     reached95_30d=freq(sum(r["reached95"] for r in long_), len(long_)))
        else:
            o.update(reached15=freq(sum(r["reached15"] for r in ended), len(ended)),
                     reached5=freq(sum(r["reached5"] for r in ended), len(ended)))
        o.update(days_to_extreme=dist(r["days_to_extreme"] for r in ended),
                 btc=dist(r["btc"] for r in ended), alt=dist(r["alt"] for r in ended),
                 btc_from_extreme=dist(r["btc_from_extreme"] for r in ended),
                 alt_from_extreme=dist(r["alt_from_extreme"] for r in ended))
        out[kind] = o
    return out


def summarize_how_ended(rows: List[dict]) -> dict:
    ended = [r for r in rows if r["type"] == "on" and not r["censored"] and not r["first"]]
    cases = {c: sum(r["how_ended"]["case"] == c for r in ended)
             for c in ("btc_first", "already_below", "breadth_first", "no_break_60d", "not_known_yet")}
    known = len(ended) - cases["not_known_yet"]
    return {"runs": len(ended), "cases": cases, "known": known,
            "btc_first": freq(cases["btc_first"], known),
            "without_btc_first": freq(cases["breadth_first"] + cases["no_break_60d"], known),
            "lead": dist(r["how_ended"].get("lead") for r in ended),
            "lag": dist(r["how_ended"].get("lag") for r in ended)}


def band_days(s: Sample) -> dict:
    out = {}
    for side in ("above", "inside", "below"):
        ds = [d for d in s.days if s.side(d) == side]
        v = [s.share[d] for d in ds]
        out[side] = {"days": len(ds), "risk_on_days": sum(x >= THR for x in v), "below_55_days": sum(x < THR for x in v),
                     "median_share": round(statistics.median(v), 3) if v else None}
    return out


def describe(s: Sample, today: dict) -> dict:
    runs = detect_runs(s.days, s.share)
    rows = [run_fields(r, s) for r in runs]
    on_ends = run_ends(runs, True)

    events = [break_event(s, t, on_ends) for t in s.breaks if t in s.share and s.share[t] >= THR]
    base = [break_event(s, t, on_ends) for t in s.days if s.share[t] >= THR and s.side(t) not in (None, "below")]
    base_sum = {}
    for h in HORIZONS:
        v = [r[f"ended{h}"] for r in base if r[f"ended{h}"] is not None]
        base_sum[str(h)] = {"ended": day_share(sum(v), len(v)), "btc": dist(r[f"btc{h}"] for r in base),
                            "alt": dist(r[f"alt{h}"] for r in base)}

    ends = run_ends(runs, today["above"])
    a, b = analog_days(s, today)
    ref = stretch_starts(s.days, s.share, today["above"])
    set_a = [{"day": t, "run_start": ref[t], "share": s.share[t], "fwd": forward(s, t, ends)} for t in a]
    set_b = [{"day": t, "share": s.share[t], "run_start": ref.get(t), "fwd": forward(s, t, ends)} for t in b]
    every = [{"fwd": forward(s, t, ends)} for t in s.days]

    ended_on = [r for r in rows if r["type"] == "on" and not r["censored"] and not r["first"]]
    age = today["age"]
    now = {**today, "age_bucket_label": age_label(today["age_bucket"]),
           "bucket_label": f"{10 * today['bucket']}-{10 * today['bucket'] + 10}%",
           "ended_runs_as_long": day_share(sum(r["length"] >= age for r in ended_on), len(ended_on)),
           "percentile_in_sample_days": round(100 * sum(s.share[d] < today["share"] for d in s.days) / len(s.days)),
           "survival_at_age": [survival_row(rows, age, 30), survival_row(rows, age, 60)]}
    if today["start"] is not None and today["start"] <= s.last:
        span = [d for d in s.days if d >= today["start"]]
        pk = max(s.share[d] for d in span)
        now["up_to_sample_end"] = {"last": s.last, "peak": pk, "reached85": pk >= .85, "reached95": pk >= .95,
                                   "band_breaks": [d for d in s.breaks if d >= today["start"]]}

    return {"sample_first": s.days[0], "sample_last": s.last, "days": len(s.days),
            "runs": rows, "summary": summarize_runs(rows),
            "survival": [survival_row(rows, d) for d in SURVIVAL_D],
            "band_days": band_days(s), "how_ended": summarize_how_ended(rows),
            "break_events": {"rows": events, "summary": summarize_events(events), "comparison": base_sum,
                             "comparison_days": len(base)},
            "analogs": {"A": {"rows": set_a, "summary": summarize_forward(set_a)},
                        "B": {"rows": set_b, "summary": summarize_forward(set_b)},
                        "all_days": summarize_forward(every, intervals=False)},
            "now": now}


# ---------------------------------------------------------------------------
# Out-of-sample check
# ---------------------------------------------------------------------------

def verdict_share(k: int, n: int, ref: Optional[dict]) -> dict:
    out = {"k": k, "n": n, "share": None if n == 0 else round(k / n, 3)}
    if n == 0:
        out["verdict"] = "no out-of-sample case"
        return out
    if not ref or ref.get("lo") is None:
        v = "no in-sample reference"
    else:
        v = "consistent" if ref["lo"] <= k / n <= ref["hi"] else "did not hold out of sample"
    out["verdict"] = v if n >= FEW else f"{v} (n = {n}, too few to read)"
    return out


def verdict_median(values: List[Optional[float]], ref: Optional[dict]) -> dict:
    v = [x for x in values if x is not None]
    out = {"n": len(v), "values": v}
    if not v:
        out["verdict"] = "no out-of-sample case"
        return out
    med = statistics.median(v)
    out["median"] = round(med, 1)
    if not ref or ref.get("n", 0) == 0:
        w = "no in-sample reference"
    else:
        w = "consistent" if ref["q25"] <= med <= ref["q75"] else "did not hold out of sample"
    out["verdict"] = w if len(v) >= FEW else f"{w} (n = {len(v)}, too few to read)"
    return out


def out_of_sample(full: dict, ins: dict) -> dict:
    """Cases that start after END_DAY, plus the run censored in-sample (marked), against the in-sample results."""
    ended_in = {(r["type"], r["start"]) for r in ins["runs"] if not r["censored"]}
    cen = next(r for r in ins["runs"] if r["censored"])
    cen_start = cen["start"]
    runs = [dict(r, began_in_sample=r["start"] <= END_DAY) for r in full["runs"]
            if not r["first"] and (r["type"], r["start"]) not in ended_in]
    ended = [r for r in runs if not r["censored"]]
    S = ins["summary"]
    out = {"insample_censored_run": {"type": cen["type"], "start": cen_start}, "runs": runs}

    # 1-2. lengths and reach
    out["length"] = {k: verdict_median([r["length"] for r in ended if r["type"] == k], S[k]["length"])
                     for k in ("on", "off")}
    on = [r for r in ended if r["type"] == "on"]
    out["reached85"] = verdict_share(sum(r["reached85"] for r in on), len(on), S["on"]["reached85"])
    out["reached95"] = verdict_share(sum(r["reached95"] for r in on), len(on), S["on"]["reached95"])

    # 3. survival rows (the declared d and today's age) with 6+ in-sample runs; the run censored in-sample counts
    # only where its outcome was unknown in-sample
    surv = []
    for row in ins["survival"] + ins["now"]["survival_at_age"]:
        if row["n"] < FEW:
            continue
        d, more = row["d"], row["more"]
        k = n = 0
        for r in (x for x in runs if x["type"] == "on"):
            length = run_length(r)
            if length < d:
                continue
            if r["began_in_sample"] and r["start"] == cen_start and cen["min_length"] >= d + more:
                continue                                          # already known in-sample
            if not r["censored"] or length >= d + more:
                n += 1
                k += length >= d + more
        surv.append({"d": d, "more": more, **verdict_share(k, n, row)})
    out["survival"] = surv

    # 4. how runs end
    he = [r["how_ended"] for r in on if r["how_ended"]["case"] != "not_known_yet"]
    H = ins["how_ended"]
    out["how_ended"] = {"cases": [dict(start=r["start"], **r["how_ended"]) for r in on],
                        "btc_first": verdict_share(sum(x["case"] == "btc_first" for x in he), len(he), H["btc_first"]),
                        "lead": verdict_median([x.get("lead") for x in he], H["lead"]),
                        "lag": verdict_median([x.get("lag") for x in he], H["lag"])}

    def counts(t: int, h: int) -> bool:
        return t > END_DAY or (cen_start <= t <= END_DAY and t + h + CONFIRM > END_DAY)

    # 5. band breaks while risk-on
    E = ins["break_events"]["summary"]
    ev = {}
    for h in HORIZONS:
        rows = [r for r in full["break_events"]["rows"] if counts(r["day"], h) and r[f"ended{h}"] is not None]
        ev[f"ended{h}"] = verdict_share(sum(r[f"ended{h}"] for r in rows), len(rows), E[f"ended{h}"])
        ev[f"alt{h}"] = verdict_median([r[f"alt{h}"] for r in rows], E[f"alt{h}"])
        ev[f"days{h}"] = [r["day"] for r in rows]
        ev[f"marked{h}"] = [r["day"] for r in rows if r["day"] <= END_DAY]
    out["break_events"] = ev

    # 6. analogs
    an = {}
    for key in ("A", "B"):
        ref = ins["analogs"][key]["summary"]
        res = {}
        for h in map(str, HORIZONS):
            rows = [r for r in full["analogs"][key]["rows"] if counts(r["day"], int(h)) and r["fwd"].get(h)]
            o = [r["fwd"][h] for r in rows]
            res[h] = {"days": [r["day"] for r in rows],
                      "marked": [r["day"] for r in rows if r["day"] <= END_DAY],
                      "reached90": verdict_share(sum(x["reached90"] for x in o), len(o), ref[h]["reached90"]),
                      "ended": verdict_share(sum(x["ended"] for x in o), len(o), ref[h]["ended"]),
                      "btc": verdict_median([x["btc"] for x in o], ref[h]["btc"]),
                      "alt": verdict_median([x["alt"] for x in o], ref[h]["alt"])}
        an[key] = res
    out["analogs"] = an
    return out


# ---------------------------------------------------------------------------
# Report tables (markdown)
# ---------------------------------------------------------------------------

def _date(d: Optional[int]) -> str:
    import datetime
    return "" if d is None else str(datetime.date(1970, 1, 1) + datetime.timedelta(days=d))


def _f(x: dict) -> str:
    if not x or x.get("n", 0) == 0:
        return "none"
    s = f"{x['k']} of {x['n']}"
    if "lo" in x and x["lo"] is not None:
        s += f" ({round(100 * x['share'])}%, 90% range {round(100 * x['lo'])}-{round(100 * x['hi'])}%)"
    else:
        s += f" ({round(100 * x['share'])}%)"
    return s + (", too few to read" if x.get("few") else "")


def _d(x: dict, unit: str = "%") -> str:
    if not x or x.get("n", 0) == 0:
        return "none"
    fmt = (lambda v: f"{v:+.1f}%") if unit == "%" else (lambda v: f"{v:g}")
    s = f"{fmt(x['median'])} ({fmt(x['q25'])} to {fmt(x['q75'])}), n = {x['n']}"
    return s + (", too few to read" if x.get("few") else "")


def markdown(res: dict) -> str:
    L = []
    S = res["summary"]
    L.append("| Run type | Runs (ended / censored / first) | Length, days: median (quartiles) |")
    L.append("|---|---|---|")
    for k, name in (("on", "Risk-on"), ("off", "Risk-off")):
        o = S[k]
        L.append(f"| {name} | {o['runs']} ({o['ended']} / {o['censored']} / {o['first_unknown_start']}) | {_d(o['length'], 'd')} |")
    L.append("")
    o = S["on"]
    L.append("| Risk-on runs (ended) | All ended | Lasted 30+ days |")
    L.append("|---|---|---|")
    L.append(f"| Reached 85% | {_f(o['reached85'])} | {_f(o['reached85_30d'])} |")
    L.append(f"| Reached 95% | {_f(o['reached95'])} | {_f(o['reached95_30d'])} |")
    L.append("")
    L.append("| Risk-on runs (ended) | Median (quartiles) |")
    L.append("|---|---|")
    L.append(f"| Days from start to peak | {_d(o['days_to_extreme'], 'd')} |")
    L.append(f"| BTC, start to end | {_d(o['btc'])} |")
    L.append(f"| Typical alt, start to end | {_d(o['alt'])} |")
    L.append(f"| BTC, peak to end | {_d(o['btc_from_extreme'])} |")
    L.append(f"| Typical alt, peak to end | {_d(o['alt_from_extreme'])} |")
    L.append("")
    o = S["off"]
    L.append("| Risk-off runs (ended) | |")
    L.append("|---|---|")
    L.append(f"| Uptrend share fell to 15% or less | {_f(o['reached15'])} |")
    L.append(f"| Uptrend share fell to 5% or less | {_f(o['reached5'])} |")
    L.append(f"| Days from start to low | {_d(o['days_to_extreme'], 'd')} |")
    L.append(f"| BTC, start to end | {_d(o['btc'])} |")
    L.append(f"| Typical alt, start to end | {_d(o['alt'])} |")
    L.append(f"| BTC, low to end | {_d(o['btc_from_extreme'])} |")
    L.append(f"| Typical alt, low to end | {_d(o['alt_from_extreme'])} |")
    L.append("")
    L.append("| # | Type | Start | End | Days | Extreme | Days to it | BTC | Alt | BTC at start | BTC during / at end |")
    L.append("|---:|---|---|---|---:|---:|---:|---:|---:|---|---|")
    for i, r in enumerate(res["runs"], 1):
        days = r.get("length", r.get("min_length"))
        days = f"{days}+" if r["censored"] else str(days)
        ext = r.get("peak", r.get("low"))
        tag = " (start unknown)" if r["first"] else ""
        end = "censored" if r["censored"] else _date(r["end"])
        if r["type"] == "on":
            he = r.get("how_ended", {})
            extra = f"{r['band_breaks']} break(s)"
            if he:
                extra += f"; {he['case'].replace('_', ' ')}"
                if "lead" in he:
                    extra += f", lead {he['lead']}d"
                if "lag" in he:
                    extra += f", lag {he['lag']}d"
        else:
            extra = f"{r['btc_at_end']} at end, holding {r['holding_days_at_end']}d"
        fmt = lambda v: "" if v is None else f"{v:+.1f}%"
        L.append(f"| {i} | {'on' if r['type'] == 'on' else 'off'}{tag} | {_date(r['start'])} | {end} | {days} | "
                 f"{100 * ext:.1f}% | {r['days_to_extreme']} | {fmt(r['btc'])} | {fmt(r['alt'])} | "
                 f"{r['btc_at_start']} | {extra} |")
    L.append("")
    L.append("| Lasted at least d days | At risk | Known | Lasted d+30 | Left out (censored) |")
    L.append("|---:|---:|---:|---|---:|")
    for row in res["survival"] + res["now"]["survival_at_age"]:
        lab = f"{row['d']} (+{row['more']})"
        L.append(f"| {lab} | {row['at_risk']} | {row['n']} | {_f(row)} | {row['left_out']} |")
    L.append("")
    L.append("| BTC side | Days | Uptrend share 55%+ | Below 55% | Median Uptrend share |")
    L.append("|---|---:|---:|---:|---:|")
    for side, o in res["band_days"].items():
        med = "" if o["median_share"] is None else f"{round(100 * o['median_share'])}%"
        L.append(f"| {side} | {o['days']} | {o['risk_on_days']} | {o['below_55_days']} | {med} |")
    L.append("")
    H = res["how_ended"]
    L.append("| How risk-on runs ended | Runs |")
    L.append("|---|---:|")
    for c, n in H["cases"].items():
        L.append(f"| {c.replace('_', ' ')} | {n} |")
    L.append("")
    L.append(f"BTC broke first: {_f(H['btc_first'])}. Ended without BTC breaking first: {_f(H['without_btc_first'])}. "
             f"Lead: {_d(H['lead'], 'd')}. Lag: {_d(H['lag'], 'd')}.")
    L.append("")
    E = res["break_events"]
    L.append("| Band break while risk-on | Day | Share | Change 10d | Change 30d | Ended 30d | Ended 60d | BTC 30d | Alt 30d | BTC 60d | Alt 60d |")
    L.append("|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|")
    yn = lambda v: "" if v is None else ("yes" if v else "no")
    num = lambda v, s="": "" if v is None else f"{v:+.1f}{s}"
    for i, r in enumerate(E["rows"], 1):
        L.append(f"| {i} | {_date(r['day'])} | {100 * r['share']:.1f}% | {num(r['change10'])} | {num(r['change30'])} | "
                 f"{yn(r['ended30'])} | {yn(r['ended60'])} | {num(r['btc30'], '%')} | {num(r['alt30'], '%')} | "
                 f"{num(r['btc60'], '%')} | {num(r['alt60'], '%')} |")
    L.append("")
    es, cmp_ = E["summary"], E["comparison"]
    L.append("| After a band break while risk-on | Events | All days 55%+ with BTC holding (days overlap) |")
    L.append("|---|---|---|")
    for h in HORIZONS:
        c = cmp_[str(h)]
        L.append(f"| Run ended within {h} days | {_f(es[f'ended{h}'])} | {_f(c['ended'])} |")
        L.append(f"| BTC {h}d | {_d(es[f'btc{h}'])} | {_d(c['btc'])} |")
        L.append(f"| Typical alt {h}d | {_d(es[f'alt{h}'])} | {_d(c['alt'])} |")
    for h in CHANGE_H:
        L.append(f"| Uptrend share change {h}d (points) | {_d(es[f'change{h}'], 'd')} | |")
    L.append("")
    A = res["analogs"]
    L.append("| Analogs | Set A (full match) | Set B (breadth bucket only) | All in-sample days (overlap) |")
    L.append("|---|---|---|---|")
    for h in map(str, HORIZONS):
        a, b, c = A["A"]["summary"][h], A["B"]["summary"][h], A["all_days"][h]
        L.append(f"| {h}d: episodes | {a['n']} | {b['n']} | {c['n']} days |")
        L.append(f"| {h}d: Uptrend share reached 90% | {_f(a['reached90'])} | {_f(b['reached90'])} | {_f(c['reached90'])} |")
        L.append(f"| {h}d: run ended | {_f(a['ended'])} | {_f(b['ended'])} | {_f(c['ended'])} |")
        L.append(f"| {h}d: BTC | {_d(a['btc'])} | {_d(b['btc'])} | {_d(c['btc'])} |")
        L.append(f"| {h}d: typical alt | {_d(a['alt'])} | {_d(b['alt'])} | {_d(c['alt'])} |")
    L.append("")
    for key in ("A", "B"):
        L.append(f"| Set {key} episode | Share | Reached 90% 30d | Ended 30d | BTC 30d | Alt 30d | Reached 90% 60d | Ended 60d | BTC 60d | Alt 60d |")
        L.append("|---|---:|---|---|---:|---:|---|---|---:|---:|")
        for r in A[key]["rows"]:
            cells = []
            for h in map(str, HORIZONS):
                o = r["fwd"].get(h)
                cells += ["", "", "", ""] if not o else [yn(o["reached90"]), yn(o["ended"]), num(o["btc"], "%"), num(o["alt"], "%")]
            L.append(f"| {_date(r['day'])} | {100 * r['share']:.1f}% | " + " | ".join(cells) + " |")
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _commit() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                       cwd=Path(__file__).resolve().parent).strip()
    except Exception:
        return None


def _api(src: Optional[str]) -> dict:
    if src and not src.startswith("http"):
        return json.loads(Path(src).read_text())
    with urllib.request.urlopen(src or API_URL, timeout=60) as r:
        return json.loads(r.read())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", nargs="?", choices=["insample", "oos"])
    ap.add_argument("--sample", choices=["in", "out", "all"])
    ap.add_argument("--out", help="write the results as JSON here")
    ap.add_argument("--insample", help="in-sample results JSON (required for out and all)")
    ap.add_argument("--api", help="path or URL of an /api/market-history snapshot (default: production)")
    ap.add_argument("--rebuild", help="rebuild JSON (default data/larsson_runs/breadth_history.json)")
    ap.add_argument("--weekday", choices=["sunday", "wednesday"], default="sunday",
                    help="weekly close of the BTC band (declared: sunday; wednesday = market_history.btc_band)")
    ap.add_argument("--markdown", action="store_true", help="print the report tables")
    args = ap.parse_args(argv)
    stage = {"insample": "in", "oos": "out"}.get(args.stage)
    if stage and args.sample and stage != args.sample:
        ap.error("stage and --sample disagree")
    sample = stage or args.sample or "in"
    if sample != "in" and not args.insample:
        ap.error("the out-of-sample and all stages need --insample (the committed in-sample results)")

    api = _api(args.api)
    m = Market.load(args.rebuild, SUNDAY if args.weekday == "sunday" else WEDNESDAY, api)
    today = today_state(m)
    meta = {"stage": sample, "commit": _commit(), "weekday": args.weekday, "api": m.api_info,
            "rebuild_last": m.rebuild_last, "end_day": END_DAY}

    if sample == "in":
        res = describe(Sample(m, END_DAY), today)
    else:
        ins = json.loads(Path(args.insample).read_text())
        # The analog buckets stay those chosen at the in-sample stage.
        today = {k: ins["now"][k] for k in ("day", "share", "above", "bucket", "start", "age", "age_bucket",
                                            "btc_side", "btc_holding", "btc", "band")}
        full = describe(Sample(m, OOS_END_DAY), today)
        res = full if sample == "all" else {"out_of_sample": out_of_sample(full, ins), "full": full}
        # Where we are now, with every day to today (the API's days included)
        cur = [d for d in sorted(m.share) if d >= today["start"]]
        allb = band_breaks(m.btc, m.band)
        pk = max(m.share[d] for d in cur)
        res["now_full"] = {"last_day": cur[-1], "share": m.share[cur[-1]], "start": today["start"],
                           "age": cur[-1] - today["start"], "peak": pk,
                           "peak_day": cur[[m.share[d] for d in cur].index(pk)],
                           "reached85": pk >= .85, "reached95": pk >= .95,
                           "band_breaks": [d for d in allb if d >= today["start"]]}
    res["meta"] = meta
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1))
    if args.markdown and sample != "out":
        print(markdown(res))
    t = res.get("now") or res["full"]["now"]
    print(f"today {_date(t['day'])}: Uptrend share {round(100 * t['share'])}%, BTC {t['btc_side']} its band, "
          f"run since {_date(t['start'])} ({t['age']} days)", file=sys.stderr)
    return res


if __name__ == "__main__":
    main()
