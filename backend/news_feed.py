"""
news_feed.py
~~~~~~~~~~~~
CryptoCompare news feed integration for the trading assistant.

Fetches recent crypto news headlines from CryptoCompare's free API
(100K calls/month), cached at 5-minute intervals.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

CRYPTOCOMPARE_API_KEY = os.environ.get("CRYPTOCOMPARE_API_KEY", "")
CRYPTOCOMPARE_NEWS_URL = "https://min-api.cryptocompare.com/data/v2/news/"

# Cache settings
_CACHE_TTL = 300  # 5 minutes
_cache: Dict[str, tuple] = {}  # key -> (timestamp, data)


@dataclass
class NewsItem:
    title: str
    body: str  # short snippet
    source: str
    published: str  # ISO-ish timestamp
    categories: List[str]  # e.g. ["BTC", "ETH", "Trading"]
    url: str


def _parse_item(raw: dict) -> NewsItem:
    """Parse a single CryptoCompare news item."""
    # published_on is a unix timestamp
    ts = raw.get("published_on", 0)
    published = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S") if ts else ""

    # Body — truncate to first ~200 chars for context
    body = raw.get("body", "")
    if len(body) > 200:
        body = body[:200].rsplit(" ", 1)[0] + "..."

    # Categories come as pipe-separated string: "BTC|Trading|Regulation"
    cat_str = raw.get("categories", "")
    categories = [c.strip() for c in cat_str.split("|") if c.strip()] if cat_str else []

    return NewsItem(
        title=raw.get("title", ""),
        body=body,
        source=raw.get("source_info", {}).get("name", raw.get("source", "unknown")),
        published=published,
        categories=categories,
        url=raw.get("url", ""),
    )


async def fetch_news(
    categories: Optional[List[str]] = None,
    limit: int = 10,
) -> List[NewsItem]:
    """Fetch recent crypto news from CryptoCompare.

    Args:
        categories: Filter by coin/topic codes, e.g. ["BTC", "ETH"]. None = all.
        limit: Max items to return.

    Returns:
        List of NewsItem, newest first.
    """
    # Build cache key
    cat_key = ",".join(sorted(categories)) if categories else "ALL"
    cache_key = f"cc:{cat_key}"

    # Check cache
    if cache_key in _cache:
        cached_ts, cached_data = _cache[cache_key]
        if time.time() - cached_ts < _CACHE_TTL:
            return cached_data[:limit]

    # Build request
    params: Dict[str, str] = {"lang": "EN"}
    if categories:
        params["categories"] = ",".join(categories)
    if CRYPTOCOMPARE_API_KEY:
        params["api_key"] = CRYPTOCOMPARE_API_KEY

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                CRYPTOCOMPARE_NEWS_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    logger.warning("CryptoCompare news API returned %d", resp.status)
                    return _cache.get(cache_key, (0, []))[1][:limit]
                data = await resp.json()
    except Exception as e:
        logger.warning("CryptoCompare news fetch failed: %s", e)
        return _cache.get(cache_key, (0, []))[1][:limit]

    raw_items = data.get("Data", [])
    items = [_parse_item(r) for r in raw_items]
    _cache[cache_key] = (time.time(), items)
    return items[:limit]


async def fetch_news_for_symbol(symbol: str, limit: int = 5) -> List[NewsItem]:
    """Fetch news for a specific trading pair like 'BTC/USDT'."""
    base = symbol.replace("/USDT", "").replace("/USD", "").upper()
    return await fetch_news(categories=[base], limit=limit)


def format_news_context(items: List[NewsItem], max_items: int = 8) -> str:
    """Format news items into a context block for the LLM system prompt."""
    if not items:
        return ""

    lines = ["## Recent Crypto News"]
    for item in items[:max_items]:
        # Coins/topics mentioned
        coin_tags = [c for c in item.categories if len(c) <= 5 and c.isupper()]
        coins = f" [{', '.join(coin_tags)}]" if coin_tags else ""

        # Timestamp — just the time portion
        time_str = ""
        if "T" in item.published:
            time_str = f" {item.published.split('T')[1][:5]}"

        lines.append(f"- **{item.title}**{coins} — {item.source}{time_str}")

        # Add body snippet if it adds useful context
        if item.body and len(item.body) > 30:
            lines.append(f"  _{item.body}_")

    lines.append("")
    lines.append(
        "*Use news to contextualize scanner signals, not to override them. "
        "Headlines explain narrative; the system measures structure.*"
    )
    return "\n".join(lines)
