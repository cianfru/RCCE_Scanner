import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";
import { usesAccount } from "../account.js";
import { refusal } from "../utils/account.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Followed traders (shortlist with Telegram alerts). Changes need the admin key; the
// global fetch wrapper adds it and raises "reflex-admin-required" when it is missing.
// One module-level store, so a follow from the wallet modal, the coin page or the
// Following tab shows everywhere at once. Signed in with a wallet (VITE_ACCOUNTS), the list
// is the account's own (/api/me/follows, same shape); a feature for holders reads {locked}.
let current = null;
let inflight = null;
let seq = 0;
const subs = new Set();
const emit = () => subs.forEach(fn => fn());
const subscribe = fn => { subs.add(fn); return () => subs.delete(fn); };
const snapshot = () => current;

const base = () => `${API_BASE}${usesAccount() ? "/api/me/follows" : "/api/hyperlens/followed"}`;

// A forced load (after a change) always starts a new read, and only the newest read lands.
function load(force = false) {
  if (inflight && !force) return inflight;
  const n = ++seq;
  const p = fetch(base())
    .then(async r => {
      if (r.ok) return r.json();
      const why = refusal(r.status, (await r.json().catch(() => ({}))).detail);
      return why ? { traders: [], events: [], locked: why } : null;
    })
    .then(d => { if (d && n === seq) { current = d; emit(); } })
    .catch(() => {})
    .finally(() => { if (inflight === p) inflight = null; });
  inflight = p;
  return p;
}

if (typeof window !== "undefined") {
  window.addEventListener("reflex-session", () => { if (current) load(true); });
}

export default function useFollowed() {
  const data = useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(() => { load(); }, []);
  const followed = useMemo(() => new Set((data?.traders || []).map(t => String(t.address).toLowerCase())), [data]);
  const toggle = useCallback(async (address, note = "") => {
    const a = address.toLowerCase();
    const on = followed.has(a);
    let ok = false;
    try {
      const res = await fetch(`${base()}${on ? `/${a}` : ""}`, on
        ? { method: "DELETE" }
        : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ address: a, note }) });
      ok = res.ok;
    } catch { ok = false; }
    if (ok) await load(true);
    return ok;
  }, [followed]);
  const reload = useCallback(() => load(true), []);
  return { data, followed, toggle, reload };
}
