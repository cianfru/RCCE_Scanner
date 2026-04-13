"""
telegram_bot.py
~~~~~~~~~~~~~~~
Telegram bot wrapper for the RCCE Scanner trading assistant.
Uses python-telegram-bot (async-native).
"""

from __future__ import annotations

import os
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_IDS = [
    cid.strip()
    for cid in os.environ.get("TELEGRAM_ALLOWED_CHATS", "").split(",")
    if cid.strip()
]


class TelegramBot:
    """Telegram bot that wraps the RCCE assistant."""

    def __init__(self):
        self.app = None
        self._running = False

    async def start(self):
        if not TELEGRAM_BOT_TOKEN:
            logger.info("TELEGRAM_BOT_TOKEN not set — bot disabled")
            return

        try:
            from telegram import Update
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.warning("python-telegram-bot not installed — bot disabled")
            return

        self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("help", self._cmd_start))
        self.app.add_handler(CommandHandler("briefing", self._cmd_briefing))
        self.app.add_handler(CommandHandler("signals", self._cmd_signals))
        self.app.add_handler(CommandHandler("explain", self._cmd_explain))
        self.app.add_handler(CommandHandler("watch", self._cmd_watch))
        self.app.add_handler(CommandHandler("unwatch", self._cmd_unwatch))
        self.app.add_handler(CommandHandler("positions", self._cmd_positions))
        self.app.add_handler(CommandHandler("overview", self._cmd_overview))
        self.app.add_handler(CommandHandler("follow", self._cmd_follow))
        self.app.add_handler(CommandHandler("unfollow", self._cmd_unfollow))
        self.app.add_handler(CommandHandler("following", self._cmd_following))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        self._running = True

        # Register commands in Telegram's UI menu
        try:
            from telegram import BotCommand
            await self.app.bot.set_my_commands([
                BotCommand("briefing", "Daily market briefing"),
                BotCommand("signals", "Active signals summary"),
                BotCommand("explain", "Explain a signal (e.g. /explain HYPE)"),
                BotCommand("watch", "Monitor HL positions (e.g. /watch 0x...)"),
                BotCommand("unwatch", "Stop position monitoring"),
                BotCommand("positions", "Show open positions with scanner context"),
                BotCommand("overview", "Full portfolio overview + opportunities"),
                BotCommand("follow", "Follow a whale wallet (e.g. /follow 0x...)"),
                BotCommand("unfollow", "Stop following a wallet"),
                BotCommand("following", "List followed whale wallets"),
                BotCommand("help", "Show help message"),
            ])
        except Exception as e:
            logger.warning("Failed to register bot commands menu: %s", e)

        logger.info("Telegram bot started")

    async def stop(self):
        if self.app and self._running:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            self._running = False
            logger.info("Telegram bot stopped")

    def _check_auth(self, chat_id: int) -> bool:
        if not ALLOWED_CHAT_IDS:
            return True
        return str(chat_id) in ALLOWED_CHAT_IDS

    async def _send(self, update, text: str):
        """Send a reply, truncating if > Telegram limit."""
        if len(text) > 4000:
            text = text[:4000] + "\n\n... (truncated)"
        await update.message.reply_text(text)

    async def _cmd_start(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        await self._send(
            update,
            "RCCE Scanner Assistant\n\n"
            "Commands:\n"
            "/briefing — Daily market briefing\n"
            "/signals — Active signals summary\n"
            "/explain SYMBOL — Explain a signal (e.g. /explain HYPE)\n"
            "/watch 0xADDRESS — Monitor your HL positions\n"
            "/unwatch — Stop position monitoring\n"
            "/positions — Show open positions with scanner context\n"
            "/overview — Full portfolio overview + opportunities\n"
            "/help — Show this message\n\n"
            "Or just type any question about the market.",
        )

    async def _cmd_briefing(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        from assistant import get_assistant

        assistant = get_assistant()
        briefing = await assistant.daily_briefing()
        await self._send(update, briefing)

    async def _cmd_signals(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        from assistant import get_assistant

        assistant = get_assistant()
        reply, _ = await assistant.chat(
            session_id=f"tg-{update.effective_chat.id}",
            user_message="List all active signals with their reasons, grouped by signal type.",
        )
        await self._send(update, reply)

    async def _cmd_explain(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        args = context.args
        if not args:
            await self._send(update, "Usage: /explain SYMBOL (e.g. /explain HYPE)")
            return

        symbol = args[0].upper()
        if "/" not in symbol:
            symbol = f"{symbol}/USDT"

        from assistant import get_assistant

        assistant = get_assistant()
        explanation = await assistant.explain_signal(symbol)
        await self._send(update, explanation)

    async def _cmd_watch(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        args = context.args
        if not args:
            await self._send(update, "Usage: /watch 0xYourWalletAddress")
            return

        from position_monitor import PositionMonitor
        monitor = PositionMonitor.get()
        result = monitor.register(update.effective_chat.id, args[0])
        await self._send(update, result)

    async def _cmd_unwatch(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        from position_monitor import PositionMonitor
        monitor = PositionMonitor.get()
        result = monitor.unregister(update.effective_chat.id)
        await self._send(update, result)

    async def _cmd_positions(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        from position_monitor import PositionMonitor
        from scanner import cache

        monitor = PositionMonitor.get()
        watcher = monitor.get_watcher(update.effective_chat.id)
        if not watcher:
            await self._send(update, "No wallet registered. Use /watch 0xADDRESS first.")
            return

        # Build symbol lookup from cached scan results
        results_by_symbol = {}
        for tf in ("4h", "1d"):
            for r in cache.results.get(tf, []):
                sym = r.get("symbol", "")
                if sym not in results_by_symbol:
                    results_by_symbol[sym] = r

        summary = await monitor.get_positions_summary(watcher.address, results_by_symbol)
        await self._send(update, summary)

    async def _cmd_overview(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        from position_monitor import PositionMonitor
        from scanner import cache

        monitor = PositionMonitor.get()
        watcher = monitor.get_watcher(update.effective_chat.id)
        if not watcher:
            await self._send(update, "No wallet registered. Use /watch 0xADDRESS first.")
            return

        results_by_symbol = {}
        for tf in ("4h", "1d"):
            for r in cache.results.get(tf, []):
                sym = r.get("symbol", "")
                if sym not in results_by_symbol:
                    results_by_symbol[sym] = r

        overview = await monitor.get_overview(watcher.address, results_by_symbol)
        await self._send(update, overview)

    async def _cmd_follow(self, update, context):
        """Follow a whale wallet for trade alerts."""
        if not self._check_auth(update.effective_chat.id):
            return
        if not context.args:
            await self._send(update, "Usage: /follow 0xADDRESS\n\nYou'll get alerts when this wallet opens/closes positions.")
            return

        address = context.args[0].lower()
        if not address.startswith("0x") or len(address) < 10:
            await self._send(update, "Invalid address. Must start with 0x.")
            return

        import whale_follows as wf
        # Use chat_id as user key for TG (no connected wallet in TG context)
        user_key = f"tg:{update.effective_chat.id}"
        added = wf.add_follow(user_key, address)
        wf.link_tg(user_key, update.effective_chat.id)

        if added:
            # Try to get wallet info
            try:
                from hl_intelligence import get_wallet_profile
                profile = get_wallet_profile(address)
                cohorts = profile.get("cohorts", [])
                av = profile.get("account_value", 0)
                roi = profile.get("roi", 0)
                cohort_str = ", ".join(c.replace("_", " ").title() for c in cohorts) if cohorts else "Tracked"
                pos_count = len(profile.get("positions", []))
                await self._send(
                    update,
                    f"Now following {address[:8]}...{address[-4:]}\n"
                    f"Cohort: {cohort_str}\n"
                    f"AV: ${av / 1e6:.1f}M | ROI: {roi:.0f}% | {pos_count} positions\n\n"
                    f"You'll be notified when this wallet trades."
                )
            except Exception:
                await self._send(update, f"Now following {address[:8]}...{address[-4:]}")
        else:
            await self._send(update, f"Already following {address[:8]}...{address[-4:]}")

    async def _cmd_unfollow(self, update, context):
        """Stop following a whale wallet."""
        if not self._check_auth(update.effective_chat.id):
            return
        if not context.args:
            await self._send(update, "Usage: /unfollow 0xADDRESS")
            return

        address = context.args[0].lower()
        import whale_follows as wf
        user_key = f"tg:{update.effective_chat.id}"
        removed = wf.remove_follow(user_key, address)

        if removed:
            await self._send(update, f"Unfollowed {address[:8]}...{address[-4:]}")
        else:
            await self._send(update, f"Not following {address[:8]}...{address[-4:]}")

    async def _cmd_following(self, update, context):
        """List followed whale wallets."""
        if not self._check_auth(update.effective_chat.id):
            return

        import whale_follows as wf
        user_key = f"tg:{update.effective_chat.id}"
        follows = wf.get_follows(user_key)

        if not follows:
            await self._send(update, "Not following any wallets.\nUse /follow 0xADDRESS to start.")
            return

        lines = [f"Following {len(follows)} wallet(s):\n"]
        for addr in follows:
            try:
                from hl_intelligence import get_wallet_profile
                profile = get_wallet_profile(addr)
                cohorts = profile.get("cohorts", [])
                cohort_str = ", ".join(c.replace("_", " ").title() for c in cohorts) if cohorts else "Tracked"
                av = profile.get("account_value", 0)
                lines.append(f"• {addr[:8]}...{addr[-4:]} ({cohort_str}, ${av / 1e6:.1f}M)")
            except Exception:
                lines.append(f"• {addr[:8]}...{addr[-4:]}")
        await self._send(update, "\n".join(lines))

    async def _handle_message(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        from assistant import get_assistant
        from position_monitor import PositionMonitor

        # Get wallet address if registered via /watch
        monitor = PositionMonitor.get()
        watcher = monitor.get_watcher(update.effective_chat.id)
        wallet = watcher.address if watcher else None

        assistant = get_assistant()
        reply, _ = await assistant.chat(
            session_id=f"tg-{update.effective_chat.id}",
            user_message=update.message.text,
            wallet_address=wallet,
        )
        await self._send(update, reply)

    # -- Proactive trade alerts --------------------------------------------

    _ALERT_SIGNALS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE"}
    _ALERT_TRANSITIONS = {"ENTRY", "UPGRADE"}
    _MIN_CONDITIONS = 10
    _MIN_WIN_RATE = 60.0
    _DEDUP_WINDOW = 4 * 3600  # 4 hours
    _MAX_ALERTS_PER_CYCLE = 5

    _recent_alerts: Dict[str, float] = {}  # "SYM:SIGNAL" -> last_alert_ts

    async def push_trade_alerts(self, transitions: List[dict]) -> int:
        """Push high-conviction trade alerts to all registered Telegram chats.

        Called after each scan cycle with the list of signal transitions.
        Returns number of alerts sent.
        """
        if not self.app or not self._running:
            return 0

        # Filter to high-conviction entries
        candidates = []
        now = time.time()
        for t in transitions:
            sig = t.get("signal", "")
            tt = t.get("transition_type", "")
            cond_met = t.get("conditions_met", 0) or 0

            if sig not in self._ALERT_SIGNALS:
                continue
            if tt not in self._ALERT_TRANSITIONS:
                continue
            if cond_met < self._MIN_CONDITIONS:
                continue

            # Dedup check
            dedup_key = f"{t.get('symbol')}:{sig}"
            last = self._recent_alerts.get(dedup_key, 0)
            if now - last < self._DEDUP_WINDOW:
                continue

            candidates.append(t)

        if not candidates:
            return 0

        # Enrich with win rate data
        try:
            from signal_analytics import SignalAnalytics
            from signal_log import SignalLog
            sig_log = SignalLog.get()
            analytics = SignalAnalytics(sig_log)
            scorecard = await sig_log.get_scorecard(timeframe="4h")
            regime_sc = await analytics.regime_stratified_scorecard(timeframe="4h")

            wr_by_signal = {c["signal"]: c for c in scorecard}
            wr_by_sig_regime: Dict[tuple, dict] = {}
            for sig, entries in regime_sc.items():
                for e in entries:
                    wr_by_sig_regime[(sig, e["regime"])] = e
        except Exception:
            wr_by_signal = {}
            wr_by_sig_regime = {}

        # Filter by win rate
        qualified = []
        for t in candidates:
            sig = t.get("signal", "")
            regime = t.get("regime", "")
            regime_entry = wr_by_sig_regime.get((sig, regime))
            signal_entry = wr_by_signal.get(sig, {})

            wr = None
            wr_n = 0
            wr_label = ""
            if regime_entry and regime_entry.get("win_rate") is not None:
                wr = regime_entry["win_rate"]
                wr_n = regime_entry.get("count", 0)
                wr_label = f"in {regime}"
            elif signal_entry.get("win_rate") is not None:
                wr = signal_entry["win_rate"]
                wr_n = signal_entry.get("has_outcomes", 0)
                wr_label = "overall"

            if wr is not None and wr < self._MIN_WIN_RATE:
                continue

            t["_wr"] = wr
            t["_wr_n"] = wr_n
            t["_wr_label"] = wr_label
            qualified.append(t)

        # Limit alerts per cycle
        alerts = qualified[:self._MAX_ALERTS_PER_CYCLE]

        # Format and send
        sent = 0
        for t in alerts:
            symbol = t.get("symbol", "?")
            sig = t.get("signal", "?")
            regime = t.get("regime", "?")
            price = t.get("price", 0)
            cond_met = t.get("conditions_met", 0) or 0
            cond_total = t.get("conditions_total", 14) or 14
            heat = t.get("heat", 0) or 0
            z = t.get("zscore", 0) or 0
            tt = t.get("transition_type", "")
            wr = t.get("_wr")
            wr_n = t.get("_wr_n", 0)
            wr_label = t.get("_wr_label", "")

            conviction = "HIGH" if cond_met >= 12 else "MED" if cond_met >= 10 else "LOW"
            coin = symbol.split("/")[0] if "/" in symbol else symbol

            msg_lines = [
                f"Trade Identified: {coin}",
                "",
                f"Signal: {sig} ({regime})",
                f"Conditions: {cond_met}/{cond_total} (conviction: {conviction})",
            ]
            if wr is not None:
                msg_lines.append(f"Win Rate: {wr}% (n={wr_n}) {wr_label}")
            msg_lines.extend([
                f"Price: ${price:.6g} | Heat: {heat} | Z: {z:.2f}",
                "",
                f"Transition: {tt}",
            ])

            # Add met conditions summary
            ctx_str = t.get("context")
            if ctx_str:
                try:
                    import json
                    ctx = json.loads(ctx_str)
                    details = ctx.get("synthesis", {}).get("conditions_detail", [])
                    met_names = [d["label"] for d in details if d.get("met")]
                    if met_names:
                        msg_lines.append(f"Triggers: {', '.join(met_names[:6])}")
                except Exception:
                    pass

            msg = "\n".join(msg_lines)

            # Send to all allowed chats
            for chat_id in ALLOWED_CHAT_IDS:
                try:
                    await self.app.bot.send_message(
                        chat_id=int(chat_id), text=msg,
                    )
                    sent += 1
                except Exception as exc:
                    logger.debug("TG alert to %s failed: %s", chat_id, exc)

            # Mark as sent for dedup
            self._recent_alerts[f"{symbol}:{sig}"] = now

        # Cleanup old dedup entries
        cutoff = now - self._DEDUP_WINDOW
        self._recent_alerts = {k: v for k, v in self._recent_alerts.items() if v > cutoff}

        if sent > 0:
            logger.info("Telegram: pushed %d trade alerts", sent)
        return sent

    # -- Anomaly alerts --------------------------------------------------------

    _ANOMALY_DEDUP_WINDOW = 30 * 60  # 30 min
    _MAX_ANOMALY_ALERTS = 3
    _recent_anomaly_alerts: Dict[str, float] = {}

    _ANOMALY_TYPE_LABELS = {
        "EXTREME_FUNDING": "EXTREME FUNDING",
        "OI_SURGE": "OI SURGE",
        "VOLUME_SPIKE": "VOLUME SPIKE",
        "LSR_EXTREME": "LSR EXTREME",
        "CVD_EXTREME": "CVD EXTREME",
        "VPIN_TOXIC": "TOXIC FLOW (VPIN)",
    }

    async def push_anomaly_alerts(self, anomalies) -> int:
        """Push critical anomaly alerts to Telegram.

        Receives a list of Anomaly dataclass instances (critical severity only).
        """
        if not self.app or not self._running:
            return 0

        now = time.time()
        candidates = []
        for a in anomalies:
            dedup_key = a.dedup_key
            last = self._recent_anomaly_alerts.get(dedup_key, 0)
            if now - last < self._ANOMALY_DEDUP_WINDOW:
                continue
            candidates.append(a)

        if not candidates:
            return 0

        alerts = candidates[:self._MAX_ANOMALY_ALERTS]
        sent = 0

        for a in alerts:
            coin = a.symbol.split("/")[0] if "/" in a.symbol else a.symbol
            type_label = self._ANOMALY_TYPE_LABELS.get(a.anomaly_type, a.anomaly_type)

            msg_lines = [
                f"Anomaly: {coin}",
                "",
                f"Type: {type_label} ({a.direction})",
                f"Severity: {a.severity.upper()}",
                f"Detail: {a.context}",
            ]
            if a.z_score:
                msg_lines.append(f"Z-score: {a.z_score:.1f}")
            if a.historical_sigma:
                msg_lines.append(f"History: {abs(a.historical_sigma):.1f} sigma vs own baseline")

            msg = "\n".join(msg_lines)

            for chat_id in ALLOWED_CHAT_IDS:
                try:
                    await self.app.bot.send_message(chat_id=int(chat_id), text=msg)
                    sent += 1
                except Exception as exc:
                    logger.debug("TG anomaly alert to %s failed: %s", chat_id, exc)

            self._recent_anomaly_alerts[dedup_key] = now

        # Cleanup old dedup
        cutoff = now - self._ANOMALY_DEDUP_WINDOW
        self._recent_anomaly_alerts = {
            k: v for k, v in self._recent_anomaly_alerts.items() if v > cutoff
        }

        if sent > 0:
            logger.info("Telegram: pushed %d anomaly alerts", sent)
        return sent


# Module-level singleton
_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    global _bot
    if _bot is None:
        _bot = TelegramBot()
    return _bot
