import { useEffect, useState } from "react";
import { T } from "../theme.js";
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
export default function OpportunityActivity() {
  const [events, setEvents] = useState([]);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch(`${API}/api/opportunities/transitions?limit=12`, { signal: controller.signal });
        if (response.ok) setEvents((await response.json()).events || []);
      } catch { /* The scanner remains usable if activity history is unavailable. */ }
    };
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  if (!events.length) return null;
  return <details style={{ color: T.text2, margin: "8px 0", padding: 10, border: `1px solid ${T.border}`, borderRadius: 8 }}>
    <summary>Recent opportunity changes ({events.length})</summary>
    <ul>{events.map(e => <li key={e.id}>{e.symbol} · {e.timeframe} · {e.status.replaceAll("_", " ")} · {new Date(e.observed_at * 1000).toLocaleString()} — {e.opportunity.reason}</li>)}</ul>
  </details>;
}
