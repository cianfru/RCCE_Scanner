import { broadRuns } from "./marketHeat.js";

// The market page's Cycles tab: each past broad downturn (or, while the market is in a broad uptrend, each past broad
// uptrend) as a path of the share of coins in uptrend from its first day, its length, and today's alongside. Day 1 is
// the first day; a past one's length is its number of days (its end is the first day of the next phase), and today's
// count includes today, so the two read on one scale ("3 of 13 ended sooner": 3 lasted fewer days than today's has).
// What happened, not what comes next.

// One phase's path: [{ d (day 1, 2, ...), day, v (share 0-1) }], from its start to `last` (included).
function pathOf(rows, start, last) {
  return rows.filter(r => r.day >= start && r.day <= last && r.uptrend != null).map(r => ({ d: r.day - start + 1, day: r.day, v: r.uptrend }));
}

const change = (a, b) => (a > 0 && b > 0 ? b / a - 1 : null);

// { kind: "down" | "up", now: the phase the latest day is in ("down", "up" or null), today: { start, days, path,
// low|high, lowDay|highDay } or null when `kind` is not the phase under way, past: [{ start, end, days, path, low|high,
// lowDay|highDay, btc }], sooner (past ones shorter than today's, or null), latest (index of the most recent past one) }.
// `want` picks the phase to show; by default the one under way. The phase switches by itself: a broad uptrend starts on
// the first day at 55% or more of coins in uptrend and ends on the first of 5 days in a row under 55%.
export function marketCycles(rows, br = broadRuns(rows), want = null) {
  const last = rows[rows.length - 1];
  if (!last) return null;
  const now = br.days.has(last.day) ? "up" : br.downDays.has(last.day) ? "down" : null;
  const kind = want || now;
  if (!kind) return null;
  const btcOn = new Map(rows.map(r => [r.day, r.btc]));
  const past = kind === "up"
    ? br.runs.filter(r => r.end != null && !r.first).map(r => ({
        start: r.start, end: r.end, days: r.end - r.start, path: pathOf(rows, r.start, r.end), high: r.high, highDay: r.highDay,
        btc: change(btcOn.get(r.start), btcOn.get(r.end)) }))
    : br.downs.filter(x => x.end != null).map(x => ({
        start: x.start, end: x.end, days: x.end - x.start, path: pathOf(rows, x.start, x.end), low: x.low, lowDay: x.lowDay,
        btc: change(btcOn.get(x.start), btcOn.get(x.end)) }));
  let today = null;
  if (kind === now && kind === "up") {
    const cur = br.runs[br.runs.length - 1];
    today = { start: cur.start, days: last.day - cur.start + 1, path: pathOf(rows, cur.start, last.day), high: cur.high, highDay: cur.highDay };
  } else if (kind === now) {
    const dn = br.downDays.get(last.day);
    today = { start: dn.start, days: last.day - dn.start + 1, path: pathOf(rows, dn.start, last.day), low: dn.low, lowDay: dn.lowDay };
  }
  const latest = past.length ? past.reduce((k, p, i) => (p.start > past[k].start ? i : k), 0) : null;
  return { kind, now, today, past, latest, sooner: today ? past.filter(p => p.days < today.days).length : null };
}

// Where a value sits among past values, in words a person reads at a glance: "lower than on 2 in 3 days".
export function shareBelow(values, v) {
  const xs = values.filter(x => x != null);
  if (!xs.length || v == null) return null;
  return xs.filter(x => x < v).length / xs.length;
}

export const CYCOPY = {
  tab: "Cycles",
  head: kind => (kind === "down" ? "Every broad downturn since 2021, from its first day" : "Every broad uptrend since 2021, from its first day"),
  kinds: [{ key: "down", label: "Downturns" }, { key: "up", label: "Uptrends" }],
  latest: (p, fmtMonth) => `last one, ${fmtMonth(p.start)}: ${p.days} days`,
  lasted: "How long each lasted",
  today: (kind, days) => `today, day ${days}`,
  end: kind => (kind === "down" ? "back to 55%" : "ends 5 days under 55%"),
  sooner: (k, n, kind) => `${k} of ${n} ended sooner`,
  dayAxis: "day",
  tip: (p, kind, fmtDay) => [
    `${fmtDay(p.start)} – ${fmtDay(p.end - 1)}`,
    `${p.days} days`,
    kind === "down" ? `lowest ${Math.round(100 * p.low)}% of coins in uptrend` : `highest ${Math.round(100 * p.high)}% of coins in uptrend`,
    p.btc == null ? null : `BTC ${p.btc >= 0 ? "+" : "−"}${Math.abs(Math.round(100 * p.btc))}% over it`,
  ].filter(Boolean),
  pop: kind => kind === "down"
    ? ["A broad downturn starts when a broad uptrend ends (5 days in a row with under 55% of coins in uptrend) and lasts until 55% of coins are in uptrend again.",
       "Each grey line is one past downturn, from its first day; the dot is the day it ended. Today's is the coloured line. The bars below show how long each lasted. What happened, not what comes next."]
    : ["A broad uptrend starts when 55% of coins are in uptrend and ends on the first of 5 days in a row under 55%.",
       "Each grey line is one past uptrend, from its first day; the dot is the day it ended. Today's is the coloured line. The bars below show how long each lasted. What happened, not what comes next."],
};

// A reading `days` before the latest one: the last point on or before (latest day - days). points: [{ day, v }], oldest
// first. { day, v } or null. "Yesterday" and "a week ago" on the market page's tiles.
export function readingAgo(points, days) {
  const xs = points.filter(p => p.v != null);
  if (!xs.length) return null;
  const at = xs[xs.length - 1].day - days;
  for (let i = xs.length - 1; i >= 0; i--) if (xs[i].day <= at) return xs[i];
  return null;
}
