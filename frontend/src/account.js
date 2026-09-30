// Wallet account: sign-in with an injected wallet (EIP-1193, personal_sign of the server's
// EIP-4361 message), the signed-in state from /api/me, and sign-out. Built in only when
// VITE_ACCOUNTS is "1"; otherwise nothing here runs and no request is made.
import { useSyncExternalStore } from "react";
import { getSession, setSession } from "./auth.js";
import { toHex } from "./utils/account.js";
import { track } from "./usage.js";

export const ACCOUNTS = import.meta.env.VITE_ACCOUNTS === "1";
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

let me = null;                 // /api/me, null until read
let inflight = null;
const subs = new Set();
const emit = () => subs.forEach(fn => fn());
const subscribe = fn => { subs.add(fn); return () => subs.delete(fn); };
const snapshot = () => me;

export function loadMe() {
  if (!ACCOUNTS) return Promise.resolve(null);
  if (inflight) return inflight;
  inflight = fetch(`${API_BASE}/api/me`)
    .then(r => (r.ok ? r.json() : null))
    .then(d => {
      if (!d) return null;
      if (getSession() && !d.address) setSession(null);       // the session ended on the server
      me = d;
      emit();
      return d;
    })
    .catch(() => null)
    .finally(() => { inflight = null; });
  return inflight;
}

async function post(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}), adminNotice: false,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Server error ${res.status}`);
  return data;
}

export async function signIn() {
  const eth = typeof window !== "undefined" ? window.ethereum : null;
  if (!eth) throw new Error("No wallet found in this browser.");
  const accounts = await eth.request({ method: "eth_requestAccounts" });
  const address = accounts?.[0];
  if (!address) throw new Error("No account selected.");
  const chainHex = await eth.request({ method: "eth_chainId" }).catch(() => "0x1");
  const { message } = await post("/api/auth/wallet/nonce", {
    address, domain: window.location.host, chain_id: parseInt(chainHex, 16) || 1,
  });
  const signature = await eth.request({ method: "personal_sign", params: [toHex(message), address] });
  const res = await post("/api/auth/wallet/verify", { message, signature });
  setSession(res.token);
  track("wallet_signin");
  await loadMe();
  return res;
}

export async function signOut() {
  try { await post("/api/auth/wallet/logout"); } catch { /* ended anyway */ }
  setSession(null);
  await loadMe();
}

export async function telegramLink() {
  const res = await post("/api/me/telegram/link");
  track("telegram_link");
  return res;
}

export async function telegramPrefs(body) {
  const res = await fetch(`${API_BASE}/api/me/telegram`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), adminNotice: false,
  });
  if (res.ok) await loadMe();
  return res.ok;
}

export async function telegramUnlink() {
  const res = await fetch(`${API_BASE}/api/me/telegram`, { method: "DELETE", adminNotice: false });
  if (res.ok) await loadMe();
  return res.ok;
}

// The account as React state; reads /api/me once per page load.
let started = false;
export function useAccount() {
  if (ACCOUNTS && !started) { started = true; loadMe(); }
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

// Features for holders: true while tiers are off (or accounts are off).
export function allowed(account, feature) {
  if (!ACCOUNTS || !account || !account.tiers) return true;
  return !!account.features?.[feature];
}

// Whether the per-account lists apply (signed in, accounts on).
export const usesAccount = () => ACCOUNTS && !!getSession();
