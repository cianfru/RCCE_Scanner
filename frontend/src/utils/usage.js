// Usage beacon, the pure parts (tested in usage.test.js). The sender lives in ../usage.js;
// the backend is usage_api.py, which keeps only the event names it knows.

export const MAX_BATCH = 50;
export const SESSION_GAP_MS = 30 * 60 * 1000;   // a new session after 30 minutes without events

const OTHER_PAGES = {
  "/signals": "signals", "/analytics": "analytics", "/tradfi": "tradfi", "/bridge": "bridge", "/ai": "ai",
  "/backtest": "backtest", "/executor": "executor", "/portfolio": "portfolio", "/settings": "settings",
};

// The view event for a path, or null (the Intel page and unknown paths are not counted).
export function viewEvent(pathname) {
  const p = String(pathname || "").replace(/\/+$/, "") || "/";
  if (p === "/scanner") return ["view_scanner", ""];
  if (/^\/scanner\/[^/]+$/.test(p)) return ["view_coin", ""];
  if (p === "/radar") return ["view_radar", ""];
  if (p === "/traders" || p === "/traders/leaderboard" || p === "/hyperlens") return ["view_traders", ""];
  if (/^\/trader\/0x[0-9a-fA-F]{40}$/.test(p)) return ["view_trader", ""];
  if (OTHER_PAGES[p]) return ["view_page", OTHER_PAGES[p]];
  return null;
}

// The session this event belongs to: the previous one while it is fresh, else a new one.
// `geo` records that this session's location has been sent (its first batch went through the site).
export function rollSession(prev, now, newId) {
  if (prev && typeof prev.id === "string" && Number.isFinite(prev.last) && now - prev.last < SESSION_GAP_MS && now >= prev.last) {
    return { ...prev, last: now };
  }
  return { id: newId(), last: now, geo: false };
}

export function randomId() {
  const bytes = new Uint8Array(8);
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
  else for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
  return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
}

// One batch body: the access token and wallet session (so the server can attribute it without
// headers, which sendBeacon cannot send), the session id and at most MAX_BATCH events.
export function batchBody({ token, session, sid, events }) {
  const body = { sid, e: events.slice(0, MAX_BATCH) };
  if (token) body.t = token;
  if (session) body.s = session;
  return JSON.stringify(body);
}
