/**
 * useWebSocket — React hook for real-time scan data via WebSocket.
 *
 * Singleton connection shared across all components (same pattern as useSharedWorker).
 * Auto-reconnect with exponential backoff. Falls back gracefully if WS unavailable.
 *
 * Events consumed:
 *   scan-updated        → a new scan is ready; the page refetches what it shows
 *   synthesis-complete  → full scan results (older servers only)
 *   price-tick          → changed prices (every 5 s while the tab is visible)
 *   price-snapshot      → all prices, on connect and when the tab is shown again
 *   signal-transition   → instant signal flips
 *   anomaly             → new market anomalies
 *   heartbeat           → keepalive (no action needed)
 *
 * Protocol 2 (?v=2): the tab tells the server when it is hidden ("pause") and
 * visible again ("resume"), so hidden tabs get no price ticks or scan notices.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { withToken } from "../auth.js";

// ── Derive WebSocket URL from API base ───────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getWsUrl() {
  // Convert http(s)://host to ws(s)://host
  const base = API_BASE.replace(/^http/, "ws");
  return withToken(`${base}/ws/scan?v=2`);
}

// ── Singleton WebSocket manager ──────────────────────────────────────────────

let ws = null;
let listeners = new Set();
let listenerIdCounter = 0;
let reconnectTimer = null;
let reconnectAttempt = 0;
let intentionalClose = false;
let wsConnected = false;

const MAX_RECONNECT_DELAY = 30_000; // 30s cap
const BASE_RECONNECT_DELAY = 1_000; // 1s initial

function notifyListeners(event) {
  for (const listener of listeners) {
    try {
      listener.handler(event);
    } catch (_) {}
  }
}

function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return; // Already connected or connecting
  }

  intentionalClose = false;

  try {
    ws = new WebSocket(getWsUrl());
  } catch (_) {
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    reconnectAttempt = 0;
    wsConnected = true;
    if (document.hidden) sendMessage({ type: "pause" });
    notifyListeners({ type: "_ws_status", connected: true });
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      notifyListeners(data);
    } catch (_) {}
  };

  ws.onclose = () => {
    wsConnected = false;
    notifyListeners({ type: "_ws_status", connected: false });
    if (!intentionalClose) {
      scheduleReconnect();
    }
  };

  ws.onerror = () => {
    // onclose will fire after this — reconnect handled there
  };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  const delay = Math.min(BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempt), MAX_RECONNECT_DELAY);
  reconnectAttempt++;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, delay);
}

function disconnect() {
  intentionalClose = true;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close();
    ws = null;
  }
  wsConnected = false;
}

function sendMessage(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

// Auto-connect on first import (lazy — only if WebSocket exists)
if (typeof WebSocket !== "undefined") {
  connect();

  // Hidden: ask the server to hold price ticks and scan notices. Visible: resume
  // (the server answers with all current prices), or reconnect if the socket
  // dropped (mobile wakes from sleep).
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      sendMessage({ type: "pause" });
    } else if (ws && ws.readyState === WebSocket.OPEN) {
      sendMessage({ type: "resume" });
    } else {
      reconnectAttempt = 0; // Reset backoff on manual focus
      connect();
    }
  });
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useWebSocket() {
  const [connected, setConnected] = useState(wsConnected);
  const [synthesisData, setSynthesisData] = useState(null);
  const [symbolUpdate, setSymbolUpdate] = useState(null);
  const [priceTicks, setPriceTicks] = useState(null);
  const [priceSnapshot, setPriceSnapshot] = useState(null);
  const [scanUpdated, setScanUpdated] = useState(null);
  const [transitions, setTransitions] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [insight, setInsight] = useState(null);
  const idRef = useRef(null);

  useEffect(() => {
    const id = ++listenerIdCounter;
    idRef.current = id;

    const handler = (msg) => {
      switch (msg.type) {
        case "_ws_status":
          setConnected(msg.connected);
          break;
        case "synthesis-complete":
          setSynthesisData(msg.data);
          break;
        case "symbol-update":
          setSymbolUpdate(msg.data);
          break;
        case "price-tick":
          setPriceTicks(msg.data);
          break;
        case "price-snapshot":
          setPriceSnapshot(msg.data);
          break;
        case "scan-updated":
          setScanUpdated({ at: Date.now(), ...(msg.data || {}) });
          break;
        case "signal-transition":
          setTransitions(msg.data || []);
          break;
        case "assistant-insight":
          setInsight(msg.data);
          break;
        case "anomaly":
          setAnomalies(msg.data || []);
          break;
        // heartbeat — no action needed
      }
    };

    const listener = { id, handler };
    listeners.add(listener);

    return () => {
      listeners.delete(listener);
      // If no listeners left, disconnect to save resources
      if (listeners.size === 0) {
        disconnect();
      }
    };
  }, []);

  const refresh = useCallback(() => {
    sendMessage({ type: "refresh" });
  }, []);

  return {
    connected,
    synthesisData,
    symbolUpdate,
    priceTicks,
    priceSnapshot,
    scanUpdated,
    transitions,
    anomalies,
    insight,
    refresh,
  };
}

export default useWebSocket;
