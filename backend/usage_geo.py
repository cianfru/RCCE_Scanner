"""
Where a session comes from, when the request itself does not say.

The usual source is the CDN: the app's first beacon of a session goes through its own
site (a rewrite in frontend/vercel.json), which adds the visitor's country and city.
When that is missing and REFLEX_USAGE_GEO_LOOKUP=1, the country and city are looked up
once per visitor per day from a public IP-location service, in the background. The
address is never stored: the day's cache is keyed by a salted hash whose salt changes
every day and lives only in memory.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
from typing import Dict, Optional, Tuple

import usage

TRUE = ("1", "true", "on", "yes")
URL = os.environ.get("REFLEX_USAGE_GEO_URL", "https://ipapi.co/{ip}/json/")
_MAX = 5000

_salt = {"day": None, "salt": b""}
_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
_pending: set = set()


def lookup_on() -> bool:
    return os.environ.get("REFLEX_USAGE_GEO_LOOKUP", "").strip().lower() in TRUE


def visitor_key(ip: str, day: str) -> str:
    """A salted hash of the address, valid for one day (the salt is replaced daily)."""
    if _salt["day"] != day:
        _salt.update(day=day, salt=secrets.token_bytes(16))
        _cache.clear()
        _pending.clear()
    return hashlib.sha256(_salt["salt"] + ip.encode()).hexdigest()[:24]


async def _fetch(ip: str) -> Tuple[Optional[str], Optional[str]]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=4)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(URL.format(ip=ip)) as r:
            if r.status != 200:
                return None, None
            d = await r.json(content_type=None)
    country = str(d.get("country_code") or d.get("countryCode") or "").upper()
    if not usage.COUNTRY_RE.match(country):
        return None, None
    return country, usage._clean_city(d.get("city"))


def schedule(ip: str, sid: str, day: str, fetch=None) -> None:
    """Look the address up at most once today, then fill the session's location."""
    if not ip or ip == "unknown" or not lookup_on():
        return
    k = visitor_key(ip, day)
    if k in _cache:
        usage.set_geo(sid, *_cache[k])
        return
    if k in _pending or len(_cache) >= _MAX:
        return
    _pending.add(k)

    async def run():
        try:
            res = await (fetch or _fetch)(ip)
        except Exception:
            res = (None, None)
        _cache[k] = res
        _pending.discard(k)
        usage.set_geo(sid, *res)

    try:
        asyncio.get_running_loop().create_task(run())
    except RuntimeError:
        _pending.discard(k)
