// Sector / ecosystem grouping for the scanner (display only; backend sectors.py).
import { setupAlignment } from "./signalPresentation.js";
import { traderLean } from "./traders.js";

const LONGS = new Set(["STRONG_LONG", "LIGHT_LONG"]);
const change = r => { const s = r.sparkline || []; return s.length > 1 && s[0] > 0 ? s[s.length - 1] / s[0] - 1 : null; };
const median = xs => { const v = xs.filter(Number.isFinite).sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : null; };

const oi = r => r.positioning?.oi_value || 0;

// Where profitable traders put their money compared with the market: the group's
// share of their gross exposure over its share of open interest. 2x = they hold
// twice the market's weight there. Null when either side is too thin to read.
export function traderWeight(lean, rows, by, name) {
  const groups = lean?.groups || {};
  const gross = g => (g ? (g.long_usd || 0) + (g.short_usd || 0) : 0);
  const book = Object.entries(groups).filter(([k]) => k.startsWith("sector:")).reduce((a, [, g]) => a + gross(g), 0);
  const market = rows.reduce((a, r) => a + oi(r), 0);
  const mine = gross(groups[`${by}:${name}`]);
  const theirs = rows.filter(r => r[by] === name).reduce((a, r) => a + oi(r), 0);
  if (!book || !market || !theirs || theirs / market < 0.002) return null;
  return (mine / book) / (theirs / market);
}

// One entry per group, strongest relative to BTC first.
export function groupStats(rows, by = "sector", lean = null) {
  const btc = rows.find(r => r.symbol === "BTC/USDT");
  const base = btc ? change(btc) : null;
  const groups = {};
  for (const r of rows) {
    const key = r[by];
    if (!key) continue;
    (groups[key] ||= []).push(r);
  }
  return Object.entries(groups).map(([name, rs]) => {
    const moved = median(rs.map(change));
    return {
      name, n: rs.length,
      uptrend: rs.filter(r => r.regime === "MARKUP").length,
      longs: rs.filter(r => LONGS.has(r.signal)).length,
      locked: rs.filter(r => setupAlignment(r).strength > 0).length,
      vsBtc: moved != null && base != null ? moved - base : null,
      traders: traderLean(lean?.groups?.[`${by}:${name}`]),
      weight: lean ? traderWeight(lean, rows, by, name) : null,
    };
  }).filter(g => g.n >= 2).sort((a, b) => (b.vsBtc ?? -1) - (a.vsBtc ?? -1));
}

export const SECTOR_SHORT = {
  "Layer 1": "L1", "Layer 2": "L2", "Exchanges": "Exchange", "Gaming & NFT": "Gaming",
  "Infrastructure": "Infra", "RWA & Stablecoins": "RWA",
};
