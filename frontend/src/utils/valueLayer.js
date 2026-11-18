// The coin chart's Value layer (/api/auction): where each swing's volume profile sits on the chart's own
// candles, the labelled ticks right of the last candle, and what each line and tag is in plain words.
// Pure: ValueAreas.js draws what these return.

const LEVEL_LABELS = { d_open: "D open", pd_high: "PDH", pd_low: "PDL", w_open: "W open", m_open: "M open", pw_high: "PWH", pw_low: "PWL",
  ib_high: "IB high", ib_low: "IB low" };
// The levels each chart shows: the day's on 1H and 4H (the first hour's high and low on 1H only), the week's on 1D.
const LEVELS_OF = {
  "1h": ["d_open", "pd_high", "pd_low", "w_open", "m_open", "ib_high", "ib_low"],
  "4h": ["d_open", "pd_high", "pd_low", "w_open", "m_open"],
  "1d": ["w_open", "m_open", "pw_high", "pw_low"],
};

// The candle a time falls on: the first candle opening at or after it. Past the last candle,
// bars are counted on at the timeframe's spacing.
export function barIndex(times, t, tfSec) {
  const last = times.length - 1;
  if (t > times[last]) return last + Math.ceil((t - times[last]) / tfSec);
  let lo = 0, hi = last;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (times[mid] >= t) hi = mid; else lo = mid + 1; }
  return lo;
}

// The candle a moment is inside: the last candle opening at or before it (the first candle for earlier moments).
export function barAt(times, t) {
  let lo = 0, hi = times.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (times[mid] <= t) lo = mid; else hi = mid - 1; }
  return lo;
}

// Swings with their span in candles: [from, to), from the candle holding the swing's start to the one holding
// its end. Swings that ended before the first candle are dropped; one that began before it is clipped to it.
export function placeRanges(ranges, times) {
  if (!times?.length) return [];
  return (ranges || []).filter(r => r.end > times[0])
    .map(r => ({ ...r, from: barAt(times, r.start), to: barAt(times, r.end - 1) + 1 }))
    .filter(r => r.to > r.from);
}

// The swing whose levels are carried on to the right edge: the last one that has ended.
export const lastDone = placed => placed.filter(r => !r.live).slice(-1)[0] || null;

// Swing highs and lows as price levels (body.swing_levels) on the chart's candles: each from its swing's candle
// (`before`: the swing is older than the first candle) to the candle that traded through it, `to`, null while
// none has. `swept`: an hourly candle then closed back inside it within three days. Levels traded through
// before the first candle are dropped.
export function placeLevels(body, times) {
  if (!times?.length) return [];
  return (body?.swing_levels || []).filter(v => v.taken == null || v.taken >= times[0]).map(v => ({
    ...v, before: v.time < times[0], from: barAt(times, v.time), to: v.taken == null ? null : barAt(times, v.taken), swept: v.back != null }));
}

// The 0.618 to 0.66 retracement bands of the live major legs, with where each starts on the chart's candles
// (the leg's start, or the first candle when that is earlier), the leg itself as a line from its start to its
// extreme (when both are on the chart), and whether a finished swing's point of control sits in the band.
// "In" allows 0.25% beyond the edges.
export const FIB_LABEL = "0.618–0.66";
export function fibBands(body, times, tfSec) {
  if (!times?.length) return [];
  const pocs = (body?.ranges || []).filter(r => !r.live).map(r => r.poc);
  return (body?.fib || []).map(z => {
    const top = Math.max(z.from, z.to), bottom = Math.min(z.from, z.to);
    const onChart = z.base_time >= times[0];
    return { top, bottom, touched: !!z.touched, direction: z.direction, base: z.base, extreme: z.extreme,
      from: onChart ? barIndex(times, z.base_time, tfSec) : 0,
      leg: onChart ? { from: barIndex(times, z.base_time, tfSec), base: z.base, to: barIndex(times, z.extreme_time, tfSec), extreme: z.extreme } : null,
      poc: pocs.some(p => p >= bottom * 0.9975 && p <= top * 1.0025) };
  });
}

// The labelled levels of a chart: opens and prior extremes.
export function ticks(body, tf = "4h") {
  const out = [];
  for (const key of LEVELS_OF[tf] || LEVELS_OF["4h"]) {
    const price = body?.levels?.[key];
    if (Number.isFinite(price)) out.push({ key, label: LEVEL_LABELS[key], price, kind: "level" });
  }
  return out;
}

// The method's rule on a finished swing: with the last price under its value area, its point of control is where
// traders go short if price comes back to it; with the last price over the value area, where they go long.
// null inside the value area, or without a price.
export function pocRule(r, last) {
  if (!r || !(last > 0)) return null;
  return last < r.val ? "short" : last > r.vah ? "long" : null;
}

// The value area and point of control of the last finished swing, as ticks. The POC's tag adds the rule's side
// while the last price is outside the value area.
export function rangeTicks(placed, last) {
  const r = lastDone(placed);
  if (!r) return [];
  const rule = pocRule(r, last);
  return [{ key: "r_vah", label: "VAH", price: r.vah, kind: "edge", range: r },
    { key: "r_poc", label: rule ? `POC \u00b7 ${rule}` : "POC", price: r.poc, kind: "poc", range: r, rule },
    { key: "r_val", label: "VAL", price: r.val, kind: "edge", range: r }];
}

// One tick per retracement band, at its middle.
export function fibTicks(bands) {
  return bands.map((b, i) => ({ key: `fib_${i}`, label: b.poc ? `${FIB_LABEL} · POC` : FIB_LABEL, price: (b.top + b.bottom) / 2, kind: "fib" }));
}

// The rows of a swing's histogram: [{low, high, share (0 to 1 of the fullest row), kind}], kind "poc" for the row
// holding the point of control, "value" inside the value area, "rest" outside it. Empty rows are left out.
export function histogram(r) {
  const b = r?.bins;
  if (!b?.v?.length || !(b.step > 0)) return [];
  const out = [];
  b.v.forEach((v, i) => {
    if (!(v > 0)) return;
    const low = b.low + i * b.step, high = low + b.step, mid = (low + high) / 2;
    out.push({ low, high, share: v / 1000, kind: r.poc >= low && r.poc < high ? "poc" : mid >= r.val && mid <= r.vah ? "value" : "rest" });
  });
  return out;
}

// Label positions: each at its own y unless that would overlap the one above, then pushed
// down to stay `gap` apart. `ys` ascending; returns the adjusted positions.
export function spread(ys, gap) {
  const out = [];
  for (const y of ys) out.push(out.length ? Math.max(y, out[out.length - 1] + gap) : y);
  return out;
}

// Ticks sorted top to bottom, with those less than `within` px apart drawn as one. Labels ending
// in the same word share it ("D open" and "W open" become "D · W open"). A point of control
// keeps its colour in a shared label.
export function mergeTicks(rows, within = 1.5) {
  const out = [];
  for (const t of [...rows].sort((a, b) => a.y - b.y)) {
    const prev = out[out.length - 1];
    if (prev && t.y - prev.y < within) {
      const a = prev.label.split(" "), b = t.label.split(" ");
      const shared = a.length > 1 && b.length === 2 && a[a.length - 1] === b[1];
      prev.label = shared ? `${a.slice(0, -1).join(" ")} · ${b[0]} ${b[1]}` : `${prev.label} · ${t.label}`;
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

const PREV = { day: "yesterday", week: "last week" };
const THIS = { day: "today", week: "this week", month: "this month" };
const BEGAN = { day: "00:00 UTC", week: "Monday 00:00 UTC", month: "the 1st, 00:00 UTC" };
const cap = str => str[0].toUpperCase() + str.slice(1);
const utcDay = t => new Date(t * 1000).toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });

const POC_USE = "Traders use a price like this as the place to take profit.";
const UNTESTED = "Not tested here.";
// docs/reviews/poc-rule-study.md: +0.32% a trade after costs in sample, +0.41% held out, every interval holding zero.
const RULE_TEST = "Tested here on 71 coins since 2021: the rule made about 0.3% a trade after fees, too little to tell from nothing.";

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

const LEVEL_COPY = {
  d_open: () => openCopy("day"), w_open: () => openCopy("week"), m_open: () => openCopy("month"),
  pd_high: () => extremeCopy("day", true), pd_low: () => extremeCopy("day", false),
  pw_high: () => extremeCopy("week", true), pw_low: () => extremeCopy("week", false),
  ib_high: () => firstHourCopy(true), ib_low: () => firstHourCopy(false),
};

// A swing in words: a rise from its low to its high, or a fall from its high to its low.
function move(r, fmt) {
  const up = r.direction > 0;
  return { noun: up ? "rise" : "fall", verb: up ? "rose" : "fell", from: fmt(up ? r.low : r.high), to: fmt(up ? r.high : r.low),
    days: utcDay(r.start) === utcDay(r.end - 1) ? utcDay(r.start) : `${utcDay(r.start)} to ${utcDay(r.end - 1)}` };
}

function rangeCopy(r, fmt) {
  const m = move(r, fmt);
  return [`Trading by price in the ${m.noun}, ${m.days}`, [
    `Price ${m.verb} from ${m.from} to ${m.to}${r.live ? " and the move is still running" : ""}. Each bar is how much was traded at that price on the way: longer means more.`,
    `70% of it was traded between ${fmt(r.val)} and ${fmt(r.vah)} (the value area, the brighter bars). The gold line, ${fmt(r.poc)}, is the single most-traded price (the point of control, POC).`,
    "Traders treat that band as the move's fair prices: they look for trades at its edges and take profit at the most-traded price.",
    UNTESTED]];
}

// rule: "short" or "long" while the last price is outside the swing's value area (pocRule), else null.
function lineCopy(r, which, fmt, rule = null) {
  const m = move(r, fmt), far = r.live ? " so far" : "";
  if (which === "poc") {
    const use = rule === "short" ? `Price is now below the ${m.noun}'s main trading range (under ${fmt(r.val)}). The method's rule then: sell (go short) at this price if price climbs back to it.`
      : rule === "long" ? `Price is now above the ${m.noun}'s main trading range (over ${fmt(r.vah)}). The method's rule then: buy (go long) at this price if price dips back to it.`
        : POC_USE;
    return [`Most-traded price of the ${m.noun}`, [
      `More was traded at this price than at any other in the ${m.noun} from ${m.from} to ${m.to}${far} (its point of control, POC).`, use, rule ? RULE_TEST : UNTESTED]];
  }
  const high = which === "vah";
  return [`${high ? "Top" : "Bottom"} of the ${m.noun}'s main trading range`, [
    `70% of the trading in the ${m.noun} from ${m.from} to ${m.to}${far} happened between ${fmt(r.val)} and ${fmt(r.vah)}. This is the ${high ? "top" : "bottom"} of that band (its value area ${high ? "high, VAH" : "low, VAL"}).`,
    `Traders treat the band as the move's fair prices. ${high ? "Above it they watch whether price holds up there or falls back in."
      : "Below it they watch whether price stays down there or climbs back in."}`,
    UNTESTED]];
}

// A swing high or low as a level: where price turned, what became of it, and how the method's traders use it.
// asOf: when the chart's data was read (seconds), to tell "not within three days" from "not so far".
const SWEEP_WINDOW = 72 * 3600;
function swingLevelCopy(v, fmt, asOf) {
  const high = v.side === "high", past = high ? "above" : "below", back = high ? "under" : "over";
  const made = `Price turned ${high ? "down" : "up"} at ${fmt(v.price)} on ${utcDay(v.time)}`;
  const use = `Traders assume stop orders rest just ${past} a swing ${v.side} like this (they call it liquidity). They wait for price to push through it and close back ${back} it, then trade the other way.`;
  if (v.taken == null) return [`Swing ${v.side} not traded through`, [`${made} and has not traded ${past} it since.`, use, UNTESTED]];
  const went = `On ${utcDay(v.taken)} it traded ${past} it${v.extreme != null ? `, as far as ${fmt(v.extreme)}` : ""}`;
  if (v.back == null) {
    const open = asOf > 0 && asOf - v.taken < SWEEP_WINDOW;
    return [`Swing ${v.side} traded through`, [
      `${made}. ${went}, and no hourly candle ${open ? `has closed back ${back} it so far` : `closed back ${back} it in the three days after`}.`,
      `Traders read a level that price holds beyond as broken: the old ${v.side} is then watched from the other side.`, UNTESTED]];
  }
  const hours = Math.max(1, Math.round((v.back - v.taken) / 3600));
  return [`Swing ${v.side} swept`, [
    `${made}. ${went}, and an hourly candle closed back ${back} it ${hours <= 1 ? "within the hour" : `${hours} hours later`}.`,
    `Traders call this a swing failure when it is quick and a failed auction when it takes hours. They read it as stop orders being filled with no follow-through, and trade back ${high ? "down" : "up"} into the range.`,
    UNTESTED]];
}

// Everything under the pointer: a tag that stands for several levels at one price gives one entry each.
export function describeAll(hit, body, fmt = String) {
  if (hit.kind !== "tick") return [describe(hit, body, fmt)];
  return (hit.tick.members || [hit.tick]).map(t => describe({ kind: "tick", tick: t, bands: hit.bands }, body, fmt));
}

// hit: what ValueAreas.hitTest returned; fmt: how to write a price. Returns { title, tag, price, range, lines }
// (price null where the thing is a band or a profile; tag is the shorthand drawn on the chart, if any).
export function describe(hit, body, fmt = String) {
  const entry = ([title, lines], extra = {}) => ({ title, tag: null, price: null, range: null, lines: lines.filter(Boolean), ...extra });
  if (hit.kind === "tick") {
    const t = hit.tick, at = { tag: t.label, price: t.price };
    if (t.kind === "fib") return describe({ kind: "fib", band: (hit.bands || [])[Number(String(t.key).split("_")[1])] }, body, fmt);
    if (t.range) return entry(lineCopy(t.range, t.key.slice(2), fmt, t.rule), at);
    return entry(LEVEL_COPY[t.key] ? LEVEL_COPY[t.key]() : [t.label, []], at);
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
  if (hit.kind === "rline") {
    return entry(lineCopy(hit.r, hit.which, fmt, hit.rule), { price: hit.r[hit.which], tag: hit.r.live ? "so far" : null });
  }
  if (hit.kind === "level") return entry(swingLevelCopy(hit.v, fmt, body?.as_of), { price: hit.v.price });
  return entry(rangeCopy(hit.r, fmt), { range: [hit.r.low, hit.r.high], tag: hit.r.live ? "so far" : null });
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
  return hit ? `${hit.kind}:${hit.tick?.key ?? hit.r?.start ?? hit.band?.top ?? hit.v?.time ?? ""}:${hit.which ?? hit.v?.side ?? ""}` : "";
}
