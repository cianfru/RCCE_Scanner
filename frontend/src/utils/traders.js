// Profitable traders (HyperLens): wallets in the top 300 by monthly return that were
// also in profit before this month. Display only; the signal's whale check still
// reads all tracked wallets weighted by size.
export const LEAN_MIN_WALLETS = 3;
export const LEAN_THRESHOLD = 0.15;

// { n, long, short, lean in [-1, 1], side: "long" | "short" | "mixed" | null }
export function traderLean(p) {
  const long = p?.long || 0, short = p?.short || 0, n = long + short;
  if (n < LEAN_MIN_WALLETS) return { n, long, short, lean: null, side: null };
  const lean = (long - short) / n;
  const side = lean > LEAN_THRESHOLD ? "long" : lean < -LEAN_THRESHOLD ? "short" : "mixed";
  return { n, long, short, lean, side, longUsd: p.long_usd || 0, shortUsd: p.short_usd || 0 };
}

export const longShare = l => (l?.n ? Math.round((100 * l.long) / l.n) : null);

export function usd(x) {
  const a = Math.abs(x || 0);
  return a >= 1e9 ? `$${(a / 1e9).toFixed(1)}B` : a >= 1e6 ? `$${(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `$${Math.round(a / 1e3)}K` : `$${Math.round(a)}`;
}
