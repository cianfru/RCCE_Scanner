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
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        self._running = True
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

    async def _handle_message(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        from assistant import get_assistant

        assistant = get_assistant()
        reply, _ = await assistant.chat(
            session_id=f"tg-{update.effective_chat.id}",
            user_message=update.message.text,
        )
        await self._send(update, reply)


# Module-level singleton
_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    global _bot
    if _bot is None:
        _bot = TelegramBot()
    return _bot
