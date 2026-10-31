import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TTL_MS = 10 * 60 * 1000;
let cached = null, cachedAt = 0, pending = null;

// How many wallets are on the tracked lists now (/api/hyperlens/status), for the group
// definitions. One request per ten minutes for the whole page, shared by every caller.
export default function useRosterCounts() {
  const [counts, setCounts] = useState(cached);
  useEffect(() => {
    if (cached && Date.now() - cachedAt < TTL_MS) return undefined;
    let alive = true;
    pending = pending || fetch(`${API_BASE}/api/hyperlens/status`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (d) {
          cached = { money_printer_count: d.money_printer_count, smart_money_count: d.smart_money_count, elite_count: d.elite_count };
          cachedAt = Date.now();
        }
        return cached;
      })
      .catch(() => cached)
      .finally(() => { pending = null; });
    pending.then(c => { if (alive && c) setCounts(c); });
    return () => { alive = false; };
  }, []);
  return counts || {};
}
