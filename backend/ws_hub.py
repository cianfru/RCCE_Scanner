"""
ws_hub.py
~~~~~~~~~
WebSocket connection manager for real-time scan event broadcasting.

Runs alongside existing REST endpoints — additive, not a replacement.
Frontend can subscribe via ``ws://host/ws/scan`` and receive:

- ``scan-updated``        — a synthesis pass finished (protocol 2, visible tabs);
                            the page refetches the timeframe it shows over HTTP
- ``synthesis-complete``  — full scan state: on connect and on "refresh" (protocol 1)
- ``signal-transition``   — instant push when signals flip (ENTRY, EXIT, etc.)
- ``anomaly``             — new market anomalies
- ``symbol-update``       — individual symbol result from drip scan (protocol 1)
- ``price-tick``          — changed prices every 5 s (visible tabs); ``price-snapshot``
                            all prices when a protocol-2 tab connects or becomes visible
- ``heartbeat``           — keepalive every 30s (prevents Railway proxy timeout)

Protocol 2 clients connect with ``?v=2`` and send ``{"type": "pause"}`` when their
tab is hidden and ``{"type": "resume"}`` when it is visible again.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("ws_hub")


def _safe_serialize(obj: Any) -> Any:
    """JSON-safe conversion for numpy/datetime types commonly in scan results."""
    import numpy as np
    from datetime import datetime

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _count(event: Dict[str, Any], payload: str, recipients: int) -> None:
    """Record WebSocket egress (best effort, never raises)."""
    if recipients <= 0:
        return
    try:
        import egress
        egress.record_ws(event.get("type", "?"), len(payload), recipients, egress.estimate_deflate(payload))
    except Exception:
        pass


class WebSocketHub:
    """Singleton manager for WebSocket connections + event broadcasting."""

    _instance: Optional["WebSocketHub"] = None

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        # Per connection: protocol version and whether the tab is hidden.
        # Version 2 clients (the current frontend) receive a small "scan-updated"
        # notice instead of full scan state, and pause price ticks while hidden.
        # Version 1 (older cached pages) keeps the original events.
        self._meta: Dict[WebSocket, Dict[str, Any]] = {}

    @classmethod
    def get(cls) -> "WebSocketHub":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Connection lifecycle ──────────────────────────────────────────────

    async def connect(self, ws: WebSocket, protocol: int = 1) -> None:
        await ws.accept()
        self._connections.add(ws)
        self._meta[ws] = {"v": protocol, "paused": False}
        # Opening a dashboard is the primary "wake" signal — bump activity so
        # idle background loops resume full cadence within a few seconds.
        try:
            from activity import mark_active
            mark_active("ws-connect")
        except Exception:
            pass
        logger.info("WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._drop(ws)
        logger.info("WS client disconnected (%d remaining)", len(self._connections))

    def _drop(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        self._meta.pop(ws, None)

    def set_paused(self, ws: WebSocket, paused: bool) -> None:
        """A version-2 client reports its tab hidden (paused) or visible again."""
        meta = self._meta.get(ws)
        if meta is not None:
            meta["paused"] = bool(paused)

    @property
    def client_count(self) -> int:
        return len(self._connections)

    @property
    def active_count(self) -> int:
        """Connections whose tab is visible (paused ones get no ticks or scan notices)."""
        return sum(1 for ws in self._connections if not (self._meta.get(ws) or {}).get("paused"))

    def counts(self) -> Dict[str, int]:
        v2 = sum(1 for ws in self._connections if (self._meta.get(ws) or {}).get("v") == 2)
        return {"total": self.client_count, "active": self.active_count,
                "v2": v2, "legacy": self.client_count - v2}

    def _audience(self, audience: str) -> List[WebSocket]:
        if audience == "all":
            return list(self._connections)
        out = []
        for ws in self._connections:
            meta = self._meta.get(ws) or {"v": 1, "paused": False}
            if audience == "active" and not meta["paused"]:
                out.append(ws)
            elif audience == "legacy" and meta["v"] == 1:
                out.append(ws)
            elif audience == "active_v2" and meta["v"] == 2 and not meta["paused"]:
                out.append(ws)
        return out

    # ── Broadcasting ──────────────────────────────────────────────────────

    async def broadcast(self, event: Dict[str, Any], audience: str = "all") -> None:
        """Send event to clients. Silently drops dead connections.

        audience: "all", "active" (tab visible), "legacy" (protocol 1) or
        "active_v2" (protocol 2 with the tab visible).
        """
        targets = self._audience(audience)
        if not targets:
            return

        payload = json.dumps(event, default=_safe_serialize)
        dead: List[WebSocket] = []

        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._drop(ws)
        _count(event, payload, len(targets) - len(dead))

    async def send_to(self, ws: WebSocket, event: Dict[str, Any]) -> None:
        """Send event to a specific client."""
        try:
            payload = json.dumps(event, default=_safe_serialize)
            await ws.send_text(payload)
            _count(event, payload, 1)
        except Exception:
            self._drop(ws)

    # ── Event helpers (called from scan pipeline) ─────────────────────────

    async def push_scan_updated(self, timestamp: Optional[float] = None) -> None:
        """Tell visible protocol-2 clients a synthesis pass finished (a few dozen bytes)."""
        await self.broadcast({
            "type": "scan-updated",
            "data": {"timestamp": timestamp or time.time()},
            "ts": time.time(),
        }, audience="active_v2")

    async def push_synthesis(
        self,
        results_4h: List[Dict],
        results_1d: List[Dict],
        consensus_4h: Optional[Dict],
        consensus_1d: Optional[Dict],
        meta: Optional[Dict] = None,
    ) -> None:
        """Tell visible clients a synthesis pass finished; they refetch what they show.

        The full state of both timeframes was ~4 MB of JSON per pass per client
        (~1.1 MB after WebSocket compression), sent every minute even to hidden
        tabs. Pages now fetch the timeframe on screen over HTTP (gzip + ETag), so
        only a small notice goes out. Older pages (protocol 1) still poll the scan
        every minute themselves, so they no longer get the periodic full push
        either; they keep the full state on connect and on "refresh".
        """
        await self.push_scan_updated((meta or {}).get("timestamp"))

    async def push_signal_transition(self, transitions: List[Dict]) -> None:
        """Broadcast signal transitions (ENTRY, EXIT, TRIM, regime change)."""
        if not transitions:
            return
        await self.broadcast({
            "type": "signal-transition",
            "data": transitions,
            "ts": time.time(),
        })

    async def push_anomaly(self, anomalies: list) -> None:
        """Broadcast new market anomalies."""
        if not anomalies:
            return
        # Convert dataclass/object anomalies to dicts if needed
        items = []
        for a in anomalies:
            if hasattr(a, "__dict__"):
                items.append({k: v for k, v in a.__dict__.items() if not k.startswith("_")})
            elif isinstance(a, dict):
                items.append(a)
            else:
                items.append(str(a))
        await self.broadcast({
            "type": "anomaly",
            "data": items,
            "ts": time.time(),
        })

    async def push_symbol_update(
        self, symbol: str, result_4h: Optional[Dict], result_1d: Optional[Dict]
    ) -> None:
        """Broadcast a single symbol update from drip scan (protocol-1 pages only).

        Current pages pick up the change with the next synthesis pass, which
        replaces the raw row anyway.
        """
        await self.broadcast({
            "type": "symbol-update",
            "data": {
                "symbol": symbol,
                "result_4h": result_4h,
                "result_1d": result_1d,
            },
            "ts": time.time(),
        }, audience="legacy")

    # ── Heartbeat ─────────────────────────────────────────────────────────

    async def run_heartbeat(self, interval: float = 30.0) -> None:
        """Send periodic heartbeat to keep connections alive.

        Railway's proxy drops idle WebSocket connections after ~5 min.
        30s heartbeat prevents this.
        """
        while True:
            await asyncio.sleep(interval)
            if self._connections:
                await self.broadcast({
                    "type": "heartbeat",
                    "ts": time.time(),
                    "clients": len(self._connections),
                })
