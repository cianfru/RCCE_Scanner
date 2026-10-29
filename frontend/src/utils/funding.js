// BTC and ETH funding for the market history page's Chart view (/api/market-history/funding): what leveraged longs
// paid shorts each day, summed per UTC day as a yearly rate in percent. The pane draws the 7-day mean of the two
// coins' average, as the turn-signs study reads it (docs/reviews/turn-signs-study.md); Hyperliquid's base rate when
// longs and shorts are even is about 11% a year. Context, not a signal.

export const NEUTRAL = 10.95;     // 0.00125% an hour: Hyperliquid's interest part, with no premium either way
const WINDOW = 7, MIN_DAYS = 5;

// {feed} -> Map(day -> { btc, eth, avg, avg7 }); avg7 needs 5 of the last 7 days.
export function fundingByDay(feed) {
  const cols = feed?.columns || [];
  const ix = Object.fromEntries(cols.map((c, i) => [c, i]));
  const out = new Map();
  if (ix.day == null) return out;
  for (const r of feed.rows || []) {
    const btc = r[ix.btc], eth = r[ix.eth];
    if (btc == null || eth == null) continue;
    out.set(r[ix.day], { btc, eth, avg: (btc + eth) / 2, avg7: null });
  }
  for (const [day, v] of out) {
    const w = [];
    for (let k = 0; k < WINDOW; k++) { const x = out.get(day - k); if (x) w.push(x.avg); }
    if (w.length >= MIN_DAYS) v.avg7 = w.reduce((a, b) => a + b, 0) / w.length;
  }
  return out;
}

export const FCOPY = {
  label: "Funding (BTC and ETH)",
  legend: v => `${Math.round(v.avg7)}% a year · BTC ${Math.round(v.btc)}% · ETH ${Math.round(v.eth)}%`,
};
