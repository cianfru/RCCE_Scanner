"""
trading_engine.py
~~~~~~~~~~~~~~~~~
Abstract trading engine with PaperEngine (simulation) and HyperliquidEngine (stub).

Replaces the kraken-cli subprocess layer. The executor calls engine.buy() / engine.sell()
instead of spawning a CLI process.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class EngineError(Exception):
    """Raised when a trading engine operation fails."""
    def __init__(self, category: str, message: str):
        self.category = category
        self.message = message
        super().__init__(f"[{category}] {message}")


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class PaperHolding:
    """A single holding in the paper portfolio."""
    symbol: str
    volume: float
    avg_price: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> PaperHolding:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class TradingEngine(ABC):
    """Interface for order execution engines."""

    @abstractmethod
    def buy(self, symbol: str, volume: float, price: float) -> dict:
        """Place a buy order. Returns {order_id, price, volume, cost}."""

    @abstractmethod
    def sell(self, symbol: str, volume: float, price: float) -> dict:
        """Place a sell order. Returns {order_id, price, volume, proceeds}."""

    @abstractmethod
    def get_balance(self) -> float:
        """Return available cash balance."""

    @abstractmethod
    def get_portfolio(self) -> dict:
        """Return full portfolio: {cash, holdings, total_value}."""

    @abstractmethod
    def get_state(self) -> dict:
        """Return serializable state for JSON persistence."""

    @abstractmethod
    def load_state(self, data: dict) -> None:
        """Restore engine state from persisted data."""

    @abstractmethod
    def reset(self, balance: float) -> dict:
        """Reset to initial state with given balance."""


# ---------------------------------------------------------------------------
# Paper Engine — pure in-memory simulation
# ---------------------------------------------------------------------------

class PaperEngine(TradingEngine):
    """Simulated trading engine. Zero network calls.

    Tracks cash balance and holdings. Uses the price provided by the scanner
    (i.e. the last close price at scan time) as the fill price.
    """

    def __init__(self, initial_balance: float = 10_000.0):
        self.cash: float = initial_balance
        self.holdings: Dict[str, PaperHolding] = {}
        self._order_counter: int = 0
        self._initial_balance = initial_balance

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"paper-{self._order_counter:04d}"

    # -- Buy --
    def buy(self, symbol: str, volume: float, price: float) -> dict:
        cost = volume * price
        if cost > self.cash:
            raise EngineError(
                "insufficient_funds",
                f"Buy {symbol} costs ${cost:.2f} but only ${self.cash:.2f} available",
            )

        self.cash -= cost
        order_id = self._next_order_id()

        if symbol in self.holdings:
            h = self.holdings[symbol]
            total_vol = h.volume + volume
            h.avg_price = (h.avg_price * h.volume + price * volume) / total_vol
            h.volume = total_vol
        else:
            self.holdings[symbol] = PaperHolding(
                symbol=symbol, volume=volume, avg_price=price,
            )

        logger.debug(
            "Paper BUY %s: vol=%.6f @ $%.2f (cost=$%.2f, cash=$%.2f)",
            symbol, volume, price, cost, self.cash,
        )
        return {"order_id": order_id, "price": price, "volume": volume, "cost": cost}

    # -- Sell --
    def sell(self, symbol: str, volume: float, price: float) -> dict:
        if symbol not in self.holdings:
            raise EngineError(
                "no_position",
                f"Cannot sell {symbol} — no holdings",
            )

        h = self.holdings[symbol]
        if volume > h.volume * 1.001:  # tiny tolerance for float precision
            raise EngineError(
                "insufficient_volume",
                f"Cannot sell {volume:.6f} {symbol} — only hold {h.volume:.6f}",
            )

        proceeds = volume * price
        self.cash += proceeds
        order_id = self._next_order_id()

        h.volume -= volume
        if h.volume < 1e-12:
            del self.holdings[symbol]

        logger.debug(
            "Paper SELL %s: vol=%.6f @ $%.2f (proceeds=$%.2f, cash=$%.2f)",
            symbol, volume, price, proceeds, self.cash,
        )
        return {"order_id": order_id, "price": price, "volume": volume, "proceeds": proceeds}

    # -- Queries --
    def get_balance(self) -> float:
        return self.cash

    def get_portfolio(self) -> dict:
        holdings_dict = {}
        for sym, h in self.holdings.items():
            holdings_dict[sym] = {
                "volume": h.volume,
                "avg_price": h.avg_price,
            }

        return {
            "cash": round(self.cash, 2),
            "holdings": holdings_dict,
            "holding_count": len(self.holdings),
        }

    # -- Persistence --
    def get_state(self) -> dict:
        return {
            "type": "paper",
            "cash": self.cash,
            "holdings": {sym: h.to_dict() for sym, h in self.holdings.items()},
            "order_counter": self._order_counter,
            "initial_balance": self._initial_balance,
        }

    def load_state(self, data: dict) -> None:
        if not data or data.get("type") != "paper":
            return
        self.cash = data.get("cash", self._initial_balance)
        self._order_counter = data.get("order_counter", 0)
        self._initial_balance = data.get("initial_balance", self._initial_balance)

        self.holdings.clear()
        for sym, h_dict in data.get("holdings", {}).items():
            self.holdings[sym] = PaperHolding.from_dict(h_dict)

        logger.info(
            "PaperEngine restored: $%.2f cash, %d holdings, %d orders placed",
            self.cash, len(self.holdings), self._order_counter,
        )

    def reset(self, balance: float) -> dict:
        self.cash = balance
        self.holdings.clear()
        self._order_counter = 0
        self._initial_balance = balance
        logger.info("PaperEngine reset: $%.2f", balance)
        return {"status": "reset", "cash": balance}


# ---------------------------------------------------------------------------
# Hyperliquid Engine — stub for future live trading
# ---------------------------------------------------------------------------

class HyperliquidEngine(TradingEngine):
    """Live trading engine targeting Hyperliquid DEX.

    Uses Hyperliquid Python SDK for order placement.
    NOT fully implemented — placeholder for when the user is ready to go live.

    Requires:
        HL_PRIVATE_KEY env var (Hyperliquid wallet private key)
    """

    def __init__(self):
        import os
        self._private_key = os.environ.get("HL_PRIVATE_KEY", "")
        if not self._private_key:
            logger.warning(
                "HyperliquidEngine: HL_PRIVATE_KEY not set — live trading disabled"
            )
        # SDK client will be initialized here when implemented
        self._client = None

    def buy(self, symbol: str, volume: float, price: float) -> dict:
        raise EngineError("not_implemented", "Hyperliquid live trading not yet implemented")

    def sell(self, symbol: str, volume: float, price: float) -> dict:
        raise EngineError("not_implemented", "Hyperliquid live trading not yet implemented")

    def get_balance(self) -> float:
        raise EngineError("not_implemented", "Hyperliquid live trading not yet implemented")

    def get_portfolio(self) -> dict:
        raise EngineError("not_implemented", "Hyperliquid live trading not yet implemented")

    def get_state(self) -> dict:
        return {"type": "hyperliquid"}

    def load_state(self, data: dict) -> None:
        pass  # No state to restore for live engine

    def reset(self, balance: float) -> dict:
        raise EngineError("not_implemented", "Cannot reset live Hyperliquid account")
