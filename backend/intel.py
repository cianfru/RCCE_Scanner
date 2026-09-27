"""
Setup intel: what tracked wallets are doing on the scanner's best setups, in one small
answer per coin, plus a one-line pulse of the profitable traders overall.

Built only from data the server already holds (the positioning map and the tracker's
opens of the last 24 hours); nothing here calls an outside API.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

RECENT_S = 24 * 3600
PULSE_S = 6 * 3600
MAX_RECENT = 20
MAX_CLUSTERS = 5


def _new_wallets(opens: Iterable[dict], since: float) -> Dict[str, Dict[str, int]]:
    """Distinct wallets that opened each side since ``since``, per cohort."""
    seen: Dict[tuple, set] = {}
    for o in opens:
        if o["ts"] >= since:
            seen.setdefault((o["cohort"], o["side"]), set()).add(o["address"])
    return {c: {s: len(seen.get((c, s), ())) for s in ("long", "short")} for c in ("profitable", "large")}


def coin_intel(coin: str, profitable: Optional[dict], large: Optional[dict], opens: List[dict],
               convergence: Optional[dict], now: float) -> dict:
    """``profitable`` / ``large``: this coin's positioning-map rows (or None when nobody holds it).
    ``opens``: the tracker's opens of the last 24h, any coin (filtered here)."""
    mine = sorted((o for o in opens if o["coin"] == coin and now - o["ts"] <= RECENT_S), key=lambda o: -o["ts"])
    empty = {"n": 0, "usd": 0, "median_entry": None, "in_profit": 0}
    side = lambda row, s: (row or {}).get(s) or empty
    mark = (profitable or {}).get("mark") or (large or {}).get("mark")
    conv = None
    if convergence:
        conv = {k: convergence.get(k) for k in ("side", "n", "ts", "first_px", "last_px")}
    return {
        "coin": coin,
        "mark": mark,
        "profitable": {"long": side(profitable, "long"), "short": side(profitable, "short")},
        "large": {"long": side(large, "long"), "short": side(large, "short")},
        "new_24h": _new_wallets(mine, now - RECENT_S),
        "new_6h": _new_wallets(mine, now - PULSE_S),
        "recent": [{"t": o["ts"], "side": o["side"], "cohort": o["cohort"], "px": o["entry_px"],
                    "usd": round(o["size_usd"])} for o in mine[:MAX_RECENT]],
        "convergence": conv,
    }


def pulse(wallets: int, holding: int, opens: List[dict], now: float) -> dict:
    """Profitable traders overall: how many hold anything, and what they opened in the last 6h."""
    recent = [o for o in opens if o["cohort"] == "profitable" and now - o["ts"] <= PULSE_S]
    by_key: Dict[tuple, set] = {}
    for o in recent:
        by_key.setdefault((o["coin"], o["side"]), set()).add(o["address"])
    clusters = sorted(({"coin": c, "side": s, "n": len(a)} for (c, s), a in by_key.items() if len(a) >= 2),
                      key=lambda x: (-x["n"], x["coin"]))
    return {
        "wallets": wallets,
        "holding": holding,
        "flat": max(0, wallets - holding),
        "hours": PULSE_S // 3600,
        "opens": len(recent),
        "traders": len({o["address"] for o in recent}),
        "coins": len({o["coin"] for o in recent}),
        "clusters": clusters[:MAX_CLUSTERS],
    }
