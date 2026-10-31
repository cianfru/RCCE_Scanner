// Pure helpers for the long/short bars under a coin's candles (/api/coin-positioning).

// One group's readings for a measure: "n" (wallets per side) or "usd" (position value per side).
// A point is { t, long, short }; long and short are null where nothing was recorded (a gap).
export function points(group, measure) {
  if (!group?.t) return [];
  const [lk, sk] = measure === "usd" ? ["lu", "su"] : ["ln", "sn"];
  return group.t.map((t, i) => ({ t, long: group[lk]?.[i] ?? null, short: group[sk]?.[i] ?? null }));
}

// Readings are taken at a candle's close (profitable traders) or up to about 25 minutes after it
// (the wallet sweep, after the quiet window): those belong to the candle that just closed.
export const SETTLE_S = 30 * 60;
export const candleOf = (t, tfSec) => Math.floor((t - SETTLE_S) / tfSec) * tfSec;

// One bar pair per candle on the chart: the last reading that belongs to it. Candles without a
// reading get no bar (the record is shorter than the chart, or nothing was recorded then).
export function candleBars(group, measure, tfSec, candleTimes) {
  const have = new Set(candleTimes || []);
  const by = new Map();
  for (const p of [...points(group, measure)].sort((a, b) => a.t - b.t)) {
    if (p.long == null || p.short == null) continue;
    const c = candleOf(p.t, tfSec);
    if (have.has(c)) by.set(c, { time: c, long: p.long, short: p.short, t: p.t });
  }
  return [...by.values()].sort((a, b) => a.time - b.time);
}

// List rebuilds per candle (the candle in which the list changed), joined counts summed.
export function rebuildCandles(rebuilds, tfSec, candleTimes) {
  const have = new Set(candleTimes || []);
  const by = new Map();
  for (const r of rebuilds || []) {
    const c = Math.floor(r.t / tfSec) * tfSec;
    if (!have.has(c)) continue;
    const e = by.get(c) || { time: c, joined: 0, left: 0, rules: false };
    e.joined += r.joined || 0;
    e.left += r.left || 0;
    e.rules = e.rules || r.note === "rules";
    by.set(c, e);
  }
  return [...by.values()].sort((a, b) => a.time - b.time);
}

// The group's newest recorded point (each group's latest reading can be at a different time).
export function latest(pts) {
  for (let i = pts.length - 1; i >= 0; i--) if (pts[i].long != null) return pts[i];
  return null;
}
export const recorded = pts => pts.some(p => p.long != null);

export function count(v) {
  if (v == null) return "—";
  return v >= 10_000 ? `${Math.round(v / 1000)}K` : String(Math.round(v));
}
