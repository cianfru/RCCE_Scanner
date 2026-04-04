"""
price_ticker.py
~~~~~~~~~~~~~~~
Lightweight price ticker relay — Binance + Hyperliquid WebSocket streams.

Subscribes to Binance combined mini-ticker for CEX-listed symbols and
Hyperliquid's allMids stream for HL-native tokens (HYPE, PURR, etc.).
Batches all price updates into a single broadcast every ~1 second.

Payload is minimal — just ``{symbol: price}`` — no extra API calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Set

logger = logging.getLogger("price_ticker")

# Batch interval — collect ticks for this long before broadcasting
_BATCH_INTERVAL = 1.0  # seconds


# ── Symbol conversion helpers ─────────────────────────────────────────────────

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


# ── Known Binance-listed symbols cache ────────────────────────────────────────
# Populated on first connect; symbols NOT on this set go to Hyperliquid.

_binance_symbols: Optional[Set[str]] = None


async def _check_binance_symbol(base: str) -> bool:
    """Quick check if a base asset is on Binance (via exchange info cache)."""
    global _binance_symbols
    if _binance_symbols is not None:
        return base.upper() in _binance_symbols

    # Fetch once from Binance
    try:
        import aiohttp
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                "https://api.binance.com/api/v3/exchangeInfo",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    _binance_symbols = {
                        s["baseAsset"].upper()
                        for s in data.get("symbols", [])
                        if s.get("status") == "TRADING"
                    }
                    return base.upper() in _binance_symbols
    except Exception as exc:
        logger.debug("Binance exchangeInfo fetch failed: %s", exc)

    _binance_symbols = set()
    return False


class PriceTicker:
    """Singleton that relays Binance + Hyperliquid tickers to our WebSocket hub."""

    _instance: Optional["PriceTicker"] = None

    def __init__(self) -> None:
        self._prices: Dict[str, float] = {}    # symbol -> latest price
        self._dirty: Dict[str, float] = {}     # prices changed since last broadcast
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
        """Main loop: launch Binance + Hyperliquid streams + broadcast task."""
        self._running = True

        # Classify symbols into Binance vs Hyperliquid
        symbols = self._get_watchlist_symbols()
        binance_syms = []
        hl_coins = []

        for sym in symbols:
            base = sym.split("/")[0] if "/" in sym else sym
            if await _check_binance_symbol(base):
                binance_syms.append(sym)
            else:
                hl_coins.append(base)

        logger.info(
            "Price ticker: %d Binance, %d Hyperliquid-only symbols",
            len(binance_syms), len(hl_coins),
        )

        # Launch all tasks concurrently
        tasks = [asyncio.create_task(self._broadcast_loop())]

        if binance_syms:
            tasks.append(asyncio.create_task(self._binance_loop(binance_syms)))
        if hl_coins:
            tasks.append(asyncio.create_task(self._hyperliquid_loop(hl_coins)))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()

    async def stop(self) -> None:
        self._running = False

    # ── Binance stream ────────────────────────────────────────────────────

    async def _binance_loop(self, symbols: list) -> None:
        """Binance combined mini-ticker stream with auto-reconnect."""
        import websockets

        while self._running:
            try:
                streams = []
                for sym in symbols:
                    s = _ccxt_to_binance(sym)
                    if s:
                        streams.append(s)

                if not streams:
                    await asyncio.sleep(30)
                    continue

                stream_path = "/".join(streams[:200])
                url = f"wss://stream.binance.com:9443/stream?streams={stream_path}"

                logger.info("Connecting to Binance ticker (%d symbols)", len(streams))

                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    async for raw in ws:
                        if not self._running:
                            return
                        try:
                            msg = json.loads(raw)
                            data = msg.get("data", msg)
                            binance_sym = data.get("s", "")
                            price_str = data.get("c", "")
                            if binance_sym and price_str:
                                ccxt_sym = _binance_to_ccxt(binance_sym)
                                if ccxt_sym:
                                    price = float(price_str)
                                    self._prices[ccxt_sym] = price
                                    self._dirty[ccxt_sym] = price
                        except Exception:
                            pass

            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Binance ticker error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    # ── Hyperliquid stream ────────────────────────────────────────────────

    async def _hyperliquid_loop(self, coins: list) -> None:
        """Hyperliquid allMids WebSocket — covers HL-native tokens not on Binance."""
        import websockets

        # Map HL coin names to CCXT symbols
        coin_to_ccxt = {coin.upper(): f"{coin.upper()}/USDT" for coin in coins}
        coin_set = set(coin_to_ccxt.keys())

        while self._running:
            try:
                url = "wss://api.hyperliquid.xyz/ws"
                logger.info("Connecting to Hyperliquid ticker (%d coins: %s)",
                            len(coins), ", ".join(coins[:10]))

                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    # Subscribe to allMids channel
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "allMids"},
                    }))

                    async for raw in ws:
                        if not self._running:
                            return
                        try:
                            msg = json.loads(raw)
                            # allMids response: {"channel": "allMids", "data": {"mids": {"BTC": "67423.5", ...}}}
                            if msg.get("channel") == "allMids":
                                mids = msg.get("data", {}).get("mids", {})
                                for coin, price_str in mids.items():
                                    if coin.upper() in coin_set:
                                        ccxt_sym = coin_to_ccxt[coin.upper()]
                                        try:
                                            price = float(price_str)
                                            self._prices[ccxt_sym] = price
                                            self._dirty[ccxt_sym] = price
                                        except ValueError:
                                            pass
                        except Exception:
                            pass

            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Hyperliquid ticker error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    # ── Broadcast ─────────────────────────────────────────────────────────

    async def _broadcast_loop(self) -> None:
        """Flush dirty prices to WebSocket hub every _BATCH_INTERVAL seconds."""
        from ws_hub import WebSocketHub

        while self._running:
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
            return [s for s in cache.symbols if s.endswith("/USDT")]
        except Exception:
            return []
