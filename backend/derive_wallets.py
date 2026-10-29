"""
Derive options wallets for the market history page's Derive drawer (docs/reviews/derive-smart-wallets.md): how
Derive's Smart options wallets were positioned at each daily close, as ranked at the time and as ranked today, and
the premium they paid on new puts. Context, not a signal.

History comes from seeds/derive_smart_seed.json, built by hand from Cowboy's records of Derive options trades
(backend/backtest/derive_smart_series.py) to 27 October 2026. Every close after it comes from Cowboy's own daily
file (smart_counts.json in its public app files, written by derive_scan's derive/smart_counts.py): the same
point-in-time counts, one row a close, read every few hours and kept in derive_live.json next to hyperlens.db so
the history outlives Cowboy's 120-row window. Those closes carry the ranking of their own day only: the hindsight
lens ("today's Smart wallets, looking back") stays the seed's, ending on its last day (``now_through``).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parent / "seeds" / "derive_smart_seed.json"
LIVE_URL = os.environ.get("DERIVE_COUNTS_URL",
                          "https://raw.githubusercontent.com/cianfru/cowboy-feed/site-data/smart_counts.json")
CHECK_EVERY_S = 3 * 3600          # Cowboy adds a row an hour or two after each 00:00 UTC close
COINS = ("BTC", "ETH", "ALL")
LIVE_COLUMNS = ["day", "btc", "eth"] + [f"{c}.{k}" for c in COINS for k in ("long", "short", "puts")]
# Tops, as the seed marks them: the highest close within TOP_WINDOW days either side, followed by a fall of TOP_FALL
# or more within TOP_AHEAD days (found with the closes after them).
TOP_WINDOW, TOP_FALL, TOP_AHEAD = 30, 0.15, 90
_EPOCH = date(1970, 1, 1)

_seed: Optional[dict] = None
_live: dict = {}                  # {"etag": str, "rows": {day (int): live row}}
_view: Optional[dict] = None


def _live_path() -> str:
    hl = os.environ.get("HYPERLENS_DB_PATH")
    base = os.path.dirname(hl) if hl else str(Path(__file__).resolve().parent)
    return os.path.join(base, "derive_live.json")


def _day(iso: str) -> int:
    return (date.fromisoformat(iso) - _EPOCH).days


def _load() -> dict:
    global _seed, _live
    if _seed is None:
        try:
            _seed = json.loads(SEED_PATH.read_text())
        except FileNotFoundError:
            _seed = {}
        try:
            saved = json.loads(Path(_live_path()).read_text())
            _live = {"etag": saved.get("etag"), "rows": {int(r[0]): r for r in saved.get("rows", [])}}
        except FileNotFoundError:
            _live = {"etag": None, "rows": {}}
        except Exception as exc:
            logger.warning("Derive counts: live file unreadable (%s); starting empty", exc)
            _live = {"etag": None, "rows": {}}
    return _seed


def _save() -> None:
    path = Path(_live_path())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"columns": ["day_n"] + LIVE_COLUMNS[1:], "etag": _live.get("etag"),
                               "rows": [_live["rows"][d] for d in sorted(_live["rows"])]}, separators=(",", ":")))
    os.replace(tmp, path)


def parse(doc: dict) -> dict:
    """Cowboy's file -> {day (int): [day, btc, eth, then long, short, puts per coin]}; {} when it is not the
    expected shape (a row with a missing or non-numeric field is dropped, never guessed)."""
    if not isinstance(doc, dict) or doc.get("schema") != 1 or doc.get("columns") != LIVE_COLUMNS:
        return {}
    out = {}
    for r in doc.get("rows") or []:
        if not isinstance(r, list) or len(r) != len(LIVE_COLUMNS):
            continue
        try:
            d = _day(r[0])
        except (TypeError, ValueError):
            continue
        vals = r[1:]
        if all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)) for v in vals):
            out[d] = [d, *vals]
    return out


def tops(prices: list) -> list:
    """Days marked as tops in [(day, close)], oldest first (the seed's rule)."""
    out = []
    for i, (d, p) in enumerate(prices):
        near = [q for _, q in prices[max(0, i - TOP_WINDOW):i + TOP_WINDOW + 1]]
        ahead = [q for _, q in prices[i + 1:i + 1 + TOP_AHEAD]]
        if p >= max(near) and ahead and min(ahead) / p - 1 <= -TOP_FALL:
            out.append(d)
    return out


def merged(seed: dict, live: dict) -> dict:
    """The seed with Cowboy's closes after its last day appended in the seed's columns (the hindsight fields
    empty), tops marked again over the longer price history, and a check of the days both cover."""
    if not seed:
        return {}
    cols = seed["columns"]
    last = seed["rows"][-1][0] if seed.get("rows") else -1
    rows = [list(r) for r in seed.get("rows") or []]
    lix = {c: i for i, c in enumerate(LIVE_COLUMNS)}
    pick = {"pit_long": "long", "pit_short": "short", "pit_puts": "puts"}
    after = [live[d] for d in sorted(live) if d > last]
    for lr in after:
        row = []
        for c in cols:
            if c == "day":
                row.append(lr[0])
            elif c in ("btc", "eth"):
                row.append(lr[lix[c]])
            else:
                coin, field = c.split(".")
                row.append(lr[lix[f"{coin}.{pick[field]}"]] if field in pick else None)
        rows.append(row)
    # Days both cover: does Cowboy's file give the seed's numbers?
    ix = {c: i for i, c in enumerate(cols)}
    seen = {r[0]: r for r in seed.get("rows") or []}
    both = [d for d in live if d in seen]
    differ = sum(1 for d in both if any(seen[d][ix[f"{c}.{f}"]] != live[d][lix[f"{c}.{pick[f]}"]]
                                        for c in COINS for f in ("pit_long", "pit_short")))
    out = dict(seed)
    out["rows"] = rows
    out["through"] = rows[-1][0] if rows else seed.get("through")
    out["now_through"] = last
    out["live_from"] = after[0][0] if after else None
    out["live_check"] = {"days": len(both), "differ": differ} if both else None
    if after:
        out["tops"] = {coin: tops([(r[0], r[ix[coin.lower()]]) for r in rows if r[ix[coin.lower()]]])
                       for coin in ("BTC", "ETH")}
    return out


def view() -> dict:
    """The drawer's feed: columns, rows (seed, then Cowboy's daily closes), tops per coin and the days it covers
    ({} without a seed)."""
    global _view
    if _view is None:
        _view = merged(_load(), _live.get("rows") or {})
    return _view


async def update(fetch=None) -> int:
    """Read Cowboy's file once (conditional on its ETag) and keep its rows. Returns the closes added or changed."""
    global _view
    _load()
    if fetch is None:
        fetch = _fetch
    status, etag, doc = await fetch(_live.get("etag"))
    if status == 304 or doc is None:
        return 0
    rows = parse(doc)
    if not rows:
        logger.warning("Derive counts: %s had no usable rows", LIVE_URL)
        return 0
    changed = sum(1 for d, r in rows.items() if _live["rows"].get(d) != r)
    _live["rows"].update(rows)
    _live["etag"] = etag
    _save()
    if changed:
        _view = None
        logger.info("Derive counts: %d close(s) added or changed, through %s", changed, max(rows))
    return changed


async def _fetch(etag: Optional[str]):
    import aiohttp
    headers = {"If-None-Match": etag} if etag else {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.get(LIVE_URL, headers=headers) as r:
            if r.status == 304:
                return 304, etag, None
            if r.status != 200:
                logger.info("Derive counts: %s answered %s", LIVE_URL, r.status)
                return r.status, etag, None
            return 200, r.headers.get("ETag"), json.loads(await r.text())


async def run_forever() -> None:
    await asyncio.sleep(240)
    while True:
        try:
            await update()
        except Exception as exc:
            logger.warning("Derive counts update failed: %s", exc)
        await asyncio.sleep(CHECK_EVERY_S)
