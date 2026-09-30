// Usage beacon: counts of page views and a few actions, for the owner's Intel page
// (backend usage_api.py). Events are queued and sent once a minute while the tab is visible,
// and once more when it is hidden. The first batch of a session goes through this site's own
// /u/beacon (frontend/vercel.json), which adds the visitor's country and city; the others go
// straight to the API. VITE_USAGE=0 turns it off. A browser holding the admin key (the owner's)
// is not counted.
import { getAdminKey, getSession, getToken } from "./auth.js";
import { MAX_BATCH, batchBody, randomId, rollSession, viewEvent } from "./utils/usage.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const ON = import.meta.env.VITE_USAGE !== "0" && typeof window !== "undefined";
const DIRECT = `${API_BASE}/api/usage/beacon`;
const VIA_SITE = "/u/beacon";
const KEY = "reflex_usage_session";
const EVERY_MS = 60_000;
const FIRST_MS = 10_000;

let queue = [];
let memorySession = null;
let started = false;
let firstTimer = 0;
let firstDone = false;       // the page's first batch goes out after 10 s, the rest once a minute

const readSession = () => {
  try { return JSON.parse(localStorage.getItem(KEY) || "null") || memorySession; } catch { return memorySession; }
};
const writeSession = s => {
  memorySession = s;
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* storage blocked */ }
};

function sendDirect(body) {
  try {
    if (navigator.sendBeacon && navigator.sendBeacon(DIRECT, new Blob([body], { type: "text/plain" }))) return;
  } catch { /* fall through */ }
  fetch(DIRECT, { method: "POST", body, keepalive: true, headers: { "Content-Type": "text/plain" } }).catch(() => {});
}

function sendViaSite(body, session) {
  fetch(VIA_SITE, { method: "POST", body, keepalive: true, headers: { "Content-Type": "text/plain" } })
    .then(r => {
      if (!r.ok || !(r.headers.get("content-type") || "").includes("json")) throw new Error("no rewrite");
      writeSession({ ...(readSession() || session), geo: true });
    })
    .catch(() => sendDirect(body));
}

function flush() {
  if (!queue.length) return;
  const events = queue.slice(0, MAX_BATCH);
  queue = queue.slice(MAX_BATCH);
  const session = rollSession(readSession(), Date.now(), randomId);
  writeSession(session);
  const body = batchBody({ token: getToken(), session: getSession(), sid: session.id, events });
  if (!session.geo && import.meta.env.PROD) sendViaSite(body, session);
  else sendDirect(body);
}

function start() {
  if (started) return;
  started = true;
  setInterval(() => { if (document.visibilityState === "visible") flush(); }, EVERY_MS);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(); });
  window.addEventListener("pagehide", flush);
}

// Record one event: a name the server knows and, for a few, a detail (see usage.py EVENTS).
export function track(name, detail = "") {
  if (!ON || getAdminKey()) return;
  start();
  queue.push([name, detail]);
  if (queue.length >= MAX_BATCH) flush();
  else if (!firstDone && !firstTimer) firstTimer = setTimeout(() => { firstDone = true; flush(); }, FIRST_MS);
}

// Record a page view for a path (App calls this when the path changes).
export function trackView(pathname) {
  const ev = viewEvent(pathname);
  if (ev) track(ev[0], ev[1]);
}
