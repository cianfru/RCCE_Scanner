import { useEffect, useState } from "react";
import { parseHlMarkets } from "../utils/search.js";
import { apiFetch } from "../edge.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const HL_INFO = "https://api.hyperliquid.xyz/info";
const MARKETS_TTL = 60_000;
const TRADERS_TTL = 600_000;

// Loaded on the first open of the search, not before. Markets (perps and spot, with price, 24h
// change, volume and open interest) come straight from Hyperliquid's public API, so the search
// works on every page and costs the server nothing; the trader list is the 30d leaderboard the
// Traders page already serves.
const cache = { markets: null, marketsAt: 0, marketsP: null, traders: null, tradersAt: 0, tradersP: null };

const hl = type => fetch(HL_INFO, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type }) })
  .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))));

function loadMarkets() {
  if (cache.markets && Date.now() - cache.marketsAt < MARKETS_TTL) return Promise.resolve(cache.markets);
  if (cache.marketsP) return cache.marketsP;
  // Either half may fail on its own: perps without spot is still a useful list.
  cache.marketsP = Promise.all([hl("metaAndAssetCtxs").catch(() => null), hl("spotMetaAndAssetCtxs").catch(() => null)])
    .then(([perp, spot]) => {
      const list = parseHlMarkets(perp, spot);
      if (!list.length) return cache.markets || [];
      cache.markets = list; cache.marketsAt = Date.now();
      return list;
    })
    .finally(() => { cache.marketsP = null; });
  return cache.marketsP;
}

function loadTraders() {
  if (cache.traders && Date.now() - cache.tradersAt < TRADERS_TTL) return Promise.resolve(cache.traders);
  if (cache.tradersP) return cache.tradersP;
  const page = offset => apiFetch(`/api/traders/leaderboard?window=30d&offset=${offset}&limit=300`)
    .then(r => (r.ok ? r.json() : { rows: [] })).catch(() => ({ rows: [] }));
  cache.tradersP = Promise.all([page(0), page(300)])
    .then(([a, b]) => {
      const rows = [...(a.rows || []), ...(b.rows || [])].map(r => ({ address: r.address, pnl: r.pnl }));
      if (!rows.length) return cache.traders || [];
      cache.traders = rows; cache.tradersAt = Date.now();
      return rows;
    })
    .finally(() => { cache.tradersP = null; });
  return cache.tradersP;
}

// Hyperliquid's markets (see parseHlMarkets) and the traders ([{address, pnl}]), fetched once
// the search has been opened and refreshed on a later open once stale.
export default function useSearchData(active) {
  const [markets, setMarkets] = useState(cache.markets);
  const [traders, setTraders] = useState(cache.traders);
  useEffect(() => {
    if (!active) return undefined;
    let live = true;
    loadMarkets().then(m => { if (live) setMarkets(m); });
    loadTraders().then(t => { if (live) setTraders(t); });
    return () => { live = false; };
  }, [active]);
  return { markets, traders };
}
