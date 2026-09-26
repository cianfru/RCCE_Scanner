// Sector / ecosystem grouping for the scanner (display only; backend sectors.py).
import { setupAlignment } from "./signalPresentation.js";
import { traderLean } from "./traders.js";

const LONGS = new Set(["STRONG_LONG", "LIGHT_LONG"]);
const change = r => { const s = r.sparkline || []; return s.length > 1 && s[0] > 0 ? s[s.length - 1] / s[0] - 1 : null; };
// True median (mean of the two middle values when the count is even).
export const median = xs => {
  const v = xs.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return null;
  const h = v.length >> 1;
  return v.length % 2 ? v[h] : (v[h - 1] + v[h]) / 2;
};

const oi = r => r.positioning?.oi_value || 0;

// by: "sector" | "ecosystem" | "pocket" (name "Sector|Ecosystem").
export function inGroup(r, by, name) {
  if (by !== "pocket") return r[by] === name;
  const [sector, eco] = name.split("|");
  return r.sector === sector && r.ecosystem === eco;
}

// Where profitable traders put their money compared with the market: the group's
// share of their gross exposure over its share of open interest. 2x = they hold
// twice the market's weight there. Null when either side is too thin to read.
export function traderWeight(lean, rows, by, name) {
  const groups = lean?.groups || {};
  const gross = g => (g ? (g.long_usd || 0) + (g.short_usd || 0) : 0);
  const book = Object.entries(groups).filter(([k]) => k.startsWith("sector:")).reduce((a, [, g]) => a + gross(g), 0);
  const market = rows.reduce((a, r) => a + oi(r), 0);
  const mine = gross(groups[`${by}:${name}`]);
  const theirs = rows.filter(r => inGroup(r, by, name)).reduce((a, r) => a + oi(r), 0);
  if (!book || !market || !theirs || theirs / market < 0.002) return null;
  return (mine / book) / (theirs / market);
}

// Chips compare each group with the typical alt (the median alt), not BTC: when the whole
// alt market beats BTC, every group looks strong against BTC. A group's lead is its
// median gap to the typical alt shrunk by size, n/(n+K): small groups keep less of their
// lead, so two strong coins in a five-coin sector cannot top the list on their own.
export const K_SIZE = 10;          // calibrated on 276 past 24-day windows
export const SMALL_N = 10;         // dashed chip: read as tentative
export const MIN_RANK_N = 3;       // fewer markets: listed after the ranked groups
export const EX_TOP_MIN = 1.5;     // show the lead without the best market when it adds this much
export const TAIL_NAMES = new Set(["Other"]);

// BTC by base (spot lists it as UBTC); pegged markets (stablecoins, gold) are not alts.
const BTC_BASES = new Set(["BTC", "UBTC"]);
const isBtc = r => BTC_BASES.has(String(r.symbol || "").split("/")[0]);
const PEGGED = "RWA & Stablecoins";

export function altBaseline(rows) {
  const btcRow = rows.find(isBtc);
  const btc = btcRow ? change(btcRow) : null;
  const alts = rows.filter(r => !isBtc(r) && r.sector !== PEGGED).map(change).filter(Number.isFinite);
  const M = median(alts);
  const gaps = M == null ? [] : alts.map(x => Math.abs(100 * (x - M))).sort((a, b) => a - b);
  const p90 = gaps.length ? gaps[Math.ceil(0.9 * gaps.length) - 1] : 0;
  const D = Math.max(10, Math.min(60, 10 * Math.ceil(p90 / 10)));
  return { M, btc, vsBtc: M != null && btc != null ? 100 * (M - btc) : null, D, nAlts: alts.length };
}

const shrink = (med, n) => (med * n) / (n + K_SIZE);
const rounded = x => { const v = Math.sign(x) * Math.round(Math.abs(x)); return v === 0 ? 0 : v; };

// Ranked groups (by size-adjusted lead, ties to the larger group), then the unranked tail.
export function groupStats(rows, by = "sector", lean = null, base = altBaseline(rows)) {
  const groups = {};
  for (const r of rows) {
    const key = r[by];
    if (!key) continue;
    (groups[key] ||= []).push(r);
  }
  const all = Object.entries(groups).filter(([, rs]) => rs.length >= 2).map(([name, rs]) => {
    const members = base.M == null ? [] : rs.map(r => ({ sym: String(r.symbol || "").split("/")[0], move: change(r) }))
      .filter(m => Number.isFinite(m.move)).map(m => ({ ...m, e: 100 * (m.move - base.M) })).sort((a, b) => b.e - a.e);
    const n = members.length;
    const med = n ? median(members.map(m => m.e)) : null;
    const lead = med == null ? null : shrink(med, n);
    const shown = lead == null ? null : rounded(lead);
    let exTop = null;
    if (n >= MIN_RANK_N && lead != null) {
      const rest = shrink(median(members.slice(1).map(m => m.e)), n - 1);
      if (lead - rest >= EX_TOP_MIN) exTop = { sym: members[0].sym, shown: rounded(rest) };
    }
    const moves = members.map(m => m.move);
    return {
      name, n, rows: rs.length, missing: rs.length - n, members, med, lead, shown, exTop,
      dir: shown == null ? "flat" : shown >= 1 ? "up" : shown <= -1 ? "down" : "flat",
      ahead: members.filter(m => m.e > 0).length,
      small: n < SMALL_N,
      tail: n < MIN_RANK_N || TAIL_NAMES.has(name),
      vsBtc: n && base.btc != null ? 100 * (median(moves) - base.btc) : null,
      uptrend: rs.filter(r => r.regime === "MARKUP").length,
      longs: rs.filter(r => LONGS.has(r.signal)).length,
      locked: rs.filter(r => setupAlignment(r).strength > 0).length,
      traders: traderLean(lean?.groups?.[`${by}:${name}`]),
      weight: lean ? traderWeight(lean, rows, by, name) : null,
    };
  });
  const ranked = all.filter(g => !g.tail).sort((a, b) =>
    (b.shown ?? -Infinity) - (a.shown ?? -Infinity) || b.n - a.n || a.name.localeCompare(b.name));
  const tail = all.filter(g => g.tail).sort((a, b) => b.rows - a.rows || a.name.localeCompare(b.name));
  return [...ranked, ...tail];
}

export const SECTOR_SHORT = {
  "Layer 1": "L1", "Layer 2": "L2", "Exchanges": "Exchange", "Gaming & NFT": "Gaming",
  "Infrastructure": "Infra", "RWA & Stablecoins": "RWA",
};
