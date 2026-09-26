"""
Market history: the share of coins in each regime on every day since 2019, for the
scanner's history drawer (declared in docs/reviews/market-breadth-study.md).

The seed (data/market_history_seed.json, written by `python -m backtest.breadth_history
export`) holds the rebuilt days and the study's episodes. Once a day the same method runs
on the last closed daily candle: Binance USDT spot closes for the seed's coin list, the
live engine on each coin's trailing 600 candles. New days are appended to a file next to
hyperlens.db. Episode outcomes stop at the study's end day; later episodes carry none.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DAY_MS = 86_400_000
SEED_PATH = Path(__file__).resolve().parent / "data" / "market_history_seed.json"
KLINES_URL = "https://data-api.binance.vision/api/v3/klines?symbol={pair}&interval=1d&limit=1000"
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
UPDATE_AFTER_S = 18 * 60         # run 18 minutes after the daily close
FETCH_CONCURRENCY = 6

_seed: Optional[dict] = None
_live: List[list] = []
_fng: Dict[int, int] = {}
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
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Market history: live file unreadable (%s); starting from the seed", exc)
    return _seed


def _save() -> None:
    path = Path(_live_path())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"days": _live, "fear_greed": {str(k): v for k, v in _fng.items()}},
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
    """Append every closed day missing since the last stored one. Returns the number added."""
    global _view
    import aiohttp
    seed = _load()
    now = time.time() if now is None else now
    yesterday = int(now * 1000) // DAY_MS - 1
    missing = list(range(all_days()[-1][0] + 1, yesterday + 1))
    added = 0
    async with aiohttp.ClientSession() as session:
        if missing:
            sem = asyncio.Semaphore(FETCH_CONCURRENCY)
            per_day: Dict[int, Dict[str, tuple]] = {d: {} for d in missing}

            async def one(pair):
                async with sem:
                    kl = await _fetch_json(session, KLINES_URL.format(pair=pair))
                rows = await asyncio.to_thread(day_rows, kl, missing, seed["window"], seed["min_bars"])
                for day, v in rows.items():
                    per_day[day][pair] = v

            await asyncio.gather(*(one(p) for p in seed["pairs"]))
            for day in missing:
                row = aggregate(day, per_day[day])
                if row and row[1] >= seed["min_coins"]:
                    _live.append(row)
                    added += 1
        fg = await _fetch_json(session, FNG_URL)
        if fg and fg.get("data"):
            _fng.update({int(x["timestamp"]) // 86_400: int(x["value"]) for x in fg["data"]})
    _save()
    _view = None
    logger.info("Market history: %d day(s) added, last %s, %d Fear & Greed days", added, all_days()[-1][0], len(_fng))
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
    """Episodes after the study's end day, same merge rule (gaps of up to 5 days), no outcomes."""
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


def view() -> dict:
    global _view
    if _view is not None:
        return _view
    seed = _load()
    days = [d for d in all_days() if d[1] >= seed["min_coins"]]
    today = days[-1]
    pct = round(100 * sum(d[2] < today[2] for d in days) / len(days))
    later = episodes_after(days, seed["end_day"], seed["bands_def"])
    bands = [{"label": label, "lo": lo, "hi": hi, "days": seed["bands"][label]["days"],
              "h30": seed["bands"][label]["h30"], "verdict": seed["bands"][label]["verdict"],
              "episodes": seed["bands"][label]["episodes"], "later": later.get(label, [])}
             for lo, hi, label in seed["bands_def"]]
    _view = {
        "columns": seed["days_cols"], "days": days, "episode_columns": seed["episode_cols"],
        "end_day": seed["end_day"], "coins": len(seed["pairs"]), "base": seed["base"], "bands": bands,
        "today": {"day": today[0], "n": today[1], "uptrend": today[2], "overheated": today[3], "median_z": today[6],
                  "percentile": pct, "band": band_of(today[2], seed["bands_def"]), "since": days[0][0]},
        "fear_greed": sorted([k, v] for k, v in _fng.items()),
    }
    return _view
