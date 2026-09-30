"""
Telegram alerts per account, fanned out from the shared readings.

Followed wallets are read once for everyone (followed_traders.addresses includes every
account's follows); each change comes here once and goes to every linked account that
follows the wallet. Watched coins are compared against the shared Radar map every five
minutes. Each account has its own delivery record and settings, and every message goes
through the same gate as the owner's (tg_alerts.gate: categories, once per key a day,
a daily cap, quiet hours, held alerts listed in the next brief).

Only accounts with a linked chat and the holder features (tiers.allows) receive alerts.
The owner's account is the single-owner setup and is served by tg_alerts directly.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Dict, List, Optional

import accounts
import tg_alerts as ta

logger = logging.getLogger(__name__)

CATEGORIES = ("followed", "watched")
_locks: Dict[str, asyncio.Lock] = {}


def defaults() -> dict:
    d = ta.defaults()
    return {"on": {c: True for c in CATEGORIES}, "brief": True, "quiet": d["quiet"], "paused_until": 0.0,
            "cap": d["cap"], "follow_min_usd": d["follow_min_usd"]}


def blank() -> dict:
    return {"settings": defaults(), "sent": {}, "held": [], "period": 0.0, "count": 0,
            "last_brief": "", "watch": {}, "brief_watch": {}}


USER_SET = ("on", "brief", "quiet", "paused_until")       # what an account changes itself


def state(user: str) -> dict:
    """The account's delivery record; the cap and the size threshold always come from the env."""
    st = blank()
    raw = accounts.tg_state(user) or {}
    for k in st:
        if k in raw:
            st[k] = raw[k]
    s = defaults()
    s.update({k: v for k, v in (raw.get("settings") or {}).items() if k in USER_SET})
    s["on"] = {c: bool((s.get("on") or {}).get(c, True)) for c in CATEGORIES}
    st["settings"] = s
    return st


def save(user: str, st: dict) -> None:
    accounts.tg_save_state(user, st)


def set_prefs(user: str, quiet="keep", brief: Optional[bool] = None) -> dict:
    st = state(user)
    if quiet != "keep":
        if quiet:
            ta.parse_hhmm(quiet[0]), ta.parse_hhmm(quiet[1])
            st["settings"]["quiet"] = [str(quiet[0]), str(quiet[1])]
        else:
            st["settings"]["quiet"] = None
    if brief is not None:
        st["settings"]["brief"] = bool(brief)
    save(user, st)
    return st["settings"]


def _lock(user: str) -> asyncio.Lock:
    lk = _locks.get(user)
    if lk is None:
        if len(_locks) > 10_000:
            _locks.clear()
        lk = _locks[user] = asyncio.Lock()
    return lk


async def submit(user: str, chat_id: int, cat: str, key: str, text: str, line: Optional[str] = None,
                 now: Optional[float] = None) -> str:
    """tg_alerts.submit for one account: "off", "dup", "held", "sent" or "nobody"."""
    now = now or time.time()
    async with _lock(user):
        st = state(user)
        verdict = ta.gate(st, cat, key, text, line, now)
        if verdict in ("off", "dup"):
            return verdict
        if verdict == "send":
            n = await ta._deliver([chat_id], text)
            if n:
                st["count"] += 1
            verdict = "sent" if n else "nobody"
        save(user, st)
        return verdict


async def _eligible(user: str) -> Optional[int]:
    """The account's chat when it should get alerts (linked, holder features), else None."""
    if accounts.is_owner(user):
        return None
    chat = accounts.tg_chat(user)
    if chat is None:
        return None
    import tiers
    return chat if await tiers.allows(user) else None


# ------------------------------------------------------------------ followed wallets
def followed_changes(wallet: str, cohort: str, ts: float, changes: List[dict], holdings: List[dict]) -> None:
    """One wallet's changes (from the shared reading): stored once for the accounts that
    follow it, then sent to each of them. Synchronous; delivery runs as a task."""
    if not accounts.enabled() or not changes:
        return
    followers = [(u, n) for u, n in accounts.followers_of(wallet) if not accounts.is_owner(u)]
    if not followers:
        return
    accounts.record_events(wallet, cohort, ts, changes)
    try:
        asyncio.get_running_loop().create_task(fan_out(wallet, cohort, changes, holdings, followers))
    except RuntimeError:
        logger.debug("account alerts: no running loop")


async def fan_out(wallet: str, cohort: str, changes: List[dict], holdings: List[dict],
                  followers, now: Optional[float] = None) -> Dict[str, List[str]]:
    import followed_traders as ft
    out: Dict[str, List[str]] = {}
    label = ft.cohort_label(cohort)
    for user, note in followers:
        chat = await _eligible(user)
        if chat is None:
            continue
        min_usd = float(state(user)["settings"].get("follow_min_usd") or ft.MIN_USD)
        for c in ft.alerts(changes, min_usd):
            text = ft.message(wallet, label, c, holdings, note=note)
            out.setdefault(user, []).append(
                await submit(user, chat, "followed", f"{wallet}:{c['coin']}:{c['kind']}", text, text.split("\n")[0], now))
    return out


# ------------------------------------------------------------------ watched coins
MapProvider = Callable[[str], Awaitable[dict]]


async def check_watched(provider: MapProvider, now: Optional[float] = None) -> Dict[str, List[str]]:
    """Every linked account's watched coins against the shared map (built once per timeframe)."""
    out: Dict[str, List[str]] = {}
    if not accounts.enabled():
        return out
    lists = accounts.all_watch()
    maps: Dict[str, dict] = {}
    for user, watched in lists.items():
        chat = await _eligible(user)
        if chat is None:
            continue
        for tf in {w["tf"] for w in watched.values()} - set(maps):
            maps[tf] = await provider(tf)

        async def send(cat, key, text, line=None, now=None, _u=user, _c=chat):
            return await submit(_u, _c, cat, key, text, line, now)
        async with _lock(user):
            last = state(user)["watch"]
        res, dirty = await ta.watch_pass(watched, maps, last, send, now)
        if dirty:
            async with _lock(user):
                st = state(user)
                st["watch"] = last
                save(user, st)
        out[user] = res
    return out


async def run(provider: MapProvider, interval: int = 300) -> None:
    """The watched-coins pass every five minutes while accounts are on."""
    await asyncio.sleep(150)
    while True:
        try:
            if accounts.enabled():
                await check_watched(provider)
        except Exception as exc:
            logger.warning("account alerts: %s", exc)
        await asyncio.sleep(interval)
