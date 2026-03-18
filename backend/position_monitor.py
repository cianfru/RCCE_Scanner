"""
position_monitor.py
~~~~~~~~~~~~~~~~~~~
Monitors open Hyperliquid positions for registered wallets and pushes
Telegram notifications when regime/signal changes affect held coins.

Features
--------
- Register wallet addresses linked to TG chat IDs
- Cross-reference open HL positions with scanner signal/regime changes
- Push alerts for regime changes, signal downgrades/upgrades on held coins
- Notify about new opportunities (STRONG_LONG, LIGHT_LONG)
- Periodic portfolio overview (every 6 hours, configurable)

Persistence: data/monitor_registry.json
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence directory
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).resolve().parent / "data"
_REGISTRY_PATH = _PERSIST_DIR / "monitor_registry.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OPPORTUNITY_SIGNALS = {"STRONG_LONG", "LIGHT_LONG"}
_ADVERSE_SIGNALS = {"TRIM", "TRIM_HARD", "NO_LONG", "RISK_OFF"}
_DEFAULT_OVERVIEW_INTERVAL = 6 * 3600  # 6 hours
_MAX_NOTIFICATIONS_PER_CYCLE = 10

# Signal ranking (higher = more bullish)
_SIGNAL_RANK = {
    "NO_LONG": -2, "RISK_OFF": -1, "TRIM_HARD": 0, "TRIM": 1,
    "WAIT": 2, "REVIVAL_SEED": 3, "ACCUMULATE": 4,
    "LIGHT_LONG": 5, "STRONG_LONG": 6,
}

# Thresholds for position-aware warnings
_HEAT_WARNING_THRESHOLD = 70
_HEAT_DANGER_THRESHOLD = 85
_LIQ_WARNING_PCT = 15            # warn if price within 15% of liq
_OI_TREND_ADVERSE = {"SQUEEZE", "LIQUIDATING"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Watcher:
    """A registered wallet linked to a TG chat."""
    chat_id: int
    address: str
    registered_at: float = 0.0
    notify_regime_changes: bool = True
    notify_signal_changes: bool = True
    notify_opportunities: bool = True
    overview_interval_hours: int = 6
    last_overview_ts: float = 0.0

    def to_dict(self) -> dict:
        return {
            "chat_id": self.chat_id,
            "address": self.address,
            "registered_at": self.registered_at,
            "notify_regime_changes": self.notify_regime_changes,
            "notify_signal_changes": self.notify_signal_changes,
            "notify_opportunities": self.notify_opportunities,
            "overview_interval_hours": self.overview_interval_hours,
            "last_overview_ts": self.last_overview_ts,
        }

    @staticmethod
    def from_dict(d: dict) -> "Watcher":
        return Watcher(
            chat_id=d["chat_id"],
            address=d["address"],
            registered_at=d.get("registered_at", 0),
            notify_regime_changes=d.get("notify_regime_changes", True),
            notify_signal_changes=d.get("notify_signal_changes", True),
            notify_opportunities=d.get("notify_opportunities", True),
            overview_interval_hours=d.get("overview_interval_hours", 6),
            last_overview_ts=d.get("last_overview_ts", 0),
        )


# ---------------------------------------------------------------------------
# PositionMonitor
# ---------------------------------------------------------------------------

class PositionMonitor:
    """Singleton that monitors HL positions and sends TG alerts."""

    _instance: Optional["PositionMonitor"] = None

    def __init__(self):
        self.watchers: List[Watcher] = []
        # Track last-notified signal/regime per (chat_id, symbol) to avoid spam
        self._last_notified_signal: Dict[str, str] = {}   # "chatid:symbol" -> signal
        self._last_notified_regime: Dict[str, str] = {}   # "chatid:symbol" -> regime
        # Track last-notified warnings to avoid repeating the same alert
        # Key: "chatid:symbol:warning_type" -> timestamp of last alert
        self._last_warned: Dict[str, float] = {}
        self._WARNING_COOLDOWN = 3600  # don't repeat same warning within 1 hour
        self._load()

    @classmethod
    def get(cls) -> "PositionMonitor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- Persistence ----------------------------------------------------------

    def _load(self):
        if _REGISTRY_PATH.exists():
            try:
                data = json.loads(_REGISTRY_PATH.read_text())
                self.watchers = [Watcher.from_dict(w) for w in data.get("watchers", [])]
                logger.info("Loaded %d monitor watchers", len(self.watchers))
            except Exception as e:
                logger.warning("Failed to load monitor registry: %s", e)

    def _save(self):
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        data = {"watchers": [w.to_dict() for w in self.watchers]}
        _REGISTRY_PATH.write_text(json.dumps(data, indent=2))

    # -- Registration ---------------------------------------------------------

    def register(self, chat_id: int, address: str) -> str:
        """Register a wallet for monitoring. Returns status message."""
        address = address.strip().lower()
        if not address.startswith("0x") or len(address) != 42:
            return "Invalid address. Please provide a valid EVM wallet address (0x...)."

        # Check if already registered for this chat
        for w in self.watchers:
            if w.chat_id == chat_id:
                old_addr = w.address
                w.address = address
                w.registered_at = time.time()
                self._save()
                if old_addr == address:
                    return f"Already monitoring {address[:8]}...{address[-4:]}"
                return f"Updated: now monitoring {address[:8]}...{address[-4:]} (was {old_addr[:8]}...{old_addr[-4:]})"

        self.watchers.append(Watcher(
            chat_id=chat_id,
            address=address,
            registered_at=time.time(),
        ))
        self._save()
        return f"Monitoring started for {address[:8]}...{address[-4:]}\nYou'll receive alerts for regime/signal changes on your open positions."

    def unregister(self, chat_id: int) -> str:
        """Remove monitoring for a chat."""
        before = len(self.watchers)
        self.watchers = [w for w in self.watchers if w.chat_id != chat_id]
        if len(self.watchers) < before:
            self._save()
            return "Monitoring stopped. You won't receive position alerts anymore."
        return "No active monitoring found for this chat."

    def get_watcher(self, chat_id: int) -> Optional[Watcher]:
        for w in self.watchers:
            if w.chat_id == chat_id:
                return w
        return None

    # -- Core: post-scan notification dispatch --------------------------------

    async def on_scan_complete(self, scan_results: Dict[str, List[dict]]):
        """Called after each scan cycle. Checks positions and sends alerts.

        Parameters
        ----------
        scan_results : dict
            Keyed by timeframe ("4h", "1d"), values are lists of scan result dicts.
        """
        if not self.watchers:
            return

        from hyperliquid_data import fetch_clearinghouse_state, parse_open_positions

        # Build lookup: symbol -> result (prefer 4h for faster signals)
        results_by_symbol: Dict[str, dict] = {}
        for tf in ("4h", "1d"):
            for r in scan_results.get(tf, []):
                sym = r.get("symbol", "")
                if sym not in results_by_symbol:
                    results_by_symbol[sym] = r

        for watcher in self.watchers:
            try:
                await self._process_watcher(watcher, results_by_symbol)
            except Exception as e:
                logger.warning("Monitor failed for chat %s: %s", watcher.chat_id, e)

    async def _process_watcher(
        self,
        watcher: Watcher,
        results_by_symbol: Dict[str, dict],
    ):
        """Process a single watcher: fetch positions, detect changes, notify."""
        from hyperliquid_data import fetch_clearinghouse_state, parse_open_positions

        # Fetch current HL positions
        clearinghouse = await fetch_clearinghouse_state(watcher.address)
        if clearinghouse is None:
            return

        positions = parse_open_positions(clearinghouse)
        held_symbols: Set[str] = {p["symbol"] for p in positions}

        notifications: List[str] = []

        # -- 1. Check regime/signal changes on held positions --
        for pos in positions:
            sym = pos["symbol"]
            scan = results_by_symbol.get(sym)
            if not scan:
                continue

            key = f"{watcher.chat_id}:{sym}"
            current_signal = scan.get("signal", "WAIT")
            current_regime = scan.get("regime", "FLAT")

            # Regime change on held position
            prev_regime = self._last_notified_regime.get(key)
            if (watcher.notify_regime_changes
                    and prev_regime is not None
                    and current_regime != prev_regime):
                notifications.append(self._fmt_regime_change(pos, scan, prev_regime))

            # Signal change on held position
            prev_signal = self._last_notified_signal.get(key)
            if (watcher.notify_signal_changes
                    and prev_signal is not None
                    and current_signal != prev_signal):
                notifications.append(self._fmt_signal_change(pos, scan, prev_signal))

            # Update tracking
            self._last_notified_signal[key] = current_signal
            self._last_notified_regime[key] = current_regime

        # -- 2. Position-aware warnings (heat, divergence, OI, liq) --
        for pos in positions:
            sym = pos["symbol"]
            scan = results_by_symbol.get(sym)
            if not scan:
                continue

            coin = pos["coin"]
            side = pos["side"]
            key_base = f"{watcher.chat_id}:{sym}"

            # Helper: check warning cooldown
            def _should_warn(warn_type: str) -> bool:
                wkey = f"{key_base}:{warn_type}"
                last = self._last_warned.get(wkey, 0)
                if time.time() - last < self._WARNING_COOLDOWN:
                    return False
                self._last_warned[wkey] = time.time()
                return True

            # -- Heat warning --
            heat = scan.get("heat", 0)
            if side == "LONG" and heat >= _HEAT_DANGER_THRESHOLD and _should_warn("heat_danger"):
                notifications.append(
                    f"\U0001f525 HEAT DANGER \u2014 {coin}\n"
                    f"Heat: {heat}/100 (danger zone)\n"
                    f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                    f"PnL: ${pos['unrealized_pnl']:+,.2f}\n"
                    f"Action: Strongly consider trimming \u2014 blow-off risk is high"
                )
            elif side == "LONG" and heat >= _HEAT_WARNING_THRESHOLD and _should_warn("heat_warn"):
                notifications.append(
                    f"\u26a0\ufe0f HEAT RISING \u2014 {coin}\n"
                    f"Heat: {heat}/100 \u2014 approaching overextension\n"
                    f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                    f"Watch for trim signals"
                )

            # -- Divergence warning --
            divergence = scan.get("divergence")
            if divergence and _should_warn("divergence"):
                if side == "LONG" and "BEAR" in str(divergence).upper():
                    notifications.append(
                        f"\u26a0\ufe0f BEAR DIVERGENCE \u2014 {coin}\n"
                        f"{coin} is in {scan.get('regime', '?')} but BTC is bearish\n"
                        f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                        f"PnL: ${pos['unrealized_pnl']:+,.2f}\n"
                        f"Risk: divergence from BTC often resolves downward"
                    )
                elif side == "SHORT" and "BULL" in str(divergence).upper():
                    notifications.append(
                        f"\u26a0\ufe0f BULL DIVERGENCE \u2014 {coin}\n"
                        f"{coin} is bearish but BTC is in MARKUP\n"
                        f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                        f"Risk: bull divergence may squeeze shorts"
                    )

            # -- OI trend warning (the case you saw yesterday) --
            positioning = scan.get("positioning") or {}
            oi_trend = positioning.get("oi_trend", "")
            if side == "LONG" and oi_trend in ("SQUEEZE", "LIQUIDATING") and _should_warn("oi_adverse"):
                notifications.append(
                    f"\u26a0\ufe0f OI WARNING \u2014 {coin}\n"
                    f"OI Trend: {oi_trend} (positions closing while you're {side})\n"
                    f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                    f"PnL: ${pos['unrealized_pnl']:+,.2f}\n"
                    f"Risk: declining OI suggests conviction weakening"
                )
            elif side == "LONG" and oi_trend == "DECLINING" and heat >= 60 and _should_warn("oi_declining_hot"):
                notifications.append(
                    f"\u26a0\ufe0f OI DECLINING + HEAT \u2014 {coin}\n"
                    f"OI dropping + Heat at {heat} \u2014 possible exhaustion\n"
                    f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                    f"Watch for reversal confirmation"
                )

            # -- Funding crowding warning --
            funding_regime = positioning.get("funding_regime", "")
            if side == "LONG" and funding_regime == "CROWDED_LONG" and _should_warn("crowded"):
                notifications.append(
                    f"\u26a0\ufe0f CROWDED LONG \u2014 {coin}\n"
                    f"Funding is extreme ({positioning.get('funding_rate', 0)*100:.4f}%)\n"
                    f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                    f"Risk: crowded funding = squeeze risk"
                )

            # -- Liquidation proximity warning --
            liq = pos.get("liq_px", 0)
            current_price = scan.get("price", 0)
            if liq > 0 and current_price > 0:
                liq_dist = abs(current_price - liq) / current_price * 100
                if liq_dist < _LIQ_WARNING_PCT and _should_warn("liq_proximity"):
                    notifications.append(
                        f"\U0001f6a8 LIQUIDATION RISK \u2014 {coin}\n"
                        f"Current: ${current_price:.6g} | Liq: ${liq:.6g} ({liq_dist:.1f}% away)\n"
                        f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                        f"ACTION REQUIRED: Add margin or reduce position"
                    )

            # -- Exhaustion state warning --
            exh_state = scan.get("exhaustion_state", "")
            if side == "LONG" and exh_state == "CLIMAX" and _should_warn("climax"):
                notifications.append(
                    f"\u26a0\ufe0f EXHAUSTION CLIMAX \u2014 {coin}\n"
                    f"Volume climax detected \u2014 entries should be blocked\n"
                    f"You hold: {side} ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                    f"Consider taking profits or tightening stops"
                )

        # -- 2b. Exhaustion confirmation on HELD positions (positive reinforcement) --
        for pos in positions:
            sym = pos["symbol"]
            scan = results_by_symbol.get(sym)
            if not scan:
                continue

            coin = pos["coin"]
            side = pos["side"]
            key_base = f"{watcher.chat_id}:{sym}"

            def _should_warn_pos(warn_type: str) -> bool:
                wkey = f"{key_base}:{warn_type}"
                last = self._last_warned.get(wkey, 0)
                if time.time() - last < self._WARNING_COOLDOWN:
                    return False
                self._last_warned[wkey] = time.time()
                return True

            exh_state = scan.get("exhaustion_state", "")
            floor_confirmed = scan.get("floor_confirmed", False)
            is_absorption = scan.get("is_absorption", False)

            # Floor confirmed while holding LONG → validates the thesis
            if side == "LONG" and floor_confirmed and _should_warn_pos("floor_confirm_long"):
                pnl = pos["unrealized_pnl"]
                pnl_sign = "+" if pnl >= 0 else ""
                notifications.append(
                    f"\U0001f7e2 FLOOR CONFIRMED \u2014 {coin}\n"
                    f"Absorption cluster + volume dry-up confirmed below weekly BMSB\n"
                    f"Sellers appear exhausted \u2014 your LONG thesis is supported\n"
                    f"You hold: LONG ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                    f"PnL: {pnl_sign}${pnl:,.2f}\n"
                    f"Action: Hold position \u2014 watch for signal upgrade"
                )

            # Absorbing while in BEAR_ZONE holding LONG → early positive signal
            elif side == "LONG" and is_absorption and exh_state == "BEAR_ZONE" and _should_warn_pos("absorbing_long"):
                notifications.append(
                    f"\U0001f4a7 ABSORPTION FORMING \u2014 {coin}\n"
                    f"Early absorption cluster detected below weekly BMSB\n"
                    f"Volume effort is high but candle range is contracting \u2014 sellers tiring\n"
                    f"You hold: LONG ${pos['size_usd']:,.0f} @ {pos['leverage']:.0f}x\n"
                    f"Not yet confirmed \u2014 wait for floor_confirmed or signal upgrade"
                )

        # -- 3. Check for new opportunities (not already held) --
        if watcher.notify_opportunities:
            for sym, scan in results_by_symbol.items():
                if sym in held_symbols:
                    continue
                signal = scan.get("signal", "WAIT")
                key = f"{watcher.chat_id}:{sym}"
                prev = self._last_notified_signal.get(key)

                # Standard signal-based opportunity (STRONG_LONG, LIGHT_LONG)
                if signal in _OPPORTUNITY_SIGNALS and prev != signal:
                    notifications.append(self._fmt_opportunity(scan))
                    self._last_notified_signal[key] = signal
                    continue

                # --- Exhaustion-based entry opportunities ---
                exh_state   = scan.get("exhaustion_state", "")
                floor_conf  = scan.get("floor_confirmed", False)
                is_climax   = scan.get("is_climax", False)
                is_absorb   = scan.get("is_absorption", False)
                regime      = scan.get("regime", "")

                # EXHAUSTED_FLOOR — strongest entry signal: confirmed absorption cluster + volume drying up
                if floor_conf and signal not in _ADVERSE_SIGNALS:
                    wkey = f"{key}:exh_floor"
                    if time.time() - self._last_warned.get(wkey, 0) > self._WARNING_COOLDOWN:
                        self._last_warned[wkey] = time.time()
                        notifications.append(self._fmt_exhaustion_entry(scan, "FLOOR"))

                # CLIMAX — downside capitulation bar on a coin not in full downtrend
                elif is_climax and regime not in ("MARKDOWN", "CAP"):
                    wkey = f"{key}:exh_climax_entry"
                    if time.time() - self._last_warned.get(wkey, 0) > self._WARNING_COOLDOWN:
                        self._last_warned[wkey] = time.time()
                        notifications.append(self._fmt_exhaustion_entry(scan, "CLIMAX"))

                # ABSORBING — early stage, only when signal is constructive
                elif is_absorb and signal in ("ACCUMULATE", "REVIVAL_SEED", "LIGHT_LONG", "STRONG_LONG"):
                    wkey = f"{key}:exh_absorb"
                    if time.time() - self._last_warned.get(wkey, 0) > self._WARNING_COOLDOWN * 2:  # 2h cooldown, less urgent
                        self._last_warned[wkey] = time.time()
                        notifications.append(self._fmt_exhaustion_entry(scan, "ABSORBING"))

                # --- OI / Price divergence setups ---
                positioning   = scan.get("positioning") or {}
                oi_trend      = positioning.get("oi_trend", "UNKNOWN")
                funding_regime = positioning.get("funding_regime", "NEUTRAL")
                funding_rate  = positioning.get("funding_rate", 0.0)
                oi_change_pct = positioning.get("oi_change_pct", 0.0)

                _bullish_regimes = {"MARKUP", "REACC", "ACCUM"}

                # SHORTING into bullish regime → squeeze setup
                if (oi_trend == "SHORTING"
                        and regime in _bullish_regimes
                        and signal not in _ADVERSE_SIGNALS
                        and heat < 70):
                    wkey = f"{key}:oi_squeeze"
                    if time.time() - self._last_warned.get(wkey, 0) > self._WARNING_COOLDOWN:
                        self._last_warned[wkey] = time.time()
                        notifications.append(self._fmt_oi_setup(scan, "SQUEEZE_SETUP"))

                # Crowded short + entry signal → textbook squeeze
                elif (funding_regime == "CROWDED_SHORT"
                          and signal in _OPPORTUNITY_SIGNALS
                          and regime not in ("MARKDOWN", "CAP")):
                    wkey = f"{key}:crowded_short"
                    if time.time() - self._last_warned.get(wkey, 0) > self._WARNING_COOLDOWN:
                        self._last_warned[wkey] = time.time()
                        notifications.append(self._fmt_oi_setup(scan, "CROWDED_SHORT"))

                # OI front-run: BUILDING + pre-signal (smart money loading)
                elif (oi_trend == "BUILDING"
                          and oi_change_pct >= 5.0
                          and signal in ("ACCUMULATE", "REVIVAL_SEED", "WAIT")
                          and heat < 50
                          and regime not in ("MARKDOWN", "CAP")):
                    wkey = f"{key}:oi_frontrun"
                    if time.time() - self._last_warned.get(wkey, 0) > self._WARNING_COOLDOWN:
                        self._last_warned[wkey] = time.time()
                        notifications.append(self._fmt_oi_setup(scan, "OI_FRONT_RUN"))

                # Shorts into exhaustion floor → highest conviction contrarian setup
                elif (oi_trend == "SHORTING"
                          and (scan.get("floor_confirmed") or scan.get("is_climax"))
                          and signal not in _ADVERSE_SIGNALS):
                    wkey = f"{key}:shorts_floor"
                    if time.time() - self._last_warned.get(wkey, 0) > self._WARNING_COOLDOWN:
                        self._last_warned[wkey] = time.time()
                        notifications.append(self._fmt_oi_setup(scan, "SHORTS_INTO_FLOOR"))

        # -- 3. Rate-limit and send --
        if notifications:
            await self._send_notifications(watcher.chat_id, notifications)

        # -- 4. Periodic overview --
        now = time.time()
        interval = watcher.overview_interval_hours * 3600
        if interval > 0 and (now - watcher.last_overview_ts) >= interval:
            overview = self._fmt_overview(positions, results_by_symbol)
            await self._send_tg(watcher.chat_id, overview)
            watcher.last_overview_ts = now
            self._save()

    # -- Notification formatting ----------------------------------------------

    def _fmt_regime_change(self, pos: dict, scan: dict, prev_regime: str) -> str:
        regime = scan.get("regime", "?")
        signal = scan.get("signal", "?")
        coin = pos["coin"]
        side = pos["side"]
        size_usd = pos["size_usd"]
        leverage = pos["leverage"]
        pnl = pos["unrealized_pnl"]
        pnl_sign = "+" if pnl >= 0 else ""

        return (
            f"\u26a0\ufe0f REGIME CHANGE \u2014 {coin}\n"
            f"{prev_regime} \u2192 {regime}\n"
            f"You hold: {side} {pos['size']:.4g} {coin} (${size_usd:,.0f}) @ {leverage:.0f}x\n"
            f"Unrealized PnL: {pnl_sign}${pnl:,.2f}\n"
            f"Current signal: {signal}"
        )

    def _fmt_signal_change(self, pos: dict, scan: dict, prev_signal: str) -> str:
        signal = scan.get("signal", "?")
        coin = pos["coin"]
        side = pos["side"]
        pnl = pos["unrealized_pnl"]
        pnl_sign = "+" if pnl >= 0 else ""

        old_rank = _SIGNAL_RANK.get(prev_signal, 2)
        new_rank = _SIGNAL_RANK.get(signal, 2)

        if new_rank > old_rank:
            icon = "\U0001f7e2"  # green circle
            direction = "UPGRADED"
        elif new_rank < old_rank:
            icon = "\U0001f53b"  # red triangle down
            direction = "DOWNGRADED"
        else:
            icon = "\u2194\ufe0f"
            direction = "CHANGED"

        action = ""
        if signal in _ADVERSE_SIGNALS and side == "LONG":
            action = "\nAction: Consider reducing/closing LONG exposure"
        elif signal in _OPPORTUNITY_SIGNALS and side == "SHORT":
            action = "\nAction: Caution \u2014 signal is bullish, you're SHORT"

        conditions = ""
        met = scan.get("conditions_met")
        total = scan.get("conditions_total")
        if met is not None and total is not None:
            conditions = f" | Conditions: {met}/{total}"

        return (
            f"{icon} SIGNAL {direction} \u2014 {coin}\n"
            f"{prev_signal} \u2192 {signal}\n"
            f"You hold: {side} {pos['size']:.4g} {coin} (${pos['size_usd']:,.0f}) @ {pos['leverage']:.0f}x\n"
            f"PnL: {pnl_sign}${pnl:,.2f}{conditions}"
            f"{action}"
        )

    def _fmt_oi_setup(self, scan: dict, setup_type: str) -> str:
        """Format an OI/price divergence setup notification."""
        sym  = scan.get("symbol", "?")
        base = sym.split("/")[0]
        signal = scan.get("signal", "?")
        regime = scan.get("regime", "?")
        heat   = scan.get("heat", 0)
        price  = scan.get("price", 0)
        met    = scan.get("conditions_met")
        total  = scan.get("conditions_total")
        positioning = scan.get("positioning") or {}
        oi_trend    = positioning.get("oi_trend", "?")
        funding_regime = positioning.get("funding_regime", "NEUTRAL")
        funding_rate   = positioning.get("funding_rate", 0.0)
        oi_change_pct  = positioning.get("oi_change_pct", 0.0)
        cond_str = f" | Conditions: {met}/{total}" if met is not None else ""
        fund_str = f"\nFunding: {funding_rate*100:.4f}%/8h ({funding_regime})" if funding_regime != "NEUTRAL" else ""

        if setup_type == "SQUEEZE_SETUP":
            return (
                f"\U0001f300 OI DIVERGENCE \u2014 {base}\n"
                f"OI \u2191 + price \u2193 (SHORTING) into a {regime} regime\n"
                f"Crowd is shorting against the trend \u2014 squeeze risk if price holds\n"
                f"Price: ${price:.4g} | Signal: {signal} | Heat: {heat}/100{fund_str}\n"
                f"{cond_str}\n"
                f"Action: Monitor for reversal confirmation \u2014 do NOT chase short"
            )
        elif setup_type == "CROWDED_SHORT":
            return (
                f"\U0001f525 CROWDED SHORT + ENTRY \u2014 {base}\n"
                f"Extreme short funding ({funding_rate*100:.4f}%/8h) \u2014 shorts paying premium\n"
                f"Signal: {signal} | Regime: {regime} | Heat: {heat}/100\n"
                f"Textbook squeeze setup: shorts trapped with bullish confirmation{cond_str}\n"
                f"Action: Watch for entry on any upside confirmation"
            )
        elif setup_type == "OI_FRONT_RUN":
            return (
                f"\U0001f4c8 OI FRONT-RUN \u2014 {base}\n"
                f"OI +{oi_change_pct:.1f}% (BUILDING) but signal still {signal}\n"
                f"Smart money loading positions before signal upgrade\n"
                f"Price: ${price:.4g} | Regime: {regime} | Heat: {heat}/100{cond_str}\n"
                f"Action: Watch for signal upgrade to LIGHT/STRONG LONG as confirmation"
            )
        elif setup_type == "SHORTS_INTO_FLOOR":
            floor = "floor confirmed" if scan.get("floor_confirmed") else "downside climax"
            return (
                f"\u26a1 SHORTS INTO FLOOR \u2014 {base}\n"
                f"OI rising (crowd shorting) while exhaustion engine shows {floor}\n"
                f"Sellers exhausted + shorts loading = high-conviction reversal setup\n"
                f"Price: ${price:.4g} | Signal: {signal} | Regime: {regime}\n"
                f"Heat: {heat}/100{cond_str}\n"
                f"Action: Highest-conviction contrarian long \u2014 wait for signal confirmation"
            )
        return f"\U0001f4ca OI SETUP \u2014 {base}: {setup_type} | {signal} | {regime}"

    def _fmt_exhaustion_entry(self, scan: dict, exh_type: str) -> str:
        """Format an exhaustion-based entry opportunity notification."""
        sym = scan.get("symbol", "?")
        base = sym.split("/")[0]
        signal = scan.get("signal", "?")
        regime = scan.get("regime", "?")
        heat   = scan.get("heat", 0)
        price  = scan.get("price", 0)
        met    = scan.get("conditions_met")
        total  = scan.get("conditions_total")
        cond_str = f" | Conditions: {met}/{total}" if met is not None else ""

        if exh_type == "FLOOR":
            return (
                f"\U0001f7e2 EXHAUSTION FLOOR \u2014 {base}\n"
                f"Absorption cluster confirmed + volume drying up below weekly BMSB\n"
                f"Sellers appear exhausted \u2014 potential reversal / long entry zone\n"
                f"Price: ${price:.4g} | Regime: {regime} | Signal: {signal}\n"
                f"Heat: {heat}/100{cond_str}\n"
                f"Action: Watch for signal upgrade to ACCUMULATE or LONG to confirm"
            )
        elif exh_type == "CLIMAX":
            return (
                f"\u26a1 DOWNSIDE CLIMAX \u2014 {base}\n"
                f"Capitulation bar: wide range, strong lower wick, high effort\n"
                f"Below weekly BMSB \u2014 panic selling may be exhausting\n"
                f"Price: ${price:.4g} | Regime: {regime} | Signal: {signal}\n"
                f"Heat: {heat}/100{cond_str}\n"
                f"Action: Do NOT chase immediately \u2014 wait for absorption or signal confirmation"
            )
        else:  # ABSORBING
            return (
                f"\U0001f4a7 ABSORPTION CLUSTER \u2014 {base}\n"
                f"Early absorption signals forming below weekly BMSB\n"
                f"High effort + narrow candle range \u2014 sellers may be tiring\n"
                f"Price: ${price:.4g} | Regime: {regime} | Signal: {signal}\n"
                f"Heat: {heat}/100{cond_str}\n"
                f"Early stage \u2014 not yet confirmed. Watch for floor_confirmed or ACCUMULATE signal"
            )

    def _fmt_opportunity(self, scan: dict) -> str:
        sym = scan.get("symbol", "?")
        base = sym.split("/")[0]
        signal = scan.get("signal", "?")
        regime = scan.get("regime", "?")
        z = scan.get("zscore")
        heat = scan.get("heat")
        met = scan.get("conditions_met")
        total = scan.get("conditions_total")
        confluence = scan.get("confluence", {})
        conf_label = confluence.get("label", "?") if isinstance(confluence, dict) else "?"

        z_str = f"Z: {z:.2f}" if z is not None else ""
        heat_str = f"Heat: {heat:.0f}" if heat is not None else ""
        cond_str = f"Conditions: {met}/{total}" if met is not None else ""

        details = " | ".join(filter(None, [z_str, heat_str]))
        if details:
            details = "\n" + details

        return (
            f"\U0001f7e2 NEW OPPORTUNITY \u2014 {base}\n"
            f"Signal: {signal}\n"
            f"Regime: {regime}{details}\n"
            f"{cond_str} | Confluence: {conf_label}"
        )

    def _fmt_overview(
        self,
        positions: List[dict],
        results_by_symbol: Dict[str, dict],
    ) -> str:
        """Format full portfolio overview."""
        lines = ["\U0001f4ca PORTFOLIO OVERVIEW\n"]

        if not positions:
            lines.append("No open positions on Hyperliquid.\n")
        else:
            total_pnl = sum(p["unrealized_pnl"] for p in positions)
            total_value = sum(p["size_usd"] for p in positions)
            pnl_sign = "+" if total_pnl >= 0 else ""
            lines.append(f"Open Positions ({len(positions)}) | Total: ${total_value:,.0f} | PnL: {pnl_sign}${total_pnl:,.2f}\n")

            for i, pos in enumerate(positions):
                sym = pos["symbol"]
                scan = results_by_symbol.get(sym, {})
                signal = scan.get("signal", "?")
                regime = scan.get("regime", "?")
                heat = scan.get("heat")
                pnl = pos["unrealized_pnl"]
                pnl_sign = "+" if pnl >= 0 else ""

                prefix = "\u2514" if i == len(positions) - 1 else "\u251c"
                heat_str = f" | Heat: {heat:.0f}" if heat is not None else ""

                lines.append(
                    f"{prefix} {pos['coin']} {pos['side']} {pos['size']:.4g} @ ${pos['entry_px']:,.2f} "
                    f"({pos['leverage']:.0f}x) \u2014 PnL: {pnl_sign}${pnl:,.2f}"
                )
                lines.append(f"  Signal: {signal} | Regime: {regime}{heat_str}")

        # Alerts for held positions
        alerts = []
        for pos in positions:
            scan = results_by_symbol.get(pos["symbol"], {})
            signal = scan.get("signal", "WAIT")
            heat = scan.get("heat")
            exh = scan.get("exhaustion_state")

            if signal in _ADVERSE_SIGNALS and pos["side"] == "LONG":
                alerts.append(f"\u26a0\ufe0f {pos['coin']} signal is {signal} \u2014 consider reducing LONG exposure")
            if signal in _OPPORTUNITY_SIGNALS and pos["side"] == "SHORT":
                alerts.append(f"\u26a0\ufe0f {pos['coin']} signal is bullish ({signal}) but you're SHORT")
            if heat is not None and heat > 65:
                alerts.append(f"\u26a0\ufe0f {pos['coin']} heat elevated ({heat:.0f}) \u2014 exhaustion risk")
            if exh and exh not in ("FRESH", "NONE"):
                alerts.append(f"\u26a0\ufe0f {pos['coin']} exhaustion: {exh}")

        if alerts:
            lines.append("\nAlerts:")
            lines.extend(alerts)

        # Top opportunities (not held)
        held = {p["symbol"] for p in positions}
        opportunities = [
            r for r in results_by_symbol.values()
            if r.get("signal") in _OPPORTUNITY_SIGNALS and r.get("symbol") not in held
        ]
        opportunities.sort(key=lambda r: r.get("conditions_met", 0), reverse=True)

        if opportunities:
            lines.append("\nTop Opportunities:")
            for opp in opportunities[:5]:
                base = opp["symbol"].split("/")[0]
                met = opp.get("conditions_met", "?")
                total = opp.get("conditions_total", "?")
                lines.append(f"\U0001f7e2 {base} \u2014 {opp['signal']} ({met}/{total} conditions)")

        return "\n".join(lines)

    # -- Telegram sending -----------------------------------------------------

    async def _send_notifications(self, chat_id: int, notifications: List[str]):
        """Send notifications, respecting rate limit."""
        if len(notifications) > _MAX_NOTIFICATIONS_PER_CYCLE:
            # Batch into a single message
            combined = "\n\n".join(notifications[:_MAX_NOTIFICATIONS_PER_CYCLE])
            remaining = len(notifications) - _MAX_NOTIFICATIONS_PER_CYCLE
            combined += f"\n\n... and {remaining} more alerts"
            await self._send_tg(chat_id, combined)
        elif len(notifications) <= 3:
            # Send individually for small counts
            for notif in notifications:
                await self._send_tg(chat_id, notif)
        else:
            # Batch medium counts into one message
            await self._send_tg(chat_id, "\n\n".join(notifications))

    async def _send_tg(self, chat_id: int, text: str):
        """Send a message via the Telegram bot."""
        try:
            from telegram_bot import get_telegram_bot
            bot = get_telegram_bot()
            if bot.app and bot._running:
                # Truncate to Telegram limit
                if len(text) > 4000:
                    text = text[:4000] + "\n\n... (truncated)"
                await bot.app.bot.send_message(chat_id=chat_id, text=text)
            else:
                logger.debug("TG bot not running, skipping notification to %s", chat_id)
        except Exception as e:
            logger.warning("Failed to send TG notification to %s: %s", chat_id, e)

    # -- On-demand helpers (used by TG commands) ------------------------------

    async def get_positions_summary(self, address: str, results_by_symbol: Dict[str, dict]) -> str:
        """Get formatted positions summary for /positions command."""
        from hyperliquid_data import fetch_clearinghouse_state, parse_open_positions

        clearinghouse = await fetch_clearinghouse_state(address)
        if clearinghouse is None:
            return "Could not fetch positions. Please check your wallet address."

        positions = parse_open_positions(clearinghouse)
        if not positions:
            return "No open positions on Hyperliquid."

        return self._fmt_overview(positions, results_by_symbol)

    async def get_overview(self, address: str, results_by_symbol: Dict[str, dict]) -> str:
        """Get full overview for /overview command."""
        return await self.get_positions_summary(address, results_by_symbol)
