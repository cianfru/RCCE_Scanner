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
      prev.members.push(t);
    } else out.push({ ...t, members: [t] });
  }
  return out;
}

// ─── What a line or tag is, in plain words (shown at the pointer) ────────────────────────────────────────────────
// Each says what the level is and, where a declared study looked at it, what was found (docs/reviews). What
// happened, never what comes next.

const PREV = { day: "yesterday", week: "last week", month: "last month" };
const PREV_S = { day: "Yesterday's", week: "Last week's", month: "Last month's" };
const cap = s => s[0].toUpperCase() + s.slice(1);
const NAKED_NOTE = "Tested here: price came back to levels like this about as often as it reached a price equally far the other way.";
const SWEEP_NOTE = "Traders watch for a push through it that closes back inside. Tested here: fading those made nothing before costs.";

const TICK_COPY = {
  d_open: () => ["Day open", "Where today began, at 00:00 UTC."],
  w_open: () => ["Week open", "Where this week began, Monday 00:00 UTC."],
  m_open: () => ["Month open", "Where this month began."],
  pd_high: () => ["Yesterday's high", `Yesterday's highest price. ${SWEEP_NOTE}`],
  pd_low: () => ["Yesterday's low", `Yesterday's lowest price. ${SWEEP_NOTE}`],
  pw_high: () => ["Last week's high", "Last week's highest price."],
  pw_low: () => ["Last week's low", "Last week's lowest price."],
  ib_high: () => ["First hour's high", "The top of today's first hour, 00:00 to 01:00 UTC."],
  ib_low: () => ["First hour's low", "The bottom of today's first hour, 00:00 to 01:00 UTC."],
  p_vah: o => [`${PREV_S[o]} value area high`, `The top of the band that held 70% of ${PREV[o]}'s volume. Above it, price is outside where most of that business was done.`],
  p_val: o => [`${PREV_S[o]} value area low`, `The bottom of the band that held 70% of ${PREV[o]}'s volume. Below it, price is outside where most of that business was done.`],
  p_poc: o => [`${PREV_S[o]} point of control`, `The price with the most volume ${PREV[o]}. Traders use it as a first exit, not as an entry.`],
};

const utcDay = t => new Date(t * 1000).toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });
const when = (s, period) => (period === "day" ? utcDay(s.start) : `${period} of ${utcDay(s.start)}`);

// Everything under the pointer: a tag that stands for several levels at one price gives one entry each.
export function describeAll(hit, body) {
  if (hit.kind !== "tick") return [describe(hit, body)];
  return (hit.tick.members || [hit.tick]).map(t => describe({ kind: "tick", tick: t, bands: hit.bands }, body));
}

// hit: what ValueAreas.hitTest returned. Returns { title, tag, price, text } (price null for the histogram).
export function describe(hit, body) {
  const period = body?.period || "day", outer = body?.outer_period || "week";
  if (hit.kind === "tick") {
    const t = hit.tick;
    if (t.kind === "fib") return describe({ kind: "fib", band: (hit.bands || [])[Number(String(t.key).split("_")[1])] || { top: t.price, bottom: t.price } }, body);
    if (t.key.startsWith("n_")) {
      return { title: `Older ${outer === "week" ? "weekly" : "monthly"} point of control`, tag: t.label, price: t.price,
        text: `The most-traded price of an earlier ${outer}, not traded back to since. ${NAKED_NOTE}` };
    }
    const [title, text] = (TICK_COPY[t.key] || (() => [t.label, ""]))(outer);
    return { title, tag: t.label, price: t.price, text };
  }
  if (hit.kind === "fib") {
    const b = hit.band;
    return { title: "0.618 to 0.66 pullback zone", tag: null, price: (b.top + b.bottom) / 2,
      text: `Between 61.8% and 66% of the way back along the dotted swing. Tested here: price turned in this zone about as often as at any other depth of a pullback.${b.poc ? " A point of control sits inside it." : ""}` };
  }
  if (hit.kind === "naked") {
    return { title: `Point of control, ${when(hit.s, period)}`, tag: "not traded back to", price: hit.s.poc,
      text: `The price with the most volume that ${period}, not traded back to since. ${NAKED_NOTE}` };
  }
  if (hit.kind === "poc") {
    return { title: `Point of control, ${when(hit.s, period)}`, tag: hit.s.live ? "so far" : null, price: hit.s.poc,
      text: `The price with the most volume that ${period}${hit.s.live ? " so far" : ""}.` };
  }
  if (hit.kind === "edge") {
    const high = hit.which === "vah";
    return { title: `${PREV_S[period]} value area ${high ? "high" : "low"}`, tag: null, price: high ? hit.s.vah : hit.s.val,
      text: `The ${high ? "top" : "bottom"} of the last finished ${period}'s value area, carried forward.${period === "day" ? " Tested here: when a day opened outside this band and came back in, price reached the other edge about 4 times in 10." : ""}` };
  }
  if (hit.kind === "value") {
    return { title: `Value area, ${when(hit.s, period)}`, tag: hit.s.live ? "so far" : null, price: null, range: [hit.s.val, hit.s.vah],
      text: `70% of that ${period}'s volume traded inside this band${hit.s.live ? " so far" : ""}. The gold line is the price with the most.` };
  }
  return { title: "Volume by price", tag: null, price: null,
    text: `How much traded at each price over the ${period}s in view. Gold: the price with the most. Brighter rows: the band that held 70%.` };
}

// How far a level is from the last price, as the tip words it ("3.2% above the last price").
export function distanceNote(price, last) {
  if (!(price > 0) || !(last > 0)) return "";
  const d = (price - last) / last * 100;
  if (Math.abs(d) < 0.05) return "at the last price";
  return `${Math.abs(d) >= 10 ? Math.abs(d).toFixed(0) : Math.abs(d).toFixed(1)}% ${d > 0 ? "above" : "below"} the last price`;
}

// A stable name for what is under the pointer, so the tip is redrawn only when it changes.
export function hitKey(hit) {
  return hit ? `${hit.kind}:${hit.tick?.key ?? hit.s?.start ?? hit.band?.top ?? ""}:${hit.which ?? ""}` : "";
}
