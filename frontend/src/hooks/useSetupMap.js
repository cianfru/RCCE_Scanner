import { useCallback, useMemo, useSyncExternalStore } from "react";
import { createKeyedCache } from "../utils/keyedCache.js";
import { WATCH_MESSAGES, watchReason } from "../utils/setupMap.js";
import { apiJson } from "../edge.js";

export { WATCH_MESSAGES };

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TTL_MS = 300_000;
const WATCH = "watch";

const getJson = url => fetch(url).then(r => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
});

// One store for the whole app: the scanner strip, the header count, the Radar and every
// Watch toggle read the same setup map per timeframe (one GET per five minutes while
// something shows it and the page is visible) and the same watch list.
export const setupMapStore = {
  byTf: createKeyedCache({ fetcher: tf => apiJson(`/api/setup-map?tf=${tf}`), ttl: TTL_MS, refresh: true }),
  watch: createKeyedCache({ fetcher: () => getJson(`${API_BASE}/api/setup-map/watch`), ttl: TTL_MS, refresh: true }),
};

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) return;
    setupMapStore.byTf.resume();
    setupMapStore.watch.resume();
  });
}

export const loadSetupMap = (tf, opts) => setupMapStore.byTf.load(tf, opts);
export const loadWatch = opts => setupMapStore.watch.load(WATCH, opts);

const watchedNow = () => new Set((setupMapStore.watch.peek(WATCH)?.coins || []).map(c => c.coin));

// Watch or stop watching a coin. Changes need the admin key; the global fetch wrapper
// adds it (and raises the admin notice on a 403). Returns {ok, watching} or {ok:false, reason}.
export async function toggleWatch(coin, tf = "1d") {
  const on = watchedNow().has(coin);
  let res;
  try {
    // Every caller shows watchToast's own "Watching needs the admin key" on a 403 (adminNotice: false).
    res = await fetch(`${API_BASE}/api/setup-map/watch${on ? `/${encodeURIComponent(coin)}` : ""}`, on
      ? { method: "DELETE", adminNotice: false }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ coin, tf }), adminNotice: false });
  } catch {
    return { ok: false, reason: "error" };
  }
  if (!res.ok) return { ok: false, reason: watchReason(res.status) };
  await loadWatch({ force: true });
  return { ok: true, watching: !on };
}

const noop = () => {};
const NONE = Object.freeze({ data: undefined, error: null, loading: false });

// The setup map for one timeframe (null: none) plus the shared watch list.
export default function useSetupMap(tf) {
  const subMap = useCallback(fn => (tf ? setupMapStore.byTf.subscribe(tf, fn) : noop), [tf]);
  const map = useSyncExternalStore(subMap, () => (tf ? setupMapStore.byTf.get(tf) : NONE));
  const subWatch = useCallback(fn => setupMapStore.watch.subscribe(WATCH, fn), []);
  const watch = useSyncExternalStore(subWatch, () => setupMapStore.watch.get(WATCH));
  const watched = useMemo(() => new Set((watch.data?.coins || []).map(c => c.coin)), [watch.data]);
  const toggle = useCallback((coin, tfOverride) => toggleWatch(coin, tfOverride || tf || "1d"), [tf]);
  return {
    data: map.data ?? null,
    loading: !!tf && map.data === undefined && !map.error,
    error: map.error ? String(map.error.message || map.error) : null,
    watched,
    telegram: watch.data?.telegram,
    toggleWatch: toggle,
  };
}
