"""
Followed traders: a shortlist of wallets whose position changes are recorded and sent to
Telegram. Not tied to a connected wallet (the app logs in with the access code); adding
or removing needs the admin key like every other change.

A change is found by comparing two readings of the wallet: a new coin/side is an open, a
missing one a close, and a coin quantity up or down by at least a quarter an add or a
cut. Changes under MIN_USD are ignored. Followed wallets are read every 5 minutes while
someone is viewing and every 10 minutes otherwise (hl_intelligence).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

MIN_USD = 10_000
SIZE_STEP = 0.25
MAX_EVENTS = 300

_dir = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not str(_dir) or not _dir.is_dir():
    _dir = Path(__file__).resolve().parent / "data"
PATH = _dir / "followed_traders.json"

_items: Dict[str, dict] = {}
_events: deque = deque(maxlen=MAX_EVENTS)
_loaded = False


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        raw = json.loads(PATH.read_text())
        _items.update(raw.get("traders", {}))
        _events.extend(raw.get("events", [])[-MAX_EVENTS:])
    except (OSError, ValueError):
        pass


def _save() -> None:
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"traders": _items, "events": list(_events)}))
        os.replace(tmp, PATH)
    except OSError as exc:
        logger.warning("followed traders: save failed: %s", exc)


def addresses() -> set:
    _load()
    return set(_items)


def items() -> Dict[str, dict]:
    _load()
    return dict(_items)


def add(address: str, note: str = "") -> bool:
    _load()
    a = address.lower()
    if a in _items:
        return False
    _items[a] = {"added": time.time(), "note": note[:80]}
    _save()
    return True


def remove(address: str) -> bool:
    _load()
    if _items.pop(address.lower(), None) is None:
        return False
    _save()
    return True


def events(address: Optional[str] = None, limit: int = 50) -> List[dict]:
    _load()
    out = [e for e in reversed(_events) if address is None or e["address"] == address.lower()]
    return out[:limit]


def diff(prev: Dict[tuple, dict], cur: Dict[tuple, dict]) -> List[dict]:
    """Position changes between two readings. Keys are (coin, side); values carry size
    (coin quantity), size_usd, entry_px and mark_px."""
    out = []
    for k, p in cur.items():
        q = prev.get(k)
        if q is None:
            if p["size_usd"] >= MIN_USD:
                out.append({"kind": "open", "coin": k[0], "side": k[1], "usd": p["size_usd"], "px": p["entry_px"]})
            continue
        a, b = abs(q.get("size") or 0), abs(p.get("size") or 0)
        if not a:
            continue
        delta_usd = abs(b - a) * (p.get("mark_px") or 0)
        if delta_usd < MIN_USD:
            continue
        if b >= a * (1 + SIZE_STEP):
            out.append({"kind": "add", "coin": k[0], "side": k[1], "usd": p["size_usd"], "delta_usd": delta_usd,
                        "px": p.get("mark_px")})
        elif b <= a * (1 - SIZE_STEP):
            out.append({"kind": "cut", "coin": k[0], "side": k[1], "usd": p["size_usd"], "delta_usd": delta_usd,
                        "px": p.get("mark_px")})
    for k, q in prev.items():
        if k not in cur and q["size_usd"] >= MIN_USD:
            out.append({"kind": "close", "coin": k[0], "side": k[1], "usd": q["size_usd"], "px": q.get("mark_px")})
    return out


def _usd(v: float) -> str:
    return f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}K" if v >= 1e3 else f"${v:.0f}"


def _px(v) -> str:
    return "?" if not v else f"{v:.4g}" if v < 1000 else f"{v:,.0f}"


def message(address: str, cohort: str, changes: List[dict], holdings: Iterable[dict]) -> str:
    verb = {"open": "Opened", "close": "Closed", "add": "Added to", "cut": "Cut"}
    note = _items.get(address, {}).get("note")
    head = f"Followed trader {address[:6]}…{address[-4:]}" + (f" ({note})" if note else "") + f" · {cohort}"
    lines = [head]
    for c in changes:
        size = _usd(c["usd"]) if c["kind"] in ("open", "close") else f"{_usd(c['delta_usd'])}, now {_usd(c['usd'])}"
        lines.append(f"{verb[c['kind']]} {c['side']} {c['coin']} {size} at {_px(c['px'])}")
    hold = sorted(holdings, key=lambda p: -p["size_usd"])
    if hold:
        top = ", ".join(f"{p['side']} {p['coin']} {_usd(p['size_usd'])}" for p in hold[:4])
        lines.append(f"Now holds: {top}" + (f" (+{len(hold) - 4} more)" if len(hold) > 4 else ""))
    else:
        lines.append("Now holds: nothing")
    return "\n".join(lines)


def record(address: str, cohort: str, ts: float, changes: List[dict], holdings: List[dict]) -> None:
    """Store the changes and send them to Telegram (best effort, never raises)."""
    if not changes:
        return
    for c in changes:
        _events.append({"address": address, "cohort": cohort, "ts": ts, **c})
    _save()
    text = message(address, {"profitable": "profitable trader", "large": "large account"}.get(cohort, cohort),
                   changes, holdings)
    try:
        asyncio.get_running_loop().create_task(_send(text))
    except Exception as exc:
        logger.debug("followed traders: telegram not sent: %s", exc)


def chat_ids() -> set:
    """Where alerts go: TELEGRAM_ALLOWED_CHATS, plus every chat registered with /watch."""
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
    return ids


def telegram_status() -> str:
    """"ready", "no-chat" (bot running but nobody to send to) or "off" (no bot)."""
    try:
        from telegram_bot import get_telegram_bot
        bot = get_telegram_bot()
        if not getattr(bot, "app", None) or not getattr(bot, "_running", False):
            return "off"
    except Exception:
        return "off"
    return "ready" if chat_ids() else "no-chat"


async def _send(text: str) -> int:
    from telegram_bot import get_telegram_bot
    bot = get_telegram_bot()
    if not getattr(bot, "app", None) or not getattr(bot, "_running", False):
        return 0
    sent = 0
    for cid in chat_ids():
        try:
            await bot.app.bot.send_message(chat_id=cid, text=text)
            sent += 1
        except Exception as exc:
            logger.debug("followed traders: send to %s failed: %s", cid, exc)
    return sent
