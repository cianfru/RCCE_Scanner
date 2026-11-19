"""
After a perp's funding first turns extremely negative, does its price spike up more often than at ordinary times?
(docs/reviews/negative-funding-study.md, declared before any outcome was computed)

Two venues, read the same way:
  hl  Hyperliquid perps (main dex, listed and delisted): hourly funding (fundingHistory) and 4h candles.
  bn  Binance USDT-margined perps (listed and delisted): funding and 4h klines from the public monthly archive
      (data.binance.vision).

Run from backend/:

  python -m research.negative_funding fetch-bn            (resumable; about 20 minutes)
  python -m research.negative_funding fetch-hl            (resumable; about 2.5 hours at ~1,100 weight a minute)
  python -m research.negative_funding status
  python -m research.negative_funding counts              (events per venue and threshold: no outcome is read)
  python -m research.negative_funding run --venue bn|hl [--out JSON]

Nothing here runs on the production server.
"""
from __future__ import annotations

import argparse
import bisect
import calendar
import csv
import io
import json
import re
import sys
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

# --- declared rules (docs/reviews/negative-funding-study.md) ---------------------------------------
HOUR = 3600
STEP = 4 * HOUR                      # candles
THRESH = -0.001                      # -0.1% an hour (about -876% a year)
THRESH_2 = -0.002                    # -0.2% an hour (about -1,750% a year): secondary
POS_THRESH = 0.001                   # +0.1% an hour: the mirror, context only
GAP_H = 168                          # a new episode: no print at or past the threshold in the 7 days before
HORIZONS_H = (24, 72, 168)
SPIKE, DROP = 0.30, -0.30            # within 7 days: a high 30%+ above entry, a low 30%+ below
MIN_EVENTS = 30
BAR_RATIO = 2.0                      # spike share at least twice the comparison's
BAR_P = 0.01


def ts(s: str) -> int:
    return calendar.timegm(time.strptime(s, "%Y-%m-%d"))


DATA_START = ts("2025-11-01")       # data read: November 2025 to October 2026 (Binance's monthly files)
DATA_END = ts("2026-11-01")
EV_START = DATA_START + GAP_H * HOUR  # 8 November 2025: events need 7 days of funding before them
EV_END = DATA_END - GAP_H * HOUR      # 25 October 2026: and 7 days of price after them
MONTHS = [f"{y}-{m:02d}" for y, m in [(2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 11)]]

CACHE = Path(__file__).resolve().parent.parent / "data" / "negative_funding_cache"

Prints = List[Tuple[int, float, float]]          # (time s, rate per interval, interval hours)
Candles = List[Tuple[int, float, float, float, float]]   # (open time s, open, high, low, close), 4h


# --- events and outcomes -----------------------------------------------------------------------------

def per_hour(p: Tuple[int, float, float]) -> float:
    return p[1] / p[2]


def hits(p, thresh: float) -> bool:
    return per_hour(p) <= thresh if thresh < 0 else per_hour(p) >= thresh


def events(prints: Prints, thresh: float, start: int = EV_START, end: int = EV_END) -> List[int]:
    """Times of the prints at or past the threshold (per hour) with none in the GAP_H hours before, in [start, end)."""
    out, last = [], None
    for p in sorted(prints):
        if not hits(p, thresh):
            continue
        if (last is None or p[0] - last >= GAP_H * HOUR) and start <= p[0] < end:
            out.append(p[0])
        last = p[0]
    return out


def entry_index(candles: Candles, t: int) -> Optional[int]:
    """The first candle that closes at or after t."""
    closes = [c[0] + STEP for c in candles]
    i = bisect.bisect_left(closes, t)
    return i if i < len(candles) else None


class Series:
    """One coin's candles and funding prints, indexed for quick look-ups."""

    def __init__(self, prints: Prints, candles: Candles):
        self.prints = sorted(prints)
        self.candles = sorted(candles)
        self.closes = [c[0] + STEP for c in self.candles]
        self.pt = [p[0] for p in self.prints]
        self.cum = [0.0]
        for p in self.prints:
            self.cum.append(self.cum[-1] + p[1])

    def funding_sum(self, a: int, b: int) -> float:
        """Sum of the funding rates printed in (a, b]."""
        return self.cum[bisect.bisect_right(self.pt, b)] - self.cum[bisect.bisect_right(self.pt, a)]

    def close_at(self, t: int) -> Tuple[float, bool]:
        """The close of the candle closing at t, else the last close before it (flagged when t is past the data)."""
        j = bisect.bisect_right(self.closes, t) - 1
        return self.candles[max(j, 0)][4], t > self.closes[-1]


def outcome(s: Series, i: int) -> dict:
    """From the close of candle i: returns at each horizon, the highest high and lowest low over the next 7 days, and
    the funding a long received over them (positive: received). A coin whose candles end sooner uses its last close
    and is flagged."""
    e = s.candles[i][4]
    t0 = s.closes[i]
    out = {"entry": e, "t": t0, "ended": False}
    for h in HORIZONS_H:
        c, ended = s.close_at(t0 + h * HOUR)
        out[f"r{h}"] = c / e - 1
        out["ended"] = out["ended"] or ended
    j = bisect.bisect_right(s.closes, t0 + 168 * HOUR)
    nxt = s.candles[i + 1:j]
    out["up7"] = max(c[2] for c in nxt) / e - 1 if nxt else 0.0
    out["down7"] = min(c[3] for c in nxt) / e - 1 if nxt else 0.0
    out["carry7"] = -s.funding_sum(t0, t0 + 168 * HOUR)
    return out


def ordinary(candles: Candles, prints: Prints, thresh: float, start: int = EV_START, end: int = EV_END) -> List[int]:
    """Candle indices in [start, end) whose close has no print at or past the threshold in the GAP_H hours up to it."""
    marks = sorted(p[0] for p in prints if hits(p, thresh))
    out = []
    for i, c in enumerate(candles):
        t = c[0] + STEP
        if not (start <= t < end):
            continue
        j = bisect.bisect_right(marks, t)
        if j and t - marks[j - 1] < GAP_H * HOUR:
            continue
        out.append(i)
    return out


# --- the bar --------------------------------------------------------------------------------------

def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    from math import exp, lgamma, log
    lp, lq = log(p), log(1 - p)     # in logs: the plain binomial terms overflow a float past a few hundred events
    return min(1.0, sum(exp(lgamma(n + 1) - lgamma(x + 1) - lgamma(n - x + 1) + x * lp + (n - x) * lq)
                        for x in range(k, n + 1)))


def share(xs, f) -> Optional[float]:
    return sum(1 for x in xs if f(x)) / len(xs) if xs else None


def judge(ev: List[dict], comp: List[dict]) -> dict:
    """The bar on one venue. ev: event outcomes (each with t); comp: ordinary-time outcomes of the same coins."""
    n = len(ev)
    res = {"events": n, "comparison": len(comp)}
    if n < MIN_EVENTS or not comp:
        res.update(met=False, reason="too few events")
        return res
    se, sc = share(ev, lambda o: o["up7"] >= SPIKE), share(comp, lambda o: o["up7"] >= SPIKE)
    k = sum(1 for o in ev if o["up7"] >= SPIKE)
    p = binom_sf(k, n, sc)
    me, mc = median(o["r168"] for o in ev), median(o["r168"] for o in comp)
    evs = sorted(ev, key=lambda o: o["t"])
    halves = [evs[: n // 2], evs[n // 2:]]
    hs = [share(h, lambda o: o["up7"] >= SPIKE) for h in halves]
    res.update(spike_share=se, comparison_spike_share=sc, ratio=(se / sc if sc else None), p=p,
               median_r168=me, comparison_median_r168=mc, halves_spike_share=hs)
    res["conditions"] = {"ratio": sc is not None and se >= BAR_RATIO * sc, "p": p <= BAR_P,
                         "median": me > 0 and me > mc, "halves": all(h is not None and h > sc for h in hs)}
    res["met"] = all(res["conditions"].values())
    return res


def summary(xs: List[dict]) -> dict:
    if not xs:
        return {"n": 0}
    out = {"n": len(xs)}
    for h in HORIZONS_H:
        v = sorted(o[f"r{h}"] for o in xs)
        out[f"median_r{h}"] = median(v)
        out[f"up_share_r{h}"] = share(xs, lambda o, h=h: o[f"r{h}"] > 0)
    out["spike_share"] = share(xs, lambda o: o["up7"] >= SPIKE)
    out["drop_share"] = share(xs, lambda o: o["down7"] <= DROP)
    out["median_up7"] = median(o["up7"] for o in xs)
    out["median_down7"] = median(o["down7"] for o in xs)
    out["median_carry7"] = median(o["carry7"] for o in xs)
    out["median_r168_plus_carry"] = median(o["r168"] + o["carry7"] for o in xs)
    return out


def analyse(data: Dict[str, Tuple[Prints, Candles]], thresh: float) -> dict:
    ev, comp, coins = [], [], set()
    for coin, (prints, candles) in sorted(data.items()):
        if not candles:
            continue
        ts_ = events(prints, thresh)
        if not ts_:
            continue
        coins.add(coin)
        s = Series(prints, candles)
        rate = {p[0]: per_hour(p) for p in s.prints}
        for t in ts_:
            i = entry_index(s.candles, t)
            if i is None:
                continue
            o = outcome(s, i)
            o.update(coin=coin, event_t=t, rate_per_hour=rate[t])
            ev.append(o)
        for i in ordinary(s.candles, s.prints, thresh):
            if i + 1 < len(s.candles):
                comp.append(outcome(s, i))
    days = len({o["event_t"] // 86400 for o in ev})
    return {"threshold_per_hour": thresh, "coins_with_events": len(coins), "distinct_days": days,
            "verdict": judge(ev, comp) if thresh < 0 else None,
            "events_summary": summary(ev), "comparison_summary": summary(comp),
            "events": [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in o.items()} for o in ev]}


# --- data ---------------------------------------------------------------------------------------------

def _get(url: str, data: Optional[bytes] = None, tries: int = 6):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (a + 1) if e.code == 429 else 2)
        except Exception:
            time.sleep(2 * (a + 1))
    raise RuntimeError(f"unreadable: {url}")


def _csv_rows(blob: Optional[bytes]) -> List[List[str]]:
    if not blob:
        return []
    z = zipfile.ZipFile(io.BytesIO(blob))
    text = z.read(z.namelist()[0]).decode()
    rows = list(csv.reader(io.StringIO(text)))
    return [r for r in rows if r and re.match(r"^-?\d", r[0])]     # drop the header row when there is one


def bn_symbols() -> List[str]:
    base = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/um/monthly/fundingRate/"
    out, marker = [], ""
    while True:
        xml = _get(base + (f"&marker={marker}" if marker else "")).decode()
        out += re.findall(r"<Prefix>data/futures/um/monthly/fundingRate/([^/<]+)/</Prefix>", xml)
        m = re.search(r"<NextMarker>([^<]+)</NextMarker>", xml)
        if "<IsTruncated>true</IsTruncated>" not in xml or not m:
            break
        marker = m.group(1)
    return sorted(s for s in set(out) if s.endswith("USDT"))


def bn_one(sym: str) -> Optional[dict]:
    from urllib.parse import quote
    q = quote(sym)                      # some symbols are not ASCII
    prints: Prints = []
    candles: Candles = []
    for m in MONTHS:
        for r in _csv_rows(_get(f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{q}/{q}-fundingRate-{m}.zip")):
            prints.append((int(r[0]) // 1000 // 60 * 60, float(r[2]), float(r[1])))
    if not prints:
        return None
    for m in MONTHS:
        for r in _csv_rows(_get(f"https://data.binance.vision/data/futures/um/monthly/klines/{q}/4h/{q}-4h-{m}.zip")):
            candles.append((int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4])))
    return {"prints": sorted(set(prints)), "candles": sorted(set(candles))}


def fetch_bn(workers: int = 8) -> None:
    d = CACHE / "bn"
    d.mkdir(parents=True, exist_ok=True)
    syms = bn_symbols()
    todo = [s for s in syms if not (d / f"{s}.json").exists()]
    print(f"binance: {len(syms)} USDT perps in the archive, {len(todo)} to read", flush=True)
    lock, n = threading.Lock(), [0]

    def one(s):
        got = bn_one(s)
        (d / f"{s}.json").write_text(json.dumps(got or {"prints": [], "candles": []}))
        with lock:
            n[0] += 1
            if n[0] % 50 == 0:
                print(f"binance {n[0]}/{len(todo)}", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    print("binance done", flush=True)


class Gate:
    """Hyperliquid's weight budget: about `rate` weight a minute."""

    def __init__(self, rate: int):
        self.lock, self.next, self.rate = threading.Lock(), time.time(), rate

    def wait(self, weight: float):
        with self.lock:
            t = max(self.next, time.time())
            self.next = t + 60.0 * weight / self.rate
        time.sleep(max(0.0, t - time.time()))


def hl_post(gate: Gate, body: dict, weight: float):
    gate.wait(weight)
    blob = _get("https://api.hyperliquid.xyz/info", json.dumps(body).encode())
    return json.loads(blob) if blob else []


def hl_one(gate: Gate, coin: str) -> dict:
    prints: Prints = []
    start = DATA_START * 1000
    while start < DATA_END * 1000:
        r = hl_post(gate, {"type": "fundingHistory", "coin": coin, "startTime": start, "endTime": DATA_END * 1000 - 1}, 45)
        if not r:
            break
        prints += [(int(x["time"]) // 1000 // 60 * 60, float(x["fundingRate"]), 1.0) for x in r]
        if len(r) < 500:
            break
        start = int(r[-1]["time"]) + 1
    candles: Candles = []
    if prints:
        r = hl_post(gate, {"type": "candleSnapshot", "req": {"coin": coin, "interval": "4h", "startTime": DATA_START * 1000,
                                                              "endTime": DATA_END * 1000 - 1}}, 60)
        candles = [(int(c["t"]) // 1000, float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"])) for c in r
                   if DATA_START <= int(c["t"]) // 1000 < DATA_END]
    return {"prints": sorted(set(prints)), "candles": sorted(set(candles))}


def fetch_hl(rate: int = 1100, workers: int = 3) -> None:
    d = CACHE / "hl"
    d.mkdir(parents=True, exist_ok=True)
    gate = Gate(rate)
    meta = hl_post(gate, {"type": "meta"}, 20)
    coins = [a["name"] for a in meta["universe"]]
    todo = [c for c in coins if not (d / f"{c}.json").exists()]
    print(f"hyperliquid: {len(coins)} perps, {len(todo)} to read", flush=True)
    lock, n = threading.Lock(), [0]

    def one(c):
        (d / f"{c}.json").write_text(json.dumps(hl_one(gate, c)))
        with lock:
            n[0] += 1
            if n[0] % 10 == 0:
                print(f"{time.strftime('%H:%M:%S')} hyperliquid {n[0]}/{len(todo)}", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    print("hyperliquid done", flush=True)


def load(venue: str) -> Dict[str, Tuple[Prints, Candles]]:
    out = {}
    for f in sorted((CACHE / venue).glob("*.json")):
        j = json.loads(f.read_text())
        out[f.stem] = ([tuple(p) for p in j["prints"]], [tuple(c) for c in j["candles"]])
    return out


def counts(venue: str) -> dict:
    data = load(venue)
    out = {"coins_read": len(data), "with_funding": sum(1 for p, _ in data.values() if p),
           "with_candles": sum(1 for _, c in data.values() if c)}
    for th in (THRESH, THRESH_2, POS_THRESH):
        ev = [(k, t) for k, (p, c) in data.items() if c for t in events(p, th)]
        out[f"events_{th:+.3%}_per_hour"] = {"events": len(ev), "coins": len({k for k, _ in ev}),
                                             "distinct_days": len({t // 86400 for _, t in ev})}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("fetch-bn", "fetch-hl", "status", "counts", "run"))
    ap.add_argument("--venue", choices=("bn", "hl"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--rate", type=int, default=1100)
    a = ap.parse_args(argv)
    if a.cmd == "fetch-bn":
        fetch_bn()
    elif a.cmd == "fetch-hl":
        fetch_hl(a.rate)
    elif a.cmd == "status":
        print(json.dumps({v: len(list((CACHE / v).glob("*.json"))) if (CACHE / v).exists() else 0 for v in ("bn", "hl")}))
    elif a.cmd == "counts":
        print(json.dumps({v: counts(v) for v in ([a.venue] if a.venue else ["bn", "hl"]) if (CACHE / v).exists()}, indent=1))
    else:
        data = load(a.venue)
        res = {"venue": a.venue, "primary": analyse(data, THRESH), "secondary": analyse(data, THRESH_2),
               "mirror_positive": analyse(data, POS_THRESH)}
        text = json.dumps(res, indent=1)
        if a.out:
            a.out.write_text(text)
        print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "events"})
                          for k, v in res.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
