import { useCallback, useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Followed traders (shortlist with Telegram alerts). Changes need the admin key; the
// global fetch wrapper adds it and raises "reflex-admin-required" when it is missing.
export default function useFollowed() {
  const [data, setData] = useState(null);
  const load = useCallback(() => fetch(`${API_BASE}/api/hyperlens/followed`)
    .then(r => (r.ok ? r.json() : null)).then(d => d && setData(d)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const followed = new Set((data?.traders || []).map(t => t.address));
  const toggle = useCallback(async (address, note = "") => {
    const a = address.toLowerCase();
    const on = followed.has(a);
    const res = await fetch(`${API_BASE}/api/hyperlens/followed${on ? `/${a}` : ""}`, on
      ? { method: "DELETE" }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ address: a, note }) });
    if (res.ok) await load();
    return res.ok;
  }, [followed, load]);
  return { data, followed, toggle, reload: load };
}
