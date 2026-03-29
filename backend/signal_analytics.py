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
_MAX_RETURN_CORRUPT = 500.0  # ±500% — anything beyond this is data error

# Position span constants
_WAIT_TIMEOUT_S = 4 * 3600  # WAIT persisting >4h = real exit, not churn
_MIN_SIGNAL_DURATION_S = 2 * 3600  # Exclude signals that lasted <2h (churn)

# Signal ranking for best-signal tracking within a span
_SIGNAL_RANK = {
    "REVIVAL_SEED": 1, "REVIVAL_SEED_CONFIRMED": 2,
    "ACCUMULATE": 3, "LIGHT_LONG": 4, "STRONG_LONG": 5,
}


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
    # 7. Position Spans + Per-Symbol Win Rate
    # ==================================================================

    async def _build_position_spans(
        self, timeframe: str, symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build position spans from signal events.

        A span = one continuous position from ENTRY to real EXIT.
        WAIT gaps < 4h are bridged (treated as churn, not a real close).
        Upgrades/downgrades within a span are tracked but don't create new spans.
        """
        db = self._log._ensure_db()

        where = "WHERE timeframe = ?"
        params: list = [timeframe]
        if symbol:
            where += " AND symbol = ?"
            params.append(symbol)

        cursor = await db.execute(
            f"SELECT signal, symbol, price, timestamp, regime, "
            f"       conditions_met, conditions_total, context "
            f"FROM signal_events {where} ORDER BY timestamp ASC",
            tuple(params),
        )
        rows = await cursor.fetchall()

        # Group by symbol
        by_sym: Dict[str, list] = defaultdict(list)
        for r in rows:
            by_sym[r["symbol"]].append(r)

        all_spans: List[Dict[str, Any]] = []

        for sym, events in by_sym.items():
            span = None  # Current open span

            for ev in events:
                sig = ev["signal"]
                ts = ev["timestamp"]
                price = ev["price"]
                is_long = sig in _LONG_SIGNALS
                is_exit = sig in _EXIT_SIGNALS

                if span is None:
                    # No open span — open one if signal is long
                    if is_long:
                        span = {
                            "symbol": sym,
                            "entry_signal": sig,
                            "best_signal": sig,
                            "entry_price": price,
                            "entry_ts": ts,
                            "entry_regime": ev["regime"],
                            "entry_conditions_met": ev["conditions_met"],
                            "entry_conditions_total": ev["conditions_total"],
                            "entry_context": ev["context"],
                            "exit_price": None,
                            "exit_ts": None,
                            "exit_reason": None,
                            "_wait_since": None,
                            "_wait_price": None,
                        }
                else:
                    # Span is open — first check if a pending WAIT has timed out
                    if span["_wait_since"] is not None and ts - span["_wait_since"] >= _WAIT_TIMEOUT_S:
                        # WAIT lasted >4h before this event arrived → close span
                        span["exit_price"] = span["_wait_price"]
                        span["exit_ts"] = span["_wait_since"]
                        span["exit_reason"] = "WAIT_TIMEOUT"
                        all_spans.append(span)
                        span = None
                        # If this event is a new long, open a new span
                        if is_long:
                            span = {
                                "symbol": sym,
                                "entry_signal": sig,
                                "best_signal": sig,
                                "entry_price": price,
                                "entry_ts": ts,
                                "entry_regime": ev["regime"],
                                "entry_conditions_met": ev["conditions_met"],
                                "entry_conditions_total": ev["conditions_total"],
                                "entry_context": ev["context"],
                                "exit_price": None,
                                "exit_ts": None,
                                "exit_reason": None,
                                "_wait_since": None,
                                "_wait_price": None,
                            }
                        continue

                    if is_long:
                        # Still in position — update best signal, clear WAIT
                        if _SIGNAL_RANK.get(sig, 0) > _SIGNAL_RANK.get(span["best_signal"], 0):
                            span["best_signal"] = sig
                        span["_wait_since"] = None
                        span["_wait_price"] = None

                    elif is_exit:
                        # Real exit signal — close span
                        span["exit_price"] = price
                        span["exit_ts"] = ts
                        span["exit_reason"] = sig
                        all_spans.append(span)
                        span = None

                    elif sig == "WAIT":
                        # Record when WAIT started (will be checked on next event)
                        if span["_wait_since"] is None:
                            span["_wait_since"] = ts
                            span["_wait_price"] = price

            # Handle still-open span at end of data
            if span is not None:
                now = int(time.time())
                if span["_wait_since"] is not None:
                    wait_dur = now - span["_wait_since"]
                    if wait_dur >= _WAIT_TIMEOUT_S:
                        # WAIT has persisted to present — close span
                        span["exit_price"] = span["_wait_price"]
                        span["exit_ts"] = span["_wait_since"]
                        span["exit_reason"] = "WAIT_TIMEOUT"
                        all_spans.append(span)
                # else: span still open (active position), don't include

        # Compute return and duration for closed spans
        result = []
        for s in all_spans:
            if s["exit_price"] is None or s["entry_price"] is None or s["entry_price"] <= 0:
                continue
            ret = (s["exit_price"] - s["entry_price"]) / s["entry_price"] * 100
            if abs(ret) > _MAX_RETURN_CORRUPT:
                continue  # Corrupted data
            dur_h = (s["exit_ts"] - s["entry_ts"]) / 3600
            result.append({
                "symbol": s["symbol"],
                "entry_signal": s["entry_signal"],
                "best_signal": s["best_signal"],
                "entry_price": s["entry_price"],
                "exit_price": s["exit_price"],
                "return_pct": round(ret, 2),
                "win": ret > 0,
                "duration_hours": round(dur_h, 1),
                "exit_reason": s["exit_reason"],
                "regime": s["entry_regime"],
                "conditions_met": s["entry_conditions_met"],
                "conditions_total": s["entry_conditions_total"],
                "context": s["entry_context"],
            })

        return result

    async def symbol_win_rate(
        self, symbol: str, timeframe: str = "4h",
    ) -> Dict[str, Any]:
        """Win rate from position spans for a specific symbol."""

        async def _compute():
            spans = await self._build_position_spans(timeframe, symbol=symbol)
            if not spans:
                return {"symbol": symbol, "total": 0}

            total = len(spans)
            wins = sum(1 for s in spans if s["win"])
            avg_ret = sum(s["return_pct"] for s in spans) / total
            avg_dur = sum(s["duration_hours"] for s in spans) / total

            # Per-signal breakdown (by best_signal reached during span)
            by_signal: Dict[str, list] = defaultdict(list)
            for s in spans:
                by_signal[s["best_signal"]].append(s)

            signals = []
            for sig in ["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"]:
                sg = by_signal.get(sig, [])
                if not sg:
                    continue
                n = len(sg)
                w = sum(1 for s in sg if s["win"])
                avg = sum(s["return_pct"] for s in sg) / n
                dur = sum(s["duration_hours"] for s in sg) / n
                signals.append({
                    "signal": sig, "count": n,
                    "win_rate": round(w / n * 100, 1),
                    "avg_return": round(avg, 2),
                    "avg_hold_hours": round(dur, 1),
                })

            return {
                "symbol": symbol,
                "total": total,
                "wins": wins,
                "win_rate": round(wins / total * 100, 1),
                "avg_return": round(avg_ret, 2),
                "avg_hold_hours": round(avg_dur, 1),
                "signals": signals,
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
