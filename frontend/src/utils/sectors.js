// Sector / ecosystem grouping for the scanner (display only; backend sectors.py).
import { setupAlignment } from "./signalPresentation.js";

const LONGS = new Set(["STRONG_LONG", "LIGHT_LONG"]);
const change = r => { const s = r.sparkline || []; return s.length > 1 && s[0] > 0 ? s[s.length - 1] / s[0] - 1 : null; };
const median = xs => { const v = xs.filter(Number.isFinite).sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : null; };

// One entry per group, strongest relative to BTC first.
export function groupStats(rows, by = "sector") {
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
    };
  }).filter(g => g.n >= 2).sort((a, b) => (b.vsBtc ?? -1) - (a.vsBtc ?? -1));
}

export const SECTOR_SHORT = {
  "Layer 1": "L1", "Layer 2": "L2", "Exchanges": "Exchange", "Gaming & NFT": "Gaming",
  "Infrastructure": "Infra", "RWA & Stablecoins": "RWA",
};
