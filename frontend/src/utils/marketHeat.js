// Market heat, for the market history page's Chart view: how stretched the market reads on a day, as the plain
// average of three readings on one 0-100 scale: the share of coins in uptrend, Fear & Greed, and the share of the
// profitable traders' positions that are long (where the wallet feed has them, from October 2025; before that the
// first two). The three tend to rise together after a rally, so a high reading says the market is stretched, not
// what comes next. Context, not a signal (docs/reviews/market-heat.md).
// Broad uptrends lead the view (owner, 29 October 2026: the share of coins in uptrend matters as much as BTC): how
// long the market has been in one against past runs, its high, and three marks (docs/reviews/late-uptrends-study.md;
// owner, same day: "60 days was just an example", so age reads against past runs, not a fixed day, and greed counts
// over the last 30 days).

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

// ---------------------------------------------------------------- broad uptrends (docs/reviews/late-uptrends-study.md)

export const ON = 0.55;           // a broad uptrend: 55% or more of coins in uptrend...
export const OFF_DAYS = 5;        // ...until the 5th day in a row under 55% (shorter dips stay inside)
export const ROLL = 0.2;          // rolled over: 20 points under the run's high so far
export const GREED = 70;          // Fear & Greed at or above: the engine's own line (its Not greedy check fails)...
export const LOOKBACK = 30;       // ...at some point in the last 30 days
export const CROWD = 0.86;        // profitable traders' share long at or above: the positioning study's extreme-long line
// Turning points (docs/reviews/turning-points-study.md): the median z 0.75 off the run's high (or the downturn's low);
// in downturns, extreme fear (Fear & Greed 25 or less in the last 30 days) and traders short (30% or less long).
export const Z_TURN = 0.75;
export const FEAR = 25;
export const SHORT = 0.3;

// Broad uptrends and the downturns between them as known on each day (research/late_uptrends.py, turning_points.py):
// { days: Map(day -> { start, age, high, rolled, zTurned }), runs: [{ start, end (first day of the 5 under 55%, null
// while on), first (under way on the first day, start unknown), high, highDay, roll, zTurn }], downDays: Map(day ->
// { start, age, low, lowDay, turned, zUp }) for the days outside a run, downs: [{ start, end (next run's start, null
// while on), low, lowDay, turnUp, zTurnUp }] }.
export function broadRuns(rows) {
  const days = new Map();
  const runs = [];
  let cur = null, below = 0;
  rows.forEach((r, i) => {
    const s = r.uptrend, z = r.median_z;
    if (!cur) {
      if (s == null || s < ON) return;
      cur = { start: r.day, end: null, first: i === 0, high: s, highDay: r.day, roll: null, zHigh: null, zTurn: null };
      below = 0;
    } else {
      below = s == null || s < ON ? below + 1 : 0;
      if (below >= OFF_DAYS) {
        cur.end = rows[i - OFF_DAYS + 1].day;
        // Once the run has ended, its last dip (the days from its end) belongs to the downturn, as its end date says.
        for (let k = i - OFF_DAYS + 1; k < i; k++) days.delete(rows[k].day);
        runs.push(cur);
        cur = null;
        return;
      }
    }
    if (s != null && s > cur.high) { cur.high = s; cur.highDay = r.day; }
    if (cur.roll == null && s != null && cur.high - s >= ROLL - 1e-9) { cur.roll = r.day; cur.rollFrom = { v: cur.high, day: cur.highDay }; }
    if (z != null) {
      cur.zHigh = cur.zHigh == null ? z : Math.max(cur.zHigh, z);
      if (cur.zTurn == null && cur.zHigh - z >= Z_TURN - 1e-9) cur.zTurn = r.day;
    }
    days.set(r.day, { start: cur.start, age: r.day - cur.start, high: cur.high, rolled: cur.roll != null,
                      zTurned: cur.zTurn != null });
  });
  if (cur) runs.push(cur);
  const downDays = new Map();
  const downs = runs.filter(run => run.end != null).map(run => {
    const next = runs.find(x => x.start > run.end);
    const dn = { start: run.end, end: next ? next.start : null, low: null, lowDay: null, turnUp: null, zLow: null, zTurnUp: null };
    for (const r of rows) {
      if (r.day < dn.start || (dn.end != null && r.day >= dn.end)) continue;
      if (r.uptrend != null) {
        if (dn.low == null || r.uptrend < dn.low) { dn.low = r.uptrend; dn.lowDay = r.day; }
        if (dn.turnUp == null && r.uptrend - dn.low >= ROLL - 1e-9) { dn.turnUp = r.day; dn.turnFrom = { v: dn.low, day: dn.lowDay }; }
      }
      if (r.median_z != null) {
        dn.zLow = dn.zLow == null ? r.median_z : Math.min(dn.zLow, r.median_z);
        if (dn.zTurnUp == null && r.median_z - dn.zLow >= Z_TURN - 1e-9) dn.zTurnUp = r.day;
      }
      if (!days.has(r.day)) {
        downDays.set(r.day, { start: dn.start, age: r.day - dn.start, low: dn.low, lowDay: dn.lowDay,
                              turned: dn.turnUp != null, zUp: dn.zTurnUp != null });
      }
    }
    return dn;
  });
  return { days, runs, downDays, downs };
}

// The latest day's reading. Inside a broad uptrend: its age against the past runs (how many ended sooner), its high,
// the highest Fear & Greed of the last 30 days and the marks. In a downturn: the same against past downturns, its low,
// the lowest Fear & Greed of the last 30 days and the downturn's marks.
export function broadState(rows, br = broadRuns(rows)) {
  const last = rows[rows.length - 1];
  if (!last || last.uptrend == null) return null;
  const fgs = rows.filter(r => r.day > last.day - LOOKBACK && r.fg != null).map(r => r.fg);
  const crowd = last.wallet?.crowd?.L;
  const d = br.days.get(last.day);
  if (d) {
    const past = br.runs.filter(r => r.end != null && !r.first);
    const fgHigh = fgs.length ? Math.max(...fgs) : null;
    return {
      on: true, share: last.uptrend, age: d.age, run: br.runs[br.runs.length - 1], fgHigh,
      longer: { k: past.filter(r => r.end - r.start < d.age).length, n: past.length },
      marks: { greed: fgHigh != null && fgHigh >= GREED, crowd: crowd != null && crowd >= CROWD, zturn: d.zTurned,
               rolled: d.rolled },
    };
  }
  const dn = br.downDays.get(last.day);
  const run = br.runs.filter(r => r.end != null).pop() || null;
  if (!dn) return { on: false, share: last.uptrend, run, down: null };
  const past = br.downs.filter(x => x.end != null);
  const fgLow = fgs.length ? Math.min(...fgs) : null;
  return {
    on: false, share: last.uptrend, run, age: dn.age, down: dn, fgLow,
    longer: { k: past.filter(x => x.end - x.start < dn.age).length, n: past.length },
    marks: { fear: fgLow != null && fgLow <= FEAR, short: crowd != null && crowd <= SHORT, zup: dn.zUp, turned: dn.turned },
  };
}

// ---------------------------------------------------------------- the Chart view's indicators

// On the price pane or in a pane of their own below it; `on` ones show the first time the page opens.
export const INDICATORS = [
  { key: "band", label: "BTC weekly band", where: "price", on: true },
  { key: "runs", label: "Broad uptrends", where: "price", on: true },
  { key: "zturns", label: "Median z turns", where: "price", on: true },
  { key: "turns", label: "Heat turns", where: "price", on: true },
  { key: "zones", label: "Hot and cold days", where: "price", on: false },
  { key: "uptrend", label: "Uptrend share", where: "pane", on: true },
  { key: "fg", label: "Fear & Greed", where: "pane", on: true },
  { key: "crowd", label: "Profitable traders", where: "pane", on: true },
  { key: "heat", label: "Market heat", where: "pane", on: false },
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

export const BCOPY = {
  title: "Coins in uptrend",
  on: age => `Broad uptrend, day ${age}`,
  high: (v, d) => `high ${v} on ${d}`,
  ended: (d, n) => `Broad uptrend ended ${d} after ${n} days`,
  longer: (k, n) => `longer than ${k} of ${n} past runs`,
  marks: { greed: "Greed", crowd: "Traders long", zturn: "Z turned down", rolled: "Rolled over" },
  day: age => `broad uptrend, day ${age}`,
  pop: () => [
    `Broad uptrend: ${Math.round(100 * ON)}% or more of coins in uptrend, until ${OFF_DAYS} days under. Marks: greed, Fear & Greed ${GREED}+ in the last ${LOOKBACK} days (high shown); traders long, ${Math.round(100 * CROWD)}%+ long; z turned down, median z ${Z_TURN} under its high; rolled over, ${Math.round(100 * ROLL)} points under the run's high.`,
    "Since 2021 the median z turned down about a month before the roll-over (10 of 10 runs with both). With recent greed, the typical coin did worse in a run's third month than its first two (3 cases). Context, not a signal.",
  ],
  down: age => `Broad downturn, day ${age}`,
  low: (v, d) => `low ${v} on ${d}`,
  downLonger: (k, n) => `longer than ${k} of ${n} past downturns`,
  downMarks: { fear: "Fear", short: "Traders short", zup: "Z turned up", turned: "Turned up" },
  downDay: age => `broad downturn, day ${age}`,
  downPop: () => [
    `Broad downturn: from a broad uptrend's end until ${Math.round(100 * ON)}% of coins are in uptrend again. Marks: fear, Fear & Greed ${FEAR} or less in the last ${LOOKBACK} days (its low shown); traders short, ${Math.round(100 * SHORT)}% or less long; z turned up, the median z ${Z_TURN} over the downturn's low; turned up, the share ${Math.round(100 * ROLL)} points over its low.`,
    "Since 2021, extreme fear in a downturn's first month came before more falls; two to three months in, before the best months (5 downturns). Context, not a signal.",
  ],
};

// What each mark on the price says, shown when the pointer is on it (owner, 29 October 2026: every icon explains
// itself on hover). `from` is the extreme the mark is measured from: { v (0-100), day }.
export const MCOPY = {
  cooling: { title: "Heat cooling", body: f => `Market heat ${TURN} points under its hot peak (${Math.round(f.v)}, ${f.d}), within ${TURN_DAYS} days.` },
  lifting: { title: "Heat lifting", body: f => `Market heat ${TURN} points over its cold low (${Math.round(f.v)}, ${f.d}), within ${TURN_DAYS} days.` },
  zdown: { title: "Median z turned down", body: () => `The typical coin's z-score is ${Z_TURN} under its high in this broad uptrend. In all 10 broad uptrends since 2021 that had both, it came about a month before the roll-over.` },
  zup: { title: "Median z turned up", body: () => `The typical coin's z-score is ${Z_TURN} over its low in this downturn. In all 7 downturns since 2021 that had both, it came before the turn-up.` },
  rolled: { title: "Rolled over", body: f => `Coins in uptrend are ${Math.round(100 * ROLL)} points under this broad uptrend's high (${Math.round(f.v)}%, ${f.d}).` },
  turned: { title: "Turned up", body: f => `Coins in uptrend are ${Math.round(100 * ROLL)} points over this downturn's low (${Math.round(f.v)}%, ${f.d}).` },
};

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
