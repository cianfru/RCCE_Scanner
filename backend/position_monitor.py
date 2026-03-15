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

        # -- 2. Check for new opportunities (not already held) --
        if watcher.notify_opportunities:
            for sym, scan in results_by_symbol.items():
                if sym in held_symbols:
                    continue
                signal = scan.get("signal", "WAIT")
                key = f"{watcher.chat_id}:{sym}"
                prev = self._last_notified_signal.get(key)

                if signal in _OPPORTUNITY_SIGNALS and prev != signal:
                    notifications.append(self._fmt_opportunity(scan))
                    self._last_notified_signal[key] = signal

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
