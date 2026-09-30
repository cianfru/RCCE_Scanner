// Heavy read-only feeds through the CDN (backend/edge.py): the same URL on this site's own
// host, /edge/api/..., which vercel.json rewrites to the API and the CDN caches for everyone.
// The API says whether this is on (/api/edge/key) and gives the key these URLs carry; when it
// is off, unavailable or answers oddly, requests go straight to the API as before.
// VITE_EDGE_CACHE=0 at build time turns it off in the page as well.
import { edgePath, withEdgeKey } from "./utils/edgeUrl.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const EDGE_ALLOWED = import.meta.env.VITE_EDGE_CACHE !== "0";

let config = null;        // { prefix, key, expiresAt } while on
let checkedAt = 0;
let pending = null;
let broken = false;       // the rewrite answered with something other than the API

const RECHECK_MS = 10 * 60 * 1000;

async function loadConfig() {
  try {
    const res = await fetch(`${API_BASE}/api/edge/key`, { cache: "no-store" });
    const body = res.ok ? await res.json() : null;
    config = body?.enabled && body.key ? { prefix: body.prefix || "/edge", key: body.key, expiresAt: (body.expires_at || 0) * 1000 } : null;
  } catch {
    config = null;
  }
  checkedAt = Date.now();
  pending = null;
  return config;
}

export async function edgeConfig() {
  if (!EDGE_ALLOWED || broken) return null;
  const now = Date.now();
  const expired = config && config.expiresAt && now > config.expiresAt - 5 * 60 * 1000;
  if (!expired && checkedAt && now - checkedAt < RECHECK_MS) return config;
  return pending || (pending = loadConfig());
}

function directUrl(path) {
  return `${API_BASE}${path}`;
}

// GET an API path ("/api/scan?timeframe=4h"): through the CDN when it is an edge feed and the
// API has it on, otherwise directly. Any trouble on the edge path falls back to a direct call.
export async function apiFetch(path, init) {
  const cfg = edgePath(path) ? await edgeConfig() : null;
  if (cfg) {
    try {
      const res = await fetch(withEdgeKey(`${cfg.prefix}${path}`, cfg.key), init);
      const json = (res.headers.get("content-type") || "").includes("application/json");
      if ((res.ok && json) || res.status === 304 || res.status === 404 || res.status === 429) return res;
      if (res.ok && !json) broken = true;              // the rewrite is not deployed here
      if (res.status === 401) checkedAt = 0;           // the key rolled over: ask for a new one
    } catch {
      /* network trouble on the edge path: go direct */
    }
  }
  return fetch(directUrl(path), init);
}

export async function apiJson(path, init) {
  const res = await apiFetch(path, init);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
