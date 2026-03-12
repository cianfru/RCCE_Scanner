"""
manual_trader.py
~~~~~~~~~~~~~~~~
Lightweight singleton for manual Hyperliquid trading.
Wraps HyperliquidEngine with size conversion, trade logging, and stats.
Completely independent from the automated Executor pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from trading_engine import HyperliquidEngine, EngineError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_PERSIST_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", ""))
if not _PERSIST_DIR.is_dir():
    _PERSIST_DIR = Path(__file__).parent / "data"
_TRADES_FILE = _PERSIST_DIR / "manual_trades.json"


# ---------------------------------------------------------------------------
# Volume formatting (same logic as executor.py)
# ---------------------------------------------------------------------------

def _format_volume(volume: float, price: float) -> float:
    if price > 10000:
        return round(volume, 8)
    elif price > 100:
        return round(volume, 6)
    elif price > 1:
        return round(volume, 4)
    elif price > 0.01:
        return round(volume, 2)
    else:
        return round(volume, 0)


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ManualTrade:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# ManualTrader
# ---------------------------------------------------------------------------

class ManualTrader:
    """Manual trading wrapper around HyperliquidEngine."""

    def __init__(self):
        self._engine: Optional[HyperliquidEngine] = None
        self._trades: List[ManualTrade] = []
        self._load_trades()

    # ------------------------------------------------------------------
    # Lazy engine init
    # ------------------------------------------------------------------

    def _ensure_engine(self) -> HyperliquidEngine:
        if self._engine is None:
            self._engine = HyperliquidEngine()
            logger.info("ManualTrader: HyperliquidEngine initialized")
        return self._engine

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    def open_position(
        self,
        symbol: str,
        side: str,
        size_usd: Optional[float] = None,
        size_pct: Optional[float] = None,
        leverage: int = 3,
        signal_at_trade: str = "",
        regime_at_trade: str = "",
    ) -> dict:
        """Open a manual position on Hyperliquid."""
        engine = self._ensure_engine()
        coin = symbol.split("/")[0]

        # Determine USD amount
        if size_usd and size_usd > 0:
            usd_amount = size_usd
        elif size_pct and size_pct > 0:
            summary = engine.get_account_summary()
            equity = summary.get("account_value", 0)
            if equity <= 0:
                raise EngineError("insufficient_funds", "Account equity is zero")
            usd_amount = equity * (size_pct / 100.0)
        else:
            raise EngineError("invalid_params", "Provide size_usd or size_pct")

        if usd_amount < 5.0:
            raise EngineError("too_small", f"Order too small: ${usd_amount:.2f} (min $5)")

        # Get current price for volume calculation
        positions = engine.get_positions()
        mark_price = 0.0
        # Try to get price from existing position
        for p in positions:
            if p.get("coin") == coin:
                mark_price = p.get("entry_price", 0)
                break

        # If no position, estimate from account context or use a conservative approach
        if mark_price <= 0:
            # Fetch from HL API via a minimal order preview
            # Use the info API to get mid price
            try:
                all_mids = engine._info.all_mids()
                mark_price = float(all_mids.get(coin, 0))
            except Exception:
                pass

        if mark_price <= 0:
            raise EngineError("no_price", f"Cannot determine price for {coin}")

        volume = usd_amount / mark_price
        volume = _format_volume(volume, mark_price)

        if volume <= 0:
            raise EngineError("zero_volume", f"Computed volume is zero for ${usd_amount:.2f} @ ${mark_price:.2f}")

        # Set leverage
        engine.set_leverage(coin, leverage)

        # Execute
        is_long = side.upper() == "LONG"
        if is_long:
            result = engine.buy(symbol, volume, mark_price, leverage)
        else:
            result = engine.sell(symbol, volume, mark_price, leverage)

        fill_price = result.get("price", mark_price)
        order_id = result.get("order_id", "")

        # Record trade
        trade = ManualTrade(
            id=uuid.uuid4().hex[:8],
            symbol=symbol,
            coin=coin,
            side=side.upper(),
            size_usd=usd_amount,
            volume=volume,
            leverage=leverage,
            entry_price=fill_price,
            status="OPEN",
            signal_at_trade=signal_at_trade,
            regime_at_trade=regime_at_trade,
            opened_at=time.time(),
            order_id=order_id,
        )
        self._trades.append(trade)
        self._save_trades()

        logger.info(
            "MANUAL TRADE: %s %s sz=$%.2f vol=%.6f @ $%.4f %dx (order %s)",
            side.upper(), symbol, usd_amount, volume, fill_price, leverage, order_id,
        )

        return {
            "status": "ok",
            "trade": trade.to_dict(),
        }

    def close_position(self, symbol: str) -> dict:
        """Close a position on Hyperliquid."""
        engine = self._ensure_engine()
        coin = symbol.split("/")[0]

        # Use market_close for clean full closure
        result = engine.close_position(symbol)

        # Find the matching open trade in our log
        open_trade = None
        for t in reversed(self._trades):
            if t.symbol == symbol and t.status == "OPEN":
                open_trade = t
                break

        # Try to get exit price from current positions or fills
        exit_price = 0.0
        try:
            recent_fills = engine.get_fills(5)
            for f in recent_fills:
                if f.get("coin") == coin:
                    exit_price = f.get("price", 0)
                    break
        except Exception:
            pass

        if open_trade:
            open_trade.status = "CLOSED"
            open_trade.closed_at = time.time()
            open_trade.close_order_id = result.get("order_id", "")

            if exit_price > 0:
                open_trade.exit_price = exit_price
                if open_trade.side == "LONG":
                    open_trade.pnl_pct = ((exit_price - open_trade.entry_price) / open_trade.entry_price) * 100
                else:
                    open_trade.pnl_pct = ((open_trade.entry_price - exit_price) / open_trade.entry_price) * 100
                open_trade.pnl_usd = open_trade.size_usd * (open_trade.pnl_pct / 100)

            self._save_trades()
            logger.info(
                "MANUAL CLOSE: %s %s pnl=%.2f%% ($%.2f)",
                open_trade.side, symbol, open_trade.pnl_pct, open_trade.pnl_usd,
            )

        return {
            "status": "closed",
            "symbol": symbol,
            "trade": open_trade.to_dict() if open_trade else None,
        }

    # ------------------------------------------------------------------
    # Proxies to engine
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        return self._ensure_engine().get_account_summary()

    def get_positions(self) -> list:
        return self._ensure_engine().get_positions()

    def get_fills(self, limit: int = 50) -> list:
        return self._ensure_engine().get_fills(limit)

    def set_leverage(self, coin: str, leverage: int, is_cross: bool = True) -> dict:
        return self._ensure_engine().set_leverage(coin, leverage, is_cross)

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

_trader: Optional[ManualTrader] = None


def get_manual_trader() -> ManualTrader:
    global _trader
    if _trader is None:
        _trader = ManualTrader()
    return _trader
