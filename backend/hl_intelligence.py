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
import os
import re
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import aiohttp

import hl_cadence as _cadence
import hl_entities as _entities_rule
import hl_calls as _hl_calls
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
    save_trader_lean as _db_save_trader_lean,
    max_account_values as _db_max_account_values,
    save_position_changes as _db_save_changes,
    load_position_changes as _db_load_changes,
    position_changes_first_ts as _db_changes_first_ts,
    get_db_stats as _db_stats,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
_HL_INFO_URL = "https://api.hyperliquid.xyz/info"

_ROSTER_REFRESH_INTERVAL = 24 * 60 * 60   # Daily

# Polling cadence — adaptive (hl_cadence): followed wallets every 5 min, a wallet whose
# positions changed 10 min later, backing off to 15/30/45/60 min while unchanged, 2 h while
# flat, elite at least every 15 min. With the cohort sweep on (production) the sweep reads the
# roster on this cadence and HyperLens reads only followed wallets itself; with it off,
# poll_positions below applies the same cadence to the roster.
_WATCHLIST_POLL_INTERVAL = _cadence.FOLLOWED_S
_POLL_INTERVAL = _cadence.TICK_S           # main loop tick (followed wallets are due every tick)
_ROSTER_IDLE_POLL_INTERVAL = 10 * 60       # loop nap while nobody is viewing and nothing is followed

# In-memory snapshot depth per wallet. "Sentiment Mode" only needs the
# latest snapshot for consensus — trade reconstruction is disabled, so
# we don't need consecutive snapshots anymore. Equity curves still served
# from SQLite (30-day retention). Was 20 → 6 → 1 (now ~88% smaller still).
_POSITION_HISTORY_LEN = 1

# Staleness: skip snapshots older than this when computing consensus
_SNAPSHOT_MAX_AGE_S = _cadence.MAX_READING_AGE_S   # the slowest tier (2 h, flat wallets) + a tick + the post-close pause
# After a restart the restored readings are up to an hour or so old (saved hourly), and a
# deploy starts the new copy before the old one saves on shutdown. Until the sweep has read
# everyone again, restored readings count as current so HyperLens is not empty.
_RESTORED_GRACE_S = 45 * 60
_RESTORED_MAX_AGE_S = 6 * 3600
_restored_until: float = 0.0


def _fresh_limit(now: float) -> float:
    return _RESTORED_MAX_AGE_S if now < _restored_until else _SNAPSHOT_MAX_AGE_S

# Perp account floor (perp equity from clearinghouseState, not the leaderboard's account value,
# which also counts spot, vaults and staking). One number for three uses: a wallet below it at
# its latest reading is left out when the roster is built (when a reading is on hand), evicted
# while tracked, and not counted in consensus or shown in the roster.
_MIN_PERP_EQUITY = 5_000
_EVICTION_THRESHOLD = _MIN_PERP_EQUITY
_DISPLAY_MIN_AV = _MIN_PERP_EQUITY

# Filtering thresholds
_MM_VLM_RATIO = 100                        # vlm/AV > 100 = market maker, skip
_MM_MAX_POSITIONS = 25                     # wallets with >25 concurrent positions = likely MM/vault
_ROI_WINDOW = "month"                      # Ranking window (was allTime)

# --- Roster rules (roster version 2, see docs/hyperlens-wallet-tracking.md) --------------------
# Built once a day from the Hyperliquid leaderboard download; market makers (monthly volume
# over 100x account value) are removed first.
#
# Profitable traders ("money_printer"), all of:
#   - monthly ROI >= 30%, and the ROI is meaningful (_meaningful_roi: the month did not start
#     from under $1K, where a small profit reads as a huge ROI);
#   - monthly profit >= $10K;
#   - all-time PnL >= this month's PnL (in profit before this month: one lucky month is not enough);
#   - leaderboard account value >= $10K (was $50K);
#   - perp equity >= $5K (_MIN_PERP_EQUITY) at the sweep's latest reading or at any HyperLens
#     reading of the last 7 days, when a reading is on hand. Wallets with no perp account (a
#     third of the qualifiers hold everything in spot or vaults) have nothing to follow.
#   Ranked by monthly ROI; the top MP_TARGET are kept (was 300). On the 29 Sept 2026
#   leaderboard 869 pass the profit rules and 583 of them have a perp account.
#
# Large accounts ("smart_money"): leaderboard account value >= $1M and the same perp-equity
# check, ranked by account value. Profit is not checked.
#
# Elite: a profitable trader that ranks within the top ELITE_KEEP_RANK large accounts. The
# large-account group is every elite wallet plus the largest others up to SM_TARGET wallets
# in all (was 300), so cutting the group never drops an elite wallet.
MP_TARGET = max(10, int(os.environ.get("HYPERLENS_MP_TARGET", "600")))
SM_TARGET = max(10, int(os.environ.get("HYPERLENS_SM_TARGET", "60")))
ELITE_KEEP_RANK = 300                      # the large-account depth of roster version 1
_MP_MIN_ROI_PCT = 30.0                     # Money Printers: 30% monthly ROI minimum
_MP_MIN_ACCOUNT_VALUE = 10_000             # Money Printers: $10K minimum leaderboard account value (was $50K)
_MP_MIN_PNL = 10_000                       # Money Printers: $10k minimum monthly profit (rejects dust/lottery)
_MIN_ROI_BASE = 1_000                      # ROI is dropped when the implied starting equity (pnl / roi) is below this
_SM_MIN_ACCOUNT_VALUE = 1_000_000          # Smart Money: $1M minimum AV
_PERP_EQUITY_MAX_AGE_S = 3 * 86400         # a perp-equity reading older than this is not used at build time
_PERP_EQUITY_LOOKBACK_S = 7 * 86400        # ...but a tracked wallet's highest reading this far back counts

# Stored records written with these rules carry roster_version = 2 (trader_lean, position_opens
# and convergences rows, cohort snapshots); rows from before have none (version 1: 300 + 300
# wallets, $50K floors, every wallet read each 30-minute sweep).
ROSTER_VERSION = _cadence.ROSTER_VERSION
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
    roi: Optional[float] = 0.0    # Monthly percentage ROI; None when it means nothing (near-empty start)
    score: float = 0.0            # monthly_roi * log(accountValue) ranking
    all_time_pnl: float = 0.0
    # The leaderboard's other windows (same download): 7-day PnL and ROI, all-time ROI.
    week_pnl: Optional[float] = None
    week_roi: Optional[float] = None
    all_time_roi: Optional[float] = None


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
    liq_distance_pct: Optional[float] = None   # abs(mark - liq_px) / mark * 100; None without a liq price
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
    money_printer_long_notional: float = 0.0
    money_printer_short_notional: float = 0.0
    smart_money_trend: str = "NEUTRAL"
    smart_money_net_ratio: float = 0.0
    smart_money_long_count: int = 0
    smart_money_short_count: int = 0
    smart_money_long_notional: float = 0.0
    smart_money_short_notional: float = 0.0


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_roster: List[TrackedWallet] = []                       # merged & deduplicated (all unique wallets)
_roster_money_printers: List[TrackedWallet] = []         # top MP_TARGET by monthly ROI
_roster_smart_money: List[TrackedWallet] = []            # SM_TARGET by account value (elite always in)
_wallet_cohorts: Dict[str, set] = {}                     # address -> {"money_printer", "smart_money", "elite"}
_roster_updated_at: float = 0.0

# Per-wallet position history: address -> deque of snapshots
_snapshots: Dict[str, deque] = {}

# Per-symbol consensus (recomputed after each poll)
_consensus: Dict[str, SymbolConsensus] = {}
# Profitable traders' open positions: address -> {coin: signed USD (+long / -short)}.
# Lets sector views count each wallet once per group (see profitable_lean).
_mp_book: Dict[str, Dict[str, float]] = {}
_consensus_updated_at: float = 0.0
# Wallets behind the last consensus: updated within _SNAPSHOT_MAX_AGE_S, and of
# those, the ones that passed the MM and account-value filters.
_fresh_wallets: int = 0
_consensus_wallets: int = 0

# Module state
_initialized = False
_last_poll_at: float = 0.0
_poll_count: int = 0

# Throttle SQLite snapshot writes — once per hour is enough for the
# wallet-detail page to stay reasonably fresh, and frequent writes
# inflate the kernel page cache (Railway bills cgroup memory).
_DB_SAVE_INTERVAL_S: float = 3600.0
_last_db_save_at: float = 0.0

# Asset index map: @index → name (e.g. @142 → "PENGU")
_asset_index_map: Dict[str, str] = {}

# Pressure Map stores
_wallet_orders: Dict[str, list] = {}          # address -> list of raw order dicts
_order_books: Dict[str, dict] = {}            # coin -> {"levels": ..., "timestamp": float}
_pressure_cache: Dict[str, dict] = {}         # coin -> computed pressure data
_ORDER_BOOK_POLL_INTERVAL = 60                # seconds (was 30)

# Tiered polling state
_xyz_active_wallets: Set[str] = set()      # Wallets that have had xyz positions
# Own polling plan (followed wallets; the whole roster only when the cohort sweep is off):
# address -> (next due time, readings in a row without a change). ~100 bytes per wallet.
_poll_plan: Dict[str, tuple] = {}
_ORDER_BOOK_TOP_N = 50                        # top N symbols by wallet count
_WALL_THRESHOLD_USD = 500_000                 # min notional for an order book "wall"


# ---------------------------------------------------------------------------
# Persistence — restore from SQLite on startup
# ---------------------------------------------------------------------------

def _restore_from_db() -> None:
    """Load persisted snapshots from SQLite on startup.

    "Sentiment Mode" only restores the LATEST snapshot per wallet (not the
    full 24h history) since consensus only needs the current state. The
    trade_log and position_first_seen restores are skipped entirely —
    trade reconstruction is disabled, so loading them was 24 MB of pure
    dead weight (per /api/admin/memory-snapshot).

    The first poll cycle (~10 min after restart) will refresh whatever
    wallets are in the new roster; non-roster wallets get pruned by
    refresh_leaderboard's eviction step.
    """
    global _snapshots, _last_positions

    # Restore snapshots — keep only the latest per wallet (deque maxlen=1
    # in Sentiment Mode). Cap to 6h to limit how many ghost wallets we
    # restore for ones that have since dropped out of the roster.
    raw_snaps = _db_load_snapshots(max_age_hours=6)
    restored_count = 0
    for address, snap_list in raw_snaps.items():
        if not snap_list:
            continue
        # Only the most recent snapshot is needed (consensus uses snaps[-1])
        s = snap_list[-1]
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
                    liq_distance_pct=p.get("liq_distance_pct") or None,   # older rows stored 0 for "none"
                    leverage_type=p.get("leverage_type", "cross"),
                    asset_class=p.get("asset_class", "crypto"),
                    dex=p.get("dex", ""),
                ))
            except Exception:
                continue

        dq = deque(maxlen=_POSITION_HISTORY_LEN)
        dq.append(PositionSnapshot(
            timestamp=s["timestamp"],
            positions=positions,
            account_value=s["account_value"],
        ))
        _snapshots[address] = dq
        restored_count += 1

    # _trade_log + _position_first_seen no longer restored (Sentiment Mode
    # disables trade reconstruction, so those structures stay empty).
    # _last_positions also unused; stays empty.

    global _restored_until
    if restored_count:
        _restored_until = time.time() + _RESTORED_GRACE_S
    logger.info(
        "HyperLens DB restore: %d wallets (latest snapshot only, 6h window)",
        restored_count,
    )


# ---------------------------------------------------------------------------
# Leaderboard fetch & roster building
# ---------------------------------------------------------------------------

def _meaningful_roi(pnl: float, roi_pct: float) -> Optional[float]:
    """The leaderboard's monthly ROI in percent, or None when the wallet began the
    month nearly empty: a modest profit then reads as thousands or millions of
    percent (the ROI equals PnL/100), which says nothing about skill."""
    if roi_pct and abs(pnl / (roi_pct / 100)) < _MIN_ROI_BASE:
        return None
    return roi_pct


def parse_leaderboard(rows: list) -> List[TrackedWallet]:
    """Leaderboard rows -> TrackedWallet list, market makers (vlm/AV > 100) removed."""
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
            all_time_pnl = 0.0
            week_pnl = week_roi = all_time_roi = None
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
                        elif window_name == "allTime":
                            all_time_pnl = float(metrics.get("pnl", 0) or 0)
                            all_time_roi = float(metrics.get("roi", 0) or 0) * 100
                        elif window_name == "week":
                            week_pnl = float(metrics.get("pnl", 0) or 0)
                            week_roi = float(metrics.get("roi", 0) or 0) * 100
            else:
                pnl = float(entry.get("pnl", 0) or 0)
                roi = float(entry.get("roi", 0) or 0) * 100

            # Market maker filter: vlm/AV ratio > 100 = likely MM/vault
            if account_value > 0 and monthly_vlm / account_value > _MM_VLM_RATIO:
                continue

            roi = _meaningful_roi(pnl, roi)

            # Compute ranking score: monthly_roi * log(accountValue)
            score = (roi or 0.0) * math.log(max(account_value, 1))

            all_wallets.append(TrackedWallet(
                address=address.lower(),
                display_name=display_name,
                account_value=account_value,
                pnl=pnl,
                roi=roi,
                score=score,
                all_time_pnl=all_time_pnl,
                week_pnl=week_pnl,
                week_roi=None if week_roi is None or week_pnl is None else _meaningful_roi(week_pnl, week_roi),
                all_time_roi=None if all_time_roi is None else _meaningful_roi(all_time_pnl, all_time_roi),
            ))
        except Exception:
            continue  # Skip malformed entries
    return all_wallets


def _perp_ok(w: TrackedWallet, perp_equity: Optional[Dict[str, float]]) -> bool:
    """False only when a recent perp-equity reading exists and is below the floor."""
    if not perp_equity:
        return True
    eq = perp_equity.get(w.address)
    return eq is None or eq >= _MIN_PERP_EQUITY


def build_cohorts(all_wallets: List[TrackedWallet], perp_equity: Optional[Dict[str, float]] = None,
                  mp_target: Optional[int] = None, sm_target: Optional[int] = None):
    """The roster rules (see the config block above). ``all_wallets``: the parsed leaderboard with
    market makers removed and ROI already passed through _meaningful_roi. ``perp_equity``: address
    -> perp equity from recent readings (may be empty). Returns (money printers ranked by ROI,
    large accounts ranked by account value, elite addresses)."""
    mp_target = MP_TARGET if mp_target is None else mp_target
    sm_target = SM_TARGET if sm_target is None else sm_target
    mp_candidates = [
        w for w in all_wallets
        if (w.roi is not None
            and w.roi >= _MP_MIN_ROI_PCT
            and w.account_value >= _MP_MIN_ACCOUNT_VALUE
            and w.pnl >= _MP_MIN_PNL
            and w.all_time_pnl >= w.pnl
            and _perp_ok(w, perp_equity))
    ]
    mp_candidates.sort(key=lambda w: w.roi, reverse=True)
    money_printers = mp_candidates[:mp_target]
    mp_addresses = {w.address for w in money_printers}

    sm_ranked = [w for w in all_wallets if w.account_value >= _SM_MIN_ACCOUNT_VALUE and _perp_ok(w, perp_equity)]
    sm_ranked.sort(key=lambda w: w.account_value, reverse=True)
    elite = {w.address for w in sm_ranked[:ELITE_KEEP_RANK] if w.address in mp_addresses}
    # Elite first, then the largest others until the group has sm_target wallets; ranking order kept.
    room = max(0, sm_target - len(elite))
    keep = elite | set([w.address for w in sm_ranked if w.address not in elite][:room])
    smart_money = [w for w in sm_ranked if w.address in keep]
    return money_printers, smart_money, elite


def _known_perp_equity() -> Dict[str, float]:
    """Perp equity per wallet: the larger of the cohort sweep's latest reading (every leaderboard
    wallet of $10K+ is read at least daily) and the highest HyperLens reading of the last
    _PERP_EQUITY_LOOKBACK_S (so a tracked trader who sold everything and moved the cash to spot
    for a few days is not dropped). Empty when neither source has data yet."""
    now = time.time()
    out: Dict[str, float] = {}
    try:
        from cohorts.sweeper import enabled, store
        if enabled():
            out.update(store().equities(now - _PERP_EQUITY_MAX_AGE_S))
    except Exception as exc:
        logger.warning("HyperLens: perp equity lookup failed: %s", exc)
    try:
        for a, av in _db_max_account_values(now - _PERP_EQUITY_LOOKBACK_S).items():
            if av > out.get(a, -1.0):
                out[a] = av
    except Exception as exc:
        logger.warning("HyperLens: account value history lookup failed: %s", exc)
    return out


async def refresh_leaderboard() -> int:
    """Fetch HL leaderboard and rebuild the tracking roster using cohorts.

    Two cohorts are built from the same leaderboard data by build_cohorts (rules in the
    config block): money printers ("profitable traders" in the UI, MP_TARGET by monthly ROI),
    smart money ("large accounts", SM_TARGET by account value, elite always kept) and
    elite (in both).

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

    all_wallets = parse_leaderboard(rows)

    # Wallet cohorts reuse this download (one 40MB leaderboard fetch a day serves both).
    try:
        from cohorts.sweeper import registry_from_leaderboard
        n = await asyncio.to_thread(registry_from_leaderboard, all_wallets)
        if n:
            logger.info("Cohorts: registry refreshed with %d wallets", n)
    except Exception as exc:
        logger.warning("Cohorts: registry refresh failed: %s", exc)

    perp_equity = await asyncio.to_thread(_known_perp_equity)
    _roster_money_printers, _roster_smart_money, elite_addresses = build_cohorts(all_wallets, perp_equity)
    mp_addresses = {w.address for w in _roster_money_printers}
    sm_addresses = {w.address for w in _roster_smart_money}

    # --- Build cohort tags ---
    _wallet_cohorts.clear()
    for addr in mp_addresses:
        _wallet_cohorts.setdefault(addr, set()).add("money_printer")
    for addr in sm_addresses:
        _wallet_cohorts.setdefault(addr, set()).add("smart_money")
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
    try:                                   # the cohort sweep reads these on the adaptive cadence
        from cohorts.sweeper import pin_roster
        await asyncio.to_thread(pin_roster, [w.address for w in _roster], elite_addresses)
    except Exception as exc:
        logger.warning("Cohorts: roster pin failed: %s", exc)

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

        # Distance to liquidation from the current price (positionValue / size is
        # the mark at fetch time; entry is the fallback). None without a liq price,
        # e.g. a well-collateralised cross position, which is not "0% away".
        pos_value = abs(float(pos.get("positionValue", 0) or 0))
        ref_px = pos_value / abs(szi) if pos_value > 0 else entry_px
        liq_dist_pct = None
        if ref_px > 0 and liq_px > 0:
            liq_dist_pct = round(abs(ref_px - liq_px) / ref_px * 100, 2)

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
            liq_distance_pct=liq_dist_pct,
            leverage_type=lev_type,
            asset_class=ac,
            dex=dex,
        ))
    return result


def _snapshot_from_state(data: dict, xyz_data: Optional[dict] = None, ts: Optional[float] = None) -> PositionSnapshot:
    """PositionSnapshot from a clearinghouseState response (and the xyz DEX one, if fetched)."""
    positions = _parse_positions(data)
    if xyz_data:
        positions.extend(_parse_positions(xyz_data, dex=_XYZ_DEX))
    av = float((data.get("marginSummary") or {}).get("accountValue", 0) or 0)
    if xyz_data:
        av += float((xyz_data.get("marginSummary") or {}).get("accountValue", 0) or 0)
    return PositionSnapshot(timestamp=time.time() if ts is None else ts, positions=positions, account_value=av)


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
            _hl_calls.record("clearinghouseState")
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
                _hl_calls.record("frontendOpenOrders")
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
                _hl_calls.record("clearinghouseState")
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
    snap = _snapshot_from_state(data, xyz_data)
    if xyz_data and any(p.dex == _XYZ_DEX for p in snap.positions):
        _xyz_active_wallets.add(wallet.address)
    return snap


def _followed_any() -> bool:
    try:
        import followed_traders
        return bool(followed_traders.addresses())
    except Exception:
        return False


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
        import followed_traders
        addrs.update(followed_traders.addresses())
    except Exception:
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


def _observe_opens(evicted: Set[str]) -> None:
    """Feed each tracked wallet's latest reading to the open and convergence tracker
    (convergence.py). Same wallet filters as consensus; builder-dex markets are skipped."""
    try:
        import followed_traders as ft
        from convergence import tracker
        tr = tracker()
        tr.entity_of = entity_of               # lockstep wallets converge as one trader
        tr.forget(evicted)
        followed = ft.addresses()
        now = time.time()
        mp = {w.address for w in _roster_money_printers}
        new = []
        for wallet in _roster:
            snaps = _snapshots.get(wallet.address)
            if not snaps:
                continue
            latest = snaps[-1]
            if now - latest.timestamp > _fresh_limit(now) or len(latest.positions) > _MM_MAX_POSITIONS:
                continue
            if 0 < latest.account_value < _DISPLAY_MIN_AV:
                continue
            positions = [{"coin": _normalize_coin(p.coin), "side": p.side.lower(), "entry_px": p.entry_px,
                          "size": p.size, "size_usd": p.size_usd,
                          "mark_px": p.size_usd / abs(p.size) if p.size else None}
                         for p in latest.positions if not (p.coin.startswith("xyz:") or p.dex == _XYZ_DEX)]
            cohort = "profitable" if wallet.address in mp else "large"
            prev, seen = tr.held.get(wallet.address), tr.seen_ts.get(wallet.address, 0)
            new += tr.observe(wallet.address, cohort, latest.timestamp, positions)
            if wallet.address in followed and prev is not None and latest.timestamp > seen:
                ft.record(wallet.address, cohort, latest.timestamp, ft.diff(prev, tr.held[wallet.address]), positions)
        for c in tr.check(new):
            logger.info("HyperLens: convergence %s %s, %d profitable traders", c["coin"], c["side"], c["n"])
    except Exception as exc:
        logger.warning("HyperLens: open tracking failed: %s", exc)


def _after_positions_update() -> Set[str]:
    """After new wallet snapshots (own poll or the cohort sweep): evict wallets that no
    longer qualify, recompute consensus, persist at most hourly. Returns evicted addresses."""
    global _roster, _roster_money_printers, _roster_smart_money, _consensus_updated_at, _last_db_save_at
    # --- Safe eviction: remove wallets that provide no value ---
    # Two categories:
    #   a) AV dropped below threshold (withdrew funds)
    #   b) Consistently idle: 10+ snapshots collected but ZERO positions ever
    #      observed → wallet made its money before we tracked it or trades
    #      intra-poll. No point wasting poll slots on it.
    _IDLE_EVICTION_MIN_SNAPS = 10  # enough polls to establish a pattern

    evicted_addrs: Set[str] = set()
    for w in _roster:
        # (a) AV too low
        if w.account_value > 0 and w.account_value < _EVICTION_THRESHOLD:
            evicted_addrs.add(w.address)
            continue
        # (b) Tracked long enough but never had a single position
        snaps = _snapshots.get(w.address)
        if snaps and len(snaps) >= _IDLE_EVICTION_MIN_SNAPS:
            ever_had_positions = any(len(s.positions) > 0 for s in snaps)
            if not ever_had_positions:
                evicted_addrs.add(w.address)

    if evicted_addrs:
        _roster = [w for w in _roster if w.address not in evicted_addrs]
        _roster_money_printers = [w for w in _roster_money_printers if w.address not in evicted_addrs]
        _roster_smart_money = [w for w in _roster_smart_money if w.address not in evicted_addrs]
        for addr in evicted_addrs:
            _wallet_cohorts.pop(addr, None)
            # Full cleanup — don't leave ghost data in memory
            _snapshots.pop(addr, None)
            _last_positions.pop(addr, None)
            _trade_log.pop(addr, None)
            _position_first_seen.pop(addr, None)
            _wallet_orders.pop(addr, None)
        logger.info(
            "HyperLens: evicted %d wallets (low AV or perpetually idle, full cleanup)",
            len(evicted_addrs),
        )

    # Prune stale wallet orders for addresses no longer in roster
    roster_addrs = {w.address for w in _roster}
    stale_order_keys = [a for a in _wallet_orders if a not in roster_addrs]
    for a in stale_order_keys:
        del _wallet_orders[a]

    # Trade reconstruction disabled in "Sentiment Mode" — we only need
    # the latest snapshot for consensus, not snapshot-to-snapshot diffs.
    # _reconstruct_trades() removed; _trade_log / _last_positions /
    # _position_first_seen stay empty.

    _recompute_consensus()
    _consensus_updated_at = time.time()
    _observe_opens(evicted_addrs)

    # Persist snapshots only — trade log + first-seen no longer populated.
    # Throttle DB writes to ≤1/hour: SQLite writes inflate the kernel page
    # cache (which Railway bills as memory). Wallet-detail page stays
    # accurate within the hour from in-memory state; on-disk persistence
    # is for surviving Railway redeploys.
    if _pending_changes:
        try:
            _db_save_changes(list(_pending_changes))
            _pending_changes.clear()
        except Exception as exc:
            logger.warning("HyperLens DB: change log save error: %s", exc)
    if (time.time() - _last_db_save_at) >= _DB_SAVE_INTERVAL_S:
        try:
            _db_save_snapshots(_snapshots)
            _last_db_save_at = time.time()
        except Exception as exc:
            logger.warning("HyperLens DB: save error: %s", exc)
    return evicted_addrs


# --- Roster fed by the cohort sweep (one poll per wallet serves both) ----------------

def roster_via_cohorts() -> bool:
    """True when the cohort sweep polls the roster (cohorts enabled); HyperLens then only
    polls followed wallets itself."""
    try:
        from cohorts.sweeper import enabled
        return enabled()
    except Exception:
        return False


_roster_index: Dict[str, TrackedWallet] = {}
_roster_index_of: int = 0


def ingest_state(address: str, data: dict, ts: Optional[float] = None) -> bool:
    """Store a clearinghouseState fetched by the cohort sweep, if the wallet is on the roster."""
    global _roster_index, _roster_index_of
    if _roster_index_of != id(_roster):
        _roster_index = {w.address: w for w in _roster}
        _roster_index_of = id(_roster)
    wallet = _roster_index.get(address.lower())
    if wallet is None:
        return False
    snap = _snapshot_from_state(data, ts=ts)
    prev = _snapshots[wallet.address][-1] if _snapshots.get(wallet.address) else None
    _note_change(wallet.address, prev, snap)
    if wallet.address not in _snapshots:
        _snapshots[wallet.address] = deque(maxlen=_POSITION_HISTORY_LEN)
    _snapshots[wallet.address].append(snap)
    if snap.account_value > 0:
        wallet.account_value = snap.account_value
    return True


def after_ingest() -> None:
    """Called by the cohort sweep after each batch."""
    global _last_poll_at, _poll_count
    _after_positions_update()
    _last_poll_at = time.time()
    _poll_count += 1


def _book_of(snap: Optional[PositionSnapshot]) -> Optional[_cadence.Book]:
    if snap is None:
        return None
    out: _cadence.Book = {}
    for p in snap.positions:
        key = f"xyz:{p.coin}" if p.dex == _XYZ_DEX and not p.coin.startswith("xyz:") else p.coin
        s0, u0 = out.get(key, (0.0, 0.0))
        out[key] = (s0 + (p.size if p.side == "LONG" else -p.size), u0 + p.size_usd)
    return out


def _plan_next(address: str, prev: Optional[PositionSnapshot], snap: PositionSnapshot, now: float,
               followed: bool, elite: bool) -> float:
    """Record a reading in the own polling plan; returns when the wallet is next due."""
    streak = _poll_plan.get(address, (0.0, _cadence.SETTLED_STREAK))[1]
    book = _book_of(snap)
    streak = _cadence.next_streak(streak, _cadence.changed(_book_of(prev), book))
    due = _cadence.next_at(now, streak, not _cadence.live(book), followed=followed, elite=elite)
    _poll_plan[address] = (due, streak)
    return due


async def poll_positions(force: bool = False) -> int:
    """Read the wallets that are due (hl_cadence).

    - Followed/watched wallets: every 5 min, always read here.
    - Roster wallets: read here only when the cohort sweep is off (otherwise the sweep reads
      them on the same cadence and feeds ingest_state). ``force`` reads every roster wallet
      (the 4-hour record when nobody has been viewing and the sweep is off).

    Positions only (one clearinghouseState call per wallet; the xyz DEX only for wallets
    known to hold xyz positions).
    """
    global _last_poll_at, _poll_count, _consensus_updated_at
    global _roster, _roster_money_printers, _roster_smart_money

    # Refresh asset index map if empty (resolves @142 → PENGU etc.)
    if not _asset_index_map:
        await _refresh_asset_index_map()

    if not _roster:
        logger.debug("HyperLens: no roster — skipping poll")
        return 0

    now = time.time()
    watchlist_addrs = _get_watchlist_addresses()
    delegated = roster_via_cohorts()      # the cohort sweep reads the roster
    elite = {a for a, c in _wallet_cohorts.items() if "elite" in c}

    watchlist_wallets = []
    roster_to_poll = []
    for w in _roster:
        if w.address.lower() in watchlist_addrs:
            watchlist_wallets.append(w)
        elif not delegated and (force or _poll_plan.get(w.address, (0.0, 0))[0] <= now):
            roster_to_poll.append(w)
    # Plan entries of wallets that left the roster
    on_roster = {w.address for w in _roster}
    for a in [a for a in _poll_plan if a not in on_roster]:
        del _poll_plan[a]

    wallets_to_poll = watchlist_wallets + roster_to_poll
    if not wallets_to_poll:
        logger.debug("HyperLens: no wallets due for polling this cycle")
        return 0

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)
    success_count = 0

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            _fetch_wallet_positions(session, semaphore, w, full=False)
            for w in wallets_to_poll
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for wallet, result in zip(wallets_to_poll, results):
        if isinstance(result, Exception) or result is None:
            continue

        prev = _snapshots[wallet.address][-1] if _snapshots.get(wallet.address) else None
        _plan_next(wallet.address, prev, result, now, followed=wallet.address.lower() in watchlist_addrs,
                   elite=wallet.address in elite)
        _note_change(wallet.address, prev, result)

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

    evicted_addrs = _after_positions_update()

    tier_info = f"followed={len(watchlist_wallets)}, roster={len(roster_to_poll)}"
    if delegated:
        tier_info += " (roster read by the cohort sweep)"
    if evicted_addrs:
        tier_info += f", evicted={len(evicted_addrs)}"
    logger.info(
        "HyperLens poll #%d: %d/%d wallets (%s), %d symbols with consensus",
        _poll_count, success_count, len(wallets_to_poll), tier_info, len(_consensus),
    )
    return success_count


def _note_change(address: str, prev: Optional[PositionSnapshot], snap: PositionSnapshot) -> None:
    """Queue the coins whose size changed since the previous reading for the change log
    (hl_entities), and ask the fills store (hl_fills) for the wallet's new fills. The log skips
    changes when the gap between the readings is too long to time them."""
    if prev is None or snap.timestamp <= prev.timestamp:
        return
    before, after = _book_of(prev), _book_of(snap)
    if not _cadence.changed(before, after):
        return
    try:
        import hl_fills
        hl_fills.mark_changed(address)
    except Exception as exc:
        logger.debug("HyperLens: fills store notice failed: %s", exc)
    if snap.timestamp - prev.timestamp > _cadence.MAX_READING_AGE_S:
        return
    b, a = _cadence.live(before), _cadence.live(after)
    for coin in set(b) | set(a):
        s0, u0 = b.get(coin, (0.0, 0.0))
        s1, u1 = a.get(coin, (0.0, 0.0))
        if s0 != s1:
            px = abs(u1 / s1) if s1 else abs(u0 / s0)
            _pending_changes.append((address, prev.timestamp, snap.timestamp, coin, s0, s1, px))
    if len(_pending_changes) > 5_000:                  # never hold much if the DB is unavailable
        del _pending_changes[:-5_000]


# ---------------------------------------------------------------------------
# Lockstep wallets (hl_entities): wallets that trade as one count as one trader
# ---------------------------------------------------------------------------

_pending_changes: List[tuple] = []
_entity_of: Dict[str, str] = {}              # address -> entity id, grouped wallets only
_entity_members: Dict[str, List[str]] = {}   # entity id -> member addresses
_entities_at: float = 0.0


def entity_of(address: str) -> str:
    """The entity a wallet trades as: its group id, or the address itself."""
    return _entity_of.get(address, address)


def entity_info(address: str) -> Optional[dict]:
    """Group details for a wallet in a lockstep group, else None."""
    gid = _entity_of.get((address or "").lower())
    if gid is None:
        return None
    members = _entity_members.get(gid, [])
    return {"id": gid, "size": len(members), "members": members, "note": _entities_rule.note(len(members)),
            "computed_at": _entities_at or None}


def _compute_entities(now: float) -> tuple:
    changes = _db_load_changes(now - _entities_rule.WINDOW_DAYS * 86400)
    on_roster = {w.address for w in _roster}
    changes = {a: cs for a, cs in changes.items() if a in on_roster}
    books = {}
    for a in changes:
        snaps = _snapshots.get(a)
        if snaps:
            books[a] = _cadence.live(_book_of(snaps[-1]))
    return _entities_rule.find_entities(changes, books, now=now)


_seed_task: Optional[asyncio.Task] = None


async def seed_changes_from_fills() -> int:
    """One-off: when the change log is empty (the first start after this change), rebuild the last
    30 days from each roster wallet's fills, so lockstep groups are known at once instead of weeks
    later. One userFills request per wallet (~630) on trader_entries' rate budget, one wallet at a
    time, in the background. Once the log has rows it never runs again. Returns the rows added."""
    now = time.time()
    if await asyncio.to_thread(_db_changes_first_ts) is not None:
        return 0
    since, until = now - _entities_rule.WINDOW_DAYS * 86400, now
    import trader_entries as te
    added = 0
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for address in [w.address for w in _roster]:
            try:
                fills = await te._post(session, {"type": "userFills", "user": address, "aggregateByTime": True})
            except Exception as exc:
                logger.debug("HyperLens: change-log seed skipped %s: %s", address[:10], exc)
                continue
            rows = [(address, *c) for c in _entities_rule.changes_from_fills(fills or [], since, until,
                                                                              _cadence.DUST_USD)]
            del fills
            if rows:
                await asyncio.to_thread(_db_save_changes, rows)
                added += len(rows)
    logger.info("HyperLens: change log seeded with %d rows from fills", added)
    return added


async def _seed_then_group() -> None:
    try:
        await seed_changes_from_fills()
    except Exception as exc:
        logger.warning("HyperLens: change-log seed failed: %s", exc)
    await recompute_entities()


async def recompute_entities() -> int:
    """Daily with the roster refresh (and at start): regroup lockstep wallets. Returns groups."""
    global _entity_of, _entity_members, _entities_at
    now = time.time()
    try:
        groups, links = await asyncio.to_thread(_compute_entities, now)
    except Exception as exc:
        logger.warning("HyperLens: lockstep grouping failed: %s", exc)
        return len(_entity_members)
    members: Dict[str, List[str]] = {}
    for a, g in groups.items():
        members.setdefault(g, []).append(a)
    _entity_of, _entity_members, _entities_at = groups, {g: sorted(m) for g, m in members.items()}, now
    logger.info("HyperLens: %d lockstep groups (%d wallets) from %d links", len(members), len(groups), len(links))
    return len(members)


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

    Counts are of traders, not wallets: wallets that trade as one (hl_entities) count once per
    coin, on the side of their combined dollars. Dollars are summed over every wallet.
    """
    global _consensus, _mp_book, _fresh_wallets, _consensus_wallets

    now = time.time()
    mp_book: Dict[str, Dict[str, float]] = {}
    score_map = {w.address: w.score for w in _roster}
    mp_addresses = {w.address for w in _roster_money_printers}
    sm_addresses = {w.address for w in _roster_smart_money}

    # Collect per-symbol data (skip stale + MM-like wallets)
    sym_data: Dict[str, dict] = {}
    fresh_wallet_count = 0
    fresh_entities: Set[str] = set()
    recent_count = 0

    for wallet in _roster:
        snapshots = _snapshots.get(wallet.address)
        if not snapshots:
            continue

        latest = snapshots[-1]

        # Staleness check: skip wallets whose last snapshot is too old
        if now - latest.timestamp > _fresh_limit(now):
            continue
        recent_count += 1

        # Position-count MM filter: wallets with >25 positions are likely
        # market makers or vaults — skip from consensus
        if len(latest.positions) > _MM_MAX_POSITIONS:
            continue

        # AV filter: consensus only counts quality wallets ($50k+)
        if latest.account_value > 0 and latest.account_value < _DISPLAY_MIN_AV:
            continue

        fresh_wallet_count += 1
        addr = wallet.address
        ent = entity_of(addr)
        fresh_entities.add(ent)
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
                    # entity -> net signed USD (all / money printers / smart money), for trader counts
                    "ent": {}, "mp_ent": {}, "sm_ent": {},
                }

            d = sym_data[coin]
            signed = pos.size_usd if pos.side == "LONG" else -pos.size_usd
            if is_mp and not coin.startswith("xyz:"):
                book = mp_book.setdefault(ent, {})
                book[coin] = book.get(coin, 0.0) + signed
            d["ent"][ent] = d["ent"].get(ent, 0.0) + signed
            if is_mp:
                d["mp_ent"][ent] = d["mp_ent"].get(ent, 0.0) + signed
            if is_sm:
                d["sm_ent"][ent] = d["sm_ent"].get(ent, 0.0) + signed
            w_score = score_map.get(wallet.address, 1.0)
            d["leverages"].append(pos.leverage)

            # Weight consensus by notional size * wallet score
            # so a $5M position from a top trader counts more than a $50k one
            notional_weight = pos.size_usd * w_score

            if pos.side == "LONG":
                d["long_notional"] += pos.size_usd
                d["weighted_sum"] += notional_weight
                d["top_longs"].append(wallet.address)
                if is_mp:
                    d["mp_long_notional"] += pos.size_usd
                if is_sm:
                    d["sm_long_notional"] += pos.size_usd
            else:
                d["short_notional"] += pos.size_usd
                d["weighted_sum"] -= notional_weight
                d["top_shorts"].append(wallet.address)
                if is_mp:
                    d["mp_short_notional"] += pos.size_usd
                if is_sm:
                    d["sm_short_notional"] += pos.size_usd

    # Trader counts: each entity once, on the side of its net dollars in the coin
    for d in sym_data.values():
        for key, lk, sk in (("ent", "long_count", "short_count"), ("mp_ent", "mp_long", "mp_short"),
                            ("sm_ent", "sm_long", "sm_short")):
            nets = d.pop(key).values()
            d[lk] = sum(1 for v in nets if v > 0)
            d[sk] = sum(1 for v in nets if v < 0)
    fresh_trader_count = len(fresh_entities)

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
        participation = total_positioned / max(fresh_trader_count, 1)
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
            neutral_count=fresh_trader_count - total_positioned,
            total_tracked=fresh_trader_count,
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
            money_printer_long_notional=round(d["mp_long_notional"], 2),
            money_printer_short_notional=round(d["mp_short_notional"], 2),
            smart_money_trend=sm_trend,
            smart_money_net_ratio=round(sm_net_ratio, 4),
            smart_money_long_count=d["sm_long"],
            smart_money_short_count=d["sm_short"],
            smart_money_long_notional=round(d["sm_long_notional"], 2),
            smart_money_short_notional=round(d["sm_short_notional"], 2),
        )

    _consensus = new_consensus
    _mp_book = mp_book
    _fresh_wallets = recent_count
    _consensus_wallets = fresh_wallet_count


def profitable_lean(groups_of) -> Dict[str, dict]:
    """How profitable traders lean per group (sector, ecosystem, ...).

    ``groups_of(coin)`` returns the group keys a coin belongs to. Each trader is
    counted once per group, on the side of its net dollar exposure there, so a
    trader long five AI coins is one AI long, not five. Wallets that trade as one
    (hl_entities) are one trader: _mp_book is keyed by entity. ``lean`` is
    (long - short) / (long + short) over traders, in [-1, +1].
    """
    out: Dict[str, dict] = {}
    for book in _mp_book.values():
        net: Dict[str, float] = {}
        for coin, usd in book.items():
            for g in groups_of(coin):
                net[g] = net.get(g, 0.0) + usd
        for g, usd in net.items():
            if not usd:
                continue
            o = out.setdefault(g, {"long": 0, "short": 0, "long_usd": 0.0, "short_usd": 0.0})
            side = "long" if usd > 0 else "short"
            o[side] += 1
            o[f"{side}_usd"] += abs(usd)
    for o in out.values():
        n = o["long"] + o["short"]
        o["lean"] = round((o["long"] - o["short"]) / n, 4) if n else 0.0
        o["long_usd"], o["short_usd"] = round(o["long_usd"]), round(o["short_usd"])
    return out


_last_lean_bar: int = 0


def _lean_groups(coin: str):
    from sectors import groups
    return (f"coin:{coin}",) + groups(coin)


async def record_lean_at_bar_close(now: Optional[float] = None) -> bool:
    """Once per 4h candle close: refresh positions (even when nobody is viewing)
    and store how profitable traders lean. Six polls a day keep the record unbroken."""
    global _last_lean_bar
    from activity import is_active
    from scan_schedule import SETTLE_SECONDS, last_bar_close
    bar = int(last_bar_close(time.time() if now is None else now)) - SETTLE_SECONDS
    if bar <= _last_lean_bar or not _roster:
        return False
    if not is_active() and not roster_via_cohorts():
        await poll_positions(force=True)       # nobody viewing and no sweep: readings may be hours old
    # With the sweep on, every reading is at most _SNAPSHOT_MAX_AGE_S old (the adaptive cadence's
    # slowest tier plus slack) and an unchanged wallet's reading is its current position, so the
    # record uses the readings on hand rather than reading 600+ wallets at the close.
    rows = profitable_lean(_lean_groups)
    if not rows:
        return False
    try:
        _db_save_trader_lean(bar, rows, ROSTER_VERSION)
        _last_lean_bar = bar
    except Exception as exc:
        logger.warning("HyperLens DB: trader lean save error: %s", exc)
        return False
    logger.info("HyperLens: stored profitable-trader lean for %d groups at bar %d", len(rows), bar)
    return True


def profitable_traders_positioned() -> int:
    return sum(1 for b in _mp_book.values() if b)


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
            _hl_calls.record("meta")
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

    # Filter by minimum account value — no bypass for unpolled wallets.
    # wallet.account_value is either the leaderboard value (before first poll)
    # or the live snapshot value (after polling), so it's always meaningful.
    if min_av > 0:
        source = [w for w in source if w.account_value >= min_av]

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
            "entity": _entity_of.get(w.address),
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


def _cohort_readings(cohort: str):
    """(wallet, latest reading) for one group's wallets with a current reading, with the consensus's
    filters (fresh, not a market maker, not a tiny account). ``cohort``: "profitable" or "large"."""
    group = {w.address for w in (_roster_money_printers if cohort == "profitable" else _roster_smart_money)}
    now = time.time()
    for wallet in _roster:
        if wallet.address not in group:
            continue
        snaps = _snapshots.get(wallet.address)
        if not snaps:
            continue
        latest = snaps[-1]
        if now - latest.timestamp > _fresh_limit(now) or len(latest.positions) > _MM_MAX_POSITIONS:
            continue
        if 0 < latest.account_value < _DISPLAY_MIN_AV:
            continue
        yield wallet, latest


def cohort_positions(coin: str, cohort: str = "profitable") -> List[dict]:
    """Each position one group of tracked wallets holds in a coin, largest first. Same wallets and filters as
    positioning_map, so the dollars match it. ``size_usd`` is valued at entry (as Hyperliquid
    reports it); ``move`` is the unrealised PnL over that, in percent (the price move in the holder's favour);
    ``roe`` is the return on margin in percent; ``entity`` is the wallet's lockstep group (None when it
    trades alone), so counts can take a group once."""
    out = []
    for wallet, latest in _cohort_readings(cohort):
        for p in latest.positions:
            if p.coin.startswith("xyz:") or p.dex == _XYZ_DEX or not p.size or _normalize_coin(p.coin) != coin:
                continue
            roe = p.return_on_equity * 100 if p.return_on_equity else (
                p.unrealized_pnl / p.margin_used * 100 if p.margin_used else None)
            out.append({"address": wallet.address, "side": p.side.lower(), "size_usd": round(p.size_usd),
                        "entry": p.entry_px, "leverage": p.leverage, "upnl": round(p.unrealized_pnl),
                        "roe": None if roe is None else round(roe, 1),
                        "move": round(100 * p.unrealized_pnl / p.size_usd, 2) if p.size_usd else None,
                        "entity": _entity_of.get(wallet.address)})
    out.sort(key=lambda x: -x["size_usd"])
    return out


def positioning_map(cohort: str = "profitable") -> dict:
    """Where one group of tracked wallets is positioned, per coin: counts, dollars and the
    median entry per side, and how many of them are in profit at the current mark.

    Same wallet filters as the consensus; builder-dex markets are skipped. ``cohort`` is
    "profitable" (money printers) or "large" (largest accounts).

    Counts are of traders: wallets that trade as one (hl_entities) count once per coin, on the
    side of their combined dollars, at their dollar-weighted entry, in profit when their combined
    unrealised PnL is positive. Dollars (``usd``) are summed over every wallet; ``wallets`` per side
    is the plain wallet count. ``avg_entry`` per side is the dollar-weighted average entry of the
    traders counted on that side (their positions on that side only; dollars valued at entry), the
    Radar's entry zone. Top level: ``wallets``/``holding`` count wallets, ``traders``/
    ``traders_holding`` count traders.
    """
    raw: Dict[str, dict] = {}
    wallets = holding = 0
    traders: Set[str] = set()
    traders_holding: Set[str] = set()
    for wallet, latest in _cohort_readings(cohort):
        wallets += 1
        ent = entity_of(wallet.address)
        traders.add(ent)
        held = False
        for p in latest.positions:
            if p.coin.startswith("xyz:") or p.dex == _XYZ_DEX or not p.size:
                continue
            held = True
            coin = _normalize_coin(p.coin)
            side = p.side.lower()
            # Current price from the position's unrealised PnL (size_usd is valued at entry).
            mark = p.entry_px + (p.unrealized_pnl if side == "long" else -p.unrealized_pnl) / abs(p.size)
            d = raw.setdefault(coin, {"marks": [], "long": [], "short": [], "ent": {}})
            d["marks"].append(mark)
            d[side].append(p.size_usd)
            e = d["ent"].setdefault(ent, {"net": 0.0, "long": [0.0, 0.0, 0.0], "short": [0.0, 0.0, 0.0]})
            e["net"] += p.size_usd if side == "long" else -p.size_usd
            acc = e[side]                                  # dollars, dollars x entry, unrealised PnL
            acc[0] += p.size_usd
            acc[1] += p.size_usd * p.entry_px
            acc[2] += p.unrealized_pnl
        holding += held
        if held:
            traders_holding.add(ent)
    out: Dict[str, dict] = {}
    for coin, d in raw.items():
        row = {"mark": statistics.median(d["marks"])}
        per_side = {"long": [], "short": []}
        for e in d["ent"].values():
            side = "long" if e["net"] > 0 else "short" if e["net"] < 0 else None
            if side is None:
                continue
            usd, usd_px, upnl = e[side]
            if usd > 0:
                per_side[side].append((usd_px / usd, upnl > 0, usd, usd_px))
        for side in ("long", "short"):
            xs = per_side[side]
            w = sum(x[2] for x in xs)
            row[side] = {"n": len(xs), "usd": round(sum(d[side])), "wallets": len(d[side]),
                         "median_entry": statistics.median(x[0] for x in xs) if xs else None,
                         "avg_entry": sum(x[3] for x in xs) / w if w > 0 else None,
                         "in_profit": sum(1 for x in xs if x[1])}
        out[coin] = row
    return {"wallets": wallets, "holding": holding, "traders": len(traders),
            "traders_holding": len(traders_holding), "coins": out}


def wallet_positions(address: str) -> dict:
    """A tracked wallet's latest reading: every perpetual position, largest first."""
    snaps = _snapshots.get(address) or _snapshots.get(address.lower())
    if not snaps:
        return {"ts": None, "account_value": None, "positions": []}
    latest = snaps[-1]
    out = []
    for p in latest.positions:
        if p.coin.startswith("xyz:") or p.dex == _XYZ_DEX:
            continue
        roe = p.return_on_equity * 100 if p.return_on_equity else (
            p.unrealized_pnl / p.margin_used * 100 if p.margin_used else 0.0)
        out.append({"coin": _normalize_coin(p.coin), "side": p.side.lower(), "size_usd": round(p.size_usd),
                    "entry_px": p.entry_px, "pnl_pct": round(roe, 1), "leverage": p.leverage})
    out.sort(key=lambda x: -x["size_usd"])
    return {"ts": latest.timestamp, "account_value": latest.account_value, "positions": out}


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
        if now - latest.timestamp > _fresh_limit(now):
            continue
        # MM filter — same as consensus
        if len(latest.positions) > _MM_MAX_POSITIONS:
            continue
        # AV filter — same as consensus
        if 0 < latest.account_value < _DISPLAY_MIN_AV:
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
                    "entity": _entity_of.get(wallet.address),
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
    """A trade by a wallet followed through the older whale_follows list, through the alert
    gate (category "whales", off by default; once per wallet, coin and action a day)."""
    import tg_alerts as ta
    from wallet_names import codename

    action = str(event.get("action", "?")).lower()
    if action not in ("opened", "closed", "flipped"):
        return
    side = str(event.get("side", "?")).lower()
    coin = event.get("coin", "?")
    wallet = event.get("wallet", "")
    cohort = event.get("cohort", "tracked").replace("_", " ")
    head = f"{ta.esc(codename(wallet))} {action} {ta.esc(side)} {ta.coin_b(coin)} {ta.usd(event.get('size_usd', 0))}"
    if action == "closed":
        pnl = event.get("pnl", 0) or 0
        detail = f"PnL {'+' if pnl >= 0 else '-'}{ta.usd(abs(pnl))} ({event.get('pnl_pct', 0):+.1f}%)"
    else:
        detail = f"At {ta.px(event.get('entry_px', 0))} · {event.get('leverage', 1):.0f}x"
    ta.submit_nowait("whales", f"{wallet}:{coin}:{action}", f"{head}\n{ta.esc(detail)} · {ta.esc(cohort)}",
                     head, chats=[chat_id])


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
            if p.liq_distance_pct:
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
        # Lockstep group (hl_entities): counted as one trader with its other wallets; None if alone
        "entity": entity_info(address),
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
        if now - latest.timestamp > _fresh_limit(now):
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
                _hl_calls.record("l2Book")
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

    # Same wallets and symbol names as the consensus, so the symbol pop-up agrees
    # with the row it was opened from.
    now = time.time()
    for wallet in _roster:
        snaps = _snapshots.get(wallet.address)
        if not snaps:
            continue
        latest = snaps[-1]
        if (now - latest.timestamp > _fresh_limit(now) or len(latest.positions) > _MM_MAX_POSITIONS
                or 0 < latest.account_value < _DISPLAY_MIN_AV):
            continue
        for pos in latest.positions:
            if pos.coin.startswith("xyz:") or pos.dex == _XYZ_DEX:
                pos_coin = f"xyz:{pos.coin.split(':', 1)[-1]}"
            else:
                pos_coin = _normalize_coin(pos.coin)
            if pos_coin == coin and pos.liq_px > 0:
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


def _fills_store_status() -> dict:
    try:
        import hl_fills
        return hl_fills.status()
    except Exception as exc:
        return {"error": str(exc)}


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
        "roster_version": ROSTER_VERSION,
        "roster_targets": {"money_printer": MP_TARGET, "smart_money": SM_TARGET, "elite_keep_rank": ELITE_KEEP_RANK,
                           "min_perp_equity": _MIN_PERP_EQUITY},
        "money_printer_count": len(_roster_money_printers),
        "smart_money_count": len(_roster_smart_money),
        "elite_count": elite_count,
        "wallets_with_data": len(_snapshots),
        "fresh_wallets": _fresh_wallets,            # updated within the staleness window
        "consensus_wallets": _consensus_wallets,    # of those, the ones the consensus counts
        "consensus_symbols": len(_consensus),
        "last_poll": _last_poll_at or None,
        "last_roster_refresh": _roster_updated_at or None,
        "poll_count": _poll_count,
        "poll_interval_sec": _POLL_INTERVAL,
        "idle_roster_poll_interval_sec": _ROSTER_IDLE_POLL_INTERVAL,
        "cadence": {
            "roster_read_by": "cohort_sweep" if roster_via_cohorts() else "hyperlens",
            "followed_s": _cadence.FOLLOWED_S, "after_change_s": list(_cadence.BACKOFF_S),
            "flat_s": _cadence.FLAT_S, "elite_max_s": _cadence.ELITE_MAX_S, "tick_s": _cadence.TICK_S,
            "reading_max_age_s": _SNAPSHOT_MAX_AGE_S,
        },
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
        # Hyperliquid info API calls per minute by request type (every caller in this process)
        "api_calls": _hl_calls.stats(),
        # Stored fills of the roster (hl_fills): backfill progress, size, its Hyperliquid weight
        "fills_store": _fills_store_status(),
        # Lockstep groups: wallets counted as one trader
        "entities": {"groups": len(_entity_members), "wallets": len(_entity_of),
                     "computed_at": _entities_at or None,
                     "sizes": sorted((len(m) for m in _entity_members.values()), reverse=True)},
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
    """Main background loop: refresh roster daily, poll positions every 10 min.

    Runtime-toggleable via /api/admin/features (flag: hyperlens_enabled).
    When disabled, the loop sleeps and skips work; toggling back on takes
    effect within ~30s without restart. The order book / pressure-map
    sub-task is gated on a separate flag (hyperlens_pressure_map).
    """
    global _initialized, _seed_task
    from feature_flags import get_flag

    logger.info("HyperLens: starting background loop...")

    # Restore persisted data from SQLite (cheap, runs once)
    try:
        _restore_from_db()
    except Exception as exc:
        logger.warning("HyperLens: DB restore failed (starting fresh): %s", exc)

    # Initial delay — let the main scan warm up first
    await asyncio.sleep(15)
    from activity import is_active, idle_sleep

    last_roster_refresh = 0.0
    last_cleanup = time.time() - 6 * 3600 + 600     # first cleanup ~10 min after start
    pressure_task: Optional[asyncio.Task] = None

    while True:
        try:
            if not get_flag("hyperlens_enabled"):
                await asyncio.sleep(30)
                continue

            # Initial roster fetch on first run after enable
            if not _initialized or not _roster:
                count = await refresh_leaderboard()
                if count == 0:
                    logger.warning("HyperLens: empty roster, retrying in 5 min")
                    _initialized = True  # don't busy-loop
                    await asyncio.sleep(5 * 60)
                    continue
                _initialized = True
                last_roster_refresh = time.time()
                await recompute_entities()
                if _seed_task is None:          # background: groups known before the log has filled
                    _seed_task = asyncio.create_task(_seed_then_group())

            # Pressure map sub-task — spawn/cancel based on the flag
            if get_flag("hyperlens_pressure_map"):
                if pressure_task is None or pressure_task.done():
                    pressure_task = asyncio.create_task(_order_book_loop())
                    logger.info("HyperLens pressure map: ENABLED (sub-task spawned)")
            else:
                if pressure_task is not None and not pressure_task.done():
                    pressure_task.cancel()
                    pressure_task = None
                    logger.info("HyperLens pressure map: DISABLED (sub-task cancelled)")

            # Refresh roster daily
            if time.time() - last_roster_refresh > _ROSTER_REFRESH_INTERVAL:
                await refresh_leaderboard()
                last_roster_refresh = time.time()
                await recompute_entities()

            # Poll positions — skip while idle (no viewer to serve); the poll
            # hits Hyperliquid once per roster member, so at rest this is the
            # bulk of HyperLens's cost. Resumes on the next active cycle.
            # Followed traders are still read while idle (one request each) when the
            # cohort sweep covers the roster, so their Telegram alerts stay timely.
            if _roster and (is_active() or (roster_via_cohorts() and _followed_any())):
                await poll_positions()
            if _roster:
                await record_lean_at_bar_close()

            # DB cleanup every 6 hours
            if time.time() - last_cleanup > 6 * 3600:
                try:
                    await asyncio.to_thread(_db_cleanup)      # may VACUUM: keep it off the event loop
                except Exception as exc:
                    logger.warning("HyperLens DB cleanup error: %s", exc)
                last_cleanup = time.time()

        except Exception as exc:
            logger.warning("HyperLens loop error: %s", exc)

        # Tick every 5 min while someone is viewing, or while followed wallets need their 5-min
        # reading for Telegram alerts; otherwise a long interruptible nap.
        if is_active() or (roster_via_cohorts() and _followed_any()):
            await asyncio.sleep(_POLL_INTERVAL)
        else:
            await idle_sleep(_ROSTER_IDLE_POLL_INTERVAL)
