"""
hl_intelligence.py
~~~~~~~~~~~~~~~~~~
HyperLens — Smart-money position tracking via Hyperliquid leaderboard.

Polls the public HL leaderboard daily to build a roster of top wallets
(filtered by ROI + account value), then fetches their open positions
every 5 minutes to compute per-symbol consensus.

No API key required.  All data is free and public.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
_HL_INFO_URL = "https://api.hyperliquid.xyz/info"

_ROSTER_REFRESH_INTERVAL = 24 * 60 * 60   # Daily
_POLL_INTERVAL = 5 * 60                    # 5 minutes (aligned with scan cycle)
_POSITION_HISTORY_LEN = 288               # 24h of 5-min snapshots

# Filtering thresholds
_MIN_ACCOUNT_VALUE = 500_000               # $500k minimum
_MIN_ROI_PCT = 30.0                        # 30% monthly ROI minimum
_ROSTER_SIZE = 100                         # Top 100 qualifying wallets
_MM_VLM_RATIO = 100                        # vlm/AV > 100 = market maker, skip
_ROI_WINDOW = "month"                      # Ranking window (was allTime)

# Consensus thresholds
_BULLISH_THRESHOLD = 0.15                  # net_ratio > 15% = BULLISH
_BEARISH_THRESHOLD = -0.15                 # net_ratio < -15% = BEARISH

# Rate limiting
_CONCURRENCY = 20                          # Max concurrent HL API calls
_REQUEST_TIMEOUT = 15

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class TrackedWallet:
    """A wallet in the tracking roster."""
    address: str
    display_name: str = ""
    account_value: float = 0.0
    pnl: float = 0.0
    roi: float = 0.0              # Percentage ROI
    score: float = 0.0            # roi * log(accountValue) ranking
    window_performances: dict = field(default_factory=dict)


@dataclass
class WalletPosition:
    """A single open position for a wallet."""
    coin: str
    side: str                     # LONG / SHORT
    size: float                   # Coin quantity
    size_usd: float
    entry_px: float
    unrealized_pnl: float
    leverage: float
    liq_px: float = 0.0


@dataclass
class PositionSnapshot:
    """Point-in-time snapshot of all positions for a wallet."""
    timestamp: float
    positions: List[WalletPosition]
    account_value: float = 0.0


@dataclass
class SymbolConsensus:
    """Aggregated smart-money consensus for a single symbol."""
    symbol: str                   # e.g. "BTC"
    long_count: int = 0
    short_count: int = 0
    neutral_count: int = 0        # Wallets with no position
    total_tracked: int = 0
    long_notional: float = 0.0    # Total USD long exposure
    short_notional: float = 0.0   # Total USD short exposure
    net_score: float = 0.0        # Weighted by wallet score
    net_ratio: float = 0.0        # (long - short) / total, -1 to +1
    trend: str = "NEUTRAL"        # BULLISH / BEARISH / NEUTRAL
    confidence: float = 0.0       # 0-1 strength of consensus
    top_longs: List[str] = field(default_factory=list)    # Top wallet addresses
    top_shorts: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_roster: List[TrackedWallet] = []
_roster_updated_at: float = 0.0

# Per-wallet position history: address -> deque of snapshots
_snapshots: Dict[str, deque] = {}

# Per-symbol consensus (recomputed after each poll)
_consensus: Dict[str, SymbolConsensus] = {}
_consensus_updated_at: float = 0.0

# Module state
_initialized = False
_last_poll_at: float = 0.0
_poll_count: int = 0


# ---------------------------------------------------------------------------
# Leaderboard fetch & roster building
# ---------------------------------------------------------------------------

async def refresh_leaderboard() -> int:
    """Fetch HL leaderboard and rebuild the tracking roster.

    Returns the number of wallets in the roster.
    """
    global _roster, _roster_updated_at

    logger.info("HyperLens: refreshing leaderboard roster...")

    timeout = aiohttp.ClientTimeout(total=45)  # Large response
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_LEADERBOARD_URL) as resp:
                if resp.status != 200:
                    logger.warning("Leaderboard fetch failed: HTTP %d", resp.status)
                    return len(_roster)
                raw = await resp.json(content_type=None)
    except Exception as exc:
        logger.warning("Leaderboard fetch error: %s", exc)
        return len(_roster)

    # Response is {"leaderboardRows": [...]}
    rows = raw if isinstance(raw, list) else raw.get("leaderboardRows", [])
    if not rows:
        logger.warning("Leaderboard empty or unexpected format: %s", type(raw))
        return len(_roster)

    # Parse and filter
    candidates: List[TrackedWallet] = []
    for entry in rows:
        try:
            # Handle different field naming conventions
            address = entry.get("ethAddress", "") or entry.get("address", "")
            if not address:
                continue

            account_value = float(entry.get("accountValue", 0) or 0)
            display_name = entry.get("displayName", "") or ""

            # Extract PnL and ROI from windowPerformances
            pnl = 0.0
            roi = 0.0
            monthly_vlm = 0.0
            window_perfs = entry.get("windowPerformances", [])

            if window_perfs and isinstance(window_perfs, list):
                # windowPerformances is a list of [window_name, {pnl, roi, vlm}]
                for wp in window_perfs:
                    if isinstance(wp, list) and len(wp) >= 2:
                        window_name = wp[0]
                        metrics = wp[1] if isinstance(wp[1], dict) else {}
                        if window_name == _ROI_WINDOW:
                            pnl = float(metrics.get("pnl", 0) or 0)
                            roi = float(metrics.get("roi", 0) or 0) * 100
                            monthly_vlm = float(metrics.get("vlm", 0) or 0)
            else:
                pnl = float(entry.get("pnl", 0) or 0)
                roi = float(entry.get("roi", 0) or 0) * 100

            # Apply filters
            if account_value < _MIN_ACCOUNT_VALUE:
                continue
            if roi < _MIN_ROI_PCT:
                continue

            # Market maker filter: vlm/AV ratio > 100 = likely MM/vault
            if account_value > 0 and monthly_vlm / account_value > _MM_VLM_RATIO:
                continue

            # Compute ranking score: monthly_roi * log(accountValue)
            score = roi * math.log(max(account_value, 1))

            candidates.append(TrackedWallet(
                address=address.lower(),
                display_name=display_name,
                account_value=account_value,
                pnl=pnl,
                roi=roi,
                score=score,
                window_performances={
                    wp[0]: wp[1] for wp in window_perfs
                    if isinstance(wp, list) and len(wp) >= 2
                } if isinstance(window_perfs, list) else {},
            ))
        except Exception:
            continue  # Skip malformed entries

    # Sort by score descending, take top N
    candidates.sort(key=lambda w: w.score, reverse=True)
    _roster = candidates[:_ROSTER_SIZE]
    _roster_updated_at = time.time()

    logger.info(
        "HyperLens: roster built — %d wallets from %d candidates (filtered from %d total). "
        "Top score: %.1f, min AV: $%.0fk",
        len(_roster),
        len(candidates),
        len(rows),
        _roster[0].score if _roster else 0,
        _roster[-1].account_value / 1000 if _roster else 0,
    )
    return len(_roster)


# ---------------------------------------------------------------------------
# Position polling
# ---------------------------------------------------------------------------

async def _fetch_wallet_positions(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    wallet: TrackedWallet,
) -> Optional[PositionSnapshot]:
    """Fetch open positions for a single wallet."""
    async with semaphore:
        try:
            async with session.post(
                _HL_INFO_URL,
                json={"type": "clearinghouseState", "user": wallet.address},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
        except Exception:
            return None

    if not data:
        return None

    # Parse positions
    positions: List[WalletPosition] = []
    for ap in data.get("assetPositions", []):
        pos = ap.get("position", {})
        szi = float(pos.get("szi", 0))
        if szi == 0:
            continue

        entry_px = float(pos.get("entryPx", 0))
        coin = pos.get("coin", "")
        lev_val = pos.get("leverage", {})
        lev = float(lev_val.get("value", 1)) if isinstance(lev_val, dict) else float(lev_val or 1)

        positions.append(WalletPosition(
            coin=coin,
            side="LONG" if szi > 0 else "SHORT",
            size=abs(szi),
            size_usd=abs(szi) * entry_px,
            entry_px=entry_px,
            unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
            leverage=lev,
            liq_px=float(pos.get("liquidationPx", 0) or 0),
        ))

    # Extract account value
    margin = data.get("marginSummary", {})
    av = float(margin.get("accountValue", 0) or 0)

    return PositionSnapshot(
        timestamp=time.time(),
        positions=positions,
        account_value=av,
    )


async def poll_positions() -> int:
    """Poll positions for all roster wallets.

    Returns number of wallets successfully polled.
    """
    global _last_poll_at, _poll_count, _consensus_updated_at

    if not _roster:
        logger.debug("HyperLens: no roster — skipping poll")
        return 0

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)
    success_count = 0

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            _fetch_wallet_positions(session, semaphore, w)
            for w in _roster
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for wallet, result in zip(_roster, results):
        if isinstance(result, Exception) or result is None:
            continue

        # Store snapshot in ring buffer
        if wallet.address not in _snapshots:
            _snapshots[wallet.address] = deque(maxlen=_POSITION_HISTORY_LEN)
        _snapshots[wallet.address].append(result)

        # Update wallet account value from live data
        if result.account_value > 0:
            wallet.account_value = result.account_value

        success_count += 1

    _last_poll_at = time.time()
    _poll_count += 1

    # Recompute consensus
    _recompute_consensus()
    _consensus_updated_at = time.time()

    logger.info(
        "HyperLens poll #%d: %d/%d wallets, %d symbols with consensus",
        _poll_count, success_count, len(_roster), len(_consensus),
    )
    return success_count


# ---------------------------------------------------------------------------
# Consensus computation
# ---------------------------------------------------------------------------

def _recompute_consensus() -> None:
    """Aggregate latest positions across all wallets into per-symbol consensus."""
    global _consensus

    # Build a score lookup for weighting (consensus weighted by notional * score)
    score_map = {w.address: w.score for w in _roster}

    # Collect per-symbol data
    sym_data: Dict[str, dict] = {}

    for wallet in _roster:
        snapshots = _snapshots.get(wallet.address)
        if not snapshots:
            continue

        latest = snapshots[-1]
        coins_seen = set()

        for pos in latest.positions:
            coin = pos.coin
            if coin not in sym_data:
                sym_data[coin] = {
                    "long_count": 0, "short_count": 0,
                    "long_notional": 0.0, "short_notional": 0.0,
                    "weighted_sum": 0.0,
                    "top_longs": [], "top_shorts": [],
                }

            d = sym_data[coin]
            w_score = score_map.get(wallet.address, 1.0)

            # Weight consensus by notional size * wallet score
            # so a $5M position from a top trader counts more than a $50k one
            notional_weight = pos.size_usd * w_score

            if pos.side == "LONG":
                d["long_count"] += 1
                d["long_notional"] += pos.size_usd
                d["weighted_sum"] += notional_weight
                d["top_longs"].append(wallet.address)
            else:
                d["short_count"] += 1
                d["short_notional"] += pos.size_usd
                d["weighted_sum"] -= notional_weight
                d["top_shorts"].append(wallet.address)

            coins_seen.add(coin)

    # Build consensus objects
    new_consensus: Dict[str, SymbolConsensus] = {}
    total_tracked = len([w for w in _roster if w.address in _snapshots])

    for coin, d in sym_data.items():
        total_positioned = d["long_count"] + d["short_count"]
        net_ratio = (d["long_count"] - d["short_count"]) / max(total_positioned, 1)
        # Notional-weighted score: positive = net long conviction, negative = short
        total_notional = d["long_notional"] + d["short_notional"]
        norm_score = d["weighted_sum"] / max(total_notional, 1.0)  # normalized by total exposure

        if net_ratio > _BULLISH_THRESHOLD:
            trend = "BULLISH"
        elif net_ratio < _BEARISH_THRESHOLD:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        confidence = min(abs(net_ratio), 1.0)

        new_consensus[coin] = SymbolConsensus(
            symbol=coin,
            long_count=d["long_count"],
            short_count=d["short_count"],
            neutral_count=total_tracked - total_positioned,
            total_tracked=total_tracked,
            long_notional=d["long_notional"],
            short_notional=d["short_notional"],
            net_score=norm_score,
            net_ratio=net_ratio,
            trend=trend,
            confidence=confidence,
            top_longs=d["top_longs"][:5],    # Top 5 only
            top_shorts=d["top_shorts"][:5],
        )

    _consensus = new_consensus


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_consensus(symbol: str) -> Optional[SymbolConsensus]:
    """Get consensus for a symbol (used by signal synthesizer).

    Accepts formats: "BTC", "BTC/USDT:USDT", "BTCUSDT"
    """
    # Normalize to bare coin
    coin = symbol.split("/")[0].split(":")[0].replace("USDT", "").replace("USDC", "")
    # Handle 1000-prefix coins
    if coin.startswith("1000"):
        coin = coin[4:]
    return _consensus.get(coin)


def get_all_consensus() -> Dict[str, SymbolConsensus]:
    """Get all symbol consensus data."""
    return dict(_consensus)


def get_roster() -> List[dict]:
    """Get current roster as serializable dicts."""
    result = []
    for i, w in enumerate(_roster):
        # Get latest position count
        snaps = _snapshots.get(w.address)
        pos_count = len(snaps[-1].positions) if snaps else 0

        result.append({
            "rank": i + 1,
            "address": w.address,
            "display_name": w.display_name,
            "account_value": w.account_value,
            "pnl": w.pnl,
            "roi": w.roi,
            "score": round(w.score, 1),
            "position_count": pos_count,
        })
    return result


def get_wallet_positions(address: str) -> Optional[dict]:
    """Get latest positions for a specific wallet."""
    address = address.lower()
    snaps = _snapshots.get(address)
    if not snaps:
        return None

    latest = snaps[-1]
    return {
        "address": address,
        "timestamp": latest.timestamp,
        "account_value": latest.account_value,
        "positions": [
            {
                "coin": p.coin,
                "side": p.side,
                "size": p.size,
                "size_usd": round(p.size_usd, 2),
                "entry_px": p.entry_px,
                "unrealized_pnl": round(p.unrealized_pnl, 2),
                "leverage": p.leverage,
                "liq_px": p.liq_px,
            }
            for p in latest.positions
        ],
    }


def get_symbol_positions(symbol: str) -> List[dict]:
    """Get all wallet positions for a specific symbol."""
    coin = symbol.split("/")[0].split(":")[0].replace("USDT", "").replace("USDC", "")
    if coin.startswith("1000"):
        coin = coin[4:]

    result = []
    for wallet in _roster:
        snaps = _snapshots.get(wallet.address)
        if not snaps:
            continue
        latest = snaps[-1]
        for pos in latest.positions:
            if pos.coin == coin:
                result.append({
                    "address": wallet.address,
                    "display_name": wallet.display_name,
                    "wallet_score": round(wallet.score, 1),
                    "wallet_roi": wallet.roi,
                    "coin": pos.coin,
                    "side": pos.side,
                    "size_usd": round(pos.size_usd, 2),
                    "entry_px": pos.entry_px,
                    "unrealized_pnl": round(pos.unrealized_pnl, 2),
                    "leverage": pos.leverage,
                })
    # Sort by wallet score descending
    result.sort(key=lambda x: x["wallet_score"], reverse=True)
    return result


def get_position_changes(symbol: str, window_minutes: int = 30) -> dict:
    """Detect position changes for a symbol over the recent window.

    Returns: {opened: int, closed: int, flipped: int, net_change: str}
    """
    coin = symbol.split("/")[0].split(":")[0].replace("USDT", "").replace("USDC", "")
    if coin.startswith("1000"):
        coin = coin[4:]

    cutoff = time.time() - (window_minutes * 60)
    opened = 0
    closed = 0
    flipped = 0

    for wallet in _roster:
        snaps = _snapshots.get(wallet.address)
        if not snaps or len(snaps) < 2:
            continue

        latest = snaps[-1]

        # Walk backwards (newest→oldest) to find the most recent snapshot
        # at or before the cutoff timestamp — first match is the closest one.
        prev = None
        for snap in reversed(snaps):
            if snap.timestamp <= cutoff:
                prev = snap
                break
        if not prev:
            prev = snaps[0]

        # Compare positions for this coin
        prev_pos = next((p for p in prev.positions if p.coin == coin), None)
        curr_pos = next((p for p in latest.positions if p.coin == coin), None)

        if prev_pos is None and curr_pos is not None:
            opened += 1
        elif prev_pos is not None and curr_pos is None:
            closed += 1
        elif prev_pos and curr_pos and prev_pos.side != curr_pos.side:
            flipped += 1

    net = opened - closed
    if net > 0:
        net_change = "INCREASING"
    elif net < 0:
        net_change = "DECREASING"
    else:
        net_change = "STABLE"

    return {
        "symbol": coin,
        "window_minutes": window_minutes,
        "opened": opened,
        "closed": closed,
        "flipped": flipped,
        "net_change": net_change,
    }


def get_status() -> dict:
    """Module status for API endpoint."""
    return {
        "tracked_wallets": len(_roster),
        "wallets_with_data": len(_snapshots),
        "consensus_symbols": len(_consensus),
        "last_poll": _last_poll_at or None,
        "last_roster_refresh": _roster_updated_at or None,
        "poll_count": _poll_count,
        "poll_interval_sec": _POLL_INTERVAL,
        "roster_refresh_interval_sec": _ROSTER_REFRESH_INTERVAL,
        "initialized": _initialized,
    }


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def run_hyperlens_loop() -> None:
    """Main background loop: refresh roster daily, poll positions every 5 min."""
    global _initialized

    logger.info("HyperLens: starting background loop...")

    # Initial delay — let the main scan warm up first
    await asyncio.sleep(15)

    # Initial roster fetch
    count = await refresh_leaderboard()
    if count == 0:
        logger.warning("HyperLens: empty roster on startup, will retry in 5 min")

    _initialized = True
    last_roster_refresh = time.time()

    while True:
        try:
            # Refresh roster daily
            if time.time() - last_roster_refresh > _ROSTER_REFRESH_INTERVAL:
                await refresh_leaderboard()
                last_roster_refresh = time.time()

            # Poll positions
            if _roster:
                await poll_positions()

        except Exception as exc:
            logger.warning("HyperLens loop error: %s", exc)

        await asyncio.sleep(_POLL_INTERVAL)
