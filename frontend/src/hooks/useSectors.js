import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

// /api/sectors: group price series (daily, vs BTC) and profitable-trader lean.
// Refreshed every 5 minutes; the lean moves with HyperLens polls, prices daily.
export default function useSectors({ days = 90, history = "" } = {}) {
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => fetch(`${API_BASE}/api/sectors?days=${days}${history ? `&history=${history}` : ""}`)
      .then(r => (r.ok ? r.json() : null)).then(d => { if (alive && d) setData(d); }).catch(() => {});
    load();
    const id = setInterval(load, 300_000);
    return () => { alive = false; clearInterval(id); };
  }, [days, history]);
  return data;
}
