"""
Sector and ecosystem views: price races against BTC and profitable-trader lean.

Display only; nothing in the signal path reads this.

Series: each group's index is the chained *median* daily log return of its
member markets (perpetual markets only), rebased to 100, so a
single coin cannot drag the line. Closed daily candles only. BTC is returned as
its own line so the client can show the race or divide by BTC.

Lean: how the profitable-trader cohort is positioned in each group, counting
each wallet once per group (hl_intelligence.profitable_lean).
"""
from __future__ import annotations

import math
import statistics
import time
from typing import Dict, List, Optional

DAY = 86_400
MIN_MEMBERS = 2


def _closed_daily(store, symbol: str, days: int, now: float) -> Optional[Dict[int, float]]:
    d = store.get(symbol, "1d")
    if not d or len(d.get("close", [])) < 2:
        return None
    out = {}
    for ts, c in zip(d["timestamp"][-(days + 2):], d["close"][-(days + 2):]):
        t = int(ts) // 1000 if ts > 1e12 else int(ts)
        if t + DAY <= now and c and c > 0:   # skip the forming candle
            out[t // DAY * DAY] = float(c)
    return out


def _members(rows: List[dict]) -> Dict[str, List[dict]]:
    """Group key -> perpetual markets (spot wrappers such as UBTC would count a coin twice)."""
    groups: Dict[str, List[dict]] = {}
    for r in rows:
        if r.get("market_kind", "perpetual") != "perpetual":
            continue
        sector, eco = r.get("sector") or "Other", r.get("ecosystem")
        groups.setdefault(f"sector:{sector}", []).append(r)
        if eco:
            groups.setdefault(f"ecosystem:{eco}", []).append(r)
            groups.setdefault(f"pocket:{sector}|{eco}", []).append(r)
    return groups


def series(rows: List[dict], store, days: int = 90, now: Optional[float] = None) -> dict:
    now = time.time() if now is None else now
    closes = {r["symbol"]: _closed_daily(store, r["symbol"], days, now) for r in rows if r.get("symbol")}
    btc = closes.get("BTC/USDT") or {}
    dates = sorted(btc)[-(days + 1):]
    if len(dates) < 2:
        return {"dates": [], "btc": [], "groups": {}}

    def rets(sym):
        c = closes.get(sym) or {}
        return [math.log(c[b] / c[a]) if a in c and b in c else None for a, b in zip(dates, dates[1:])]

    def index(daily):
        out, level = [100.0], 100.0
        for x in daily:
            level *= math.exp(x or 0.0)
            out.append(round(level, 3))
        return out

    per_symbol = {}
    groups = {}
    for key, members in _members(rows).items():
        syms = [r["symbol"] for r in members]
        for s in syms:
            if s not in per_symbol:
                per_symbol[s] = rets(s)
        daily = []
        for t in range(len(dates) - 1):
            xs = [per_symbol[s][t] for s in syms if per_symbol[s][t] is not None]
            daily.append(statistics.median(xs) if len(xs) >= MIN_MEMBERS else None)
        if sum(x is not None for x in daily) < len(daily) // 2:
            continue
        groups[key] = {"n": len(syms), "coins": sorted(s.split("/")[0] for s in syms), "index": index(daily)}
    return {"dates": dates, "btc": index(rets("BTC/USDT")), "groups": groups}


def lean() -> dict:
    import hl_intelligence as hl
    from sectors import groups as sector_groups
    rows = hl.profitable_lean(sector_groups)
    return {"groups": rows, "traders_positioned": hl.profitable_traders_positioned(),
            "traders_tracked": len(hl._roster_money_printers)}


def lean_history(prefix: str, days: int = 30) -> Dict[str, list]:
    """Stored 4h lean per group: {group: [[bar_close, lean, long, short], ...]}."""
    from hl_persistence import load_trader_lean
    out: Dict[str, list] = {}
    for bar, grp, lo, sh, _, _ in load_trader_lean(prefix, time.time() - days * DAY):
        n = lo + sh
        out.setdefault(grp, []).append([bar, round((lo - sh) / n, 4) if n else 0.0, lo, sh])
    return out
