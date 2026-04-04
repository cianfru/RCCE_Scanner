"""
price_ticker.py
~~~~~~~~~~~~~~~
Lightweight Binance WebSocket ticker relay.

Subscribes to Binance's combined mini-ticker stream for all watchlist
symbols, batches price updates into a single dict, and pushes to our
WebSocket hub every ~1 second.

Payload is minimal — just ``{symbol: price}`` — no extra API calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Set

logger = logging.getLogger("price_ticker")

# ── Binance WebSocket ─────────────────────────────────────────────────────────

_BINANCE_WS = "wss://stream.binance.com:9443/ws"

# Batch interval — collect ticks for this long before broadcasting
_BATCH_INTERVAL = 1.0  # seconds


def _ccxt_to_binance(symbol: str) -> Optional[str]:
    """Convert CCXT symbol (BTC/USDT) to Binance stream name (btcusdt@miniTicker)."""
    parts = symbol.split("/")
    if len(parts) != 2:
        return None
    return f"{parts[0].lower()}{parts[1].lower()}@miniTicker"


def _binance_to_ccxt(stream_symbol: str) -> Optional[str]:
    """Convert Binance symbol (BTCUSDT) back to CCXT (BTC/USDT)."""
    s = stream_symbol.upper()
    for quote in ("USDT", "BTC", "BUSD"):
        if s.endswith(quote):
            base = s[: -len(quote)]
            if base:
                return f"{base}/{quote}"
    return None


class PriceTicker:
    """Singleton that relays Binance mini-tickers to our WebSocket hub."""

    _instance: Optional["PriceTicker"] = None

    def __init__(self) -> None:
        self._prices: Dict[str, float] = {}    # symbol -> latest price
        self._dirty: Dict[str, float] = {}     # prices changed since last broadcast
        self._subscribed: Set[str] = set()     # Binance stream names
        self._ws = None
        self._running = False

    @classmethod
    def get(cls) -> "PriceTicker":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def prices(self) -> Dict[str, float]:
        return dict(self._prices)

    async def run(self) -> None:
        """Main loop: connect to Binance, consume ticks, broadcast batches."""
        self._running = True

        while self._running:
            try:
                await self._connect_and_stream()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Ticker stream error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _connect_and_stream(self) -> None:
        """Single connection lifecycle."""
        import websockets

        symbols = self._get_watchlist_symbols()
        if not symbols:
            logger.info("No watchlist symbols — ticker idle, retrying in 30s")
            await asyncio.sleep(30)
            return

        streams = []
        for sym in symbols:
            s = _ccxt_to_binance(sym)
            if s:
                streams.append(s)

        if not streams:
            await asyncio.sleep(30)
            return

        # Binance combined stream URL
        stream_path = "/".join(streams[:200])  # Binance limit ~200 streams
        url = f"wss://stream.binance.com:9443/stream?streams={stream_path}"

        logger.info("Connecting to Binance ticker (%d symbols)", len(streams))

        async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
            self._ws = ws
            self._subscribed = set(streams)

            # Start broadcast task
            broadcast_task = asyncio.create_task(self._broadcast_loop())

            try:
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        data = msg.get("data", msg)
                        self._handle_tick(data)
                    except Exception:
                        pass
            finally:
                broadcast_task.cancel()
                try:
                    await broadcast_task
                except asyncio.CancelledError:
                    pass

    def _handle_tick(self, data: dict) -> None:
        """Process a single mini-ticker message."""
        binance_sym = data.get("s", "")
        price_str = data.get("c", "")  # 'c' = close price in miniTicker
        if not binance_sym or not price_str:
            return

        ccxt_sym = _binance_to_ccxt(binance_sym)
        if not ccxt_sym:
            return

        try:
            price = float(price_str)
        except ValueError:
            return

        self._prices[ccxt_sym] = price
        self._dirty[ccxt_sym] = price

    async def _broadcast_loop(self) -> None:
        """Flush dirty prices to WebSocket hub every _BATCH_INTERVAL seconds."""
        from ws_hub import WebSocketHub

        while True:
            await asyncio.sleep(_BATCH_INTERVAL)

            if not self._dirty:
                continue

            hub = WebSocketHub.get()
            if hub.client_count == 0:
                self._dirty.clear()
                continue

            # Snapshot and clear
            batch = self._dirty
            self._dirty = {}

            await hub.broadcast({
                "type": "price-tick",
                "data": batch,
                "ts": time.time(),
            })

    def _get_watchlist_symbols(self) -> list:
        """Get current watchlist from scan cache."""
        try:
            from scanner import cache
            # Only USDT pairs work on Binance stream
            return [s for s in cache.symbols if s.endswith("/USDT")]
        except Exception:
            return []
