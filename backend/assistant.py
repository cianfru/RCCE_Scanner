"""
assistant.py
~~~~~~~~~~~~
LLM-powered trading assistant using Claude Haiku.

Provides natural-language signal explanations, daily briefings,
and conversational Q&A over live RCCE Scanner data.
"""

from __future__ import annotations

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

## Response Style
- Walk through which conditions pass/fail when explaining signals.
- Use the actual numbers from the data provided.
- Keep responses focused and under 300 words unless more detail is needed.
- For position sizing, suggest conservative percentages based on signal strength \
(STRONG_LONG: full size, LIGHT_LONG: 50-60%, ACCUMULATE: 25-30% DCA).
"""


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

    def build_context(
        self,
        symbol: Optional[str] = None,
        include_market: bool = True,
    ) -> str:
        """Build a compact data snapshot from the live ScanCache."""
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

        return "\n\n".join(parts)

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

        # Build context
        context = self.build_context(symbol=detected, include_market=True)

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
