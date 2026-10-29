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
 *  - the scan list comes without per-coin detail and without sparklines
 *    (?view=list); the sparklines have their own feed, which changes only when a
 *    candle closes, and are merged back in here (backend/scan_view.py).
 *  - when the API turns it on (/api/edge/key), the CDN feeds go through this
 *    site's /edge path, cached for everyone (backend/edge.py); any trouble there
 *    falls back to the API directly. The scan URL carries the pass it asks for, so
 *    a scan notice never gets an older copy.
 */

// ── State ────────────────────────────────────────────────────────────────────

const ports = new Set();
let apiBase = "";
let token = null;   // API token from the page (see src/auth.js)

// CDN feeds (keep in step with src/utils/edgeUrl.js and backend/edge.py).
const EDGE_PATHS = new Set(["/api/scan", "/api/scan/sparklines", "/api/scan/row", "/api/setup-map",
  "/api/market-history", "/api/market-history/spark", "/api/market-history/wallets", "/api/market-history/derive", "/api/market-history/funding",
  "/api/market-history/forward",
  "/api/hyperlens/consensus",
  "/api/hyperlens/positioning",
  "/api/traders/leaderboard", "/api/tradfi", "/api/universe", "/api/sectors",
  "/api/portfolio/context", "/api/portfolio/events"]);
let edgeAllowed = false;     // the page allows it (VITE_EDGE_CACHE)
let edgeCfg = null;          // { prefix, key, expiresAt } while the API has it on
let edgeCheckedAt = 0;
let edgePending = null;
let edgeBroken = false;      // the /edge path answered with something other than the API
let scanVersion = null;      // the scan pass the last notice announced

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

// API path of a main feed (the scan list's sparklines are fetched next to it, see fetchFeed).
function feedPath(feed) {
  const [kind, tf] = feed.split(":");
  if (kind === "sentiment") return "/api/sentiment";
  const params = new URLSearchParams({ timeframe: tf });
  if (kind === "scan") {
    params.append("view", "list");
    if (filterRegime !== "ALL") params.append("regime", filterRegime);
    if (filterSignal !== "ALL") params.append("signal", filterSignal);
    return `/api/scan?${params}`;
  }
  return `/api/tradfi?${params}`;
}

function isEdgePath(path) {
  return EDGE_PATHS.has(path.split("?")[0]);
}

// Whether the API has the CDN path on, and the key its URLs carry (asked again every 10 minutes).
async function edgeConfig() {
  if (!edgeAllowed || edgeBroken || !apiBase) return null;
  const now = Date.now();
  const expiring = edgeCfg && edgeCfg.expiresAt && now > edgeCfg.expiresAt - 300_000;
  if (!expiring && edgeCheckedAt && now - edgeCheckedAt < 600_000) return edgeCfg;
  if (!edgePending) {
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    edgePending = fetch(`${apiBase}/api/edge/key`, { headers, cache: "no-store" })
      .then(r => (r.ok ? r.json() : null))
      .then(b => (b && b.enabled && b.key ? { prefix: b.prefix || "/edge", key: b.key, expiresAt: (b.expires_at || 0) * 1000 } : null))
      .catch(() => null)
      .then(cfg => { edgeCfg = cfg; edgeCheckedAt = Date.now(); edgePending = null; return cfg; });
  }
  return edgePending;
}

function edgeUrl(cfg, path, version) {
  let url = `${cfg.prefix}${path}`;
  const add = (k, v) => { url += `${url.includes("?") ? "&" : "?"}${k}=${encodeURIComponent(v)}`; };
  if (version != null) add("v", version);
  add("k", cfg.key);
  return url;
}

// GET with If-None-Match. Resolves { data, changed }; a 304 returns the kept copy.
// `edge` requests carry no token (the CDN URL holds the key) and throw on anything odd,
// so the caller can go to the API directly instead.
async function fetchConditional(url, edge = false) {
  const headers = {};
  if (token && !edge) headers.Authorization = `Bearer ${token}`;
  const kept = etagCache.get(url);
  if (kept) headers["If-None-Match"] = kept.etag;
  const res = await fetch(url, { headers });
  if (res.status === 304 && kept) return { data: kept.data, changed: false };
  if (edge) {
    const ctype = (res.headers.get("content-type") || "").toLowerCase();
    if (res.status === 401) edgeCheckedAt = 0;                         // a new key next time
    if (res.ok && ctype && !ctype.includes("json")) edgeBroken = true;  // not deployed here
    if (!res.ok || (ctype && !ctype.includes("json"))) throw new Error(`edge ${res.status}`);
  }
  if (res.status === 401) { token = null; broadcast({ type: "auth-expired" }); }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const etag = res.headers.get("ETag");
  if (etag) etagCache.set(url, { etag, data });
  else etagCache.delete(url);
  return { data, changed: true };
}

// An API path through the CDN when it is a CDN feed and the API has it on; otherwise directly.
async function fetchPath(path, version) {
  const cfg = isEdgePath(path) ? await edgeConfig() : null;
  if (cfg) {
    try {
      return await fetchConditional(edgeUrl(cfg, path, version), true);
    } catch (_) {
      /* fall through to the API */
    }
  }
  return fetchConditional(`${apiBase}${path}`);
}

// Rows of the list view get their sparklines back by symbol.
function mergeSparklines(rows, sparks) {
  if (!Array.isArray(rows)) return rows;
  const map = sparks && typeof sparks === "object" ? sparks : {};
  return rows.map(r => (r && r.sparkline === undefined ? { ...r, sparkline: map[r.symbol] || [] } : r));
}

// One main feed. A scan is its list plus its sparklines; it changed when either did.
async function fetchFeed(feed) {
  const path = feedPath(feed);
  if (!feed.startsWith("scan:")) return fetchPath(path);
  const tf = feed.split(":")[1];
  const [list, spark] = await Promise.all([
    fetchPath(path, scanVersion),
    fetchPath(`/api/scan/sparklines?timeframe=${tf}`).catch(() => null),
  ]);
  const data = { ...list.data, results: mergeSparklines(list.data?.results, spark?.data?.sparklines) };
  return { data, changed: list.changed || !!(spark && spark.changed) };
}

async function fetchJSON(path) {
  return (await fetchPath(path)).data;
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
    fetchFeed(feed).then(r => ({ feed, r }), err => ({ feed, err }))));

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
      fetchJSON(`/api/notifications?limit=10`).catch(() => ({ events: [] })),
      fetchJSON(`/api/notifications/anomalies`).catch(() => ({ anomalies: [] })),
    ];

    // Wallet-dependent endpoints
    if (walletAddress) {
      fetches.push(
        fetchJSON(`/api/notifications/position-warnings?address=${walletAddress}`).catch(() => ({ warnings: [] }))
      );
      fetches.push(
        fetchJSON(`/api/notifications/exhaustion-opportunities?address=${walletAddress}`).catch(() => ({ opportunities: [] }))
      );
      fetches.push(
        fetchJSON(`/api/notifications/market-setups?address=${walletAddress}&min_score=${notifMinScore}`).catch(() => ({ setups: [] }))
      );
    } else {
      fetches.push(Promise.resolve({ warnings: [] }));
      fetches.push(
        fetchJSON(`/api/notifications/exhaustion-opportunities`).catch(() => ({ opportunities: [] }))
      );
      fetches.push(
        fetchJSON(`/api/notifications/market-setups?min_score=${notifMinScore}`).catch(() => ({ setups: [] }))
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
        if (msg.edge !== undefined) edgeAllowed = !!msg.edge;
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
        if (msg.version != null) scanVersion = msg.version;
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
