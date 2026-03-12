"""
manual_trader.py
~~~~~~~~~~~~~~~~
Trade journal for manual Hyperliquid trades.
Records trades reported by the frontend (wallet-signed), tracks P&L, stats.
No private key or HyperliquidEngine dependency — all execution is browser-side.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).parent / "data"
_TRADES_FILE = _PERSIST_DIR / "manual_trades.json"


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------

@dataclass
class ManualTrade:
    id: str
    symbol: str                          # "BTC/USDT"
    coin: str                            # "BTC"
    side: str = "LONG"                   # LONG or SHORT
    size_usd: float = 0.0
    volume: float = 0.0
    leverage: int = 3
    entry_price: float = 0.0
    exit_price: float = 0.0
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0
    status: str = "OPEN"                 # OPEN or CLOSED
    signal_at_trade: str = ""
    regime_at_trade: str = ""
    opened_at: float = 0.0
    closed_at: float = 0.0
    order_id: str = ""
    close_order_id: str = ""
    address: str = ""                    # wallet address

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ManualTrade:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# TradeJournal (formerly ManualTrader)
# ---------------------------------------------------------------------------

class TradeJournal:
    """Trade journal — logs trades reported by the frontend wallet."""

    def __init__(self):
        self._trades: List[ManualTrade] = []
        self._load_trades()

    # ------------------------------------------------------------------
    # Log trade (called by backend when frontend reports a fill)
    # ------------------------------------------------------------------

    def log_trade(
        self,
        address: str,
        symbol: str,
        coin: str,
        side: str,
        size_usd: float,
        volume: float,
        leverage: int,
        entry_price: float,
        order_id: str = "",
        signal_at_trade: str = "",
        regime_at_trade: str = "",
    ) -> ManualTrade:
        """Record a new trade reported by the frontend."""
        trade = ManualTrade(
            id=uuid.uuid4().hex[:8],
            symbol=symbol,
            coin=coin,
            side=side.upper(),
            size_usd=size_usd,
            volume=volume,
            leverage=leverage,
            entry_price=entry_price,
            status="OPEN",
            signal_at_trade=signal_at_trade,
            regime_at_trade=regime_at_trade,
            opened_at=time.time(),
            order_id=str(order_id),
            address=address.lower(),
        )
        self._trades.append(trade)
        self._save_trades()

        logger.info(
            "TRADE LOG: %s %s sz=$%.2f vol=%.6f @ $%.4f %dx (order %s) [%s]",
            side.upper(), symbol, size_usd, volume, entry_price, leverage, order_id, address[:10],
        )
        return trade

    def log_close(
        self,
        symbol: str,
        exit_price: float,
        close_order_id: str = "",
    ) -> Optional[ManualTrade]:
        """Record a position closure reported by the frontend."""
        open_trade = None
        for t in reversed(self._trades):
            if t.symbol == symbol and t.status == "OPEN":
                open_trade = t
                break

        if not open_trade:
            logger.warning("log_close: no open trade found for %s", symbol)
            return None

        open_trade.status = "CLOSED"
        open_trade.closed_at = time.time()
        open_trade.close_order_id = str(close_order_id)

        if exit_price > 0:
            open_trade.exit_price = exit_price
            if open_trade.side == "LONG":
                open_trade.pnl_pct = ((exit_price - open_trade.entry_price) / open_trade.entry_price) * 100
            else:
                open_trade.pnl_pct = ((open_trade.entry_price - exit_price) / open_trade.entry_price) * 100
            open_trade.pnl_usd = open_trade.size_usd * (open_trade.pnl_pct / 100)

        self._save_trades()
        logger.info(
            "TRADE CLOSE: %s %s pnl=%.2f%% ($%.2f)",
            open_trade.side, symbol, open_trade.pnl_pct, open_trade.pnl_usd,
        )
        return open_trade

    # ------------------------------------------------------------------
    # Trade history & stats
    # ------------------------------------------------------------------

    def get_trade_history(self) -> list:
        return [t.to_dict() for t in reversed(self._trades)]

    def get_stats(self) -> dict:
        closed = [t for t in self._trades if t.status == "CLOSED"]
        if not closed:
            return {
                "total_trades": 0, "open_trades": sum(1 for t in self._trades if t.status == "OPEN"),
                "wins": 0, "losses": 0, "win_rate": 0,
                "total_pnl_usd": 0, "total_pnl_pct": 0,
                "avg_pnl_pct": 0, "best_pnl_pct": 0, "worst_pnl_pct": 0,
            }

        wins = [t for t in closed if t.pnl_pct > 0]
        losses = [t for t in closed if t.pnl_pct <= 0]
        total_pnl_usd = sum(t.pnl_usd for t in closed)
        pnls = [t.pnl_pct for t in closed]

        return {
            "total_trades": len(closed),
            "open_trades": sum(1 for t in self._trades if t.status == "OPEN"),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "total_pnl_usd": round(total_pnl_usd, 2),
            "total_pnl_pct": round(sum(pnls), 2),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 2),
            "best_pnl_pct": round(max(pnls), 2),
            "worst_pnl_pct": round(min(pnls), 2),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_trades(self) -> None:
        try:
            _TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
            _TRADES_FILE.write_text(json.dumps(
                [t.to_dict() for t in self._trades], indent=2,
            ))
        except Exception as e:
            logger.error("Failed to save manual trades: %s", e)

    def _load_trades(self) -> None:
        if not _TRADES_FILE.exists():
            return
        try:
            data = json.loads(_TRADES_FILE.read_text())
            self._trades = [ManualTrade.from_dict(d) for d in data]
            logger.info("Loaded %d manual trades from disk", len(self._trades))
        except Exception as e:
            logger.error("Failed to load manual trades: %s", e)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_journal: Optional[TradeJournal] = None


def get_trade_journal() -> TradeJournal:
    global _journal
    if _journal is None:
        _journal = TradeJournal()
    return _journal
