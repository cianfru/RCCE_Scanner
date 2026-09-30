// Search across coins and traders (the header search). Pure functions: the component feeds the
// scanner rows, Hyperliquid's market contexts, the Radar's setup map and the trader list.
import { coinName } from "../data/coinNames.js";
import { codename } from "./walletName.js";

export const isFullAddress = v => /^0x[0-9a-f]{40}$/i.test(String(v || "").trim());

const norm = s => String(s || "").trim().toLowerCase();

// Optimal string alignment distance (Levenshtein plus adjacent swaps), stopping early past max.
export function editDistance(a, b, max = 2) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  const prev2 = new Array(b.length + 1).fill(0);
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      let v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, prev2[j - 2] + 1);
      cur.push(v);
      best = Math.min(best, v);
    }
    for (let j = 0; j <= b.length; j++) prev2[j] = prev[j];
    prev = cur;
    if (best > max) return max + 1;
  }
  return prev[b.length];
}

// Typos allowed for a query this long: none under 4 letters, one up to 7, two from 8.
const typoBudget = q => (q.length < 4 ? 0 : q.length < 8 ? 1 : 2);

// A fuzzy hit: the query within the budget of the ticker, the name, one of its words, or the
// name's start cut to the query's length (so a typo in a half-typed name still finds it).
function fuzzy(q, ticker, name) {
  const k = typoBudget(q);
  if (!k) return false;
  const cands = [ticker, name, ...name.split(/\s+/)];
  for (let d = -1; d <= 1; d++) if (q.length + d > 0) cands.push(name.slice(0, q.length + d));
  return cands.some(c => c && editDistance(q, c, k) <= k);
}

// 0 exact ticker or name, 1 ticker prefix, 2 name (or a word of it) prefix, 3 contains, 4 typo; null: no match.
export function coinTier(query, ticker, name) {
  const q = norm(query), t = norm(ticker), n = norm(name);
  if (!q) return null;
  if (t === q || n === q) return 0;
  if (t.startsWith(q)) return 1;
  if (n && (n.startsWith(q) || n.split(/[\s.-]+/).some(w => w.startsWith(q)))) return 2;
  if (t.includes(q) || n.includes(q)) return 3;
  if (fuzzy(q, t, n)) return 4;
  return null;
}

// Spot markets the app analyses (backend/hyperliquid_universe.py and spot_quality.py): one USDC
// pair per base token, no stablecoins, at least $25K traded in 24h.
const STABLECOINS = new Set(["USDT0", "USDE", "USDH", "USDHL", "USDXL", "FEUSD", "USDT", "DAI", "USDS", "PYUSD", "FDUSD", "RLUSD", "USD1", "EURC"]);
export const MIN_SPOT_VOLUME = 25_000;
const num = v => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };

// Hyperliquid's markets from its metaAndAssetCtxs (perps) and spotMetaAndAssetCtxs (spot) answers,
// either of which may be null: [{kind, symbol (the app's key: "BTC/USDT", "HYPE/USDC"), coin
// (Hyperliquid's id), ticker, name, price, prevDay, volume, oi}]. Delisted perps and HIP-3
// markets are left out, as the backend does.
export function parseHlMarkets(perp, spot) {
  const out = [];
  if (Array.isArray(perp) && perp[0]?.universe) {
    const [meta, ctxs] = perp;
    meta.universe.forEach((u, i) => {
      const c = ctxs?.[i];
      if (!c || u.isDelisted || u.name.includes(":")) return;
      const price = num(c.markPx);
      out.push({ kind: "perpetual", symbol: `${u.name.toUpperCase()}/USDT`, coin: u.name, ticker: u.name, name: coinName(u.name),
        price, prevDay: num(c.prevDayPx), volume: num(c.dayNtlVlm) || 0, oi: (num(c.openInterest) || 0) * (price || 0) });
    });
  }
  if (Array.isArray(spot) && spot[0]?.universe) {
    const [meta, ctxs] = spot;
    const tokens = new Map(meta.tokens.map(t => [t.index, t]));
    const byCoin = new Map((ctxs || []).map(c => [c.coin, c]));
    const names = new Map();
    for (const t of meta.tokens) names.set(t.name, (names.get(t.name) || 0) + 1);
    const pairs = [...meta.universe].sort((a, b) => ((tokens.get(a.tokens[1])?.name !== "USDC") - (tokens.get(b.tokens[1])?.name !== "USDC")) || a.index - b.index);
    const seen = new Set();
    for (const pair of pairs) {
      if (pair.isDelisted) continue;
      const base = tokens.get(pair.tokens[0]), quote = tokens.get(pair.tokens[1]);
      if (!base || !quote || seen.has(base.index)) continue;
      seen.add(base.index);
      if (quote.name !== "USDC") continue;
      const label = names.get(base.name) === 1 ? base.name : `${base.name}~${base.index}`;
      const plain = base.name.toUpperCase();
      if (STABLECOINS.has(plain) || plain.startsWith("USD")) continue;
      const c = byCoin.get(pair.name);
      const volume = num(c?.dayNtlVlm) || 0;
      if (volume < MIN_SPOT_VOLUME) continue;
      out.push({ kind: "spot", symbol: `${label}/USDC`.toUpperCase(), coin: pair.name, ticker: base.name, name: base.fullName || coinName(base.name),
        price: num(c?.markPx), prevDay: num(c?.prevDayPx), volume, oi: 0 });
    }
  }
  return out;
}

// Search entries: Hyperliquid's markets, with the scanner's row where it is loaded (opening a
// coin keeps its timeframe). The right-hand word is the Radar's state for a perp, "Spot" for a
// spot market. radar: Map base ticker -> setup-map coin. Without Hyperliquid's list (not loaded,
// or unreachable) the scanner rows stand in.
export function coinEntries(markets, rows, radar) {
  const scan = new Map((rows || []).map(r => [String(r.symbol || "").toUpperCase(), r]));
  const list = markets?.length ? markets : (rows || []).map(r => {
    const spot = (r.market_kind || "perpetual") === "spot";
    const base = String(r.symbol || "").split("/")[0];
    return { kind: spot ? "spot" : "perpetual", symbol: String(r.symbol || "").toUpperCase(), coin: r.market_coin || base,
      ticker: spot ? base : (r.market_coin || base), name: coinName(base), price: r.price ?? null, prevDay: null, volume: 0, oi: 0 };
  });
  return list.map(m => {
    const r = scan.get(m.symbol);
    const spot = m.kind === "spot";
    const base = m.symbol.split("/")[0];
    const s = spot ? null : radar?.get(base);
    return { kind: "coin", key: `c:${m.symbol}`, spot, ticker: m.ticker, name: m.name,
      row: r || { symbol: m.symbol, market_kind: m.kind, market_coin: m.coin },
      price: m.price ?? r?.price ?? null, change: m.price && m.prevDay ? m.price / m.prevDay - 1 : null,
      volume: m.volume || 0, oi: m.oi || 0, status: spot ? "Spot" : s ? radarStatus(s) : null };
  });
}

// The Radar's plain word for a coin: Early setup (in the box), In entry zone (price near where
// profitable traders went long), both, or nothing.
export function radarStatus(c) {
  const early = c?.zone === "watch", zone = !!c?.entry?.in_zone;
  if (early && zone) return "Early setup · entry zone";
  if (early) return "Early setup";
  if (zone) return "In entry zone";
  return null;
}

// Typo matches are a fallback: they show only when nothing matches as typed ("bitcon" finds
// Bitcoin, but "bitcoin" does not also bring Litecoin).
export function searchCoins(query, entries, limit = 6) {
  let hits = [];
  for (const e of entries) {
    const tier = coinTier(query, e.ticker, e.name);
    if (tier != null) hits.push([tier, e]);
  }
  if (hits.some(h => h[0] < 4)) hits = hits.filter(h => h[0] < 4);
  // Same match quality: perps before spot, then by 24h volume and open interest.
  hits.sort((a, b) => a[0] - b[0] || (!!a[1].spot - !!b[1].spot) || (b[1].volume - a[1].volume) || (b[1].oi - a[1].oi));
  return hits.slice(0, limit).map(([tier, e]) => ({ ...e, tier }));
}

// Traders by codename (from 3 letters: two letters match half the list): a whole word, then
// a word's start, then anywhere; ties by 30d PnL. A 0x prefix of 6+ characters matches addresses.
export function searchTraders(query, traders, limit = 3) {
  const q = norm(query);
  if (q.length < 3) return [];
  const hex = /^0x[0-9a-f]{4,}$/.test(q);
  const hits = [];
  for (const t of traders || []) {
    const name = t.name || codename(t.address);
    const n = name.toLowerCase(), words = n.split(" ");
    let tier = null;
    if (hex) tier = t.address.toLowerCase().startsWith(q) ? 1 : null;
    else if (words.includes(q) || n === q) tier = 0;
    else if (words.some(w => w.startsWith(q))) tier = 1;
    else if (n.includes(q)) tier = 2;
    if (tier != null) hits.push([tier, { kind: "trader", key: `t:${t.address}`, address: t.address, name, pnl: t.pnl }]);
  }
  hits.sort((a, b) => a[0] - b[0] || (b[1].pnl ?? -Infinity) - (a[1].pnl ?? -Infinity));
  return hits.slice(0, limit).map(h => h[1]);
}

// Everything the list shows for one query: a pasted address is one row; otherwise coins, then traders.
export function searchAll(query, { coins = [], traders = [] } = {}) {
  const q = String(query || "").trim();
  if (!q) return { coins: [], traders: [], address: null };
  if (isFullAddress(q)) {
    const a = q.toLowerCase();
    const known = traders.find(t => t.address.toLowerCase() === a);
    return { coins: [], traders: [], address: { kind: "address", key: `a:${a}`, address: a, name: codename(a), pnl: known?.pnl ?? null } };
  }
  return { coins: searchCoins(q, coins), traders: searchTraders(q, traders), address: null };
}
