"""
The Radar forward test (docs/reviews/radar-forward-test.md, declared 29 September 2026): events and
outcomes from the logged readings (radar_log, table radar_readings), with the declared rules.

    python -m research.radar_forward score [--db path/to/hyperlens.db] [--no-candles]   (run from backend/)

Prints a JSON report: per hypothesis the events (scored, pending, unscored), distinct coins, median
14-day excess, its 90% day-block bootstrap interval, the share beating the median coin, the 7-day
figures and the verdict ("too few" under the minimum). Outcomes use the logged daily closes; a
missing close falls back to the stored daily candles (the OHLCV store) when they are available.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from typing import Callable, Dict, Iterable, List, Optional, Tuple

DAY = 86400
H_MAIN, H_SHORT = 14, 7          # outcome horizons, days
SPACING = 14                     # days between two events of one coin in one group
PREV_WITHIN = 3                  # days back the "previous reading" may be
MIN_EVENTS, MIN_COINS = 30, 15
MIN_BENCH = 20                   # coins needed for the median coin
SHARE_BAR = 0.55
BOOT_DRAWS, BOOT_BLOCK, BOOT_SEED = 2000, 14, 20260929
ROSTER_VERSION = 2
SCHEMA_VERSION = 1
REPORT_DAYS = (30, 60, 90)
MIN_TRADERS = 3
BAND_FILL = 0.5
LATE_Z = 2.0


# ------------------------------------------------------------------ conditions (declared)
def h1(r: dict) -> bool:
    """Early setup with support: in the box, 3+ traders long, net rose on 24h, band ring half full or more."""
    return (r["zone"] == "watch" and (r["long"] or 0) >= MIN_TRADERS and r["net_24h"] is not None and r["net_24h"] > 0
            and r["band_state"] is not None and r["band_state"] != "closed_under"
            and r["band_fill"] is not None and r["band_fill"] >= BAND_FILL)


def h2_zone(r: dict) -> bool:
    return bool(r["in_zone"])


def h2_comparison(r: dict) -> bool:
    return (r["long"] or 0) >= MIN_TRADERS and not r["in_zone"]


def h3(r: dict) -> bool:
    return r["z"] is not None and r["z"] >= LATE_Z and r["crowd"] == "crowded"


# ------------------------------------------------------------------ events
def counted(rows: Iterable[dict]) -> List[dict]:
    """Readings that count: roster version 2, schema version 1."""
    return [r for r in rows if r.get("roster_version") == ROSTER_VERSION and r.get("schema_version") == SCHEMA_VERSION]


def by_coin(rows: Iterable[dict]) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for r in sorted(rows, key=lambda r: (r["coin"], r["day"])):
        out.setdefault(r["coin"], []).append(r)
    return out


def first_day_events(rows: Iterable[dict], cond: Callable[[dict], bool]) -> List[Tuple[str, int]]:
    """(coin, day) events: cond holds at the day and did not at the coin's previous reading (the one
    within PREV_WITHIN days before; with none the day only sets the baseline); SPACING days since the
    coin's previous event. A first day inside the spacing is skipped, not reconsidered."""
    out = []
    for coin, rs in by_coin(rows).items():
        last = None
        for k, r in enumerate(rs):
            if not cond(r):
                continue
            prev = rs[k - 1] if k > 0 else None
            if prev is None or r["day"] - prev["day"] > PREV_WITHIN * DAY or cond(prev):
                continue
            if last is not None and r["day"] - last < SPACING * DAY:
                continue
            out.append((coin, r["day"]))
            last = r["day"]
    return sorted(out, key=lambda e: (e[1], e[0]))


def spaced_events(rows: Iterable[dict], cond: Callable[[dict], bool]) -> List[Tuple[str, int]]:
    """(coin, day) events for H2's groups: the first reading meeting cond, then the first at least
    SPACING days after the coin's previous event in the group."""
    out = []
    for coin, rs in by_coin(rows).items():
        last = None
        for r in rs:
            if cond(r) and (last is None or r["day"] - last >= SPACING * DAY):
                out.append((coin, r["day"]))
                last = r["day"]
    return sorted(out, key=lambda e: (e[1], e[0]))


# ------------------------------------------------------------------ outcomes
class Closes:
    """Daily closes by (coin, day): the logged ones, else the stored candles."""

    def __init__(self, rows: Iterable[dict], candles: Optional[Dict[str, Dict[int, float]]] = None):
        self.logged: Dict[int, Dict[str, float]] = {}
        self.read: Dict[int, set] = {}
        for r in rows:
            self.read.setdefault(r["day"], set()).add(r["coin"])
            if r.get("close") and r["close"] > 0:
                self.logged.setdefault(r["day"], {})[r["coin"]] = float(r["close"])
        self.candles = candles or {}
        self._bench: Dict[Tuple[int, int], Optional[float]] = {}

    def get(self, coin: str, day: int) -> Optional[float]:
        v = self.logged.get(day, {}).get(coin)
        if v is None:
            v = self.candles.get(coin, {}).get(day)
        return v if v and v > 0 else None

    def ret(self, coin: str, day: int, h: int) -> Optional[float]:
        a, b = self.get(coin, day), self.get(coin, day + h * DAY)
        return None if a is None or b is None else b / a - 1

    def coins_at(self, day: int) -> set:
        return self.read.get(day, set())

    def bench(self, day: int, h: int) -> Optional[float]:
        """The median coin: median return over every coin read at day with a close at day and day + h
        (20 or more)."""
        key = (day, h)
        if key not in self._bench:
            rs = [x for x in (self.ret(c, day, h) for c in self.coins_at(day)) if x is not None]
            self._bench[key] = statistics.median(rs) if len(rs) >= MIN_BENCH else None
        return self._bench[key]

    def excess(self, coin: str, day: int, h: int) -> Optional[float]:
        r, b = self.ret(coin, day, h), self.bench(day, h)
        return None if r is None or b is None else r - b


def outcomes(events: List[Tuple[str, int]], closes: Closes, today: int, h: int) -> dict:
    """Scored (coin, day, excess) events, pending ones (window not closed) and unscored ones."""
    scored, pending, unscored = [], 0, 0
    for coin, day in events:
        if day + h * DAY > today:
            pending += 1
            continue
        x = closes.excess(coin, day, h)
        if x is None:
            unscored += 1
        else:
            scored.append((coin, day, x))
    return {"scored": scored, "pending": pending, "unscored": unscored}


# ------------------------------------------------------------------ statistics
def percentile(xs: List[float], q: float) -> float:
    """Linear interpolation between order statistics (numpy's default)."""
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def block_days(first: int, last: int, rng: random.Random, block: int = BOOT_BLOCK) -> List[int]:
    """One circular moving-block draw of calendar days from first to last (inclusive)."""
    n = (last - first) // DAY + 1
    out: List[int] = []
    while len(out) < n:
        s = rng.randrange(n)
        out.extend(first + ((s + k) % n) * DAY for k in range(block))
    return out[:n]


def bootstrap(groups: List[List[Tuple[str, int, float]]], stat: Callable[..., Optional[float]],
              draws: int = BOOT_DRAWS, seed: int = BOOT_SEED) -> Optional[Tuple[float, float]]:
    """90% interval of stat(*groups) under whole-day block resampling. Days span every group's events."""
    days = [e[1] for g in groups for e in g]
    if not days:
        return None
    first, last = min(days), max(days)
    by_day = [{} for _ in groups]
    for k, g in enumerate(groups):
        for e in g:
            by_day[k].setdefault(e[1], []).append(e)
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        picked = block_days(first, last, rng)
        drawn = [[e for d in picked for e in by_day[k].get(d, ())] for k in range(len(groups))]
        if any(not g for g in drawn):
            continue
        v = stat(*drawn)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return (percentile(vals, 0.05), percentile(vals, 0.95))


def med(g) -> Optional[float]:
    return statistics.median(e[2] for e in g) if g else None


def verdict(n: int, coins: int, m: Optional[float], interval: Optional[Tuple[float, float]], share: Optional[float],
            enough_other: bool = True) -> str:
    """The declared bars: too few / fails / holds / undecided."""
    if n < MIN_EVENTS or coins < MIN_COINS or not enough_other or m is None:
        return "too few"
    if m <= 0:
        return "fails"
    if interval is not None and interval[0] > 0 and share is not None and share > SHARE_BAR:
        return "holds"
    return "undecided"


def r4(v):
    return None if v is None else round(v, 4)


def one_group(events, closes, today, boot=True) -> dict:
    main, short = outcomes(events, closes, today, H_MAIN), outcomes(events, closes, today, H_SHORT)
    s = main["scored"]
    m = med(s)
    iv = bootstrap([s], med) if boot and s else None
    share = sum(1 for e in s if e[2] > 0) / len(s) if s else None
    return {"events": len(events), "scored": len(s), "pending": main["pending"], "unscored": main["unscored"],
            "coins": len({e[0] for e in s}), "median_excess_14d": r4(m),
            "interval_90": None if iv is None else [r4(iv[0]), r4(iv[1])], "share_beating_median_coin": r4(share),
            "median_excess_7d": r4(med(short["scored"])), "scored_7d": len(short["scored"]), "_s": s}


def report(rows: Iterable[dict], candles: Optional[Dict[str, Dict[int, float]]] = None, today: Optional[float] = None,
           boot: bool = True) -> dict:
    """The whole report from logged readings (all of them; only counted ones are used)."""
    import time as _t
    rows = list(rows)
    use = counted(rows)
    today = int((today if today is not None else _t.time()) // DAY * DAY)
    days = sorted({r["day"] for r in use})
    closes = Closes(use, candles)
    out = {"declared": "2026-09-29", "doc": "docs/reviews/radar-forward-test.md",
           "readings": len(use), "readings_not_counted": len(rows) - len(use), "days_logged": len(days),
           "first_close": days[0] if days else None, "last_close": days[-1] if days else None,
           "days_since_first": (today - days[0]) // DAY if days else 0, "min_events": MIN_EVENTS, "min_coins": MIN_COINS}
    since = out["days_since_first"]
    out["next_report_day"] = next((d for d in REPORT_DAYS if d > since), (since // 30 + 1) * 30)
    out["decisive"] = since >= REPORT_DAYS[-1]

    g1 = one_group(first_day_events(use, h1), closes, today, boot)
    g1["verdict"] = verdict(g1["scored"], g1["coins"], g1["median_excess_14d"], g1["interval_90"] and tuple(g1["interval_90"]),
                            g1["share_beating_median_coin"])
    g3 = one_group(first_day_events(use, h3), closes, today, boot)
    g3["verdict"] = "description only"

    z = one_group(spaced_events(use, h2_zone), closes, today, boot=False)
    c = one_group(spaced_events(use, h2_comparison), closes, today, boot=False)
    zs, cs = z["_s"], c["_s"]
    d = med(zs) - med(cs) if zs and cs else None
    diff = lambda a, b: med(a) - med(b)
    iv = bootstrap([zs, cs], diff) if boot and zs and cs else None
    cm = med(cs)
    share = sum(1 for e in zs if e[2] > cm) / len(zs) if zs and cm is not None else None
    h2 = {"entry_zone": z, "comparison": c, "difference_14d": r4(d), "interval_90": None if iv is None else [r4(iv[0]), r4(iv[1])],
          "share_above_comparison_median": r4(share)}
    h2["verdict"] = verdict(z["scored"], z["coins"], d, iv, share, enough_other=c["scored"] >= MIN_EVENTS)
    for g in (g1, g3, z, c):
        g.pop("_s")
    out["hypotheses"] = {"H1": g1, "H2": h2, "H3": g3}
    return out


def status(rep: dict) -> dict:
    """The compact view for /api/radar/forward-test."""
    h = rep["hypotheses"]
    return {"declared": rep["declared"], "doc": rep["doc"], "days_logged": rep["days_logged"],
            "first_close": rep["first_close"], "last_close": rep["last_close"], "days_since_first": rep["days_since_first"],
            "next_report_day": rep["next_report_day"], "min_events": rep["min_events"], "min_coins": rep["min_coins"],
            "H1": {k: h["H1"][k] for k in ("events", "scored", "pending", "coins", "median_excess_14d", "interval_90",
                                             "share_beating_median_coin", "verdict")},
            "H2": {"events": h["H2"]["entry_zone"]["events"], "scored": h["H2"]["entry_zone"]["scored"],
                   "comparison_scored": h["H2"]["comparison"]["scored"], "coins": h["H2"]["entry_zone"]["coins"],
                   "difference_14d": h["H2"]["difference_14d"], "interval_90": h["H2"]["interval_90"], "verdict": h["H2"]["verdict"]},
            "H3": {k: h["H3"][k] for k in ("events", "scored", "median_excess_14d", "verdict")}}


# ------------------------------------------------------------------ command line
def store_candles(coins: Iterable[str]) -> Dict[str, Dict[int, float]]:
    """Daily closes by coin and close day from the OHLCV store on disk (best effort)."""
    try:
        from data_fetcher import _ohlcv_store
        from hl_intelligence import _normalize_coin
        import setup_map
        _ohlcv_store.load_from_disk()
        wanted = set(coins)
        out: Dict[str, Dict[int, float]] = {}
        for key in list(getattr(_ohlcv_store, "_store", {})):
            sym, tf = key.split("|", 1)
            coin = _normalize_coin(sym)
            if tf != "1d" or coin not in wanted:
                continue
            import time as _t
            ts, cs = setup_map.closes(_ohlcv_store.get(sym, "1d"), "1d", _t.time())
            out[coin] = dict(zip(ts, cs))
        return out
    except Exception as exc:                                   # the logged closes still work
        print(f"stored candles not used: {exc}", file=sys.stderr)
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m research.radar_forward")
    ap.add_argument("cmd", choices=["score"])
    ap.add_argument("--db", help="SQLite file (default: the HyperLens store)")
    ap.add_argument("--no-candles", action="store_true", help="logged closes only")
    a = ap.parse_args(argv)
    import sqlite3
    import radar_log
    if a.db:
        conn = sqlite3.connect(a.db)
        radar_log.ensure(conn)
    else:
        conn = radar_log.conn()
    rows = radar_log.load(conn)
    candles = {} if a.no_candles else store_candles({r["coin"] for r in rows})
    print(json.dumps(report(rows, candles), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
