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
    return { top, bottom, touched: !!z.touched, direction: z.direction, base: z.base, extreme: z.extreme,
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
// Each entry: a plain title, then short lines in this order: what it is (with this chart's own numbers), how
// traders who follow the method use it, and what a declared study found where one looked (docs/reviews).
// What happened, never what comes next. No trader shorthand without its meaning beside it.

const PREV = { day: "yesterday", week: "last week", month: "last month" };
const THIS = { day: "today", week: "this week", month: "this month" };
const BEGAN = { day: "00:00 UTC", week: "Monday 00:00 UTC", month: "the 1st, 00:00 UTC" };
const cap = str => str[0].toUpperCase() + str.slice(1);
const utcDay = t => new Date(t * 1000).toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });
const when = (start, period) => (period === "day" ? utcDay(start) : `the ${period} of ${utcDay(start)}`);

const POC_USE = "Traders use a price like this as the place to take profit.";
const NAKED_USE = "Traders treat a price like this as a magnet: one the market comes back to.";
const NAKED_TEST = "Tested here: price reached these about as often as any other price the same distance away.";

const openCopy = period => [`${cap(THIS[period])}'s opening price`, [
  `The price when ${THIS[period]} began (${BEGAN[period]}).`,
  `Traders read price above it as buyers being ahead ${THIS[period]}, below it as sellers being ahead.`]];

// The fade of yesterday's extremes was tested (S4); last week's were not.
const extremeCopy = (period, high) => [`${cap(PREV[period])}'s ${high ? "high" : "low"}`, [
  `The ${high ? "highest" : "lowest"} price reached ${PREV[period]}.`,
  high ? "Traders watch for price to poke above it and fall straight back, then sell."
    : "Traders watch for price to dip below it and climb straight back, then buy.",
  period === "day" ? `Tested here: ${high ? "selling those pokes" : "buying those dips"} made nothing before fees and lost after them.` : ""]];

const firstHourCopy = high => [`${high ? "High" : "Low"} of today's first hour`, [
  `The ${high ? "highest" : "lowest"} price in today's first hour (00:00 to 01:00 UTC).`,
  "Traders use the first hour's range as an early gauge: a move beyond it is read as the day picking a direction."]];

const nakedCopy = (start, period) => [`Most-traded price of ${when(start, period)}, not revisited`, [
  `More was traded at this price than at any other that ${period} (its point of control, POC). Price has not been back since.`,
  NAKED_USE, NAKED_TEST]];

// Everything under the pointer: a tag that stands for several levels at one price gives one entry each.
export function describeAll(hit, body, fmt = String) {
  if (hit.kind !== "tick") return [describe(hit, body, fmt)];
  return (hit.tick.members || [hit.tick]).map(t => describe({ kind: "tick", tick: t, bands: hit.bands }, body, fmt));
}

// hit: what ValueAreas.hitTest returned; fmt: how to write a price. Returns { title, tag, price, range, lines }
// (price null where the thing is a band or the histogram; tag is the shorthand drawn on the chart, if any).
export function describe(hit, body, fmt = String) {
  const period = body?.period || "day", outer = body?.outer_period || "week";
  const entry = ([title, lines], extra = {}) => ({ title, tag: null, price: null, range: null, lines: lines.filter(Boolean), ...extra });
  if (hit.kind === "tick") {
    const t = hit.tick, at = { tag: t.label, price: t.price };
    if (t.kind === "fib") return describe({ kind: "fib", band: (hit.bands || [])[Number(String(t.key).split("_")[1])] }, body, fmt);
    if (t.key.startsWith("n_")) return entry(nakedCopy(Number(t.key.slice(2)), outer), at);
    const prev = (body?.outer || []).filter(x => !x.live).slice(-1)[0];
    const band = prev ? `70% of ${PREV[outer]}'s trading happened between ${fmt(prev.val)} and ${fmt(prev.vah)}. ` : "";
    const edge = high => [`${high ? "Top" : "Bottom"} of ${PREV[outer]}'s main trading range`, [
      `${band}This is the ${high ? "top" : "bottom"} of that band (its value area ${high ? "high, VAH" : "low, VAL"}).`,
      `Traders treat the band as ${PREV[outer]}'s fair prices. ${high ? "Above it they watch whether price holds up there or falls back in."
        : "Below it they watch whether price stays down there or climbs back in."}`]];
    const copy = {
      d_open: () => openCopy("day"), w_open: () => openCopy("week"), m_open: () => openCopy("month"),
      pd_high: () => extremeCopy("day", true), pd_low: () => extremeCopy("day", false),
      pw_high: () => extremeCopy("week", true), pw_low: () => extremeCopy("week", false),
      ib_high: () => firstHourCopy(true), ib_low: () => firstHourCopy(false),
      p_vah: () => edge(true), p_val: () => edge(false),
      p_poc: () => [`${cap(PREV[outer])}'s most-traded price`, [
        `More was traded at this price than at any other ${PREV[outer]} (its point of control, POC).`, POC_USE]],
    }[t.key];
    return entry(copy ? copy() : [t.label, []], at);
  }
  if (hit.kind === "fib") {
    const b = hit.band || {};
    const up = b.direction > 0, drawn = b.leg ? " (the dotted line)" : "";
    return entry(["Pullback zone (0.618 to 0.66)", [
      b.base == null ? "" : up
        ? `Price rose from ${fmt(b.base)} to ${fmt(b.extreme)}${drawn}. This band is where a dip has given back about two thirds of that rise (61.8% to 66%).`
        : `Price fell from ${fmt(b.base)} to ${fmt(b.extreme)}${drawn}. This band is where a bounce has taken back about two thirds of that fall (61.8% to 66%).`,
      `Traders use it as the place to ${up ? "buy the dip" : "sell the bounce"}.`,
      "Tested here on 71 coins: after reaching this band, price turned back 47 times in 100 and kept going 53. The same happened at every other distance tested.",
      b.poc ? "A most-traded price (POC) sits inside the band, which traders count as a second reason. Tested here: it made no difference." : "",
      b.touched ? "Price has already traded into this band." : "",
    ]], { range: b.top != null ? [b.bottom, b.top] : null });
  }
  if (hit.kind === "naked") return entry(nakedCopy(hit.s.start, period), { price: hit.s.poc });
  if (hit.kind === "poc") {
    return entry([`Most-traded price, ${when(hit.s.start, period)}`, [
      `More was traded at this price than at any other that ${period}${hit.s.live ? " so far" : ""} (its point of control, POC).`, POC_USE,
    ]], { price: hit.s.poc, tag: hit.s.live ? "so far" : null });
  }
  if (hit.kind === "edge") {
    const high = hit.which === "vah";
    return entry([`${high ? "Top" : "Bottom"} of ${PREV[period]}'s main trading range`, [
      `70% of ${PREV[period]}'s trading happened between ${fmt(hit.s.val)} and ${fmt(hit.s.vah)}. This dashed line is the ${high ? "top" : "bottom"} of that band, carried into ${THIS[period]}.`,
      "Traders watch whether price holds outside the band or comes back in. Their rule: after opening outside and coming back in, price crosses to the other side 8 times in 10.",
      `Tested here${period === "day" ? "" : " on days, not weeks"}: it crossed 4 times in 10.`,
    ]], { price: high ? hit.s.vah : hit.s.val });
  }
  if (hit.kind === "value") {
    return entry([`Main trading range, ${when(hit.s.start, period)}`, [
      `70% of that ${period}'s trading${hit.s.live ? " so far" : ""} happened inside this band (its value area). The gold line is the single most-traded price.`,
      `Traders treat the band as that ${period}'s fair prices and look for trades at its edges.`,
    ]], { range: [hit.s.val, hit.s.vah], tag: hit.s.live ? "so far" : null });
  }
  return entry(["Trading by price", [
    `Each bar is how much was traded at that price over the ${period}s on screen: longer means more.`,
    "Gold is the most-traded price. The brighter bars hold 70% of the trading.",
  ]]);
}

// How far a level is from the last price, as the tip words it ("3.2% above the last price").
export function distanceNote(price, last) {
  if (!(price > 0) || !(last > 0)) return "";
  const d = (price - last) / last * 100;
  if (Math.abs(d) < 0.05) return "at the last price";
  return `${Math.abs(d) >= 10 ? Math.abs(d).toFixed(0) : Math.abs(d).toFixed(1)}% ${d > 0 ? "above" : "below"} the last price`;
}

// The same for a band: to its nearer edge, or that the last price is inside it.
export function rangeNote(range, last) {
  if (!range || !(last > 0)) return "";
  const [lo, hi] = range;
  if (last >= lo && last <= hi) return "the last price is inside";
  return distanceNote(last < lo ? lo : hi, last);
}

// A stable name for what is under the pointer, so the tip is redrawn only when it changes.
export function hitKey(hit) {
  return hit ? `${hit.kind}:${hit.tick?.key ?? hit.s?.start ?? hit.band?.top ?? ""}:${hit.which ?? ""}` : "";
}
