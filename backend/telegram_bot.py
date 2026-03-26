"""
telegram_bot.py
~~~~~~~~~~~~~~~
Telegram bot wrapper for the RCCE Scanner trading assistant.
Uses python-telegram-bot (async-native).
"""

from __future__ import annotations

import os
import logging
from typing import Optional

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


# Module-level singleton
_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    global _bot
    if _bot is None:
        _bot = TelegramBot()
    return _bot
