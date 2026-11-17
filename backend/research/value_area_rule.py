"""
The 80% rule on crypto days (docs/reviews/value-area-rule-study.md, declared before running).

The claim: when a day opens outside the previous day's value area, and price comes back inside and is accepted
there, it goes on to the other edge of that value area about 80% of the time. This measures it on Binance USD-M
perpetuals and UTC days, with the same value-area code the coin chart's Value layer draws
(engines/auction_engine.session_levels). Context, not a signal, unless a declared bar is met.

Run from backend/:

  python -m research.value_area_rule fetch                    (public 5-minute candles from data.binance.vision)
  python -m research.value_area_rule shape [--out JSON]       (counts only: no outcome is computed)
  python -m research.value_area_rule power --shape JSON       (the bars on made-up outcomes)
  python -m research.value_area_rule run [--holdout] [--out JSON]

The candles are cached under backend/data/value_area_cache/ (not kept in the repository; `shape` prints their hash).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from backtest.binance_history import _get
from engines import auction_engine as ae

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
           "SOLUSDT", "LTCUSDT", "LINKUSDT", "DOTUSDT", "AVAXUSDT", "BCHUSDT")
ARCHIVE = "https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{sym}-5m-{ym}.zip"
FIRST_MONTH, LAST_MONTH = "2020-12", "2026-10"
IN_SAMPLE = ("2021-01-01", "2026-04-30")
HOLDOUT = ("2026-05-01", "2026-10-31")
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "value_area_cache"

DAY_MS = ae.DAY_MS
BAR_MS = 300_000
HALF_HOUR_MS = 1_800_000
HOUR_MS = 3_600_000
MIN_BARS = 285            # of 288 five-minute candles: both the profile's day and the event day
STEP_FRACTION = ae.STEP_FRACTION["day"]
NEED = 2                  # closes inside the value area in a row
# The two declared readings of "accepted back inside": the textbook's two half-hour periods, and the one
# half-hour close Chart Champions' own guide gives as its sign of acceptance.
READINGS = {"two_closes": 2, "one_close": 1}
COST = 0.002              # 10 bps a side, all in (the repo's convention)

# The bars (docs/reviews/value-area-rule-study.md).
MIN_EVENTS, MIN_DAYS = 200, 100
CLAIM_RATE, CLAIM_LOW, CLAIM_HALF = 0.75, 0.70, 0.70
EDGE_POINTS = 0.10        # the rule's rate over the control's
DRAWS = 10_000
RNG_SEED = 20261116
HOURS = ((0, 6), (6, 12), (12, 18), (18, 24))


def _ms(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def months(first: str = FIRST_MONTH, last: str = LAST_MONTH) -> List[str]:
    y, m = map(int, first.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def parse_month(raw: bytes) -> np.ndarray:
    """Rows (open time ms, open, high, low, close, volume, taker buy volume) of one monthly archive."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode()
    rows = []
    for line in text.splitlines():
        f = line.split(",")
        if not f[0].isdigit():
            continue                                    # a header line (newer files have one)
        t = int(f[0])
        rows.append((t // 1000 if t > 10 ** 14 else t, float(f[1]), float(f[2]), float(f[3]), float(f[4]),
                     float(f[5]), float(f[9])))
    return np.array(rows, dtype=np.float64)


def fetch(symbols=SYMBOLS, cache: Path = CACHE_DIR, workers: int = 8) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    report = {}
    for sym in symbols:
        def one(ym: str):
            try:
                return ym, parse_month(_get(ARCHIVE.format(sym=sym, ym=ym)))
            except Exception as exc:                      # a month the archive does not have
                return ym, str(exc)
        with ThreadPoolExecutor(workers) as pool:
            got = list(pool.map(one, months()))
        missing = [ym for ym, a in got if isinstance(a, str)]
        a = np.vstack([a for _, a in got if not isinstance(a, str) and len(a)])
        a = a[np.argsort(a[:, 0], kind="stable")]
        a = a[np.concatenate(([True], np.diff(a[:, 0]) > 0))]
        np.savez_compressed(cache / f"{sym}-5m.npz", ts=a[:, 0].astype(np.int64), open=a[:, 1], high=a[:, 2],
                            low=a[:, 3], close=a[:, 4], volume=a[:, 5], taker=a[:, 6])
        report[sym] = {"bars": int(len(a)), "from": iso(int(a[0, 0])), "to": iso(int(a[-1, 0])), "missing_months": missing}
        print(sym, report[sym], flush=True)
    return report


def load(sym: str, cache: Path = CACHE_DIR) -> Dict[str, np.ndarray]:
    with np.load(cache / f"{sym}-5m.npz") as z:
        return {k: z[k] for k in z.files}


def data_hash(symbols=SYMBOLS, cache: Path = CACHE_DIR) -> str:
    h = hashlib.sha256()
    for sym in symbols:
        d = load(sym, cache)
        for k in ("ts", "open", "high", "low", "close", "volume"):
            h.update(np.ascontiguousarray(d[k]).tobytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Events (everything known at the event's time; no outcome)
# ---------------------------------------------------------------------------

def buckets(ts: np.ndarray, close: np.ndarray, day_start: int, bucket_ms: int = HALF_HOUR_MS):
    """Per bucket of the day: its close (nan when it has no candle) and its first and last candle index."""
    n = DAY_MS // bucket_ms
    b = ((ts - day_start) // bucket_ms).astype(np.int64)
    i = np.arange(len(ts))
    closes, first, last = np.full(n, np.nan), np.full(n, -1), np.full(n, -1)
    closes[b] = close                    # repeated indices: the last candle of the bucket wins
    last[b] = i
    first[b[::-1]] = i[::-1]
    return closes, first, last


def accepted(inside: np.ndarray, start: int, need: int = NEED) -> Optional[int]:
    """The first bucket, from ``start`` on, that completes ``need`` closes inside in a row."""
    run = 0
    for k in range(max(start, 0), len(inside)):
        run = run + 1 if inside[k] else 0
        if run >= need:
            return k
    return None


def find_event(day: dict, vah: float, val: float, bucket_ms: int = HALF_HOUR_MS, need: int = NEED) -> dict:
    """What the day did against the previous day's value area, up to the acceptance back inside.

    ``day``: the event day's 5-minute candles (ts, open, high, low, close) and ``start`` (ms).
    kind "rule": the day opened outside the value area. kind "control": it opened inside, a bucket closed
    outside, and price came back. state "event": ``need`` buckets in a row closed back inside before the other
    edge was touched (since the open for the rule, since the bucket that closed outside for the control).
    side +1: the excursion was above the value area (the trade is a short towards VAL); -1: below.
    """
    closes, first, last = buckets(day["ts"], day["close"], day["start"], bucket_ms)
    inside = (closes >= val) & (closes <= vah)
    o = float(day["open"][0])
    if o > vah or o < val:
        kind, side, begin, search = "rule", (1 if o > vah else -1), 0, 0
    else:
        kind = "control"
        out = np.flatnonzero((closes > vah) | (closes < val))
        if not out.size:
            return {"kind": kind, "state": "stayed_inside", "side": 0}
        j = int(out[0])
        side, begin, search = (1 if closes[j] > vah else -1), int(first[j]), j + 1
    k = accepted(inside, search, need)
    if k is None:
        return {"kind": kind, "state": "no_acceptance", "side": side}
    end = int(last[k])
    hi, lo = float(day["high"][begin:end + 1].max()), float(day["low"][begin:end + 1].min())
    if (lo <= val) if side > 0 else (hi >= vah):
        return {"kind": kind, "state": "crossed_first", "side": side}
    return {"kind": kind, "state": "event", "side": side, "bucket": int(k), "end": end,
            "t": int(day["start"] + (k + 1) * bucket_ms), "entry": float(closes[k]), "extreme": hi if side > 0 else lo}


def day_pairs(d: Dict[str, np.ndarray], first_ms: int, last_ms: int):
    """(previous day's slice, event day's slice, event day's start) for event days in [first, last] with both
    days nearly complete."""
    day = d["ts"] // DAY_MS
    days, start, count = np.unique(day, return_index=True, return_counts=True)
    for i in range(1, len(days)):
        t = int(days[i]) * DAY_MS
        if t < first_ms or t > last_ms or days[i] != days[i - 1] + 1:
            continue
        if count[i] < MIN_BARS or count[i - 1] < MIN_BARS:
            continue
        yield slice(start[i - 1], start[i - 1] + count[i - 1]), slice(start[i], start[i] + count[i]), t


def events_of(sym: str, d: Dict[str, np.ndarray], first: str, last: str, bucket_ms: int = HALF_HOUR_MS,
              need: int = NEED) -> List[dict]:
    """One row per valid day of one coin: the previous day's levels and what the day did (find_event)."""
    rows = []
    for prev, cur, t in day_pairs(d, _ms(first), _ms(last)):
        if not d["volume"][prev].sum() > 0:
            continue
        ref = float(d["close"][prev][-1])
        step = ae.nice_step(ref * STEP_FRACTION)
        poc, vah, val = ae.session_levels(d["high"][prev], d["low"][prev], d["volume"][prev], step)
        if not vah > val:
            continue
        day = {"start": t, **{k: d[k][cur] for k in ("ts", "open", "high", "low", "close")}}
        ev = find_event(day, vah, val, bucket_ms, need)
        ev.update(sym=sym, day=t, poc=poc, vah=vah, val=val, step=step, width=(vah - val) / ref,
                  open_side=(1 if day["open"][0] > vah else -1 if day["open"][0] < val else 0))
        if ev["state"] == "event":
            ev["gi"] = cur.start + ev.pop("end")           # index of the event's last candle in the coin's arrays
            ev["day_end"] = cur.stop
        rows.append(ev)
    return rows


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

def score(d: Dict[str, np.ndarray], ev: dict) -> dict:
    """What followed an event, to the end of its UTC day (and, for one reported figure, over 24 hours).

    The trade: in at the acceptance close, towards the other edge; stop one row beyond the excursion's extreme;
    out at the other edge, at the stop (which wins when one candle holds both), or at the day's last close.
    """
    side, entry = ev["side"], ev["entry"]
    target = ev["val"] if side > 0 else ev["vah"]
    stop = ev["extreme"] + side * ev["step"]
    i0, i1 = ev["gi"] + 1, ev["day_end"]
    hi, lo = d["high"][i0:i1], d["low"][i0:i1]
    reach = (lo <= target) if side > 0 else (hi >= target)
    stopped = (hi >= stop) if side > 0 else (lo <= stop)
    first = lambda mask: int(np.argmax(mask)) if mask.any() else None
    r, s = first(reach), first(stopped)
    if s is not None and (r is None or s <= r):
        exit_ = stop
    elif r is not None:
        exit_ = target
    else:
        exit_ = float(d["close"][i1 - 1]) if i1 > i0 else entry
    gross = -side * (exit_ - entry) / entry
    out = {"traverse": r is not None, "minutes": None if r is None else (r + 1) * 5,
           "stopped_first": s is not None and (r is None or s <= r),
           "gross": gross, "net": gross - COST, "r": gross / (abs(stop - entry) / entry)}
    beyond = entry > ev["poc"] if side > 0 else entry < ev["poc"]
    out["poc"] = (bool(((lo <= ev["poc"]) if side > 0 else (hi >= ev["poc"])).any()) if beyond else None)
    j = int(np.searchsorted(d["ts"], ev["t"] + DAY_MS))
    hi24, lo24 = d["high"][i0:j], d["low"][i0:j]
    out["traverse_24h"] = bool(((lo24 <= target) if side > 0 else (hi24 >= target)).any())
    return out


# ---------------------------------------------------------------------------
# Statistics: days are the unit (the coins move together on a day)
# ---------------------------------------------------------------------------

def by_day(rows: List[dict], key: str):
    """Per event day: the sum of ``key`` and the number of events."""
    days = sorted({r["day"] for r in rows})
    at = {t: i for i, t in enumerate(days)}
    num, den = np.zeros(len(days)), np.zeros(len(days))
    for r in rows:
        num[at[r["day"]]] += float(r[key])
        den[at[r["day"]]] += 1
    return days, num, den


def resampled(num: np.ndarray, den: np.ndarray, draws: int = DRAWS, seed: int = RNG_SEED) -> np.ndarray:
    """The pooled ratio on ``draws`` resamples of the days."""
    rng = np.random.default_rng(seed)
    n, out = len(num), []
    for _ in range(0, draws, 500):
        idx = rng.integers(0, n, size=(500, n))
        out.append(num[idx].sum(1) / den[idx].sum(1))
    return np.concatenate(out)[:draws]


def ratio(rows: List[dict], key: str, draws: int = DRAWS) -> dict:
    """The pooled mean of ``key`` over events, with a 95% interval from resampling days, and by half."""
    if not rows:
        return {"n": 0, "days": 0}
    days, num, den = by_day(rows, key)
    half = len(days) // 2
    part = lambda a, b: float(num[a:b].sum() / den[a:b].sum()) if den[a:b].sum() else None
    sims = resampled(num, den, draws) if len(days) > 1 else np.array([num.sum() / den.sum()])
    return {"n": int(den.sum()), "days": len(days), "value": float(num.sum() / den.sum()),
            "low": float(np.percentile(sims, 2.5)), "high": float(np.percentile(sims, 97.5)),
            "first_half": part(0, half), "second_half": part(half, len(days)),
            "split_day": iso(days[half]) if len(days) > 1 else None}


def difference(a: List[dict], b: List[dict], key: str, draws: int = DRAWS) -> dict:
    """Pooled mean of ``key`` in a minus in b, resampling the days either has, and by half of those days."""
    days = sorted({r["day"] for r in a} | {r["day"] for r in b})
    at = {t: i for i, t in enumerate(days)}
    m = np.zeros((4, len(days)))
    for row, rows in ((0, a), (2, b)):
        for r in rows:
            m[row, at[r["day"]]] += float(r[key])
            m[row + 1, at[r["day"]]] += 1
    diff = lambda x: x[0].sum(-1) / x[1].sum(-1) - x[2].sum(-1) / x[3].sum(-1)
    rng = np.random.default_rng(RNG_SEED)
    sims = []
    for _ in range(0, draws, 500):
        idx = rng.integers(0, len(days), size=(500, len(days)))
        sims.append(diff(m[:, idx]))
    sims = np.concatenate(sims)
    half = len(days) // 2
    return {"value": float(diff(m)), "low": float(np.percentile(sims, 2.5)), "high": float(np.percentile(sims, 97.5)),
            "first_half": float(diff(m[:, :half])), "second_half": float(diff(m[:, half:]))}


def claim_bar(st: dict) -> dict:
    """R1: the rule's events went on to the other edge about as often as claimed."""
    checks = {
        "events": st["n"] >= MIN_EVENTS and st["days"] >= MIN_DAYS,
        "rate": st.get("value", 0) >= CLAIM_RATE,
        "interval": st.get("low", 0) >= CLAIM_LOW,
        "halves": min(st.get("first_half") or 0, st.get("second_half") or 0) >= CLAIM_HALF,
    }
    return {"checks": checks, "met": all(checks.values())}


def edge_bar(rule: dict, control: dict, diff: dict) -> dict:
    """R2: opening outside adds to coming back inside."""
    checks = {
        "events": min(rule["n"], control["n"]) >= MIN_EVENTS and min(rule["days"], control["days"]) >= MIN_DAYS,
        "gap": diff["value"] >= EDGE_POINTS,
        "interval": diff["low"] > 0,
        "halves": min(diff["first_half"], diff["second_half"]) > 0,
    }
    return {"checks": checks, "met": all(checks.values())}


def trade_bar(net: dict, btc: dict) -> dict:
    """R3: the trade paid after costs."""
    checks = {
        "events": net["n"] >= MIN_EVENTS and net["days"] >= MIN_DAYS,
        "mean": net.get("value", -1) > 0,
        "interval": net.get("low", -1) > 0,
        "halves": min(net.get("first_half") or -1, net.get("second_half") or -1) > 0,
        "btc": btc.get("value", -1) > 0,
    }
    return {"checks": checks, "met": all(checks.values())}


# ---------------------------------------------------------------------------
# The study
# ---------------------------------------------------------------------------

def all_rows(first: str, last: str, cache: Path = CACHE_DIR, symbols=SYMBOLS, bucket_ms: int = HALF_HOUR_MS,
             need: int = NEED, with_outcomes: bool = False) -> List[dict]:
    rows = []
    for sym in symbols:
        d = load(sym, cache)
        got = events_of(sym, d, first, last, bucket_ms, need)
        if with_outcomes:
            for ev in got:
                if ev["state"] == "event":
                    ev.update(score(d, ev))
        rows += got
    return rows


def shape(first: str = IN_SAMPLE[0], last: str = IN_SAMPLE[1], cache: Path = CACHE_DIR, symbols=SYMBOLS) -> dict:
    """Counts only, for each reading of "accepted". Nothing after an event's time is read."""
    out = {"period": [first, last], "data_sha256": data_hash(symbols, cache), "readings": {}}
    for name, need in READINGS.items():
        rows = all_rows(first, last, cache, symbols, need=need)
        count = lambda sel: sum(1 for r in rows if sel(r))
        block = {"coin_days": len(rows), "by_coin": {},
                 "open": {"above": count(lambda r: r["open_side"] > 0), "inside": count(lambda r: r["open_side"] == 0),
                          "below": count(lambda r: r["open_side"] < 0)}}
        for kind in ("rule", "control"):
            mine = [r for r in rows if r["kind"] == kind]
            ev = [r for r in mine if r["state"] == "event"]
            per_day: Dict[int, int] = {}
            for r in ev:
                per_day[r["day"]] = per_day.get(r["day"], 0) + 1
            hours = [(r["t"] - r["day"] - 1) // HOUR_MS for r in ev]
            block[kind] = {
                "coin_days": len(mine),
                "states": {st: sum(1 for r in mine if r["state"] == st) for st in sorted({r["state"] for r in mine})},
                "events": len(ev), "event_days": len(per_day),
                "above": sum(1 for r in ev if r["side"] > 0), "below": sum(1 for r in ev if r["side"] < 0),
                "by_hour": {f"{a:02d}-{b:02d}": sum(1 for h in hours if a <= h < b) for a, b in HOURS},
                "per_day": [per_day[t] for t in sorted(per_day)],
            }
        widths = np.array([r["width"] for r in rows])
        block["width_pct"] = {q: round(float(np.percentile(widths, q)) * 100, 2) for q in (10, 25, 50, 75, 90)}
        for sym in symbols:
            mine = [r for r in rows if r["sym"] == sym]
            block["by_coin"][sym] = {"days": len(mine),
                                     "rule_events": sum(1 for r in mine if r["kind"] == "rule" and r["state"] == "event"),
                                     "control_events": sum(1 for r in mine if r["kind"] == "control" and r["state"] == "event")}
        out["readings"][name] = block
    return out


def thirds(rows: List[dict], key: str):
    cuts = np.percentile([r[key] for r in rows], [100 / 3, 200 / 3]) if rows else (0, 0)
    return [("narrow", lambda r: r[key] <= cuts[0]), ("middle", lambda r: cuts[0] < r[key] <= cuts[1]),
            ("wide", lambda r: r[key] > cuts[1])]


def reading_block(rows: List[dict], symbols, draws: int) -> dict:
    """The three declared rows and the reported breakdowns for one reading of "accepted"."""
    rule = [r for r in rows if r["kind"] == "rule" and r["state"] == "event"]
    control = [r for r in rows if r["kind"] == "control" and r["state"] == "event"]
    r1 = ratio(rule, "traverse", draws)
    ctl = ratio(control, "traverse", draws)
    gap = difference(rule, control, "traverse", draws)
    net = ratio(rule, "net", draws)
    btc = ratio([r for r in rule if r["sym"] == "BTCUSDT"], "net", draws)
    out = {"R1": {"rule": r1, **claim_bar(r1)},
           "R2": {"rule": r1, "control": ctl, "difference": gap, **edge_bar(r1, ctl, gap)},
           "R3": {"net": net, "btc_net": btc, **trade_bar(net, btc)}}
    keep = ("n", "days", "value", "low", "high")
    brief = lambda sel, key="traverse": {k: v for k, v in ratio([r for r in rule if sel(r)], key, 2000).items() if k in keep}
    reached = [r["minutes"] for r in rule if r["traverse"]]
    out["reported"] = {
        "trade": {"gross": ratio(rule, "gross", draws), "r_multiple": ratio(rule, "r", draws),
                  "stopped_first": ratio(rule, "stopped_first", 2000), "control_net": ratio(control, "net", draws),
                  "minutes_to_edge_median": float(np.median(reached)) if reached else None},
        "poc_first": ratio([{**r, "poc": float(r["poc"])} for r in rule if r["poc"] is not None], "poc", 2000),
        "within_24h": ratio(rule, "traverse_24h", 2000),
        "by_side": {"above": brief(lambda r: r["side"] > 0), "below": brief(lambda r: r["side"] < 0)},
        "by_side_net": {"above": brief(lambda r: r["side"] > 0, "net"), "below": brief(lambda r: r["side"] < 0, "net")},
        "by_hour": {f"{a:02d}-{b:02d}": brief(lambda r, a=a, b=b: a <= (r["t"] - r["day"] - 1) // HOUR_MS < b) for a, b in HOURS},
        "by_hour_net": {f"{a:02d}-{b:02d}": brief(lambda r, a=a, b=b: a <= (r["t"] - r["day"] - 1) // HOUR_MS < b, "net") for a, b in HOURS},
        "by_width": {name: brief(sel) for name, sel in thirds(rule, "width")},
        "by_width_net": {name: brief(sel, "net") for name, sel in thirds(rule, "width")},
        "by_coin": {sym: brief(lambda r, sym=sym: r["sym"] == sym) for sym in symbols},
        "by_coin_net": {sym: brief(lambda r, sym=sym: r["sym"] == sym, "net") for sym in symbols},
        "by_year": {y: brief(lambda r, y=y: iso(r["day"])[:4] == y) for y in sorted({iso(r["day"])[:4] for r in rule})},
        "by_year_net": {y: brief(lambda r, y=y: iso(r["day"])[:4] == y, "net") for y in sorted({iso(r["day"])[:4] for r in rule})},
    }
    return out


def run_study(first: str, last: str, cache: Path = CACHE_DIR, symbols=SYMBOLS, draws: int = DRAWS) -> dict:
    out = {"period": [first, last], "data_sha256": data_hash(symbols, cache), "readings": {}}
    rows = []
    for name, need in READINGS.items():
        rows = all_rows(first, last, cache, symbols, need=need, with_outcomes=True)
        out["readings"][name] = reading_block(rows, symbols, draws)
    out["coin_days"] = len(rows)
    keep = ("n", "days", "value", "low", "high")
    # One hourly close inside (the form in the outline the owner supplied): reported only.
    hourly = [r for r in all_rows(first, last, cache, symbols, HOUR_MS, 1, with_outcomes=True)
              if r["kind"] == "rule" and r["state"] == "event"]
    out["one_hour_close"] = {"traverse": {k: v for k, v in ratio(hourly, "traverse", 2000).items() if k in keep},
                             "net": {k: v for k, v in ratio(hourly, "net", 2000).items() if k in keep}}
    # Every day, whatever it did: how often the day touched both edges of the previous day's value area.
    both = []
    found = {(r["sym"], r["day"]): r for r in rows}
    for sym in symbols:
        d = load(sym, cache)
        for prev, cur, t in day_pairs(d, _ms(first), _ms(last)):
            row = found.get((sym, t))
            if row:
                both.append({"day": t, "both": float(d["high"][cur].max() >= row["vah"] and d["low"][cur].min() <= row["val"]),
                             "open_side": row["open_side"]})
    part = lambda sel: {k: v for k, v in ratio([b for b in both if sel(b)], "both", 2000).items() if k in ("n", "days", "value")}
    out["all_days_touch_both_edges"] = {"all": part(lambda b: True), "opened_outside": part(lambda b: b["open_side"] != 0),
                                        "opened_inside": part(lambda b: b["open_side"] == 0)}
    return out


def power(shape_json: dict, reps: int = 2000, spread: float = 0.015) -> dict:
    """How often each bar is met on made-up outcomes with this study's event counts per day.

    Two cases for events on one day: independent, and all sharing one outcome (the coins moving as one).
    The interval here is the normal approximation of the day-resampling interval (far cheaper to simulate).
    """
    rng = np.random.default_rng(RNG_SEED)
    counts = shape_json["readings"]["two_closes"]
    per_rule = np.array(counts["rule"]["per_day"], dtype=float)
    per_ctl = np.array(counts["control"]["per_day"], dtype=float)

    def draw_rate(per, p, shared):
        if shared:
            return rng.random(len(per)) < p
        return rng.binomial(per.astype(int), p) / per

    def summary(num, den):
        v = num.sum() / den.sum()
        se = np.sqrt(((num - v * den) ** 2).sum()) / den.sum()
        h = len(num) // 2
        return v, v - 1.96 * se, num[:h].sum() / den[:h].sum(), num[h:].sum() / den[h:].sum(), se

    out = {"R1": {}, "R2": {}, "R3": {}, "events": int(per_rule.sum()), "days": len(per_rule), "spread": spread}
    for shared in (False, True):
        tag = "one outcome a day" if shared else "independent"
        out["R1"][tag] = {}
        for p in (0.60, 0.65, 0.70, 0.75, 0.78, 0.80, 0.85):
            met = 0
            for _ in range(reps):
                v, lo, a, b, _ = summary(draw_rate(per_rule, p, shared) * per_rule, per_rule)
                met += v >= CLAIM_RATE and lo >= CLAIM_LOW and min(a, b) >= CLAIM_HALF
            out["R1"][tag][p] = round(met / reps, 3)
        out["R2"][tag] = {}
        for gap in (0.0, 0.05, 0.10, 0.15, 0.20):
            met = 0
            for _ in range(reps):
                v, _, a, b, se = summary(draw_rate(per_rule, 0.55 + gap, shared) * per_rule, per_rule)
                w, _, c, e, se2 = summary(draw_rate(per_ctl, 0.55, shared) * per_ctl, per_ctl)
                d = v - w
                met += d >= EDGE_POINTS and d - 1.96 * np.hypot(se, se2) > 0 and min(a - c, b - e) > 0
            out["R2"][tag][gap] = round(met / reps, 3)
        out["R3"][tag] = {}
        for mean in (0.0, 0.0005, 0.001, 0.002, 0.003):
            met = 0
            for _ in range(reps):
                if shared:
                    num = rng.normal(mean, spread, len(per_rule)) * per_rule
                else:
                    num = rng.normal(mean * per_rule, spread * np.sqrt(per_rule))
                v, lo, a, b, _ = summary(num, per_rule)
                met += v > 0 and lo > 0 and min(a, b) > 0
            out["R3"][tag][mean] = round(met / reps, 3)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "shape", "power", "run"):
        p = sub.add_parser(name)
        p.add_argument("--cache", type=Path, default=CACHE_DIR)
        p.add_argument("--out", type=Path)
        if name == "power":
            p.add_argument("--shape", type=Path, required=True)
            p.add_argument("--spread", type=float, default=0.015)
        if name == "run":
            p.add_argument("--holdout", action="store_true", help="the held-out months instead of the in-sample period")
            p.add_argument("--from", dest="first"), p.add_argument("--to", dest="last")
    a = ap.parse_args()
    if a.cmd == "fetch":
        res = fetch(cache=a.cache)
    elif a.cmd == "shape":
        res = shape(cache=a.cache)
    elif a.cmd == "power":
        res = power(json.loads(a.shape.read_text()), spread=a.spread)
    else:
        first, last = HOLDOUT if a.holdout else IN_SAMPLE
        res = run_study(a.first or first, a.last or last, cache=a.cache)
    text = json.dumps(res, indent=1, default=float)
    if a.out:
        a.out.write_text(text)
    if a.cmd != "fetch":
        if a.cmd == "shape":
            res = {**res, "readings": {n: {**b, "rule": {**b["rule"], "per_day": "..."}, "control": {**b["control"], "per_day": "..."}}
                                       for n, b in res["readings"].items()}}
        json.dump(res, sys.stdout, indent=1, default=float)
        print()


if __name__ == "__main__":
    main()
