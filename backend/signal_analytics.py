"""
signal_analytics.py
~~~~~~~~~~~~~~~~~~~
Performance attribution engine for RCCE Scanner signals.

Mines the existing signal_events SQLite table to answer:
  - Which conditions predict winners?
  - Which condition combos work best?
  - How does performance vary by regime / confluence level?
  - Do whale-confirmed signals outperform?
  - Does signal alpha decay over time?

All data comes from signal_events — no new data collection needed.
Uses a 5-minute in-memory cache to avoid repeated expensive queries.
"""

from __future__ import annotations

import itertools
import json
import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LONG_SIGNALS = {
    "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE",
    "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
}
_EXIT_SIGNALS = {"TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"}
_CACHE_TTL = 300  # 5 minutes

# All known condition names (used for combo iteration)
_ALL_CONDITIONS = [
    # Core (weight 1.0)
    "bullish_regime", "consensus", "z_range", "no_bear_div",
    "heat_ok", "no_climax", "funding_ok", "not_greedy", "liquidity_ok",
    # CoinGlass (weight 0.75)
    "oi_confirms", "cvd_confirms", "smart_money_ok", "macro_tailwind",
    # HyperLens (weight 0.5)
    "hl_whale_aligned", "hl_not_counter",
]

_CONDITION_GROUP = {
    "bullish_regime": "core", "consensus": "core", "z_range": "core",
    "no_bear_div": "core", "heat_ok": "core", "no_climax": "core",
    "funding_ok": "core", "not_greedy": "core", "liquidity_ok": "core",
    "oi_confirms": "coinglass", "cvd_confirms": "coinglass",
    "smart_money_ok": "coinglass", "macro_tailwind": "coinglass",
    "hl_whale_aligned": "hyperlens", "hl_not_counter": "hyperlens",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_conditions(context_str: Optional[str]) -> Optional[Dict[str, bool]]:
    """Parse context JSON and return {condition_name: bool} map.

    Returns None if context is missing or unparseable.
    """
    if not context_str:
        return None
    try:
        ctx = json.loads(context_str)
        details = ctx.get("synthesis", {}).get("conditions_detail", [])
        if not details:
            return None
        return {d["name"]: bool(d["met"]) for d in details if "name" in d}
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _is_win(signal: str, outcome_7d_pct: float) -> bool:
    """Determine if a signal outcome was a 'win'.

    LONG signals win when price goes up; EXIT signals win when price goes down.
    """
    if signal in _LONG_SIGNALS:
        return outcome_7d_pct > 0
    if signal in _EXIT_SIGNALS:
        return outcome_7d_pct < 0
    return False


# ---------------------------------------------------------------------------
# Analytics engine
# ---------------------------------------------------------------------------

class SignalAnalytics:
    """Performance attribution analytics for signal events."""

    def __init__(self, signal_log) -> None:
        self._log = signal_log
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def invalidate_cache(self) -> None:
        """Clear all cached results (call after outcome back-fill)."""
        self._cache.clear()

    async def _cached(self, key: str, compute_fn):
        now = time.time()
        if key in self._cache:
            ts, result = self._cache[key]
            if now - ts < _CACHE_TTL:
                return result
        result = await compute_fn()
        self._cache[key] = (now, result)
        return result

    # ------------------------------------------------------------------
    # Internal: fetch rows with outcomes
    # ------------------------------------------------------------------

    async def _fetch_rows_with_outcomes(
        self, timeframe: str, extra_where: str = "", extra_params: tuple = ()
    ) -> list:
        """Fetch signal_events rows that have 7d outcomes."""
        db = self._log._ensure_db()
        sql = (
            "SELECT signal, regime, conditions_met, conditions_total, "
            "       outcome_1d_pct, outcome_3d_pct, outcome_7d_pct, context "
            "FROM signal_events "
            f"WHERE timeframe = ? AND outcome_7d_pct IS NOT NULL AND signal != 'WAIT' {extra_where} "
            "ORDER BY timestamp DESC"
        )
        cursor = await db.execute(sql, (timeframe, *extra_params))
        return await cursor.fetchall()

    # ==================================================================
    # 1. Condition Predictive Value
    # ==================================================================

    async def condition_predictive_value(
        self, timeframe: str = "4h",
    ) -> List[Dict[str, Any]]:
        """For each condition: avg 7d return and win rate when TRUE vs FALSE."""

        async def _compute():
            rows = await self._fetch_rows_with_outcomes(timeframe)
            # Buckets: condition_name -> {"true": [outcomes], "false": [outcomes]}
            buckets: Dict[str, Dict[str, list]] = {
                c: {"true": [], "false": []} for c in _ALL_CONDITIONS
            }

            for r in rows:
                conds = _extract_conditions(r["context"])
                if not conds:
                    continue
                outcome = r["outcome_7d_pct"]
                signal = r["signal"]
                win = _is_win(signal, outcome)

                for cond_name in _ALL_CONDITIONS:
                    val = conds.get(cond_name)
                    if val is None:
                        continue  # Condition not present (e.g., no CoinGlass data)
                    key = "true" if val else "false"
                    buckets[cond_name][key].append((outcome, win))

            results = []
            for cond_name in _ALL_CONDITIONS:
                b = buckets[cond_name]
                t_outcomes = b["true"]
                f_outcomes = b["false"]

                t_count = len(t_outcomes)
                f_count = len(f_outcomes)
                t_avg = sum(o for o, _ in t_outcomes) / t_count if t_count else None
                f_avg = sum(o for o, _ in f_outcomes) / f_count if f_count else None
                t_wr = sum(1 for _, w in t_outcomes if w) / t_count * 100 if t_count else None
                f_wr = sum(1 for _, w in f_outcomes if w) / f_count * 100 if f_count else None

                edge = round(t_avg - f_avg, 2) if t_avg is not None and f_avg is not None else None

                results.append({
                    "name": cond_name,
                    "group": _CONDITION_GROUP[cond_name],
                    "true_count": t_count,
                    "false_count": f_count,
                    "avg_7d_true": round(t_avg, 2) if t_avg is not None else None,
                    "avg_7d_false": round(f_avg, 2) if f_avg is not None else None,
                    "win_rate_true": round(t_wr, 1) if t_wr is not None else None,
                    "win_rate_false": round(f_wr, 1) if f_wr is not None else None,
                    "edge": edge,
                })

            # Sort by absolute edge descending
            results.sort(key=lambda x: abs(x["edge"] or 0), reverse=True)
            return results

        return await self._cached(f"cpv:{timeframe}", _compute)

    # ==================================================================
    # 2. Condition Combo Attribution
    # ==================================================================

    async def condition_combo_attribution(
        self,
        timeframe: str = "4h",
        combo_size: int = 3,
        min_samples: int = 5,
    ) -> List[Dict[str, Any]]:
        """Top condition combinations ranked by win rate."""

        async def _compute():
            rows = await self._fetch_rows_with_outcomes(timeframe)

            # Pre-compute met-condition sets per row
            row_data: List[Tuple[frozenset, float, bool]] = []
            for r in rows:
                conds = _extract_conditions(r["context"])
                if not conds:
                    continue
                met = frozenset(c for c, v in conds.items() if v)
                outcome = r["outcome_7d_pct"]
                win = _is_win(r["signal"], outcome)
                row_data.append((met, outcome, win))

            if not row_data:
                return []

            # Only consider conditions that appear in the data
            present_conditions = set()
            for met, _, _ in row_data:
                present_conditions.update(met)
            active_conditions = [c for c in _ALL_CONDITIONS if c in present_conditions]

            # Iterate all combos
            combo_stats: Dict[frozenset, Dict] = {}
            for combo in itertools.combinations(active_conditions, combo_size):
                combo_set = frozenset(combo)
                outcomes = []
                wins = 0
                for met, outcome, win in row_data:
                    if combo_set.issubset(met):
                        outcomes.append(outcome)
                        if win:
                            wins += 1

                if len(outcomes) < min_samples:
                    continue

                combo_stats[combo_set] = {
                    "conditions": sorted(combo_set),
                    "count": len(outcomes),
                    "wins": wins,
                    "win_rate": round(wins / len(outcomes) * 100, 1),
                    "avg_7d": round(sum(outcomes) / len(outcomes), 2),
                }

            # Sort by win rate desc, then by count desc
            ranked = sorted(
                combo_stats.values(),
                key=lambda x: (x["win_rate"], x["count"]),
                reverse=True,
            )
            return ranked[:20]

        return await self._cached(f"combo:{timeframe}:{combo_size}:{min_samples}", _compute)

    # ==================================================================
    # 3. Regime-Stratified Scorecard
    # ==================================================================

    async def regime_stratified_scorecard(
        self, timeframe: str = "4h",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Signal performance broken down by regime."""

        async def _compute():
            rows = await self._fetch_rows_with_outcomes(timeframe)

            # Group by (signal, regime)
            groups: Dict[Tuple[str, str], list] = defaultdict(list)
            for r in rows:
                groups[(r["signal"], r["regime"])].append(
                    (r["outcome_7d_pct"], _is_win(r["signal"], r["outcome_7d_pct"]))
                )

            result: Dict[str, List[Dict]] = defaultdict(list)
            for (signal, regime), entries in groups.items():
                count = len(entries)
                if count < 2:
                    continue
                wins = sum(1 for _, w in entries if w)
                avg_7d = sum(o for o, _ in entries) / count
                result[signal].append({
                    "regime": regime,
                    "count": count,
                    "win_rate": round(wins / count * 100, 1),
                    "avg_7d": round(avg_7d, 2),
                })

            # Sort each signal's regimes by count desc
            for sig in result:
                result[sig].sort(key=lambda x: x["count"], reverse=True)

            return dict(result)

        return await self._cached(f"regime:{timeframe}", _compute)

    # ==================================================================
    # 4. Confluence-Stratified Scorecard
    # ==================================================================

    async def confluence_stratified_scorecard(
        self, timeframe: str = "4h",
    ) -> List[Dict[str, Any]]:
        """Performance by conditions_met bucket."""

        async def _compute():
            rows = await self._fetch_rows_with_outcomes(timeframe)

            def _bucket(met: int) -> str:
                if met >= 12:
                    return "12+"
                elif met >= 10:
                    return "10-11"
                elif met >= 8:
                    return "8-9"
                else:
                    return "<8"

            buckets: Dict[str, list] = defaultdict(list)
            for r in rows:
                met = r["conditions_met"] or 0
                b = _bucket(met)
                buckets[b].append(
                    (r["outcome_7d_pct"], _is_win(r["signal"], r["outcome_7d_pct"]), r["signal"])
                )

            bucket_order = ["12+", "10-11", "8-9", "<8"]
            results = []
            for b in bucket_order:
                entries = buckets.get(b, [])
                if not entries:
                    results.append({"bucket": b, "count": 0, "win_rate": None, "avg_7d": None, "signals": {}})
                    continue

                count = len(entries)
                wins = sum(1 for _, w, _ in entries if w)
                avg_7d = sum(o for o, _, _ in entries) / count

                # Per-signal breakdown within bucket
                sig_groups: Dict[str, list] = defaultdict(list)
                for o, w, sig in entries:
                    sig_groups[sig].append((o, w))
                signals = {}
                for sig, sg_entries in sig_groups.items():
                    sc = len(sg_entries)
                    sw = sum(1 for _, w in sg_entries if w)
                    signals[sig] = {
                        "count": sc,
                        "win_rate": round(sw / sc * 100, 1),
                    }

                results.append({
                    "bucket": b,
                    "count": count,
                    "win_rate": round(wins / count * 100, 1),
                    "avg_7d": round(avg_7d, 2),
                    "signals": signals,
                })

            return results

        return await self._cached(f"confluence:{timeframe}", _compute)

    # ==================================================================
    # 5. Signal Edge Decay
    # ==================================================================

    async def signal_edge_decay(
        self, timeframe: str = "4h",
    ) -> List[Dict[str, Any]]:
        """How signal returns distribute across time periods."""

        async def _compute():
            rows = await self._fetch_rows_with_outcomes(timeframe,
                extra_where="AND signal IN ('STRONG_LONG','LIGHT_LONG','ACCUMULATE','REVIVAL_SEED','REVIVAL_SEED_CONFIRMED')")

            periods = {
                "0-24h": [],
                "24h-72h": [],
                "72h-7d": [],
            }

            for r in rows:
                d1 = r["outcome_1d_pct"]
                d3 = r["outcome_3d_pct"]
                d7 = r["outcome_7d_pct"]

                if d1 is not None:
                    periods["0-24h"].append(d1)
                if d1 is not None and d3 is not None:
                    periods["24h-72h"].append(d3 - d1)
                if d3 is not None and d7 is not None:
                    periods["72h-7d"].append(d7 - d3)

            results = []
            for period in ["0-24h", "24h-72h", "72h-7d"]:
                values = periods[period]
                if values:
                    results.append({
                        "period": period,
                        "avg_return": round(sum(values) / len(values), 2),
                        "count": len(values),
                        "positive_pct": round(sum(1 for v in values if v > 0) / len(values) * 100, 1),
                    })
                else:
                    results.append({
                        "period": period,
                        "avg_return": None,
                        "count": 0,
                        "positive_pct": None,
                    })

            return results

        return await self._cached(f"decay:{timeframe}", _compute)

    # ==================================================================
    # 6. HyperLens Attribution
    # ==================================================================

    async def hyperlens_attribution(
        self, timeframe: str = "4h",
    ) -> Dict[str, Any]:
        """Compare performance with vs without whale confirmation."""

        async def _compute():
            rows = await self._fetch_rows_with_outcomes(timeframe,
                extra_where="AND signal IN ('STRONG_LONG','LIGHT_LONG','ACCUMULATE','REVIVAL_SEED','REVIVAL_SEED_CONFIRMED')")

            with_whale = []
            without_whale = []

            for r in rows:
                conds = _extract_conditions(r["context"])
                if conds is None:
                    continue
                outcome = r["outcome_7d_pct"]
                win = _is_win(r["signal"], outcome)
                whale = conds.get("hl_whale_aligned")

                if whale is None:
                    continue  # No HyperLens data for this event
                if whale:
                    with_whale.append((outcome, win))
                else:
                    without_whale.append((outcome, win))

            def _stats(entries):
                if not entries:
                    return {"count": 0, "avg_7d": None, "win_rate": None}
                count = len(entries)
                avg = sum(o for o, _ in entries) / count
                wins = sum(1 for _, w in entries if w)
                return {
                    "count": count,
                    "avg_7d": round(avg, 2),
                    "win_rate": round(wins / count * 100, 1),
                }

            ww = _stats(with_whale)
            wo = _stats(without_whale)

            edge = None
            if ww["avg_7d"] is not None and wo["avg_7d"] is not None:
                edge = round(ww["avg_7d"] - wo["avg_7d"], 2)

            return {
                "with_whale": ww,
                "without_whale": wo,
                "edge_pct": edge,
            }

        return await self._cached(f"hl:{timeframe}", _compute)

    # ==================================================================
    # Combined endpoint
    # ==================================================================

    async def get_full_attribution(
        self, timeframe: str = "4h",
    ) -> Dict[str, Any]:
        """Combined response with all 6 analytics sections."""
        return {
            "timeframe": timeframe,
            "conditions": await self.condition_predictive_value(timeframe),
            "combos": await self.condition_combo_attribution(timeframe),
            "regime_scorecard": await self.regime_stratified_scorecard(timeframe),
            "confluence_scorecard": await self.confluence_stratified_scorecard(timeframe),
            "edge_decay": await self.signal_edge_decay(timeframe),
            "hyperlens": await self.hyperlens_attribution(timeframe),
        }
