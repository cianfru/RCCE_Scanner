// Pure helpers for a coin page's long/short chart (/api/coin-positioning).

// One group's points for a measure: "n" (wallets per side) or "usd" (position value per side).
// A point is { t, long, short }; long and short are null where nothing was recorded (a gap).
export function points(group, measure) {
  if (!group?.t) return [];
  const [lk, sk] = measure === "usd" ? ["lu", "su"] : ["ln", "sn"];
  return group.t.map((t, i) => ({ t, long: group[lk]?.[i] ?? null, short: group[sk]?.[i] ?? null }));
}

// Runs of consecutive recorded points: an area is drawn per run, so gaps stay gaps. Readings are
// 4 hours apart; a longer silence (maxGap, one and a half readings) is a gap too, not a straight line.
export const MAX_GAP_S = 6 * 3600;
export function runs(pts, maxGap = MAX_GAP_S) {
  const out = [];
  let cur = [];
  for (const p of pts) {
    if (p.long == null || p.short == null) { if (cur.length) out.push(cur); cur = []; continue; }
    if (cur.length && p.t - cur[cur.length - 1].t > maxGap) { out.push(cur); cur = []; }
    cur.push(p);
  }
  if (cur.length) out.push(cur);
  return out;
}

// The larger side's peak: long and short share one scale, above and below the line.
export function peak(pts) {
  let m = 0;
  for (const p of pts) m = Math.max(m, p.long || 0, p.short || 0);
  return m;
}

// The recorded point nearest t, if one lies within maxGap seconds.
export function nearest(pts, t, maxGap = 3 * 3600) {
  let best = null;
  for (const p of pts) {
    if (p.long == null) continue;
    if (!best || Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
  }
  return best && Math.abs(best.t - t) <= maxGap ? best : null;
}

// The group's newest recorded point (each group's latest reading can be at a different time).
export function latest(pts) {
  for (let i = pts.length - 1; i >= 0; i--) if (pts[i].long != null) return pts[i];
  return null;
}

// Did anyone in the group hold the coin in this window?
export const everHeld = pts => pts.some(p => (p.long || 0) + (p.short || 0) > 0);
export const recorded = pts => pts.filter(p => p.long != null).length;

// A rounded top for the scale: 1, 2 or 5 times a power of ten.
export function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const m = v / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
}

// Axis label for a scale top from niceMax: "$500M", "$1B", "$20K", or a plain count.
export function tickLabel(v, measure) {
  if (measure !== "usd") return count(v);
  for (const [d, u] of [[1e9, "B"], [1e6, "M"], [1e3, "K"]]) if (v >= d) return `$${+(v / d).toFixed(1)}${u}`;
  return `$${Math.round(v)}`;
}

export function count(v) {
  if (v == null) return "—";
  return v >= 10_000 ? `${Math.round(v / 1000)}K` : String(Math.round(v));
}
