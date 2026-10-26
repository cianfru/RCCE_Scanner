// metaAndAssetCtxs per dex, read from Hyperliquid in the browser and kept for the visit (five
// minutes for the expanded row): szDecimals and the current hourly funding rate per coin.
import { useEffect, useState } from "react";
import * as hlClient from "../../services/hlClient.js";
import { venueOf } from "../../utils/portfolio/displayNames.js";

const cache = new Map();          // dex -> {at, v: Map(coin -> {szDecimals, funding})}
const pending = new Map();        // dex -> Promise

export function loadAssetCtx(dex, maxAge = 300_000) {
  const hit = cache.get(dex);
  if (hit && Date.now() - hit.at < maxAge) return Promise.resolve(hit.v);
  if (pending.has(dex)) return pending.get(dex);
  const p = hlClient.getMetaAndAssetCtxs(dex).then(raw => {
    const [meta, ctxs] = raw || [];
    const out = new Map();
    (meta?.universe || []).forEach((u, i) => out.set(u.name, { szDecimals: u.szDecimals, funding: parseFloat(ctxs?.[i]?.funding) }));
    cache.set(dex, { at: Date.now(), v: out });
    return out;
  }).finally(() => pending.delete(dex));
  pending.set(dex, p);
  return p;
}

const dexOf = coin => (venueOf(coin) === "main" ? "" : venueOf(coin));

// One coin's {szDecimals, funding}, or null while it loads.
export function useAssetCtx(coin) {
  const dex = dexOf(coin);
  const [v, setV] = useState(() => cache.get(dex)?.v || null);
  useEffect(() => {
    let alive = true;
    loadAssetCtx(dex).then(m => alive && setV(m)).catch(() => {});
    return () => { alive = false; };
  }, [dex]);
  return v?.get(coin) || null;
}

// The held venues' contexts, read once per visit (a new venue reads its own once): coin -> ctx.
export function useHeldAssetCtx(coins) {
  const dexes = [...new Set((coins || []).filter(c => venueOf(c) !== "spot").map(dexOf))].sort();
  const key = dexes.join(",");
  const [v, setV] = useState(() => new Map());
  useEffect(() => {
    if (!dexes.length) return undefined;
    let alive = true;
    Promise.all(dexes.map(d => loadAssetCtx(d, Infinity).catch(() => new Map()))).then(maps => {
      if (!alive) return;
      const out = new Map();
      for (const m of maps) for (const [k, x] of m) out.set(k, x);
      setV(out);
    });
    return () => { alive = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return v;
}
