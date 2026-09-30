"""
public_preview.py
~~~~~~~~~~~~~~~~~
Public payloads for the landing page.

* ``preview_rows``: five large markets, one slim scan row each (/api/public/preview).
* ``landing``: the Radar map slimmed to what the landing draws, the read of one coin,
  breadth by week and the forward test's counter (/api/public/landing).

A full scan row carries well over a hundred fields; these keep what the page reads.
"""

from __future__ import annotations

import json
from typing import Iterable, List, Optional

PREVIEW_COINS = ("BTC", "ETH", "SOL", "HYPE", "LINK")

# Copied as they are.
_FIELDS = (
    "symbol", "timeframe", "price", "market_kind", "sector", "ecosystem", "size_tier",
    "regime", "regime_transition", "history_bars", "normalization_ready",
    "signal", "signal_status", "signal_reason", "signal_warnings", "strong_long_blockers",
    "entry_blocked", "signal_confidence", "conditions_met", "conditions_total",
    "zscore", "energy", "heat", "heat_phase", "exhaustion_state", "floor_confirmed",
    "divergence", "cvd_trend", "cvd_divergence", "buy_sell_ratio",
    "confluence", "smart_money", "priority_score", "sparkline",
)
# Per entry check: enough to name a check that has no data.
_CONDITION_FIELDS = ("name", "label", "group", "available", "met")


def preview_row(row: dict) -> dict:
    out = {k: row[k] for k in _FIELDS if k in row}
    positioning = row.get("positioning")
    if isinstance(positioning, dict):
        out["positioning"] = {"oi_trend": positioning.get("oi_trend")}
    detail = row.get("conditions_detail")
    if isinstance(detail, list):
        out["conditions_detail"] = [
            {k: c[k] for k in _CONDITION_FIELDS if k in c} for c in detail if isinstance(c, dict)
        ]
    return out


def preview_rows(results: Iterable[dict]) -> List[dict]:
    """One slim row per preview coin, in coin order; the USDT quote wins when a coin has two."""
    best = {}
    for row in results or []:
        symbol = str(row.get("symbol", ""))
        base, _, quote = symbol.partition("/")
        if base not in PREVIEW_COINS or quote not in ("USDT", "USD", "USDC"):
            continue
        if base not in best or (quote == "USDT" and not best[base]["symbol"].endswith("/USDT")):
            best[base] = row
    return [preview_row(best[c]) for c in PREVIEW_COINS if c in best]


# ------------------------------------------------------------------ the landing page
# One small public payload for the landing (/api/public/landing): the Radar map slimmed to
# what the map draws, the read of one coin, breadth since 2021 by week, and the Radar
# forward test's day counter. The same for every visitor, so the CDN serves it (edge.py).

# The coin the landing follows through every section: HYPE, Hyperliquid's own token, so the
# live read matches the page's screen crops. When it is not on the map, the coin whose
# profitable traders hold the most dollars.
LANDING_FOCUS = "HYPE"


def _r(v, nd=3):
    return round(v, nd) if isinstance(v, float) else v


def _landing_coin(c: dict) -> dict:
    t = c.get("traders") or {}
    m = c.get("money") or {}
    b = c.get("band") or {}
    e = c.get("entry") or {}
    tr = c.get("trail") or {}
    out = {
        "coin": c.get("coin"), "symbol": c.get("symbol"), "price": c.get("price"), "regime": c.get("regime"),
        "zscore": _r(c.get("zscore")), "priority": _r(c.get("priority"), 1), "stage": c.get("stage"),
        "zone": c.get("zone"), "crowd": c.get("crowd"), "checks": c.get("checks"),
        "traders": {k: t[k] for k in ("pl", "ps", "n24l") if t.get(k) is not None},
        "money": {k: _r(m[k]) for k in ("long_usd", "short_usd", "gross_usd", "net_long_share") if m.get(k) is not None},
        "entry": {k: _r(e[k], 2) for k in ("dist_pct", "in_zone") if k in e},
        "band": {k: b[k] for k in ("lo", "hi", "week_close") if b.get(k) is not None},
        "trail": {"t": tr.get("t") or [], "z": [_r(z) for z in tr.get("z") or []], "n": tr.get("n") or []},
    }
    if c.get("transition"):
        out["transition"] = {k: c["transition"].get(k) for k in ("need", "seen") if k in c["transition"]}
    return out


def _drawn(c: dict) -> bool:
    """A coin the landing's map draws in any view (the app's setupMap.visible, Long, Short or Both)."""
    t = c.get("traders") or {}
    pl, ps = t.get("pl") or 0, t.get("ps") or 0
    if ps - pl >= 1:
        return True
    return c.get("stage") != "waiting" and (pl + ps > 0 or c.get("stage") in ("forming", "fresh"))


def landing_focus(coins: List[dict]) -> Optional[dict]:
    on_map = [c for c in coins if c.get("zscore") is not None]
    hit = next((c for c in on_map if c.get("coin") == LANDING_FOCUS), None)
    if hit:
        return hit
    return max(on_map, key=lambda c: (c.get("money") or {}).get("gross_usd") or 0, default=None)


def landing(smap: Optional[dict], results: Iterable[dict], history: Optional[dict] = None,
            forward: Optional[dict] = None) -> dict:
    smap = smap or {}
    coins = [c for c in smap.get("coins") or [] if c.get("zscore") is not None and _drawn(c)]
    focus = landing_focus(coins)
    row = next((r for r in results or [] if focus and r.get("symbol") == focus.get("symbol")), None)
    slim = [_landing_coin(c) for c in coins]
    # The closes are the same for nearly every coin: sent once, and left out of a coin's
    # trail when they match (the page puts them back).
    ts = [json.dumps(c["trail"]["t"]) for c in slim]
    common = json.loads(max(set(ts), key=ts.count)) if ts else []
    for c in slim:
        if c["trail"]["t"] == common:
            del c["trail"]["t"]
    out = {
        "as_of": smap.get("as_of") or smap.get("updated_at"),
        "box": smap.get("box"),
        "focus": focus.get("coin") if focus else None,
        "t": common,
        "coins": slim,
        "read": preview_row(row) if row else None,
    }
    if history:
        cols = history.get("columns") or []
        iu = cols.index("uptrend") if "uptrend" in cols else 2
        days = history.get("days") or []
        weekly = [[d[0], round(d[iu], 3)] for d in days[::7]]
        if days and weekly[-1][0] != days[-1][0]:
            weekly.append([days[-1][0], round(days[-1][iu], 3)])
        cyc = history.get("cycle") or {}
        out["history"] = {
            "weekly": weekly,
            "today": {k: (history.get("today") or {}).get(k) for k in ("day", "uptrend")},
            "cycle": {k: cyc.get(k) for k in ("type", "start", "day", "threshold", "runs", "past", "median")},
        }
    if forward:
        out["forward"] = {k: forward.get(k) for k in ("declared", "days_logged", "next_report_day", "min_events", "min_coins")}
    return out
