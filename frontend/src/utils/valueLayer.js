// The coin chart's Value layer (/api/auction): where sessions sit on the chart's own candles,
// the labelled ticks right of the last candle, and the volume by price of the sessions in view.
// Pure: ValueAreas.js draws what these return.

export const VALUE_SHARE = 0.7;

const LEVEL_LABELS = { d_open: "D open", pd_high: "PDH", pd_low: "PDL", w_open: "W open", m_open: "M open", pw_high: "PWH", pw_low: "PWL" };
const FIRST_HOUR_LABELS = { ib_high: "IB high", ib_low: "IB low" };   // the day's first hour: readable on the 1-hour chart only
const PERIOD_LETTER = { day: "D", week: "W", month: "M" };

// The candle a time falls on: the first candle opening at or after it. Past the last candle,
// bars are counted on at the timeframe's spacing (a session still running ends there).
export function barIndex(times, t, tfSec) {
  const last = times.length - 1;
  if (t > times[last]) return last + Math.ceil((t - times[last]) / tfSec);
  let lo = 0, hi = last;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (times[mid] >= t) hi = mid; else lo = mid + 1; }
  return lo;
}

// Sessions with their span in candles: [from, to). Sessions that ended before the first candle are dropped.
export function placeSessions(sessions, times, tfSec) {
  if (!times?.length) return [];
  return (sessions || []).filter(s => s.end > times[0])
    .map(s => ({ ...s, from: barIndex(times, s.start, tfSec), to: barIndex(times, s.end, tfSec) }))
    .filter(s => s.to > s.from);
}

// The 0.618 to 0.66 retracement bands of the live major legs, with where each starts on the chart's candles
// (the leg's start, or the first candle when that is earlier), the leg itself as a line from its start to its
// extreme (when both are on the chart), and whether a point of control sits in the band:
// the previous outer session's, or one price has not traded back to. "In" allows 0.25% beyond the edges.
export const FIB_LABEL = "0.618\u20130.66";
export function fibBands(body, times, tfSec) {
  if (!times?.length) return [];
  const done = (body?.outer || []).filter(s => !s.live);
  const pocs = [
    ...done.filter((s, i) => i === done.length - 1 || s.touched == null).map(s => s.poc),
    ...(body?.sessions || []).filter(s => !s.live && s.touched == null).map(s => s.poc),
  ];
  return (body?.fib || []).map(z => {
    const top = Math.max(z.from, z.to), bottom = Math.min(z.from, z.to);
    const onChart = z.base_time >= times[0];
    return { top, bottom, touched: !!z.touched, direction: z.direction,
      from: onChart ? barIndex(times, z.base_time, tfSec) : 0,
      leg: onChart ? { from: barIndex(times, z.base_time, tfSec), base: z.base, to: barIndex(times, z.extreme_time, tfSec), extreme: z.extreme } : null,
      poc: pocs.some(p => p >= bottom * 0.9975 && p <= top * 1.0025) };
  });
}

// The labelled levels: opens and prior extremes, the last finished outer session's value area
// (the previous week under days, the previous month under weeks), and older outer points of
// control price has not traded back to.
export function ticks(body, { firstHour = false } = {}) {
  const out = [];
  for (const [key, label] of Object.entries(firstHour ? { ...LEVEL_LABELS, ...FIRST_HOUR_LABELS } : LEVEL_LABELS)) {
    const price = body?.levels?.[key];
    if (Number.isFinite(price)) out.push({ key, label, price, kind: "level" });
  }
  const letter = PERIOD_LETTER[body?.outer_period] || "";
  const done = (body?.outer || []).filter(s => !s.live);
  const prev = done[done.length - 1];
  if (prev) {
    out.push({ key: "p_vah", label: `P${letter} VAH`, price: prev.vah, kind: "edge" });
    out.push({ key: "p_poc", label: `P${letter} POC`, price: prev.poc, kind: "poc" });
    out.push({ key: "p_val", label: `P${letter} VAL`, price: prev.val, kind: "edge" });
  }
  for (const s of done.slice(0, -1)) {
    if (s.touched == null) out.push({ key: `n_${s.start}`, label: `${letter} nPOC`, price: s.poc, kind: "poc" });
  }
  return out;
}

// One tick per retracement band, at its middle.
export function fibTicks(bands) {
  return bands.map((b, i) => ({ key: `fib_${i}`, label: b.poc ? `${FIB_LABEL} \u00b7 POC` : FIB_LABEL, price: (b.top + b.bottom) / 2, kind: "fib" }));
}

// POC row and value-area rows of a profile: the same rule as the backend (two rows at a time
// towards the side with more volume, until 70% of the volume is inside; ties go up).
export function valueArea(v, share = VALUE_SHARE) {
  const n = v.length;
  let max = 0, total = 0;
  for (const x of v) { if (x > max) max = x; total += x; }
  if (!(total > 0)) return null;
  let poc = -1, best = Infinity;
  for (let i = 0; i < n; i++) {
    if (v[i] === max && Math.abs(i - (n - 1) / 2) < best) { poc = i; best = Math.abs(i - (n - 1) / 2); }
  }
  let lo = poc, hi = poc, held = v[poc];
  const pair = (a, b) => (v[a] || 0) + (v[b] || 0);
  while (held < share * total && (lo > 0 || hi < n - 1)) {
    const up = hi < n - 1 ? pair(hi + 1, hi + 2) : -1;
    const down = lo > 0 ? pair(lo - 1, lo - 2) : -1;
    if (up >= down) { hi = Math.min(hi + 2, n - 1); held += up; }
    else { lo = Math.max(lo - 2, 0); held += down; }
  }
  return { poc, lo, hi, max };
}

// Volume by price of the sessions overlapping candles [from, to], on the layer's coarse grid.
export function composite(placed, rows, from, to) {
  const v = new Array(rows).fill(0);
  let any = false;
  for (const s of placed) {
    if (!s.bins || s.to <= from || s.from > to) continue;
    any = true;
    s.bins.v.forEach((x, i) => { if (s.bins.from + i < rows) v[s.bins.from + i] += x; });
  }
  const area = any ? valueArea(v) : null;
  return area ? { v, ...area } : null;
}

// Label positions: each at its own y unless that would overlap the one above, then pushed
// down to stay `gap` apart. `ys` ascending; returns the adjusted positions.
export function spread(ys, gap) {
  const out = [];
  for (const y of ys) out.push(out.length ? Math.max(y, out[out.length - 1] + gap) : y);
  return out;
}

// Ticks sorted top to bottom, with those less than `within` px apart drawn as one. Labels ending
// in the same word share it ("D open" and "W open" become "D \u00b7 W open"). A point of control
// keeps its colour in a shared label.
export function mergeTicks(rows, within = 1.5) {
  const out = [];
  for (const t of [...rows].sort((a, b) => a.y - b.y)) {
    const prev = out[out.length - 1];
    if (prev && t.y - prev.y < within) {
      const a = prev.label.split(" "), b = t.label.split(" ");
      const shared = a.length > 1 && b.length === 2 && a[a.length - 1] === b[1];
      prev.label = shared ? `${a.slice(0, -1).join(" ")} \u00b7 ${b[0]} ${b[1]}` : `${prev.label} \u00b7 ${t.label}`;
      if (t.kind === "poc") prev.kind = "poc";
    } else out.push({ ...t });
  }
  return out;
}
