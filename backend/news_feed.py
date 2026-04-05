"""
news_feed.py
~~~~~~~~~~~~
CryptoPanic news feed integration for the trading assistant.

Fetches recent crypto news headlines with sentiment votes,
cached to avoid hammering the free-tier API (5 req/min).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY", "")
CRYPTOPANIC_BASE = "https://cryptopanic.com/api/v1/posts/"

# Cache settings
_CACHE_TTL = 300  # 5 minutes — well within free-tier rate limits
_cache: Dict[str, tuple] = {}  # key -> (timestamp, data)


@dataclass
class NewsItem:
    title: str
    source: str
    published: str
    currencies: List[str]
    sentiment: str  # "bullish", "bearish", "neutral"
    votes_positive: int
    votes_negative: int
    votes_important: int
    kind: str  # "news", "media", "analysis"


def _extract_sentiment(votes: dict) -> str:
    """Derive sentiment from community votes."""
    pos = votes.get("positive", 0) + votes.get("liked", 0)
    neg = votes.get("negative", 0) + votes.get("disliked", 0) + votes.get("toxic", 0)
    if pos > neg + 2:
        return "bullish"
    elif neg > pos + 2:
        return "bearish"
    return "neutral"


def _parse_item(raw: dict) -> NewsItem:
    """Parse a single CryptoPanic API result into a NewsItem."""
    votes = raw.get("votes", {})
    currencies = [c.get("code", "") for c in raw.get("currencies", []) if c.get("code")]
    source = raw.get("source", {})
    return NewsItem(
        title=raw.get("title", ""),
        source=source.get("title", source.get("domain", "unknown")),
        published=raw.get("published_at", raw.get("created_at", "")),
        currencies=currencies,
        sentiment=_extract_sentiment(votes),
        votes_positive=votes.get("positive", 0),
        votes_negative=votes.get("negative", 0),
        votes_important=votes.get("important", 0),
        kind=raw.get("kind", "news"),
    )


async def fetch_news(
    currencies: Optional[List[str]] = None,
    filter_type: str = "hot",
    limit: int = 10,
) -> List[NewsItem]:
    """Fetch recent crypto news from CryptoPanic.

    Args:
        currencies: Filter by coin codes, e.g. ["BTC", "ETH"]. None = all.
        filter_type: "hot", "rising", "bullish", "bearish", "important"
        limit: Max items to return.

    Returns:
        List of NewsItem, newest first.
    """
    if not CRYPTOPANIC_API_KEY:
        logger.debug("CRYPTOPANIC_API_KEY not set — news feed disabled")
        return []

    # Build cache key
    curr_key = ",".join(sorted(currencies)) if currencies else "ALL"
    cache_key = f"{curr_key}:{filter_type}"

    # Check cache
    if cache_key in _cache:
        cached_ts, cached_data = _cache[cache_key]
        if time.time() - cached_ts < _CACHE_TTL:
            return cached_data[:limit]

    # Build request
    params = {
        "auth_token": CRYPTOPANIC_API_KEY,
        "filter": filter_type,
        "regions": "en",
        "kind": "news",
    }
    if currencies:
        params["currencies"] = ",".join(currencies)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                CRYPTOPANIC_BASE,
                params=params,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    logger.warning("CryptoPanic API returned %d", resp.status)
                    return _cache.get(cache_key, (0, []))[1][:limit]
                data = await resp.json()
    except Exception as e:
        logger.warning("CryptoPanic fetch failed: %s", e)
        return _cache.get(cache_key, (0, []))[1][:limit]

    items = [_parse_item(r) for r in data.get("results", [])]
    _cache[cache_key] = (time.time(), items)
    return items[:limit]


async def fetch_news_for_symbol(symbol: str, limit: int = 5) -> List[NewsItem]:
    """Fetch news for a specific trading pair like 'BTC/USDT'."""
    base = symbol.replace("/USDT", "").replace("/USD", "").upper()
    return await fetch_news(currencies=[base], filter_type="hot", limit=limit)


def format_news_context(items: List[NewsItem], max_items: int = 8) -> str:
    """Format news items into a context block for the LLM system prompt.

    Returns a compact string suitable for injection into the assistant context.
    """
    if not items:
        return ""

    lines = ["## Recent Crypto News (CryptoPanic)"]
    for item in items[:max_items]:
        # Sentiment indicator
        if item.sentiment == "bullish":
            sent = "▲"
        elif item.sentiment == "bearish":
            sent = "▼"
        else:
            sent = "—"

        # Coins mentioned
        coins = f" [{', '.join(item.currencies)}]" if item.currencies else ""

        # Votes summary (only if notable)
        vote_parts = []
        if item.votes_important > 0:
            vote_parts.append(f"!{item.votes_important}")
        if item.votes_positive > 0:
            vote_parts.append(f"+{item.votes_positive}")
        if item.votes_negative > 0:
            vote_parts.append(f"-{item.votes_negative}")
        votes_str = f" ({', '.join(vote_parts)})" if vote_parts else ""

        # Timestamp — just the time portion
        time_str = ""
        if "T" in item.published:
            time_str = f" {item.published.split('T')[1][:5]}"

        lines.append(f"- {sent} **{item.title}**{coins}{votes_str} — {item.source}{time_str}")

    lines.append("")
    lines.append(
        "*Use news to contextualize scanner signals, not to override them. "
        "Headlines explain narrative; the system measures structure.*"
    )
    return "\n".join(lines)
