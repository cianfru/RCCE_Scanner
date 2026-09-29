/**
 * RCCE Scanner — SharedWorker
 *
 * Single polling loop shared across all browser tabs.
 * Tabs connect via port, worker broadcasts fetched data.
 * Falls back gracefully (tabs do their own polling) when unsupported.
 *
 * Egress (the server's bill is mostly data sent):
 *  - each tab says which feeds its page shows ("set-needs"); only the union over
 *    visible tabs is polled. Every feed is loaded once at start so switching
 *    pages shows data at once, then refreshed the moment a page needs it.
 *  - requests are conditional (If-None-Match); an unchanged feed costs an empty
 *    304 and is not re-broadcast.
 *  - a tab asks for "refresh" when the server announces a new scan, so the
 *    minute timer is only a fallback.
 */

// ── State ────────────────────────────────────────────────────────────────────

const ports = new Set();
let apiBase = "";
let token = null;   // API token from the page (see src/auth.js)

// Visibility tracking — pause when ALL tabs are hidden
const tabVisibility = new Map(); // portId → boolean (true = visible)
const tabNeeds = new Map();      // portId → { scan: ["1d"], tradfi, sentiment }
let portIdCounter = 0;

// Poll intervals (ms)
const MAIN_INTERVAL = 60_000;
const NOTIF_INTERVAL = 60_000;
const SENTIMENT_INTERVAL = 300_000;   // Fear & Greed moves once a day

const SCAN_TFS = ["4h", "1d"];
// A tab that has not said what it shows (an older page) gets everything, as before.
const DEFAULT_NEEDS = { scan: SCAN_TFS, tradfi: true, sentiment: true };

let mainTimer = null;
let notifTimer = null;

// Latest data cache — new tabs get data immediately on connect
let latestMain = null;
let latestNotif = null;

// Per feed: when it last loaded (feeds never loaded are fetched on the next poll)
const feedLoadedAt = new Map();
// Per URL: { etag, data } for conditional requests
const etagCache = new Map();

// Per-tab params (use latest values from any tab)
let walletAddress = "";
let notifMinScore = 3; // "HIGH" default
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

// The feeds any visible tab shows.
function unionNeeds(needsByPort, visibleByPort) {
  const out = { scan: new Set(), tradfi: false, sentiment: false };
  for (const [id, visible] of visibleByPort) {
    if (!visible) continue;
    const n = needsByPort.get(id) || DEFAULT_NEEDS;
    for (const tf of n.scan || []) out.scan.add(tf);
    if (n.tradfi) out.tradfi = true;
    if (n.sentiment) out.sentiment = true;
  }
  return out;
}

// Feed keys to fetch now: what is shown (sentiment at its own slower pace), plus anything never loaded.
function planMainFetches(needs, loadedAt, now) {
  const feeds = [];
  for (const tf of SCAN_TFS) {
    const key = `scan:${tf}`;
    if (needs.scan.has(tf) || !loadedAt.has(key)) feeds.push(key);
  }
  for (const tf of SCAN_TFS) {
    const key = `tradfi:${tf}`;
    if (needs.tradfi || !loadedAt.has(key)) feeds.push(key);
  }
  const sentAt = loadedAt.get("sentiment");
  if (sentAt === undefined || (needs.sentiment && now - sentAt >= SENTIMENT_INTERVAL)) feeds.push("sentiment");
  return feeds;
}

// True when `after` shows a feed `before` did not (a page switch that needs fresh data now).
function needsGrew(before, after) {
  for (const tf of after.scan) if (!before.scan.has(tf)) return true;
  return (after.tradfi && !before.tradfi) || (after.sentiment && !before.sentiment);
}

function feedUrl(feed) {
  const [kind, tf] = feed.split(":");
  if (kind === "sentiment") return `${apiBase}/api/sentiment`;
  const params = new URLSearchParams({ timeframe: tf });
  if (kind === "scan") {
    if (filterRegime !== "ALL") params.append("regime", filterRegime);
    if (filterSignal !== "ALL") params.append("signal", filterSignal);
    return `${apiBase}/api/scan?${params}`;
  }
  return `${apiBase}/api/tradfi?${params}`;
}

// GET with If-None-Match. Resolves { data, changed }; a 304 returns the kept copy.
async function fetchConditional(url) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const kept = etagCache.get(url);
  if (kept) headers["If-None-Match"] = kept.etag;
  const res = await fetch(url, { headers });
  if (res.status === 304 && kept) return { data: kept.data, changed: false };
  if (res.status === 401) { token = null; broadcast({ type: "auth-expired" }); }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const etag = res.headers.get("ETag");
  if (etag) etagCache.set(url, { etag, data });
  else etagCache.delete(url);
  return { data, changed: true };
}

async function fetchJSON(url) {
  return (await fetchConditional(url)).data;
}

// ── Main data polling ────────────────────────────────────────────────────────

let mainInFlight = null;
let mainAgain = false;

function scheduleMain() {
  if (mainTimer) clearTimeout(mainTimer);
  mainTimer = setTimeout(() => {
    mainTimer = null;
    if (anyTabVisible()) pollMain();
    else scheduleMain();
  }, MAIN_INTERVAL);
}

// One poll at a time; requests arriving meanwhile (several tabs hearing the same
// scan notice) fold into a single follow-up poll.
function pollMain() {
  if (!apiBase) return Promise.resolve();
  if (mainInFlight) { mainAgain = true; return mainInFlight; }
  scheduleMain();
  mainInFlight = pollMainOnce().finally(() => {
    mainInFlight = null;
    if (mainAgain) { mainAgain = false; pollMain(); }
  });
  return mainInFlight;
}

async function pollMainOnce() {
  const now = Date.now();
  const feeds = planMainFetches(unionNeeds(tabNeeds, tabVisibility), feedLoadedAt, now);
  if (!feeds.length) return;
  const results = await Promise.all(feeds.map(feed =>
    fetchConditional(feedUrl(feed)).then(r => ({ feed, r }), err => ({ feed, err }))));

  const next = { ...(latestMain || {}) };
  let changed = false, scanChanged = false, scanError = null;
  for (const { feed, r, err } of results) {
    if (err) {
      if (feed.startsWith("scan:")) scanError = err;
      continue;
    }
    feedLoadedAt.set(feed, now);
    if (!r.changed && latestMain) continue;
    changed = true;
    if (feed === "scan:4h") next.r4h = r.data;
    else if (feed === "scan:1d") next.r1d = r.data;
    else if (feed === "tradfi:4h") next.tradfi4h = r.data;
    else if (feed === "tradfi:1d") next.tradfi1d = r.data;
    else if (feed === "sentiment") next.sentiment = r.data;
    if (feed.startsWith("scan:")) {
      scanChanged = true;
      // Scan time = received minus its age; same pass for both timeframes.
      next.timestamp = now;
      next.cacheAge = r.data?.cache_age_seconds ?? null;
    }
  }
  if (scanError && !scanChanged) {
    broadcast({ type: "error", source: "main", message: scanError.message });
  }
  if (!changed) return;
  if (next.timestamp == null) next.timestamp = now;
  latestMain = next;
  broadcast({ type: "main-data", payload: latestMain });
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

// ── Timer management ─────────────────────────────────────────────────────────

function startPolling() {
  stopPolling();

  // Initial fetch (schedules the next main poll itself)
  pollMain();
  pollNotifications();

  notifTimer = setInterval(() => {
    if (anyTabVisible()) pollNotifications();
  }, NOTIF_INTERVAL);
}

function stopPolling() {
  if (mainTimer) { clearTimeout(mainTimer); mainTimer = null; }
  if (notifTimer) { clearInterval(notifTimer); notifTimer = null; }
}

// ── Port handling ────────────────────────────────────────────────────────────

function dropPort(port, portId) {
  ports.delete(port);
  tabVisibility.delete(portId);
  tabNeeds.delete(portId);
  if (ports.size === 0) stopPolling();
}

self.onconnect = function (e) {
  const port = e.ports[0];
  const portId = ++portIdCounter;
  ports.add(port);
  tabVisibility.set(portId, true);

  port.onmessage = function (event) {
    const msg = event.data;

    switch (msg.type) {
      case "connect":
        if (msg.token) token = msg.token;
        if (msg.hidden !== undefined) tabVisibility.set(portId, !msg.hidden);
        if (msg.apiBase && !apiBase) {
          apiBase = msg.apiBase;
          startPolling();
        }
        // Send cached data immediately so new tab doesn't wait for next poll
        if (latestMain) port.postMessage({ type: "main-data", payload: latestMain });
        if (latestNotif) port.postMessage({ type: "notif-data", payload: latestNotif });
        break;

      case "set-needs": {
        const before = unionNeeds(tabNeeds, tabVisibility);
        tabNeeds.set(portId, msg.needs || DEFAULT_NEEDS);
        if (needsGrew(before, unionNeeds(tabNeeds, tabVisibility))) pollMain();
        break;
      }

      case "refresh":
        // Immediate re-fetch (a new scan was announced, or the user triggered one)
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

      case "set-filters": {
        const changed = (msg.regime !== undefined && msg.regime !== filterRegime)
          || (msg.signal !== undefined && msg.signal !== filterSignal);
        if (msg.regime !== undefined) filterRegime = msg.regime;
        if (msg.signal !== undefined) filterSignal = msg.signal;
        if (changed) {
          for (const tf of SCAN_TFS) feedLoadedAt.delete(`scan:${tf}`);
          pollMain(); // re-fetch with new filters
        }
        break;
      }

      case "visibility":
        tabVisibility.set(portId, !msg.hidden);
        // If a tab just became visible and we were paused, poll immediately
        if (!msg.hidden && anyTabVisible()) {
          pollMain();
          pollNotifications();
        }
        break;

      case "disconnect":
        dropPort(port, portId);
        break;
    }
  };

  // Handle port closing (tab closed without sending disconnect)
  port.onmessageerror = function () {
    dropPort(port, portId);
  };

  port.start();
};
