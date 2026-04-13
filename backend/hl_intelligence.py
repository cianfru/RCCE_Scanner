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
from typing import Dict, List, Optional, Set

import aiohttp

from hl_persistence import (
    save_snapshots as _db_save_snapshots,
    save_trade_events as _db_save_trades,
    save_position_first_seen as _db_save_first_seen,
    load_snapshots as _db_load_snapshots,
    load_trade_log as _db_load_trades,
    load_position_first_seen as _db_load_first_seen,
    load_equity_history as _db_load_equity,
    load_full_trade_history as _db_load_full_trades,
    cleanup_old_data as _db_cleanup,
    get_db_stats as _db_stats,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
_HL_INFO_URL = "https://api.hyperliquid.xyz/info"

_ROSTER_REFRESH_INTERVAL = 24 * 60 * 60   # Daily

# Tiered polling — watchlist wallets get priority, rest of roster polled less often
_WATCHLIST_POLL_INTERVAL = 5 * 60          # 5 min for followed/watched wallets
_ROSTER_POLL_INTERVAL = 15 * 60            # 15 min for the rest of the roster
_ROSTER_IDLE_POLL_INTERVAL = 30 * 60       # 30 min for wallets with zero open positions
_POLL_INTERVAL = _WATCHLIST_POLL_INTERVAL  # Main loop cadence (fastest tier)

# In-memory snapshot depth per wallet.  Only recent snapshots are needed:
# trade reconstruction uses last 2, consensus uses last 1,
# get_position_changes() needs ~6 for its 30-min window.
# Historical equity curves are served from SQLite (30-day retention).
_POSITION_HISTORY_LEN = 20

# Staleness: skip snapshots older than this when computing consensus
_SNAPSHOT_MAX_AGE_S = 20 * 60              # 20 minutes (covers roster interval)

# Live eviction: remove wallets whose AV drops below this during polling
_EVICTION_THRESHOLD = 25_000               # $25K — half of MP minimum ($50K)
_DISPLAY_MIN_AV = 50_000                   # Only display wallets above $50K in roster/consensus

# Filtering thresholds
_MM_VLM_RATIO = 100                        # vlm/AV > 100 = market maker, skip
_MM_MAX_POSITIONS = 25                     # wallets with >25 concurrent positions = likely MM/vault
_ROI_WINDOW = "month"                      # Ranking window (was allTime)

# Cohort definitions
_ROSTER_COHORTS = {
    "money_printers": 300,  # top performers by ROI
    "smart_money": 300,      # largest wallets by AV
}
_MP_MIN_ROI_PCT = 30.0                     # Money Printers: 30% monthly ROI minimum
_MP_MIN_ACCOUNT_VALUE = 50_000             # Money Printers: $50k minimum AV
_SM_MIN_ACCOUNT_VALUE = 1_000_000          # Smart Money: $1M minimum AV
_POLL_SLEEP = 0.5                          # seconds between wallet fetches (was 1.5)

# Consensus thresholds
_BULLISH_THRESHOLD = 0.15                  # net_ratio > 15% = BULLISH
_BEARISH_THRESHOLD = -0.15                 # net_ratio < -15% = BEARISH

# Rate limiting
_CONCURRENCY = 20                          # Max concurrent HL API calls
_REQUEST_TIMEOUT = 15

# ---------------------------------------------------------------------------
# HIP-3 DEX (xyz) — TradFi / Commodity / FX perps on Hyperliquid
# ---------------------------------------------------------------------------
_XYZ_DEX = "xyz"

# Asset class lookup for xyz DEX instruments
_XYZ_ASSET_CLASS: Dict[str, str] = {
    # Commodities
    "GOLD": "commodity", "SILVER": "commodity", "COPPER": "commodity",
    "WTIOIL": "commodity", "BRENTOIL": "commodity", "NATGAS": "commodity",
    "PLATINUM": "commodity", "PALLADIUM": "commodity", "SOYBEAN": "commodity",
    "WHEAT": "commodity", "CORN": "commodity", "COTTON": "commodity",
    "SUGAR": "commodity", "COFFEE": "commodity", "COCOA": "commodity",
    "LUMBER": "commodity",
    # Equities
    "AAPL": "equity", "MSFT": "equity", "AMZN": "equity", "GOOGL": "equity",
    "META": "equity", "TSLA": "equity", "NVDA": "equity", "AMD": "equity",
    "NFLX": "equity", "COIN": "equity", "MSTR": "equity", "GME": "equity",
    "AMC": "equity", "PLTR": "equity", "SQ": "equity", "SHOP": "equity",
    "ABNB": "equity", "UBER": "equity", "RIVN": "equity", "LCID": "equity",
    # Indices
    "SP500": "index", "NDX100": "index", "DJI30": "index", "FTSE100": "index",
    "DAX40": "index", "NIK225": "index", "HSI": "index", "VIX": "index",
    "XYZ100": "index", "RUSSELL": "index",
    # FX pairs
    "EUR": "fx", "JPY": "fx", "GBP": "fx", "AUD": "fx", "CAD": "fx",
    "CHF": "fx", "NZD": "fx", "SEK": "fx", "NOK": "fx", "CNH": "fx",
    "MXN": "fx", "BRL": "fx", "TRY": "fx", "ZAR": "fx", "INR": "fx",
}

def _classify_xyz_asset(coin: str) -> str:
    """Return asset class for an xyz DEX instrument."""
    return _XYZ_ASSET_CLASS.get(coin.upper(), "tradfi")

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
    margin_used: float = 0.0
    return_on_equity: float = 0.0
    liq_distance_pct: float = 0.0   # abs(entry_px - liq_px) / entry_px * 100
    leverage_type: str = "cross"    # "cross" or "isolated"
    asset_class: str = "crypto"    # "crypto" | "commodity" | "equity" | "fx" | "index"
    dex: str = ""                  # "" = native HL, "xyz" = HIP-3 TradFi DEX


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
    avg_leverage: float = 0.0     # Average leverage across all positioned wallets
    top_longs: List[str] = field(default_factory=list)    # Top wallet addresses
    top_shorts: List[str] = field(default_factory=list)
    # Per-cohort consensus
    money_printer_trend: str = "NEUTRAL"
    money_printer_net_ratio: float = 0.0
    money_printer_long_count: int = 0
    money_printer_short_count: int = 0
    smart_money_trend: str = "NEUTRAL"
    smart_money_net_ratio: float = 0.0
    smart_money_long_count: int = 0
    smart_money_short_count: int = 0


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_roster: List[TrackedWallet] = []                       # merged & deduplicated (all unique wallets)
_roster_money_printers: List[TrackedWallet] = []         # top 200 by ROI
_roster_smart_money: List[TrackedWallet] = []            # top 200 by AV
_wallet_cohorts: Dict[str, set] = {}                     # address -> {"money_printer", "smart_money", "elite"}
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

# Asset index map: @index → name (e.g. @142 → "PENGU")
_asset_index_map: Dict[str, str] = {}

# Pressure Map stores
_wallet_orders: Dict[str, list] = {}          # address -> list of raw order dicts
_order_books: Dict[str, dict] = {}            # coin -> {"levels": ..., "timestamp": float}
_pressure_cache: Dict[str, dict] = {}         # coin -> computed pressure data
_ORDER_BOOK_POLL_INTERVAL = 60                # seconds (was 30)

# Tiered polling state
_xyz_active_wallets: Set[str] = set()      # Wallets that have had xyz positions
_last_roster_poll_at: float = 0            # Last time full roster was polled
_last_idle_roster_poll_at: float = 0       # Last time idle-roster wallets were polled
_ORDER_BOOK_TOP_N = 50                        # top N symbols by wallet count
_WALL_THRESHOLD_USD = 500_000                 # min notional for an order book "wall"


# ---------------------------------------------------------------------------
# Persistence — restore from SQLite on startup
# ---------------------------------------------------------------------------

def _restore_from_db() -> None:
    """Load persisted snapshots, trade log, and first-seen data from SQLite.

    Called once on startup before the first poll to restore state across
    Railway redeploys.
    """
    global _snapshots, _trade_log, _position_first_seen, _last_positions

    # 1. Restore snapshots (last 24h into in-memory deque)
    raw_snaps = _db_load_snapshots(max_age_hours=24)
    restored_snap_count = 0
    for address, snap_list in raw_snaps.items():
        dq = deque(maxlen=_POSITION_HISTORY_LEN)
        for s in snap_list:
            positions = []
            for p in s["positions"]:
                try:
                    positions.append(WalletPosition(
                        coin=p["coin"],
                        side=p["side"],
                        size=p.get("size", 0),
                        size_usd=p.get("size_usd", 0),
                        entry_px=p.get("entry_px", 0),
                        unrealized_pnl=p.get("unrealized_pnl", 0),
                        leverage=p.get("leverage", 1),
                        liq_px=p.get("liq_px", 0),
                        margin_used=p.get("margin_used", 0),
                        return_on_equity=p.get("return_on_equity", 0),
                        liq_distance_pct=p.get("liq_distance_pct", 0),
                        leverage_type=p.get("leverage_type", "cross"),
                        asset_class=p.get("asset_class", "crypto"),
                        dex=p.get("dex", ""),
                    ))
                except Exception:
                    continue

            dq.append(PositionSnapshot(
                timestamp=s["timestamp"],
                positions=positions,
                account_value=s["account_value"],
            ))
            restored_snap_count += 1
        _snapshots[address] = dq

        # Rebuild _last_positions from latest snapshot (needed for trade reconstruction diffs)
        if dq:
            latest = dq[-1]
            _last_positions[address] = {
                pos.coin: {
                    "side": pos.side,
                    "size": pos.size,
                    "size_usd": pos.size_usd,
                    "entry_px": pos.entry_px,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "leverage": pos.leverage,
                }
                for pos in latest.positions
            }

    # 2. Restore trade log
    _trade_log.update(_db_load_trades())

    # 3. Restore position first-seen
    _position_first_seen.update(_db_load_first_seen())

    logger.info(
        "HyperLens DB restore: %d snapshots for %d wallets, %d trades, %d first-seen entries",
        restored_snap_count, len(raw_snaps),
        sum(len(v) for v in _trade_log.values()),
        sum(len(v) for v in _position_first_seen.values()),
    )


# ---------------------------------------------------------------------------
# Leaderboard fetch & roster building
# ---------------------------------------------------------------------------

async def refresh_leaderboard() -> int:
    """Fetch HL leaderboard and rebuild the tracking roster using cohorts.

    Two independent cohorts are built from the same leaderboard data:
    - Money Printers: top 200 by ROI (>= 30%, AV >= $50k)
    - Smart Money: top 200 by AV (>= $1M)
    - Elite: wallets in BOTH cohorts (auto-tagged)

    Returns the number of wallets in the merged roster.
    """
    global _roster, _roster_money_printers, _roster_smart_money
    global _wallet_cohorts, _roster_updated_at

    logger.info("HyperLens: refreshing leaderboard roster (cohort mode)...")

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

    # Parse all wallets (filter out market makers only)
    all_wallets: List[TrackedWallet] = []
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

            # Market maker filter: vlm/AV ratio > 100 = likely MM/vault
            if account_value > 0 and monthly_vlm / account_value > _MM_VLM_RATIO:
                continue

            # Compute ranking score: monthly_roi * log(accountValue)
            score = roi * math.log(max(account_value, 1))

            all_wallets.append(TrackedWallet(
                address=address.lower(),
                display_name=display_name,
                account_value=account_value,
                pnl=pnl,
                roi=roi,
                score=score,
            ))
        except Exception:
            continue  # Skip malformed entries

    # --- Build Money Printers cohort ---
    mp_candidates = [
        w for w in all_wallets
        if w.roi >= _MP_MIN_ROI_PCT and w.account_value >= _MP_MIN_ACCOUNT_VALUE
    ]
    mp_candidates.sort(key=lambda w: w.roi, reverse=True)
    _roster_money_printers = mp_candidates[:_ROSTER_COHORTS["money_printers"]]
    mp_addresses = {w.address for w in _roster_money_printers}

    # --- Build Smart Money cohort ---
    sm_candidates = [
        w for w in all_wallets
        if w.account_value >= _SM_MIN_ACCOUNT_VALUE
    ]
    sm_candidates.sort(key=lambda w: w.account_value, reverse=True)
    _roster_smart_money = sm_candidates[:_ROSTER_COHORTS["smart_money"]]
    sm_addresses = {w.address for w in _roster_smart_money}

    # --- Build cohort tags ---
    _wallet_cohorts.clear()
    for addr in mp_addresses:
        _wallet_cohorts.setdefault(addr, set()).add("money_printer")
    for addr in sm_addresses:
        _wallet_cohorts.setdefault(addr, set()).add("smart_money")
    # Elite = in both cohorts
    elite_addresses = mp_addresses & sm_addresses
    for addr in elite_addresses:
        _wallet_cohorts[addr].add("elite")

    # --- Merge into deduplicated _roster ---
    seen: set = set()
    merged: List[TrackedWallet] = []
    # Add money printers first (preserves MP rank ordering), then smart money
    for w in _roster_money_printers:
        if w.address not in seen:
            seen.add(w.address)
            merged.append(w)
    for w in _roster_smart_money:
        if w.address not in seen:
            seen.add(w.address)
            merged.append(w)
    _roster = merged
    _roster_updated_at = time.time()

    # Prune ghost wallets from _snapshots — addresses that were tracked in a
    # previous refresh but no longer qualify.  Consensus already iterates
    # _roster (not _snapshots) so ghosts don't affect signals, but they waste
    # RAM and inflate the "with data" counter, confusing the UI.
    roster_addrs = {w.address for w in _roster}
    ghost_addrs = [a for a in _snapshots if a not in roster_addrs]
    for a in ghost_addrs:
        del _snapshots[a]
        _last_positions.pop(a, None)
        _trade_log.pop(a, None)
        _position_first_seen.pop(a, None)
        _wallet_orders.pop(a, None)

    logger.info(
        "HyperLens: cohort roster built — %d total (%d money_printers, %d smart_money, "
        "%d elite) from %d parsed (%d raw rows). Pruned %d ghost wallets.",
        len(_roster),
        len(_roster_money_printers),
        len(_roster_smart_money),
        len(elite_addresses),
        len(all_wallets),
        len(rows),
        len(ghost_addrs),
    )
    return len(_roster)


# ---------------------------------------------------------------------------
# Position polling
# ---------------------------------------------------------------------------

async def _fetch_wallet_positions(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    wallet: TrackedWallet,
    full: bool = True,
) -> Optional[PositionSnapshot]:
    """Fetch open positions for a single wallet.

    Args:
        full: If True (watchlist tier), fetch all 3 endpoints (positions +
              orders + xyz DEX).  If False (roster tier), fetch positions
              only — saves 2 API calls per wallet.
    """
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

        # Orders — watchlist only (most wallets have no stops/TPs; book walls
        # come from L2 data which is fetched separately)
        if full:
            try:
                async with session.post(
                    _HL_INFO_URL,
                    json={"type": "frontendOpenOrders", "user": wallet.address},
                ) as resp:
                    if resp.status == 200:
                        orders_raw = await resp.json(content_type=None)
                        if isinstance(orders_raw, list):
                            _wallet_orders[wallet.address] = orders_raw
                        else:
                            _wallet_orders[wallet.address] = []
            except Exception:
                pass

        # xyz DEX — only for watchlist tier OR wallets known to have xyz positions
        xyz_data = None
        fetch_xyz = full or wallet.address in _xyz_active_wallets
        if fetch_xyz:
            try:
                async with session.post(
                    _HL_INFO_URL,
                    json={"type": "clearinghouseState", "user": wallet.address, "dex": _XYZ_DEX},
                ) as resp:
                    if resp.status == 200:
                        xyz_data = await resp.json(content_type=None)
            except Exception:
                pass

    if not data:
        return None

    # Parse positions helper
    def _parse_positions(raw: dict, dex: str = "", asset_class: str = "crypto") -> List[WalletPosition]:
        result: List[WalletPosition] = []
        for ap in raw.get("assetPositions", []):
            pos = ap.get("position", {})
            szi = float(pos.get("szi", 0))
            if szi == 0:
                continue

            entry_px = float(pos.get("entryPx", 0))
            coin = pos.get("coin", "")
            lev_val = pos.get("leverage", {})
            lev = float(lev_val.get("value", 1)) if isinstance(lev_val, dict) else float(lev_val or 1)
            lev_type = lev_val.get("type", "cross") if isinstance(lev_val, dict) else "cross"

            liq_px = float(pos.get("liquidationPx", 0) or 0)
            margin_used = float(pos.get("marginUsed", 0) or 0)
            roe = float(pos.get("returnOnEquity", 0) or 0)

            # Calculate liquidation distance percentage
            liq_dist_pct = 0.0
            if entry_px > 0 and liq_px > 0:
                liq_dist_pct = abs(entry_px - liq_px) / entry_px * 100

            # Determine asset class for xyz DEX instruments
            ac = _classify_xyz_asset(coin) if dex == _XYZ_DEX else asset_class

            result.append(WalletPosition(
                coin=coin,
                side="LONG" if szi > 0 else "SHORT",
                size=abs(szi),
                size_usd=abs(szi) * entry_px,
                entry_px=entry_px,
                unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                leverage=lev,
                liq_px=liq_px,
                margin_used=margin_used,
                return_on_equity=roe,
                liq_distance_pct=round(liq_dist_pct, 2),
                leverage_type=lev_type,
                asset_class=ac,
                dex=dex,
            ))
        return result

    # Parse crypto positions (native HL)
    positions = _parse_positions(data)

    # Parse TradFi positions (xyz DEX)
    if xyz_data:
        xyz_positions = _parse_positions(xyz_data, dex=_XYZ_DEX)
        if xyz_positions:
            positions.extend(xyz_positions)
            _xyz_active_wallets.add(wallet.address)
            logger.debug("HyperLens: %s has %d xyz DEX positions", wallet.address[:8], len(xyz_positions))

    # Extract account value (from native HL — xyz has separate margin)
    margin = data.get("marginSummary", {})
    av = float(margin.get("accountValue", 0) or 0)

    # Add xyz account value if available
    if xyz_data:
        xyz_margin = xyz_data.get("marginSummary", {})
        xyz_av = float(xyz_margin.get("accountValue", 0) or 0)
        av += xyz_av

    return PositionSnapshot(
        timestamp=time.time(),
        positions=positions,
        account_value=av,
    )


def _get_watchlist_addresses() -> Set[str]:
    """Return the set of wallet addresses that should be polled at high frequency.

    Includes: wallets followed via whale_follows (starred on frontend) +
    wallets monitored via position_monitor (/watch TG command).
    """
    addrs: Set[str] = set()
    try:
        import whale_follows as wf
        addrs.update(wf.get_all_followed_addresses())
    except ImportError:
        pass
    try:
        from position_monitor import PositionMonitor
        monitor = PositionMonitor.get()
        for w in monitor.watchers:
            addrs.add(w.address.lower())
    except Exception:
        pass
    return addrs


def _wallet_has_open_positions(address: str) -> bool:
    """Check if wallet's last-known snapshot has any open positions.

    Returns True (assume active) if no snapshot data exists yet, so
    newly-added wallets get polled at normal frequency until we know.
    """
    dq = _snapshots.get(address)
    if not dq:
        return True  # No data yet — assume active
    return len(dq[-1].positions) > 0


async def poll_positions() -> int:
    """Poll positions using tiered strategy.

    - **Watchlist tier** (every 5 min): followed/watched wallets get full
      polling — positions + orders + xyz DEX (3 API calls).
    - **Active roster** (every 15 min): wallets with ≥1 open position —
      positions only (1 API call).
    - **Idle roster** (every 30 min): wallets with zero open positions —
      they might open one, but no urgency.

    In practice most wallets have zero positions at any given time, so
    this reduces API volume significantly.
    """
    global _last_poll_at, _poll_count, _consensus_updated_at, _last_roster_poll_at
    global _last_idle_roster_poll_at
    global _roster, _roster_money_printers, _roster_smart_money

    # Refresh asset index map if empty (resolves @142 → PENGU etc.)
    if not _asset_index_map:
        await _refresh_asset_index_map()

    if not _roster:
        logger.debug("HyperLens: no roster — skipping poll")
        return 0

    now = time.time()
    watchlist_addrs = _get_watchlist_addresses()
    roster_due = (now - _last_roster_poll_at) >= _ROSTER_POLL_INTERVAL
    idle_roster_due = (now - _last_idle_roster_poll_at) >= _ROSTER_IDLE_POLL_INTERVAL

    # Split roster into tiers based on open positions
    watchlist_wallets = []
    active_roster_wallets = []
    idle_roster_wallets = []
    for w in _roster:
        if w.address.lower() in watchlist_addrs:
            watchlist_wallets.append(w)
        elif _wallet_has_open_positions(w.address):
            if roster_due:
                active_roster_wallets.append(w)
        else:
            if idle_roster_due:
                idle_roster_wallets.append(w)

    wallets_to_poll = watchlist_wallets + active_roster_wallets + idle_roster_wallets
    if not wallets_to_poll:
        logger.debug("HyperLens: no wallets due for polling this cycle")
        return 0

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)
    success_count = 0

    # Build tasks with tier-appropriate full/light polling
    watchlist_set = {w.address for w in watchlist_wallets}

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            _fetch_wallet_positions(
                session, semaphore, w,
                full=(w.address in watchlist_set),
            )
            for w in wallets_to_poll
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for wallet, result in zip(wallets_to_poll, results):
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

    _last_poll_at = now
    _poll_count += 1
    if roster_due:
        _last_roster_poll_at = now
    if idle_roster_due:
        _last_idle_roster_poll_at = now

    # --- Safe eviction: remove wallets whose AV dropped below threshold ---
    # Build new lists (atomic reference swap — safe for concurrent readers).
    evicted_addrs: Set[str] = set()
    for w in _roster:
        if w.account_value > 0 and w.account_value < _EVICTION_THRESHOLD:
            evicted_addrs.add(w.address)

    if evicted_addrs:
        _roster = [w for w in _roster if w.address not in evicted_addrs]
        _roster_money_printers = [w for w in _roster_money_printers if w.address not in evicted_addrs]
        _roster_smart_money = [w for w in _roster_smart_money if w.address not in evicted_addrs]
        for addr in evicted_addrs:
            _wallet_cohorts.pop(addr, None)
        logger.info(
            "HyperLens: evicted %d wallets below $%dk AV",
            len(evicted_addrs), _EVICTION_THRESHOLD // 1000,
        )

    # Prune stale wallet orders for addresses no longer in roster
    roster_addrs = {w.address for w in _roster}
    stale_order_keys = [a for a in _wallet_orders if a not in roster_addrs]
    for a in stale_order_keys:
        del _wallet_orders[a]

    # Reconstruct trades from snapshot diffs (must run before consensus)
    _reconstruct_trades()

    # Recompute consensus
    _recompute_consensus()
    _consensus_updated_at = time.time()

    # Persist to SQLite (non-blocking — runs in background thread)
    try:
        _db_save_snapshots(_snapshots)
        _db_save_trades(_trade_log, since_timestamp=_last_poll_at - _POLL_INTERVAL)
        _db_save_first_seen(_position_first_seen)
    except Exception as exc:
        logger.warning("HyperLens DB: save error: %s", exc)

    # Logging
    tier_info = f"watchlist={len(watchlist_wallets)}"
    if roster_due:
        tier_info += f", active={len(active_roster_wallets)}"
    if idle_roster_due:
        tier_info += f", idle={len(idle_roster_wallets)}"
    else:
        idle_count = sum(1 for w in _roster
                         if w.address.lower() not in watchlist_addrs
                         and not _wallet_has_open_positions(w.address))
        if idle_count > 0:
            tier_info += f", idle_skipped={idle_count}"
    if evicted_addrs:
        tier_info += f", evicted={len(evicted_addrs)}"
    logger.info(
        "HyperLens poll #%d: %d/%d wallets (%s), %d symbols with consensus",
        _poll_count, success_count, len(wallets_to_poll), tier_info, len(_consensus),
    )
    return success_count


# ---------------------------------------------------------------------------
# Consensus computation
# ---------------------------------------------------------------------------

def _compute_cohort_trend(
    long_count: int, short_count: int,
    long_notional: float = 0.0, short_notional: float = 0.0,
) -> tuple:
    """Compute trend and net_ratio for a cohort subset.

    Uses same adaptive notional+count blend as aggregate consensus
    so cohort trends match the overall methodology.
    Returns (trend, net_ratio).
    """
    total = long_count + short_count
    if total == 0:
        return ("NEUTRAL", 0.0)
    count_ratio = (long_count - short_count) / total
    total_notional = long_notional + short_notional
    if total_notional > 0:
        notional_ratio = (long_notional - short_notional) / total_notional
        skew = abs(notional_ratio)
        nw = 0.85 if skew > 0.5 else 0.70
        blended = nw * notional_ratio + (1.0 - nw) * count_ratio
    else:
        blended = count_ratio
    if blended > _BULLISH_THRESHOLD:
        trend = "BULLISH"
    elif blended < _BEARISH_THRESHOLD:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"
    return (trend, blended)


def _recompute_consensus() -> None:
    """Aggregate latest positions across all wallets into per-symbol consensus.

    Trend is derived from notional-weighted net_score (not raw wallet count)
    so a single whale with $10M has more influence than ten $50k wallets.
    Stale snapshots (>15min old) are excluded to prevent ghost data.

    Also computes per-cohort consensus (money_printer / smart_money).
    """
    global _consensus

    now = time.time()
    score_map = {w.address: w.score for w in _roster}
    mp_addresses = {w.address for w in _roster_money_printers}
    sm_addresses = {w.address for w in _roster_smart_money}

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

        # AV filter: consensus only counts quality wallets ($50k+)
        if latest.account_value > 0 and latest.account_value < _DISPLAY_MIN_AV:
            continue

        fresh_wallet_count += 1
        addr = wallet.address
        is_mp = addr in mp_addresses
        is_sm = addr in sm_addresses

        for pos in latest.positions:
            # Normalize coin name: kPEPE→PEPE, preserve existing xyz: prefix
            raw = pos.coin
            if raw.startswith("xyz:") or pos.dex == _XYZ_DEX:
                # xyz DEX coins — ensure exactly one xyz: prefix
                bare = raw.split(":", 1)[1] if ":" in raw else raw
                coin = f"xyz:{bare}"
            else:
                coin = _normalize_coin(raw)
            if coin not in sym_data:
                sym_data[coin] = {
                    "long_count": 0, "short_count": 0,
                    "long_notional": 0.0, "short_notional": 0.0,
                    "weighted_sum": 0.0,
                    "leverages": [],
                    "top_longs": [], "top_shorts": [],
                    # Per-cohort counters + notional
                    "mp_long": 0, "mp_short": 0,
                    "mp_long_notional": 0.0, "mp_short_notional": 0.0,
                    "sm_long": 0, "sm_short": 0,
                    "sm_long_notional": 0.0, "sm_short_notional": 0.0,
                }

            d = sym_data[coin]
            w_score = score_map.get(wallet.address, 1.0)
            d["leverages"].append(pos.leverage)

            # Weight consensus by notional size * wallet score
            # so a $5M position from a top trader counts more than a $50k one
            notional_weight = pos.size_usd * w_score

            if pos.side == "LONG":
                d["long_count"] += 1
                d["long_notional"] += pos.size_usd
                d["weighted_sum"] += notional_weight
                d["top_longs"].append(wallet.address)
                if is_mp:
                    d["mp_long"] += 1
                    d["mp_long_notional"] += pos.size_usd
                if is_sm:
                    d["sm_long"] += 1
                    d["sm_long_notional"] += pos.size_usd
            else:
                d["short_count"] += 1
                d["short_notional"] += pos.size_usd
                d["weighted_sum"] -= notional_weight
                d["top_shorts"].append(wallet.address)
                if is_mp:
                    d["mp_short"] += 1
                    d["mp_short_notional"] += pos.size_usd
                if is_sm:
                    d["sm_short"] += 1
                    d["sm_short_notional"] += pos.size_usd

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

        # Adaptive blend: notional weight increases when dollar imbalance is extreme.
        # Base: 70% notional, 30% count.  When notional ratio > 0.5 (3:1+ dollar skew),
        # boost to 85/15 so whales can't be drowned out by many small counter-positions.
        notional_skew = abs(notional_ratio)
        nw = 0.85 if notional_skew > 0.5 else 0.70
        blended = nw * notional_ratio + (1.0 - nw) * net_ratio

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

        # Average leverage across all positioned wallets for this symbol
        sym_leverages = d["leverages"]
        sym_avg_lev = sum(sym_leverages) / len(sym_leverages) if sym_leverages else 0.0

        # Per-cohort trend computation (same adaptive blend as aggregate)
        mp_trend, mp_net_ratio = _compute_cohort_trend(
            d["mp_long"], d["mp_short"], d["mp_long_notional"], d["mp_short_notional"])
        sm_trend, sm_net_ratio = _compute_cohort_trend(
            d["sm_long"], d["sm_short"], d["sm_long_notional"], d["sm_short_notional"])

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
            avg_leverage=round(sym_avg_lev, 2),
            top_longs=d["top_longs"][:5],
            top_shorts=d["top_shorts"][:5],
            # Per-cohort consensus
            money_printer_trend=mp_trend,
            money_printer_net_ratio=round(mp_net_ratio, 4),
            money_printer_long_count=d["mp_long"],
            money_printer_short_count=d["mp_short"],
            smart_money_trend=sm_trend,
            smart_money_net_ratio=round(sm_net_ratio, 4),
            smart_money_long_count=d["sm_long"],
            smart_money_short_count=d["sm_short"],
        )

    _consensus = new_consensus


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Reverse map: HL coin names → scanner base names (kPEPE→PEPE, POL→MATIC, etc.)
_HL_REVERSE_MAP: Dict[str, str] = {
    "kPEPE": "PEPE", "kSHIB": "SHIB", "kBONK": "BONK", "kFLOKI": "FLOKI",
    "POL": "MATIC", "RENDER": "RNDR", "S": "FTM",
}


def _normalize_coin(symbol: str) -> str:
    """Normalize any symbol format to bare coin name.

    Handles: "BTC", "BTC/USDT:USDT", "BTCUSDT", "1000PEPE/USDT:USDT",
    HL names like "kPEPE", "POL", "RENDER", "S".
    Also preserves xyz DEX prefix: "xyz:GOLD" stays "xyz:GOLD".
    """
    # Preserve xyz DEX prefix (HIP-3 TradFi instruments)
    if symbol.lower().startswith("xyz:"):
        return f"xyz:{symbol.split(':',1)[1].upper()}"

    coin = symbol.split("/")[0].split(":")[0]
    coin = re.sub(r"(USDT|USDC|USD)$", "", coin)
    if coin.startswith("1000"):
        coin = coin[4:]
    # Map HL-specific names back to scanner base names
    coin = _HL_REVERSE_MAP.get(coin, coin)
    # Resolve @index IDs (e.g. @142 → PENGU)
    if coin.startswith("@"):
        coin = _asset_index_map.get(coin, coin)
    return coin


async def _refresh_asset_index_map():
    """Fetch HL perps universe and build @index → name map."""
    global _asset_index_map
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _HL_INFO_URL,
                json={"type": "meta"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return
                data = await resp.json(content_type=None)
        universe = data.get("universe", [])
        new_map = {}
        for idx, asset in enumerate(universe):
            name = asset.get("name") or asset.get("coin", "")
            if name:
                new_map[f"@{idx}"] = name
        if new_map:
            _asset_index_map = new_map
            logger.info("Refreshed asset index map: %d entries", len(new_map))
    except Exception as e:
        logger.warning("Failed to refresh asset index map: %s", e)


def get_consensus(symbol: str) -> Optional[SymbolConsensus]:
    """Get consensus for a symbol (used by signal synthesizer).

    Accepts formats: "BTC", "BTC/USDT:USDT", "BTCUSDT"
    """
    return _consensus.get(_normalize_coin(symbol))


def get_all_consensus() -> Dict[str, SymbolConsensus]:
    """Get all symbol consensus data."""
    return dict(_consensus)


def get_roster(cohort: Optional[str] = None, min_av: float = _DISPLAY_MIN_AV) -> List[dict]:
    """Get current roster as serializable dicts.

    Args:
        cohort: Optional filter — "money_printers", "smart_money", or None for all.
        min_av: Minimum account value to display (default $50k).
                Pass 0 to show all wallets (debug mode).

    Each wallet includes cohort tags and cohort-specific rank.
    """
    # Select source list based on cohort filter
    if cohort == "money_printers":
        source = _roster_money_printers
    elif cohort == "smart_money":
        source = _roster_smart_money
    else:
        source = _roster

    # Filter by minimum account value (keep wallets not yet polled)
    if min_av > 0:
        source = [w for w in source
                  if w.account_value >= min_av or w.address not in _snapshots]

    # Pre-build cohort rank lookups
    mp_rank = {w.address: i + 1 for i, w in enumerate(_roster_money_printers)}
    sm_rank = {w.address: i + 1 for i, w in enumerate(_roster_smart_money)}

    result = []
    for i, w in enumerate(source):
        # Get latest position count (crypto + tradfi)
        snaps = _snapshots.get(w.address)
        pos_count = len(snaps[-1].positions) if snaps else 0
        xyz_count = sum(1 for p in snaps[-1].positions if p.dex == _XYZ_DEX) if snaps else 0

        cohorts_list = sorted(_wallet_cohorts.get(w.address, set()))

        entry = {
            "rank": i + 1,
            "address": w.address,
            "display_name": w.display_name,
            "account_value": w.account_value,
            "pnl": w.pnl,
            "roi": w.roi,
            "score": round(w.score, 1),
            "position_count": pos_count,
            "tradfi_position_count": xyz_count,
            "cohorts": cohorts_list,
        }

        # Add cohort-specific ranks when available
        if w.address in mp_rank:
            entry["mp_rank"] = mp_rank[w.address]
        if w.address in sm_rank:
            entry["sm_rank"] = sm_rank[w.address]

        result.append(entry)
    return result


def get_wallet_positions(address: str) -> Optional[dict]:
    """Get latest positions for a specific wallet."""
    address = address.lower()
    snaps = _snapshots.get(address)
    if not snaps:
        return None

    latest = snaps[-1]
    now = time.time()
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
                "margin_used": round(p.margin_used, 2),
                "return_on_equity": round(p.return_on_equity, 4),
                "liq_distance_pct": p.liq_distance_pct,
                "leverage_type": p.leverage_type,
                "position_age_s": round(now - fs, 0) if (fs := _position_first_seen.get(address, {}).get(p.coin)) else None,
                "asset_class": p.asset_class,
                "dex": p.dex,
            }
            for p in latest.positions
        ],
    }


def get_symbol_positions(symbol: str) -> List[dict]:
    """Get all wallet positions for a specific symbol.

    Uses the same staleness + MM filters as consensus so counts match.
    """
    coin = _normalize_coin(symbol)
    now = time.time()

    result = []
    for wallet in _roster:
        snaps = _snapshots.get(wallet.address)
        if not snaps:
            continue
        latest = snaps[-1]
        # Staleness check — same as consensus
        if now - latest.timestamp > _SNAPSHOT_MAX_AGE_S:
            continue
        # MM filter — same as consensus
        if len(latest.positions) > _MM_MAX_POSITIONS:
            continue
        for pos in latest.positions:
            # Normalize pos.coin the same way as consensus
            raw = pos.coin
            if raw.startswith("xyz:") or pos.dex == _XYZ_DEX:
                bare = raw.split(":", 1)[1] if ":" in raw else raw
                pos_coin = f"xyz:{bare}"
            else:
                pos_coin = _normalize_coin(raw)
            if pos_coin == coin:
                # PnL % = unrealized_pnl / margin_used (ROE)
                pnl_pct = round(pos.return_on_equity * 100, 2) if pos.return_on_equity else (
                    round(pos.unrealized_pnl / max(pos.margin_used, 1) * 100, 2) if pos.margin_used > 0 else 0
                )
                now = time.time()
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
                    "pnl_pct": pnl_pct,
                    "leverage": pos.leverage,
                    "liq_distance_pct": pos.liq_distance_pct,
                    "position_age_s": round(now - fs, 0) if (fs := _position_first_seen.get(wallet.address, {}).get(pos.coin)) else None,
                    "cohorts": sorted(_wallet_cohorts.get(wallet.address, set())),
                    "asset_class": pos.asset_class,
                    "dex": pos.dex,
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

# Track when a position was first seen (for position age): addr -> {coin: timestamp}
_position_first_seen: Dict[str, Dict[str, float]] = {}


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

        # Initialize first-seen tracker for this wallet (needed for closed cleanup)
        if addr not in _position_first_seen:
            _position_first_seen[addr] = {}

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
                    "opened_at": _position_first_seen.get(addr, {}).get(coin),
                    "closed_at": latest.timestamp,
                    "status": "CLOSED",
                })
                # Clean up first-seen entry for closed position
                _position_first_seen.get(addr, {}).pop(coin, None)

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
                    "opened_at": _position_first_seen.get(addr, {}).get(coin),
                    "closed_at": latest.timestamp,
                    "status": "FLIPPED",
                })
                # Reset first-seen for flipped position (new direction)
                _position_first_seen[addr][coin] = latest.timestamp

        # New positions: in curr but not in prev (logged as "OPEN" events)
        for coin in curr_map:
            if coin not in prev_map:
                # Record first-seen timestamp for position age tracking
                _position_first_seen[addr][coin] = latest.timestamp
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

    # --- Whale follow alerts ---
    _process_followed_wallet_events()


def _process_followed_wallet_events() -> None:
    """Check recent trades against followed wallet lists and fire TG alerts."""
    try:
        import whale_follows as wf
    except ImportError:
        return

    followed = wf.get_all_followed_addresses()
    if not followed:
        return

    now = time.time()
    tg_links = wf.get_all_tg_links()

    for addr_lower in followed:
        trades = _trade_log.get(addr_lower, [])
        if not trades:
            # Try original case
            for k in _trade_log:
                if k.lower() == addr_lower:
                    trades = _trade_log[k]
                    break
        if not trades:
            continue

        # Only look at very recent trades (last 10 min = 2 poll cycles)
        recent = [t for t in trades if t.get("closed_at") and t["closed_at"] > now - 600
                  or t.get("opened_at") and t["opened_at"] > now - 600]

        for trade in recent:
            size_usd = trade.get("size_usd", 0)
            if size_usd < wf.MIN_SIZE_USD:
                continue

            # Build event
            cohorts = _wallet_cohorts.get(addr_lower, set())
            if not cohorts:
                for k, v in _wallet_cohorts.items():
                    if k.lower() == addr_lower:
                        cohorts = v
                        break
            cohort_label = "elite" if "elite" in cohorts else (
                "money_printer" if "money_printer" in cohorts else (
                    "smart_money" if "smart_money" in cohorts else "tracked"
                )
            )

            event = {
                "wallet": addr_lower,
                "coin": trade.get("coin", "?"),
                "action": trade.get("status", "?"),
                "side": trade.get("side", "?"),
                "size_usd": size_usd,
                "entry_px": trade.get("entry_px", 0),
                "leverage": trade.get("leverage", 1),
                "pnl": trade.get("pnl", 0),
                "pnl_pct": trade.get("pnl_pct", 0),
                "timestamp": trade.get("closed_at") or trade.get("opened_at") or now,
                "cohort": cohort_label,
            }

            # Deduplicate: don't push same event twice
            existing = wf.get_events({addr_lower}, since=now - 600)
            is_dup = any(
                e.get("coin") == event["coin"]
                and e.get("action") == event["action"]
                and abs(e.get("timestamp", 0) - event["timestamp"]) < 60
                for e in existing
            )
            if is_dup:
                continue

            wf.push_event(event)

            # Fire TG alerts to all users following this wallet
            users = wf.get_users_following(addr_lower)
            for user in users:
                chat_id = wf.get_tg_chat_id(user)
                if chat_id:
                    _fire_tg_whale_alert(chat_id, event)


def _fire_tg_whale_alert(chat_id: int, event: dict) -> None:
    """Send a whale trade alert via Telegram."""
    import asyncio

    action = event.get("action", "?")
    side = event.get("side", "?")
    coin = event.get("coin", "?")
    size = event.get("size_usd", 0)
    entry = event.get("entry_px", 0)
    lev = event.get("leverage", 1)
    cohort = event.get("cohort", "tracked").replace("_", " ").title()
    wallet = event.get("wallet", "")
    pnl = event.get("pnl", 0)
    pnl_pct = event.get("pnl_pct", 0)

    # Format size
    if size >= 1e6:
        size_str = f"${size / 1e6:.1f}M"
    elif size >= 1e3:
        size_str = f"${size / 1e3:.0f}K"
    else:
        size_str = f"${size:.0f}"

    wallet_short = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet

    if action == "OPENED":
        emoji = "🟢" if side == "LONG" else "🔴"
        text = (
            f"🐋 {cohort} wallet {action} {side} {coin}\n"
            f"{emoji} {size_str} @ ${entry:,.2f} · {lev:.0f}x\n"
            f"📊 {wallet_short}"
        )
    elif action == "CLOSED":
        pnl_emoji = "✅" if pnl >= 0 else "❌"
        pnl_sign = "+" if pnl >= 0 else ""
        if abs(pnl) >= 1e3:
            pnl_str = f"${pnl / 1e3:{pnl_sign}.1f}K"
        else:
            pnl_str = f"${pnl:{pnl_sign},.0f}"
        text = (
            f"🐋 {cohort} wallet {action} {side} {coin}\n"
            f"{pnl_emoji} PnL: {pnl_str} ({pnl_pct:+.1f}%)\n"
            f"📊 {wallet_short}"
        )
    elif action == "FLIPPED":
        text = (
            f"🐋 {cohort} wallet FLIPPED {coin}\n"
            f"🔄 Was {side} → now {'SHORT' if side == 'LONG' else 'LONG'}\n"
            f"💰 {size_str} @ ${entry:,.2f} · {lev:.0f}x\n"
            f"📊 {wallet_short}"
        )
    else:
        return

    try:
        from telegram_bot import get_telegram_bot
        bot = get_telegram_bot()
        if bot.app and bot._running:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    bot.app.bot.send_message(chat_id=chat_id, text=text)
                )
            else:
                loop.run_until_complete(
                    bot.app.bot.send_message(chat_id=chat_id, text=text)
                )
    except Exception as e:
        logger.debug("TG whale alert failed for chat %s: %s", chat_id, e)


def get_wallet_trades(address: str, limit: int = 50) -> List[dict]:
    """Get reconstructed trade history for a wallet.

    Pulls from DB for extended history (500 trades) with in-memory fallback.
    """
    address = address.lower()
    # Try DB first for richer history
    db_trades = _db_load_full_trades(address, limit=limit)
    if db_trades:
        return db_trades  # Already sorted most-recent-first by DB query
    # Fallback to in-memory
    trades = _trade_log.get(address, [])
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

    # Trade stats — prefer DB (full history) over in-memory (200 cap)
    trades = _db_load_full_trades(address, limit=500) or _trade_log.get(address, [])
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

    # Account value history — prefer DB (up to 30 days) over in-memory deque (24h)
    av_history = _db_load_equity(address, days=30)
    if not av_history and snaps:
        # Fallback to in-memory if DB is empty (first run)
        for snap in snaps:
            if snap.account_value > 0:
                av_history.append({
                    "timestamp": snap.timestamp,
                    "value": round(snap.account_value, 2),
                })

    # Current positions (with age and new fields)
    now = time.time()
    current_positions = []
    total_margin_used = 0.0
    leverages = []
    liq_distances = []
    total_notional = 0.0
    max_position_usd = 0.0

    if latest:
        for p in sorted(latest.positions, key=lambda x: x.size_usd, reverse=True):
            # Position age: seconds since first seen
            first_seen = _position_first_seen.get(address, {}).get(p.coin)
            age_s = round(now - first_seen, 0) if first_seen else None

            current_positions.append({
                "coin": p.coin,
                "side": p.side,
                "size": p.size,
                "size_usd": round(p.size_usd, 2),
                "entry_px": p.entry_px,
                "unrealized_pnl": round(p.unrealized_pnl, 2),
                "leverage": p.leverage,
                "liq_px": p.liq_px,
                "margin_used": round(p.margin_used, 2),
                "return_on_equity": round(p.return_on_equity, 4),
                "liq_distance_pct": p.liq_distance_pct,
                "leverage_type": p.leverage_type,
                "position_age_s": age_s,
                "asset_class": p.asset_class,
                "dex": p.dex,
            })

            # Accumulate stats for leverage_stats and risk_score
            total_margin_used += p.margin_used
            leverages.append(p.leverage)
            if p.liq_distance_pct > 0:
                liq_distances.append(p.liq_distance_pct)
            total_notional += p.size_usd
            if p.size_usd > max_position_usd:
                max_position_usd = p.size_usd

    # Leverage stats
    avg_leverage = sum(leverages) / len(leverages) if leverages else 0.0
    max_leverage = max(leverages) if leverages else 0.0
    leverage_stats = {
        "avg_leverage": round(avg_leverage, 2),
        "max_leverage": round(max_leverage, 2),
        "total_margin_used": round(total_margin_used, 2),
    }

    # Risk score (0-100): blend of leverage risk, liq proximity, and concentration
    # Higher = riskier
    lev_risk = min(avg_leverage / 20.0, 1.0) * 40          # 0-40 pts (20x = max)
    avg_liq_dist = sum(liq_distances) / len(liq_distances) if liq_distances else 100.0
    liq_risk = max(0, (1.0 - avg_liq_dist / 50.0)) * 30   # 0-30 pts (closer liq = higher)
    concentration = (max_position_usd / total_notional) if total_notional > 0 else 0.0
    conc_risk = concentration * 30                          # 0-30 pts (100% in one = max)
    risk_score = round(min(lev_risk + liq_risk + conc_risk, 100.0), 1)

    # Cohort info
    cohorts_list = sorted(_wallet_cohorts.get(address, set()))
    mp_rank_val = next((i + 1 for i, w in enumerate(_roster_money_printers) if w.address == address), None)
    sm_rank_val = next((i + 1 for i, w in enumerate(_roster_smart_money) if w.address == address), None)

    return {
        "address": address,
        "display_name": wallet.display_name,
        "rank": next((i + 1 for i, w in enumerate(_roster) if w.address == address), None),
        "account_value": wallet.account_value,
        "monthly_roi": wallet.roi,
        "monthly_pnl": wallet.pnl,
        "score": round(wallet.score, 1),
        "cohorts": cohorts_list,
        "mp_rank": mp_rank_val,
        "sm_rank": sm_rank_val,
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
        "leverage_stats": leverage_stats,
        "risk_score": risk_score,
        "av_history": av_history,
        "trade_count_since_tracking": len(trades),
        "snapshot_count": len(snaps) if snaps else 0,
    }



# ---------------------------------------------------------------------------
# Order Book Polling
# ---------------------------------------------------------------------------

async def _poll_order_books() -> None:
    """Fetch L2 order book for top symbols by wallet count.

    Runs every 30 seconds independently of the position poll.
    """
    # Determine top symbols from ALL snapshots (not consensus, which is
    # AV-filtered). This ensures the pressure map covers all symbols where
    # any tracked wallet has a position, regardless of account value.
    from collections import Counter
    symbol_counts: Counter = Counter()
    now = time.time()
    for dq in _snapshots.values():
        if not dq:
            continue
        latest = dq[-1]
        if now - latest.timestamp > _SNAPSHOT_MAX_AGE_S:
            continue
        for pos in latest.positions:
            raw = pos.coin
            coin = f"xyz:{raw.split(':', 1)[1]}" if (raw.startswith("xyz:") or pos.dex == _XYZ_DEX) else _normalize_coin(raw)
            symbol_counts[coin] += 1

    top_symbols = [sym for sym, _ in symbol_counts.most_common(_ORDER_BOOK_TOP_N)]

    if not top_symbols:
        return

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)

    async def _fetch_book(session: aiohttp.ClientSession, coin: str) -> None:
        async with semaphore:
            try:
                async with session.post(
                    _HL_INFO_URL,
                    json={"type": "l2Book", "coin": coin, "nSigFigs": 3},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        _order_books[coin] = {
                            "levels": data.get("levels", [[], []]),
                            "timestamp": time.time(),
                        }
            except Exception:
                pass  # Non-critical

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [_fetch_book(session, coin) for coin in top_symbols]
        await asyncio.gather(*tasks, return_exceptions=True)

    # Prune order books for symbols no longer in top-N
    top_set = set(top_symbols)
    stale_books = [c for c in _order_books if c not in top_set]
    for c in stale_books:
        del _order_books[c]

    logger.debug("HyperLens: order books fetched for %d symbols", len(top_symbols))


# ---------------------------------------------------------------------------
# Price Clustering Helpers
# ---------------------------------------------------------------------------

def _cluster_precision(price: float) -> float:
    """Return the rounding step for clustering based on price magnitude."""
    if price >= 1000:
        return 100.0
    elif price >= 10:
        return 1.0
    else:
        return 0.01


def _round_to_cluster(price: float, step: float) -> float:
    """Round a price to the nearest cluster step."""
    if step <= 0:
        return price
    return round(round(price / step) * step, 8)


# ---------------------------------------------------------------------------
# Pressure Computation
# ---------------------------------------------------------------------------

def _compute_pressure(symbol: str) -> dict:
    """Compute aggregated pressure data for a symbol.

    Combines smart money orders, order book walls, and liquidation clusters.
    """
    coin = _normalize_coin(symbol)

    # ---- (a) Smart Money Orders ----
    stops: Dict[float, dict] = {}     # price -> {total_size_usd, wallet_count, side}
    take_profits: Dict[float, dict] = {}
    limits: Dict[float, dict] = {}

    for addr, orders in _wallet_orders.items():
        for order in orders:
            order_coin = order.get("coin", "")
            if order_coin != coin:
                continue

            is_trigger = order.get("isTrigger", False)
            is_tpsl = order.get("isPositionTpsl", False)
            order_type = (order.get("orderType") or "").lower()
            raw_side = order.get("side", "")
            side = "BUY" if raw_side == "B" else "SELL" if raw_side == "A" else raw_side

            # Determine order price
            if is_trigger:
                px_str = order.get("triggerPx") or order.get("limitPx", "0")
            else:
                px_str = order.get("limitPx", "0")
            try:
                px = float(px_str)
            except (ValueError, TypeError):
                continue

            sz_str = order.get("sz", "0")
            try:
                sz = float(sz_str)
            except (ValueError, TypeError):
                continue

            # sz can be 0 for fully-filled partial orders — use origSz as fallback
            if sz == 0:
                orig_sz_str = order.get("origSz", "0")
                try:
                    sz = float(orig_sz_str)
                except (ValueError, TypeError):
                    pass
            if sz == 0:
                continue

            size_usd = sz * px
            step = _cluster_precision(px)
            clustered_px = _round_to_cluster(px, step)

            # Classify order using orderType (HL returns human-readable strings
            # like "Stop Market", "Take Profit Limit", etc.)
            if is_tpsl and "stop" in order_type:
                bucket = stops
            elif is_tpsl and "take profit" in order_type:
                bucket = take_profits
            elif not is_trigger:
                # Resting limit order
                bucket = limits
            else:
                # Other trigger orders (e.g. stop market entry) — put in limits
                bucket = limits

            if clustered_px not in bucket:
                bucket[clustered_px] = {
                    "price": clustered_px,
                    "total_size_usd": 0.0,
                    "wallet_count": 0,
                    "side": side,
                    "wallets": set(),
                }
            entry = bucket[clustered_px]
            entry["total_size_usd"] += size_usd
            entry["wallets"].add(addr)
            entry["wallet_count"] = len(entry["wallets"])
            # Side: if mixed, keep first seen (unlikely for stops/TPs)
            if not entry["side"]:
                entry["side"] = side

    def _serialize_order_levels(bucket: Dict[float, dict]) -> list:
        """Convert order bucket to sorted serializable list."""
        result = []
        for px, data in bucket.items():
            result.append({
                "price": data["price"],
                "total_size_usd": round(data["total_size_usd"], 2),
                "wallet_count": data["wallet_count"],
                "side": data["side"],
            })
        result.sort(key=lambda x: x["price"])
        return result

    smart_money_orders = {
        "stops": _serialize_order_levels(stops),
        "take_profits": _serialize_order_levels(take_profits),
        "limits": _serialize_order_levels(limits),
    }

    # ---- (b) Order Book Walls ----
    bid_walls = []
    ask_walls = []

    book = _order_books.get(coin)
    if book and book.get("levels"):
        levels = book["levels"]
        bids = levels[0] if len(levels) > 0 else []
        asks = levels[1] if len(levels) > 1 else []

        for lvl in bids:
            try:
                px = float(lvl.get("px", 0))
                sz = float(lvl.get("sz", 0))
                n = int(lvl.get("n", 0))
            except (ValueError, TypeError):
                continue
            notional = px * sz
            if notional >= _WALL_THRESHOLD_USD:
                bid_walls.append({
                    "price": px,
                    "size_usd": round(notional, 2),
                    "order_count": n,
                })

        for lvl in asks:
            try:
                px = float(lvl.get("px", 0))
                sz = float(lvl.get("sz", 0))
                n = int(lvl.get("n", 0))
            except (ValueError, TypeError):
                continue
            notional = px * sz
            if notional >= _WALL_THRESHOLD_USD:
                ask_walls.append({
                    "price": px,
                    "size_usd": round(notional, 2),
                    "order_count": n,
                })

    # Sort by size descending, take top 5
    bid_walls.sort(key=lambda x: x["size_usd"], reverse=True)
    ask_walls.sort(key=lambda x: x["size_usd"], reverse=True)

    order_book_walls = {
        "bid_walls": bid_walls[:5],
        "ask_walls": ask_walls[:5],
        "book_timestamp": book["timestamp"] if book else None,
    }

    # ---- (c) Liquidation Clusters ----
    liq_prices: List[dict] = []

    for wallet in _roster:
        snaps = _snapshots.get(wallet.address)
        if not snaps:
            continue
        latest = snaps[-1]
        for pos in latest.positions:
            if pos.coin == coin and pos.liq_px > 0:
                liq_prices.append({
                    "liq_px": pos.liq_px,
                    "side": pos.side,
                    "size_usd": pos.size_usd,
                    "address": wallet.address,
                })

    # Cluster liq prices within 1% of each other
    liq_clusters = []
    if liq_prices:
        # Sort by liq_px
        liq_prices.sort(key=lambda x: x["liq_px"])
        current_cluster = [liq_prices[0]]

        for i in range(1, len(liq_prices)):
            cluster_avg = sum(lp["liq_px"] for lp in current_cluster) / len(current_cluster)
            if abs(liq_prices[i]["liq_px"] - cluster_avg) / max(cluster_avg, 0.001) <= 0.01:
                current_cluster.append(liq_prices[i])
            else:
                if len(current_cluster) >= 2:
                    liq_clusters.append(_summarize_liq_cluster(current_cluster))
                current_cluster = [liq_prices[i]]

        # Don't forget last cluster
        if len(current_cluster) >= 2:
            liq_clusters.append(_summarize_liq_cluster(current_cluster))

    liq_clusters.sort(key=lambda x: x["total_size_usd"], reverse=True)

    return {
        "symbol": coin,
        "smart_money_orders": smart_money_orders,
        "order_book_walls": order_book_walls,
        "liquidation_clusters": liq_clusters,
        "computed_at": time.time(),
    }


def _summarize_liq_cluster(entries: List[dict]) -> dict:
    """Summarize a cluster of nearby liquidation prices."""
    avg_px = sum(e["liq_px"] for e in entries) / len(entries)
    total_usd = sum(e["size_usd"] for e in entries)
    sides = {}
    for e in entries:
        sides[e["side"]] = sides.get(e["side"], 0) + 1
    dominant_side = max(sides, key=sides.get) if sides else "UNKNOWN"
    wallets = list({e["address"] for e in entries})

    return {
        "avg_price": round(avg_px, 4),
        "min_price": round(min(e["liq_px"] for e in entries), 4),
        "max_price": round(max(e["liq_px"] for e in entries), 4),
        "wallet_count": len(wallets),
        "total_size_usd": round(total_usd, 2),
        "dominant_side": dominant_side,
    }


# ---------------------------------------------------------------------------
# Pressure Map Public API
# ---------------------------------------------------------------------------

def get_pressure(symbol: str = None) -> dict:
    """Get pressure map for a symbol or all symbols.

    If symbol is None, returns an overview with per-symbol summary stats.
    If symbol is given, returns full pressure detail for that symbol.
    """
    if symbol:
        coin = _normalize_coin(symbol)
        return _compute_pressure(coin)

    # Build overview: aggregate per-symbol stats from _wallet_orders
    sym_stats: Dict[str, dict] = {}

    for addr, orders in _wallet_orders.items():
        for order in orders:
            order_coin = _normalize_coin(order.get("coin", ""))
            if not order_coin:
                continue

            is_tpsl = order.get("isPositionTpsl", False)
            hl_order_type = (order.get("orderType") or "").lower()
            is_trigger = order.get("isTrigger", False)

            # Classify
            if is_tpsl and "stop" in hl_order_type:
                otype = "stop"
            elif is_tpsl and "take profit" in hl_order_type:
                otype = "tp"
            else:
                otype = "limit"

            # Price
            px_str = order.get("triggerPx") or order.get("limitPx", "0") if is_trigger else order.get("limitPx", "0")
            try:
                px = float(px_str)
            except (ValueError, TypeError):
                continue

            # Size
            try:
                sz = float(order.get("sz", "0"))
            except (ValueError, TypeError):
                continue
            if sz == 0:
                try:
                    sz = float(order.get("origSz", "0"))
                except (ValueError, TypeError):
                    pass
            if sz == 0:
                continue

            notional = sz * px
            raw_side = order.get("side", "")
            side = "BUY" if raw_side == "B" else "SELL" if raw_side == "A" else raw_side

            if order_coin not in sym_stats:
                sym_stats[order_coin] = {
                    "symbol": order_coin,
                    "stop_count": 0, "tp_count": 0, "limit_count": 0,
                    "stop_notional": 0.0, "tp_notional": 0.0, "limit_notional": 0.0,
                    "total_notional": 0.0,
                    "buy_notional": 0.0, "sell_notional": 0.0,
                    "wallet_addrs": set(),
                }

            s = sym_stats[order_coin]
            s[f"{otype}_count"] += 1
            s[f"{otype}_notional"] += notional
            s["total_notional"] += notional
            s["wallet_addrs"].add(addr)
            if side == "BUY":
                s["buy_notional"] += notional
            else:
                s["sell_notional"] += notional

    # Serialize
    symbols = []
    for coin, s in sym_stats.items():
        net = s["buy_notional"] - s["sell_notional"]
        total = s["buy_notional"] + s["sell_notional"]
        bias = net / total if total > 0 else 0.0
        symbols.append({
            "symbol": s["symbol"],
            "stop_count": s["stop_count"],
            "tp_count": s["tp_count"],
            "limit_count": s["limit_count"],
            "stop_notional": round(s["stop_notional"], 2),
            "tp_notional": round(s["tp_notional"], 2),
            "limit_notional": round(s["limit_notional"], 2),
            "total_notional": round(s["total_notional"], 2),
            "wallet_count": len(s["wallet_addrs"]),
            "net_bias": round(bias, 3),  # +1 = all buy, -1 = all sell
        })

    symbols.sort(key=lambda x: x["total_notional"], reverse=True)

    return {
        "count": len(symbols),
        "total_wallets_with_orders": sum(1 for v in _wallet_orders.values() if v),
        "symbols": symbols,
    }


def get_order_book_walls(symbol: str) -> dict:
    """Get significant order book walls for a symbol."""
    coin = _normalize_coin(symbol)
    book = _order_books.get(coin)
    if not book or not book.get("levels"):
        return {"bid_walls": [], "ask_walls": [], "book_timestamp": None}

    bid_walls = []
    ask_walls = []
    levels = book["levels"]
    bids = levels[0] if len(levels) > 0 else []
    asks = levels[1] if len(levels) > 1 else []

    for lvl in bids:
        try:
            px = float(lvl.get("px", 0))
            sz = float(lvl.get("sz", 0))
            n = int(lvl.get("n", 0))
        except (ValueError, TypeError):
            continue
        notional = px * sz
        if notional >= _WALL_THRESHOLD_USD:
            bid_walls.append({"price": px, "size_usd": round(notional, 2), "order_count": n})

    for lvl in asks:
        try:
            px = float(lvl.get("px", 0))
            sz = float(lvl.get("sz", 0))
            n = int(lvl.get("n", 0))
        except (ValueError, TypeError):
            continue
        notional = px * sz
        if notional >= _WALL_THRESHOLD_USD:
            ask_walls.append({"price": px, "size_usd": round(notional, 2), "order_count": n})

    bid_walls.sort(key=lambda x: x["size_usd"], reverse=True)
    ask_walls.sort(key=lambda x: x["size_usd"], reverse=True)

    return {
        "bid_walls": bid_walls[:5],
        "ask_walls": ask_walls[:5],
        "book_timestamp": book.get("timestamp"),
    }


def get_smart_money_orders(symbol: str = None) -> list:
    """Get aggregated smart money orders (stops/TPs/limits).

    If symbol is None, returns orders across all symbols.
    """
    target_coin = _normalize_coin(symbol) if symbol else None

    aggregated: Dict[str, Dict[str, Dict[float, dict]]] = {}  # coin -> type -> price -> data

    for addr, orders in _wallet_orders.items():
        for order in orders:
            order_coin = order.get("coin", "")
            if target_coin and order_coin != target_coin:
                continue

            is_trigger = order.get("isTrigger", False)
            is_tpsl = order.get("isPositionTpsl", False)
            hl_order_type = (order.get("orderType") or "").lower()
            raw_side = order.get("side", "")
            side = "BUY" if raw_side == "B" else "SELL" if raw_side == "A" else raw_side

            if is_trigger:
                px_str = order.get("triggerPx") or order.get("limitPx", "0")
            else:
                px_str = order.get("limitPx", "0")
            try:
                px = float(px_str)
            except (ValueError, TypeError):
                continue

            try:
                sz = float(order.get("sz", "0"))
            except (ValueError, TypeError):
                continue

            # sz can be 0 for partially-filled — use origSz as fallback
            if sz == 0:
                try:
                    sz = float(order.get("origSz", "0"))
                except (ValueError, TypeError):
                    pass
            if sz == 0:
                continue

            size_usd = sz * px

            # Classify using orderType string
            if is_tpsl and "stop" in hl_order_type:
                order_type = "stop"
            elif is_tpsl and "take profit" in hl_order_type:
                order_type = "take_profit"
            else:
                order_type = "limit"

            step = _cluster_precision(px)
            clustered_px = _round_to_cluster(px, step)

            if order_coin not in aggregated:
                aggregated[order_coin] = {"stop": {}, "take_profit": {}, "limit": {}}
            bucket = aggregated[order_coin][order_type]

            if clustered_px not in bucket:
                bucket[clustered_px] = {
                    "coin": order_coin,
                    "type": order_type,
                    "price": clustered_px,
                    "total_size_usd": 0.0,
                    "wallet_count": 0,
                    "side": side,
                    "wallets": set(),
                }
            entry = bucket[clustered_px]
            entry["total_size_usd"] += size_usd
            entry["wallets"].add(addr)
            entry["wallet_count"] = len(entry["wallets"])

    # Flatten to list
    result = []
    for coin_data in aggregated.values():
        for type_bucket in coin_data.values():
            for data in type_bucket.values():
                result.append({
                    "coin": data["coin"],
                    "type": data["type"],
                    "price": data["price"],
                    "total_size_usd": round(data["total_size_usd"], 2),
                    "wallet_count": data["wallet_count"],
                    "side": data["side"],
                })

    result.sort(key=lambda x: x["total_size_usd"], reverse=True)
    return result


def get_status() -> dict:
    """Module status for API endpoint."""
    mp_addrs = {w.address for w in _roster_money_printers}
    sm_addrs = {w.address for w in _roster_smart_money}
    elite_count = len(mp_addrs & sm_addrs)

    # Count xyz DEX positions across all snapshots
    xyz_position_count = 0
    xyz_wallets = set()
    tradfi_symbols = set()
    for addr, snaps in _snapshots.items():
        if snaps:
            latest = snaps[-1]
            for p in latest.positions:
                if p.dex == _XYZ_DEX:
                    xyz_position_count += 1
                    xyz_wallets.add(addr)
                    tradfi_symbols.add(p.coin)

    return {
        "tracked_wallets": len(_roster),
        "money_printer_count": len(_roster_money_printers),
        "smart_money_count": len(_roster_smart_money),
        "elite_count": elite_count,
        "wallets_with_data": len(_snapshots),
        "consensus_symbols": len(_consensus),
        "last_poll": _last_poll_at or None,
        "last_roster_refresh": _roster_updated_at or None,
        "poll_count": _poll_count,
        "poll_interval_sec": _POLL_INTERVAL,
        "idle_roster_poll_interval_sec": _ROSTER_IDLE_POLL_INTERVAL,
        "active_wallets": sum(1 for w in _roster if _wallet_has_open_positions(w.address)),
        "idle_wallets": sum(1 for w in _roster if not _wallet_has_open_positions(w.address)),
        "roster_refresh_interval_sec": _ROSTER_REFRESH_INTERVAL,
        "initialized": _initialized,
        "wallets_with_orders": sum(1 for v in _wallet_orders.values() if v),
        "order_books_cached": len(_order_books),
        # HIP-3 xyz DEX stats
        "xyz_positions": xyz_position_count,
        "xyz_wallets": len(xyz_wallets),
        "tradfi_symbols": sorted(tradfi_symbols),
        # Persistence stats
        "db": _db_stats(),
    }


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def _order_book_loop() -> None:
    """Independent loop that polls order books every 30 seconds."""
    while True:
        try:
            await _poll_order_books()
        except Exception as exc:
            logger.warning("HyperLens order book poll error: %s", exc)
        await asyncio.sleep(_ORDER_BOOK_POLL_INTERVAL)


async def run_hyperlens_loop() -> None:
    """Main background loop: refresh roster daily, poll positions with tiered intervals."""
    global _initialized

    logger.info("HyperLens: starting background loop...")

    # Restore persisted data from SQLite before anything else
    try:
        _restore_from_db()
    except Exception as exc:
        logger.warning("HyperLens: DB restore failed (starting fresh): %s", exc)

    # Initial delay — let the main scan warm up first
    await asyncio.sleep(15)

    # Initial roster fetch
    count = await refresh_leaderboard()
    if count == 0:
        logger.warning("HyperLens: empty roster on startup, will retry in 5 min")

    _initialized = True
    last_roster_refresh = time.time()
    last_cleanup = time.time()

    # Launch order book polling as an independent concurrent task
    asyncio.create_task(_order_book_loop())

    while True:
        try:
            # Refresh roster daily
            if time.time() - last_roster_refresh > _ROSTER_REFRESH_INTERVAL:
                await refresh_leaderboard()
                last_roster_refresh = time.time()

            # Poll positions (also fetches open orders per wallet)
            if _roster:
                await poll_positions()

            # DB cleanup every 6 hours
            if time.time() - last_cleanup > 6 * 3600:
                try:
                    _db_cleanup()
                except Exception as exc:
                    logger.warning("HyperLens DB cleanup error: %s", exc)
                last_cleanup = time.time()

        except Exception as exc:
            logger.warning("HyperLens loop error: %s", exc)

        await asyncio.sleep(_POLL_INTERVAL)
