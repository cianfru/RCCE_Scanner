// Pure helpers for the long/short bars under a coin's candles (/api/coin-positioning).

// One group's readings for a measure: "n" (wallets per side) or "usd" (position value per side).
// A point is { t, long, short }; long and short are null where nothing was recorded (a gap).
export function points(group, measure) {
  if (!group?.t) return [];
  const [lk, sk] = measure === "usd" ? ["lu", "su"] : ["ln", "sn"];
  return group.t.map((t, i) => ({ t, long: group[lk]?.[i] ?? null, short: group[sk]?.[i] ?? null }));
}

// The 4h close a stored reading describes. Profitable traders are stored at the close itself;
// the wallet sweep stores the first snapshot after a close (some minutes into the next 4h).
const H4 = 4 * 3600;
export function closeOf(t, group) {
  return group === "profitable" ? Math.round(t / H4) * H4 : Math.floor(t / H4) * H4;
}
// The chart candle that ended at a close (4h or daily), or that contains a moment.
export const candleEndingAt = (end, tfSec) => Math.floor((end - 1) / tfSec) * tfSec;

// One bar pair per candle on the chart: the reading at its close; the current candle shows the
// latest (live) reading. Candles without a reading get no bar (the record is shorter than the
// chart, or nothing was recorded then).
export function candleBars(series, measure, tfSec, candleTimes, group = "profitable") {
  const have = new Set(candleTimes || []);
  const by = new Map();
  const pts = points(series, measure);
  pts.forEach((p, i) => {
    if (p.long == null || p.short == null) return;
    const live = !!series.live && i === pts.length - 1;
    const c = candleEndingAt(live ? p.t + 1 : closeOf(p.t, group), tfSec);
    const prev = by.get(c);
    if (have.has(c) && (!prev || prev.t <= p.t)) by.set(c, { time: c, long: p.long, short: p.short, t: p.t, live });
  });
  return [...by.values()].sort((a, b) => a.time - b.time);
}

// List rebuilds per candle (the candle in which the list changed; a rules change is stamped at
// the close it took effect), joined counts summed.
export function rebuildCandles(rebuilds, tfSec, candleTimes) {
  const have = new Set(candleTimes || []);
  const by = new Map();
  for (const r of rebuilds || []) {
    const c = r.note === "rules" ? candleEndingAt(r.t, tfSec) : Math.floor(r.t / tfSec) * tfSec;
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
