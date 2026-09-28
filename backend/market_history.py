"""
Market history: the share of coins in each regime on every day since 2019, for the
scanner's history drawer (declared in docs/reviews/market-breadth-study.md).

The seed (seeds/market_history_seed.json, written by `python -m backtest.breadth_history
export`) holds the rebuilt days and the study's episodes. Once a day the same method runs
on the last closed daily candle: Binance USDT spot closes for the seed's coin list, the
live engine on each coin's trailing 600 candles. New days are appended to a file next to
hyperlens.db. The study's counts (base rates, band records) stop at its end day; episodes are
scored after it too, once their 30 or 60 days have closed (approved by the owner on 28 Sep 2026).
The chart's past paths (what followed days like today, docs/reviews/market-paths-method.md) are built
here from the days, the seed's typical-alt paths and the per-coin closes of recent days.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
import time
from bisect import bisect_right
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DAY_MS = 86_400_000
SEED_PATH = Path(__file__).resolve().parent / "seeds" / "market_history_seed.json"   # data/ is not in the image
KLINES_URL = "https://data-api.binance.vision/api/v3/klines?symbol={pair}&interval=1d&limit=1000"
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
UPDATE_AFTER_S = 18 * 60         # run 18 minutes after the daily close
FETCH_CONCURRENCY = 6

_seed: Optional[dict] = None
_live: List[list] = []
_fng: Dict[int, int] = {}
_closes: Dict[int, Dict[str, float]] = {}     # daily closes per coin: live days, and seed days from 60 before the end day
_fan_log: List[list] = []                     # the fan at each new drawer episode's first day, from FAN_LOG_FROM

# Forward test (docs/reviews/btc-band-breadth-forward-test.md): BTC below its weekly band
# while the Uptrend share is 55% or more. Only episodes starting after the declaration count.
FT_DECLARED_DAY = 20722                       # 2026-09-26
FT_SHARE = 0.55
FT_MIN_COINS = 20
# Exploratory episodes it was found on (windows 1-9, 60 days closed by 2026-03-29), on Sunday closes as the rule
# says: start day, days, share, BTC 30d, alt 30d, alt 60d (%). Reproduce: python -m backtest.breadth_history ft-history
FT_HISTORY = [
    [18965, 13, 0.77, -6, -4, -35], [18984, 11, 0.60, -31, -40, -44], [19009, 8, 0.56, 4, -20, -29],
    [19088, 15, 0.64, -17, -28, -55], [19193, 143, 0.68, -10, -4, -14], [19997, 10, 0.83, 16, -1, 64],
    [20356, 1, 0.89, 2, -20, -40], [20372, 1, 0.86, -4, -1, -27],
]
# Episode outcomes as in backtest.breadth_history.study: BTC and the median alt (20+ alts with both closes).
HORIZONS = (10, 30, 60)
MIN_ALTS = 20
_view: Optional[dict] = None


def _live_path() -> str:
    hl = os.environ.get("HYPERLENS_DB_PATH")
    base = os.path.dirname(hl) if hl else str(Path(__file__).resolve().parent)
    return os.path.join(base, "market_history_live.json")


def _load() -> dict:
    global _seed, _live, _fng, _fan_log
    if _seed is None:
        _seed = json.loads(SEED_PATH.read_text())
        _fan_log = []
        try:
            saved = json.loads(Path(_live_path()).read_text())
            last = _seed["days"][-1][0]
            _live = [r for r in saved.get("days", []) if r[0] > last]
            _fng = {int(k): v for k, v in saved.get("fear_greed", {}).items()}
            _closes.update({int(k): v for k, v in saved.get("closes", {}).items()})
            _fan_log = saved.get("fan_log", [])
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Market history: live file unreadable (%s); starting from the seed", exc)
    return _seed


def _save() -> None:
    path = Path(_live_path())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"days": _live, "fear_greed": {str(k): v for k, v in _fng.items()},
                               "closes": {str(k): v for k, v in _closes.items()}, "fan_log": _fan_log},
                              separators=(",", ":")))
    os.replace(tmp, path)


def all_days() -> List[list]:
    return _load()["days"] + _live


# ---------------------------------------------------------------------------
# Daily update (same method as backtest.breadth_history.rebuild)
# ---------------------------------------------------------------------------

def day_rows(klines, days: List[int], window: int, min_bars: int) -> Dict[int, tuple]:
    """(regime, z, close) for each requested day, from daily klines (closed candles only)."""
    from engines.rcce_engine import compute_rcce
    if not klines:
        return {}
    a = np.asarray([[float(x) for x in r[:6]] for r in klines], dtype=np.float64)
    d = {"timestamp": a[:, 0], "open": a[:, 1], "high": a[:, 2], "low": a[:, 3], "close": a[:, 4], "volume": a[:, 5]}
    kday = (d["timestamp"] // DAY_MS).astype(int)
    out = {}
    for day in days:
        i = int(np.searchsorted(kday, day, side="right"))       # candles up to and including `day`
        if i < min_bars or kday[i - 1] != day:
            continue
        w = {k: v[max(0, i - window):i] for k, v in d.items()}
        r = compute_rcce(w)
        out[day] = (r.get("regime"), round(float(r.get("z_score") or 0.0), 3), float(d["close"][i - 1]))
    return out


def day_closes(klines, days: List[int], min_bars: int) -> Dict[int, float]:
    """Close on each requested day, from daily klines, where the coin had min_bars candles by then (as day_rows)."""
    try:
        kday = [int(r[0]) // DAY_MS for r in klines or []]
        close = [float(r[4]) for r in klines or []]
    except (TypeError, ValueError, IndexError):
        return {}
    out = {}
    for day in days:
        i = bisect_right(kday, day)
        if i >= min_bars and kday[i - 1] == day:
            out[day] = close[i - 1]
    return out


def aggregate(day: int, per_coin: Dict[str, tuple]) -> Optional[list]:
    """One seed-format row: [day, n, uptrend, overheated, downtrend, basing, median_z, btc]."""
    rs = list(per_coin.values())
    n = len(rs)
    if not n:
        return None
    c = Counter(r for r, _, _ in rs)
    share = lambda *ks: round(sum(c.get(k, 0) for k in ks) / n, 4)
    btc = per_coin.get("BTCUSDT")
    return [day, n, share("MARKUP"), share("BLOWOFF"), share("MARKDOWN"), share("ACCUM", "REACC", "CAP"),
            round(statistics.median(z for _, z, _ in rs), 3), btc[2] if btc else None]


async def _fetch_json(session, url: str):
    import aiohttp
    for attempt in range(3):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
                if r.status in (400, 404):
                    return None                      # delisted pair
        except Exception:
            pass
        await asyncio.sleep(2 * (attempt + 1))
    return None


async def update(now: Optional[float] = None) -> int:
    """Append every closed day missing since the last stored one. Returns the number added. Also fills the
    per-coin closes of seed days from 60 days before the study's end day, which score the episodes after it."""
    global _view
    import aiohttp
    seed = _load()
    now = time.time() if now is None else now
    yesterday = int(now * 1000) // DAY_MS - 1
    missing = list(range(all_days()[-1][0] + 1, yesterday + 1))
    backfill = {d[0]: d[1] for d in seed["days"] if d[0] > seed["end_day"] - max(HORIZONS) and d[0] not in _closes}
    added = 0
    async with aiohttp.ClientSession() as session:
        if missing or backfill:
            sem = asyncio.Semaphore(FETCH_CONCURRENCY)
            per_day: Dict[int, Dict[str, tuple]] = {d: {} for d in missing}
            filled: Dict[int, Dict[str, float]] = {d: {} for d in backfill}

            async def one(pair):
                async with sem:
                    kl = await _fetch_json(session, KLINES_URL.format(pair=pair))
                if missing:
                    rows = await asyncio.to_thread(day_rows, kl, missing, seed["window"], seed["min_bars"])
                    for day, v in rows.items():
                        per_day[day][pair] = v
                for day, c in day_closes(kl, list(backfill), seed["min_bars"]).items():
                    filled[day][pair] = c

            await asyncio.gather(*(one(p) for p in seed["pairs"]))
            for day in missing:
                row = aggregate(day, per_day[day])
                if row and row[1] >= seed["min_coins"]:
                    _live.append(row)
                    _closes[day] = {p: v[2] for p, v in per_day[day].items()}
                    added += 1
            for day, n in backfill.items():
                if len(filled[day]) >= 0.9 * n:              # a partial fetch is retried on the next update
                    _closes[day] = filled[day]
            if added:
                try:
                    log_fans(missing)
                except Exception as exc:                     # the log never blocks the daily rows
                    logger.warning("Market history: fan log skipped (%s)", exc)
        fg = await _fetch_json(session, FNG_URL)
        if fg and fg.get("data"):
            _fng.update({int(x["timestamp"]) // 86_400: int(x["value"]) for x in fg["data"]})
    _save()
    _view = None
    logger.info("Market history: %d day(s) added, last %s, %d Fear & Greed days, %d days of closes",
                added, all_days()[-1][0], len(_fng), len(_closes))
    return added


async def run_forever() -> None:
    await asyncio.sleep(120)
    while True:
        try:
            await update()
        except Exception as exc:
            logger.warning("Market history update failed: %s", exc)
        now = time.time()
        next_close = (int(now) // 86_400 + 1) * 86_400
        await asyncio.sleep(max(60, next_close + UPDATE_AFTER_S - now))


# ---------------------------------------------------------------------------
# View for /api/market-history
# ---------------------------------------------------------------------------

def band_of(share: float, bands_def) -> str:
    return next(label for lo, hi, label in bands_def if lo <= share < hi)


def episodes_after(days: List[list], start_after: int, bands_def) -> Dict[str, List[list]]:
    """Episodes after the study's end day, same merge rule (gaps of up to 5 days): [start, last, breadth]."""
    out: Dict[str, List[list]] = {}
    cur = None
    for d in days:
        if d[0] <= start_after:
            continue
        b = band_of(d[2], bands_def)
        if cur and cur["band"] == b and d[0] - cur["last"] <= 6:
            cur["last"] = d[0]
            continue
        if cur:
            out.setdefault(cur["band"], []).append([cur["start"], cur["last"], cur["breadth"]])
        cur = {"band": b, "start": d[0], "last": d[0], "breadth": d[2]}
    if cur:
        out.setdefault(cur["band"], []).append([cur["start"], cur["last"], cur["breadth"]])
    return out


def _change(btc: Dict[int, float], t: int, e: int):
    """(BTC %, typical alt %) from day t's close to day e's: the median over alts with both closes, as in
    backtest.breadth_history.study; None where the closes are missing."""
    b = round(100 * (btc[e] / btc[t] - 1), 1) + 0.0 if btc.get(t) and btc.get(e) else None
    a0, a1 = _closes.get(t) or {}, _closes.get(e) or {}
    rs = [a1[p] / a0[p] - 1 for p in a0 if p != "BTCUSDT" and p in a1 and a0[p] > 0]
    return b, (round(100 * statistics.median(rs), 1) + 0.0 if len(rs) >= MIN_ALTS else None)       # + 0.0: no -0.0


def score(row: list, btc: Dict[int, float], last: int, end_day: int) -> list:
    """An episode row [start, end, breadth, btc10, alt10, btc30, alt30, btc60, alt60] with every horizon that
    runs past the study's end day scored once it has closed (by `last`). The study's own outcomes stay."""
    out = list(row[:3]) + (list(row[3:]) or [None] * 2 * len(HORIZONS))
    t = out[0]
    for i, h in enumerate(HORIZONS):
        if end_day < t + h <= last:
            out[3 + 2 * i], out[4 + 2 * i] = _change(btc, t, t + h)
    return out


def scored_bands(seed: dict, days: List[list], btc: Dict[int, float]) -> Dict[str, dict]:
    """Per band: the study's episodes and the later ones, all scored up to the latest day. The episode running
    on the study's end day continues into the days after it when the band holds (same merge rule)."""
    end, last = seed["end_day"], days[-1][0]
    eps = {label: [list(e) for e in seed["bands"][label]["episodes"]] for _, _, label in seed["bands_def"]}
    later = episodes_after(days, end, seed["bands_def"])
    tails = [(e[1], label, e) for label, es in eps.items() for e in es]
    if tails and later:
        _, label, tail = max(tails, key=lambda x: x[0])
        first = min((e[0], lb) for lb, es in later.items() for e in es)
        if first[1] == label and first[0] - tail[1] <= 6:
            tail[1] = later[label].pop(0)[1]
    return {label: {"episodes": [score(e, btc, last, end) for e in eps[label]],
                    "later": [score(e, btc, last, end) for e in later.get(label, [])]} for label in eps}


def cycle(days: List[list]) -> Optional[dict]:
    """Today's risk-on run (or risk-off stretch) against the past ones, by the rules of
    docs/reviews/risk-on-cycles-study.md (backtest.risk_on_cycles.detect_runs): breadth is the Uptrend +
    Overheated share; a run starts on the first day at 55% or more and ends on the first of 5+ days below.
    Day 1 is the run's first day, so a past run reached day N if it lasted N days or more. The first run
    (start unknown) is left out."""
    from backtest.risk_on_cycles import OFF_DAYS, THR, detect_runs
    ds = [d[0] for d in days]
    share = {d[0]: round(d[2] + d[3], 4) for d in days}
    try:
        runs = detect_runs(ds, share)
    except KeyError:                                   # a missing day inside a run
        logger.warning("Market history: gap in the days, no risk-on run shown")
        return None
    cur = runs[-1]
    if cur["first"]:
        return None
    day = ds[-1] - cur["start"] + 1
    ended = [r for r in runs if r["type"] == cur["type"] and not r["first"] and r["end"] is not None]
    past = sorted(r["length"] for r in ended)
    reached = [n for n in past if n >= day]
    below = 0
    while cur["type"] == "on" and below < len(ds) and share[ds[-1 - below]] < THR:
        below += 1
    return {"type": cur["type"], "start": cur["start"], "day": day, "threshold": THR, "off_days": OFF_DAYS,
            "below_days": below, "since": ds[0], "past": len(past),
            "median": statistics.median(past) if past else None, "reached": len(reached),
            "more": 30, "lasted_more": sum(n >= day + 30 for n in reached),
            # Ended runs of today's type, oldest first: start, length in days, and the highest share on the way
            # (risk-on) or the lowest (risk-off).
            "runs": [[r["start"], r["length"], round((max if cur["type"] == "on" else min)(
                share.get(d, 0.0) for d in range(r["start"], r["end"])), 2)] for r in ended]}


def btc_band_rows(days: List[list]) -> List[tuple]:
    """BTC's weekly bull market support band at each Sunday close: (close_day, (lower, upper) or None), from the
    20-week SMA and 21-week EMA of Sunday closes, as in the forward test's rule. A close's band applies from the
    next day (completed weeks only)."""
    from backtest.risk_on_cycles import SUNDAY, weekly_rows
    return weekly_rows({d[0]: d[7] for d in days if d[7]}, SUNDAY)


def btc_band(days: List[list]) -> Dict[int, tuple]:
    """BTC's weekly band per day with a close: (lower, upper) of the last completed week (Sunday closes)."""
    from backtest.risk_on_cycles import SUNDAY, weekly_band
    return weekly_band({d[0]: d[7] for d in days if d[7]}, SUNDAY)


def ft_episodes(days: List[list], band: Dict[int, tuple], after: int = -1) -> List[dict]:
    """The forward test's episodes among days after `after`: BTC's daily close under the lower edge of its band
    while the Uptrend + Overheated share is 55% or more; days with gaps of up to 5 days join one episode."""
    # Share = Uptrend + Overheated: the rule stays the same whether or not Overheated fires.
    flagged = [d for d in days if d[0] > after and d[0] in band and d[7] and d[7] < band[d[0]][0]
               and d[2] + d[3] >= FT_SHARE]
    eps: List[dict] = []
    for d in flagged:
        if eps and d[0] - eps[-1]["end"] <= 6:
            eps[-1]["end"] = d[0]
        else:
            eps.append({"start": d[0], "end": d[0], "share": round(d[2] + d[3], 4)})
    return eps


def forward_test(days: List[list], band: Dict[int, tuple]) -> dict:
    """Episodes after the declaration: first day, length, share, and outcomes once they exist."""
    btc = {d[0]: d[7] for d in days}
    eps = ft_episodes(days, band, after=FT_DECLARED_DAY)

    def outcome(t: int, h: int) -> Optional[dict]:
        a, b = _closes.get(t), _closes.get(t + h)
        if not a or not b or t not in btc or t + h not in btc:
            return None
        rs = [b[p] / a[p] - 1 for p in a if p != "BTCUSDT" and p in b and a[p] > 0]
        if len(rs) < FT_MIN_COINS:
            return None
        return {"btc": round(100 * (btc[t + h] / btc[t] - 1), 1), "alt": round(100 * statistics.median(rs), 1)}

    for e in eps:
        e["h30"], e["h60"] = outcome(e["start"], 30), outcome(e["start"], 60)
    return {"declared_day": FT_DECLARED_DAY, "share": FT_SHARE, "episodes": eps,
            "history_columns": ["start", "days", "share", "btc30", "alt30", "alt60"], "history": FT_HISTORY}


# ---------------------------------------------------------------------------
# Past paths: what followed days like today (docs/reviews/market-paths-method.md)
# ---------------------------------------------------------------------------

FAN_K = tuple(range(0, 61, 5))              # knots, days from today
FAN_Q = (0.10, 0.25, 0.50, 0.75, 0.90)
FAN_MIN_RUNS = 6                            # a median and bands need matches from 6+ runs
FAN_FEW_RUNS = 3                            # 3-5 runs: paths only; under 3: no fan
FAN_H = 60                                  # a match needs its 60 days closed
FAN_LADDER = ((0.05, True), (0.10, True), (0.10, False), (0.15, False))   # (width, same BTC side)
FAN_SERIES = ("uptrend", "btc", "alt")
FAN_CHECK_H = (30, 60)
FAN_LOG_FROM = 20724                        # 2026-09-28: the method doc's commit date; the clean check starts here
ALT_PATHS_K = tuple(range(5, 61, 5))
CHECK_MIN_TESTS, CHECK_MIN_RUNS = 30, 8


def _share(d: list) -> float:
    return d[2] + d[3]                      # Uptrend + Overheated: the 55% line's share


def run_state_at_close(days: List[list]) -> Dict[int, tuple]:
    """(state, run_id) per day as known at that day's close: 'on' from the first day at 55% or more, 'off' on
    the 5th day in a row below 55% (dip days 1-4 stay 'on'); the run id changes at every flip. No hindsight."""
    from backtest.risk_on_cycles import OFF_DAYS, THR
    out, state, rid, below = {}, "off", 0, 0
    for d in days:
        if _share(d) >= THR:
            below = 0
            if state == "off":
                state, rid = "on", rid + 1
        else:
            below += 1
            if state == "on" and below == OFF_DAYS:
                state, rid = "off", rid + 1
        out[d[0]] = (state, rid)
    return out


def hazen(values: List[float], q: float) -> float:
    """Quantile by the Hazen rule: sorted values at (i - 0.5)/n, linear in between, clamped at the ends."""
    v = sorted(values)
    n = len(v)
    x = q * n - 0.5                          # 0-based position
    if x <= 0:
        return v[0]
    if x >= n - 1:
        return v[-1]
    i = int(x)
    return v[i] + (x - i) * (v[i + 1] - v[i])


def _btc_side(d: list, band: Dict[int, tuple]) -> Optional[str]:
    b = band.get(d[0])
    if not b or not d[7]:
        return None
    return "holding" if d[7] >= b[0] else "below"


def analogs(days: List[list], band: Dict[int, tuple], T: int, cutoff: Optional[int] = None,
            states: Optional[Dict[int, tuple]] = None):
    """Episodes of past days like T (method doc, 'Which past days match today'): same run state at close, another
    run, 60 days closed by `cutoff` (default T), then the ladder. Returns (episodes, rule) with episodes as lists of
    matching days (the first is the path's origin), or ([], None) when T is not in `days`."""
    cutoff = T if cutoff is None else cutoff
    states = states or run_state_at_close(days)
    row = {d[0]: d for d in days}
    if T not in row:
        return [], None
    st, rid = states[T]
    s0, side0 = _share(row[T]), _btc_side(row[T], band)
    cand = [d for d in days if d[0] + FAN_H <= cutoff and states[d[0]][0] == st and states[d[0]][1] != rid]
    eps: List[list] = []
    rule = None
    for step, (w, same) in enumerate(FAN_LADDER):
        m = [d[0] for d in cand if round(abs(_share(d) - s0), 6) <= w
             and (not same or (side0 is not None and _btc_side(d, band) == side0))]
        eps = []
        for d in m:
            if eps and d - eps[-1][-1] <= 6 and states[d][1] == states[eps[-1][-1]][1]:
                eps[-1].append(d)
            else:
                eps.append([d])
        rule = {"width": w, "btc_side": side0 if same else "either", "step": step}
        if len({states[e[0]][1] for e in eps}) >= FAN_MIN_RUNS:
            break
    return eps, rule


def _anchored(row: Dict[int, list], alt_ret, T: int, t: int, k: int) -> Dict[str, Optional[float]]:
    """The three series k days after origin t, started at T's values (method doc, 'Horizons and anchoring')."""
    a, b, now = row.get(t), row.get(t + k), row[T]
    up = btc = None
    if a and b:
        up = min(1.0, max(0.0, _share(now) + _share(b) - _share(a)))
        if a[7] and b[7] and now[7]:
            btc = now[7] * b[7] / a[7]
    alt = 0.0 if k == 0 else alt_ret(t, t + k)
    return {"uptrend": up, "btc": btc, "alt": alt}


def fan(days: List[list], band: Dict[int, tuple], alt_ret, T: int, cutoff: Optional[int] = None,
        states: Optional[Dict[int, tuple]] = None, base_path: Optional[dict] = None) -> Optional[dict]:
    """Past paths from days like T, one per episode (weight 1), anchored at T, with Hazen quantiles per knot where
    the values come from 6+ runs. None under 3 runs. `alt_ret(t, e)` gives the typical alt's % change or None."""
    states = states or run_state_at_close(days)
    eps, rule = analogs(days, band, T, cutoff, states)
    runs = {states[e[0]][1] for e in eps}
    if len(runs) < FAN_FEW_RUNS:
        return None
    row = {d[0]: d for d in days}
    too_few = len(runs) < FAN_MIN_RUNS
    run_start: Dict[int, int] = {}
    for d in days:
        run_start.setdefault(states[d[0]][1], d[0])
    paths = {s: [] for s in FAN_SERIES}
    for e in eps:
        pts = [_anchored(row, alt_ret, T, e[0], k) for k in FAN_K]
        for s in FAN_SERIES:
            paths[s].append([p[s] for p in pts])
    bands: Dict[str, Optional[list]] = {}
    for s in FAN_SERIES:
        if too_few:
            bands[s] = None
            continue
        per_k = []
        for i in range(len(FAN_K)):
            vals = [(p[i], states[e[0]][1]) for p, e in zip(paths[s], eps) if p[i] is not None]
            ok = len({r for _, r in vals}) >= FAN_MIN_RUNS
            per_k.append([hazen([v for v, _ in vals], q) for q in FAN_Q] if ok else None)
        bands[s] = per_k
    out = {"day": T, "state": states[T][0], "rule": rule, "runs": len(runs), "min_runs": FAN_MIN_RUNS,
           "too_few": too_few, "k": list(FAN_K), "q": list(FAN_Q),
           "episodes": [[e[0], run_start[states[e[0]][1]], row[e[0]][1], int(_btc_side(row[e[0]], band) == "below")]
                        for e in eps],
           "paths": paths, "bands": bands}
    if base_path:
        now = row[T][7]
        out["ordinary"] = {"btc": [now * (1 + x / 100) if now else None for x in base_path["btc"]],
                           "alt": list(base_path["alt"])}
    return out


def fan_payload(f: dict) -> dict:
    """The fan rounded for the API: Uptrend 3 dp (0-1), BTC whole USD, typical alt 1 dp (%)."""
    rnd = {"uptrend": lambda x: round(x, 3), "btc": lambda x: int(round(x)), "alt": lambda x: round(x, 1) + 0.0}
    r = lambda s, x: None if x is None else rnd[s](x)
    out = {**f, "paths": {s: [[r(s, x) for x in p] for p in f["paths"][s]] for s in FAN_SERIES},
           "bands": {s: None if f["bands"][s] is None else [None if b is None else [r(s, x) for x in b]
                                                             for b in f["bands"][s]] for s in FAN_SERIES}}
    if "ordinary" in f:
        out["ordinary"] = {s: [r(s, x) for x in f["ordinary"][s]] for s in ("btc", "alt")}
    return out


def make_alt_ret(alt_paths: Optional[dict], closes: Dict[int, Dict[str, float]]):
    """alt_ret(t, e): the typical alt's % change from day t's close to day e's. Origins covered by the seed's
    alt_paths (whole %) read from it; later origins are computed from per-coin closes (1 dp): the median simple
    return of 20+ coins other than BTC with both closes, as backtest.breadth_history.study."""
    first = alt_paths["from"] if alt_paths else None
    ks = {k: i for i, k in enumerate(alt_paths["k"])} if alt_paths else {}
    rows = alt_paths["rows"] if alt_paths else []

    def alt_ret(t: int, e: int) -> Optional[float]:
        if e == t:
            return 0.0
        if first is not None and first <= t < first + len(rows):
            i = ks.get(e - t)
            return None if i is None else rows[t - first][i]
        a0, a1 = closes.get(t) or {}, closes.get(e) or {}
        rs = [a1[p] / a0[p] - 1 for p in a0 if p != "BTCUSDT" and p in a1 and a0[p] > 0]
        return round(100 * statistics.median(rs), 1) + 0.0 if len(rs) >= MIN_ALTS else None
    return alt_ret


def wilson_contains(k: int, n: int, target: float) -> bool:
    from backtest.risk_on_cycles import wilson
    lo, hi = wilson(k, n)
    return lo is not None and lo <= target <= hi


def drawer_episode_starts(days: List[list], bands_def) -> List[int]:
    """First day of every drawer episode (six Uptrend bands, gaps of up to 5 days joined)."""
    return sorted(e[0] for es in episodes_after(days, -1, bands_def).values() for e in es)


def fan_check(days: List[list], band: Dict[int, tuple], alt_ret, last_closed: int, bands_def,
              detail: bool = False) -> dict:
    """The declared walk-forward check (method doc, 'Walk-forward check'): at the first day T of every drawer
    episode with T + 60 <= last_closed, the fan built with cutoff T against what followed, and the median of all
    earlier days (T's run left out) as the benchmark."""
    states = run_state_at_close(days)
    row = {d[0]: d for d in days}
    units = [T for T in drawer_episode_starts(days, bands_def) if T + FAN_H <= last_closed]
    hits = {s: {h: [0, 0, 0] for h in FAN_CHECK_H} for s in FAN_SERIES}     # mid, out, n
    err = {s: {h: [0.0, 0.0, 0] for h in FAN_CHECK_H} for s in FAN_SERIES}  # fan, all, n
    tested, tested_runs, scored, scored_runs, per_t = 0, set(), 0, set(), []
    for T in units:
        f = fan(days, band, alt_ret, T, cutoff=T, states=states)
        if f is None:
            per_t.append({"T": T, "fan": False})
            continue
        tested += 1
        tested_runs.add(states[T][1])
        earlier = [d[0] for d in days if d[0] + FAN_H <= T and states[d[0]][1] != states[T][1]]
        rec = {"T": T, "fan": True, "runs": f["runs"], "step": f["rule"]["step"], "series": {}}
        bench = {h: [_anchored(row, alt_ret, T, d, h) for d in earlier] for h in FAN_CHECK_H}
        for s in FAN_SERIES:
            for h in FAN_CHECK_H:
                i = FAN_K.index(h)
                y = _anchored(row, alt_ret, T, T, h)[s]
                qs = f["bands"][s][i] if f["bands"][s] else None
                if y is None or qs is None:
                    continue
                p10, p25, p50, p75, p90 = qs
                mid, out = p25 <= y <= p75, p10 <= y <= p90
                allv = [v[s] for v in bench[h] if v[s] is not None]
                m_all = statistics.median(allv) if allv else None
                c = hits[s][h]
                c[0] += mid
                c[1] += out
                c[2] += 1
                if m_all is not None:
                    e = err[s][h]
                    e[0] += abs(p50 - y)
                    e[1] += abs(m_all - y)
                    e[2] += 1
                rec["series"][f"{s}{h}"] = {"y": y, "q": qs, "all": m_all, "mid": mid, "out": out}
        per_t.append(rec)
        if rec["series"]:                   # at least one series had quantiles (6+ runs) at T
            scored += 1
            scored_runs.add(states[T][1])
    # The bar counts the scored test days (quantiles from 6+ runs), the ones the hit rates are made of.
    untested = scored < CHECK_MIN_TESTS or len(scored_runs) < CHECK_MIN_RUNS
    series = {}
    for s in FAN_SERIES:
        ok = not untested and all(
            hits[s][h][2] > 0 and wilson_contains(hits[s][h][0], hits[s][h][2], 0.50)
            and wilson_contains(hits[s][h][1], hits[s][h][2], 0.80) for h in FAN_CHECK_H)
        series[s] = {**{str(h): list(hits[s][h]) for h in FAN_CHECK_H}, "pass": ok}
    ratios = [err[s][h][0] / err[s][h][1] for s in FAN_SERIES for h in FAN_CHECK_H if err[s][h][1] > 0]
    # tested: test days with a fan (3+ runs); scored: those with quantiles (6+ runs), the ones the hits count.
    out = {"through": last_closed, "tested": tested, "of": len(units), "runs": len(tested_runs),
           "scored": scored, "scored_runs": len(scored_runs), "series": series,
           "median_vs_all": round(sum(ratios) / len(ratios), 2) if len(ratios) == 2 * len(FAN_SERIES) else None,
           "mae": {s: {str(h): [round(err[s][h][0] / err[s][h][2], 4) if err[s][h][2] else None,
                                round(err[s][h][1] / err[s][h][2], 4) if err[s][h][2] else None]
                       for h in FAN_CHECK_H} for s in FAN_SERIES},
           "untested": untested}
    if detail:
        out["per_t"] = per_t
    return out


def fan_show(check: Optional[dict], too_few: bool) -> Dict[str, str]:
    """'bands' for a series that passed the check, 'paths' otherwise (failed, untested, or 3-5 runs)."""
    return {s: "bands" if (not too_few and check and not check.get("untested")
                           and check["series"].get(s, {}).get("pass")) else "paths" for s in FAN_SERIES}


def fan_log_entry(f: dict) -> list:
    """[day, {series: {30: [p10..p90], 60: [...]}}] with anchored numbers, None where there is no band."""
    return [f["day"], {s: {str(h): (f["bands"][s][FAN_K.index(h)] if f["bands"][s] else None) for h in FAN_CHECK_H}
                       for s in FAN_SERIES}]


def live_check(log: List[list], days: List[list], alt_ret) -> Optional[dict]:
    """Score logged fans once their 60 days have closed (method doc, 'Clean check'): middle-half and 10-90 hits
    per series over both horizons. An entry still inside its 60 days counts nowhere, not even at +30."""
    if not log:
        return None
    row = {d[0]: d for d in days}
    last = days[-1][0]
    mid = {s: [0, 0] for s in FAN_SERIES}
    out = {s: [0, 0] for s in FAN_SERIES}
    scored = 0
    for T, qs in log:
        if T not in row or T + FAN_H > last:
            continue
        scored += 1
        for s in FAN_SERIES:
            for h in FAN_CHECK_H:
                q = (qs.get(s) or {}).get(str(h))
                if not q:
                    continue
                y = _anchored(row, alt_ret, T, T, h)[s]
                if y is None:
                    continue
                mid[s][0] += q[1] <= y <= q[3]
                mid[s][1] += 1
                out[s][0] += q[0] <= y <= q[4]
                out[s][1] += 1
    return {"logged": len(log), "scored": scored, "mid": mid, "out": out}


def alt_recent(days: List[list], n: int = 90) -> List[list]:
    """The typical alt over the last n days, as % against today's close: 100 * median over alts of close(d) /
    close(T) - 100 (20+ alts with both closes); 0.0 on today."""
    T = days[-1][0]
    now = _closes.get(T) or {}
    out = []
    for d in days:
        if d[0] < T - n:
            continue
        c = _closes.get(d[0]) or {}
        rs = [c[p] / now[p] for p in c if p != "BTCUSDT" and p in now and now[p] > 0]
        if len(rs) >= MIN_ALTS:
            out.append([d[0], round(100 * statistics.median(rs) - 100, 1) + 0.0])
    return out


def _alt_ret(seed: dict):
    return make_alt_ret(seed.get("alt_paths"), _closes)


def fan_view(seed: dict, days: List[list], band: Dict[int, tuple]) -> Optional[dict]:
    """Today's past-paths fan for the drawer, with the seed's walk-forward check and the clean check so far."""
    alt_ret = _alt_ret(seed)
    f = fan(days, band, alt_ret, days[-1][0], base_path=seed.get("base_path"))
    if f is None:
        return None
    out = fan_payload(f)
    check = seed.get("fan_check")
    out["show"] = fan_show(check, f["too_few"])
    out["check"] = check
    out["live_check"] = live_check(_fan_log, days, alt_ret)
    return out


def log_fans(new_days: List[int]) -> None:
    """Clean check (method doc): on the first day of each new drawer episode from FAN_LOG_FROM, log the fan's
    quantiles at +30 and +60. Scored in view() once the windows close."""
    seed = _load()
    days = [d for d in all_days() if d[1] >= seed["min_coins"]]
    starts = set(drawer_episode_starts(days, seed["bands_def"]))
    logged = {e[0] for e in _fan_log}
    todo = [d for d in new_days if d >= FAN_LOG_FROM and d in starts and d not in logged]
    if not todo:
        return
    band = btc_band(all_days())
    states = run_state_at_close(days)
    alt_ret = _alt_ret(seed)
    for T in todo:
        f = fan(days, band, alt_ret, T, states=states)
        if f is not None:
            _fan_log.append(fan_log_entry(fan_payload(f)))      # saved with the rest by update()


def view() -> dict:
    global _view
    if _view is not None:
        return _view
    seed = _load()
    days = [d for d in all_days() if d[1] >= seed["min_coins"]]
    today = days[-1]
    pct = round(100 * sum(d[2] < today[2] for d in days) / len(days))
    btc = {d[0]: d[7] for d in all_days() if d[7]}
    eps = scored_bands(seed, days, btc)
    rows = btc_band_rows(all_days())
    from backtest.risk_on_cycles import expand_weekly
    band = expand_weekly(rows, [d[0] for d in all_days() if d[7]])
    bands = [{"label": label, "lo": lo, "hi": hi, "days": seed["bands"][label]["days"],
              "h30": seed["bands"][label]["h30"], "verdict": seed["bands"][label]["verdict"], **eps[label]}
             for lo, hi, label in seed["bands_def"]]
    _view = {
        "columns": seed["days_cols"], "days": days, "episode_columns": seed["episode_cols"],
        "end_day": seed["end_day"], "coins": len(seed["pairs"]), "base": seed["base"], "bands": bands,
        # The base rates and each band's record count days and episodes in this period only.
        "base_period": [days[0][0], seed["end_day"]], "scored_through": today[0],
        "today": {"day": today[0], "n": today[1], "uptrend": today[2], "overheated": today[3], "median_z": today[6],
                  "percentile": pct, "band": band_of(today[2], seed["bands_def"]), "since": days[0][0]},
        "cycle": cycle(days),
        "fear_greed": sorted([k, v] for k, v in _fng.items()),
        # One row per Sunday close: its band applies from the next day to the next close day.
        "btc_band_weekly": [[w, round(b[0], 2), round(b[1], 2)] for i, (w, b) in enumerate(rows)
                            if b and (i + 1 == len(rows) or rows[i + 1][0] >= days[0][0])],
        "forward_test": forward_test(days, band),
        "fan": _guarded("fan", lambda: fan_view(seed, days, band), None),
        "alt_recent": _guarded("alt_recent", lambda: alt_recent(days), []),
    }
    return _view


def _guarded(name: str, build, fallback):
    """The fan and the recent alt line are extras: a failure there must not take the whole drawer down."""
    try:
        return build()
    except Exception:
        logger.warning("Market history: %s unavailable", name, exc_info=True)
        return fallback
