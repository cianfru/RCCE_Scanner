"""
HTTP endpoints for wallet sign-in and per-account lists (main.py includes ``router``).

  POST   /api/auth/wallet/nonce     {address, domain, chain_id?} -> {message, expires}
  POST   /api/auth/wallet/verify    {message, signature} -> {token, address, tier, expires}
  POST   /api/auth/wallet/logout
  GET    /api/me                    flags, the signed-in address, its tier and Telegram link
  GET    /api/me/follows            same shape as /api/hyperlens/followed
  POST   /api/me/follows            {address, note?}
  DELETE /api/me/follows/{address}
  GET    /api/me/watch              same shape as /api/setup-map/watch
  POST   /api/me/watch              {coin, tf}
  DELETE /api/me/watch/{coin}
  POST   /api/me/telegram/link      a one-time code for /start <code>
  PUT    /api/me/telegram           {quiet?: [from, to] | null, brief?: bool}
  DELETE /api/me/telegram

Everything but /api/me answers 404 while REFLEX_ACCOUNTS is off. A missing session and a
feature for holders both answer 403 (401 is the access-code login's). The owner's account
reads and writes the existing single-owner lists.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

import accounts
import tiers
import wallet_auth as wa

router = APIRouter()

SIGN_IN = "Sign in with a wallet"
HOLDER_ONLY = "holder"


# ------------------------------------------------------------------ request helpers
def _on() -> None:
    if not accounts.enabled():
        raise HTTPException(status_code=404, detail="Not found")


def user_of(request: Request) -> Optional[str]:
    return wa.request_address(request.headers)


def _signed_in(request: Request) -> str:
    _on()
    user = user_of(request)
    if not user:
        raise HTTPException(status_code=403, detail=SIGN_IN)
    return user


async def _holder(request: Request) -> str:
    user = _signed_in(request)
    if not await tiers.allows(user):
        raise HTTPException(status_code=403, detail=HOLDER_ONLY)
    return user


def admin_key_ok(request: Request) -> bool:
    import hmac
    key = os.environ.get("REFLEX_ADMIN_KEY", "")
    given = request.headers.get("x-admin-key", "")
    return bool(key) and bool(given) and hmac.compare_digest(given.encode(), key.encode())


async def request_is_holder(request: Request) -> bool:
    """For gating existing endpoints: tiers off, the admin key, or a holder's session."""
    if not tiers.enforced() or admin_key_ok(request):
        return True
    user = user_of(request)
    return bool(user) and await tiers.tier_for(user) == tiers.HOLDER


async def require_holder(request: Request) -> None:
    """Raise 403 for a feature for holders while tiers are on."""
    if not await request_is_holder(request):
        raise HTTPException(status_code=403, detail=HOLDER_ONLY)


def require_owner_when_public(request: Request) -> None:
    """The owner's single-owner lists while tiers are on: the admin key or the owner's session."""
    if not tiers.enforced() or admin_key_ok(request) or accounts.is_owner(user_of(request)):
        return
    raise HTTPException(status_code=403, detail=HOLDER_ONLY)


async def setup_map_for(request: Request, tf: str, build) -> dict:
    """/api/setup-map: live for holders (and for everyone while tiers are off), otherwise the
    map as it was at least the free delay ago."""
    import radar_delay
    body = await build(tf)
    if not tiers.enforced():
        return body
    delay = tiers.radar_delay_s()
    radar_delay.note(tf, body, delay)
    if await request_is_holder(request):
        return body
    return radar_delay.get(tf, delay)


# ------------------------------------------------------------------ sign-in
_REFUSED = {"format": "The sign-in message is not valid", "domain": "The sign-in message is for another site",
            "expired": "The sign-in message has expired", "nonce": "The sign-in message was already used",
            "signature": "The signature does not match the address"}


@router.post("/api/auth/wallet/nonce")
async def wallet_nonce(body: dict):
    _on()
    try:
        chain = int((body or {}).get("chain_id") or 1)
        return wa.issue(str((body or {}).get("address", "")), str((body or {}).get("domain", "")), chain)
    except (wa.AuthError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=_REFUSED.get(getattr(exc, "reason", "format")))


@router.post("/api/auth/wallet/verify")
async def wallet_verify(body: dict):
    _on()
    try:
        address = wa.verify(str((body or {}).get("message", "")), str((body or {}).get("signature", "")))
    except wa.AuthError as exc:
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=400, detail=_REFUSED.get(exc.reason, "Sign-in refused"))
    token, expires = wa.start_session(address)
    return {"token": token, "address": address, "expires": expires, "tier": await tiers.tier_for(address),
            "owner": accounts.is_owner(address)}


@router.post("/api/auth/wallet/logout")
async def wallet_logout(request: Request):
    _on()
    return {"ok": wa.end_session(request.headers.get(wa.HEADER))}


# ------------------------------------------------------------------ the account
def _telegram_status(user: Optional[str]) -> str:
    import followed_traders as ft
    base = ft.telegram_status() if accounts.is_owner(user) else _bot_state()
    if base == "off" or accounts.is_owner(user):
        return base
    return "ready" if user and accounts.tg_chat(user) is not None else "no-chat"


def _bot_state() -> str:
    import tg_alerts as ta
    return "off" if ta.bot_app() is None else "ready"


def _bot_name() -> Optional[str]:
    name = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if name:
        return name
    try:
        import tg_alerts as ta
        app = ta.bot_app()
        return app.bot.username if app is not None else None
    except Exception:
        return None


@router.get("/api/me")
async def me(request: Request):
    if not accounts.enabled():
        return {"accounts": False, "tiers": False}
    user = user_of(request)
    out = {"accounts": True, "tiers": tiers.enforced(), "address": user, "owner": accounts.is_owner(user),
           "tier": await tiers.tier_for(user), "features": {},
           "limits": {"follows": accounts.follow_cap(), "watch": accounts.watch_cap()},
           "radar_delay_min": round(tiers.radar_delay_s() / 60)}
    allowed = await tiers.allows(user) if user else not tiers.enforced()
    out["features"] = {f: allowed for f in tiers.HOLDER_FEATURES}
    if user:
        import user_alerts as ua
        s = ua.state(user)["settings"] if not accounts.is_owner(user) else None
        out["telegram"] = {"status": _telegram_status(user), "quiet": s["quiet"] if s else None,
                           "brief": s["brief"] if s else None}
    return out


# ------------------------------------------------------------------ follows
def _follow_rows(items: dict, events) -> list:
    from hl_intelligence import _wallet_cohorts, wallet_positions
    rows = []
    for addr, meta in sorted(items.items(), key=lambda kv: -kv[1]["added"]):
        cohorts = sorted(_wallet_cohorts.get(addr, set()))
        rows.append({"address": addr, **meta, "cohorts": cohorts, "tracked": bool(cohorts),
                     **wallet_positions(addr), "events": [e for e in events if e["address"] == addr][:10]})
    return rows


@router.get("/api/me/follows")
async def my_follows(request: Request):
    user = await _holder(request)
    if accounts.is_owner(user):
        import followed_traders as ft
        items = ft.items()
        return {"traders": _follow_rows(items, ft.events(None, 300)), "events": ft.events(None, 50),
                "telegram": _telegram_status(user), "cap": None}
    items = accounts.follows(user)
    events = accounts.events_for(items, 200)
    return {"traders": _follow_rows(items, events), "events": events[:50], "telegram": _telegram_status(user),
            "cap": accounts.follow_cap()}


@router.post("/api/me/follows")
async def my_follow(request: Request, body: dict):
    user = await _holder(request)
    address = str((body or {}).get("address", "")).strip().lower()
    if not accounts.valid_address(address):
        raise HTTPException(status_code=400, detail="address must be a 0x wallet address")
    note = str((body or {}).get("note", ""))
    if accounts.is_owner(user):
        import followed_traders as ft
        return {"added": ft.add(address, note), "address": address}
    res = accounts.follow(user, address, note)
    if res == "cap":
        raise HTTPException(status_code=400, detail=f"at most {accounts.follow_cap()} traders can be followed")
    return {"added": res == "added", "address": address}


@router.delete("/api/me/follows/{address}")
async def my_unfollow(request: Request, address: str):
    user = await _holder(request)
    if accounts.is_owner(user):
        import followed_traders as ft
        return {"removed": ft.remove(address), "address": address.lower()}
    return {"removed": accounts.unfollow(user, address), "address": address.lower()}


# ------------------------------------------------------------------ watch list
@router.get("/api/me/watch")
async def my_watch(request: Request):
    user = await _holder(request)
    if accounts.is_owner(user):
        import setup_map
        watched = setup_map.watched()
    else:
        watched = accounts.watch_list(user)
    return {"coins": [{"coin": c, "tf": w.get("tf"), "added": w.get("added")} for c, w in watched.items()],
            "telegram": _telegram_status(user)}


@router.post("/api/me/watch")
async def my_watch_add(request: Request, body: dict):
    user = await _holder(request)
    from hl_intelligence import _normalize_coin
    coin = _normalize_coin(str((body or {}).get("coin", "")).strip().upper())
    if not coin or len(coin) > 20:
        raise HTTPException(status_code=400, detail="coin is required")
    tf = str((body or {}).get("tf", "1d"))
    if accounts.is_owner(user):
        import setup_map
        ok = setup_map.watch(coin, tf)
    else:
        ok = accounts.watch(user, coin, tf) != "cap"
    if not ok:
        raise HTTPException(status_code=400, detail=f"at most {accounts.watch_cap()} coins can be watched")
    return {"watching": coin}


@router.delete("/api/me/watch/{coin}")
async def my_watch_remove(request: Request, coin: str):
    user = await _holder(request)
    from hl_intelligence import _normalize_coin
    c = _normalize_coin(coin.upper())
    if accounts.is_owner(user):
        import setup_map
        setup_map.unwatch(c)
    else:
        accounts.unwatch(user, c)
    return {"removed": coin.upper()}


# ------------------------------------------------------------------ Telegram
@router.post("/api/me/telegram/link")
async def my_telegram_link(request: Request):
    user = await _holder(request)
    code, expires = accounts.tg_code(user)
    bot = _bot_name()
    return {"code": code, "expires": expires, "bot": bot,
            "url": f"https://t.me/{bot}?start={code}" if bot else None}


@router.put("/api/me/telegram")
async def my_telegram_prefs(request: Request, body: dict):
    user = await _holder(request)
    import user_alerts as ua
    body = body or {}
    try:
        s = ua.set_prefs(user, quiet=body["quiet"] if "quiet" in body else "keep",
                         brief=body.get("brief") if isinstance(body.get("brief"), bool) else None)
    except (ValueError, TypeError, IndexError):
        raise HTTPException(status_code=400, detail="quiet hours as [\"23:00\", \"07:30\"] or null")
    return {"quiet": s["quiet"], "brief": s["brief"]}


@router.delete("/api/me/telegram")
async def my_telegram_unlink(request: Request):
    user = _signed_in(request)
    return {"unlinked": accounts.tg_unlink(user=user)}


def start_background(map_provider) -> None:
    """The per-account watched-coins pass (main.py lifespan, accounts on)."""
    if accounts.enabled():
        import user_alerts
        asyncio.create_task(user_alerts.run(map_provider))

