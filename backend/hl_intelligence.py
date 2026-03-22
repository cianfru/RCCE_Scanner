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
import re
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
# ~24h of 5-min snapshots (actual count may drift slightly due to
# network delays and retries, so treat as approximate)
_POSITION_HISTORY_LEN = 300

# Staleness: skip snapshots older than this when computing consensus
_SNAPSHOT_MAX_AGE_S = 15 * 60              # 15 minutes (3 missed polls)

# Filtering thresholds
_MIN_ACCOUNT_VALUE = 500_000               # $500k minimum
_MIN_ROI_PCT = 30.0                        # 30% monthly ROI minimum
_ROSTER_SIZE = 100                         # Top 100 qualifying wallets
_MM_VLM_RATIO = 100                        # vlm/AV > 100 = market maker, skip
_MM_MAX_POSITIONS = 25                     # wallets with >25 concurrent positions = likely MM/vault
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
    roi: float = 0.0              # Monthly percentage ROI
    score: float = 0.0            # monthly_roi * log(accountValue) ranking


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

    # Reconstruct trades from snapshot diffs (must run before consensus)
    _reconstruct_trades()

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
    """Aggregate latest positions across all wallets into per-symbol consensus.

    Trend is derived from notional-weighted net_score (not raw wallet count)
    so a single whale with $10M has more influence than ten $50k wallets.
    Stale snapshots (>15min old) are excluded to prevent ghost data.
    """
    global _consensus

    now = time.time()
    score_map = {w.address: w.score for w in _roster}

    # Collect per-symbol data (skip stale + MM-like wallets)
    sym_data: Dict[str, dict] = {}
    fresh_wallet_count = 0

    for wallet in _roster:
        snapshots = _snapshots.get(wallet.address)
        if not snapshots:
            continue

        latest = snapshots[-1]

        # Staleness check: skip wallets whose last snapshot is too old
        if now - latest.timestamp > _SNAPSHOT_MAX_AGE_S:
            continue

        # Position-count MM filter: wallets with >25 positions are likely
        # market makers or vaults — skip from consensus
        if len(latest.positions) > _MM_MAX_POSITIONS:
            continue

        fresh_wallet_count += 1

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

    # Build consensus objects
    new_consensus: Dict[str, SymbolConsensus] = {}

    for coin, d in sym_data.items():
        total_positioned = d["long_count"] + d["short_count"]

        # Count-based ratio (kept for API consumers)
        net_ratio = (d["long_count"] - d["short_count"]) / max(total_positioned, 1)

        # Notional-weighted directional ratio in [-1, +1]
        # (long$ - short$) / (long$ + short$) — pure dollars, no score multiplication
        total_notional = d["long_notional"] + d["short_notional"]
        notional_ratio = (d["long_notional"] - d["short_notional"]) / max(total_notional, 1.0)

        # Blend count ratio and notional ratio (60% notional, 40% count)
        # so a $10M whale outweighs ten $50k wallets, but pure count
        # still has some voice to prevent single-whale domination
        blended = 0.6 * notional_ratio + 0.4 * net_ratio

        # Derive trend from blended score
        if blended > _BULLISH_THRESHOLD:
            trend = "BULLISH"
        elif blended < _BEARISH_THRESHOLD:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        # Confidence = directional conviction * participation rate
        # 3L/1S with 4/100 wallets positioned = much weaker than
        # 30L/10S with 40/100 wallets positioned
        participation = total_positioned / max(fresh_wallet_count, 1)
        confidence = min(abs(blended) * math.sqrt(participation), 1.0)

        new_consensus[coin] = SymbolConsensus(
            symbol=coin,
            long_count=d["long_count"],
            short_count=d["short_count"],
            neutral_count=fresh_wallet_count - total_positioned,
            total_tracked=fresh_wallet_count,
            long_notional=d["long_notional"],
            short_notional=d["short_notional"],
            net_score=blended,
            net_ratio=net_ratio,
            trend=trend,
            confidence=confidence,
            top_longs=d["top_longs"][:5],
            top_shorts=d["top_shorts"][:5],
        )

    _consensus = new_consensus


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _normalize_coin(symbol: str) -> str:
    """Normalize any symbol format to bare coin name.

    Handles: "BTC", "BTC/USDT:USDT", "BTCUSDT", "1000PEPE/USDT:USDT"
    Uses anchored regex to avoid mangling coins that contain USDT/USDC substrings.
    """
    coin = symbol.split("/")[0].split(":")[0]
    coin = re.sub(r"(USDT|USDC|USD)$", "", coin)
    if coin.startswith("1000"):
        coin = coin[4:]
    return coin


def get_consensus(symbol: str) -> Optional[SymbolConsensus]:
    """Get consensus for a symbol (used by signal synthesizer).

    Accepts formats: "BTC", "BTC/USDT:USDT", "BTCUSDT"
    """
    return _consensus.get(_normalize_coin(symbol))


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
    coin = _normalize_coin(symbol)

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
    coin = _normalize_coin(symbol)

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
            # Fallback to oldest snapshot, but only if it's meaningfully
            # older than latest (at least half the window). Otherwise this
            # wallet was just added and we'd undercount changes.
            if latest.timestamp - snaps[0].timestamp >= (window_minutes * 60) / 2:
                prev = snaps[0]
            else:
                continue  # Not enough history for this wallet

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


# ---------------------------------------------------------------------------
# Trade reconstruction — detect opens/closes from snapshot diffs
# ---------------------------------------------------------------------------

# Persistent trade log per wallet: address -> list of completed trades
_trade_log: Dict[str, List[dict]] = {}

# Track "last known positions" per wallet for diff detection
_last_positions: Dict[str, Dict[str, dict]] = {}  # addr -> {coin: {side, size, entry_px, ...}}


def _reconstruct_trades() -> None:
    """Compare consecutive snapshots to detect position opens/closes.

    Called after each poll. Builds a persistent trade log that survives
    across the session (but not across restarts — in-memory only).
    """
    for wallet in _roster:
        snaps = _snapshots.get(wallet.address)
        if not snaps or len(snaps) < 2:
            continue

        latest = snaps[-1]
        addr = wallet.address

        # Build current position map: coin -> position dict
        curr_map: Dict[str, dict] = {}
        for pos in latest.positions:
            curr_map[pos.coin] = {
                "side": pos.side,
                "size": pos.size,
                "size_usd": pos.size_usd,
                "entry_px": pos.entry_px,
                "unrealized_pnl": pos.unrealized_pnl,
                "leverage": pos.leverage,
            }

        prev_map = _last_positions.get(addr, {})

        # Detect changes
        if addr not in _trade_log:
            _trade_log[addr] = []

        # Closed positions: in prev but not in curr
        for coin, prev_pos in prev_map.items():
            if coin not in curr_map:
                _trade_log[addr].append({
                    "coin": coin,
                    "side": prev_pos["side"],
                    "size_usd": prev_pos["size_usd"],
                    "entry_px": prev_pos["entry_px"],
                    "leverage": prev_pos["leverage"],
                    "pnl": prev_pos["unrealized_pnl"],  # Last known unrealized = approximate realized
                    "pnl_pct": (prev_pos["unrealized_pnl"] / max(prev_pos["size_usd"], 1)) * 100,
                    "opened_at": None,   # We don't know exact open time
                    "closed_at": latest.timestamp,
                    "status": "CLOSED",
                })

            # Flipped side: closed one direction, opened opposite
            elif curr_map[coin]["side"] != prev_pos["side"]:
                _trade_log[addr].append({
                    "coin": coin,
                    "side": prev_pos["side"],
                    "size_usd": prev_pos["size_usd"],
                    "entry_px": prev_pos["entry_px"],
                    "leverage": prev_pos["leverage"],
                    "pnl": prev_pos["unrealized_pnl"],
                    "pnl_pct": (prev_pos["unrealized_pnl"] / max(prev_pos["size_usd"], 1)) * 100,
                    "opened_at": None,
                    "closed_at": latest.timestamp,
                    "status": "FLIPPED",
                })

        # New positions: in curr but not in prev (logged as "OPEN" events)
        for coin in curr_map:
            if coin not in prev_map:
                _trade_log[addr].append({
                    "coin": coin,
                    "side": curr_map[coin]["side"],
                    "size_usd": curr_map[coin]["size_usd"],
                    "entry_px": curr_map[coin]["entry_px"],
                    "leverage": curr_map[coin]["leverage"],
                    "pnl": 0.0,
                    "pnl_pct": 0.0,
                    "opened_at": latest.timestamp,
                    "closed_at": None,
                    "status": "OPENED",
                })

        # Keep only last 200 trade events per wallet
        if len(_trade_log[addr]) > 200:
            _trade_log[addr] = _trade_log[addr][-200:]

        # Update last known positions
        _last_positions[addr] = curr_map


def get_wallet_trades(address: str, limit: int = 50) -> List[dict]:
    """Get reconstructed trade history for a wallet."""
    address = address.lower()
    trades = _trade_log.get(address, [])
    # Return most recent first
    return list(reversed(trades[-limit:]))


def get_wallet_profile(address: str) -> Optional[dict]:
    """Get comprehensive wallet profile with performance stats.

    Returns: current positions, trade history, win rate, avg PnL, etc.
    """
    address = address.lower()

    # Find wallet in roster
    wallet = next((w for w in _roster if w.address == address), None)
    if not wallet:
        return None

    snaps = _snapshots.get(address)
    latest = snaps[-1] if snaps else None

    # Trade stats from log
    trades = _trade_log.get(address, [])
    closed_trades = [t for t in trades if t["status"] in ("CLOSED", "FLIPPED")]

    wins = sum(1 for t in closed_trades if t["pnl"] > 0)
    losses = sum(1 for t in closed_trades if t["pnl"] <= 0)
    total_closed = len(closed_trades)
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    total_pnl = sum(t["pnl"] for t in closed_trades)
    avg_pnl_pct = sum(t["pnl_pct"] for t in closed_trades) / max(total_closed, 1)

    # Biggest win/loss
    best_trade = max(closed_trades, key=lambda t: t["pnl"]) if closed_trades else None
    worst_trade = min(closed_trades, key=lambda t: t["pnl"]) if closed_trades else None

    # Coin breakdown: which coins does this wallet trade most?
    coin_stats: Dict[str, dict] = {}
    for t in closed_trades:
        coin = t["coin"]
        if coin not in coin_stats:
            coin_stats[coin] = {"trades": 0, "wins": 0, "pnl": 0.0}
        coin_stats[coin]["trades"] += 1
        coin_stats[coin]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            coin_stats[coin]["wins"] += 1
    coin_breakdown = sorted(
        [{"coin": k, **v, "win_rate": round(v["wins"] / max(v["trades"], 1) * 100, 1)}
         for k, v in coin_stats.items()],
        key=lambda x: x["trades"], reverse=True,
    )

    # Account value history from snapshots
    av_history = []
    if snaps:
        for snap in snaps:
            if snap.account_value > 0:
                av_history.append({
                    "timestamp": snap.timestamp,
                    "value": round(snap.account_value, 2),
                })

    # Current positions
    current_positions = []
    if latest:
        for p in sorted(latest.positions, key=lambda x: x.size_usd, reverse=True):
            current_positions.append({
                "coin": p.coin,
                "side": p.side,
                "size": p.size,
                "size_usd": round(p.size_usd, 2),
                "entry_px": p.entry_px,
                "unrealized_pnl": round(p.unrealized_pnl, 2),
                "leverage": p.leverage,
                "liq_px": p.liq_px,
            })

    return {
        "address": address,
        "display_name": wallet.display_name,
        "rank": next((i + 1 for i, w in enumerate(_roster) if w.address == address), None),
        "account_value": wallet.account_value,
        "monthly_roi": wallet.roi,
        "monthly_pnl": wallet.pnl,
        "score": round(wallet.score, 1),
        # Performance stats
        "stats": {
            "total_trades": total_closed,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_pct": round(avg_pnl_pct, 2),
            "best_trade": {
                "coin": best_trade["coin"],
                "side": best_trade["side"],
                "pnl": round(best_trade["pnl"], 2),
                "pnl_pct": round(best_trade["pnl_pct"], 2),
            } if best_trade else None,
            "worst_trade": {
                "coin": worst_trade["coin"],
                "side": worst_trade["side"],
                "pnl": round(worst_trade["pnl"], 2),
                "pnl_pct": round(worst_trade["pnl_pct"], 2),
            } if worst_trade else None,
        },
        "coin_breakdown": coin_breakdown[:10],
        "current_positions": current_positions,
        "av_history": av_history,
        "trade_count_since_tracking": len(trades),
        "snapshot_count": len(snaps) if snaps else 0,
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
