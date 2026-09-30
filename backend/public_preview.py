"""
public_preview.py
~~~~~~~~~~~~~~~~~
The landing page's public preview: five large markets, one row each, with only the
fields the landing shows (the embedded scanner table, its help popovers and the hero
card). A full scan row carries well over a hundred fields; the landing reads about
thirty, so the rest never leaves the server.
"""

from __future__ import annotations

from typing import Iterable, List

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
