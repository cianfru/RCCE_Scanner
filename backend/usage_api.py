"""
HTTP endpoints for usage capture and the owner's Intel page (main.py includes ``router``).

  POST   /api/usage/beacon          a batch of events from the app (text/plain JSON body:
                                    {t: access token, s?: wallet session, sid, e: [[name, detail], ...]})
  GET    /api/owner/intel           everything the Intel page shows (usage.summary)
  POST   /api/owner/invites         {label, expires_days?} -> the new invite, with its code
  DELETE /api/owner/invites/{id}    revoke

The owner is the admin key, or the owner's wallet session while accounts are on. The
beacon answers 202 whether or not it kept anything, so the app never retries it.
"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import access
import invites
import usage
import usage_geo
from ratelimit import SlidingWindowLimiter

router = APIRouter()

# A visible tab sends one batch a minute, plus one when it is hidden.
_limiter = SlidingWindowLimiter(max_requests=20, window_seconds=60)
PRIVATE = {"Cache-Control": "no-store"}


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _accepted(ok: bool, kept: int = 0) -> JSONResponse:
    return JSONResponse({"ok": ok, "kept": kept}, status_code=202)


def _wallet(session) -> tuple:
    """(wallet signed in, Telegram linked or None) for a wallet session token."""
    import accounts
    if not accounts.enabled() or not isinstance(session, str) or not session:
        return None, None
    import wallet_auth as wa
    address = wa.session_address(session)
    if not address:
        return None, None
    if accounts.is_owner(address):
        return True, None
    return True, accounts.tg_chat(address) is not None


@router.post(access.BEACON_PATH)
async def beacon(request: Request):
    if not usage.enabled():
        return _accepted(False)
    ip = _client_ip(request)
    allowed, retry = _limiter.check(ip)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many requests",
                            headers={"Retry-After": str(int(retry) + 1)})
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > usage.MAX_BODY:
        raise HTTPException(status_code=413, detail="Too large")
    body = await request.body()
    if len(body) > usage.MAX_BODY:
        raise HTTPException(status_code=413, detail="Too large")
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Not an object")

    if access.enforced():
        person = access.token_person(data.get("t") if isinstance(data.get("t"), str) else None)
        if person is None:
            return _accepted(False)
    else:
        person = invites.OPEN
    events = usage.clean_events(data.get("e"))
    sid = str(data.get("sid") or "")
    country, city = usage.geo_of(request.headers, request.query_params)
    device, browser = usage.device_of(request.headers.get("user-agent"))
    wallet, telegram = _wallet(data.get("s"))
    now = time.time()
    kept = usage.ingest(person, sid, events, country=country, city=city, device=device, browser=browser,
                        wallet=wallet, telegram=telegram, now=now)
    if kept and not country:
        usage_geo.schedule(ip, sid, usage.day_of(now))
    return _accepted(True, kept)


# ------------------------------------------------------------------ the owner
def owner_ok(request: Request) -> bool:
    from accounts_api import admin_key_ok
    if admin_key_ok(request):
        return True
    import accounts
    import wallet_auth as wa
    return accounts.enabled() and accounts.is_owner(wa.request_address(request.headers))


def _owner(request: Request) -> None:
    if not owner_ok(request):
        raise HTTPException(status_code=403, detail="Owner only")


@router.get("/api/owner/intel")
async def intel(request: Request):
    _owner(request)
    return JSONResponse(usage.summary(), headers=PRIVATE)


@router.post("/api/owner/invites")
async def invite_create(request: Request, body: dict):
    _owner(request)
    body = body or {}
    expires = None
    days = body.get("expires_days")
    if days not in (None, "", 0):
        try:
            days = float(days)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="expires_days must be a number")
        if not 0 < days <= 3650:
            raise HTTPException(status_code=400, detail="expires_days must be between 1 and 3650")
        expires = time.time() + days * 86400
    try:
        inv = invites.create(str(body.get("label") or ""), expires)
    except ValueError:
        raise HTTPException(status_code=400, detail="A label is required")
    return JSONResponse(inv, headers=PRIVATE)


@router.delete("/api/owner/invites/{inv}")
async def invite_revoke(request: Request, inv: str):
    _owner(request)
    if not invites.ID_RE.match(inv) or invites.get(inv) is None:
        raise HTTPException(status_code=404, detail="No such invite")
    return JSONResponse({"revoked": invites.revoke(inv), "id": inv}, headers=PRIVATE)
