"""
Who uses the app, how much, from where and which features: the owner's Intel page.

The app sends small batches of named events (usage_api.py, the beacon). Each batch is
stored as counts per day, person and event, one row per session (country, city, device
class, browser family) and the days a person was active. People are invites
(invites.py), "shared" (the shared access code) or "open" (no access code configured).

Kept for 180 days (REFLEX_USAGE_DAYS); the per-person summary (first and last seen)
stays while the person does. Days are calendar days in REFLEX_USAGE_TZ (Europe/Rome).
"""
from __future__ import annotations

import os
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

import invites
import usage_db as db

TRUE = ("1", "true", "on", "yes")

# Event -> allowed detail values (None: no detail kept).
EVENTS: Dict[str, Optional[frozenset]] = {
    "view_scanner": None,
    "view_radar": None,
    "view_traders": None,
    "view_coin": None,
    "view_trader": None,
    "view_page": frozenset({"signals", "analytics", "tradfi", "bridge", "ai", "backtest", "executor",
                            "portfolio", "settings"}),
    "search": None,
    "radar_tab": frozenset({"long", "short", "both"}),
    "follow": None,
    "watch": None,
    "telegram_link": None,
    "wallet_signin": None,
    "theme": frozenset({"dark", "light"}),
}
FEATURE_NAMES = {
    "view_scanner": "Scanner", "view_radar": "Radar", "view_traders": "Traders", "view_coin": "Coin page",
    "view_trader": "Trader profile", "view_page": "Other pages", "search": "Search", "radar_tab": "Radar side",
    "follow": "Follow", "watch": "Watch", "telegram_link": "Telegram", "wallet_signin": "Wallet sign-in",
    "theme": "Theme",
}
MAX_EVENTS = 50            # per batch
MAX_BODY = 8 * 1024        # bytes per batch
DAILY_CAP = 3000           # events per person per day; more are dropped
SID_RE = re.compile(r"^[a-z0-9]{8,32}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


def enabled() -> bool:
    return os.environ.get("REFLEX_USAGE", "1").strip().lower() in TRUE


def keep_days() -> int:
    try:
        return max(1, int(os.environ.get("REFLEX_USAGE_DAYS", 180)))
    except ValueError:
        return 180


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(os.environ.get("REFLEX_USAGE_TZ", "Europe/Rome"))
    except Exception:
        return None


def day_of(ts: float) -> str:
    tz = _tz()
    return (datetime.fromtimestamp(ts, tz) if tz else datetime.utcfromtimestamp(ts)).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ what a request tells
def device_of(ua: Optional[str]) -> Tuple[str, str]:
    """(device class, browser family) from a user agent; the string itself is not kept."""
    ua = ua or ""
    if re.search(r"iPad|Tablet|Android(?!.*Mobile)", ua):
        device = "tablet"
    elif re.search(r"Mobi|iPhone|iPod|Android", ua):
        device = "phone"
    elif ua:
        device = "desktop"
    else:
        device = "unknown"
    for pattern, name in ((r"MetaMaskMobile|Rabby|Phantom|Trust/|CoinbaseWallet", "wallet app"),
                          (r"Edg[A]?/|EdgiOS", "Edge"), (r"OPR/|Opera", "Opera"),
                          (r"SamsungBrowser", "Samsung"), (r"Firefox/|FxiOS", "Firefox"),
                          (r"Brave", "Brave"), (r"Chrome/|CriOS|Chromium", "Chrome"), (r"Safari/", "Safari")):
        if re.search(pattern, ua):
            return device, name
    return device, "other"


def _clean_city(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        city = str(raw)
        for _ in range(2):          # the CDN encodes it; a rewrite may encode it again
            if "%" not in city:
                break
            city = unquote(city)
    except Exception:
        return None
    city = " ".join(city.split())[:40]
    return city if city and re.match(r"^[^\x00-\x1f<>]+$", city) else None


def geo_of(headers, query=None) -> Tuple[Optional[str], Optional[str]]:
    """(country, city) from the CDN's location headers, or from the query the same-origin
    rewrite adds (frontend/vercel.json). None when neither is there."""
    query = query or {}
    country = (headers.get("x-vercel-ip-country") or headers.get("cf-ipcountry") or query.get("cc") or "")
    country = str(country).strip().upper()
    if not COUNTRY_RE.match(country) or country in ("XX", "T1", "ZZ"):
        return None, None
    city = _clean_city(headers.get("x-vercel-ip-city") or query.get("city"))
    return country, city


# ------------------------------------------------------------------ validation
def clean_events(raw) -> List[Tuple[str, str]]:
    """Known events only, detail values from each event's list; at most MAX_EVENTS."""
    out: List[Tuple[str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw[:MAX_EVENTS]:
        if isinstance(item, str):
            name, v = item, ""
        elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
            name, v = item[0], item[1] if len(item) > 1 and isinstance(item[1], str) else ""
        else:
            continue
        if name not in EVENTS:
            continue
        allowed = EVENTS[name]
        if allowed is None:
            v = ""
        elif v not in allowed:
            continue
        out.append((name, v))
    return out


# ------------------------------------------------------------------ storing
_day_totals: Dict[Tuple[str, str], int] = {}
_last_prune = {"day": None}


def ingest(person: str, sid: str, events: List[Tuple[str, str]], *, country: Optional[str] = None,
           city: Optional[str] = None, device: str = "unknown", browser: str = "other",
           wallet: Optional[bool] = None, telegram: Optional[bool] = None, now: Optional[float] = None) -> int:
    """Store one batch. Returns how many events were kept."""
    now = now or time.time()
    if not SID_RE.match(sid or "") or not events:
        return 0
    day = day_of(now)
    total_key = (day, person)
    room = DAILY_CAP - _day_totals.get(total_key, 0)
    if room <= 0:
        return 0
    events = events[:room]
    if len(_day_totals) > 5000:
        _day_totals.clear()
    _day_totals[total_key] = _day_totals.get(total_key, 0) + len(events)
    with db.lock:
        row = db.q("SELECT person FROM sessions WHERE sid = ?", (sid,))
        if row and row[0][0] != person:
            return 0
        if row:
            db.x("UPDATE sessions SET last = ?, n = n + ?, country = COALESCE(country, ?), city = COALESCE(city, ?) "
                 "WHERE sid = ?", (now, len(events), country, city, sid))
        else:
            db.x("INSERT INTO sessions (sid, person, day, start, last, n, country, city, device, browser) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (sid, person, day, now, now, len(events), country, city, device, browser))
        for (name, v), n in Counter(events).items():
            db.x("INSERT INTO counts (day, person, name, v, n) VALUES (?, ?, ?, ?, ?) "
                 "ON CONFLICT (day, person, name, v) DO UPDATE SET n = n + excluded.n", (day, person, name, v, n))
        db.x("INSERT OR IGNORE INTO activity (person, day) VALUES (?, ?)", (person, day))
        if db.q("SELECT 1 FROM people WHERE person = ?", (person,)):
            db.x("UPDATE people SET last_seen = ? WHERE person = ?", (now, person))
        else:
            db.x("INSERT INTO people (person, first_seen, last_seen) VALUES (?, ?, ?)", (person, now, now))
        if wallet or any(n == "wallet_signin" for n, _ in events):
            db.x("UPDATE people SET wallet = 1 WHERE person = ?", (person,))
        if telegram is not None:
            db.x("UPDATE people SET telegram = ? WHERE person = ?", (1 if telegram else 0, person))
    if _last_prune["day"] != day:
        _last_prune["day"] = day
        prune(now)
    return len(events)


def set_geo(sid: str, country: Optional[str], city: Optional[str]) -> None:
    """Fill a session's location once it is known (the optional lookup, usage_geo.py)."""
    if country:
        db.x("UPDATE sessions SET country = COALESCE(country, ?), city = COALESCE(city, ?) WHERE sid = ?",
             (country, city, sid))


def prune(now: Optional[float] = None) -> None:
    cutoff = day_of((now or time.time()) - keep_days() * 86400)
    with db.lock:
        db.x("DELETE FROM sessions WHERE day < ?", (cutoff,))
        db.x("DELETE FROM activity WHERE day < ?", (cutoff,))
        db.x("DELETE FROM counts WHERE day < ?", (cutoff,))


def reset_memory() -> None:
    _day_totals.clear()
    _last_prune["day"] = None


# ------------------------------------------------------------------ aggregates
def _d(s: str) -> date:
    return date.fromisoformat(s)


def _active_days() -> Dict[str, set]:
    out: Dict[str, set] = defaultdict(set)
    for p, d in db.q("SELECT person, day FROM activity"):
        out[p].add(d)
    return out


def active_between(days_by_person: Dict[str, set], first: date, last: date) -> int:
    lo, hi = first.isoformat(), last.isoformat()
    return sum(1 for ds in days_by_person.values() if any(lo <= d <= hi for d in ds))


def first_days(days_by_person: Dict[str, set]) -> Dict[str, date]:
    """Each person's first active day: people.first_seen when known (it outlives the
    180-day window), else the earliest stored day."""
    seen = {p: _d(day_of(f)) for p, f in db.q("SELECT person, first_seen FROM people") if f}
    return {p: seen.get(p) or _d(min(ds)) for p, ds in days_by_person.items() if ds}


def week4(days_by_person: Dict[str, set], today: date) -> dict:
    """The beta bar: of the people whose first day was 35+ days ago (so their fourth week
    after it, days 28 to 34, is over), the share active in that week."""
    firsts = first_days(days_by_person)
    eligible = [p for p, f in firsts.items() if (today - f).days >= 34]
    kept = 0
    for p in eligible:
        f = firsts[p]
        lo, hi = (f + timedelta(days=28)).isoformat(), (f + timedelta(days=34)).isoformat()
        kept += any(lo <= d <= hi for d in days_by_person[p])
    return {"n": len(eligible), "kept": kept, "share": (kept / len(eligible)) if eligible else None,
            "pending": sum(1 for p, f in firsts.items() if (today - f).days < 34)}


def daily_active(days_by_person: Dict[str, set], today: date, span: int = 90) -> List[dict]:
    per_day = Counter(d for ds in days_by_person.values() for d in ds)
    return [{"day": (today - timedelta(days=i)).isoformat(), "n": per_day.get((today - timedelta(days=i)).isoformat(), 0)}
            for i in range(span - 1, -1, -1)]


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def retention_grid(days_by_person: Dict[str, set], today: date, cohorts: int = 12) -> List[dict]:
    """Rows: the week people first used the app (Monday). Cells: the share of that row's
    people active in week 0, 1, 2... after it (up to the current week)."""
    firsts = first_days(days_by_person)
    by_week: Dict[date, List[str]] = defaultdict(list)
    for p, f in firsts.items():
        by_week[_monday(f)].append(p)
    this_week = _monday(today)
    rows = []
    for wk in sorted(by_week)[-cohorts:]:
        people = by_week[wk]
        weeks = (this_week - wk).days // 7 + 1
        cells = []
        for k in range(weeks):
            lo = wk + timedelta(days=7 * k)
            hi = lo + timedelta(days=6)
            n = sum(1 for p in people if any(lo.isoformat() <= d <= hi.isoformat() for d in days_by_person[p]))
            cells.append({"n": n, "share": n / len(people)})
        rows.append({"week": wk.isoformat(), "size": len(people), "cells": cells})
    return rows


def summary(now: Optional[float] = None) -> dict:
    """Everything the Intel page shows, in one answer."""
    now = now or time.time()
    today = _d(day_of(now))
    days = _active_days()
    labels = invites.labels()
    inv = invites.all_invites()
    live = [i for i in inv if i["revoked"] is None]

    top = {
        "today": active_between(days, today, today),
        "d7": active_between(days, today - timedelta(days=6), today),
        "d28": active_between(days, today - timedelta(days=27), today),
        "invited": len(live),
        "logged_in": sum(1 for i in live if i["first_login"]),
        "week4": week4(days, today),
    }

    # People
    lo7, lo28 = (today - timedelta(days=6)).isoformat(), (today - timedelta(days=27)).isoformat()
    feats: Dict[str, Counter] = defaultdict(Counter)
    for p, name, n in db.q("SELECT person, name, SUM(n) FROM counts WHERE day >= ? GROUP BY person, name", (lo28,)):
        feats[p][name] += n
    latest: Dict[str, tuple] = {}
    n_sessions: Counter = Counter()
    for p, c, city, dev, br, start in db.q(
            "SELECT person, country, city, device, browser, start FROM sessions ORDER BY start"):
        n_sessions[p] += 1
        prev = latest.get(p)
        latest[p] = (c or (prev[0] if prev else None), city or (prev[1] if prev else None), dev, br)
    last28 = [(today - timedelta(days=i)).isoformat() for i in range(27, -1, -1)]
    revoked = {i["id"] for i in inv if i["revoked"] is not None}
    people = []
    for p, first, last, wallet, tg in db.q("SELECT person, first_seen, last_seen, wallet, telegram FROM people"):
        ds = days.get(p, set())
        geo = latest.get(p, (None, None, None, None))
        people.append({
            "id": p, "label": labels.get(p, p), "first_seen": first, "last_seen": last,
            "d7": sum(1 for d in ds if d >= lo7), "d28": sum(1 for d in ds if d >= lo28), "days": len(ds),
            "sessions": n_sessions.get(p, 0), "recent": [1 if d in ds else 0 for d in last28],
            "revoked": p in revoked,
            "top": [FEATURE_NAMES[n] for n, _ in feats[p].most_common(3)],
            "country": geo[0], "city": geo[1], "device": geo[2], "browser": geo[3],
            "wallet": bool(wallet), "telegram": bool(tg),
        })
    # Invites nobody has used yet still show, as not seen.
    seen = {x["id"] for x in people}
    for i in live:
        if i["id"] not in seen:
            people.append({"id": i["id"], "label": i["label"], "first_seen": None, "last_seen": None, "d7": 0,
                           "d28": 0, "days": 0, "sessions": 0, "recent": [0] * 28, "revoked": False, "top": [], "country": None, "city": None,
                           "device": None, "browser": None, "wallet": False, "telegram": False})

    # Features: events and people over 28 days; returning (2+ active days) vs one-time users.
    total: Counter = Counter()
    users: Dict[str, set] = defaultdict(set)
    for p, c in feats.items():
        for name, n in c.items():
            total[name] += n
            users[name].add(p)
    ever: Dict[str, set] = defaultdict(set)
    for p, name in db.q("SELECT DISTINCT person, name FROM counts"):
        ever[name].add(p)
    returning = {p for p, ds in days.items() if len(ds) >= 2}
    once = {p for p, ds in days.items() if len(ds) == 1}
    features = []
    for name in EVENTS:
        features.append({
            "key": name, "name": FEATURE_NAMES[name], "events": total.get(name, 0), "people": len(users.get(name, ())),
            "returning": (len(ever[name] & returning) / len(returning)) if returning else None,
            "once": (len(ever[name] & once) / len(once)) if once else None,
        })
    features.sort(key=lambda f: (-f["events"], f["name"]))

    radar_sides = {v: n for v, n in db.q(
        "SELECT v, SUM(n) FROM counts WHERE name = 'radar_tab' AND day >= ? GROUP BY v", (lo28,))}

    # Places: people and sessions per country (28 days), with the top city.
    per_country: Dict[str, dict] = {}
    for p, c, city in db.q("SELECT person, country, city FROM sessions WHERE day >= ?", (lo28,)):
        key = c or "?"
        e = per_country.setdefault(key, {"country": c, "people": set(), "sessions": 0, "cities": Counter()})
        e["people"].add(p)
        e["sessions"] += 1
        if city:
            e["cities"][city] += 1
    countries = sorted(({"country": e["country"], "people": len(e["people"]), "sessions": e["sessions"],
                         "cities": [c for c, _ in e["cities"].most_common(3)]} for e in per_country.values()),
                       key=lambda e: (-e["people"], -e["sessions"]))
    devices = Counter(p["device"] for p in people if p["device"])

    return {
        "now": now, "today": today.isoformat(), "keep_days": keep_days(), "recording": enabled(),
        "top": top, "dau": daily_active(days, today), "retention": retention_grid(days, today),
        "people": people, "features": features, "radar_sides": radar_sides, "countries": countries,
        "devices": dict(devices), "invites": inv,
    }
