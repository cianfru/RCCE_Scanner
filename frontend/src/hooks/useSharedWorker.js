/**
 * useSharedWorker — React hook for the RCCE SharedWorker.
 *
 * Singleton pattern: all components share one worker connection.
 * Falls back gracefully when SharedWorker is unavailable (Safari).
 */

import { useState, useEffect, useCallback, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Singleton worker instance ────────────────────────────────────────────────

let worker = null;
let workerPort = null;
let workerSupported = false;
let listeners = new Set(); // { id, handler }
let listenerIdCounter = 0;
let connected = false;

function initWorker() {
  if (worker !== null || typeof SharedWorker === "undefined") return;
  try {
    worker = new SharedWorker("/shared-worker.js");
    workerPort = worker.port;
    workerSupported = true;

    workerPort.onmessage = (event) => {
      for (const listener of listeners) {
        try {
          listener.handler(event.data);
        } catch (_) {}
      }
    };

    workerPort.start();
    workerPort.postMessage({ type: "connect", apiBase: API_BASE });

    // Visibility forwarding
    document.addEventListener("visibilitychange", () => {
      workerPort.postMessage({ type: "visibility", hidden: document.hidden });
    });
  } catch (_) {
    worker = null;
    workerPort = null;
    workerSupported = false;
  }
}

// Try to init immediately on module load
initWorker();

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useSharedWorker() {
  const [mainData, setMainData] = useState(null);
  const [notifData, setNotifData] = useState(null);
  const [onchainData, setOnchainData] = useState(null);
  const idRef = useRef(null);

  useEffect(() => {
    if (!workerSupported) return;

    const id = ++listenerIdCounter;
    idRef.current = id;

    const handler = (msg) => {
      switch (msg.type) {
        case "main-data":
          setMainData(msg.payload);
          break;
        case "notif-data":
          setNotifData(msg.payload);
          break;
        case "onchain-data":
          setOnchainData(msg.payload);
          break;
      }
    };

    const listener = { id, handler };
    listeners.add(listener);

    return () => {
      listeners.delete(listener);
    };
  }, []);

  const send = useCallback((message) => {
    if (workerPort) {
      workerPort.postMessage(message);
    }
  }, []);

  const refresh = useCallback(() => send({ type: "refresh" }), [send]);
  const refreshNotifications = useCallback(() => send({ type: "refresh-notifications" }), [send]);
  const setWallet = useCallback((address) => send({ type: "set-wallet", address }), [send]);
  const setNotifParams = useCallback((minScore) => send({ type: "set-notif-params", minScore }), [send]);
  const setFilters = useCallback((regime, signal) => send({ type: "set-filters", regime, signal }), [send]);
  const setOnchainToken = useCallback((token) => send({ type: "set-onchain-token", token }), [send]);

  return {
    supported: workerSupported,
    mainData,
    notifData,
    onchainData,
    refresh,
    refreshNotifications,
    setWallet,
    setNotifParams,
    setFilters,
    setOnchainToken,
    send,
  };
}

export default useSharedWorker;
