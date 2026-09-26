"""
When and where the profitable traders holding a coin got in.

The cohort sweep only sees positions (size and average entry), not when they were built.
Hyperliquid publishes every wallet's fills, so for the few profitable traders holding a
coin we fetch them on demand, when someone opens that coin's chart, and cache the answer.
Timed orders (TWAP) fill in slices that come from a separate request.

Each fill carries the position size before it (``startPosition``), so the current
position's start is the last fill that opened it from flat or flipped its side. Fills are
grouped into bursts: same action, less than BURST_GAP_S apart.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import time
from typing import Dict, List, Optional

import aiohttp

from cohorts.sweeper import TokenBucket

logger = logging.getLogger(__name__)

INFO_URL = "https://api.hyperliquid.xyz/info"
MAX_TRADERS = 6               # largest positions first
MAX_BURSTS = 20               # latest bursts per trader
BURST_GAP_S = 30 * 60
BUYING_NOW_S = 5 * 60          # a timed-order slice this recent means it is still running
CACHE_S = 10 * 60
ANSWER_WITHIN_S = 8            # answer with what is ready; the rest keeps loading
# Hyperliquid charges 20 weight per fills request plus 1 per 20 fills returned. This feature
# gets its own small share of the per-IP budget so it cannot starve the cohort sweep.
_bucket = TokenBucket(480, capacity=480)
_CALL_WEIGHT = 20

_DIRS = {
    "Open Long": ("open", "long"), "Close Long": ("close", "long"),
    "Open Short": ("open", "short"), "Close Short": ("close", "short"),
    "Short > Long": ("open", "long"), "Long > Short": ("open", "short"),
}

_fills_cache: Dict[str, tuple] = {}     # address -> (fetched_at, {fills, covered_from})
_result_cache: Dict[str, tuple] = {}    # coin -> (fetched_at, result)
_tasks: Dict[str, asyncio.Task] = {}    # coin -> background fetch of its holders' fills


async def _post(session: aiohttp.ClientSession, body: dict):
    await _bucket.take(_CALL_WEIGHT)
    async with session.post(INFO_URL, json=body) as resp:
        if resp.status == 429:
            _bucket.penalize()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    if isinstance(data, list) and len(data) >= 20:
        await _bucket.take(len(data) // 20)
    return data


def _prune() -> None:
    """Drop expired entries so the caches only ever hold the last ten minutes of views."""
    now = time.time()
    for cache in (_fills_cache, _result_cache):
        for k in [k for k, v in cache.items() if now - v[0] >= CACHE_S]:
            del cache[k]
    for k in [k for k, t in _tasks.items() if t.done()]:
        del _tasks[k]


def _fresh(address: str) -> Optional[dict]:
    hit = _fills_cache.get(address)
    return hit[1] if hit and time.time() - hit[0] < CACHE_S else None


async def _wallet_fills(session, address: str) -> dict:
    """The wallet's latest fills (up to 2,000, same-time fills merged) plus its timed-order slices
    (latest 2,000). ``covered_from``: fills may be missing before this time (None: full history).
    """
    hit = _fresh(address)
    if hit is not None:
        return hit
    regular = await _post(session, {"type": "userFills", "user": address, "aggregateByTime": True})
    twap = await _post(session, {"type": "userTwapSliceFills", "user": address})
    # Keep only the fields the bursts need: a full fill is ~20 fields, and up to 4,000 per wallet.
    slim = lambda f, tw: {"coin": f.get("coin"), "time": f["time"], "px": f["px"], "sz": f["sz"], "side": f.get("side"),
                          "dir": f.get("dir"), "startPosition": f.get("startPosition"), "twap": tw, "tid": f.get("tid")}
    fills = [slim(f, False) for f in regular] + [slim(x["fill"], True) for x in twap]
    seen, out = set(), []
    for f in sorted(fills, key=lambda f: f["time"]):
        key = (f["tid"], f["time"], f["px"], f["sz"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    # Both lists are capped at the latest 2,000; before the later of their oldest entries, fills may be missing.
    limits = [min(f["time"] for f in lst) / 1000 for lst in (regular, [x["fill"] for x in twap]) if len(lst) >= 2000]
    covered = max(limits) if limits else None
    res = {"fills": out, "covered_from": covered}
    _prune()
    _fills_cache[address] = (time.time(), res)
    return res


def position_bursts(fills: List[dict], coin: str, now_s: Optional[float] = None) -> dict:
    """The current position's start and its bursts, from one wallet's fills (time-sorted)."""
    now_s = time.time() if now_s is None else now_s
    fs = [f for f in fills if f.get("coin") == coin and f.get("dir") in _DIRS]
    start = None
    for i, f in enumerate(fs):
        before = float(f.get("startPosition") or 0)
        delta = float(f["sz"]) * (1 if f.get("side") == "B" else -1)
        after = before + delta
        if before == 0 or (before > 0) != (after > 0):
            start = i
    cur = fs[start:] if start is not None else fs
    bursts: List[dict] = []
    for f in cur:
        kind, side = _DIRS[f["dir"]]
        t, px, sz = f["time"] / 1000, float(f["px"]), float(f["sz"])
        b = bursts[-1] if bursts else None
        if b and b["kind"] == kind and b["side"] == side and b["twap"] == bool(f.get("twap")) \
                and t - b["t_end"] <= BURST_GAP_S:
            b["t_end"], b["_sz"], b["_notional"], b["fills"] = t, b["_sz"] + sz, b["_notional"] + px * sz, b["fills"] + 1
        else:
            bursts.append({"t": t, "t_end": t, "kind": kind, "side": side, "twap": bool(f.get("twap")),
                           "_sz": sz, "_notional": px * sz, "fills": 1})
    for b in bursts:
        b["px"] = b["_notional"] / b["_sz"]
        b["usd"] = round(b.pop("_notional"))
        b.pop("_sz")
    last_twap = max((f["time"] / 1000 for f in cur if f.get("twap")), default=None)
    return {"opened_at": cur[0]["time"] / 1000 if start is not None and cur else None,
            "buying_now": bool(last_twap and now_s - last_twap <= BUYING_NOW_S),
            "bursts": bursts[-MAX_BURSTS:], "bursts_total": len(bursts)}


def _side_summary(traders: List[dict]) -> dict:
    out = {}
    for side in ("long", "short"):
        ts = [t for t in traders if t["side"] == side]
        out[side] = {"n": len(ts), "usd": round(sum(t["size_usd"] for t in ts)),
                     "median_entry": statistics.median(t["entry_px"] for t in ts) if ts else None}
    return out


async def _fetch_all(addresses: List[str]) -> None:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        for a in addresses:
            if _fresh(a) is None:
                try:
                    await _wallet_fills(session, a)
                except Exception as exc:
                    logger.warning("trader entries: fills for %s failed: %s", a[:10], exc)


async def entries_for(symbol: str) -> dict:
    from hl_intelligence import _normalize_coin, get_symbol_positions
    coin = _normalize_coin(symbol)
    _prune()
    hit = _result_cache.get(coin)
    if hit and time.time() - hit[0] < CACHE_S:
        return _with_others(hit[1])
    held = [p for p in get_symbol_positions(coin)
            if "money_printer" in p.get("cohorts", []) and not p.get("coin", "").startswith("xyz:")]
    held.sort(key=lambda p: -p["size_usd"])
    held = held[:MAX_TRADERS]
    missing = [p["address"] for p in held if _fresh(p["address"]) is None]
    if missing:
        task = _tasks.get(coin)
        if task is None or task.done():
            task = _tasks[coin] = asyncio.create_task(_fetch_all(missing))
        try:
            await asyncio.wait_for(asyncio.shield(task), ANSWER_WITHIN_S)
        except asyncio.TimeoutError:
            pass
    now = time.time()
    traders, pending = [], False
    for i, p in enumerate(held):
        t = {"label": chr(ord("A") + i), "address": p["address"], "side": p["side"].lower(),
             "entry_px": p["entry_px"], "size_usd": p["size_usd"], "pnl_pct": p["pnl_pct"],
             "leverage": p.get("leverage"), "opened_at": None, "covered_from": None,
             "buying_now": False, "bursts": [], "pending": False}
        got = _fresh(p["address"])
        if got is None:
            t["pending"] = pending = True
        else:
            t.update(position_bursts(got["fills"], p["coin"], now), covered_from=got["covered_from"])
        traders.append(t)
    result = {"symbol": coin, "updated_at": now, "traders": traders,
              "sides": _side_summary(traders), "pending": pending}
    if not pending:
        _result_cache[coin] = (now, result)
    return _with_others(result)


def _with_others(result: dict) -> dict:
    """Each trader's other positions, from the latest reading (not cached with the fills)."""
    from hl_intelligence import wallet_positions
    traders = []
    for t in result["traders"]:
        w = wallet_positions(t["address"])
        traders.append({**t, "account_value": w["account_value"],
                        "others": [p for p in w["positions"] if p["coin"] != result["symbol"]]})
    return {**result, "traders": traders}
