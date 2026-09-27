import { useCallback, useMemo, useSyncExternalStore } from "react";
import { createKeyedCache } from "../utils/keyedCache.js";
import { isAddress } from "../utils/setupMap.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const EXECUTOR = "executor";

// Open positions to mark as "mine": a Hyperliquid address's (public, read-only) or, with
// executorFallback and no address, the executor's. Cached per address for five minutes
// and shared by every consumer.
const cache = createKeyedCache({
  fetcher: key => fetch(`${API_BASE}/api/setup-map/mine${key === EXECUTOR ? "" : `?address=${encodeURIComponent(key)}`}`)
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
  ttl: 300_000,
  refresh: true,
});

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => { if (!document.hidden) cache.resume(); });
}

const noop = () => {};
const NONE = Object.freeze({ data: undefined, error: null, loading: false });
const NO_POSITIONS = new Map();

export default function useMyPositions(address, { executorFallback = false } = {}) {
  const key = isAddress(address) ? address : executorFallback ? EXECUTOR : null;
  const sub = useCallback(fn => (key ? cache.subscribe(key, fn) : noop), [key]);
  const snap = useSyncExternalStore(sub, () => (key ? cache.get(key) : NONE));
  const positions = snap.data?.positions || null;
  const byCoin = useMemo(() => (positions ? new Map(positions.map(p => [p.coin, p])) : NO_POSITIONS), [positions]);
  return { positions, byCoin, loading: !!key && snap.data === undefined && !snap.error, source: snap.data?.source || null };
}
