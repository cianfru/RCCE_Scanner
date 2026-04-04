/**
 * RCCE Scanner — SharedWorker
 *
 * Single polling loop shared across all browser tabs.
 * Tabs connect via port, worker broadcasts fetched data.
 * Falls back gracefully (tabs do their own polling) when unsupported.
 */

// ── State ────────────────────────────────────────────────────────────────────

const ports = new Set();
let apiBase = "";

// Visibility tracking — pause when ALL tabs are hidden
const tabVisibility = new Map(); // portId → boolean (true = visible)
let portIdCounter = 0;

// Poll intervals (ms)
const MAIN_INTERVAL = 60_000;
const NOTIF_INTERVAL = 60_000;
const ONCHAIN_INTERVAL = 15_000;

let mainTimer = null;
let notifTimer = null;
let onchainTimer = null;

// Latest data cache — new tabs get data immediately on connect
let latestMain = null;
let latestNotif = null;
let latestOnchain = null;

// Per-tab params (use latest values from any tab)
let walletAddress = "";
let notifMinScore = 3; // "HIGH" default
let onchainActiveToken = null; // { chain, contract }
let filterRegime = "ALL";
let filterSignal = "ALL";

// ── Helpers ──────────────────────────────────────────────────────────────────

function broadcast(message) {
  for (const port of ports) {
    try {
      port.postMessage(message);
    } catch (_) {
      ports.delete(port);
    }
  }
}

function anyTabVisible() {
  if (tabVisibility.size === 0) return true; // no visibility info = assume visible
  for (const visible of tabVisibility.values()) {
    if (visible) return true;
  }
  return false;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Main data polling ────────────────────────────────────────────────────────

async function pollMain() {
  if (!apiBase) return;
  try {
    const params4h = new URLSearchParams({ timeframe: "4h" });
    const params1d = new URLSearchParams({ timeframe: "1d" });
    if (filterRegime !== "ALL") {
      params4h.append("regime", filterRegime);
      params1d.append("regime", filterRegime);
    }
    if (filterSignal !== "ALL") {
      params4h.append("signal", filterSignal);
      params1d.append("signal", filterSignal);
    }

    const [r4h, r1d] = await Promise.all([
      fetchJSON(`${apiBase}/api/scan?${params4h}`),
      fetchJSON(`${apiBase}/api/scan?${params1d}`),
    ]);

    // Secondary metrics — fail silently
    let gm = null, as = null, sent = null, stable = null, tf4h = null, tf1d = null, macroData = null;
    try {
      [gm, as, sent, stable, tf4h, tf1d, macroData] = await Promise.all([
        fetchJSON(`${apiBase}/api/global-metrics`).catch(() => null),
        fetchJSON(`${apiBase}/api/alt-season?timeframe=1d`).catch(() => null),
        fetchJSON(`${apiBase}/api/sentiment`).catch(() => null),
        fetchJSON(`${apiBase}/api/stablecoin`).catch(() => null),
        fetchJSON(`${apiBase}/api/tradfi?timeframe=4h`).catch(() => null),
        fetchJSON(`${apiBase}/api/tradfi?timeframe=1d`).catch(() => null),
        fetchJSON(`${apiBase}/api/coinglass/macro`).catch(() => null),
      ]);
    } catch (_) {}

    latestMain = {
      r4h, r1d,
      globalMetrics: gm,
      altSeason: as,
      sentiment: sent,
      stablecoin: stable,
      tradfi4h: tf4h,
      tradfi1d: tf1d,
      macro: macroData,
      timestamp: Date.now(),
    };

    broadcast({ type: "main-data", payload: latestMain });
  } catch (e) {
    broadcast({ type: "error", source: "main", message: e.message });
  }
}

// ── Notification polling ─────────────────────────────────────────────────────

async function pollNotifications() {
  if (!apiBase) return;
  try {
    const fetches = [
      fetchJSON(`${apiBase}/api/notifications?limit=10`).catch(() => ({ events: [] })),
      fetchJSON(`${apiBase}/api/notifications/anomalies`).catch(() => ({ anomalies: [] })),
    ];

    // Wallet-dependent endpoints
    if (walletAddress) {
      fetches.push(
        fetchJSON(`${apiBase}/api/notifications/position-warnings?address=${walletAddress}`).catch(() => ({ warnings: [] }))
      );
      fetches.push(
        fetchJSON(`${apiBase}/api/notifications/exhaustion-opportunities?address=${walletAddress}`).catch(() => ({ opportunities: [] }))
      );
      fetches.push(
        fetchJSON(`${apiBase}/api/notifications/market-setups?address=${walletAddress}&min_score=${notifMinScore}`).catch(() => ({ setups: [] }))
      );
    } else {
      fetches.push(Promise.resolve({ warnings: [] }));
      fetches.push(
        fetchJSON(`${apiBase}/api/notifications/exhaustion-opportunities`).catch(() => ({ opportunities: [] }))
      );
      fetches.push(
        fetchJSON(`${apiBase}/api/notifications/market-setups?min_score=${notifMinScore}`).catch(() => ({ setups: [] }))
      );
    }

    const [notifs, anomalies, warnings, exhaustion, setups] = await Promise.all(fetches);

    latestNotif = {
      events: notifs.events || [],
      anomalies: anomalies.anomalies || [],
      warnings: warnings.warnings || [],
      exhaustionOpps: exhaustion.opportunities || [],
      marketSetups: setups.setups || [],
      timestamp: Date.now(),
    };

    broadcast({ type: "notif-data", payload: latestNotif });
  } catch (e) {
    broadcast({ type: "error", source: "notif", message: e.message });
  }
}

// ── On-chain polling ─────────────────────────────────────────────────────────

async function pollOnchain() {
  if (!apiBase) return;
  try {
    const baseFetches = [
      fetchJSON(`${apiBase}/api/whales/status`).catch(() => null),
      fetchJSON(`${apiBase}/api/whales/tokens`).catch(() => []),
      fetchJSON(`${apiBase}/api/whales/alerts?limit=30`).catch(() => []),
      fetchJSON(`${apiBase}/api/whales/trending`).catch(() => []),
    ];

    const [status, tokens, alerts, trending] = await Promise.all(baseFetches);

    // Per-token data if an active token is set
    let holdersData = null;
    let transfers = [];
    let tokenAlerts = [];

    if (onchainActiveToken) {
      const { chain, contract } = onchainActiveToken;
      const enc = encodeURIComponent(contract);
      try {
        [holdersData, transfers, tokenAlerts] = await Promise.all([
          fetchJSON(`${apiBase}/api/whales/holders/${chain}/${enc}?min_pct=0.4&limit=50`).catch(() => null),
          fetchJSON(`${apiBase}/api/whales/transfers?chain=${chain}&contract=${enc}&limit=50`).catch(() => []),
          fetchJSON(`${apiBase}/api/whales/alerts?contract=${enc}&limit=20`).catch(() => []),
        ]);
      } catch (_) {}
    }

    latestOnchain = {
      status, tokens, alerts, trending,
      holdersData, transfers, tokenAlerts,
      activeContract: onchainActiveToken?.contract || null,
      timestamp: Date.now(),
    };

    broadcast({ type: "onchain-data", payload: latestOnchain });
  } catch (e) {
    broadcast({ type: "error", source: "onchain", message: e.message });
  }
}

// ── Timer management ─────────────────────────────────────────────────────────

function startPolling() {
  stopPolling();

  // Initial fetch
  pollMain();
  pollNotifications();
  pollOnchain();

  mainTimer = setInterval(() => {
    if (anyTabVisible()) pollMain();
  }, MAIN_INTERVAL);

  notifTimer = setInterval(() => {
    if (anyTabVisible()) pollNotifications();
  }, NOTIF_INTERVAL);

  onchainTimer = setInterval(() => {
    if (anyTabVisible()) pollOnchain();
  }, ONCHAIN_INTERVAL);
}

function stopPolling() {
  if (mainTimer) { clearInterval(mainTimer); mainTimer = null; }
  if (notifTimer) { clearInterval(notifTimer); notifTimer = null; }
  if (onchainTimer) { clearInterval(onchainTimer); onchainTimer = null; }
}

// ── Port handling ────────────────────────────────────────────────────────────

self.onconnect = function (e) {
  const port = e.ports[0];
  const portId = ++portIdCounter;
  ports.add(port);
  tabVisibility.set(portId, true);

  port.onmessage = function (event) {
    const msg = event.data;

    switch (msg.type) {
      case "connect":
        if (msg.apiBase && !apiBase) {
          apiBase = msg.apiBase;
          startPolling();
        }
        // Send cached data immediately so new tab doesn't wait for next poll
        if (latestMain) port.postMessage({ type: "main-data", payload: latestMain });
        if (latestNotif) port.postMessage({ type: "notif-data", payload: latestNotif });
        if (latestOnchain) port.postMessage({ type: "onchain-data", payload: latestOnchain });
        break;

      case "refresh":
        // Immediate re-fetch (e.g., user clicked refresh or triggered scan)
        pollMain();
        break;

      case "refresh-notifications":
        pollNotifications();
        break;

      case "set-wallet":
        if (msg.address !== walletAddress) {
          walletAddress = msg.address || "";
          pollNotifications(); // re-fetch with new wallet
        }
        break;

      case "set-notif-params":
        if (msg.minScore !== undefined && msg.minScore !== notifMinScore) {
          notifMinScore = msg.minScore;
          pollNotifications();
        }
        break;

      case "set-filters":
        if (msg.regime !== undefined) filterRegime = msg.regime;
        if (msg.signal !== undefined) filterSignal = msg.signal;
        pollMain(); // re-fetch with new filters
        break;

      case "set-onchain-token":
        const newToken = msg.token; // { chain, contract } or null
        const changed = JSON.stringify(newToken) !== JSON.stringify(onchainActiveToken);
        if (changed) {
          onchainActiveToken = newToken;
          pollOnchain();
        }
        break;

      case "visibility":
        tabVisibility.set(portId, !msg.hidden);
        // If a tab just became visible and we were paused, poll immediately
        if (!msg.hidden && anyTabVisible()) {
          pollMain();
          pollNotifications();
          pollOnchain();
        }
        break;

      case "disconnect":
        ports.delete(port);
        tabVisibility.delete(portId);
        if (ports.size === 0) {
          stopPolling();
        }
        break;
    }
  };

  // Handle port closing (tab closed without sending disconnect)
  port.onmessageerror = function () {
    ports.delete(port);
    tabVisibility.delete(portId);
    if (ports.size === 0) stopPolling();
  };

  port.start();
};
