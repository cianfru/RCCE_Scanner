"""
Forward test of funding and whales (docs/reviews/funding-whales-forward-test.md, declared 29 October 2026): each day
from 30 October 2026 whose next 30 days have closed, the reading against the typical coin's next 30 days with the last
30 days held fixed. Collecting under 180 forward days, interim from 180, the verdict on the first 365. Context, not a
signal unless a bar is met.

Everything comes from what the server already keeps (funding_history, wallet_history, market_history); the record is
computed once per new close.
"""
from __future__ import annotations

import statistics
from typing import Callable, Dict, Optional

FROM_DAY = 20756            # 30 October 2026
H = 30
INTERIM_DAYS = 180
VERDICT_DAYS = 365
MIN_RHO = 0.15
TAIL = 0.10
TRAIL = 365

_cache: dict = {}


def funding_reading(rows: list) -> Dict[int, float]:
    """{day: 7-day mean of the BTC and ETH average (yearly %)}, with at least 5 of the 7 days."""
    avg = {r[0]: (r[1] + r[2]) / 2 for r in rows or [] if r[1] is not None and r[2] is not None}
    out = {}
    for d in avg:
        w = [avg[d - k] for k in range(7) if d - k in avg]
        if len(w) >= 5:
            out[d] = sum(w) / len(w)
    return out


def whales_reading(wallets: dict, coin: Optional[str] = None) -> Dict[int, float]:
    """{day: (long - short) / wallets} for the whales group, or (long - short) / (long + short) in one coin."""
    if coin:
        cols = wallets.get("coin_columns") or []
        ix = {c: i for i, c in enumerate(cols)}
        rows = ((wallets.get("coins") or {}).get(coin) or {}).get("whales") or []
        return {r[ix["day"]]: (r[ix["long"]] - r[ix["short"]]) / (r[ix["long"]] + r[ix["short"]])
                for r in rows if (r[ix["long"]] or 0) + (r[ix["short"]] or 0)}
    ix = {c: i for i, c in enumerate(wallets.get("columns") or [])}
    rows = (wallets.get("groups") or {}).get("whales") or []
    return {r[ix["day"]]: (r[ix["long"]] - r[ix["short"]]) / r[ix["wallets"]] for r in rows if r[ix["wallets"]]}


def test(reading: Dict[int, float], outcome: Callable, past: Callable, sign: int, last_day: int) -> dict:
    """The declared statistic on the forward days so far (the verdict on the first 365 only)."""
    from research.turn_signs import block_interval, spearman
    pts = []
    for d in sorted(reading):
        if d < FROM_DAY or d + H > last_day:
            continue
        y, z = outcome(d), past(d)
        if y is not None and z is not None:
            pts.append((d, reading[d], y, z))
    n = len(pts)
    status = "collecting" if n < INTERIM_DAYS else "interim" if n < VERDICT_DAYS else "verdict"
    out = {"days": n, "status": status, "from": FROM_DAY, "needed": VERDICT_DAYS}
    use = pts[:VERDICT_DAYS]
    if n >= 2 * H:
        x, y, z = ([p[i] for p in use] for i in (1, 2, 3))
        out.update({"rho": round(spearman(x, y), 3), "partial": round(spearman(x, y, z), 3),
                    "interval": block_interval(x, y, z)})
    if status == "verdict":
        lo, hi = out["interval"]
        ok = sign * out["partial"] >= MIN_RHO and (hi < 0 if sign < 0 else lo > 0)
        out["verdict"] = "met" if ok else "not met"
    return out


def tails(reading: Dict[int, float], outcome: Callable, last_day: int) -> Optional[dict]:
    """Reported for funding: forward days in the top and bottom 10% of the previous 365 days' readings."""
    fwd = [d for d in sorted(reading) if FROM_DAY <= d and d + H <= last_day and outcome(d) is not None]
    if not fwd:
        return None
    every = statistics.median(outcome(d) for d in fwd)
    top, bottom = [], []
    for d in fwd:
        prev = sorted(reading[d - k] for k in range(1, TRAIL + 1) if d - k in reading)
        if len(prev) < TRAIL // 2:
            continue
        if reading[d] >= prev[int((1 - TAIL) * (len(prev) - 1))]:
            top.append(outcome(d))
        elif reading[d] <= prev[int(TAIL * (len(prev) - 1))]:
            bottom.append(outcome(d))
    med = lambda xs: None if not xs else round(statistics.median(xs), 1)   # noqa: E731
    return {"every_day": round(every, 1), "top": {"days": len(top), "median": med(top)},
            "bottom": {"days": len(bottom), "median": med(bottom)}}


def record(days: list, alt_ret: Callable, funding_rows: list, wallets: dict) -> dict:
    """days: market history rows [day, ..., btc last]; alt_ret(t, e): the typical coin's % change."""
    last = days[-1][0] if days else 0
    btc = {d[0]: d[-1] for d in days if d[-1]}
    alt_next = lambda d: alt_ret(d, d + H)                                                    # noqa: E731
    alt_past = lambda d: alt_ret(d - H, d)                                                    # noqa: E731
    btc_next = lambda d: None if not btc.get(d) or not btc.get(d + H) else 100 * (btc[d + H] / btc[d] - 1)  # noqa: E731
    btc_past = lambda d: None if not btc.get(d) or not btc.get(d - H) else 100 * (btc[d] / btc[d - H] - 1)  # noqa: E731
    f = funding_reading(funding_rows)
    w = whales_reading(wallets)
    wb = whales_reading(wallets, "BTC")
    return {
        "declared": "docs/reviews/funding-whales-forward-test.md (29 October 2026)",
        "through": last,
        "funding": {**test(f, alt_next, alt_past, -1, last),
                    "reported": {"btc": test(f, btc_next, btc_past, -1, last), "tails": tails(f, alt_next, last)}},
        "whales": {**test(w, alt_next, alt_past, +1, last),
                   "reported": {"btc_in_btc": test(wb, btc_next, btc_past, +1, last)}},
    }


def view() -> dict:
    """The record as of the latest close, computed once per close."""
    import funding_history
    import market_history
    import wallet_history
    seed = market_history._load()
    days = [d for d in market_history.all_days() if d[1] >= seed["min_coins"]]
    wallets = wallet_history.view()
    whales = (wallets.get("groups") or {}).get("whales") or []
    key = (days[-1][0] if days else None, funding_history.view().get("through"), whales[-1][0] if whales else None)
    if _cache.get("key") != key:
        _cache["key"] = key
        _cache["view"] = record(days, market_history._alt_ret(seed), funding_history.view()["rows"], wallets)
    return _cache["view"]
