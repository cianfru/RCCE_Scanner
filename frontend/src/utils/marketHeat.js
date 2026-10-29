// Market heat, for the market history page's Chart view: how stretched the market reads on a day, as the plain
// average of three readings on one 0-100 scale: the share of coins in uptrend, Fear & Greed, and the share of the
// profitable traders' positions that are long (where the wallet feed has them, from October 2025; before that the
// first two). The three tend to rise together after a rally, so a high reading says the market is stretched, not
// what comes next. Context, not a signal (docs/reviews/market-heat.md).

export const HOT = 75;            // at or above: hot
export const COLD = 25;           // at or below: cold
export const TURN = 10;           // points off a hot episode's peak (or up from a cold one's trough) that mark a turn
export const TURN_DAYS = 21;      // ...counted only within this many days of the peak (or trough)
export const STATE_DAYS = 30;     // a turn's state ("Cooling", "Lifting") is shown for at most this many days

// One day's heat from a market history row joined with Fear & Greed (0-100) and the wallet groups: { heat, parts, n },
// or null without the Uptrend share and at least one other reading.
export function heatOf(r) {
  const parts = {
    uptrend: r?.uptrend == null ? null : 100 * r.uptrend,
    fg: r?.fg == null ? null : r.fg,
    traders: r?.wallet?.crowd?.L == null ? null : 100 * r.wallet.crowd.L,
  };
  if (parts.uptrend == null) return null;
  const vals = Object.values(parts).filter(v => v != null);
  if (vals.length < 2) return null;
  return { heat: vals.reduce((a, b) => a + b, 0) / vals.length, parts, n: vals.length };
}

// [{ day, heat, parts, n }] for the rows that have a heat, oldest first.
export function heatSeries(rows) {
  const out = [];
  for (const r of rows) {
    const h = heatOf(r);
    if (h) out.push({ day: r.day, ...h });
  }
  return out;
}

// Turns: "cooling" on the first day the heat is TURN points under the peak of a hot episode (a run that reached HOT),
// within TURN_DAYS of that peak; "lifting" on the first day it is TURN points over a cold episode's trough. One turn per
// episode: a new one needs the heat back at HOT (or COLD) first. [{ day, kind, from: { day, heat } }].
export function heatTurns(series) {
  const out = [];
  let peak = null, trough = null;
  for (const s of series) {
    if (s.heat >= HOT && (!peak || s.heat > peak.heat)) peak = { day: s.day, heat: s.heat };
    if (s.heat <= COLD && (!trough || s.heat < trough.heat)) trough = { day: s.day, heat: s.heat };
    if (peak && s.day - peak.day > TURN_DAYS && s.heat < HOT) peak = null;
    if (trough && s.day - trough.day > TURN_DAYS && s.heat > COLD) trough = null;
    if (peak && s.heat <= peak.heat - TURN) {
      out.push({ day: s.day, kind: "cooling", from: peak });
      peak = null;
    }
    if (trough && s.heat >= trough.heat + TURN) {
      out.push({ day: s.day, kind: "lifting", from: trough });
      trough = null;
    }
  }
  return out;
}

// Today's state: "Cooling" or "Lifting" for STATE_DAYS after a turn (until the heat makes a new extreme past the one it
// turned from), else "Hot" or "Cold" by zone, else "Neutral". { word, since (day or null), heat }.
export function heatState(series, turns = heatTurns(series)) {
  const last = series[series.length - 1];
  if (!last) return null;
  const t = turns[turns.length - 1];
  if (t && last.day - t.day <= STATE_DAYS) {
    const after = series.filter(s => s.day > t.day);
    const renewed = t.kind === "cooling" ? after.some(s => s.heat > t.from.heat) : after.some(s => s.heat < t.from.heat);
    if (!renewed) return { word: t.kind === "cooling" ? "Cooling" : "Lifting", since: t.day, heat: last.heat };
  }
  if (last.heat >= HOT || last.heat <= COLD) {
    const hot = last.heat >= HOT;
    let i = series.length - 1;
    while (i > 0 && (hot ? series[i - 1].heat >= HOT : series[i - 1].heat <= COLD)) i--;
    return { word: hot ? "Hot" : "Cold", since: series[i].day, heat: last.heat };
  }
  return { word: "Neutral", since: null, heat: last.heat };
}

// The zone a heat value sits in: "hot", "cold" or null.
export const zoneOf = v => (v == null ? null : v >= HOT ? "hot" : v <= COLD ? "cold" : null);

// ---------------------------------------------------------------- the Chart view's indicators

// On the price pane or in a pane of their own below it; `on` ones show the first time the page opens.
export const INDICATORS = [
  { key: "band", label: "BTC weekly band", where: "price", on: true },
  { key: "zones", label: "Hot and cold days", where: "price", on: true },
  { key: "turns", label: "Heat turns", where: "price", on: true },
  { key: "heat", label: "Market heat", where: "pane", on: true },
  { key: "uptrend", label: "Uptrend share", where: "pane", on: true },
  { key: "crowd", label: "Profitable traders", where: "pane", on: true },
  { key: "fg", label: "Fear & Greed", where: "pane", on: false },
  { key: "smart", label: "Smart money", where: "pane", on: false },
  { key: "whales", label: "Whales", where: "pane", on: false },
  { key: "median_z", label: "Median z", where: "pane", on: false },
  { key: "derive", label: "Derive Smart wallets", where: "pane", on: false },
];
export const DEFAULT_ON = INDICATORS.filter(i => i.on).map(i => i.key);

// The indicators to draw from a saved list: known keys only, in the catalogue's order; the defaults when none is saved.
export function pickIndicators(saved) {
  const keys = Array.isArray(saved) ? saved : DEFAULT_ON;
  return INDICATORS.map(i => i.key).filter(k => keys.includes(k));
}

export const HCOPY = {
  title: "Market heat",
  states: { Hot: "Hot", Cooling: "Cooling", Cold: "Cold", Lifting: "Lifting", Neutral: "Neutral" },
  parts: { uptrend: "Uptrend", fg: "Fear & Greed", traders: "Traders long" },
  since: d => `since ${d}`,
  indicators: "Indicators",
  onPrice: "On the price",
  below: "Below the price",
  pop: () => [
    `The average of three readings, each 0 to 100: the share of coins in uptrend, Fear & Greed, and the share of the profitable traders' positions that are long (from October 2025; before, the first two). Hot from ${HOT}, cold at ${COLD} or under.`,
    `A turn is ${TURN} points off a hot peak (cooling) or up from a cold trough (lifting) within ${TURN_DAYS} days. The three rise together after rallies, so heat describes how stretched the market is, not what comes next. Context, not a signal.`,
  ],
};
