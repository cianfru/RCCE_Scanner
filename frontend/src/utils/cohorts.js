// Pure helpers for HyperLens's Cohorts view (/api/cohorts, /api/cohorts/history).

// Display names by range: the backend's cohort names are internal keys.
export const PNL_ORDER = [
  ["Giga-Rekt", "Lost $1M+"], ["Full Rekt", "Lost $100K–1M"], ["Semi-Rekt", "Lost $10K–100K"],
  ["Exit Liquidity", "Lost up to $10K"], ["Humble Earner", "Up to $10K profit"], ["Grinder", "$10K–100K profit"],
  ["Smart Money", "$100K–1M profit"], ["Money Printer", "$1M+ profit"],
];
export const EQUITY_ORDER = [
  ["Small Whale", "$100K–500K account"], ["Whale", "$500K–1M account"], ["Tidal Whale", "$1M–5M account"], ["Leviathan", "$5M+ account"],
];
export const WINNERS = ["Smart Money", "Money Printer"];
export const LOSERS = ["Giga-Rekt", "Full Rekt", "Semi-Rekt", "Exit Liquidity"];

export const orderFor = dimension => (dimension === "equity" ? EQUITY_ORDER : PNL_ORDER);
export const displayName = (dimension, cohort) => orderFor(dimension).find(([k]) => k === cohort)?.[1] || cohort;

// Current rows in display order; cohorts with no row are left out.
export function orderedRows(rows, dimension) {
  const by = new Map((rows || []).filter(r => r.dimension === dimension).map(r => [r.cohort, r]));
  return orderFor(dimension).filter(([k]) => by.has(k)).map(([k, name]) => ({ ...by.get(k), name }));
}

const bias = (lo, sh) => (lo + sh > 0 ? (lo - sh) / (lo + sh) : null);

// Profitable (all-time $100K+) against losing wallets at each reading, from the per-cohort history.
export function gapSeries(history) {
  const at = new Map();
  for (const [cohort, pts] of Object.entries(history || {})) {
    const side = WINNERS.includes(cohort) ? "w" : LOSERS.includes(cohort) ? "l" : null;
    if (!side) continue;
    for (const p of pts) {
      const e = at.get(p.ts) || { ts: p.ts, wl: 0, ws: 0, ll: 0, ls: 0 };
      e[`${side}l`] += p.long_usd || 0;
      e[`${side}s`] += p.short_usd || 0;
      at.set(p.ts, e);
    }
  }
  return [...at.values()].sort((a, b) => a.ts - b.ts).map(e => {
    const w = bias(e.wl, e.ws), l = bias(e.ll, e.ls);
    return { ts: e.ts, winners: w, losers: l, gap: w == null || l == null ? null : w - l };
  });
}

export function leanPct(b) {
  if (b == null) return "—";
  const r = Math.round(b * 100);                        // sign from the rounded value: never "-0%"
  return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r)}%`;
}

export function usd(v) {
  const a = Math.abs(v || 0);
  if (a >= 1e9) return `$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${Math.round(a / 1e3)}K`;
  return `$${Math.round(a)}`;
}
