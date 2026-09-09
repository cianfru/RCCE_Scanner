"""
assistant.py
~~~~~~~~~~~~
LLM-powered trading assistant with OpenRouter multi-model support.

Provides natural-language signal explanations, daily briefings,
and conversational Q&A over live RCCE Scanner data.
Uses an operator-configured, verified free OpenRouter model with no paid fallback.
"""

from __future__ import annotations

import os
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model catalogue & provider config
# ---------------------------------------------------------------------------

# Operator-owned configuration. Never accept provider/model choices from a chat request.
DEFAULT_MODEL = os.environ.get("REFLEX_ASSISTANT_MODEL", "google/gemma-4-31b-it:free")
MAX_HISTORY_MESSAGES = 20
# Cap retained chat sessions. Briefing/explain mint a unique session id per call,
# so an unbounded dict would leak memory over time; evict the oldest past this.
MAX_SESSIONS = 500

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

        # Skip non-text models (music, image, video generators)
        # Modality format: "input->output" e.g. "text->text", "text+image->text+audio"
        # Only keep models whose output is pure text (not text+audio, text+image etc)
        modality = (m.get("architecture", {}) or {}).get("modality", "")
        if modality:
            output_modality = modality.split("->")[-1].strip()
            if output_modality != "text":
                continue

        # Derive provider from model ID (e.g. "anthropic/claude-3.5-haiku" -> "Anthropic")
        provider = model_id.split("/")[0].title() if "/" in model_id else "Unknown"

        # Extract pricing — free models have prompt/completion = "0"
        pricing = m.get("pricing", {})
        prompt_cost = float(pricing.get("prompt", "0") or "0")
        completion_cost = float(pricing.get("completion", "0") or "0")
        is_free = ("prompt" in pricing and "completion" in pricing and prompt_cost == 0 and completion_cost == 0 and float(pricing.get("request", "0") or "0") == 0)

        # Created timestamp — newer models are generally more capable
        created_at = m.get("created", 0) or 0

        models.append({
            "id": model_id,
            "label": f"{'[FREE] ' if is_free else ''}{name}",
            "provider": provider,
            "context_length": ctx,
            "is_free": is_free,
            "cost_per_1k": round((prompt_cost + completion_cost) * 1000, 4),
            "created_at": created_at,
        })

    # Sort: free first → biggest context → newest (best free model at top)
    # Paid: cheapest first → biggest context → newest
    models.sort(key=lambda m: (
        0 if m["is_free"] else 1,           # free first
        -m["context_length"],                # biggest context first
        -m["created_at"],                    # newest first (tiebreaker)
        m["cost_per_1k"],                    # paid: cheapest first
        m["label"].lower(),
    ))

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

    OpenRouter only; absent configuration fails closed.
    """
    # Try OpenRouter first
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not or_key:
        _load_env()
        or_key = os.environ.get("OPENROUTER_API_KEY", "")

    if or_key:
        return or_key, "https://openrouter.ai/api/v1", "openrouter"

    raise RuntimeError("AI Assist is unavailable: the server needs OPENROUTER_API_KEY.")


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
        self.sessions: "OrderedDict[str, ChatSession]" = OrderedDict()
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
        return self._client

    # -- Model management ---------------------------------------------------

    def get_current_model(self) -> str:
        """Return the active model ID."""
        return self._current_model

    def set_model(self, model_id: str) -> bool:
        """Retired public mutation. Operators use REFLEX_ASSISTANT_MODEL."""
        return False

    async def get_available_models(self) -> list:
        return [m for m in await _fetch_openrouter_models() if m.get("is_free") and m["id"].endswith(":free")]

    async def _validate_free_model(self):
        models = await self.get_available_models()
        if not self._current_model.endswith(":free") or not any(m["id"] == self._current_model for m in models):
            raise RuntimeError("AI Assist is temporarily unavailable. The configured free model needs an operator update.")

    def get_mode(self) -> str:
        """Return current provider mode, initialising client if needed."""
        self._get_client()
        return self._mode or "unknown"

    def get_or_create_session(self, session_id: str) -> ChatSession:
        session = self.sessions.get(session_id)
        if session is None:
            session = ChatSession(session_id=session_id)
            self.sessions[session_id] = session
            # Evict the least-recently-used sessions past the cap.
            while len(self.sessions) > MAX_SESSIONS:
                self.sessions.popitem(last=False)
        else:
            self.sessions.move_to_end(session_id)
        return session

    # -- Context builder ---------------------------------------------------






    @staticmethod

    # -- Analytics context -------------------------------------------------


    # -- Symbol detection --------------------------------------------------

    def _detect_symbol(self, text: str) -> Optional[str]:
        """Extract a symbol from user text, e.g. 'why is HYPE light long?' -> 'HYPE/USDT'."""
        matches = self._detect_all_symbols(text)
        return matches[0] if matches else None

    def _detect_all_symbols(self, text: str) -> List[str]:
        """Extract all mentioned symbols from user text for comparison queries."""
        from scanner import cache
        import re

        text_upper = text.upper()
        found: List[str] = []
        seen_bases: set = set()

        # Collect all known base symbols
        all_bases: List[tuple] = []
        for tf_key in ("4h", "1d"):
            tf_results = cache.get_results(tf_key)
            for r in tf_results:
                sym = r.get("symbol", "")
                base = sym.split("/")[0]
                if (len(base) == 1 or base.upper() in {"I", "A", "AN", "IS", "IT", "ME", "MY", "ON", "IN", "THE", "AND", "OR", "FOR", "TO", "WHY", "WHAT", "HOW", "ALL", "NOW", "UP", "DOWN", "GO", "BE", "AS", "AT", "DO", "AI", "SELL", "BUY", "LONG", "SHORT", "STRONG", "LIGHT", "WAIT", "HOLD", "HIGH", "LOW", "NEAR", "ONE", "RISK", "MARKET", "PRICE", "ENTRY", "EXIT", "TIME", "CHECK", "SIGNAL", "STOP", "FUN", "SAFE", "GOOD", "BEST", "NEW"}) and "$" + base.upper() not in text_upper:
                    continue
                if base not in seen_bases:
                    all_bases.append((base, sym))
                    seen_bases.add(base)

        # Sort by length descending to match longest first
        all_bases.sort(key=lambda x: -len(x[0]))

        matched_positions: set = set()
        for base, sym in all_bases:
            # Use word boundary to avoid partial matches
            pattern = rf'\b{re.escape(base)}\b'
            for m in re.finditer(pattern, text_upper):
                pos = m.start()
                if pos not in matched_positions:
                    matched_positions.add(pos)
                    if sym not in found:
                        found.append(sym)

        return found

    # -- Chat --------------------------------------------------------------

    async def chat(
        self,
        session_id: str,
        user_message: str,
        symbol: Optional[str] = None,
        wallet_address: Optional[str] = None,
        timeframe: str = "1d",
    ) -> tuple[str, Optional[str]]:
        """Process a user message and return (reply, detected_symbol)."""
        import re
        from scanner import cache
        from assistant_snapshot import snapshot, RULES
        requested_tf = re.search(r"\b(4h|1d)\b", user_message, re.I)
        timeframe = requested_tf.group(1).lower() if requested_tf else timeframe
        if timeframe not in {"4h", "1d"}:
            raise ValueError("Timeframe must be 4h or 1d")
        scoped_session_id = f"{wallet_address or 'public'}:{session_id}:{timeframe}"
        session = self.get_or_create_session(scoped_session_id)
        mentions = self._detect_all_symbols(user_message)
        detected = mentions[0] if mentions else symbol
        if detected and "/" not in detected:
            detected = next((s for s in cache.symbols if s.split("/")[0].upper() == detected.upper()), f"{detected}/USDT")
        requested = list(dict.fromkeys(mentions + ([detected] if detected else [])))
        context = snapshot(cache, requested, timeframe)
        await self._validate_free_model()

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

        system = RULES + "\n\nCurrent scanner snapshot:\n" + context

        client = self._get_client()

        if self._mode == "openrouter":
            # OpenAI-compatible format: system is first message in array
            openai_messages = [{"role": "system", "content": system}] + messages
            import asyncio
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self._current_model,
                max_tokens=4096,
                temperature=0.1,
                messages=openai_messages,
                extra_body={"provider": {"max_price": {"prompt": 0, "completion": 0}, "allow_fallbacks": False}},
            )
            # Defensive parsing — some free OpenRouter models return empty/null
            # choices when the upstream provider has issues. Surface a readable
            # error instead of crashing with 'NoneType is not subscriptable'.
            choices = getattr(response, "choices", None)
            if not choices:
                raw = getattr(response, "model_dump", lambda: {})() or str(response)
                logger.warning("OpenRouter returned no choices for model %s. Raw: %s",
                               self._current_model, str(raw)[:500])
                reply = "AI Assist is temporarily unavailable. Please try again shortly."
            else:
                first = choices[0]
                msg = getattr(first, "message", None)
                content = getattr(msg, "content", None) if msg else None
                if content is None or content == "":
                    finish = getattr(first, "finish_reason", None)
                    logger.warning(
                        "OpenRouter returned empty content for model %s (finish_reason=%s)",
                        self._current_model, finish,
                    )
                    reply = "AI Assist could not produce an explanation. Please try again shortly."
                else:
                    reply = content
        else:
            raise RuntimeError("AI Assist requires the configured free provider.")

        session.messages.append(ChatMessage(role="assistant", content=reply))

        # Persist to memory + extract profile (fire-and-forget)
        try:
            from assistant_memory import ConversationMemory
            mem = ConversationMemory.get()
            await mem.store_exchange(session_id, user_message, reply, detected, wallet=wallet_address)
            await mem.extract_profile_from_conversation(user_message, reply, detected, wallet=wallet_address)
        except Exception:
            pass

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
                f"timeframe. Walk through the conditions supplied in the snapshot, "
                f"explain which pass and fail, show the weighted score, and explain "
                f"the specific reason the signal is what it is. Include how CVD, "
                f"smart money LSR, and macro data influenced the outcome. Be precise with numbers."
            ),
            symbol=symbol,
            timeframe=timeframe,
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
