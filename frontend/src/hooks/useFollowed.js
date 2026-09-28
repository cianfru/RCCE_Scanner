import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Followed traders (shortlist with Telegram alerts). Changes need the admin key; the
// global fetch wrapper adds it and raises "reflex-admin-required" when it is missing.
// One module-level store, so a follow from the wallet modal, the coin page or the
// Following tab shows everywhere at once.
let current = null;
let inflight = null;
let seq = 0;
const subs = new Set();
const emit = () => subs.forEach(fn => fn());
const subscribe = fn => { subs.add(fn); return () => subs.delete(fn); };
const snapshot = () => current;

// A forced load (after a change) always starts a new read, and only the newest read lands.
function load(force = false) {
  if (inflight && !force) return inflight;
  const n = ++seq;
  const p = fetch(`${API_BASE}/api/hyperlens/followed`)
    .then(r => (r.ok ? r.json() : null))
    .then(d => { if (d && n === seq) { current = d; emit(); } })
    .catch(() => {})
    .finally(() => { if (inflight === p) inflight = null; });
  inflight = p;
  return p;
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
      const res = await fetch(`${API_BASE}/api/hyperlens/followed${on ? `/${a}` : ""}`, on
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
