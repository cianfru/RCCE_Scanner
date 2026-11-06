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

// { kind: "down" | "up", today: { start, days, path, low|high, lowDay|highDay }, past: [{ start, end, days, path,
// low|high, lowDay|highDay, btc }], sooner } or null when the latest day sits in neither (no phase known yet).
export function marketCycles(rows, br = broadRuns(rows)) {
  const last = rows[rows.length - 1];
  if (!last) return null;
  const btcOn = new Map(rows.map(r => [r.day, r.btc]));
  const run = br.days.get(last.day);
  if (run) {
    const cur = br.runs[br.runs.length - 1];
    const past = br.runs.filter(r => r.end != null && !r.first).map(r => ({
      start: r.start, end: r.end, days: r.end - r.start, path: pathOf(rows, r.start, r.end), high: r.high, highDay: r.highDay,
      btc: change(btcOn.get(r.start), btcOn.get(r.end)),
    }));
    const days = last.day - cur.start + 1;
    return { kind: "up", today: { start: cur.start, days, path: pathOf(rows, cur.start, last.day), high: cur.high, highDay: cur.highDay },
      past, sooner: past.filter(p => p.days < days).length };
  }
  const dn = br.downDays.get(last.day);
  if (!dn) return null;
  const past = br.downs.filter(x => x.end != null).map(x => ({
    start: x.start, end: x.end, days: x.end - x.start, path: pathOf(rows, x.start, x.end), low: x.low, lowDay: x.lowDay,
    btc: change(btcOn.get(x.start), btcOn.get(x.end)),
  }));
  const days = last.day - dn.start + 1;
  return { kind: "down", today: { start: dn.start, days, path: pathOf(rows, dn.start, last.day), low: dn.low, lowDay: dn.lowDay },
    past, sooner: past.filter(p => p.days < days).length };
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
  lasted: "How long each lasted",
  today: (kind, days) => `today, day ${days}`,
  end: kind => (kind === "down" ? "back to 55%" : "55%"),
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
