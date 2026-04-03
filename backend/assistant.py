"""
assistant.py
~~~~~~~~~~~~
LLM-powered trading assistant with OpenRouter multi-model support.

Provides natural-language signal explanations, daily briefings,
and conversational Q&A over live RCCE Scanner data.
Supports model switching via OpenRouter (Claude, GPT, Gemini, DeepSeek, etc.)
with automatic fallback to direct Anthropic API.
"""

from __future__ import annotations

import json
import os
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from engines.positioning_engine import interpret_oi_context

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model catalogue & provider config
# ---------------------------------------------------------------------------

DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3.5-haiku")
ANTHROPIC_FALLBACK_MODEL = "claude-haiku-4-5-20251001"
MAX_HISTORY_MESSAGES = 20

# Minimum context window to include a model (filters out tiny/toy models)
_MIN_CONTEXT_LENGTH = 16_000

# Cache for dynamically fetched OpenRouter models
_openrouter_models_cache: Optional[list] = None
_openrouter_models_fetched_at: float = 0
_MODELS_CACHE_TTL = 3600  # re-fetch every hour


async def _fetch_openrouter_models() -> list:
    """Fetch all available models from OpenRouter API, cached for 1 hour."""
    global _openrouter_models_cache, _openrouter_models_fetched_at

    now = time.time()
    if _openrouter_models_cache is not None and (now - _openrouter_models_fetched_at) < _MODELS_CACHE_TTL:
        return _openrouter_models_cache

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("https://openrouter.ai/api/v1/models", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning("OpenRouter models API returned %d", resp.status)
                    return _openrouter_models_cache or []
                data = await resp.json()
    except Exception as e:
        logger.warning("Failed to fetch OpenRouter models: %s", e)
        return _openrouter_models_cache or []

    models = []
    for m in data.get("data", []):
        model_id = m.get("id", "")
        name = m.get("name", model_id)
        ctx = m.get("context_length", 0)

        # Skip models with tiny context (can't fit our system prompt + data)
        if ctx < _MIN_CONTEXT_LENGTH:
            continue

        # Derive provider from model ID (e.g. "anthropic/claude-3.5-haiku" -> "Anthropic")
        provider = model_id.split("/")[0].title() if "/" in model_id else "Unknown"

        models.append({
            "id": model_id,
            "label": name,
            "provider": provider,
            "context_length": ctx,
        })

    # Sort: by provider name, then by model name
    models.sort(key=lambda m: (m["provider"].lower(), m["label"].lower()))

    _openrouter_models_cache = models
    _openrouter_models_fetched_at = now
    logger.info("Fetched %d models from OpenRouter (filtered from %d)", len(models), len(data.get("data", [])))
    return models


def _load_env():
    """Ensure .env is loaded (idempotent)."""
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        env_file = Path(__file__).resolve().parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)
    except ImportError:
        pass


def _get_provider_config() -> Tuple[str, Optional[str], str]:
    """Return (api_key, base_url, mode) for the active LLM provider.

    Prefers OpenRouter; falls back to direct Anthropic SDK.
    """
    # Try OpenRouter first
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not or_key:
        _load_env()
        or_key = os.environ.get("OPENROUTER_API_KEY", "")

    if or_key:
        return or_key, "https://openrouter.ai/api/v1", "openrouter"

    # Fallback: direct Anthropic
    ant_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not ant_key:
        _load_env()
        ant_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if ant_key:
        return ant_key, None, "anthropic"

    raise RuntimeError(
        "No LLM API key found. Set OPENROUTER_API_KEY or ANTHROPIC_API_KEY in .env"
    )

# ---------------------------------------------------------------------------
# System prompt — encodes the full RCCE decision matrix
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the RCCE Scanner trading assistant. You explain crypto trading signals \
produced by the RCCE (Regime-Cycle-Confidence-Energy) multi-engine scanner. \
Be concise, data-driven, and reference actual numbers from the provided data. \
Never give financial advice — frame everything as "the scanner indicates" or \
"the system suggests."

## Market Reference
- **BTC is the primary market anchor** — always reference BTC's regime, signal, \
and z-score when discussing general market conditions. ETH and SOL are secondary anchors.
- For market-wide analysis, frame the narrative around BTC's position first, \
then discuss how altcoins are behaving relative to BTC.
- **HyperLens data** shows what 500 tracked smart-money wallets on HyperLiquid \
are doing. When whale consensus diverges from scanner signals, flag it — this is \
high-value alpha. Whale trend BULLISH + scanner WAIT = potential early accumulation. \
Whale BEARISH + scanner LONG = caution, smart money exiting.

## Formatting Rules
- Keep responses SHORT — 3-8 bullet points max for most answers.
- Use **bold** for key values and signals, `code` for numbers and metrics.
- For comparisons, use bullet lists with bold labels — NOT markdown tables. \
Tables render poorly on mobile. Instead of a table, use a compact list like:
  - **BTC**: MARKUP, z=`1.2`, conf=`78%`, STRONG_LONG
  - **ETH**: REACC, z=`0.4`, conf=`65%`, LIGHT_LONG
- Never repeat the full signal matrix back to the user — they already know it.
- Prioritize actionable insight over exhaustive data dumps.

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
- **STRONG_LONG**: >= 75% weighted score + no BEAR-DIV. MARKUP also requires \
z between -0.5 and 1.0. If z > 1.0, it downgrades to LIGHT_LONG ("MARKUP extended").
- **LIGHT_LONG**: >= 40% weighted score + regime MARKUP/REACC/ACCUM:
  - MARKUP extended: z between 1.0 and 2.0×vol_scale, conf > 50%, heat < 80
  - MARKUP moderate: z between 0 and 2.0×vol_scale, conf > 50%, consensus RISK-ON/MIXED
  - REACC: z < 0.5, conf > 50%, consensus RISK-ON/MIXED, heat < 80
- **ACCUMULATE**: ACCUM + z < 0 + vol LOW + conf > 40% + F&G <= 40 (fear territory)
  OR absorption detected in ACCUM/REACC with supportive consensus
- **REVIVAL_SEED**: CAP + z < -1 + vol HIGH + conf > 30% + F&G <= 40
  (REVIVAL_SEED_CONFIRMED if floor_confirmed)
- Default: **WAIT**

### The 14 Weighted Conditions (STRONG_LONG requires >= 75% weighted score):

**Core Conditions (weight 1.0 each, max 10 pts):**
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

**CoinGlass Conditions (weight 0.75 each, max 3 pts — CEX coins only):**
11. OI Confirms: OI trend aligns with signal direction (BUILDING/STABLE for longs)
12. CVD Confirms: taker buy volume dominant (cvd_trend == BULLISH)
13. Smart Money Aligned: top trader LSR >= 0.85 (pros not heavily short)
14. Macro Tailwind: ETF 7d net inflow > 0 OR Coinbase premium > 0

**Scoring**: Total max is 13.0 for CEX coins, 10.0 for HL-native tokens. \
STRONG_LONG requires >= 75% of weighted max. LIGHT_LONG requires >= 40%. \
HL-native tokens (not on CoinGlass) are scored out of 10 only — the 4 \
CoinGlass conditions are excluded entirely, not penalized.

### Regime Boosts & Penalties:
- CAP/ACCUM: floor_confirmed = +2, absorption = +1 to effective weighted score
- MARKUP + heat phase Fading/Exhaustion: -1 penalty

### CoinGlass Data Layer:
- **CVD (Cumulative Volume Delta)**: net taker buy minus sell volume. \
BULLISH = buy pressure dominant. BEARISH = distribution. UNAVAILABLE = fetch failed.
- **Spot Dominance**: SPOT_LED = organic demand (spot > futures taker volume). \
FUTURES_LED = speculative/leverage driven.
- **Smart Money LSR**: top-trader long/short ratio. < 0.85 = pros skewing short \
(condition #13 fails). < 0.7 = extreme short bias (hard downgrade modifier). \
> 1.5 = pros heavily long (reinforcement).
- **Macro**: ETF 7-day flows + Coinbase premium rate. Positive = institutional demand.

### Post-Condition CVD Modifiers:
After conditions are scored, these combo modifiers can upgrade/downgrade signals:
- CVD BULLISH + SPOT_LED: ACCUMULATE → LIGHT_LONG; LIGHT_LONG → STRONG_LONG
- CVD BULLISH + crowded shorts (LSR < 0.85): WAIT → ACCUMULATE
- CVD BEARISH divergence: STRONG_LONG → TRIM; LIGHT_LONG → WAIT
- Liq washout ($50M+) + CVD BULLISH: WAIT → ACCUMULATE
- Smart Money LSR < 0.7: hard downgrade one step

### Positioning Layer:
- Funding regimes: NEUTRAL, CROWDED_LONG (squeeze risk), CROWDED_SHORT (rally fuel)
- OI trends: STABLE, BUILDING (new longs), SQUEEZE (OI down + price up), \
LIQUIDATING (OI down + price down), SHORTING (OI up + price down)

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

## HyperLens Smart Money Intelligence

HyperLens tracks ~500 elite wallets on HyperLiquid across two cohorts:
- **Money Printers**: top 300 by ROI (skill-based, >= 30% ROI)
- **Smart Money**: top 300 by account value (conviction-based, >= $1M AV)
- **Elite**: wallets in both cohorts

Per-symbol consensus shows:
- trend (BULLISH/BEARISH/NEUTRAL), confidence (0-100%)
- long_count / short_count (wallet positions)
- long_notional / short_notional (USD exposure)
- net_ratio (-1 to +1, positive = net long)

Key patterns:
- Whale BULLISH with high confidence (>40%) = strong smart-money conviction
- Whale BEARISH while scanner shows entry signal = divergence, proceed with caution
- High short_notional from few wallets = concentrated whale shorts (may know something)
- net_ratio near 0 = no consensus, mixed positioning

## User Positions (Hyperliquid)

When position data is provided, you are aware of the user's actual live trades.
Use this to give **personalized, actionable context**:

- State each position clearly: coin, side (LONG/SHORT), size, entry price,
  current PnL, leverage, and liquidation price.
- Cross-reference each position against the scanner data:
  - Is the position aligned with the current signal? (e.g. LONG + STRONG_LONG = good)
  - Is the position fighting the regime? (e.g. LONG + MARKDOWN = concerning)
  - Is heat building toward a trim zone? Warn proactively.
  - Is there a divergence (BEAR-DIV/BULL-DIV) on their held coin?
- Calculate approximate PnL % from entry: ((current_price - entry) / entry) * 100
  for longs, inverse for shorts.
- Flag liquidation risk: if current price is within 15% of liq price, warn clearly.
- When the user asks "how are my positions" or similar, give a structured breakdown
  of every open position with scanner context for each.
- Suggest specific actions per position based on scanner signals:
  - TRIM/TRIM_HARD signal on held coin → suggest partial or full exit
  - STRONG_LONG on held coin → hold or add
  - RISK_OFF → suggest reducing exposure
  - Heat > 80 on held coin → warn about overextension

## Anomaly Detection

The scanner runs a statistical anomaly detector that flags unusual activity:
- **EXTREME_FUNDING**: funding rate far outside normal range (e.g. -400% annualized)
- **OI_SURGE**: open interest spiking or crashing abnormally (rolling ~2h window, updates every 5 min)
- **VOLUME_SPIKE**: trading volume multiples above normal
- **LSR_EXTREME**: long/short ratio extremely one-sided (crowd positioning)
- **CVD_EXTREME**: taker buy/sell ratio far from balanced

Each anomaly has:
- **severity**: critical or high
- **direction**: LONG or SHORT (which side is anomalous)
- **z-score**: how many standard deviations from the cross-market norm
- **exchanges_confirmed**: when both HL and Binance confirm, it's higher conviction
- **context**: human-readable explanation

When anomalies are present in the data:
- Always mention them prominently — anomalies are actionable intelligence
- Extreme SHORT funding = squeeze potential (shorts paying unsustainable rates)
- Extreme LONG funding = overheated, caution on new entries
- OI surge + price move = real momentum. OI surge without price = leverage trap
- Cross-exchange confirmed anomalies (HL+BN) are more reliable than single-exchange

## Response Style
- Walk through which conditions pass/fail when explaining signals.
- Use the actual numbers from the data provided.
- Reference recent signal/regime history when relevant to provide context.
- Keep responses focused and under 300 words unless more detail is needed.
- For position sizing, suggest conservative percentages based on signal strength \
(STRONG_LONG: full size, LIGHT_LONG: 50-60%, ACCUMULATE: 25-30% DCA).
- When positions are available, always contextualize advice relative to held positions.
- **NEVER mention ARK unless the user explicitly asks about it.** ARK is in the \
watchlist for tracking only — do not include it in summaries, top picks, or examples.
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
    """Manages chat sessions and LLM API calls (OpenRouter or Anthropic)."""

    def __init__(self):
        self.sessions: Dict[str, ChatSession] = {}
        self._client = None
        self._mode: Optional[str] = None  # "openrouter" or "anthropic"
        self._current_model: str = DEFAULT_MODEL

    def _get_client(self):
        if self._client is None:
            api_key, base_url, mode = _get_provider_config()
            self._mode = mode
            if mode == "openrouter":
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    default_headers={
                        "HTTP-Referer": "https://rcce-scanner.local",
                        "X-Title": "RCCE Scanner",
                    },
                )
                logger.info("LLM provider: OpenRouter (model=%s)", self._current_model)
            else:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=api_key)
                logger.info("LLM provider: Anthropic direct (model=%s)", ANTHROPIC_FALLBACK_MODEL)
        return self._client

    # -- Model management ---------------------------------------------------

    def get_current_model(self) -> str:
        """Return the active model ID."""
        if self._mode == "anthropic":
            return ANTHROPIC_FALLBACK_MODEL
        return self._current_model

    def set_model(self, model_id: str) -> bool:
        """Switch to a different model. Accepts any OpenRouter model ID."""
        if not model_id or not isinstance(model_id, str):
            return False
        self._current_model = model_id
        logger.info("Model switched to: %s", model_id)
        return True

    async def get_available_models(self) -> list:
        """Return the full OpenRouter model catalogue (cached)."""
        return await _fetch_openrouter_models()

    def get_mode(self) -> str:
        """Return current provider mode, initialising client if needed."""
        self._get_client()
        return self._mode or "unknown"

    def get_or_create_session(self, session_id: str) -> ChatSession:
        if session_id not in self.sessions:
            self.sessions[session_id] = ChatSession(session_id=session_id)
        return self.sessions[session_id]

    # -- Context builder ---------------------------------------------------

    async def build_context(
        self,
        symbol: Optional[str] = None,
        include_market: bool = True,
        wallet_address: Optional[str] = None,
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

            # Always include BTC + ETH + SOL as market anchors
            results_1d = cache.get_results("1d")
            for anchor_sym in ("BTC/USDT", "ETH/USDT", "SOL/USDT"):
                anchor = next((r for r in results_1d if r.get("symbol") == anchor_sym), None)
                if anchor:
                    sm = anchor.get("smart_money") or {}
                    sm_line = ""
                    if sm.get("trend"):
                        sm_line = (
                            f"Whale Consensus: {sm['trend']} "
                            f"({sm.get('confidence', 0):.0%} conf, "
                            f"L:{sm.get('long_count', 0)}/S:{sm.get('short_count', 0)})\n"
                        )
                    parts.append(
                        f"### {anchor_sym.replace('/USDT', '')} (1D anchor)\n"
                        f"Price: ${anchor.get('price', 0):.6g} | "
                        f"Regime: {anchor.get('regime', '?')} | "
                        f"Signal: {anchor.get('signal', '?')}\n"
                        f"Z-score: {anchor.get('zscore', 0):.3f} | "
                        f"Heat: {anchor.get('heat', 0)}/100 | "
                        f"Conditions: {anchor.get('conditions_met', 0)}/{anchor.get('conditions_total', 10)}\n"
                        f"CVD: {anchor.get('cvd_trend', 'N/A')} | "
                        f"Divergence: {anchor.get('divergence') or 'none'}\n"
                        f"{sm_line}"
                        f"Reason: {anchor.get('signal_reason', '')}"
                    )

            # HyperLens whale consensus summary (top movers)
            try:
                from hl_intelligence import get_all_consensus as _hl_all
                hl_consensus = _hl_all()
                if hl_consensus:
                    # Sort by confidence, show top bullish and bearish
                    bullish = sorted(
                        [c for c in hl_consensus.values() if c.trend == "BULLISH" and c.confidence >= 0.20],
                        key=lambda c: c.confidence, reverse=True
                    )[:5]
                    bearish = sorted(
                        [c for c in hl_consensus.values() if c.trend == "BEARISH" and c.confidence >= 0.20],
                        key=lambda c: c.confidence, reverse=True
                    )[:5]
                    hl_lines = ["## HyperLens Whale Consensus (500 tracked wallets)"]
                    if bullish:
                        hl_lines.append("Bullish:")
                        for c in bullish:
                            hl_lines.append(
                                f"  - {c.symbol}: {c.confidence:.0%} conf, "
                                f"L:{c.long_count}/S:{c.short_count}, "
                                f"ratio={c.net_ratio:+.2f}"
                            )
                    if bearish:
                        hl_lines.append("Bearish:")
                        for c in bearish:
                            hl_lines.append(
                                f"  - {c.symbol}: {c.confidence:.0%} conf, "
                                f"L:{c.long_count}/S:{c.short_count}, "
                                f"ratio={c.net_ratio:+.2f}"
                            )
                    if not bullish and not bearish:
                        hl_lines.append("No strong whale consensus (all < 20% confidence)")
                    parts.append("\n".join(hl_lines))
            except Exception:
                pass

            # Active anomalies (statistical outliers across all coins)
            active_anomalies = getattr(cache, "anomalies", [])
            if active_anomalies:
                anom_lines = ["## Active Anomalies (unusual activity detected)"]
                for a in active_anomalies[:10]:  # cap at 10 for context window
                    coin = a.get("symbol", "?").replace("/USDT", "")
                    atype = a.get("anomaly_type", "?")
                    sev = a.get("severity", "?")
                    ctx = a.get("context", "")
                    exchanges = a.get("exchanges_confirmed", [])
                    ex_str = f" [{'+'.join(e[:2].upper() for e in exchanges)}]" if len(exchanges) >= 2 else ""
                    anom_lines.append(f"  - {coin}: {atype} ({sev}){ex_str} — {ctx}")
                parts.append("\n".join(anom_lines))

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
                core_conds = [c for c in conds if c.get("group") != "coinglass"]
                cg_conds = [c for c in conds if c.get("group") == "coinglass"]
                core_lines = "\n".join(
                    f"  {'PASS' if c['met'] else 'FAIL'}: "
                    f"{c['label']} — {c['desc']}"
                    for c in core_conds
                )
                cg_lines = "\n".join(
                    f"  {'PASS' if c['met'] else 'FAIL'}: "
                    f"{c['label']} — {c['desc']}"
                    for c in cg_conds
                ) if cg_conds else ""
                pos = match.get("positioning") or {}
                conf = match.get("confluence") or {}

                cond_section = f"Core Conditions ({sum(1 for c in core_conds if c['met'])}/{len(core_conds)}):\n{core_lines}"
                if cg_lines:
                    cond_section += f"\nCoinGlass Conditions ({sum(1 for c in cg_conds if c['met'])}/{len(cg_conds)}):\n{cg_lines}"

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
                    f"{cond_section}\n"
                    f"Funding: {pos.get('funding_regime', 'N/A')} | "
                    f"OI: {pos.get('oi_trend', 'N/A')} | "
                    f"OI Change: {pos.get('oi_change_pct', 0):.2f}% | "
                    f"OI Context: {interpret_oi_context(pos.get('oi_trend', 'STABLE'), match.get('signal', 'WAIT')) or 'n/a'}\n"
                    f"CVD: {match.get('cvd_trend', 'N/A')} | "
                    f"BSR: {match.get('buy_sell_ratio', 'N/A')} | "
                    f"Divergence: {match.get('cvd_divergence', False)}\n"
                    f"Spot Dominance: {pos.get('spot_dominance', 'N/A')} | "
                    f"Smart Money LSR: {pos.get('top_trader_lsr', 'N/A')} | "
                    f"Retail LSR: {pos.get('long_short_ratio', 'N/A')}\n"
                    f"Liq 24H: ${pos.get('liquidation_24h_usd', 0)/1e6:.1f}M | "
                    f"Liq 4H: ${pos.get('liquidation_4h_usd', 0)/1e6:.1f}M\n"
                    f"Confluence: {conf.get('label', 'N/A')} "
                    f"(score {conf.get('score', 0)})\n"
                    f"Priority: {match.get('priority_score', 0):.1f}"
                )

                # Add HyperLens whale consensus for this symbol
                sm = match.get("smart_money")
                if sm and sm.get("trend"):
                    parts.append(
                        f"### Whale Consensus ({symbol}, {tf.upper()})\n"
                        f"Trend: {sm['trend']} | "
                        f"Confidence: {sm.get('confidence', 0):.0%}\n"
                        f"Wallets Long: {sm.get('long_count', 0)} | "
                        f"Short: {sm.get('short_count', 0)}\n"
                        f"Long Notional: ${sm.get('long_notional', 0)/1e6:.1f}M | "
                        f"Short Notional: ${sm.get('short_notional', 0)/1e6:.1f}M\n"
                        f"Net Ratio: {sm.get('net_ratio', 0):+.2f}"
                    )

                # Anomalies specific to this symbol
                sym_anomalies = [
                    a for a in getattr(cache, "anomalies", [])
                    if a.get("symbol") == symbol
                ]
                if sym_anomalies:
                    anom_lines = [f"### Anomalies ({symbol}, {tf.upper()})"]
                    for a in sym_anomalies:
                        atype = a.get("anomaly_type", "?")
                        sev = a.get("severity", "?")
                        ctx = a.get("context", "")
                        direction = a.get("direction", "")
                        z = a.get("z_score", 0)
                        sigma = a.get("historical_sigma", 0)
                        exchanges = a.get("exchanges_confirmed", [])
                        ex_vals = a.get("exchange_values", {})
                        ex_str = ""
                        if ex_vals:
                            ex_str = " | Exchanges: " + ", ".join(
                                f"{e}: {v}" for e, v in ex_vals.items()
                            )
                        anom_lines.append(
                            f"  {atype} ({sev}, {direction}): {ctx}"
                            f"\n  Z-score: {z:.1f} | History sigma: {sigma:.1f}{ex_str}"
                        )
                    parts.append("\n".join(anom_lines))
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

        # -- User positions from Hyperliquid ---------------------------------
        if wallet_address:
            pos_section = await self._build_positions_context(wallet_address, cache)
            if pos_section:
                parts.append(pos_section)

        # -- Historical signal log context ----------------------------------
        history_section = await self._build_history_context(symbol)
        if history_section:
            parts.append(history_section)

        # -- Performance analytics context ----------------------------------
        analytics_section = await self._build_analytics_context()
        if analytics_section:
            parts.append(analytics_section)

        return "\n\n".join(parts)

    async def _build_positions_context(
        self,
        wallet_address: str,
        cache,
    ) -> Optional[str]:
        """Fetch user's HL positions and cross-reference with scanner data."""
        try:
            from hyperliquid_data import fetch_clearinghouse_state, parse_open_positions

            state = await fetch_clearinghouse_state(wallet_address)
            if not state:
                return None

            positions = parse_open_positions(state)
            if not positions:
                return None

            # Account summary
            summary = state.get("marginSummary", {})
            account_value = float(summary.get("accountValue", 0))
            margin_used = float(summary.get("totalMarginUsed", 0))
            withdrawable = float(state.get("withdrawable", 0))

            lines: List[str] = [
                "## Your Hyperliquid Positions",
                f"Account Value: ${account_value:,.2f} | "
                f"Margin Used: ${margin_used:,.2f} | "
                f"Free: ${withdrawable:,.2f}",
                "",
            ]

            total_pnl = 0.0
            for p in positions:
                coin = p["coin"]
                symbol = p["symbol"]
                side = p["side"]
                entry = p["entry_px"]
                pnl = p["unrealized_pnl"]
                lev = p["leverage"]
                liq = p["liq_px"]
                size_usd = p["size_usd"]
                total_pnl += pnl

                # Get current price from scanner cache
                current_price = None
                scanner_signal = None
                scanner_regime = None
                scanner_heat = None
                scanner_zscore = None
                scanner_divergence = None

                for tf in ("4h", "1d"):
                    results = cache.get_results(tf)
                    match = next((r for r in results if r.get("symbol") == symbol), None)
                    if match:
                        if tf == "4h":  # prefer 4h data
                            current_price = match.get("price", 0)
                            scanner_signal = match.get("signal", "N/A")
                            scanner_regime = match.get("regime", "N/A")
                            scanner_heat = match.get("heat", 0)
                            scanner_zscore = match.get("zscore", 0)
                            scanner_divergence = match.get("divergence")

                # PnL %
                if entry > 0 and current_price:
                    if side == "LONG":
                        pnl_pct = ((current_price - entry) / entry) * 100
                    else:
                        pnl_pct = ((entry - current_price) / entry) * 100
                else:
                    pnl_pct = 0

                # Liquidation distance
                liq_warning = ""
                if liq > 0 and current_price:
                    liq_dist = abs(current_price - liq) / current_price * 100
                    if liq_dist < 10:
                        liq_warning = f" ⚠ LIQ RISK ({liq_dist:.1f}% away)"
                    elif liq_dist < 20:
                        liq_warning = f" (liq {liq_dist:.1f}% away)"

                # Scanner alignment
                alignment = ""
                if scanner_signal:
                    if side == "LONG":
                        if scanner_signal in ("STRONG_LONG", "LIGHT_LONG", "ACCUMULATE"):
                            alignment = "ALIGNED"
                        elif scanner_signal in ("TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"):
                            alignment = "CONFLICTING"
                        elif scanner_regime == "MARKDOWN":
                            alignment = "AGAINST REGIME"
                        else:
                            alignment = "NEUTRAL"
                    else:  # SHORT
                        if scanner_signal in ("TRIM", "TRIM_HARD", "RISK_OFF"):
                            alignment = "ALIGNED"
                        elif scanner_signal in ("STRONG_LONG", "LIGHT_LONG"):
                            alignment = "CONFLICTING"
                        elif scanner_regime in ("MARKUP", "ACCUM"):
                            alignment = "AGAINST REGIME"
                        else:
                            alignment = "NEUTRAL"

                price_str = f"${current_price:.6g}" if current_price else "N/A"
                lines.append(
                    f"### {coin} — {side} {lev}x"
                )
                lines.append(
                    f"Size: ${size_usd:,.0f} | Entry: ${entry:.6g} | "
                    f"Current: {price_str}"
                )
                lines.append(
                    f"PnL: ${pnl:+,.2f} ({pnl_pct:+.2f}%){liq_warning}"
                )
                if liq > 0:
                    lines.append(f"Liquidation: ${liq:.6g}")
                if scanner_signal:
                    div_str = f" | Div: {scanner_divergence}" if scanner_divergence else ""
                    lines.append(
                        f"Scanner: {scanner_signal} ({scanner_regime}) | "
                        f"Heat: {scanner_heat} | Z: {scanner_zscore:.2f}{div_str}"
                    )
                    lines.append(f"Position vs Signal: **{alignment}**")
                lines.append("")

            lines.append(f"**Total Unrealized PnL: ${total_pnl:+,.2f}**")

            return "\n".join(lines)

        except Exception as exc:
            logger.warning("Failed to build positions context: %s", exc)
            return None

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

    # -- Analytics context -------------------------------------------------

    async def _build_analytics_context(self) -> Optional[str]:
        """Fetch signal performance analytics and format as compact LLM context."""
        try:
            from signal_analytics import SignalAnalytics
            from signal_log import SignalLog
            slog = SignalLog.get()
            if slog._db is None:
                return None
            analytics = SignalAnalytics(slog)
            data = await analytics.get_full_attribution(timeframe="4h")
        except Exception as exc:
            logger.debug("Analytics context unavailable: %s", exc)
            return None

        lines: List[str] = ["## Signal Performance Analytics (Live)"]

        # Top predictive conditions
        conditions = data.get("conditions", [])
        if conditions:
            top = [c for c in conditions if c.get("edge") is not None]
            top_pos = [c for c in top if (c["edge"] or 0) > 0][:3]
            top_neg = [c for c in reversed(top) if (c["edge"] or 0) < 0][:2]
            if top_pos:
                parts = [f"{c['name']} (+{c['edge']}%)" for c in top_pos]
                lines.append(f"Top predictors: {', '.join(parts)}")
            if top_neg:
                parts = [f"{c['name']} ({c['edge']}%)" for c in top_neg]
                lines.append(f"Weakest: {', '.join(parts)}")

        # Best combos
        combos = data.get("combos", [])
        if combos:
            lines.append("Best condition combos:")
            for i, combo in enumerate(combos[:3], 1):
                conds = " + ".join(combo["conditions"])
                lines.append(
                    f"  {i}. {conds}: {combo['win_rate']}% WR (n={combo['count']})"
                )

        # Regime scorecard (compact: best/worst per signal)
        regime_data = data.get("regime_scorecard", {})
        if regime_data:
            lines.append("Regime performance:")
            for sig in ("STRONG_LONG", "LIGHT_LONG", "ACCUMULATE"):
                entries = regime_data.get(sig, [])
                if len(entries) >= 2:
                    best = max(entries, key=lambda e: e.get("win_rate", 0))
                    worst = min(entries, key=lambda e: e.get("win_rate", 100))
                    lines.append(
                        f"  {sig}: best in {best['regime']} ({best['win_rate']}%), "
                        f"worst in {worst['regime']} ({worst['win_rate']}%)"
                    )

        # Confluence scorecard
        confluence = data.get("confluence_scorecard", [])
        if confluence:
            parts = []
            for b in confluence:
                if b.get("win_rate") is not None and b["count"] > 0:
                    parts.append(f"{b['bucket']} cond -> {b['win_rate']}% WR")
            if parts:
                lines.append(f"Conviction: {', '.join(parts)}")

        # HyperLens attribution
        hl = data.get("hyperlens", {})
        ww = hl.get("with_whale", {})
        wo = hl.get("without_whale", {})
        if ww.get("count", 0) > 0 and wo.get("count", 0) > 0:
            edge = hl.get("edge_pct")
            if edge is not None:
                lines.append(
                    f"Whale edge: {'+' if edge > 0 else ''}{edge}% avg 7d "
                    f"(confirmed: {ww['win_rate']}% WR n={ww['count']}, "
                    f"without: {wo['win_rate']}% WR n={wo['count']})"
                )

        # Edge decay
        decay = data.get("edge_decay", [])
        if decay and any(p.get("avg_return") is not None for p in decay):
            parts = []
            for p in decay:
                if p.get("avg_return") is not None:
                    label = {"0-24h": "Day 1", "24h-72h": "Days 2-3", "72h-7d": "Days 4-7"}.get(p["period"], p["period"])
                    parts.append(f"{label}: {'+' if p['avg_return'] > 0 else ''}{p['avg_return']}%")
            lines.append(f"Edge decay: {', '.join(parts)}")

        return "\n".join(lines) if len(lines) > 1 else None

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
        wallet_address: Optional[str] = None,
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

        # Build context (async — queries signal log history + user positions)
        context = await self.build_context(
            symbol=detected,
            include_market=True,
            wallet_address=wallet_address,
        )

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

        if self._mode == "openrouter":
            # OpenAI-compatible format: system is first message in array
            openai_messages = [{"role": "system", "content": system}] + messages
            response = client.chat.completions.create(
                model=self._current_model,
                max_tokens=4096,
                messages=openai_messages,
            )
            reply = response.choices[0].message.content
        else:
            # Direct Anthropic SDK (fallback)
            response = client.messages.create(
                model=ANTHROPIC_FALLBACK_MODEL,
                max_tokens=4096,
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
                f"timeframe. Walk through the 14 conditions (10 core + 4 CoinGlass), "
                f"explain which pass and fail, show the weighted score, and explain "
                f"the specific reason the signal is what it is. Include how CVD, "
                f"smart money LSR, and macro data influenced the outcome. Be precise with numbers."
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
