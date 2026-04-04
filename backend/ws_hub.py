"""
ws_hub.py
~~~~~~~~~
WebSocket connection manager for real-time scan event broadcasting.

Runs alongside existing REST endpoints — additive, not a replacement.
Frontend can subscribe via ``ws://host/ws/scan`` and receive:

- ``synthesis-complete``  — full scan results after each synthesis pass (every 60s)
- ``signal-transition``   — instant push when signals flip (ENTRY, EXIT, etc.)
- ``anomaly``             — new market anomalies
- ``symbol-update``       — individual symbol result from drip scan
- ``heartbeat``           — keepalive every 30s (prevents Railway proxy timeout)
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


class WebSocketHub:
    """Singleton manager for WebSocket connections + event broadcasting."""

    _instance: Optional["WebSocketHub"] = None

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()

    @classmethod
    def get(cls) -> "WebSocketHub":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Connection lifecycle ──────────────────────────────────────────────

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("WS client disconnected (%d remaining)", len(self._connections))

    @property
    def client_count(self) -> int:
        return len(self._connections)

    # ── Broadcasting ──────────────────────────────────────────────────────

    async def broadcast(self, event: Dict[str, Any]) -> None:
        """Send event to all connected clients. Silently drops dead connections."""
        if not self._connections:
            return

        payload = json.dumps(event, default=_safe_serialize)
        dead: List[WebSocket] = []

        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._connections.discard(ws)

    async def send_to(self, ws: WebSocket, event: Dict[str, Any]) -> None:
        """Send event to a specific client."""
        try:
            payload = json.dumps(event, default=_safe_serialize)
            await ws.send_text(payload)
        except Exception:
            self._connections.discard(ws)

    # ── Event helpers (called from scan pipeline) ─────────────────────────

    async def push_synthesis(
        self,
        results_4h: List[Dict],
        results_1d: List[Dict],
        consensus_4h: Optional[Dict],
        consensus_1d: Optional[Dict],
        meta: Optional[Dict] = None,
    ) -> None:
        """Broadcast full synthesis results — replaces REST polling for full state."""
        await self.broadcast({
            "type": "synthesis-complete",
            "data": {
                "results_4h": results_4h,
                "results_1d": results_1d,
                "consensus_4h": consensus_4h,
                "consensus_1d": consensus_1d,
                "meta": meta or {},
            },
            "ts": time.time(),
        })

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
        """Broadcast a single symbol update from drip scan."""
        await self.broadcast({
            "type": "symbol-update",
            "data": {
                "symbol": symbol,
                "result_4h": result_4h,
                "result_1d": result_1d,
            },
            "ts": time.time(),
        })

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
