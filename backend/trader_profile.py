"""
Trader leaderboard and trader profiles.

Leaderboard: the profitable traders (HyperLens "money printers") or the large accounts, ranked
by PnL over 7 days, 30 days or all time. The PnL and ROI figures are Hyperliquid's own leaderboard
windows ("week", "month", "allTime"), kept from the daily leaderboard download in hl_intelligence,
so they can lag by up to a day. Open positions come from the cohort sweep's latest reading.

Profile: one wallet's account (Hyperliquid ``portfolio``: account value history per window),
live positions (``clearinghouseState``) and its fills (``userFills`` and timed-order slices,
shared with the coin page's trader entries through trader_entries' cache and rate budget).

Fill classification: every fill carries the position size before it (``startPosition``), so each
one is placed against the running position of its coin:

    before 0                    open
    after 0                     close
    sign changes                flip  (closes one side and opens the other in one fill)
    |after| > |before|          add
    otherwise                   trim

Closed positions (round trips) run from an open to the close (or flip) that returns the coin to
flat. Win rate: the share of round trips closed in the window whose realised PnL net of fees is
above zero. Round trips whose opening fill is older than the fills on hand are left out of it.
"""
from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional

import aiohttp

from cohorts.sweeper import TokenBucket

logger = logging.getLogger(__name__)

ADDRESS_PATTERN = r"^0x[0-9a-fA-F]{40}$"
WINDOWS = ("7d", "30d", "all")
WINDOW_DAYS = {"7d": 7, "30d": 30, "all": None}
# hl_intelligence's roster fields per window: (pnl, roi); Hyperliquid names them week / month / allTime.
_ROSTER_FIELDS = {"7d": ("week_pnl", "week_roi"), "30d": ("pnl", "roi"), "all": ("all_time_pnl", "all_time_roi")}
# The perp account (the positions shown are perps; the leaderboard bands use the perp account too).
_PORTFOLIO_KEYS = {"7d": ("perpWeek", "week"), "30d": ("perpMonth", "month"), "all": ("perpAllTime", "allTime")}

PROFILE_FILLS_MAX_AGE_S = 90       # a profile re-reads fills older than this
PROFILE_CACHE_S = 60
PORTFOLIO_CACHE_S = 120
LEADERBOARD_CACHE_S = 60
STATS_TTL_S = 3 * 3600             # leaderboard win rates are recomputed after this
WARM_MAX_WALLETS = 100             # a leaderboard view warms at most this many wallets' win rates
MAX_COINS_SHOWN = 5

# Win rates for the leaderboard: one userFills request per wallet (20 weight plus 1 per 20 fills),
# on its own small share of the per-IP budget (the sweep takes 400/min, trader entries 480/min).
_warm_bucket = TokenBucket(240, capacity=240)
_CALL_WEIGHT = 20

_stats: Dict[str, tuple] = {}            # address -> (computed_at, {"7d": {...}, "30d": {...}, "all": {...}})
_portfolio_cache: Dict[str, tuple] = {}  # address -> (fetched_at, parsed portfolio)
_profile_cache: Dict[str, tuple] = {}    # address -> (built_at, profile)
_board_cache: Dict[tuple, tuple] = {}    # (window, cohort) -> (built_at, ranked rows)
_warm_task: Optional[asyncio.Task] = None
_warm_queue: List[str] = []


# ---------------------------------------------------------------------------
# Fill classification (pure)
# ---------------------------------------------------------------------------

def _dec(x) -> Optional[Decimal]:
    if x is None:
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def is_perp_fill(f: dict) -> bool:
    """A fill on a native Hyperliquid perpetual: spot pairs ("@107", "PURR/USDC") and builder-dex
    markets ("xyz:TSLA") are left out, as elsewhere in the app."""
    coin = str(f.get("coin") or "")
    d = str(f.get("dir") or "")
    return bool(coin) and not coin.startswith("@") and "/" not in coin and ":" not in coin \
        and ("Long" in d or "Short" in d)


def _sign(x: Decimal) -> int:
    return (x > 0) - (x < 0)


def _order(f: dict):
    """Time order; fills in the same millisecond (one order sweeping the book) chain by their
    starting size: rising for buys, falling for sells."""
    sp = _dec(f.get("startPosition")) or Decimal(0)
    return (f["time"], f.get("coin") or "", sp if f.get("side") == "B" else -sp)


def classify_fills(fills: Iterable[dict]) -> List[dict]:
    """Each perp fill placed against the running position of its coin, oldest first.

    Input fills are Hyperliquid's (``coin, time`` in ms, ``px, sz`` strings, ``side`` B/A,
    ``startPosition``, ``closedPnl``, ``fee``). ``startPosition`` is used when present (it survives
    gaps in the fills on hand); otherwise the running size is. Out: ``t`` (s), ``coin``, ``kind``
    (open/add/trim/close/flip), ``side`` (the position's side after the fill; the side closed for
    trim/close), ``px``, ``sz``, ``usd``, ``before``/``after`` (signed sizes), ``pnl`` (realised,
    net of the fee), ``avg_entry`` (the position's average entry after the fill; None when flat or
    when the opening happened before the fills on hand) and ``twap``.
    """
    fs = sorted((f for f in fills if is_perp_fill(f)), key=_order)
    # A timed-order slice already present among the regular fills (same coin, side and time) is dropped.
    regular = {(f["coin"], f.get("side"), f["time"]) for f in fs if not f.get("twap")}
    fs = [f for f in fs if not (f.get("twap") and (f["coin"], f.get("side"), f["time"]) in regular)]
    state: Dict[str, dict] = {}
    out = []
    for f in fs:
        coin = f["coin"]
        sz, px = _dec(f.get("sz")), _dec(f.get("px"))
        if not sz or px is None:
            continue
        st = state.setdefault(coin, {"pos": None, "avg": None})
        before = _dec(f.get("startPosition"))
        if before is None:
            before = st["pos"] if st["pos"] is not None else Decimal(0)
        if st["pos"] is None or (before != st["pos"] and _sign(before) != _sign(st["pos"])):
            # First fill seen for this coin, or a gap across a flat or a flip: the average entry is
            # unknown until the next open. (A gap on the same side keeps it: close enough.)
            st["avg"] = None
        delta = sz if f.get("side") == "B" else -sz
        after = before + delta
        sb, sa = _sign(before), _sign(after)
        if sb == 0:
            kind = "open"
        elif sa == 0:
            kind = "close"
        elif sa != sb:
            kind = "flip"
        elif abs(after) > abs(before):
            kind = "add"
        else:
            kind = "trim"
        pxf, szf = float(px), float(sz)
        avg = st["avg"]
        if kind in ("open", "flip"):
            avg = pxf
        elif kind == "add":
            avg = (avg * float(abs(before)) + pxf * szf) / float(abs(after)) if avg is not None else None
        elif kind == "close":
            avg = None
        st["pos"], st["avg"] = after, avg
        side_sign = sa if kind in ("open", "add", "flip") else sb
        pnl = float(_dec(f.get("closedPnl")) or 0) - float(_dec(f.get("fee")) or 0)
        out.append({
            "t": f["time"] / 1000, "coin": coin, "kind": kind, "side": "long" if side_sign > 0 else "short",
            "px": pxf, "sz": szf, "usd": round(pxf * szf, 2), "before": float(before), "after": float(after),
            "pnl": round(pnl, 2), "fee": float(_dec(f.get("fee")) or 0), "avg_entry": avg, "twap": bool(f.get("twap")),
        })
    return out


def round_trips(classified: List[dict]) -> dict:
    """Closed positions and the still-open ones, from classified fills (oldest first).

    A round trip starts at an open (or the opening half of a flip) and ends when the coin is flat
    again (or flips). One whose start is older than the fills on hand is ``partial``: its entry and
    PnL are incomplete. Out: {"closed": most recent first, "open": {coin: trip}}.
    """
    cur: Dict[str, dict] = {}
    closed: List[dict] = []

    def start(coin, f, partial):
        return {"coin": coin, "side": f["side"], "opened_at": None if partial else f["t"], "first_t": f["t"],
                "partial": partial, "_in_sz": 0.0, "_in_usd": 0.0, "_out_sz": 0.0, "_out_usd": 0.0,
                "pnl": 0.0, "fills": 0, "peak_size": 0.0, "adds": 0, "trims": 0}

    def finish(tr, t):
        tr["closed_at"] = t
        tr["entry_px"] = tr["_in_usd"] / tr["_in_sz"] if tr["_in_sz"] and not tr["partial"] else None
        tr["exit_px"] = tr["_out_usd"] / tr["_out_sz"] if tr["_out_sz"] else None
        basis = tr["entry_px"] * tr["_out_sz"] if tr["entry_px"] else None
        tr["pnl"] = round(tr["pnl"], 2)
        tr["pnl_pct"] = round(tr["pnl"] / basis * 100, 2) if basis else None
        tr["peak_usd"] = round(tr["peak_size"] * (tr["entry_px"] or tr["exit_px"] or 0))
        for k in ("_in_sz", "_in_usd", "_out_sz", "_out_usd"):
            tr.pop(k)
        return tr

    for f in classified:
        coin, kind = f["coin"], f["kind"]
        tr = cur.get(coin)
        if kind == "open" or tr is None:
            if tr is not None:                      # a gap in the fills: drop the unfinished one
                cur.pop(coin)
            tr = cur[coin] = start(coin, f, partial=kind != "open")
        tr["fills"] += 1
        if kind in ("open", "add"):
            tr["_in_sz"] += f["sz"]
            tr["_in_usd"] += f["usd"]
            tr["pnl"] += f["pnl"]
            tr["adds"] += kind == "add"
            tr["peak_size"] = max(tr["peak_size"], abs(f["after"]))
        elif kind == "trim":
            tr["_out_sz"] += f["sz"]
            tr["_out_usd"] += f["usd"]
            tr["pnl"] += f["pnl"]
            tr["trims"] += 1
            tr["peak_size"] = max(tr["peak_size"], abs(f["before"]))
        elif kind == "close":
            tr["_out_sz"] += f["sz"]
            tr["_out_usd"] += f["usd"]
            tr["pnl"] += f["pnl"]
            tr["peak_size"] = max(tr["peak_size"], abs(f["before"]))
            closed.append(finish(cur.pop(coin), f["t"]))
        elif kind == "flip":
            closing = abs(f["before"])
            share = closing / f["sz"] if f["sz"] else 1.0
            fee = f["fee"]
            tr["_out_sz"] += closing
            tr["_out_usd"] += closing * f["px"]
            # closedPnl on a flip is the closing half's; the fee is split by size.
            tr["pnl"] += f["pnl"] + fee - fee * share
            tr["peak_size"] = max(tr["peak_size"], closing)
            tr["side"] = "long" if f["before"] > 0 else "short"
            closed.append(finish(cur.pop(coin), f["t"]))
            nt = cur[coin] = start(coin, f, partial=False)
            nt["fills"] = 1
            nt["_in_sz"] = abs(f["after"])
            nt["_in_usd"] = abs(f["after"]) * f["px"]
            nt["pnl"] = -fee * (1 - share)
            nt["peak_size"] = abs(f["after"])
    closed.sort(key=lambda tr: -tr["closed_at"])
    opened = {}
    for coin, tr in cur.items():
        opened[coin] = {"coin": coin, "side": tr["side"], "opened_at": tr["opened_at"], "first_t": tr["first_t"],
                        "partial": tr["partial"], "fills": tr["fills"], "adds": tr["adds"], "trims": tr["trims"],
                        "realized": round(tr["pnl"], 2)}
    return {"closed": closed, "open": opened}


def win_stats(closed: List[dict], now: float) -> dict:
    """Per window: round trips closed in it (complete ones only), how many made money, the rate in %."""
    out = {}
    for w, days in WINDOW_DAYS.items():
        since = now - days * 86400 if days else None
        trips = [tr for tr in closed if not tr["partial"] and (since is None or tr["closed_at"] >= since)]
        wins = sum(1 for tr in trips if tr["pnl"] > 0)
        out[w] = {"wins": wins, "n": len(trips), "rate": round(wins / len(trips) * 100, 1) if trips else None}
    return out


def size_band(av: Optional[float]) -> Optional[str]:
    if not av or av <= 0:
        return None
    for floor, label in ((10e6, "$10M+"), (1e6, "$1M–10M"), (250e3, "$250K–1M"), (50e3, "$50K–250K")):
        if av >= floor:
            return label
    return "<$50K"


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

def _cohort_source(cohort: str):
    import hl_intelligence as hl
    return hl._roster_money_printers if cohort == "profitable" else hl._roster_smart_money


def _holdings(address: str) -> dict:
    """Open perp positions from the sweep's latest reading: count and coins, largest first."""
    import hl_intelligence as hl
    snaps = hl._snapshots.get(address)
    if not snaps:
        return {"n": None, "coins": [], "ts": None}
    latest = snaps[-1]
    ps = [p for p in latest.positions if not p.coin.startswith("xyz:") and p.dex != hl._XYZ_DEX and p.size]
    ps.sort(key=lambda p: -p.size_usd)
    return {"n": len(ps), "ts": latest.timestamp,
            "coins": [{"coin": hl._normalize_coin(p.coin), "side": p.side.lower(), "usd": round(p.size_usd)} for p in ps]}


def ranked(window: str, cohort: str = "profitable") -> List[dict]:
    """The cohort ranked by PnL over the window (Hyperliquid leaderboard figures), cached a minute."""
    import hl_intelligence as hl
    key = (window, cohort)
    hit = _board_cache.get(key)
    now = time.time()
    if hit and now - hit[0] < LEADERBOARD_CACHE_S:
        return hit[1]
    pnl_f, roi_f = _ROSTER_FIELDS[window]
    rows = []
    for w in _cohort_source(cohort):
        if w.account_value < hl._DISPLAY_MIN_AV:
            continue
        pnl = getattr(w, pnl_f, None)
        rows.append({"address": w.address, "pnl": pnl, "roi": getattr(w, roi_f, None),
                     "account_value": w.account_value, "band": size_band(w.account_value)})
    rows.sort(key=lambda r: (r["pnl"] is None, -(r["pnl"] or 0)))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    _board_cache[key] = (now, rows)
    return rows


def leaderboard(window: str = "30d", cohort: str = "profitable", offset: int = 0, limit: int = 50) -> dict:
    import hl_intelligence as hl
    rows = ranked(window, cohort)
    page = []
    missing = []
    now = time.time()
    for r in rows[offset:offset + limit]:
        h = _holdings(r["address"])
        st = _stats.get(r["address"])
        win = st[1]["30d"] if st else None
        if not st or now - st[0] > STATS_TTL_S:
            missing.append(r["address"])
        page.append({**r, "win_rate": win["rate"] if win else None, "closed_30d": win["n"] if win else None,
                     "positions": h["n"], "coins": [c["coin"] for c in h["coins"][:MAX_COINS_SHOWN]],
                     "sides": [c["side"] for c in h["coins"][:MAX_COINS_SHOWN]],
                     "more_coins": max(0, len(h["coins"]) - MAX_COINS_SHOWN)})
    if missing:
        _schedule_warm(missing[:WARM_MAX_WALLETS])
    return {"window": window, "cohort": cohort, "total": len(rows), "offset": offset, "limit": limit,
            "as_of": hl._roster_updated_at or None, "win_rate_pending": len(missing), "rows": page}


# ---------------------------------------------------------------------------
# Hyperliquid requests
# ---------------------------------------------------------------------------

async def _post(session: aiohttp.ClientSession, body: dict, bucket: TokenBucket):
    await bucket.take(_CALL_WEIGHT)
    async with session.post("https://api.hyperliquid.xyz/info", json=body) as resp:
        if resp.status == 429:
            bucket.penalize()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    if isinstance(data, list) and len(data) >= 20:
        await bucket.take(len(data) // 20)
    return data


def _schedule_warm(addresses: List[str]) -> None:
    """Compute win rates for these wallets in the background, one at a time (at most one task)."""
    global _warm_task, _warm_queue
    _warm_queue = list(dict.fromkeys(addresses))
    if _warm_task is None or _warm_task.done():
        try:
            _warm_task = asyncio.get_running_loop().create_task(_warm())
        except RuntimeError:                      # no running loop (sync caller in tests)
            _warm_task = None


async def _warm() -> None:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        while _warm_queue:
            address = _warm_queue.pop(0)
            st = _stats.get(address)
            if st and time.time() - st[0] < STATS_TTL_S:
                continue
            try:
                raw = await _post(session, {"type": "userFills", "user": address, "aggregateByTime": True}, _warm_bucket)
                _stats[address] = (time.time(), win_stats(round_trips(classify_fills(raw))["closed"], time.time()))
            except Exception as exc:
                logger.warning("trader leaderboard: fills for %s failed: %s", address[:10], exc)
                await asyncio.sleep(5)


async def wallet_fills(address: str) -> dict:
    """The wallet's fills (shared cache with trader entries), at most PROFILE_FILLS_MAX_AGE_S old."""
    import trader_entries as te
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        return await te._wallet_fills(session, address, max_age=PROFILE_FILLS_MAX_AGE_S)


def parse_portfolio(raw) -> dict:
    """Hyperliquid portfolio -> {window: {"pnl", "equity": [[t_s, value]], "start_value"}} for 7d/30d/all,
    for the perp account (the whole account when the perp series are missing)."""
    by = {k: v for k, v in raw} if isinstance(raw, list) else {}
    out = {}
    for w, (perp_key, key) in _PORTFOLIO_KEYS.items():
        d = by.get(perp_key) or by.get(key) or {}
        av = [[p[0] / 1000, float(p[1])] for p in d.get("accountValueHistory") or []]
        pnl = d.get("pnlHistory") or []
        out[w] = {"pnl": float(pnl[-1][1]) if pnl else None, "equity": av,
                  "start_value": av[0][1] if av else None}
    return out


async def portfolio(address: str) -> Optional[dict]:
    import trader_entries as te
    hit = _portfolio_cache.get(address)
    if hit and time.time() - hit[0] < PORTFOLIO_CACHE_S:
        return hit[1]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        raw = await _post(session, {"type": "portfolio", "user": address}, te._bucket)
    res = parse_portfolio(raw)
    if len(_portfolio_cache) > 500:
        _portfolio_cache.clear()
    _portfolio_cache[address] = (time.time(), res)
    return res


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def _positions(state: Optional[dict], open_trips: Dict[str, dict]) -> List[dict]:
    import hl_intelligence as hl
    out = []
    for p in hl._parse_positions(state or {}):
        if ":" in p.coin:
            continue
        sign = 1 if p.side == "LONG" else -1
        mark = p.entry_px + sign * p.unrealized_pnl / p.size if p.size else p.entry_px
        roe = p.return_on_equity * 100 if p.return_on_equity else (
            p.unrealized_pnl / p.margin_used * 100 if p.margin_used else None)
        trip = open_trips.get(p.coin) or {}
        out.append({
            "coin": hl._normalize_coin(p.coin), "hl_coin": p.coin, "side": p.side.lower(), "size": p.size,
            "size_usd": round(p.size * mark), "entry_px": p.entry_px, "mark_px": mark,
            "upnl": round(p.unrealized_pnl, 2), "roe_pct": None if roe is None else round(roe, 1),
            "leverage": p.leverage, "leverage_type": p.leverage_type, "liq_px": p.liq_px or None,
            "liq_distance_pct": p.liq_distance_pct, "margin": round(p.margin_used, 2),
            "opened_at": trip.get("opened_at"), "fills": trip.get("fills"), "adds": trip.get("adds"),
            "trims": trip.get("trims"), "realized": trip.get("realized"),
        })
    out.sort(key=lambda x: -x["size_usd"])
    return out


def _windows(address: str, port: Optional[dict]) -> dict:
    """PnL and ROI per window: the Hyperliquid leaderboard figures for a tracked wallet (the ones the
    leaderboard ranks by), else the wallet's own Hyperliquid account history (no ROI)."""
    import hl_intelligence as hl
    w = next((x for x in hl._roster if x.address == address), None)
    out = {}
    for win, (pnl_f, roi_f) in _ROSTER_FIELDS.items():
        pnl = getattr(w, pnl_f, None) if w else None
        if pnl is not None:
            out[win] = {"pnl": pnl, "roi": getattr(w, roi_f, None), "source": "leaderboard"}
        else:
            out[win] = {"pnl": (port or {}).get(win, {}).get("pnl"), "roi": None, "source": "account"}
    return out


async def profile(address: str) -> Optional[dict]:
    """Everything the profile page shows but the trade history. None when Hyperliquid knows nothing
    of the address (no account history, no positions and no fills)."""
    import hl_intelligence as hl
    from hyperliquid_data import fetch_clearinghouse_state
    address = address.lower()
    hit = _profile_cache.get(address)
    if hit and time.time() - hit[0] < PROFILE_CACHE_S:
        return hit[1]
    results = await asyncio.gather(fetch_clearinghouse_state(address), portfolio(address), wallet_fills(address),
                                   return_exceptions=True)
    state, port, fills = [None if isinstance(r, BaseException) else r for r in results]
    for r in results:
        if isinstance(r, BaseException):
            logger.warning("trader profile %s: %s", address[:10], r)
    now = time.time()
    fl = (fills or {}).get("fills") or []
    trips = round_trips(classify_fills(fl))
    stats = win_stats(trips["closed"], now)
    if fills is not None:
        _stats[address] = (now, stats)
    positions = _positions(state, trips["open"])
    equity = {w: (port or {}).get(w, {}).get("equity") or [] for w in WINDOWS}
    has_history = any(any(v for _, v in equity[w]) for w in WINDOWS)
    tracked = any(x.address == address for x in hl._roster)
    if not (tracked or has_history or positions or fl):
        return None
    av = None
    if equity["all"]:
        av = equity["all"][-1][1]
    elif state:
        av = float((state.get("marginSummary") or {}).get("accountValue", 0) or 0)
    ranks = {w: next((x["rank"] for x in ranked(w) if x["address"] == address), None) for w in WINDOWS}
    res = {
        "address": address, "tracked": tracked, "cohorts": sorted(hl._wallet_cohorts.get(address, set())),
        "ranks": ranks, "board_size": len(ranked("30d", "profitable")),
        "account_value": av, "band": size_band(av), "windows": _windows(address, port), "win": stats,
        "equity": equity, "positions": positions,
        "fills_on_hand": len(fl), "covered_from": (fills or {}).get("covered_from"),
        "earliest_fill": fl[0]["time"] / 1000 if fl else None,
        "updated_at": now, "partial": [k for k, v in (("positions", state), ("account", port), ("fills", fills)) if v is None],
    }
    if len(_profile_cache) > 300:
        _profile_cache.clear()
    _profile_cache[address] = (now, res)
    return res


def _match(coin_filter: Optional[str], coin: str) -> bool:
    if not coin_filter:
        return True
    from hl_intelligence import _normalize_coin
    return coin == coin_filter or _normalize_coin(coin) == _normalize_coin(coin_filter)


async def fills(address: str, coin: Optional[str] = None, since: Optional[float] = None,
                until: Optional[float] = None, limit: int = 500) -> dict:
    """Classified fills, most recent first, optionally for one coin and a time range (seconds)."""
    from hl_intelligence import _normalize_coin
    got = await wallet_fills(address.lower())
    cl = classify_fills(got["fills"])
    sel = [dict(f, hl_coin=f["coin"], coin=_normalize_coin(f["coin"])) for f in cl
           if _match(coin, f["coin"]) and (since is None or f["t"] >= since) and (until is None or f["t"] <= until)]
    sel.reverse()
    return {"address": address.lower(), "coin": _normalize_coin(coin) if coin else None, "count": len(sel),
            "fills": sel[:limit], "truncated": len(sel) > limit, "covered_from": got.get("covered_from")}


async def history(address: str, coin: Optional[str] = None, offset: int = 0, limit: int = 20) -> dict:
    """Closed positions (round trips), most recent first, paginated."""
    from hl_intelligence import _normalize_coin
    got = await wallet_fills(address.lower())
    every = [dict(tr, hl_coin=tr["coin"], coin=_normalize_coin(tr["coin"]))
             for tr in round_trips(classify_fills(got["fills"]))["closed"]]
    counts: Dict[str, int] = {}
    for tr in every:
        counts[tr["coin"]] = counts.get(tr["coin"], 0) + 1
    trips = [tr for tr in every if _match(coin, tr["hl_coin"])]
    return {"address": address.lower(), "total": len(trips), "offset": offset, "limit": limit,
            "trips": trips[offset:offset + limit], "covered_from": got.get("covered_from"),
            "earliest_fill": got["fills"][0]["time"] / 1000 if got.get("fills") else None,
            "coins": [{"coin": c, "n": n} for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]}
