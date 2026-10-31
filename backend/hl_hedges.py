"""
hl_hedges.py
~~~~~~~~~~~~
Tracked wallets' perp shorts that are covered by the same coin held on Hyperliquid spot (or, for
HYPE, staked): a funding trade, not a bet on price. Counting treats them by net exposure:

    a short covered for more than (1 - MIN_UNCOVERED) of its size is not counted at all;
    a partly covered short counts for its uncovered part only;
    longs, and shorts with nothing on spot, count as before.

Only Hyperliquid is visible: a hedge held on another exchange still counts as a short.

Readings: spotClearinghouseState (weight 2) for every tracked wallet holding a short, at most once
per REFRESH_S, and delegatorSummary (weight 20) only when it is short HYPE. Kept in hyperlens.db
(wallet_hedges), so a restart does not briefly count hedged shorts again.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

REFRESH_S = 3600
MIN_UNCOVERED = 0.2          # under 20% of the short left uncovered: not counted
BATCH = 60                   # wallets read per call of refresh() (one loop tick)
_INFO_URL = "https://api.hyperliquid.xyz/info"

# coin -> held amount in perp size units, per wallet; when each wallet was read
_held: Dict[str, Dict[str, float]] = {}
_read_at: Dict[str, float] = {}
_loaded = False


def _token_coins(token: str, amount: float) -> Dict[str, float]:
    """The perp coins (scanner keys) a spot token covers, in perp size units. HYPE is HYPE; Unit
    tokens are "U" + the coin (UBTC, UETH, USOL, UFART is FARTCOIN); a Unit token whose coin trades
    as a k market (UBONK) covers KBONK at 1/1000 (k markets are quoted per 1,000 tokens)."""
    from ticker_renames import K_BASES
    out: Dict[str, float] = {}
    name = token.upper()
    bases = {name}                                   # a coin's own token (HYPE, PURR, UNI)
    if name.startswith("U") and len(name) > 2:
        bases.add("FARTCOIN" if name == "UFART" else name[1:])   # Unit-bridged: UBTC, UETH, USOL
    for base in bases:
        out[base] = out.get(base, 0.0) + amount
        if base in K_BASES:
            out["K" + base] = out.get("K" + base, 0.0) + amount / 1000.0
    return out


def parse(spot: Optional[dict], delegator: Optional[dict] = None) -> Dict[str, float]:
    """coin -> amount held, from a spotClearinghouseState answer (and a delegatorSummary one)."""
    held: Dict[str, float] = {}
    for b in (spot or {}).get("balances") or []:
        try:
            amt = float(b.get("total") or 0)
        except (TypeError, ValueError):
            continue
        if amt <= 0 or str(b.get("coin", "")).upper().startswith("USD"):
            continue
        for coin, a in _token_coins(str(b.get("coin")), amt).items():
            held[coin] = held.get(coin, 0.0) + a
    if delegator:
        staked = sum(float(delegator.get(k) or 0) for k in ("delegated", "undelegated", "totalPendingWithdrawal"))
        if staked > 0:
            held["HYPE"] = held.get("HYPE", 0.0) + staked
    return held


def covered(address: str, coin: str) -> float:
    return _held.get(address, {}).get(coin, 0.0)


def counted(address: str, positions: List, normalize) -> List:
    """The positions as counted: hedged shorts left out or cut to their uncovered part."""
    if not _loaded:
        _load()
    held = _held.get(address)
    if not held:
        return positions
    out = []
    for p in positions:
        if p.side != "SHORT" or not p.size or p.dex or p.coin.startswith("xyz:"):
            out.append(p)
            continue
        h = held.get(normalize(p.coin), 0.0)
        if h <= 0:
            out.append(p)
            continue
        left = max(0.0, 1.0 - h / abs(p.size))
        if left < MIN_UNCOVERED:
            continue
        out.append(dataclasses.replace(p, size=p.size * left, size_usd=p.size_usd * left,
                                       unrealized_pnl=p.unrealized_pnl * left, margin_used=p.margin_used * left))
    return out


def due(wallets_with_shorts: Iterable[str], now: Optional[float] = None) -> List[str]:
    now = time.time() if now is None else now
    return [a for a in wallets_with_shorts if a not in _read_at or now - _read_at[a] >= REFRESH_S]


async def refresh(session, shorts: Dict[str, set], acquire, now: Optional[float] = None) -> int:
    """Read the spot (and, if short HYPE, staked) holdings of up to BATCH wallets that are due.
    ``shorts``: address -> the coins it is short. ``acquire(kind)``: the shared weight budget."""
    _load()
    now = time.time() if now is None else now
    todo = due(shorts, now)[:BATCH]
    done = 0
    for a in todo:
        try:
            await acquire("spotClearinghouseState")
            async with session.post(_INFO_URL, json={"type": "spotClearinghouseState", "user": a}) as resp:
                if resp.status != 200:
                    continue
                spot = await resp.json(content_type=None)
            delegator = None
            if "HYPE" in shorts[a]:
                await acquire("delegatorSummary")
                async with session.post(_INFO_URL, json={"type": "delegatorSummary", "user": a}) as resp:
                    if resp.status == 200:
                        delegator = await resp.json(content_type=None)
            held = parse(spot, delegator)
            if held:
                _held[a] = held
            else:
                _held.pop(a, None)
            _read_at[a] = now
            done += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("hedges: %s read failed: %s", a, exc)
    # Wallets no longer short anything need no reading; forget them.
    for a in [a for a in _read_at if a not in shorts]:
        _read_at.pop(a, None)
        _held.pop(a, None)
    if done:
        _save()
    return done


def stats() -> dict:
    return {"wallets_read": len(_read_at), "wallets_holding": len(_held)}


# --- persistence (hyperlens.db) -------------------------------------------------------

def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from hl_persistence import load_hedges
        for a, coin, amount, ts in load_hedges(time.time() - 2 * REFRESH_S):
            if coin:                                  # '' marks a wallet read with nothing held
                _held.setdefault(a, {})[coin] = amount
            _read_at[a] = max(_read_at.get(a, 0.0), ts)
    except Exception as exc:
        logger.warning("hedges: load failed: %s", exc)


def _save() -> None:
    try:
        from hl_persistence import save_hedges
        save_hedges({a: (_read_at.get(a, 0.0), held) for a, held in _held.items()},
                    {a: t for a, t in _read_at.items() if a not in _held})
    except Exception as exc:
        logger.warning("hedges: save failed: %s", exc)
