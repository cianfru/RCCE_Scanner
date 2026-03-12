"""
trading_engine.py
~~~~~~~~~~~~~~~~~
Abstract trading engine with PaperEngine (simulation) and HyperliquidEngine (stub).

Replaces the kraken-cli subprocess layer. The executor calls engine.buy() / engine.sell()
instead of spawning a CLI process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

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
    def buy(self, symbol: str, volume: float, price: float, leverage: Optional[int] = None) -> dict:
        """Place a buy order. Returns {order_id, price, volume, cost}."""

    @abstractmethod
    def sell(self, symbol: str, volume: float, price: float, leverage: Optional[int] = None) -> dict:
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
    def buy(self, symbol: str, volume: float, price: float, leverage: Optional[int] = None) -> dict:
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
    def sell(self, symbol: str, volume: float, price: float, leverage: Optional[int] = None) -> dict:
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
# Hyperliquid Engine — live trading via Hyperliquid DEX
# ---------------------------------------------------------------------------

_DEFAULT_SLIPPAGE = 0.01  # 1% slippage tolerance for market orders


class HyperliquidEngine(TradingEngine):
    """Live trading engine targeting Hyperliquid DEX.

    Uses the ``hyperliquid-python-sdk`` for order placement, position
    queries, and leverage management.

    Requires:
        HL_PRIVATE_KEY env var (EVM wallet private key)
    """

    def __init__(self, default_leverage: int = 3):
        self._private_key = os.environ.get("HL_PRIVATE_KEY", "")
        if not self._private_key:
            raise EngineError("config", "HL_PRIVATE_KEY env var not set")

        try:
            from eth_account import Account
            from hyperliquid.info import Info
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils import constants
        except ImportError as exc:
            raise EngineError(
                "dependency",
                "hyperliquid-python-sdk not installed. "
                "Run: pip install hyperliquid-python-sdk",
            ) from exc

        self._account = Account.from_key(self._private_key)
        self._address: str = self._account.address
        self._info = Info(constants.MAINNET_API_URL)
        self._exchange = Exchange(self._account, constants.MAINNET_API_URL)
        self._default_leverage = default_leverage
        self._leverage_cache: Dict[str, int] = {}  # coin → last-set leverage
        self._order_counter: int = 0

        logger.info(
            "HyperliquidEngine initialised for address %s (default leverage %dx)",
            self._address[:10] + "...",
            self._default_leverage,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coin(symbol: str) -> str:
        """Convert scanner symbol 'BTC/USDT' → Hyperliquid coin 'BTC'."""
        return symbol.split("/")[0]

    def _next_order_id(self, hl_status: Optional[dict] = None) -> str:
        """Generate a local order ID, optionally enriched with HL response."""
        self._order_counter += 1
        if hl_status and isinstance(hl_status, dict):
            oid = hl_status.get("resting", {}).get("oid") or hl_status.get("filled", {}).get("oid", "")
            if oid:
                return f"hl-{oid}"
        return f"hl-{self._order_counter:06d}"

    def _ensure_leverage(self, coin: str, leverage: int) -> None:
        """Set leverage on Hyperliquid if different from cached value."""
        if self._leverage_cache.get(coin) == leverage:
            return
        try:
            self._exchange.update_leverage(leverage, coin, is_cross=True)
            self._leverage_cache[coin] = leverage
            logger.info("Set leverage for %s to %dx (cross)", coin, leverage)
        except Exception as exc:
            logger.warning("Failed to set leverage for %s to %dx: %s", coin, leverage, exc)
            # Non-fatal — trade can proceed with existing leverage

    def _parse_order_response(self, resp: dict, coin: str, is_buy: bool,
                               volume: float, price: float) -> dict:
        """Parse the SDK order response into a normalised dict."""
        statuses = []
        try:
            statuses = resp.get("response", {}).get("data", {}).get("statuses", [])
        except (AttributeError, TypeError):
            pass

        hl_status = statuses[0] if statuses else {}
        order_id = self._next_order_id(hl_status)

        # Try to extract fill price from response
        fill_px = price
        if isinstance(hl_status, dict):
            filled = hl_status.get("filled")
            if isinstance(filled, dict):
                fill_px = float(filled.get("avgPx", price))

        cost = volume * fill_px

        return {
            "order_id": order_id,
            "price": fill_px,
            "volume": volume,
            "cost" if is_buy else "proceeds": cost,
            "side": "BUY" if is_buy else "SELL",
            "coin": coin,
            "raw_status": hl_status,
        }

    # ------------------------------------------------------------------
    # Buy / Sell
    # ------------------------------------------------------------------

    def buy(self, symbol: str, volume: float, price: float, leverage: Optional[int] = None) -> dict:
        """Place a long / buy order on Hyperliquid."""
        coin = self._coin(symbol)
        lev = leverage or self._default_leverage
        self._ensure_leverage(coin, lev)

        logger.info("HL BUY %s: sz=%.6f, price=~$%.2f, leverage=%dx", coin, volume, price, lev)

        try:
            resp = self._exchange.market_open(
                coin, is_buy=True, sz=volume, slippage=_DEFAULT_SLIPPAGE,
            )
        except Exception as exc:
            raise EngineError("order_failed", f"HL buy {coin} failed: {exc}") from exc

        status = resp.get("status", "")
        if status != "ok":
            err_msg = resp.get("response", {}).get("data", {}).get("error", str(resp))
            raise EngineError("order_rejected", f"HL buy {coin} rejected: {err_msg}")

        result = self._parse_order_response(resp, coin, is_buy=True, volume=volume, price=price)
        logger.info(
            "HL BUY filled: %s sz=%.6f @ $%.4f (order %s)",
            coin, volume, result["price"], result["order_id"],
        )
        return result

    def sell(self, symbol: str, volume: float, price: float, leverage: Optional[int] = None) -> dict:
        """Place a short / sell order on Hyperliquid."""
        coin = self._coin(symbol)
        lev = leverage or self._default_leverage
        self._ensure_leverage(coin, lev)

        logger.info("HL SELL %s: sz=%.6f, price=~$%.2f, leverage=%dx", coin, volume, price, lev)

        try:
            resp = self._exchange.market_open(
                coin, is_buy=False, sz=volume, slippage=_DEFAULT_SLIPPAGE,
            )
        except Exception as exc:
            raise EngineError("order_failed", f"HL sell {coin} failed: {exc}") from exc

        status = resp.get("status", "")
        if status != "ok":
            err_msg = resp.get("response", {}).get("data", {}).get("error", str(resp))
            raise EngineError("order_rejected", f"HL sell {coin} rejected: {err_msg}")

        result = self._parse_order_response(resp, coin, is_buy=False, volume=volume, price=price)
        logger.info(
            "HL SELL filled: %s sz=%.6f @ $%.4f (order %s)",
            coin, volume, result["price"], result["order_id"],
        )
        return result

    def close_position(self, symbol: str) -> dict:
        """Close an entire position on Hyperliquid using market_close."""
        coin = self._coin(symbol)
        logger.info("HL CLOSE position: %s", coin)

        try:
            resp = self._exchange.market_close(coin, slippage=_DEFAULT_SLIPPAGE)
        except Exception as exc:
            raise EngineError("close_failed", f"HL close {coin} failed: {exc}") from exc

        status = resp.get("status", "")
        if status != "ok":
            err_msg = resp.get("response", {}).get("data", {}).get("error", str(resp))
            raise EngineError("close_rejected", f"HL close {coin} rejected: {err_msg}")

        logger.info("HL CLOSE %s: %s", coin, status)
        return {"status": "closed", "coin": coin, "raw": resp}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_balance(self) -> float:
        """Return account equity from Hyperliquid."""
        try:
            state = self._info.user_state(self._address)
            summary = state.get("marginSummary", {})
            return float(summary.get("accountValue", 0.0))
        except Exception as exc:
            raise EngineError("query_failed", f"Failed to get HL balance: {exc}") from exc

    def get_portfolio(self) -> dict:
        """Return full portfolio from Hyperliquid: positions + margin."""
        try:
            state = self._info.user_state(self._address)
        except Exception as exc:
            raise EngineError("query_failed", f"Failed to get HL portfolio: {exc}") from exc

        summary = state.get("marginSummary", {})
        account_value = float(summary.get("accountValue", 0.0))
        margin_used = float(summary.get("totalMarginUsed", 0.0))
        available_margin = account_value - margin_used

        positions = []
        for ap in state.get("assetPositions", []):
            pos = ap.get("position", {})
            coin = pos.get("coin", "")
            szi = float(pos.get("szi", 0.0))
            if abs(szi) < 1e-12:
                continue
            entry_px = float(pos.get("entryPx", 0.0))
            unrealized_pnl = float(pos.get("unrealizedPnl", 0.0))
            margin_used_pos = float(pos.get("marginUsed", 0.0))
            liq_px = pos.get("liquidationPx")
            leverage_info = pos.get("leverage", {})
            lev_type = leverage_info.get("type", "cross")
            lev_val = int(leverage_info.get("value", self._default_leverage))

            positions.append({
                "coin": coin,
                "symbol": f"{coin}/USDT",
                "size": szi,
                "side": "LONG" if szi > 0 else "SHORT",
                "entry_price": entry_px,
                "unrealized_pnl": unrealized_pnl,
                "margin_used": margin_used_pos,
                "liquidation_price": float(liq_px) if liq_px else None,
                "leverage": lev_val,
                "leverage_type": lev_type,
                "notional_value": abs(szi) * entry_px,
            })

        return {
            "cash": round(available_margin, 2),
            "account_value": round(account_value, 2),
            "margin_used": round(margin_used, 2),
            "available_margin": round(available_margin, 2),
            "positions": positions,
            "holding_count": len(positions),
            "total_value": round(account_value, 2),
        }

    def get_positions(self) -> List[dict]:
        """Return current open positions from Hyperliquid."""
        portfolio = self.get_portfolio()
        return portfolio.get("positions", [])

    def get_fills(self, limit: int = 50) -> List[dict]:
        """Return recent order fills from Hyperliquid."""
        try:
            fills = self._info.user_fills(self._address)
        except Exception as exc:
            logger.warning("Failed to get HL fills: %s", exc)
            return []

        if not isinstance(fills, list):
            return []

        # Sort newest first and limit
        fills = sorted(fills, key=lambda f: f.get("time", 0), reverse=True)[:limit]

        result = []
        for f in fills:
            result.append({
                "coin": f.get("coin", ""),
                "side": f.get("side", ""),
                "size": float(f.get("sz", 0)),
                "price": float(f.get("px", 0)),
                "time": f.get("time", 0),
                "fee": float(f.get("fee", 0)),
                "crossed": f.get("crossed", False),
                "hash": f.get("hash", ""),
                "oid": f.get("oid", ""),
                "close_position": f.get("closedPnl") is not None,
                "closed_pnl": float(f.get("closedPnl", 0)),
            })
        return result

    def set_leverage(self, coin: str, leverage: int, is_cross: bool = True) -> dict:
        """Set leverage for a specific coin."""
        try:
            self._exchange.update_leverage(leverage, coin, is_cross=is_cross)
            self._leverage_cache[coin] = leverage
            logger.info("Leverage set: %s → %dx (%s)", coin, leverage, "cross" if is_cross else "isolated")
            return {"status": "ok", "coin": coin, "leverage": leverage, "type": "cross" if is_cross else "isolated"}
        except Exception as exc:
            raise EngineError("leverage_failed", f"Failed to set leverage for {coin}: {exc}") from exc

    def get_account_summary(self) -> dict:
        """Return account-level summary from Hyperliquid."""
        try:
            state = self._info.user_state(self._address)
        except Exception as exc:
            raise EngineError("query_failed", f"Failed to get HL account: {exc}") from exc

        summary = state.get("marginSummary", {})
        positions = state.get("assetPositions", [])
        active_positions = [p for p in positions if abs(float(p.get("position", {}).get("szi", 0))) > 1e-12]

        return {
            "address": self._address,
            "account_value": float(summary.get("accountValue", 0)),
            "total_margin_used": float(summary.get("totalMarginUsed", 0)),
            "total_ntl_pos": float(summary.get("totalNtlPos", 0)),
            "total_raw_usd": float(summary.get("totalRawUsd", 0)),
            "positions_count": len(active_positions),
        }

    # ------------------------------------------------------------------
    # Persistence (minimal — live state is on-chain)
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "type": "hyperliquid",
            "address": self._address,
            "default_leverage": self._default_leverage,
            "leverage_cache": self._leverage_cache,
            "order_counter": self._order_counter,
        }

    def load_state(self, data: dict) -> None:
        if not data or data.get("type") != "hyperliquid":
            return
        self._leverage_cache = data.get("leverage_cache", {})
        self._order_counter = data.get("order_counter", 0)
        self._default_leverage = data.get("default_leverage", self._default_leverage)
        logger.info(
            "HyperliquidEngine state restored: %d leverage entries, %d orders placed",
            len(self._leverage_cache), self._order_counter,
        )

    def reset(self, balance: float) -> dict:
        """Reset clears local state only — cannot reset a live account."""
        self._leverage_cache.clear()
        self._order_counter = 0
        logger.info("HyperliquidEngine local state reset (live account unchanged)")
        return {"status": "reset", "note": "Local state cleared. Live positions are unaffected."}
