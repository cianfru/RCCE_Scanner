"""
telegram_bot.py
~~~~~~~~~~~~~~~
Telegram bot wrapper for the RCCE Scanner trading assistant.
Uses python-telegram-bot (async-native).
"""

from __future__ import annotations

import os
import logging
from typing import Dict, List, Optional

import tg_alerts as ta
from wallet_names import codename

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
                CallbackQueryHandler,
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
        self.app.add_handler(CommandHandler("alerts", self._cmd_alerts))
        self.app.add_handler(CommandHandler("brief", self._cmd_brief))
        self.app.add_handler(CommandHandler("quiet", self._cmd_quiet))
        self.app.add_handler(CommandHandler("unlink", self._cmd_unlink))
        self.app.add_handler(CallbackQueryHandler(self._on_alerts_button, pattern=r"^al:"))
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
                BotCommand("brief", "The daily brief, now"),
                BotCommand("alerts", "What sends a message, quiet hours, pause"),
                BotCommand("positions", "Open positions against the scanner"),
                BotCommand("watch", "Register a wallet (/watch 0x...)"),
                BotCommand("unwatch", "Stop reading the wallet"),
                BotCommand("follow", "Follow a trader (/follow 0x...)"),
                BotCommand("unfollow", "Stop following a trader"),
                BotCommand("following", "Followed traders"),
                BotCommand("explain", "A coin's signal (/explain HYPE)"),
                BotCommand("signals", "Active signals"),
                BotCommand("briefing", "Written market briefing"),
                BotCommand("overview", "Positions and opportunities"),
                BotCommand("help", "Commands"),
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

    async def _send_html(self, update, text: str, markup=None):
        await update.message.reply_text(text[:4000], parse_mode="HTML", reply_markup=markup,
                                        disable_web_page_preview=True)

    async def _cmd_start(self, update, context):
        # /start <code> from the app links this chat to a Reflex account (accounts on).
        if context.args and await self._link(update, context.args[0]):
            return
        if not self._check_auth(update.effective_chat.id):
            return
        await self._send_html(
            update,
            "<b>Reflex</b>\n"
            f"A brief every morning at {ta.BRIEF_TIME}; instant alerts only for your positions, "
            "watched coins, followed traders and anomalies on them.\n\n"
            "/brief the brief now\n"
            "/alerts what sends a message\n"
            "/watch 0x... your wallet\n"
            "/follow 0x... a trader\n"
            "Or ask a question.",
        )

    # -- Account link (accounts.py) -------------------------------------------

    async def _link(self, update, code: str) -> bool:
        """Bind the chat to the account the code was made for. False when accounts are off."""
        import accounts
        if not accounts.enabled():
            return False
        user = accounts.tg_claim(code, update.effective_chat.id)
        if user is None:
            await self._send(update, "That code is not valid any more. Make a new one in the app.")
        else:
            await self._send_html(update, f"Linked to {ta.esc(codename(user))}. "
                                           "Alerts for your followed traders and watched coins arrive here.\n"
                                           "/unlink to stop.")
        return True

    async def _cmd_unlink(self, update, context):
        import accounts
        if not accounts.enabled():
            return
        done = accounts.tg_unlink(chat_id=update.effective_chat.id)
        await self._send(update, "Unlinked." if done else "This chat is not linked to an account.")

    # -- Alerts and brief ---------------------------------------------------

    @staticmethod
    def _markup(rows):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in row]
                                     for row in rows])

    async def _cmd_alerts(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        text, rows = ta.alerts_view("main")
        await self._send_html(update, text, self._markup(rows))

    async def _on_alerts_button(self, update, context):
        query = update.callback_query
        if not self._check_auth(update.effective_chat.id):
            await query.answer()
            return
        page = ta.apply_callback(query.data or "")
        await query.answer()
        if page == "brief":
            import tg_brief
            await tg_brief.send_brief(chats=[update.effective_chat.id])
            page = "main"
        text, rows = ta.alerts_view(page)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=self._markup(rows))
        except Exception as exc:                      # "message is not modified" and the like
            logger.debug("alerts: edit failed: %s", exc)

    async def _cmd_brief(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        import tg_brief
        if not await tg_brief.send_brief(chats=[update.effective_chat.id]):
            await self._send(update, "The brief could not be built right now.")

    async def _cmd_quiet(self, update, context):
        """/quiet 23:00 07:30, or /quiet off."""
        if not self._check_auth(update.effective_chat.id):
            return
        args = context.args or []
        try:
            if args and args[0].lower() == "off":
                ta.set_quiet(None)
            elif len(args) == 2:
                ta.set_quiet([args[0], args[1]])
            else:
                raise ValueError
        except ValueError:
            await self._send(update, "Usage: /quiet 23:00 07:30, or /quiet off")
            return
        q = ta.settings().get("quiet")
        await self._send(update, f"Quiet hours {q[0]}-{q[1]}" if q else "Quiet hours off")

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
        await self._send(update, ta.strip_emoji(summary))

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
        await self._send(update, ta.strip_emoji(overview))

    async def _cmd_follow(self, update, context):
        """Follow a trader: the same list as the app's followed traders, so one set of alerts."""
        if not self._check_auth(update.effective_chat.id):
            return
        args = context.args or []
        address = args[0].strip().lower() if args else ""
        if not (address.startswith("0x") and len(address) == 42):
            await self._send(update, "Usage: /follow 0xADDRESS")
            return
        import followed_traders as ft
        added = ft.add(address, " ".join(args[1:])[:80])
        name = codename(address)
        await self._send(update, f"Following {name}" if added else f"Already following {name}")

    async def _cmd_unfollow(self, update, context):
        if not self._check_auth(update.effective_chat.id):
            return
        if not context.args:
            await self._send(update, "Usage: /unfollow 0xADDRESS")
            return
        address = context.args[0].strip().lower()
        import followed_traders as ft
        import whale_follows as wf
        removed = ft.remove(address)
        removed = wf.remove_follow(f"tg:{update.effective_chat.id}", address) or removed
        await self._send(update, f"{'Unfollowed' if removed else 'Not following'} {codename(address)}")

    async def _cmd_following(self, update, context):
        """Followed traders (the app's list, plus any older /follow entries of this chat)."""
        if not self._check_auth(update.effective_chat.id):
            return
        import followed_traders as ft
        import whale_follows as wf
        items = ft.items()
        addrs = list(items) + [a for a in wf.get_follows(f"tg:{update.effective_chat.id}") if a not in items]
        if not addrs:
            await self._send(update, "Not following anyone. /follow 0xADDRESS")
            return
        lines = ["<b>Following</b>"]
        for a in addrs:
            note = (items.get(a) or {}).get("note")
            lines.append(ta.esc(codename(a) + (f" · {note}" if note else "")))
        await self._send_html(update, "\n".join(lines))

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

    # -- 4H signal alerts (off by default: the brief covers the market) -------

    _ALERT_SIGNALS = {"STRONG_LONG", "LIGHT_LONG", "ACCUMULATE"}
    _ALERT_TRANSITIONS = {"ENTRY", "UPGRADE"}
    _MIN_CONDITIONS = 10
    _MIN_WIN_RATE = 60.0
    _MAX_ALERTS_PER_CYCLE = 5

    async def push_trade_alerts(self, transitions: List[dict]) -> int:
        """High-conviction 4H entries, through the alert gate (category "signals", off by
        default; once per coin and signal a day). Returns the number of alerts sent."""
        if not self.app or not self._running or not ta.enabled("signals"):
            return 0
        candidates = [t for t in transitions
                      if t.get("signal", "") in self._ALERT_SIGNALS
                      and t.get("transition_type", "") in self._ALERT_TRANSITIONS
                      and (t.get("conditions_met", 0) or 0) >= self._MIN_CONDITIONS]
        if not candidates:
            return 0

        # Win rate by signal (and regime, when it has one)
        try:
            from signal_analytics import shared as shared_analytics
            from signal_log import SignalLog
            sig_log = SignalLog.get()
            analytics = shared_analytics(sig_log)
            scorecard = await sig_log.get_scorecard(timeframe="4h")
            regime_sc = await analytics.regime_stratified_scorecard(timeframe="4h")
            wr_by_signal = {c["signal"]: c for c in scorecard}
            wr_by_sig_regime: Dict[tuple, dict] = {}
            for sig, entries in regime_sc.items():
                for e in entries:
                    wr_by_sig_regime[(sig, e["regime"])] = e
        except Exception:
            wr_by_signal, wr_by_sig_regime = {}, {}

        sent = 0
        for t in candidates[:self._MAX_ALERTS_PER_CYCLE]:
            sig, regime = t.get("signal", ""), t.get("regime", "")
            entry = wr_by_sig_regime.get((sig, regime)) or {}
            wr = entry.get("win_rate")
            if wr is None:
                wr = (wr_by_signal.get(sig) or {}).get("win_rate")
            if wr is not None and wr < self._MIN_WIN_RATE:
                continue
            symbol = t.get("symbol", "?")
            coin = symbol.split("/")[0]
            lines = [f"{ta.coin_b(coin)} · 4H {ta.esc(ta.signal_word(sig))}",
                     f"{ta.esc(ta.REGIME_WORD.get(regime, regime))} · checks {t.get('conditions_met', 0)}/"
                     f"{t.get('conditions_total', 14)} · stretch {(t.get('zscore') or 0):.1f} · heat {t.get('heat') or 0}"]
            if wr is not None:
                lines.append(f"Past win rate {wr:.0f}%")
            if await ta.submit("signals", f"{coin}:{sig}", "\n".join(lines)) == "sent":
                sent += 1
        if sent:
            logger.info("Telegram: pushed %d trade alerts", sent)
        return sent

    # -- Anomaly alerts --------------------------------------------------------

    _ANOMALY_WORD = {
        "EXTREME_FUNDING": "extreme funding",
        "OI_SURGE": "open interest surge",
        "VOLUME_SPIKE": "volume spike",
        "LSR_EXTREME": "long/short ratio extreme",
        "CVD_EXTREME": "CVD extreme",
        "VPIN_TOXIC": "toxic flow (VPIN)",
    }

    async def push_anomaly_alerts(self, anomalies) -> int:
        """Critical anomalies through the gate: category "anomalies" when the coin is watched
        or held, "anomalies_all" (off by default) otherwise; once per anomaly a day."""
        if not self.app or not self._running:
            return 0
        mine = _my_coins()
        sent = 0
        for a in anomalies:
            coin = a.symbol.split("/")[0]
            cat = "anomalies" if coin in mine else "anomalies_all"
            if not ta.enabled(cat):
                continue
            word = self._ANOMALY_WORD.get(a.anomaly_type, a.anomaly_type.replace("_", " ").lower())
            side = str(a.direction or "").lower()
            text = f"{ta.coin_b(coin)} · {ta.esc(word)}" + (f", {ta.esc(side)} side" if side else "")
            if a.context:
                text += "\n" + ta.esc(a.context)
            if await ta.submit(cat, a.dedup_key, text) == "sent":
                sent += 1
        if sent:
            logger.info("Telegram: pushed %d anomaly alerts", sent)
        return sent


def _my_coins() -> set:
    """Watched coins and coins in registered wallets' open positions."""
    out = set()
    try:
        import setup_map
        out |= set(setup_map.watched())
    except Exception:
        pass
    try:
        from position_monitor import PositionMonitor
        out |= PositionMonitor.get().held_coins()
    except Exception:
        pass
    return out


# Module-level singleton
_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    global _bot
    if _bot is None:
        _bot = TelegramBot()
    return _bot
