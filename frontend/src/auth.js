// Server-side access (backend/access.py). The token from /api/auth/login rides on
// every API request; a 401 sends the user back to the login screen.
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TOKEN_KEY = "reflex_token";
const AUTH_KEY = "reflex_auth";
const ENFORCED_KEY = "reflex_auth_enforced";

const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
const write = (key, value) => { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* storage blocked */ } };

export const getToken = () => read(TOKEN_KEY);

// Changes (executor controls, TradFi markets, settings, chat...) need the admin key once
// REFLEX_ADMIN_KEY is set on the server. It stays in this browser only.
const ADMIN_KEY = "reflex_admin_key";
export const getAdminKey = () => read(ADMIN_KEY) || "";
export const setAdminKey = key => write(ADMIN_KEY, key ? String(key).trim() : null);
export const authEnforced = () => read(ENFORCED_KEY) === "1";

export function isAuthenticated() {
  // A connected wallet used to skip the code; that only holds while the server is open.
  return read(AUTH_KEY) === "1" || (!authEnforced() && !!read("rcce-wallet-address"));
}

export async function login(code) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }),
  });
  if (res.status === 401) return false;
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  const data = await res.json();
  write(TOKEN_KEY, data.token || null);
  write(ENFORCED_KEY, data.enforced ? "1" : null);
  write(AUTH_KEY, "1");
  return true;
}

// Whether the server asks for a code at all; null when it cannot be reached.
export async function authStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/auth/status`);
    if (!res.ok) return null;
    const { enforced } = await res.json();
    write(ENFORCED_KEY, enforced ? "1" : null);
    return !!enforced;
  } catch {
    return null;
  }
}

export function logout() {
  write(TOKEN_KEY, null);
  write(AUTH_KEY, null);
  window.dispatchEvent(new Event("reflex-auth-expired"));
}

export function withToken(url) {
  const token = getToken();
  return token ? `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}` : url;
}

// Attach the token to API calls and react to 401s, without touching every fetch site.
const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  const url = typeof input === "string" ? input : input?.url || "";
  const isApi = url.startsWith(API_BASE) && !url.includes("/api/auth/");
  const token = isApi ? getToken() : null;
  const method = String(init.method || (typeof input !== "string" && input?.method) || "GET").toUpperCase();
  const adminKey = isApi && method !== "GET" && method !== "HEAD" ? getAdminKey() : "";
  if (token || adminKey) {
    const headers = new Headers(init.headers || (typeof input !== "string" ? input.headers : undefined));
    if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
    if (adminKey) headers.set("X-Admin-Key", adminKey);
    init = { ...init, headers };
  }
  const res = await nativeFetch(input, init);
  if (isApi && res.status === 403 && method !== "GET") {
    window.dispatchEvent(new Event("reflex-admin-required"));
  }
  if (isApi && res.status === 401) {
    write(ENFORCED_KEY, "1");
    logout();
  }
  return res;
};
