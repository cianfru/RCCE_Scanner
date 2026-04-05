"""
assistant_context.py
~~~~~~~~~~~~~~~~~~~~
Extended context builders for the trading assistant.

Adds richer data layers that the LLM can reference:
  1. Fear & Greed 7-day trend (not just current value)
  2. Signal backtest stats (win rates from signal_log)
  3. Convergence-ranked best setups
  4. Comparative pair analysis
  5. Liquidation pressure context
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Fear & Greed 7-Day Trend
# ══════════════════════════════════════════════════════════════════════════════

# Cache for F&G trend data
_fng_trend_cache: Dict[str, Any] = {"data": None, "expires": 0}
_FNG_TREND_TTL = 4 * 3600  # 4 hours (updates daily)


async def build_fng_trend_context() -> str:
    """Fetch 7-day Fear & Greed trend and format for LLM context.

    Uses the same CoinGlass endpoint that already returns the full history
    array — we just grab the last 7 entries instead of only the latest.
    """
    import aiohttp
    import os

    now = time.time()
    if _fng_trend_cache["data"] and now < _fng_trend_cache["expires"]:
        return _fng_trend_cache["data"]

    api_key = os.environ.get("COINGLASS_API_KEY", "")
    if not api_key:
        return ""

    url = "https://open-api-v4.coinglass.com/api/index/fear-greed-history"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"CG-API-KEY": api_key},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return ""
                payload = await resp.json()

        if payload.get("code") != "0":
            return ""

        data = payload.get("data", [])
        if not data:
            return ""

        entry = data[0] if isinstance(data, list) else data
        values = entry.get("data_list") or entry.get("dataList") or []
        timestamps = entry.get("time_list") or entry.get("timeList") or []

        if len(values) < 7:
            return ""

        # Last 7 days
        recent = values[-7:]
        recent_int = [int(v) for v in recent]

        def _label(v: int) -> str:
            if v <= 20: return "Extreme Fear"
            if v <= 40: return "Fear"
            if v <= 60: return "Neutral"
            if v <= 80: return "Greed"
            return "Extreme Greed"

        # Trend analysis
        first, last = recent_int[0], recent_int[-1]
        delta = last - first
        if delta > 10:
            direction = "rising sharply"
        elif delta > 3:
            direction = "rising"
        elif delta < -10:
            direction = "falling sharply"
        elif delta < -3:
            direction = "falling"
        else:
            direction = "stable"

        trend_str = " → ".join(str(v) for v in recent_int)
        result = (
            f"### Fear & Greed Trend (7d)\n"
            f"{trend_str} ({direction}, Δ{delta:+d})\n"
            f"Current: {last} ({_label(last)}) | 7d ago: {first} ({_label(first)})"
        )

        _fng_trend_cache["data"] = result
        _fng_trend_cache["expires"] = now + _FNG_TREND_TTL
        return result

    except Exception as e:
        logger.warning("F&G trend fetch failed: %s", e)
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# 2. Signal Backtest Stats
# ══════════════════════════════════════════════════════════════════════════════

async def build_backtest_context(symbol: Optional[str] = None) -> str:
    """Pull win-rate scorecard from signal_log and format for LLM.

    If a symbol is provided, also include that symbol's specific history stats.
    """
    try:
        from signal_log import SignalLog
        sl = SignalLog()
        await sl.initialize()

        # Global scorecard
        scorecard = await sl.get_scorecard(timeframe="4h")
        if not scorecard:
            return ""

        lines = [
            "### Signal Backtest Stats (4H)",
            "Historical win rates based on 7-day price outcomes:",
        ]

        for card in scorecard:
            sig = card["signal"]
            count = card["count"]
            wr = card.get("win_rate")
            avg_7d = card.get("avg_7d")
            has = card.get("has_outcomes", 0)

            if has < 3:  # not enough data
                continue

            wr_str = f"{wr:.0f}%" if wr is not None else "N/A"
            avg_str = f"{avg_7d:+.1f}%" if avg_7d is not None else "N/A"
            lines.append(
                f"- **{sig}**: {wr_str} win rate "
                f"(avg 7d: {avg_str}, n={has})"
            )

        # Symbol-specific history if requested
        if symbol:
            db = sl._ensure_db()
            cursor = await db.execute(
                """SELECT signal, COUNT(*) as cnt,
                          AVG(CASE WHEN abs(outcome_7d_pct) <= 500 THEN outcome_7d_pct END) as avg_7d,
                          COUNT(CASE WHEN outcome_7d_pct IS NOT NULL AND abs(outcome_7d_pct) <= 500 THEN 1 END) as has_7d
                   FROM signal_events
                   WHERE symbol = ? AND timeframe = '4h'
                   GROUP BY signal
                   ORDER BY cnt DESC""",
                (symbol,),
            )
            rows = await cursor.fetchall()
            if rows:
                sym_lines = [f"**{symbol} signal history:**"]
                for r in rows:
                    sig = r["signal"]
                    if sig == "WAIT":
                        continue
                    cnt = r["cnt"]
                    avg = r["avg_7d"]
                    avg_str = f"{avg:+.1f}%" if avg is not None else "—"
                    sym_lines.append(f"  - {sig}: {cnt}× (avg 7d: {avg_str})")
                if len(sym_lines) > 1:
                    lines.append("")
                    lines.extend(sym_lines)

        return "\n".join(lines) if len(lines) > 2 else ""

    except Exception as e:
        logger.warning("Backtest context failed: %s", e)
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# 3. Convergence-Ranked Best Setups
# ══════════════════════════════════════════════════════════════════════════════

def build_convergence_context(cache: Any) -> str:
    """Rank coins by multi-factor convergence quality.

    Convergence score = weighted sum of:
      - Signal strength (STRONG_LONG=3, LIGHT_LONG=2, ACCUMULATE=1)
      - Whale alignment (+1 if whale trend matches signal direction)
      - Anomaly boost (+1 if favorable anomaly present)
      - Conditions ratio (conditions_met / conditions_total)
      - No divergence (+0.5)
      - Floor confirmed (+0.5 for ACCUM/CAP regimes)
    """
    results = cache.get_results("4h")
    if not results:
        return ""

    _SIGNAL_SCORE = {
        "STRONG_LONG": 3.0,
        "LIGHT_LONG": 2.0,
        "ACCUMULATE": 1.5,
        "REVIVAL_SEED_CONFIRMED": 1.5,
        "REVIVAL_SEED": 1.0,
    }

    scored: List[Tuple[float, Dict]] = []
    for r in results:
        sig = r.get("signal", "WAIT")
        base_score = _SIGNAL_SCORE.get(sig, 0)
        if base_score == 0:
            continue

        # Conditions ratio
        met = r.get("conditions_met", 0)
        total = r.get("conditions_total", 10)
        cond_ratio = met / max(total, 1)

        # Whale alignment
        sm = r.get("smart_money") or {}
        whale_boost = 0
        if sm.get("trend") == "BULLISH" and sm.get("confidence", 0) >= 0.2:
            whale_boost = 1.0
        elif sm.get("trend") == "BEARISH" and sm.get("confidence", 0) >= 0.2:
            whale_boost = -0.5

        # Divergence penalty
        div_bonus = 0.5 if not r.get("divergence") else -0.5

        # Floor bonus for accumulation regimes
        floor_bonus = 0
        if r.get("floor_confirmed") and r.get("regime") in ("ACCUM", "CAP"):
            floor_bonus = 0.5

        # Anomaly boost (favorable direction)
        anom_boost = 0
        if r.get("has_anomaly"):
            sym_anomalies = [
                a for a in getattr(cache, "anomalies", [])
                if a.get("symbol") == r.get("symbol")
            ]
            for a in sym_anomalies:
                if a.get("direction") == "SHORT" and a.get("anomaly_type") == "EXTREME_FUNDING":
                    anom_boost = 0.5  # short squeeze potential
                    break

        convergence = base_score + cond_ratio + whale_boost + div_bonus + floor_bonus + anom_boost
        scored.append((convergence, r))

    if not scored:
        return ""

    scored.sort(key=lambda x: -x[0])
    top = scored[:8]

    lines = [
        "### Top Convergence Setups",
        "Ranked by multi-factor convergence (signal + whales + conditions + structure):",
    ]
    for conv_score, r in top:
        sym = r["symbol"].replace("/USDT", "")
        sig = r["signal"]
        regime = r.get("regime", "?")
        z = r.get("zscore", 0)
        heat = r.get("heat", 0)
        sm = r.get("smart_money") or {}
        whale = sm.get("trend", "—")
        whale_conf = sm.get("confidence", 0)
        met = r.get("conditions_met", 0)
        total = r.get("conditions_total", 10)
        div = r.get("divergence") or "none"

        whale_str = f"{whale} {whale_conf:.0%}" if whale != "—" else "no data"
        lines.append(
            f"- **{sym}** (conv={conv_score:.1f}): {sig} | {regime} | "
            f"z=`{z:.2f}` | heat=`{heat}` | conds={met}/{total} | "
            f"whales={whale_str} | div={div}"
        )

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Comparative Pair Analysis
# ══════════════════════════════════════════════════════════════════════════════

def build_comparison_context(cache: Any, symbols: List[str]) -> str:
    """Build a side-by-side factor breakdown for 2-4 symbols.

    Used when the user asks "compare X vs Y" or mentions multiple symbols.
    """
    if len(symbols) < 2:
        return ""

    results_4h = cache.get_results("4h")
    results_1d = cache.get_results("1d")

    lines = [f"### Comparative Analysis: {' vs '.join(s.replace('/USDT', '') for s in symbols)}"]
    lines.append("")

    factors = [
        ("Signal", "signal"),
        ("Regime", "regime"),
        ("Z-Score", "zscore"),
        ("Heat", "heat"),
        ("Confidence", "confidence"),
        ("Conditions", None),  # special handling
        ("CVD", "cvd_trend"),
        ("Divergence", "divergence"),
        ("Floor", "floor_confirmed"),
        ("Priority", "priority_score"),
    ]

    for sym in symbols[:4]:
        match_4h = next((r for r in results_4h if r.get("symbol") == sym), None)
        match_1d = next((r for r in results_1d if r.get("symbol") == sym), None)
        if not match_4h:
            continue

        base = sym.replace("/USDT", "")
        lines.append(f"**{base} (4H / 1D):**")

        for label, key in factors:
            if key is None:  # Conditions
                met4 = match_4h.get("conditions_met", 0)
                tot4 = match_4h.get("conditions_total", 10)
                if match_1d:
                    met1 = match_1d.get("conditions_met", 0)
                    tot1 = match_1d.get("conditions_total", 10)
                    lines.append(f"  - {label}: {met4}/{tot4} / {met1}/{tot1}")
                else:
                    lines.append(f"  - {label}: {met4}/{tot4} / —")
                continue

            val_4h = match_4h.get(key, "—")
            val_1d = match_1d.get(key, "—") if match_1d else "—"

            # Format numbers
            if isinstance(val_4h, float):
                val_4h = f"{val_4h:.2f}"
            if isinstance(val_1d, float):
                val_1d = f"{val_1d:.2f}"
            if val_4h is None or val_4h is False:
                val_4h = "no"
            if val_1d is None or val_1d is False:
                val_1d = "no"
            if val_4h is True:
                val_4h = "yes"
            if val_1d is True:
                val_1d = "yes"

            lines.append(f"  - {label}: `{val_4h}` / `{val_1d}`")

        # Whale data
        sm = match_4h.get("smart_money") or {}
        if sm.get("trend"):
            lines.append(
                f"  - Whales: {sm['trend']} ({sm.get('confidence', 0):.0%} conf, "
                f"L:{sm.get('long_count', 0)}/S:{sm.get('short_count', 0)})"
            )
        lines.append("")

    return "\n".join(lines) if len(lines) > 2 else ""


# ══════════════════════════════════════════════════════════════════════════════
# 5. Liquidation Pressure Context
# ══════════════════════════════════════════════════════════════════════════════

def build_liquidation_context(cache: Any, symbol: Optional[str] = None) -> str:
    """Build liquidation pressure analysis from available data.

    Uses existing CoinGlass aggregate liquidation data to identify
    which side is getting liquidated more (long vs short pressure).
    """
    results = cache.get_results("4h")
    if not results:
        return ""

    if symbol:
        # Single symbol liquidation context
        match = next((r for r in results if r.get("symbol") == symbol), None)
        if not match:
            return ""
        pos = match.get("positioning") or {}
        return _format_liq_single(match, pos)

    # Market-wide liquidation scan
    liq_data: List[Tuple[float, str, Dict]] = []
    for r in results:
        pos = r.get("positioning") or {}
        liq_24h = pos.get("liquidation_24h_usd", 0)
        if liq_24h > 0:
            liq_data.append((liq_24h, r["symbol"], pos))

    if not liq_data:
        return ""

    liq_data.sort(key=lambda x: -x[0])
    top = liq_data[:8]

    total_liq = sum(d[0] for d in liq_data)
    total_long_liq = sum(d[2].get("long_liquidation_usd_24h", 0) for d in liq_data)
    total_short_liq = sum(d[2].get("short_liquidation_usd_24h", 0) for d in liq_data)

    if total_long_liq + total_short_liq > 0:
        long_pct = total_long_liq / (total_long_liq + total_short_liq) * 100
    else:
        long_pct = 50

    if long_pct > 60:
        pressure = "LONG-HEAVY (longs getting flushed — bearish pressure)"
    elif long_pct < 40:
        pressure = "SHORT-HEAVY (shorts getting squeezed — bullish pressure)"
    else:
        pressure = "BALANCED (no clear directional flush)"

    lines = [
        "### Liquidation Pressure (24h)",
        f"Total: ${total_liq/1e6:.0f}M | "
        f"Longs: ${total_long_liq/1e6:.0f}M ({long_pct:.0f}%) | "
        f"Shorts: ${total_short_liq/1e6:.0f}M ({100-long_pct:.0f}%)",
        f"Pressure: {pressure}",
        "",
        "Top liquidation activity:",
    ]
    for liq, sym, pos in top:
        base = sym.replace("/USDT", "")
        long_liq = pos.get("long_liquidation_usd_24h", 0)
        short_liq = pos.get("short_liquidation_usd_24h", 0)
        liq_4h = pos.get("liquidation_4h_usd", 0)
        ratio = long_liq / max(short_liq, 1)

        if ratio > 2:
            side = "longs flushed"
        elif ratio < 0.5:
            side = "shorts squeezed"
        else:
            side = "mixed"

        lines.append(
            f"- **{base}**: ${liq/1e6:.1f}M total "
            f"(L:${long_liq/1e6:.1f}M / S:${short_liq/1e6:.1f}M — {side}) "
            f"| 4h: ${liq_4h/1e6:.1f}M"
        )

    return "\n".join(lines)


def _format_liq_single(match: Dict, pos: Dict) -> str:
    """Format liquidation context for a single symbol."""
    sym = match.get("symbol", "?")
    base = sym.replace("/USDT", "")
    liq_24h = pos.get("liquidation_24h_usd", 0)
    long_liq = pos.get("long_liquidation_usd_24h", 0)
    short_liq = pos.get("short_liquidation_usd_24h", 0)
    liq_4h = pos.get("liquidation_4h_usd", 0)
    liq_1h = pos.get("liquidation_1h_usd", 0)

    if liq_24h == 0:
        return ""

    ratio = long_liq / max(short_liq, 1)
    if ratio > 2:
        bias = "long-heavy (longs getting flushed — bears in control)"
    elif ratio < 0.5:
        bias = "short-heavy (shorts squeezed — potential rally fuel)"
    else:
        bias = "balanced (no clear directional flush)"

    # Acceleration: is liquidation picking up recently?
    if liq_4h > 0 and liq_24h > 0:
        accel_ratio = (liq_4h / liq_24h) * 6  # normalize to 24h equivalent
        if accel_ratio > 1.5:
            accel = "ACCELERATING (4h pace above 24h average)"
        elif accel_ratio < 0.5:
            accel = "DECELERATING (liquidations cooling off)"
        else:
            accel = "STEADY"
    else:
        accel = "N/A"

    return (
        f"### {base} Liquidation Profile\n"
        f"24h: ${liq_24h/1e6:.1f}M (L:${long_liq/1e6:.1f}M / S:${short_liq/1e6:.1f}M)\n"
        f"4h: ${liq_4h/1e6:.1f}M | 1h: ${liq_1h/1e6:.1f}M\n"
        f"Bias: {bias}\n"
        f"Pace: {accel}"
    )
