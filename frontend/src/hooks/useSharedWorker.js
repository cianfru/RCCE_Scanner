import { getToken, logout } from "../auth.js";
import { EDGE_ALLOWED } from "../edge.js";
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
// The last message of each data type, replayed to a listener that subscribes after it arrived.
const lastByType = new Map();

function initWorker() {
  if (worker !== null || typeof SharedWorker === "undefined") return;
  try {
    worker = new SharedWorker("/shared-worker.js");
    workerPort = worker.port;
    workerSupported = true;

    workerPort.onmessage = (event) => {
      if (event.data?.type === "auth-expired") { logout(); return; }
      if (event.data?.type) lastByType.set(event.data.type, event.data);
      for (const listener of listeners) {
        try {
          listener.handler(event.data);
        } catch (_) {}
      }
    };

    workerPort.start();
    workerPort.postMessage({ type: "connect", apiBase: API_BASE, token: getToken(), hidden: document.hidden, edge: EDGE_ALLOWED });

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

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useSharedWorker() {
  // Starts on the first render of a component that uses it (the app), never at
  // import time, so a page that only imports the module starts no polling.
  // Idempotent; runs during render so `supported` is right on that first render.
  initWorker();
  const [mainData, setMainData] = useState(null);
  const [notifData, setNotifData] = useState(null);
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
      }
    };

    const listener = { id, handler };
    listeners.add(listener);
    for (const msg of lastByType.values()) handler(msg);

    return () => {
      listeners.delete(listener);
    };
  }, []);

  const send = useCallback((message) => {
    if (workerPort) {
      workerPort.postMessage(message);
    }
  }, []);

  // `version`: the scan pass a notice announced (the CDN URL carries it; see shared-worker.js).
  const refresh = useCallback((version) => send({ type: "refresh", version: Number.isFinite(version) ? version : undefined }), [send]);
  const refreshNotifications = useCallback(() => send({ type: "refresh-notifications" }), [send]);
  const setWallet = useCallback((address) => send({ type: "set-wallet", address }), [send]);
  const setNotifParams = useCallback((minScore) => send({ type: "set-notif-params", minScore }), [send]);
  const setFilters = useCallback((regime, signal) => send({ type: "set-filters", regime, signal }), [send]);
  // Which feeds this tab's page shows (utils/feedNeeds.js); the worker polls only those.
  const setNeeds = useCallback((needs) => send({ type: "set-needs", needs }), [send]);

  return {
    supported: workerSupported,
    mainData,
    notifData,
    refresh,
    refreshNotifications,
    setWallet,
    setNotifParams,
    setFilters,
    setNeeds,
    send,
  };
}

export default useSharedWorker;
