"""
assistant.py
~~~~~~~~~~~~
LLM-powered trading assistant using Claude Haiku.

Provides natural-language signal explanations, daily briefings,
and conversational Q&A over live RCCE Scanner data.
"""

from __future__ import annotations

import json
import os
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        # Fallback: re-read .env with override in case shell had empty var
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            env_file = Path(__file__).resolve().parent / ".env"
            if env_file.exists():
                load_dotenv(env_file, override=True)
            key = os.environ.get("ANTHROPIC_API_KEY", "")
        except ImportError:
            pass
    return key
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_HISTORY_MESSAGES = 20

# ---------------------------------------------------------------------------
# System prompt — encodes the full RCCE decision matrix
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the RCCE Scanner trading assistant. You explain crypto trading signals \
produced by the RCCE (Regime-Cycle-Confidence-Energy) multi-engine scanner. \
Be concise, data-driven, and reference actual numbers from the provided data. \
Never give financial advice — frame everything as "the scanner indicates" or \
"the system suggests."

## The Three Engines

1. **RCCE Engine**: Z-score regime detection using 200-bar log-price deviation.
   Regimes: MARKUP (bullish trend), BLOWOFF (overextended up), REACC \
(reaccumulation dip in uptrend), MARKDOWN (bearish trend), CAP (capitulation), \
ACCUM (accumulation base).
   Key outputs: z-score (distance from mean), confidence (0-100%), \
energy (fast/slow stdev ratio), vol_state (LOW/MID/HIGH).

2. **Heatmap Engine (BMSB)**: Weekly Bull-Market Support Band deviation.
   Heat 0-100 measures overextension from the weekly EMA21/SMA20 midpoint.
   Phases: Warming, Expanding, Fading, Exhaustion.
   heat_direction: positive = above BMSB (bullish structure), \
negative = below (macro_blocked = bearish structure).

3. **Exhaustion Engine**: Detects capitulation and absorption at bottoms.
   floor_confirmed = downside support detected. is_absorption = declining \
volume on dips (institutional accumulation). is_climax = extreme volume event.

## Signal Decision Matrix

### EXIT RULES (Step 1 — highest priority, any single trigger fires):
- Heat >= 95 (BLOWOFF: 85) → TRIM (forced exit)
- BLOWOFF + z > 3.5×vol_scale → TRIM_HARD
- BLOWOFF + z > 3.0×vol_scale → TRIM
- MARKDOWN + consensus=RISK-OFF → RISK_OFF
- BEAR-DIV + confidence < 50% → NO_LONG
- EUPHORIA consensus + z > 2.0×vol_scale → NO_LONG
- MARKDOWN → WAIT
- Exhaustion climax → WAIT (entries blocked)
- Macro blocked (below BMSB): LIGHT_SHORT if conditions met, else WAIT

### ENTRY RULES (Step 2):
- **STRONG_LONG**: ALL 10 conditions met (effective >= 10 with boosts) + \
no BEAR-DIV. MARKUP also requires z between -0.5 and 1.0. \
If z > 1.0, it downgrades to LIGHT_LONG ("MARKUP extended").
- **LIGHT_LONG**: 5+ effective conditions + regime MARKUP/REACC/ACCUM:
  - MARKUP extended: z between 1.0 and 2.0×vol_scale, conf > 50%, heat < 80
  - MARKUP moderate: z between 0 and 2.0×vol_scale, conf > 50%, consensus RISK-ON/MIXED
  - REACC: z < 0.5, conf > 50%, consensus RISK-ON/MIXED, heat < 80
- **ACCUMULATE**: ACCUM + z < 0 + vol LOW + conf > 40% + F&G <= 40 (fear territory)
  OR absorption detected in ACCUM/REACC with supportive consensus
- **REVIVAL_SEED**: CAP + z < -1 + vol HIGH + conf > 30% + F&G <= 40
  (REVIVAL_SEED_CONFIRMED if floor_confirmed)
- Default: **WAIT**

### The 10 STRONG_LONG Conditions:
1. Bullish Regime: MARKUP or ACCUM
2. Confidence: > 60%
3. Consensus: RISK-ON or ACCUMULATION
4. Z-Score: -0.5 to 2.5
5. No Bear Divergence
6. Heat OK: < 85 (< 75 in BLOWOFF)
7. No Exhaustion Climax
8. Funding OK: not CROWDED_LONG
9. Not Greedy: Fear & Greed < 70
10. Liquidity OK: stablecoins not contracting

### Regime Boosts & Penalties:
- CAP/ACCUM: floor_confirmed = +2, absorption = +1 to effective conditions
- MARKUP + heat phase Fading/Exhaustion: -1 penalty

### Positioning Layer:
- Funding regimes: NEUTRAL, CROWDED_LONG (squeeze risk), CROWDED_SHORT (rally fuel)
- OI trends: STABLE, RISING, DECLINING, SQUEEZE (OI down + price up), \
LIQUIDATING (OI down + price down)

### Consensus:
- >55% MARKUP = RISK-ON, >55% BLOWOFF = EUPHORIA, >55% MARKDOWN = RISK-OFF, \
>55% ACCUM family = ACCUMULATION, else MIXED

### Divergence:
- BEAR-DIV: symbol in MARKUP/REACC while BTC in MARKDOWN
- BULL-DIV: symbol in MARKDOWN/CAP while BTC in MARKUP

## Historical Signal Log

The scanner persists every signal transition and regime change with full engine \
context snapshots. When provided, "Recent History" data shows:

- **Signal events**: transitions like WAIT→LIGHT_LONG with a classification:
  - ENTRY: non-long → long signal (new position)
  - EXIT: long → exit/wait (position closed)
  - UPGRADE: signal improved (e.g. LIGHT_LONG → STRONG_LONG)
  - DOWNGRADE: signal weakened (e.g. STRONG_LONG → LIGHT_LONG)
  - LATERAL: same-rank lateral move
  - INITIAL: first observation

- **Regime events**: structural phase transitions like MARKUP→BLOWOFF

## Metric Trends

When "Metric Trends" data is provided, it shows how key engine metrics evolved \
across recent signal events with sampled values and direction arrows:
- Heat: structural intensity (0-100), rising = overextension building
- Z-Score: deviation from mean, rising = price extending from equilibrium
- Confidence: regime conviction (0-100%), falling = weakening structure
- Energy: fast/slow volatility ratio, rising = acceleration
- Effort: directional pressure from exhaustion engine
- Deviation%: price distance from BMSB weekly band

Cross-metric patterns to watch:
- All rising together = potential blowoff / overextension risk
- Heat rising + Z falling = structural divergence
- Confidence falling + Energy rising = regime uncertainty
- Heat cooling + Confidence rising = healthy consolidation

Reference specific trend arrows (e.g. "heat: 30 → 45 → 62 → 78") when they \
add clarity. The trend data supplements the point-in-time snapshot.

Use historical events to:
- Identify momentum: multiple upgrades = strengthening, downgrades = weakening
- Spot regime rotation patterns (e.g. ACCUM→MARKUP = healthy, MARKUP→BLOWOFF = caution)
- Note how long a symbol has been in its current regime
- Reference recent signal changes when explaining current state ("recently upgraded from...")
- Warn when a symbol has been rapidly cycling between signals (instability)

## Response Style
- Walk through which conditions pass/fail when explaining signals.
- Use the actual numbers from the data provided.
- Reference recent signal/regime history when relevant to provide context.
- Keep responses focused and under 300 words unless more detail is needed.
- For position sizing, suggest conservative percentages based on signal strength \
(STRONG_LONG: full size, LIGHT_LONG: 50-60%, ACCUMULATE: 25-30% DCA).
"""


# ---------------------------------------------------------------------------
# Trend analysis helpers
# ---------------------------------------------------------------------------

def _analyze_trend(values: list, label: str) -> Optional[str]:
    """Produce a one-line trend summary.

    Example output: 'Heat: 30 → 45 → 62 → 78 (↑ rising sharply, Δ+48.0)'
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return None

    first, last = clean[0], clean[-1]
    delta = last - first

    # Direction
    threshold = 0.05 * (abs(first) + 1)
    if abs(delta) < threshold:
        direction = "stable"
    elif delta > 0:
        direction = "rising"
    else:
        direction = "falling"

    # Rate: compare first half vs second half
    mid = len(clean) // 2
    avg1 = sum(clean[:mid]) / mid
    avg2 = sum(clean[mid:]) / (len(clean) - mid)
    rng = max(clean) - min(clean)

    if direction != "stable" and rng > 0:
        half_delta = abs(avg2 - avg1)
        if half_delta / rng > 0.5:
            rate = "sharply"
        elif half_delta / rng > 0.25:
            rate = "steadily"
        else:
            rate = "gradually"
    else:
        rate = ""

    # Sample 4-5 points for arrow sequence
    step = max(1, len(clean) // 4)
    sampled = [clean[i] for i in range(0, len(clean), step)]
    if clean[-1] not in sampled:
        sampled.append(clean[-1])

    def _fmt(v):
        if abs(v) >= 10:
            return f"{v:.0f}"
        if abs(v) >= 1:
            return f"{v:.1f}"
        return f"{v:.2f}"

    arrow_str = " → ".join(_fmt(v) for v in sampled)
    arrows = {"rising": "↑", "falling": "↓", "stable": "~"}
    return f"{label}: {arrow_str} ({arrows[direction]} {rate} {direction}, Δ{delta:+.1f})"


def _format_age_span(seconds: int) -> str:
    """Format a duration span as 'over N days/hours'."""
    if seconds < 3600:
        return f"over {seconds // 60}m"
    if seconds < 86400:
        return f"over {seconds // 3600}h"
    return f"over {seconds // 86400}d"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str


@dataclass
class ChatSession:
    session_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Assistant manager
# ---------------------------------------------------------------------------

class AssistantManager:
    """Manages chat sessions and Anthropic API calls."""

    def __init__(self):
        self.sessions: Dict[str, ChatSession] = {}
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=_get_api_key())
        return self._client

    def get_or_create_session(self, session_id: str) -> ChatSession:
        if session_id not in self.sessions:
            self.sessions[session_id] = ChatSession(session_id=session_id)
        return self.sessions[session_id]

    # -- Context builder ---------------------------------------------------

    async def build_context(
        self,
        symbol: Optional[str] = None,
        include_market: bool = True,
    ) -> str:
        """Build a compact data snapshot from live ScanCache + signal log history."""
        from scanner import cache

        parts: List[str] = []

        # Market overview
        if include_market:
            c4 = cache.consensus.get("4h", {})
            c1 = cache.consensus.get("1d", {})
            sent = cache.sentiment or {}
            stbl = cache.stablecoin or {}
            alt4 = cache.alt_season.get("4h", {})
            gm = cache.global_metrics or {}

            parts.append(
                f"## Market Overview\n"
                f"Consensus 4H: {c4.get('consensus', 'N/A')} "
                f"(strength {c4.get('strength', 0):.0f}%)\n"
                f"Consensus 1D: {c1.get('consensus', 'N/A')} "
                f"(strength {c1.get('strength', 0):.0f}%)\n"
                f"Fear & Greed: {sent.get('fear_greed_value', 'N/A')} "
                f"({sent.get('fear_greed_label', 'N/A')})\n"
                f"BTC Dominance: {gm.get('btc_dominance', 'N/A')}%\n"
                f"Stablecoin trend: {stbl.get('trend', 'N/A')} "
                f"(7d: {stbl.get('change_7d_pct', 0):+.1f}%)\n"
                f"Alt-season: {alt4.get('label', 'N/A')} "
                f"(score {alt4.get('score', 0):.0f})"
            )

        # Symbol-specific data
        if symbol:
            for tf in ("4h", "1d"):
                results = cache.get_results(tf)
                match = next(
                    (r for r in results if r.get("symbol") == symbol), None
                )
                if not match:
                    continue

                conds = match.get("conditions_detail", [])
                cond_lines = "\n".join(
                    f"  {'PASS' if c['met'] else 'FAIL'}: "
                    f"{c['label']} — {c['desc']}"
                    for c in conds
                )
                pos = match.get("positioning") or {}
                conf = match.get("confluence") or {}

                parts.append(
                    f"## {symbol} ({tf.upper()})\n"
                    f"Price: ${match.get('price', 0):.6g}\n"
                    f"Regime: {match.get('regime', '?')} | "
                    f"Confidence: {match.get('confidence', 0):.0f}%\n"
                    f"Signal: {match.get('signal', '?')} | "
                    f"Raw: {match.get('raw_signal', '?')}\n"
                    f"Reason: {match.get('signal_reason', '')}\n"
                    f"Warnings: {'; '.join(match.get('signal_warnings', [])) or 'none'}\n"
                    f"Z-score: {match.get('zscore', 0):.3f} | "
                    f"Energy: {match.get('energy', 0):.3f} | "
                    f"Vol: {match.get('vol_state', '?')}\n"
                    f"Heat: {match.get('heat', 0)}/100 | "
                    f"Phase: {match.get('heat_phase', '?')} | "
                    f"Direction: {match.get('heat_direction', 0)}\n"
                    f"Deviation: {match.get('deviation_pct', 0):.2f}% | "
                    f"ATR: {match.get('atr_regime', '?')}\n"
                    f"Exhaustion: {match.get('exhaustion_state', '?')} | "
                    f"Floor: {match.get('floor_confirmed', False)} | "
                    f"Absorption: {match.get('is_absorption', False)} | "
                    f"Climax: {match.get('is_climax', False)}\n"
                    f"Divergence: {match.get('divergence') or 'none'}\n"
                    f"Conditions: {match.get('conditions_met', 0)}/"
                    f"{match.get('conditions_total', 10)} "
                    f"(effective: {match.get('effective_conditions', 'N/A')})\n"
                    f"{cond_lines}\n"
                    f"Funding: {pos.get('funding_regime', 'N/A')} | "
                    f"OI: {pos.get('oi_trend', 'N/A')}\n"
                    f"Confluence: {conf.get('label', 'N/A')} "
                    f"(score {conf.get('score', 0)})\n"
                    f"Priority: {match.get('priority_score', 0):.1f}"
                )
        else:
            # No symbol: show active signals summary
            for tf in ("4h",):
                results = cache.get_results(tf)
                active = [
                    r for r in results
                    if r.get("signal") not in ("WAIT", None)
                ]
                if active:
                    lines = [f"## Active Signals ({tf.upper()})"]
                    for r in sorted(
                        active,
                        key=lambda x: x.get("priority_score", 0),
                        reverse=True,
                    )[:15]:
                        lines.append(
                            f"- {r['symbol']}: {r['signal']} "
                            f"({r['regime']}, z={r.get('zscore', 0):.2f}, "
                            f"heat={r.get('heat', 0)}, "
                            f"cond={r.get('conditions_met', 0)}/"
                            f"{r.get('conditions_total', 10)})"
                        )
                    parts.append("\n".join(lines))

                # Also list WAIT symbols count
                wait_count = len(results) - len(active)
                if wait_count > 0:
                    parts.append(f"({wait_count} symbols on WAIT)")

        # -- Historical signal log context ----------------------------------
        history_section = await self._build_history_context(symbol)
        if history_section:
            parts.append(history_section)

        return "\n\n".join(parts)

    async def _build_trend_summary(
        self,
        symbol: str,
    ) -> Optional[str]:
        """Analyze metric trajectories and generate narrative summary."""
        try:
            from signal_log import SignalLog
            slog = SignalLog.get()
            if slog._db is None:
                return None
        except Exception:
            return None

        events = await slog.get_metric_series(symbol, "4h", limit=20)
        if len(events) < 3:
            return None

        # Extract metric sequences
        heats = [e["heat"] for e in events]
        zscores = [e["zscore"] for e in events]
        confs = [e["confidence"] for e in events]
        energies = [e["energy"] for e in events]
        efforts = [e["effort"] for e in events]
        devs = [e["deviation_pct"] for e in events]

        lines: List[str] = [f"## Metric Trends — {symbol}"]

        # Individual metric trends with direction tracking
        trends: Dict[str, str] = {}
        for values, label, key in [
            (heats, "Heat", "heat"),
            (zscores, "Z-Score", "zscore"),
            (confs, "Confidence", "confidence"),
            (energies, "Energy", "energy"),
            (efforts, "Effort", "effort"),
            (devs, "Deviation%", "deviation"),
        ]:
            result = _analyze_trend(values, label)
            if result:
                lines.append(f"- {result}")
                # Track direction for cross-metric patterns
                clean = [v for v in values if v is not None]
                if len(clean) >= 3:
                    d = clean[-1] - clean[0]
                    th = 0.05 * (abs(clean[0]) + 1)
                    trends[key] = (
                        "rising" if d > th
                        else "falling" if d < -th
                        else "stable"
                    )

        # Time span context
        if len(events) >= 2:
            span = events[-1]["timestamp"] - events[0]["timestamp"]
            lines.append(
                f"- Span: {len(events)} events {_format_age_span(span)}"
            )

        # Cross-metric pattern detection
        patterns: List[str] = []
        h = trends.get("heat")
        z = trends.get("zscore")
        c = trends.get("confidence")
        e = trends.get("energy")

        if h == "rising" and z == "rising" and c == "rising":
            patterns.append(
                "Heat + Z-Score + Confidence all rising "
                "→ acceleration, watch for overextension"
            )
        if h == "rising" and z == "falling":
            patterns.append(
                "Heat rising while Z-Score falling "
                "→ possible structural divergence"
            )
        if c == "falling" and e == "rising":
            patterns.append(
                "Confidence declining + Energy rising "
                "→ regime uncertainty, volatility increasing"
            )
        if h == "falling" and c == "rising":
            patterns.append(
                "Heat cooling + Confidence rising "
                "→ healthy consolidation"
            )
        if h == "rising" and z == "rising" and c == "falling":
            patterns.append(
                "Heat & Z rising but Confidence falling "
                "→ stretched move losing conviction"
            )
        if all(d == "stable" for d in [h, z, c] if d):
            patterns.append(
                "All metrics stable → range-bound, waiting for catalyst"
            )

        if patterns:
            lines.append("Patterns:")
            for p in patterns:
                lines.append(f"  → {p}")

        return "\n".join(lines)

    async def _build_history_context(
        self,
        symbol: Optional[str] = None,
    ) -> Optional[str]:
        """Query signal log for recent signal + regime events and format as text."""
        try:
            from signal_log import SignalLog
            slog = SignalLog.get()
            if slog._db is None:
                return None
        except Exception:
            return None

        lines: List[str] = []

        if symbol:
            # Trend summary first (prepended before raw events)
            trend = await self._build_trend_summary(symbol)
            if trend:
                lines.append(trend)

            # Symbol-specific: recent timeline events (signals + regimes)
            events = await slog.get_timeline(
                timeframe="4h", symbol=symbol, limit=30
            )
            if events:
                lines.append(
                    f"## Recent History — {symbol} ({len(events)} events)"
                )
                for ev in events[:15]:
                    ts = ev.get("timestamp", 0)
                    age = self._format_age(ts)
                    etype = ev.get("event_type", "?")
                    label = ev.get("label", "?")
                    prev = ev.get("prev_label")
                    price = ev.get("price", 0)
                    z = ev.get("zscore")
                    conf = ev.get("confidence")

                    if etype == "signal":
                        tt = ev.get("transition_type", "")
                        arrow = f"{prev} → " if prev else ""
                        z_str = f", z={z:.2f}" if z is not None else ""
                        c_str = (
                            f", conf={conf:.0f}%"
                            if conf is not None else ""
                        )
                        lines.append(
                            f"- [{age}] SIG {tt}: {arrow}{label} "
                            f"@ ${price:.6g}{z_str}{c_str}"
                        )
                    else:  # regime
                        arrow = f"{prev} → " if prev else ""
                        e_str = ""
                        ctx_str = ev.get("context")
                        if ctx_str:
                            try:
                                ctx = json.loads(ctx_str)
                                energy = ctx.get("rcce", {}).get("energy")
                                if energy is not None:
                                    e_str = f", energy={energy:.3f}"
                            except Exception:
                                pass
                        c_str = (
                            f", conf={conf:.0f}%"
                            if conf is not None else ""
                        )
                        lines.append(
                            f"- [{age}] REG: {arrow}{label} "
                            f"@ ${price:.6g}{c_str}{e_str}"
                        )
        else:
            # No symbol: show recent signal changes across all assets
            recent = await slog.get_recent_changes(timeframe="4h", limit=20)
            if recent:
                lines.append("## Recent Signal Changes (4H)")
                for ev in recent:
                    ts = ev.get("timestamp", 0)
                    age = self._format_age(ts)
                    sym = ev.get("symbol", "?")
                    sig = ev.get("signal", "?")
                    prev = ev.get("prev_signal")
                    tt = ev.get("transition_type", "")
                    regime = ev.get("regime", "?")
                    price = ev.get("price", 0)

                    arrow = f"{prev} → " if prev else ""
                    lines.append(
                        f"- [{age}] {sym}: {tt} {arrow}{sig} "
                        f"({regime}) @ ${price:.6g}"
                    )

        return "\n".join(lines) if lines else None

    @staticmethod
    def _format_age(timestamp: int) -> str:
        """Format a timestamp as relative age (e.g. '2h ago', '3d ago')."""
        delta = int(time.time()) - timestamp
        if delta < 60:
            return "just now"
        if delta < 3600:
            return f"{delta // 60}m ago"
        if delta < 86400:
            h = delta // 3600
            return f"{h}h ago"
        d = delta // 86400
        return f"{d}d ago"

    # -- Symbol detection --------------------------------------------------

    def _detect_symbol(self, text: str) -> Optional[str]:
        """Extract a symbol from user text, e.g. 'why is HYPE light long?' -> 'HYPE/USDT'."""
        from scanner import cache

        text_upper = text.upper()
        best_match = None
        best_len = 0

        for tf_key, tf_results in cache.results.items():
            for r in tf_results:
                sym = r.get("symbol", "")
                base = sym.split("/")[0]
                # Match longest base symbol to avoid "BTC" matching inside "ABTC"
                if base in text_upper and len(base) > best_len:
                    best_match = sym
                    best_len = len(base)

        return best_match

    # -- Chat --------------------------------------------------------------

    async def chat(
        self,
        session_id: str,
        user_message: str,
        symbol: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """Process a user message and return (reply, detected_symbol)."""
        session = self.get_or_create_session(session_id)

        # Detect symbol from message if not provided
        detected = symbol
        if not detected:
            detected = self._detect_symbol(user_message)

        # Normalize symbol format
        if detected and "/" not in detected:
            detected = f"{detected}/USDT"

        # Build context (async — queries signal log history)
        context = await self.build_context(symbol=detected, include_market=True)

        # Append user message
        session.messages.append(ChatMessage(role="user", content=user_message))

        # Trim to sliding window
        if len(session.messages) > MAX_HISTORY_MESSAGES:
            session.messages = session.messages[-MAX_HISTORY_MESSAGES:]

        # Build API messages
        messages = [
            {"role": m.role, "content": m.content}
            for m in session.messages
        ]

        # System prompt + live data context
        system = SYSTEM_PROMPT + "\n\n## Current Scanner Data\n\n" + context

        client = self._get_client()
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1024,
            system=system,
            messages=messages,
        )

        reply = response.content[0].text
        session.messages.append(ChatMessage(role="assistant", content=reply))

        return reply, detected

    # -- Convenience methods -----------------------------------------------

    async def daily_briefing(self) -> str:
        """Generate a daily market briefing."""
        reply, _ = await self.chat(
            session_id=f"briefing-{int(time.time())}",
            user_message=(
                "Give me a daily market briefing. Cover: overall market consensus, "
                "Fear & Greed level, any active entry/exit signals with their reasons, "
                "and key risk warnings. Be structured and concise."
            ),
        )
        return reply

    async def explain_signal(self, symbol: str, timeframe: str = "4h") -> str:
        """Explain the current signal for a specific symbol."""
        if "/" not in symbol:
            symbol = f"{symbol}/USDT"

        reply, _ = await self.chat(
            session_id=f"explain-{symbol}-{int(time.time())}",
            user_message=(
                f"Explain why {symbol} has its current signal on the {timeframe} "
                f"timeframe. Walk through each of the 10 conditions, explain which "
                f"pass and fail, and explain the specific reason the signal is what "
                f"it is (not a higher or lower signal). Be precise with numbers."
            ),
            symbol=symbol,
        )
        return reply


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[AssistantManager] = None


def get_assistant() -> AssistantManager:
    global _manager
    if _manager is None:
        _manager = AssistantManager()
    return _manager
