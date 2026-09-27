import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const REFRESH_MS = 120_000;

// Traders' positioning on a few coins (the best and forming setups), refreshed every two
// minutes while shown. One small request for all of them.
export default function useSetupIntel(coins) {
  const key = [...new Set(coins.filter(Boolean))].sort().join(",");
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!key) { setData(null); return undefined; }
    let alive = true;
    const load = () => fetch(`${API_BASE}/api/hyperlens/intel?coins=${encodeURIComponent(key)}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (alive && d) setData(d); })
      .catch(() => {});
    load();
    const timer = setInterval(() => { if (!document.hidden) load(); }, REFRESH_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [key]);
  return data;
}
