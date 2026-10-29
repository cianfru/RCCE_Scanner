"""
BTC and ETH funding on Hyperliquid for the market history page's Chart view (docs/reviews/turn-signs-study.md): what
leveraged longs paid shorts (or shorts paid longs) each day, summed per UTC day as a yearly rate in percent.
Context, not a signal.

History comes from seeds/funding_seed.json (from 12 May 2023, fetched with research/fetch_turn_data.py). Every closed
day after it is read from Hyperliquid's public fundingHistory a few times a day (two calls, BTC and ETH, from the
shared Hyperliquid budget as a low-priority consumer) and kept in funding_live.json next to hyperlens.db.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parent / "seeds" / "funding_seed.json"
INFO_URL = "https://api.hyperliquid.xyz/info"
COINS = ("BTC", "ETH")
DAY_MS = 86_400_000
CHECK_EVERY_S = 6 * 3600
MAX_PAGES = 20                    # 500 hourly records a page: about 20 days each

_seed: Optional[dict] = None
_live: dict = {}                  # {day (int): [day, btc, eth]}
_view: Optional[dict] = None


def _live_path() -> str:
    hl = os.environ.get("HYPERLENS_DB_PATH")
    base = os.path.dirname(hl) if hl else str(Path(__file__).resolve().parent)
    return os.path.join(base, "funding_live.json")


def _load() -> dict:
    global _seed, _live
    if _seed is None:
        try:
            _seed = json.loads(SEED_PATH.read_text())
        except FileNotFoundError:
            _seed = {}
        try:
            _live = {int(r[0]): r for r in json.loads(Path(_live_path()).read_text()).get("rows", [])}
        except FileNotFoundError:
            _live = {}
        except Exception as exc:
            logger.warning("Funding: live file unreadable (%s); starting empty", exc)
            _live = {}
    return _seed


def _save() -> None:
    path = Path(_live_path())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"columns": ["day", "btc", "eth"], "rows": [_live[d] for d in sorted(_live)]},
                              separators=(",", ":")))
    os.replace(tmp, path)


def daily(records: list, before_day: int) -> dict:
    """Hyperliquid funding records -> {day: yearly rate in percent}, summing each UTC day's payments; only days
    before ``before_day`` (closed), a malformed record dropped."""
    out = {}
    for r in records or []:
        try:
            d = int(r["time"]) // DAY_MS
            v = float(r["fundingRate"])
        except (KeyError, TypeError, ValueError):
            continue
        if d < before_day:
            out[d] = out.get(d, 0.0) + v
    return {d: round(100 * 365 * v, 2) for d, v in out.items()}


def merged(seed: dict, live: dict) -> dict:
    """The seed's rows, then the live closes after its last day."""
    rows = [list(r) for r in (seed or {}).get("rows") or []]
    last = rows[-1][0] if rows else -1
    rows += [live[d] for d in sorted(live) if d > last]
    return {"columns": ["day", "btc", "eth"], "rows": rows, "through": rows[-1][0] if rows else None,
            "unit": "yearly rate, percent", "source": "Hyperliquid funding, summed per UTC day"}


def view() -> dict:
    global _view
    if _view is None:
        _view = merged(_load(), _live)
    return _view


def _last_day() -> int:
    seed = _load()
    days = [r[0] for r in seed.get("rows") or []] + list(_live)
    return max(days) if days else 19_488


async def update(fetch=None, now_ms: Optional[int] = None) -> int:
    """Read the closed days after the last one kept (only closed days are kept, so the last one is whole).
    Returns the days added."""
    global _view
    fetch = fetch or _fetch
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    today = now_ms // DAY_MS
    start_day = _last_day() + 1
    if start_day >= today:
        return 0
    per_coin = {}
    for coin in COINS:
        records, t = [], start_day * DAY_MS
        for _ in range(MAX_PAGES):
            page = await fetch(coin, t)
            if not page:
                break
            records += page
            nxt = int(page[-1]["time"]) + 1
            if nxt <= t or nxt >= today * DAY_MS or len(page) < 500:
                break
            t = nxt
        per_coin[coin] = daily(records, today)
    added = 0
    for d in sorted(set(per_coin["BTC"]) & set(per_coin["ETH"])):
        if d >= start_day:
            _live[d] = [d, per_coin["BTC"][d], per_coin["ETH"][d]]
            added += 1
    if added:
        _save()
        _view = None
        logger.info("Funding: %d day(s) added, through %s", added, max(_live))
    return added


async def _fetch(coin: str, start_ms: int) -> list:
    import aiohttp
    import hl_calls
    await hl_calls.acquire("cohorts", "fundingHistory")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post(INFO_URL, json={"type": "fundingHistory", "coin": coin, "startTime": start_ms}) as r:
            if r.status == 429:
                hl_calls.rate_limited("cohorts")
                return []
            if r.status != 200:
                logger.info("Funding: fundingHistory %s answered %s", coin, r.status)
                return []
            return await r.json(content_type=None)


async def run_forever() -> None:
    await asyncio.sleep(300)
    while True:
        try:
            await update()
        except Exception as exc:
            logger.warning("Funding update failed: %s", exc)
        await asyncio.sleep(CHECK_EVERY_S)
