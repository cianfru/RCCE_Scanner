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


def _is_win(signal: str, outcome_pct: float) -> bool:
    """Determine if a signal outcome was a 'win'.

    LONG signals win when price goes up; EXIT signals win when price goes down.
    """
    if signal in _LONG_SIGNALS:
        return outcome_pct > 0
    if signal in _EXIT_SIGNALS:
        return outcome_pct < 0
    return False


# Corruption filter — returns beyond this are back-fill errors, not real moves
# (micro-cap coins, stale price back-fills producing 200,000%+ returns)
_MAX_RETURN_CORRUPT = 500.0  # ±500% — anything beyond this is data error

# Minimum signal duration to count in analytics — signals that churn
# (e.g., LIGHT_LONG for 19 minutes then back to WAIT) are noise
_MIN_SIGNAL_DURATION_S = 2 * 3600  # 2 hours minimum


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
        """Fetch signal_events rows that have 7d outcomes.

        Excludes corrupted back-fills (>500% return = data error, not real move)
        and very short-lived signals (<2h) that churned and don't represent
        real conviction.

        Duration is measured as time until the NEXT signal event (including WAIT),
        so a LIGHT_LONG → STRONG_LONG upgrade after 30min correctly filters the
        short LIGHT_LONG while keeping the STRONG_LONG.
        """
        db = self._log._ensure_db()

        # Step 1: fetch ALL signal events (including WAIT) for duration calculation
        all_cursor = await db.execute(
            "SELECT symbol, signal, timestamp FROM signal_events "
            "WHERE timeframe = ? ORDER BY timestamp DESC",
            (timeframe,),
        )
        all_rows = await all_cursor.fetchall()

        # Build next-event timestamp map: (symbol, timestamp) → next_event_ts
        next_event_ts: Dict[tuple, int] = {}
        prev_by_sym: Dict[str, int] = {}  # symbol → most recent timestamp seen
        for r in all_rows:
            sym = r["symbol"]
            ts = r["timestamp"]
            if sym in prev_by_sym:
                # prev_by_sym has the MORE RECENT event (we iterate DESC)
                next_event_ts[(sym, ts)] = prev_by_sym[sym]
            prev_by_sym[sym] = ts

        # Step 2: fetch the actual analytics rows (non-WAIT, with outcomes)
        sql = (
            "SELECT signal, regime, conditions_met, conditions_total, "
            "       outcome_1d_pct, outcome_3d_pct, outcome_7d_pct, context, "
            "       timestamp, symbol "
            "FROM signal_events "
            f"WHERE timeframe = ? AND outcome_7d_pct IS NOT NULL AND signal != 'WAIT' "
            f"AND abs(outcome_7d_pct) <= {_MAX_RETURN_CORRUPT} "
            f"{extra_where} "
            "ORDER BY timestamp DESC"
        )
        cursor = await db.execute(sql, (timeframe, *extra_params))
        rows = await cursor.fetchall()

        # Step 3: filter by signal duration
        filtered = []
        for r in rows:
            key = (r["symbol"], r["timestamp"])
            next_ts = next_event_ts.get(key)
            if next_ts is None:
                # Most recent event for this symbol — include
                filtered.append(r)
            else:
                duration = next_ts - r["timestamp"]
                if duration >= _MIN_SIGNAL_DURATION_S:
                    filtered.append(r)

        return filtered

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
        """Top condition combinations ranked by lift over baseline.

        Only considers conditions that are FALSE at least 10% of the time
        (always-true conditions don't differentiate). Ranks by lift
        (combo WR minus baseline WR) to surface truly predictive combos.
        Deduplicates combos that match the exact same set of rows.
        """

        async def _compute():
            rows = await self._fetch_rows_with_outcomes(timeframe)

            # Pre-compute met-condition sets per row
            row_data: List[Tuple[frozenset, float, bool]] = []
            total_wins = 0
            for r in rows:
                conds = _extract_conditions(r["context"])
                if not conds:
                    continue
                met = frozenset(c for c, v in conds.items() if v)
                outcome = r["outcome_7d_pct"]
                win = _is_win(r["signal"], outcome)
                row_data.append((met, outcome, win))
                if win:
                    total_wins += 1

            if not row_data:
                return []

            baseline_wr = total_wins / len(row_data) * 100
            baseline_avg = sum(o for _, o, _ in row_data) / len(row_data)

            # Count how often each condition is TRUE vs FALSE
            cond_true_rate: Dict[str, float] = {}
            for cond in _ALL_CONDITIONS:
                true_count = sum(1 for met, _, _ in row_data if cond in met)
                total_with_cond = sum(
                    1 for met, _, _ in row_data
                    # Only count rows where this condition was evaluated
                    if any(c == cond for c in met) or True  # simplify: count all
                )
                cond_true_rate[cond] = true_count / len(row_data) if row_data else 0

            # Filter: only use conditions that are FALSE >= 10% of the time
            # (conditions that are always TRUE don't differentiate)
            selective_conditions = [
                c for c in _ALL_CONDITIONS
                if cond_true_rate.get(c, 0) < 0.90 and cond_true_rate.get(c, 0) > 0.01
            ]

            # If too few selective conditions, relax to 95% threshold
            if len(selective_conditions) < combo_size:
                selective_conditions = [
                    c for c in _ALL_CONDITIONS
                    if cond_true_rate.get(c, 0) < 0.95 and cond_true_rate.get(c, 0) > 0.01
                ]

            if len(selective_conditions) < combo_size:
                return []

            # Iterate combos, dedup by matching row count
            combo_stats: Dict[frozenset, Dict] = {}
            seen_counts: Dict[int, int] = {}  # match_count -> how many combos have it

            for combo in itertools.combinations(selective_conditions, combo_size):
                combo_set = frozenset(combo)
                outcomes = []
                wins = 0
                for met, outcome, win in row_data:
                    if combo_set.issubset(met):
                        outcomes.append(outcome)
                        if win:
                            wins += 1

                n = len(outcomes)
                if n < min_samples:
                    continue

                # Dedup: skip combos that match the exact same row count
                # (likely the same rows, just different always-true conditions swapped)
                seen_counts[n] = seen_counts.get(n, 0) + 1
                if seen_counts[n] > 3:
                    continue  # max 3 combos per row-count bucket

                wr = wins / n * 100
                avg = sum(outcomes) / n
                lift = round(wr - baseline_wr, 1)

                combo_stats[combo_set] = {
                    "conditions": sorted(combo_set),
                    "count": n,
                    "wins": wins,
                    "win_rate": round(wr, 1),
                    "avg_7d": round(avg, 2),
                    "lift": lift,
                    "baseline_wr": round(baseline_wr, 1),
                }

            # Sort by lift desc (how much better than baseline), then count desc
            ranked = sorted(
                combo_stats.values(),
                key=lambda x: (x["lift"], x["count"]),
                reverse=True,
            )
            return ranked[:15]

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
    # 7. Per-Symbol Win Rate
    # ==================================================================

    async def symbol_win_rate(
        self, symbol: str, timeframe: str = "4h",
    ) -> Dict[str, Any]:
        """Win rate and performance stats for a specific symbol across 1d/3d/7d horizons."""

        async def _compute():
            db = self._log._ensure_db()
            cursor = await db.execute(
                """SELECT signal, regime, conditions_met, conditions_total,
                          outcome_1d_pct, outcome_3d_pct, outcome_7d_pct, timestamp
                   FROM signal_events
                   WHERE timeframe = ? AND symbol = ?
                     AND signal != 'WAIT'
                     AND (outcome_1d_pct IS NOT NULL
                       OR outcome_3d_pct IS NOT NULL
                       OR outcome_7d_pct IS NOT NULL)
                   ORDER BY timestamp DESC""",
                (timeframe, symbol),
            )
            rows = await cursor.fetchall()
            if not rows:
                return {"symbol": symbol, "total": 0}

            # Filter corrupted back-fills
            clean_rows = [r for r in rows if not (
                (r["outcome_7d_pct"] is not None and abs(r["outcome_7d_pct"]) > _MAX_RETURN_CORRUPT) or
                (r["outcome_3d_pct"] is not None and abs(r["outcome_3d_pct"]) > _MAX_RETURN_CORRUPT) or
                (r["outcome_1d_pct"] is not None and abs(r["outcome_1d_pct"]) > _MAX_RETURN_CORRUPT)
            )]

            # Get ALL events (including WAIT) for this symbol to measure duration
            dur_cursor = await db.execute(
                "SELECT signal, timestamp FROM signal_events "
                "WHERE timeframe = ? AND symbol = ? ORDER BY timestamp DESC",
                (timeframe, symbol),
            )
            dur_rows = await dur_cursor.fetchall()
            # Build next-event map
            next_ts_map: Dict[int, int] = {}
            for i, dr in enumerate(dur_rows):
                if i > 0:
                    next_ts_map[dr["timestamp"]] = dur_rows[i - 1]["timestamp"]

            # Filter short-lived signals (< 2h duration)
            filtered_rows = []
            for r in clean_rows:
                nxt = next_ts_map.get(r["timestamp"])
                if nxt is None:
                    filtered_rows.append(r)  # Most recent
                elif nxt - r["timestamp"] >= _MIN_SIGNAL_DURATION_S:
                    filtered_rows.append(r)

            if not filtered_rows:
                return {"symbol": symbol, "total": 0}

            # Multi-horizon stats
            horizons = {}
            for label, col in [("1d", "outcome_1d_pct"), ("3d", "outcome_3d_pct"), ("7d", "outcome_7d_pct")]:
                vals = [(r["signal"], r[col]) for r in filtered_rows
                        if r[col] is not None]
                if not vals:
                    horizons[label] = {"count": 0, "win_rate": None, "avg": None}
                    continue
                n = len(vals)
                wins = sum(1 for sig, o in vals if _is_win(sig, o))
                avg = sum(o for _, o in vals) / n
                horizons[label] = {
                    "count": n,
                    "win_rate": round(wins / n * 100, 1),
                    "avg": round(avg, 2),
                }

            # Use 7d as primary, fall back to 3d, then 1d
            primary = horizons.get("7d", {})
            if not primary.get("count"):
                primary = horizons.get("3d", {})
            if not primary.get("count"):
                primary = horizons.get("1d", {})
            total = primary.get("count", 0)
            win_rate = primary.get("win_rate")

            # Per-signal breakdown (use best available outcome)
            by_signal: Dict[str, list] = defaultdict(list)
            by_regime: Dict[str, list] = defaultdict(list)
            for r in filtered_rows:
                sig = r["signal"]
                regime = r["regime"]
                outcome = r["outcome_7d_pct"] or r["outcome_3d_pct"] or r["outcome_1d_pct"]
                if outcome is None:
                    continue
                win = _is_win(sig, outcome)
                by_signal[sig].append((outcome, win))
                by_regime[regime].append((outcome, win))

            signal_stats = {}
            for sig, entries in by_signal.items():
                n = len(entries)
                w = sum(1 for _, win in entries if win)
                avg = sum(o for o, _ in entries) / n
                signal_stats[sig] = {
                    "count": n,
                    "win_rate": round(w / n * 100, 1),
                    "avg": round(avg, 2),
                }

            regime_stats = {}
            for reg, entries in by_regime.items():
                n = len(entries)
                if n >= 2:
                    w = sum(1 for _, win in entries if win)
                    regime_stats[reg] = {
                        "count": n,
                        "win_rate": round(w / n * 100, 1),
                    }

            return {
                "symbol": symbol,
                "total": total,
                "win_rate": win_rate,
                "horizons": horizons,
                "by_signal": signal_stats,
                "by_regime": regime_stats,
            }

        return await self._cached(f"sym_wr:{symbol}:{timeframe}", _compute)

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
