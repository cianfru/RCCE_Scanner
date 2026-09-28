"""
Market history: the share of coins in each regime on every day since 2019, for the
scanner's history drawer (declared in docs/reviews/market-breadth-study.md).

The seed (seeds/market_history_seed.json, written by `python -m backtest.breadth_history
export`) holds the rebuilt days and the study's episodes. Once a day the same method runs
on the last closed daily candle: Binance USDT spot closes for the seed's coin list, the
live engine on each coin's trailing 600 candles. New days are appended to a file next to
hyperlens.db. The study's counts (base rates, band records) stop at its end day; episodes are
scored after it too, once their 30 or 60 days have closed (approved by the owner on 28 Sep 2026).
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

# Forward test (docs/reviews/btc-band-breadth-forward-test.md): BTC below its weekly band
# while the Uptrend share is 55% or more. Only episodes starting after the declaration count.
FT_DECLARED_DAY = 20722                       # 2026-09-26
FT_SHARE = 0.55
FT_MIN_COINS = 20
# Exploratory episodes it was found on (windows 1-9): start day, days, share, BTC 30d, alt 30d, alt 60d (%).
FT_HISTORY = [
    [18965, 13, 0.77, -6, -4, -35], [18984, 11, 0.60, -31, -40, -44], [19009, 8, 0.56, 4, -20, -29],
    [19088, 15, 0.64, -17, -28, -55], [19193, 143, 0.68, -10, -4, -14], [19998, 1, 0.83, 15, 1, 70],
    [20005, 2, 0.83, 26, 10, 100], [20356, 3, 0.89, 2, -20, -40], [20372, 1, 0.86, -4, -1, -27],
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
    global _seed, _live, _fng
    if _seed is None:
        _seed = json.loads(SEED_PATH.read_text())
        try:
            saved = json.loads(Path(_live_path()).read_text())
            last = _seed["days"][-1][0]
            _live = [r for r in saved.get("days", []) if r[0] > last]
            _fng = {int(k): v for k, v in saved.get("fear_greed", {}).items()}
            _closes.update({int(k): v for k, v in saved.get("closes", {}).items()})
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Market history: live file unreadable (%s); starting from the seed", exc)
    return _seed


def _save() -> None:
    path = Path(_live_path())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"days": _live, "fear_greed": {str(k): v for k, v in _fng.items()},
                               "closes": {str(k): v for k, v in _closes.items()}}, separators=(",", ":")))
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
    past = sorted(r["length"] for r in runs if r["type"] == cur["type"] and not r["first"] and r["end"] is not None)
    reached = [n for n in past if n >= day]
    below = 0
    while cur["type"] == "on" and below < len(ds) and share[ds[-1 - below]] < THR:
        below += 1
    return {"type": cur["type"], "start": cur["start"], "day": day, "threshold": THR, "off_days": OFF_DAYS,
            "below_days": below, "since": ds[0], "past": len(past),
            "median": statistics.median(past) if past else None, "reached": len(reached),
            "more": 30, "lasted_more": sum(n >= day + 30 for n in reached)}


def btc_band(days: List[list]) -> Dict[int, tuple]:
    """BTC's weekly bull market support band per day: (lower, upper) from the 20-week SMA and
    21-week EMA of completed weeks (Sunday closes), as in the forward test's rule."""
    btc = {d[0]: d[7] for d in days if d[7]}
    weeks = [d for d in sorted(btc) if (d + 4) % 7 == 3]           # day 3 (1970-01-04) was a Sunday
    out: Dict[int, tuple] = {}
    ema, closes, wi = None, [], -1
    bands = []
    for w in weeks:
        c = btc[w]
        closes.append(c)
        ema = c if ema is None else (2 / 22) * c + (1 - 2 / 22) * ema
        sma = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        bands.append((w, None if sma is None or len(closes) < 21 else (min(sma, ema), max(sma, ema))))
    for d in sorted(btc):
        while wi + 1 < len(bands) and bands[wi + 1][0] < d:         # completed weeks only
            wi += 1
        if wi >= 0 and bands[wi][1]:
            out[d] = bands[wi][1]
    return out


def forward_test(days: List[list], band: Dict[int, tuple]) -> dict:
    """Episodes after the declaration: first day, length, share, and outcomes once they exist."""
    btc = {d[0]: d[7] for d in days}
    # Share = Uptrend + Overheated: the rule stays the same whether or not Overheated fires.
    flagged = [d for d in days if d[0] > FT_DECLARED_DAY and d[0] in band and d[7] and d[7] < band[d[0]][0]
               and d[2] + d[3] >= FT_SHARE]
    eps: List[dict] = []
    for d in flagged:
        if eps and d[0] - eps[-1]["end"] <= 6:
            eps[-1]["end"] = d[0]
        else:
            eps.append({"start": d[0], "end": d[0], "share": round(d[2] + d[3], 4)})

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
    band = btc_band(all_days())
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
        "btc_band": [[d, round(lo, 2), round(hi, 2)] for d, (lo, hi) in sorted(band.items()) if d >= days[0][0]],
        "forward_test": forward_test(days, band),
    }
    return _view
