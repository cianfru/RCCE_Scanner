"""
The daily Telegram brief: one message a day at TELEGRAM_BRIEF_TIME (08:00) in TELEGRAM_TZ
(Europe/Rome), a small picture of the Radar with a short caption:

  market state (consensus, share of coins in Uptrend, day of the risk-on run)
  Fear & Greed
  up to 3 Early setups (coin · profitable traders long · their dollars · band or entry zone)
  open positions against the scanner, when a wallet is registered with /watch
  watched coins that changed since the last brief
  alerts held back by quiet hours, a pause or the daily cap
  a link to the Radar (REFLEX_APP_URL) and the footer "Reflex · 08:00"

``compose`` is pure (tests build it from fixtures); ``gather`` reads the server's memory;
``send_brief`` draws the picture once and sends it to every chat.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Awaitable, Callable, Dict, List, Optional

import tg_alerts as ta
from tg_alerts import coin_b, esc, usd

logger = logging.getLogger(__name__)

APP_URL = os.environ.get("REFLEX_APP_URL", "https://reflexsignal.xyz").strip().rstrip("/")
GRACE_S = 3 * 3600          # a brief missed by a restart still goes out within 3 hours
CAPTION_MAX = 1024          # Telegram's limit for a photo caption

LONGS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"}
SHORTS = {"LIGHT_SHORT", "STRONG_SHORT"}
CONSENSUS_WORD = {"RISK-ON": "Risk-on", "RISK-OFF": "Risk-off", "MIXED": "Mixed"}

# The map is built in main.py (cached two minutes); main registers the builder here.
_map_provider: Optional[Callable[[str], Awaitable[dict]]] = None


def set_map_provider(fn: Callable[[str], Awaitable[dict]]) -> None:
    global _map_provider
    _map_provider = fn


# ------------------------------------------------------------------ early setups (as the app's picks)
def _trail(c: dict) -> Optional[List[tuple]]:
    t = c.get("trail") or {}
    zs, ns = t.get("z") or [], list(t.get("n") or [])
    if not zs or len(ns) != len(zs):
        return None
    tr = c.get("traders") or {}
    now_n = (tr.get("pl") or 0) - (tr.get("ps") or 0)
    for k in range(len(ns)):
        if ns[k] is None:
            ns[k] = ns[k - 1] if k > 0 else None
    for k in range(len(ns) - 1, -1, -1):
        if ns[k] is None:
            ns[k] = ns[k + 1] if k < len(ns) - 1 else now_n
    return list(zip(zs, ns))


def _in_box(box: dict, z, n) -> bool:
    return z is not None and box["z"][0] <= z <= box["z"][1] and box["n"][0] <= n <= box["n"][1]


def early_setups(smap: dict, limit: int = 3) -> List[dict]:
    """Coins in the Early setups box ranked as the app's shortlist (utils/setupMap.js picks):
    the engine's priority, plus came in within the trail, more traders arriving, just fired,
    a regime change one candle away and an early crowd; minus crowded or against. Each item
    gets ``_new`` when it came into the box within the trail."""
    box = smap.get("box") or {"z": [-0.5, 1.5], "n": [1, 8]}
    out = []
    for c in smap.get("coins") or []:
        if c.get("zone") != "watch":
            continue
        s = c.get("priority") or 0
        p = _trail(c)
        new = False
        if p and len(p) >= 2:
            new = not _in_box(box, *p[0])
            if new:
                s += 10
            dn = p[-1][1] - p[0][1]
            if dn > 0:
                s += min(15, 5 * dn)
        if c.get("stage") == "fresh":
            s += 8
        tr = c.get("transition")
        if c.get("stage") == "forming" and tr and tr.get("need") is not None \
                and tr["need"] - min(tr.get("seen") or 0, tr["need"]) <= 1:
            s += 8
        s += {"early": 10, "crowded": -10, "against": -20}.get(c.get("crowd"), 0)
        out.append((s, c["coin"], dict(c, _new=new)))
    out.sort(key=lambda x: (-x[0], x[1]))
    return [c for _, _, c in out[:limit]]


def band_note(item: dict) -> str:
    if ta.entry_in(item):
        return "in entry zone"
    b = item.get("band") or {}
    st = b.get("state")
    if st == "above" and b.get("d") is not None:
        return f"{100 * b['d']:.0f}% above band"
    return {"inside": "in band", "under_now": "under band now", "closed_under": "closed under band"}.get(st, "")


def setup_line(c: dict) -> str:
    t = c.get("traders") or {}
    parts = [coin_b(c["coin"])]
    if c.get("_new"):
        parts.append("new")
    parts.append(f"{t.get('pl', 0)} traders")
    lu = (c.get("money") or {}).get("long_usd") or 0
    if lu:
        parts.append(usd(lu))
    note = band_note(c)
    if note:
        parts.append(esc(note))
    return " · ".join(parts)


# ------------------------------------------------------------------ positions against the scanner
def stance(side: str, signal: Optional[str]) -> str:
    """agree | against | none for an open position and the scanner's signal on the coin."""
    long_side = str(side).upper() == "LONG"
    if signal in LONGS:
        return "agree" if long_side else "against"
    if signal in ta.EXITS or signal in SHORTS:
        return "against" if long_side else "agree"
    return "none"


def positions_line(positions: List[dict], results: Dict[str, dict]) -> str:
    if not positions:
        return "Positions: none open"
    agree, against = 0, []
    for p in positions:
        s = stance(p.get("side", ""), (results.get(p.get("symbol")) or {}).get("signal"))
        if s == "agree":
            agree += 1
        elif s == "against":
            against.append(p.get("coin", "?"))
    parts = [f"Positions: {len(positions)} open", f"{agree} agree"]
    if against:
        names = ", ".join(coin_b(c) for c in against[:3]) + (f" +{len(against) - 3}" if len(against) > 3 else "")
        parts.append(f"{len(against)} against: {names}")
    return " · ".join(parts)


# ------------------------------------------------------------------ watched coins since the last brief
def watch_changes(prev: Dict[str, dict], cur: Dict[str, dict]) -> List[str]:
    out = []
    for coin in sorted(cur):
        for _, _, words in ta.watch_events(prev.get(coin), cur[coin]):
            out.append(f"{coin_b(coin)} {esc(words)}")
    return out


def _joined(items: List[str], n: int) -> str:
    return " · ".join(items[:n]) + (f" · +{len(items) - n} more" if len(items) > n else "")


# ------------------------------------------------------------------ the caption
def compose(ctx: dict) -> List[str]:
    """Caption lines (HTML) from gathered data. Keys (all optional): consensus, uptrend (share),
    cycle {type, day}, fear_greed (value, label), smap, positions (None: no wallet), results
    (symbol -> 1D row), watched (count), changes (lines), held (held alerts), app_url, now."""
    now = ctx.get("now") or time.time()
    lines: List[str] = []
    head = []
    cons = ctx.get("consensus")
    if cons:
        head.append(CONSENSUS_WORD.get(cons, str(cons).capitalize()))
    if ctx.get("uptrend") is not None:
        head.append(f"{round(100 * ctx['uptrend'])}% in Uptrend")
    cyc = ctx.get("cycle") or {}
    if cyc.get("day"):
        head.append(f"risk-on run day {cyc['day']}" if cyc.get("type") == "on" else f"risk-off day {cyc['day']}")
    if head:
        lines.append(" · ".join(head))
    fg = ctx.get("fear_greed")
    if fg and fg[0] is not None:
        lines.append(esc(f"Fear & Greed {fg[0]}" + (f" · {fg[1]}" if fg[1] else "")))
    picks = early_setups(ctx.get("smap") or {}) if ctx.get("smap") else []
    lines.append("")
    if picks:
        lines.append("<b>Early setups</b>")
        lines.extend(setup_line(c) for c in picks)
    else:
        lines.append("Early setups: none")
    tail = []
    if ctx.get("positions") is not None:
        tail.append(positions_line(ctx["positions"], ctx.get("results") or {}))
    if ctx.get("watched"):
        ch = ctx.get("changes") or []
        tail.append("Watched: " + (_joined(ch, 3) if ch else "no changes"))
    held = ctx.get("held") or []
    if held:
        tail.append("Held: " + _joined([h["line"] for h in held], 2))
    if tail:
        lines.append("")
        lines.extend(tail)
    lines.append("")
    url = ctx.get("app_url")
    if url:
        lines.append(f'<a href="{esc(url)}/radar?tf=1d">Open Radar</a>')
    lines.append(f"<i>Reflex · {ta.hm(now)}</i>")
    return lines


def picks_of(smap: Optional[dict]) -> List[str]:
    return [c["coin"] for c in early_setups(smap or {})]


# ------------------------------------------------------------------ gathering (server memory)
async def _positions(address: Optional[str]) -> Optional[List[dict]]:
    if not address:
        return None
    try:
        from hyperliquid_data import fetch_clearinghouse_state, parse_open_positions
        state = await fetch_clearinghouse_state(address)
        return parse_open_positions(state) if state is not None else None
    except Exception as exc:
        logger.debug("brief: positions not read: %s", exc)
        return None


def wallet_for(chat_id: int) -> Optional[str]:
    try:
        from position_monitor import PositionMonitor
        w = PositionMonitor.get().get_watcher(int(chat_id))
        if w:
            return w.address
    except Exception:
        pass
    return os.environ.get("TELEGRAM_WALLET", "").strip().lower() or None


async def gather(now: Optional[float] = None) -> dict:
    """Everything the caption needs except positions and held alerts (per chat, at send)."""
    now = now or time.time()
    ctx: dict = {"now": now, "app_url": APP_URL}
    try:
        from scanner import cache
        ctx["consensus"] = (cache.consensus.get("1d") or {}).get("consensus")
        s = cache.sentiment or {}
        if s.get("fear_greed_value") is not None:
            ctx["fear_greed"] = (s.get("fear_greed_value"), s.get("fear_greed_label"))
        rows = cache.get_results("1d") or cache.get_results("4h") or []
        ctx["results"] = {r.get("symbol"): r for r in rows if isinstance(r, dict)}
        if rows:
            up = sum(1 for r in rows if isinstance(r, dict) and r.get("regime") in ("MARKUP", "BLOWOFF"))
            ctx["uptrend"] = up / len(rows)
    except Exception as exc:
        logger.debug("brief: scanner cache not read: %s", exc)
    try:
        import market_history
        v = await asyncio.to_thread(market_history.view)
        t = v.get("today") or {}
        if t.get("uptrend") is not None:
            ctx["uptrend"] = (t.get("uptrend") or 0) + (t.get("overheated") or 0)
        ctx["cycle"] = v.get("cycle") or {}
    except Exception as exc:
        logger.debug("brief: market history not read: %s", exc)
    if _map_provider is not None:
        try:
            ctx["smap"] = await _map_provider("1d")
        except Exception as exc:
            logger.warning("brief: no setup map: %s", exc)
    try:
        import setup_map
        watched = setup_map.watched()
        ctx["watched"] = len(watched)
        items = {c["coin"]: c for c in (ctx.get("smap") or {}).get("coins", [])}
        ctx["watch_now"] = {c: ta.watch_state(items[c]) for c in watched if c in items}
        ctx["changes"] = watch_changes(ta.state().get("brief_watch") or {}, ctx["watch_now"])
    except Exception as exc:
        logger.debug("brief: watch list not read: %s", exc)
    return ctx


# ------------------------------------------------------------------ sending
async def _send(chat_id: int, caption: str, png: Optional[bytes]) -> bool:
    app = ta.bot_app()
    if app is None:
        return False
    try:
        if png and len(caption) <= CAPTION_MAX:
            await app.bot.send_photo(chat_id=int(chat_id), photo=png, caption=caption, parse_mode="HTML")
        else:
            if png:
                await app.bot.send_photo(chat_id=int(chat_id), photo=png)
            await app.bot.send_message(chat_id=int(chat_id), text=caption[:4000], parse_mode="HTML",
                                       disable_web_page_preview=True)
        return True
    except Exception as exc:
        logger.warning("brief: send to %s failed: %s", chat_id, exc)
        return False


def render_image(smap: Optional[dict], now: float) -> Optional[bytes]:
    if not smap:
        return None
    import radar_image
    title = "Radar 1D · " + ta.local(now).strftime("%a %d %b")
    return radar_image.render(smap, picks_of(smap), title)


async def send_brief(chats: Optional[List[int]] = None, now: Optional[float] = None,
                     scheduled: bool = False) -> int:
    """Build and send the brief; returns the number of chats reached. A scheduled brief also
    records its day and the watched coins' readings (the next brief's "since yesterday")."""
    now = now or time.time()
    chats = list(chats) if chats is not None else ta.default_chats()
    if not chats:
        return 0
    ctx = await gather(now)
    held = ta.take_held()
    png = await asyncio.to_thread(render_image, ctx.get("smap"), now)
    sent = 0
    for cid in chats:
        c = dict(ctx, held=held, positions=await _positions(wallet_for(cid)))
        if await _send(cid, "\n".join(compose(c)), png):
            sent += 1
    st = ta.state()
    if scheduled:
        st["last_brief"] = slot_of(now)
        if ctx.get("watch_now") is not None:
            st["brief_watch"] = ctx["watch_now"]
    ta.save()
    logger.info("Telegram brief sent to %d chat(s)%s", sent, "" if png else " (text only)")
    return sent


def slot_of(now: float) -> str:
    """The date of the brief slot that ``now`` belongs to (the last brief time at or before it)."""
    return ta.local(ta.period_start(now)).date().isoformat()


def brief_due(now: float, last_brief: str, grace: float = GRACE_S) -> bool:
    """The last brief time has passed, its brief has not gone out, and it is within the grace."""
    start = ta.period_start(now)
    return now - start < grace and last_brief != slot_of(now)


async def run_scheduler() -> None:
    """Send the brief at the brief time each day; wakes at least every 10 minutes."""
    await asyncio.sleep(90)
    while True:
        now = time.time()
        try:
            if ta.settings().get("brief", True) and brief_due(now, ta.state().get("last_brief", "")):
                await send_brief(now=now, scheduled=True)
        except Exception as exc:
            logger.warning("brief: %s", exc)
        wait = ta.next_brief_at(time.time()).timestamp() - time.time()
        await asyncio.sleep(max(5.0, min(600.0, wait + 1)))
