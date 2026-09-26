import { useEffect, useState } from "react";
import { getBaseSymbol } from "../theme.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Profitable traders holding a coin (their fills, loaded in the background on the server,
// so it asks again while some are pending) and the new positions seen by the wallet sweep.
export default function useCoinTraders(symbol, enabled = true) {
  const [entries, setEntries] = useState(null);
  const [opens, setOpens] = useState(null);
  useEffect(() => {
    setEntries(null);
    setOpens(null);
    if (!enabled || !symbol) return undefined;
    const coin = encodeURIComponent(getBaseSymbol(symbol));
    let cancelled = false, timer = null, tries = 0;
    const load = () => fetch(`${API_BASE}/api/hyperlens/entries/${coin}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (cancelled) return;
        setEntries(d);
        if (d?.pending && ++tries < 12) timer = setTimeout(load, 10000);
      })
      .catch(() => {});
    load();
    fetch(`${API_BASE}/api/hyperlens/opens/${coin}?days=60`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (!cancelled) setOpens(d); })
      .catch(() => {});
    return () => { cancelled = true; clearTimeout(timer); };
  }, [symbol, enabled]);
  return { entries, opens };
}
