"""
Telegram delivery rules: which alerts go out at once, and when.

Every instant message goes through ``submit``. A category that is off sends nothing. The
same category and key (a coin and what happened to it) goes out at most once in 24 hours.
At most ``cap`` alerts go out between two daily briefs; the rest, and anything that comes
in during quiet hours or a pause, is held and listed in the next brief. Liquidation
warnings are the one exception: they ignore quiet hours and the cap (still once per key).

What /alerts changes (categories, the brief, quiet hours, pause) and the delivery record
(sent keys, held alerts, the count since the last brief, the watched coins' last readings)
live in one small JSON file on the data volume, next to watched_coins.json. The defaults
and the cap and thresholds come from the environment (TELEGRAM_QUIET, TELEGRAM_DAILY_CAP,
TELEGRAM_FOLLOW_MIN_USD, TELEGRAM_LIQ_PCT; TELEGRAM_BRIEF_TIME and TELEGRAM_TZ for time).

Messages use Telegram's HTML mode: ``esc`` every value that is not markup.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

TZ_NAME = os.environ.get("TELEGRAM_TZ", "Europe/Rome")
BRIEF_TIME = os.environ.get("TELEGRAM_BRIEF_TIME", "08:00")
DEDUPE_S = 24 * 3600
HELD_MAX = 60


def _env_quiet() -> Optional[List[str]]:
    raw = os.environ.get("TELEGRAM_QUIET", "23:00-07:30").strip().lower()
    if raw in ("", "off", "none"):
        return None
    try:
        a, b = raw.split("-")
        parse_hhmm(a), parse_hhmm(b)
        return [a.strip(), b.strip()]
    except ValueError:
        return ["23:00", "07:30"]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# key, label, on by default. The first four are what the owner acts on; the rest stay
# available behind "More" in /alerts.
CATEGORIES: List[Tuple[str, str, bool]] = [
    ("positions", "My positions", True),
    ("watched", "Watched coins", True),
    ("followed", "Followed traders", True),
    ("anomalies", "Anomalies on my coins", True),
    ("signals", "4H signal changes, all coins", False),
    ("whales", "Whale follows", False),
    ("bridge", "Bridge flow", False),
    ("anomalies_all", "All critical anomalies", False),
    ("position_notes", "Position notes: heat, OI, regime", False),
    ("opportunities", "Opportunities: BTC ETH SOL HYPE", False),
    ("overview", "Portfolio overview every 6h", False),
    ("market_shift", "Consensus changes", False),
    ("watched_more", "Watched coins: other changes", False),
]
CORE = [c for c, _, on in CATEGORIES if on]
LABEL = {c: label for c, label, _ in CATEGORIES}
QUIET_PRESETS = [["23:00", "07:30"], ["22:00", "08:00"], ["00:00", "07:00"], None]
CHAT_SET = ("on", "brief", "quiet", "paused_until")        # settings changed from the chat


def defaults() -> dict:
    return {"on": {c: on for c, _, on in CATEGORIES}, "brief": True, "quiet": _env_quiet(),
            "paused_until": 0.0, "cap": _env_int("TELEGRAM_DAILY_CAP", 6),
            "follow_min_usd": _env_int("TELEGRAM_FOLLOW_MIN_USD", 25_000),
            "liq_pct": _env_int("TELEGRAM_LIQ_PCT", 15)}


# ------------------------------------------------------------------ storage
_dir = Path(os.environ["RAILWAY_VOLUME_MOUNT_PATH"]) if os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") \
    else Path(__file__).resolve().parent / "data"
PATH = _dir / "telegram_alerts.json"
_state: dict = {}
_loaded = False


def _blank() -> dict:
    return {"settings": defaults(), "sent": {}, "held": [], "period": 0.0, "count": 0,
            "last_brief": "", "watch": {}, "brief_watch": {}}


def _load() -> dict:
    global _state, _loaded
    if _loaded:
        return _state
    _loaded = True
    _state = _blank()
    try:
        raw = json.loads(PATH.read_text())
        for k in _state:
            if k in raw:
                _state[k] = raw[k]
        # What the chat changes persists; the cap and the thresholds always come from the env.
        s = defaults()
        s.update({k: v for k, v in (raw.get("settings") or {}).items() if k in CHAT_SET})
        s["on"] = {**defaults()["on"], **{k: bool(v) for k, v in (s.get("on") or {}).items() if k in LABEL}}
        _state["settings"] = s
    except (OSError, ValueError, AttributeError):
        pass
    return _state


def save() -> None:
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PATH.with_suffix(".tmp")
        d = defaults()
        chat = {k: _state["settings"].get(k) for k in CHAT_SET if _state["settings"].get(k) != d.get(k)}
        tmp.write_text(json.dumps(dict(_state, settings=chat)))
        os.replace(tmp, PATH)
    except OSError as exc:
        logger.warning("telegram alerts: not saved: %s", exc)


def reset(path: Optional[Path] = None) -> None:
    """Start from a blank record (tests; a path points storage elsewhere)."""
    global PATH, _state, _loaded
    if path is not None:
        PATH = path
    _state, _loaded = _blank(), True


def state() -> dict:
    return _load()


def settings() -> dict:
    return _load()["settings"]


def enabled(cat: str) -> bool:
    return bool(settings()["on"].get(cat, False))


def set_on(cat: str, on: bool) -> None:
    if cat in LABEL:
        settings()["on"][cat] = bool(on)
        save()


def toggle(cat: str) -> bool:
    if cat == "brief":
        settings()["brief"] = not settings()["brief"]
        save()
        return settings()["brief"]
    set_on(cat, not enabled(cat))
    return enabled(cat)


def set_quiet(q: Optional[List[str]]) -> None:
    if q is not None:
        parse_hhmm(q[0]), parse_hhmm(q[1])
    settings()["quiet"] = list(q) if q else None
    save()


def cycle_quiet() -> Optional[List[str]]:
    cur = settings().get("quiet")
    i = QUIET_PRESETS.index(cur) if cur in QUIET_PRESETS else -1
    set_quiet(QUIET_PRESETS[(i + 1) % len(QUIET_PRESETS)])
    return settings()["quiet"]


def pause(hours: float = 24, now: Optional[float] = None) -> None:
    settings()["paused_until"] = (now or time.time()) + hours * 3600
    save()


def resume() -> None:
    settings()["paused_until"] = 0.0
    save()


def paused_at(s: dict, now: Optional[float] = None) -> bool:
    return (now or time.time()) < float(s.get("paused_until") or 0)


def paused(now: Optional[float] = None) -> bool:
    return paused_at(settings(), now)


# ------------------------------------------------------------------ time (Europe/Rome by default)
def tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZ_NAME)
    except Exception:                       # no tz database: fall back to UTC rather than fail
        from datetime import timezone
        return timezone.utc


def local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz())


def hm(ts: float) -> str:
    return local(ts).strftime("%H:%M")


def parse_hhmm(s: str) -> Tuple[int, int]:
    h, m = str(s).strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(s)
    return h, m


def in_quiet(ts: float, quiet: Optional[List[str]]) -> bool:
    """Quiet hours [start, end) in local time; a window past midnight wraps (23:00-07:30)."""
    if not quiet:
        return False
    d = local(ts)
    m = d.hour * 60 + d.minute
    a, b = (h * 60 + mm for h, mm in (parse_hhmm(quiet[0]), parse_hhmm(quiet[1])))
    if a == b:
        return False
    return a <= m < b if a < b else (m >= a or m < b)


def next_brief_at(ts: float, hhmm: str = None) -> datetime:
    """The next brief time strictly after ts, as an aware local datetime (DST-safe: the wall
    clock time is fixed, the UTC offset follows the date)."""
    h, m = parse_hhmm(hhmm or BRIEF_TIME)
    d = local(ts)
    cand = d.replace(hour=h, minute=m, second=0, microsecond=0)
    if cand.timestamp() <= ts:
        cand = (d + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
        cand = cand.replace(tzinfo=None).replace(tzinfo=tz())       # re-resolve the offset for that date
    return cand


def period_start(ts: float, hhmm: str = None) -> float:
    """The last brief time at or before ts: the daily cap counts from there."""
    h, m = parse_hhmm(hhmm or BRIEF_TIME)
    d = local(ts)
    cand = d.replace(hour=h, minute=m, second=0, microsecond=0)
    if cand.timestamp() > ts:
        prev = (d - timedelta(days=1)).replace(tzinfo=None).replace(hour=h, minute=m, second=0, microsecond=0)
        cand = prev.replace(tzinfo=tz())
    return cand.timestamp()


# ------------------------------------------------------------------ text
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")
_SHOUT = re.compile(r"^(?P<head>[A-Z][A-Z0-9 &()+/.,'-]{2,}?)\s*[—-]\s*(?P<coin>[A-Za-z0-9]{1,15})$")
_ACRONYM = {"OI", "CVD", "BTC", "HL", "VPIN", "LSR", "PNL", "AV"}


def esc(v) -> str:
    return html.escape(str(v), quote=False)


def coin_b(coin: str) -> str:
    return f"<b>{esc(coin)}</b>"


def usd(v: float) -> str:
    a = abs(v or 0)
    s = "-" if (v or 0) < 0 else ""
    if a >= 1e6:
        return f"{s}${a / 1e6:.1f}M"
    if a >= 1e3:
        return f"{s}${a / 1e3:.0f}K"
    return f"{s}${a:.0f}"


def px(v) -> str:
    if not v:
        return "?"
    return f"{v:,.0f}" if v >= 1000 else f"{v:.4g}"


def strip_emoji(text: str) -> str:
    out = _EMOJI.sub("", text)
    return "\n".join(re.sub(r"[ \t]{2,}", " ", ln).strip() for ln in out.split("\n")).strip()


def calm(text: str) -> str:
    """An older plain-text alert in the house style: no emojis, escaped for HTML, and a
    shouted header ("HEAT DANGER — ETH") turned into "<b>ETH</b> · Heat danger"."""
    lines = strip_emoji(text).split("\n")
    first = lines[0] if lines else ""
    m = _SHOUT.match(first)
    out = [esc(ln) for ln in lines]
    if m:
        words = [w if w in _ACRONYM else w.lower() for w in m.group("head").split()]
        head = " ".join(words)
        out[0] = f"{coin_b(m.group('coin'))} · {esc(head[:1].upper() + head[1:])}"
    return "\n".join(out)


# ------------------------------------------------------------------ recipients and delivery
def default_chats() -> List[int]:
    """TELEGRAM_ALLOWED_CHATS plus every chat registered with /watch."""
    ids = set()
    try:
        from telegram_bot import ALLOWED_CHAT_IDS
        ids |= {int(c) for c in ALLOWED_CHAT_IDS}
    except Exception:
        pass
    try:
        from position_monitor import PositionMonitor
        ids |= {int(w.chat_id) for w in PositionMonitor.get().watchers}
    except Exception:
        pass
    return sorted(ids)


def bot_app():
    try:
        from telegram_bot import get_telegram_bot
        bot = get_telegram_bot()
    except Exception:
        return None
    return bot.app if getattr(bot, "app", None) and getattr(bot, "_running", False) else None


async def _deliver(chats: Iterable[int], text: str) -> int:
    """Send one HTML message to each chat; returns how many went out."""
    app = bot_app()
    if app is None:
        return 0
    if len(text) > 4000:
        text = text[:4000]
    sent = 0
    for cid in chats:
        try:
            await app.bot.send_message(chat_id=int(cid), text=text, parse_mode="HTML",
                                       disable_web_page_preview=True)
            sent += 1
        except Exception as exc:
            logger.debug("telegram: send to %s failed: %s", cid, exc)
    return sent


# ------------------------------------------------------------------ the gate
def _prune(st: dict, now: float) -> None:
    st["sent"] = {k: v for k, v in st["sent"].items() if now - v[0] < v[1]} if st["sent"] else {}


def gate(st: dict, cat: str, key: str, text: str, line: Optional[str], now: float,
         urgent: bool = False, window: float = DEDUPE_S) -> str:
    """The delivery rules on one record (the owner's, or an account's in user_alerts):
    "off", "dup", "held" (recorded for the brief) or "send". Marks the key as sent."""
    s = st["settings"]
    if not bool(s["on"].get(cat, False)):
        return "off"
    full = f"{cat}:{key}"
    _prune(st, now)
    if full in st["sent"]:
        return "dup"
    st["sent"][full] = [now, window]
    per = period_start(now)
    if st.get("period") != per:
        st["period"], st["count"] = per, 0
    hold = paused_at(s, now) or (not urgent and (in_quiet(now, s.get("quiet")) or st["count"] >= int(s.get("cap") or 0)))
    if hold:
        st["held"].append({"ts": now, "cat": cat, "line": line or text.split("\n")[0]})
        st["held"] = st["held"][-HELD_MAX:]
        return "held"
    return "send"


async def submit(cat: str, key: str, text: str, line: Optional[str] = None, *,
                 chats: Optional[Iterable[int]] = None, urgent: bool = False,
                 window: float = DEDUPE_S, now: Optional[float] = None) -> str:
    """Send ``text`` (HTML) now, hold it for the brief, or drop it.

    ``line`` is the one-line form listed in the brief when held (defaults to the first line).
    Returns "off" (category off), "dup" (same key within the window), "held" (quiet hours,
    pause or cap reached), "sent" or "nobody" (no chat or no bot)."""
    st = _load()
    now = now or time.time()
    verdict = gate(st, cat, key, text, line, now, urgent, window)
    if verdict in ("off", "dup"):
        return verdict
    if verdict == "held":
        save()
        return "held"
    targets = list(chats) if chats is not None else default_chats()
    n = await _deliver(targets, text) if targets else 0
    if n:
        st["count"] += 1
    save()
    return "sent" if n else "nobody"


def submit_nowait(*args, **kwargs) -> None:
    """submit from synchronous code running inside the event loop (best effort)."""
    try:
        asyncio.get_running_loop().create_task(submit(*args, **kwargs))
    except RuntimeError:
        logger.debug("telegram: no running loop, alert dropped")


def take_held() -> List[dict]:
    st = _load()
    out, st["held"] = list(st["held"]), []
    save()
    return out


def status_line(now: Optional[float] = None) -> str:
    """One line for /alerts: the count since the last brief, held alerts, pause."""
    st = _load()
    now = now or time.time()
    s = st["settings"]
    count = st["count"] if st.get("period") == period_start(now) else 0
    parts = [f"{count} of {s['cap']} sent since the brief", f"{len(st['held'])} held for the brief"]
    if paused(now):
        parts.append(f"paused until {local(s['paused_until']).strftime('%a %H:%M')}")
    return " · ".join(parts)


# ------------------------------------------------------------------ /alerts view (pure; the bot wraps it)
def alerts_view(page: str = "main", now: Optional[float] = None) -> Tuple[str, List[List[Tuple[str, str]]]]:
    """Text and inline keyboard rows [(label, callback data)] for /alerts."""
    s = settings()
    now = now or time.time()
    mark = lambda on: "on" if on else "off"
    q = s.get("quiet")
    quiet = f"{q[0]}-{q[1]}" if q else "off"
    lines = ["<b>Alerts</b>",
             f"Brief {BRIEF_TIME} · quiet hours {quiet} · at most {s['cap']} a day",
             esc(status_line(now))]
    rows: List[List[Tuple[str, str]]] = []
    cats = [c for c, _, on in CATEGORIES if on] if page == "main" else [c for c, _, on in CATEGORIES if not on]
    for c in cats:
        rows.append([(f"{LABEL[c]}: {mark(enabled(c))}", f"al:t:{c}")])
    if page == "main":
        rows.append([(f"Daily brief: {mark(s['brief'])}", "al:t:brief")])
        rows.append([(f"Quiet hours: {quiet}", "al:q"),
                     ("Resume" if paused(now) else "Pause 24h", "al:r" if paused(now) else "al:p")])
        rows.append([("More", "al:more"), ("Send brief now", "al:b")])
    else:
        rows.append([("Back", "al:main")])
    return "\n".join(lines), rows


def apply_callback(data: str, now: Optional[float] = None) -> str:
    """Apply an /alerts button; returns the page to show next ("main", "more" or "brief")."""
    parts = data.split(":")
    if len(parts) < 2 or parts[0] != "al":
        return "main"
    act = parts[1]
    if act == "t" and len(parts) == 3:
        toggle(parts[2])
        return "main" if parts[2] in CORE or parts[2] == "brief" else "more"
    if act == "q":
        cycle_quiet()
    elif act == "p":
        pause(24, now)
    elif act == "r":
        resume()
    elif act == "more":
        return "more"
    elif act == "b":
        return "brief"
    return "main"


# ------------------------------------------------------------------ watched coins (the Radar's Watch list)
EXITS = {"TRIM", "TRIM_HARD", "NO_LONG", "RISK_OFF"}
SIGNAL_WORD = {"STRONG_LONG": "Strong long", "LIGHT_LONG": "Light long", "ACCUMULATE": "Accumulate",
               "REVIVAL_SEED": "Revival", "REVIVAL_SEED_CONFIRMED": "Revival", "LIGHT_SHORT": "Light short",
               "STRONG_SHORT": "Strong short", "TRIM": "Trim", "TRIM_HARD": "Trim hard", "NO_LONG": "No long",
               "RISK_OFF": "Risk off", "WAIT": "Wait"}
REGIME_WORD = {"MARKUP": "Uptrend", "BLOWOFF": "Overheated", "REACC": "Re-accumulating", "MARKDOWN": "Downtrend",
               "CAP": "Capitulation", "ACCUM": "Accumulation", "ABSORBING": "Absorbing", "FLAT": "Flat"}


def signal_word(s: Optional[str]) -> str:
    return SIGNAL_WORD.get(s or "WAIT", str(s or "wait").replace("_", " ").capitalize())


def entry_in(item: dict) -> Optional[bool]:
    """Whether the coin's price is in its entry zone, from the setup map's optional ``entry``
    field (read defensively: a bool, a dict with a flag, a state or lo/hi, or a [lo, hi] pair).
    None when the map carries no entry zone."""
    e = item.get("entry")
    if e is None:
        return None
    if isinstance(e, bool):
        return e
    price = item.get("price")
    if isinstance(e, dict):
        for k in ("in_zone", "inside", "in", "active"):
            if isinstance(e.get(k), bool):
                return e[k]
        st = e.get("state") or e.get("zone") or e.get("status")
        if isinstance(st, str):
            return st.lower() in ("in", "inside", "in_zone", "entry", "active")
        lo, hi = e.get("lo", e.get("low")), e.get("hi", e.get("high"))
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and price:
            return lo <= price <= hi
        return None
    if isinstance(e, (list, tuple)) and len(e) == 2 and price:
        try:
            return float(e[0]) <= price <= float(e[1])
        except (TypeError, ValueError):
            return None
    return None


def watch_state(item: dict) -> dict:
    return {"zone": item.get("zone"), "signal": item.get("signal"), "regime": item.get("regime"),
            "crowd": item.get("crowd"), "entry": entry_in(item)}


def watch_events(prev: Optional[dict], cur: dict) -> List[Tuple[str, str, str]]:
    """(category, kind, words) for what changed between two readings of a watched coin.
    Instant: entered Early setups, entered the entry zone, exit signal. The rest goes to
    ``watched_more`` (off by default). First reading: nothing."""
    if not prev:
        return []
    out = []
    if cur["zone"] == "watch" and prev.get("zone") != "watch":
        out.append(("watched", "early", "entered Early setups"))
    if cur.get("entry") is True and prev.get("entry") is not True:
        out.append(("watched", "entry", "entered the entry zone"))
    if cur.get("signal") in EXITS and cur.get("signal") != prev.get("signal"):
        out.append(("watched", "exit", f"exit signal {signal_word(cur['signal'])}"))
    if prev.get("zone") == "watch" and cur["zone"] != "watch":
        out.append(("watched_more", "left", "left Early setups"))
    if cur.get("regime") == "MARKUP" and prev.get("regime") != "MARKUP":
        out.append(("watched_more", "uptrend", "Uptrend confirmed"))
    if cur.get("crowd") == "crowded" and prev.get("crowd") != "crowded":
        out.append(("watched_more", "crowded", "turned crowded"))
    return out


def watched_text(coin: str, words: str, item: dict) -> str:
    t = item.get("traders") or {}
    return (f"{coin_b(coin)} · {esc(words)}\n"
            f"Stretch {item.get('zscore') or 0:.1f} · {t.get('pl', 0)} profitable traders long, {t.get('ps', 0)} short"
            f" · {esc(signal_word(item.get('signal')))}")


async def watch_pass(watched: Dict[str, dict], maps: Dict[str, dict], last: Dict[str, dict],
                     send: Callable[..., Awaitable[str]], now: Optional[float] = None) -> Tuple[List[str], bool]:
    """Compare each watched coin with its last reading (``last``, updated in place) and send
    what changed through ``send(cat, key, text, line, now=)``. Returns (statuses, changed)."""
    out, dirty = [], False
    for coin, w in watched.items():
        m = maps.get(w.get("tf", "1d"))
        item = next((c for c in (m or {}).get("coins", []) if c.get("coin") == coin), None)
        if item is None:
            continue
        cur = watch_state(item)
        for cat, kind, words in watch_events(last.get(coin), cur):
            out.append(await send(cat, f"{kind}:{coin}", watched_text(coin, words, item),
                                  f"{coin_b(coin)} {esc(words)}", now=now))
        if cur != last.get(coin):
            last[coin] = cur
            dirty = True
    for coin in [c for c in last if c not in watched]:
        last.pop(coin)
        dirty = True
    return out, dirty


async def check_watched(maps: Dict[str, dict], now: Optional[float] = None) -> List[str]:
    """Compare each watched coin with its last reading and submit what changed. Returns the
    statuses (for logs and tests)."""
    import setup_map
    st = _load()
    out, dirty = await watch_pass(setup_map.watched(), maps, st["watch"], submit, now)
    if dirty:
        save()
    return out
