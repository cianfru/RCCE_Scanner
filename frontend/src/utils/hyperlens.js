// HyperLens: number formatting and the per-symbol figures for one wallet group.

const MINUS = "−";

// A symbol needs this many positioned wallets before it gets a trend: one or two
// wallets say nothing about how a group leans.
export const MIN_WALLETS = 5;

export function fmtUsd(v) {
  if (v == null || isNaN(v)) return "--";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export function fmtPct(v, digits = 0) {
  if (v == null || isNaN(v)) return "--";
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M%`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(0)}K%`;
  return `${v.toFixed(digits)}%`;
}

const sign = v => (v > 0 ? "+" : v < 0 ? MINUS : "");

// Sign first, then the unsigned amount: "+$12K", "−$3K", "$0".
export const fmtSignedUsd = v => (v == null || isNaN(v) ? "--" : sign(v) + fmtUsd(Math.abs(v)));
export const fmtSignedPct = (v, digits = 0) => (v == null || isNaN(v) ? "--" : sign(v) + fmtPct(Math.abs(v), digits));

const COHORT_BLOCK = { money_printers: "money_printer", smart_money: "smart_money" };

// Figures for one consensus row and wallet group. The API nests cohort figures
// under c.money_printer / c.smart_money; the aggregate is only a fallback for rows
// that lack the nested block.
export function cohortFields(c, cohort) {
  const k = COHORT_BLOCK[cohort];
  const g = (k && c?.[k]) || c || {};
  const long_count = g.long_count ?? 0;
  const short_count = g.short_count ?? 0;
  const positioned = long_count + short_count;
  return {
    long_count, short_count, positioned,
    // Long minus short wallets as a share of positioned wallets. Recomputed here so
    // it means the same for every group (the API's cohort net_ratio is size-weighted).
    net_wallets: positioned ? (long_count - short_count) / positioned : 0,
    // Size-weighted lean the trend comes from, -1..+1.
    lean: g.size_lean ?? null,
    trend: positioned < MIN_WALLETS ? "THIN" : (g.trend ?? "NEUTRAL"),
    long_notional: g.long_notional ?? 0,
    short_notional: g.short_notional ?? 0,
  };
}

// Symbols per trend for the header; thin rows are counted apart, not as flat.
export function trendCounts(consensus, cohort) {
  const n = { BULLISH: 0, BEARISH: 0, NEUTRAL: 0, THIN: 0 };
  for (const c of consensus || []) n[cohortFields(c, cohort).trend] += 1;
  return n;
}
