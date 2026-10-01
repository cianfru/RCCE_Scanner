import { useCallback, useSyncExternalStore } from "react";
import { createKeyedCache } from "../utils/keyedCache.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const NONE = Object.freeze({ data: undefined, error: null, loading: false });

// The Radar's price ladder for one coin: the profitable wallets at their entry prices, the weekly
// band, the engine's trend line and the median entries (/api/setup-map/ladder). One read per coin and
// timeframe per minute, refreshed while it shows.
const ladders = createKeyedCache({
  fetcher: key => {
    const [tf, coin] = key.split("|");
    return fetch(`${API_BASE}/api/setup-map/ladder?coin=${encodeURIComponent(coin)}&tf=${tf}`).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
  },
  ttl: 60_000,
  refresh: true,
});

export default function useLadder(coin, tf) {
  const key = coin ? `${tf === "4h" ? "4h" : "1d"}|${coin}` : null;
  const sub = useCallback(fn => (key ? ladders.subscribe(key, fn) : () => {}), [key]);
  const snap = useSyncExternalStore(sub, () => (key ? ladders.get(key) : NONE));
  return { data: snap.data ?? null, error: snap.error ? String(snap.error.message || snap.error) : null, loading: !!key && snap.data === undefined && !snap.error };
}
