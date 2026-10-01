import { useCallback, useEffect, useSyncExternalStore } from "react";
import { currentSymbols } from "../utils/tickerRenames.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const KEY = "reflex_favorites";

// Starred symbols ("BTC/USDT", spot "X/USDC"): pinned to the top of the scanner, scanned
// more often, and read by the Telegram opportunity alerts. One store for the whole app,
// kept in localStorage and synced to /api/favorites.
const store = { favorites: null, hydrated: false, subs: new Set() };

// Symbols starred under a ticker Hyperliquid has since renamed (MATIC, RNDR, FTM) are read
// under the current name and saved back that way.
function current() {
  if (!store.favorites) {
    try {
      const { list, changed } = currentSymbols(JSON.parse(localStorage.getItem(KEY) || "[]"));
      store.favorites = new Set(list);
      if (changed) localStorage.setItem(KEY, JSON.stringify(list));
    } catch {
      store.favorites = new Set();
    }
  }
  return store.favorites;
}

function commit(next) {
  store.favorites = next;
  try { localStorage.setItem(KEY, JSON.stringify([...next])); } catch { /* storage blocked */ }
  for (const fn of [...store.subs]) fn();
}

function subscribe(fn) {
  store.subs.add(fn);
  return () => store.subs.delete(fn);
}

// Once per page load: add the server's list to this browser's (the server is what the
// Telegram bot reads).
function hydrate() {
  if (store.hydrated) return;
  store.hydrated = true;
  fetch(`${API_BASE}/api/favorites`)
    .then(r => r.json())
    .then(data => {
      if (Array.isArray(data?.symbols) && data.symbols.length > 0) commit(new Set([...current(), ...currentSymbols(data.symbols).list]));
    })
    .catch(() => {});
}

// Optimistic: the pin changes at once and stays if the server refuses (the fetch wrapper
// shows the admin notice on a 403).
export function toggleFavorite(symbol) {
  const next = new Set(current());
  const wasFav = next.has(symbol);
  if (wasFav) next.delete(symbol); else next.add(symbol);
  commit(next);
  fetch(`${API_BASE}/api/favorites/${encodeURIComponent(symbol)}`, { method: wasFav ? "DELETE" : "POST" }).catch(() => {});
}

export default function useFavorites() {
  const favorites = useSyncExternalStore(subscribe, current);
  useEffect(hydrate, []);
  const isFav = useCallback(symbol => favorites.has(symbol), [favorites]);
  return { favorites, isFav, toggle: toggleFavorite };
}
