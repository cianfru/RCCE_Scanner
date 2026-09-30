"""
scan_view.py
~~~~~~~~~~~~
The scan list as the scanner pages read it, and one full row for the coin views.

``/api/scan`` returns every field of every row (~1.9 MB of JSON, ~145 KB gzip per
timeframe per pass). Most of that is per-coin detail that only the coin page and the
detail panel show (condition cards, research shadows, data-quality stamps), plus
fields no page reads. ``?view=list`` sends each row through :func:`list_row`:

* fields no page reads are left out (``DROP``);
* nested blocks the list reads only a part of keep that part (``_slim_*``);
* the sparkline (24 closes, a third of what is left) changes only when a candle
  closes, so it moves to its own feed, ``/api/scan/sparklines``, whose ETag holds
  between candles; the page merges it back by symbol;
* everything else is unchanged, so the grid, Radar, search and sectors see the same
  values as before.

The coin page and the detail panel ask ``/api/scan/row`` for the full row of the coin
they show. ``view=full`` (the default) keeps the original response for anything else.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

# Fields no page reads from the list. Kept in the full row.
DROP = frozenset({
    "cto", "cto_shadow", "cto_mode", "cto_policy", "cto_policy_evidence", "opportunity_persisted",
    "trading_setups", "expected_range", "decision_input_id", "decision_version", "decision_price",
    "signal_bar_close_time", "evidence_coverage", "weighted_total", "effective_conditions",
    "regime_probability", "smoothed_confidence", "regime_unstable", "regime_changes_7d",
    "signal_score", "vol_scale", "vol_state", "heat_direction", "agent_warnings", "vpin_label",
    "confidence_history", "funding_history", "oi_history", "oi_change_history", "lsr_history",
    "bsr_history", "spot_ratio_history", "vpin_history",
    # Per coin detail: the coin page and the detail panel read it from the full row.
    "signal_age_seconds",
    # Its own feed (see module docstring).
    "sparkline",
})

# Positioning keys the list reads (funding and OI cells, counter-evidence, size tiers, chart source).
_POSITIONING_KEYS = frozenset({
    "funding_rate", "funding_regime", "oi_trend", "oi_value", "oi_change_pct", "volume_24h",
    "source", "source_map", "spot_dominance", "top_trader_lsr", "leverage_risk",
})

# Condition keys the list reads (a coin's missing core inputs and market-wide outages).
_CONDITION_KEYS = ("name", "label", "group", "available")


def _slim_conditions(items: Any) -> Any:
    """Only the unavailable conditions, with the keys the list reads; the rest is detail."""
    if not isinstance(items, list):
        return items
    out = []
    for c in items:
        if isinstance(c, dict) and c.get("available") is False:
            out.append({k: c.get(k) for k in _CONDITION_KEYS if k in c})
    return out


def _slim_quality(q: Any) -> Any:
    """The derivatives feed's status only (the list reads whether it is ready)."""
    if not isinstance(q, dict):
        return q
    cg = q.get("coinglass")
    return {"coinglass": {"status": cg.get("status")}} if isinstance(cg, dict) else {}


def _slim_positioning(p: Any) -> Any:
    if not isinstance(p, dict):
        return p
    return {k: v for k, v in p.items() if k in _POSITIONING_KEYS}


def _round_money(k: str, v: Any) -> Any:
    """Dollar amounts to whole dollars, ratios to four decimals (what the list shows)."""
    if isinstance(v, float):
        return round(v) if ("notional" in k or k.endswith("_usd")) else round(v, 4)
    if isinstance(v, dict):
        return {a: _round_money(a, b) for a, b in v.items()}
    return v


def _slim_smart_money(s: Any) -> Any:
    if not isinstance(s, dict):
        return s
    return {k: _round_money(k, v) for k, v in s.items()}


def _slim_opportunity(o: Any) -> Any:
    if not isinstance(o, dict):
        return o
    return {k: o[k] for k in ("status", "direction", "setup_type") if k in o}


_SLIM = {
    "conditions_detail": _slim_conditions,
    "input_quality": _slim_quality,
    "opportunity": _slim_opportunity,
    "positioning": _slim_positioning,
    "smart_money": _slim_smart_money,
}


def list_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """One scan row as the list pages read it."""
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if k in DROP:
            continue
        fn = _SLIM.get(k)
        out[k] = fn(v) if fn else v
    return out


def list_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [list_row(r) for r in rows]


def sparklines(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Symbol -> its sparkline (the closes the list rows leave out)."""
    return {r["symbol"]: r.get("sparkline") or [] for r in rows if r.get("symbol")}


def find_row(rows: Iterable[Dict[str, Any]], symbol: str, market: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The row for *symbol* (``BTC/USDT``, ``BTC`` or ``BTCUSDT``), in *market* when given."""
    want = (symbol or "").strip().upper()
    if not want:
        return None
    rows = [r for r in rows if not market or (r.get("market_kind") or "perpetual") == market]
    for r in rows:
        if str(r.get("symbol", "")).upper() == want:
            return r
    for r in rows:
        base = str(r.get("symbol", "")).upper().split("/")[0]
        if base == want or str(r.get("symbol", "")).upper().replace("/", "") == want:
            return r
    return None
