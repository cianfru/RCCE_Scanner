// The scanner's list of long signals (components/LongsNow.jsx): the coins with a long signal on the timeframe, in
// the scanner's priority order, each joined to its Radar reading (strength against the median coin, profitable
// traders, band distance, heat signs). Ordering stays the priority score: the ranking study
// (docs/reviews/ranking-study.md) found strength against the market did not pick better trades. Context only.

export const LONG_SIGNALS = new Set(["STRONG_LONG", "LIGHT_LONG", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"]);
export const SIGNAL_WORD = { STRONG_LONG: "Strong", LIGHT_LONG: "Light", REVIVAL_SEED: "Revival", REVIVAL_SEED_CONFIRMED: "Revival" };

// rows: the scan's rows for the timeframe; coins: the setup map's coins. Returns [{row, c}] sorted by priority
// (highest first), then by name.
export function longsNow(rows, coins) {
  const by = new Map((coins || []).map(c => [c.symbol, c]));
  return (rows || []).filter(r => LONG_SIGNALS.has(r.signal) && (r.market_kind || "perpetual") === "perpetual")
    .map(r => ({ row: r, c: by.get(r.symbol) || null }))
    .sort((a, b) => (b.row.priority_score || 0) - (a.row.priority_score || 0) || String(a.row.symbol).localeCompare(String(b.row.symbol)));
}

// Bar for the strength column: share of the half-width for a value in percent, capped at `cap`.
export const strengthBar = (v, cap = 40) => (v == null ? 0 : Math.max(-1, Math.min(1, v / cap)));

const MINUS = "−";
export const pctText = v => (v == null ? "-" : `${v > 0 ? "+" : v < 0 ? MINUS : ""}${Math.abs(v) >= 10 ? Math.round(Math.abs(v)) : Math.abs(v).toFixed(1)}%`);
