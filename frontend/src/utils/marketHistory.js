// Pure helpers and all visible copy for the market history drawer (/api/market-history).
// The drawer leads with charts; the method text lives in the info popovers (COPY.pop).

const DAY_MS = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MINUS = "−";

export const FAN_H = 60;                              // the fan's last knot, in days after today
export const FAN_MARKS = [30, 60];                    // knots marked on the chart and in the readout
export const FAN_SERIES = ["uptrend", "btc", "alt"];
export const FAN_LOG_FROM = 20724;                    // 28 Sep 2026: the clean check starts (docs/reviews/market-paths-method.md)
export const MIN_RUNS = 6;                            // the repo's "too few" bar

export const RANGES = [{ key: "3m", label: "3M", days: 90 }, { key: "1y", label: "1Y", days: 365 },
  { key: "3y", label: "3Y", days: 3 * 365 }, { key: "all", label: "All", days: null }];

export function dayDate(day, withYear = true) {
  const d = new Date(day * DAY_MS);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${withYear ? ` ${d.getUTCFullYear()}` : ""}`;
}

export const monthYear = day => { const d = new Date(day * DAY_MS); return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const monthOf = day => MONTHS[new Date(day * DAY_MS).getUTCMonth()];
export const yearOf = day => new Date(day * DAY_MS).getUTCFullYear();

export const signedPct = (x, digits = 1) => (x == null ? "—" : `${x > 0 ? "+" : x < 0 ? MINUS : ""}${Math.abs(x).toFixed(digits)}%`);
const signedInt = x => `${x > 0 ? "+" : x < 0 ? MINUS : ""}${Math.abs(Math.round(x))}`;
export const pctLabel = x => (x == null ? "—" : `${Math.round(100 * x)}%`);
export const usd = v => (v == null ? "—" : `$${Math.round(v).toLocaleString("en-US")}`);
export const kUsd = v => {                            // 84,836 -> 84.8k; 109,775 -> 110k
  if (v == null) return "—";
  if (v >= 100_000) return `${Math.round(v / 1000)}k`;
  if (v >= 1000) return `${(v / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(Math.round(v));
};
export function ordinal(n) {
  const r100 = n % 100, r10 = n % 10;
  const suf = r100 >= 11 && r100 <= 13 ? "th" : r10 === 1 ? "st" : r10 === 2 ? "nd" : r10 === 3 ? "rd" : "th";
  return `${n}${suf}`;
}

// Rows as objects keyed by the API's column names.
export function rowsOf(data) {
  if (!data?.days) return [];
  const cols = data.columns;
  return data.days.map(r => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
}

export function inRange(rows, rangeKey) {
  const r = RANGES.find(x => x.key === rangeKey);
  if (!r?.days || !rows.length) return rows;
  const from = rows[rows.length - 1].day - r.days;
  return rows.filter(x => x.day >= from);
}

// Fear & Greed by day, for joining onto the breadth rows.
export const fearGreedByDay = data => new Map((data?.fear_greed || []).map(([d, v]) => [d, v]));

// Share of values strictly below v (the "Nth percentile").
export function percentileOf(values, v) {
  const xs = values.filter(x => x != null);
  return xs.length ? Math.round((100 * xs.filter(x => x < v).length) / xs.length) : null;
}

// BTC's weekly band on a day: rows are [close_day, lo, hi], one per Sunday close, each used from the day
// after its close through the next close day. The close day itself uses the previous week's row.
export function bandOn(weekly, day) {
  if (!weekly?.length) return null;
  let lo = 0, hi = weekly.length - 1, best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (weekly[mid][0] < day) { best = mid; lo = mid + 1; } else hi = mid - 1;
  }
  if (best < 0 || day - weekly[best][0] > 7) return null;
  return [weekly[best][1], weekly[best][2]];
}

export function btcSide(btc, band) {
  if (!band || !(btc > 0)) return null;
  return btc < band[0] ? "below" : btc > band[1] ? "above" : "inside";
}

// Distance from the nearer edge, in %: positive above the band, negative below, 0 inside.
export function bandDistance(btc, band) {
  const side = btcSide(btc, band);
  if (!side) return null;
  return side === "above" ? 100 * (btc / band[1] - 1) : side === "below" ? 100 * (btc / band[0] - 1) : 0;
}

// Uptrend band labels: short for the tabs, full for the heading.
export const bandShort = b => (b.lo <= 0 ? `<${Math.round(100 * b.hi)}` : b.hi > 1 ? `${Math.round(100 * b.lo)}+`
  : `${Math.round(100 * b.lo)}–${Math.round(100 * b.hi)}`);
export const bandHead = b => (b.lo <= 0 ? `under ${Math.round(100 * b.hi)}%` : b.hi > 1 ? `${Math.round(100 * b.lo)}% and over`
  : `${Math.round(100 * b.lo)}–${Math.round(100 * b.hi)}%`);

// Episode rows as objects, newest first. A 30- or 60-day outcome still running carries the day it
// scores (due30 / due60); one that has closed but has no data stays null. `later` marks rows after the study window.
export function episodesOf(data, band) {
  if (!band) return [];
  const cols = data.episode_columns;
  const last = data.scored_through ?? data.today?.day ?? Infinity;
  const row = later => e => {
    const o = Object.fromEntries(cols.map((c, i) => [c, e[i] ?? null]));
    for (const h of [30, 60]) o[`due${h}`] = o.start + h > last ? o.start + h : null;
    o.later = later;
    return o;
  };
  return [...band.episodes.map(row(false)), ...(band.later || []).map(row(true))].sort((a, b) => b.start - a.start);
}

// Better / worse than an ordinary 30 days on the typical alt; pending episodes are left out.
export function stripCounts(eps, baseAlt) {
  let better = 0, worse = 0;
  for (const e of eps) {
    if (e.due30 || e.alt30 == null || baseAlt == null) continue;
    if (e.alt30 > baseAlt) better++; else worse++;
  }
  return { better, worse };
}

// Shares of days at <=40, 41-69 and >=70, in whole % summing to 100 (largest remainder).
export function fgSplit(values) {
  const xs = values.filter(v => v != null);
  if (!xs.length) return null;
  const counts = [xs.filter(v => v <= 40).length, xs.filter(v => v > 40 && v < 70).length, xs.filter(v => v >= 70).length];
  const raw = counts.map(c => (100 * c) / xs.length);
  const out = raw.map(Math.floor);
  const order = raw.map((r, i) => [r - Math.floor(r), i]).sort((a, b) => b[0] - a[0]);
  for (let j = 0; out.reduce((a, b) => a + b, 0) < 100; j++) out[order[j % 3][1]]++;
  return out;
}

// Today's run against ended ones: the counts drawn on the runs chart (docs/reviews/risk-on-cycles-study.md).
export function runsMarks(cycle) {
  if (!cycle?.runs) return null;
  const mark = (a, b) => COPY.runs.mark(a, b);
  return {
    now: { day: cycle.day, text: mark(cycle.reached, cycle.past) },
    later: cycle.reached > 0 ? { day: cycle.day + cycle.more, text: mark(cycle.lasted_more, cycle.reached) } : null,
    columns: cycle.runs.map(([start, len, peak]) => ({ start, len, peak, reached: len >= cycle.day })),
  };
}

// ---------------------------------------------------------------- the past-paths fan

// x geometry of the chart with the future zone: linear in days over [d0, T + 60] (just [d0, T] without a fan).
// Band polygons are [[x, lo, hi], ...] in data units, only for series the check lets draw bands.
export function fanGeometry({ fan, T, d0, width, padL = 8, padR = 44, future = true }) {
  const d1 = future ? T + FAN_H : T;
  const span = Math.max(1, d1 - d0);
  const x = day => padL + ((day - d0) / span) * (width - padL - padR);
  const knots = (fan?.k || []).map((k, i) => ({ k, i, day: T + k, x: x(T + k) }));
  const polys = {};
  for (const s of FAN_SERIES) {
    const b = fan?.bands?.[s];
    if (!b || fan.show?.[s] !== "bands" || fan.too_few) { polys[s] = null; continue; }
    const at = (lo, hi) => knots.filter(({ i }) => b[i]).map(({ x: px, i }) => [px, b[i][lo], b[i][hi]]);
    polys[s] = { outer: at(0, 4), mid: at(1, 3) };
  }
  return { d0, d1, T, x, frac: future ? FAN_H / span : 0, zone: future ? [x(T), x(d1)] : null, knots, polys };
}

// The median line at each knot ([[knotIndex, value]]); none with too few runs.
export function fanMedian(fan, s) {
  const b = fan?.bands?.[s];
  if (!b || fan.too_few) return [];
  return b.map((q, i) => (q ? [i, q[2]] : null)).filter(Boolean);
}

const fmt = {
  uptrend: { v: pctLabel, n: v => String(Math.round(100 * v)) },
  btc: { v: v => `$${kUsd(v)}`, n: kUsd },
  alt: { v: v => signedPct(v, 1).replace(/^0\.0%$/, "0%"), n: signedInt },
};
export const fmtSeries = (s, v) => (v == null ? "—" : fmt[s].v(v));

// One readout cell at knot i: the median plus the middle half (bands) or the lowest-highest range (paths).
export function readoutCells(fan, s, i) {
  if (!fan) return { median: null, spread: null };
  const vals = (fan.paths?.[s] || []).map(p => p[i]).filter(v => v != null);
  const q = fan.too_few ? null : fan.bands?.[s]?.[i];
  const median = q ? fmt[s].v(q[2]) : null;
  const join = (a, b) => (s === "alt" ? `${fmt.alt.n(a)}/${fmt.alt.n(b)}` : `${fmt[s].n(a)}–${fmt[s].n(b)}`);
  if (fan.show?.[s] === "bands" && q) return { median, spread: join(q[1], q[3]) };
  if (!vals.length) return { median, spread: null };
  return { median, spread: COPY.readout.range(join(Math.min(...vals), Math.max(...vals))) };
}

// ---------------------------------------------------------------- copy

const plural = (n, w, ws = `${w}s`) => `${n} ${n === 1 ? w : ws}`;
const SERIES_NAME = { btc: "BTC", uptrend: "Uptrend", alt: "typical alt" };

// Drop the lowest-priority sentences until a popover fits its word budget. parts: [[priority, text]].
function fit(parts, max = 90) {
  const keep = parts.filter(p => p[1]);
  while (popWords(keep.map(p => p[1]).join(" ")) > max && keep.length > 1) {
    let low = 0;
    keep.forEach((p, i) => { if (p[0] < keep[low][0]) low = i; });
    keep.splice(low, 1);
  }
  return keep.map(p => p[1]).join(" ");
}

function checkLine(ctx) {
  const c = ctx.check;
  if (ctx.tooFew) return `Only ${ctx.runs} runs: too few for a median or bands.`;
  if (!c || c.untested) return "Too few past episodes to test the bands, so paths are drawn.";
  const n = c.scored ?? c.tested;
  const failed = ["btc", "uptrend", "alt"].filter(s => !c.series?.[s]?.pass).map(s => SERIES_NAME[s]);
  if (!failed.length) {
    const m = c.median_vs_all;
    const how = m == null ? "about as close as" : m < 0.9 ? "closer than" : m > 1.1 ? "further off than" : "about as close as";
    return `Tested on ${n} episodes with only earlier data, the bands held about as often as drawn; the median was ${how} all past days.`;
  }
  const names = failed.length === 1 ? failed[0] : `${failed.slice(0, -1).join(", ")} and ${failed[failed.length - 1]}`;
  return `Tested on ${n} episodes with only earlier data, the ${names} bands held too few real moves, so ${failed.length === 1 ? "its" : "their"} paths are drawn.`;
}

function liveLine(live) {
  if (!live || live.scored < 12) return null;
  let hit = 0, n = 0;
  for (const s of FAN_SERIES) { hit += live.mid?.[s]?.[0] || 0; n += live.mid?.[s]?.[1] || 0; }
  if (!n) return null;
  return `Since ${dayDate(FAN_LOG_FROM)}: ${live.scored} new episodes, middle half held ${Math.round((100 * hit) / n)}%.`;
}

export const COPY = {
  title: "Market history",
  close: "Close",
  tabs: { breadth: "Uptrend share", fear: "Fear & Greed" },
  loading: "Loading history…",
  unavailable: "History is unavailable right now.",
  empty: "No history in this range.",
  rangeLabel: "Range",
  overlaysLabel: "Add to the chart",
  overlays: { overheated: "Overheated", median_z: "Median z", fg: "Fear & Greed" },

  caption: (paths, runs, tooFew) => `${plural(paths, "past path")} · ${plural(runs, "run")}${tooFew ? " · too few for a median" : ""}`,
  tooFewDays: "Too few similar days",
  axis: { today: "Today", h: k => `+${k}d` },
  panel: { btc: "BTC · weekly band", uptrend: "Uptrend share", alt: "Typical alt vs today", fg: "Fear & Greed" },
  riskOn: "55%: RISK-ON",
  zones: { greed: "Not greedy fails", fear: "Fear gate open" },

  readout: {
    today: "Today", uptrend: "Uptrend", btc: "BTC", alt: "Typical alt", ordinary: "ordinary",
    overheated: "Overheated", median_z: "Median z", fg: "Fear & Greed",
    range: s => `range ${s}`,
    side: { above: "above band", inside: "inside band", below: "below band" },
    altVs: x => `${x} vs today`,
  },

  kpi: {
    uptrend: "Uptrend",
    pct: p => `${ordinal(p)} percentile`,
    day: n => `Day ${n}`,
    run: on => (on ? "risk-on run" : "risk-off stretch"),
    under: n => `${plural(n, "day")} under 55%`,
    band: side => `BTC ${side} its band`,
    fg: "Fear & Greed",
  },

  runs: {
    head: on => (on ? "Risk-on runs" : "Risk-off stretches"),
    mark: (a, b) => `${a} of ${b}${b < MIN_RUNS ? ", too few" : ""}`,
    hover: (start, len, peak) => `${monthYear(start)} · ${len} days · peak ${Math.round(100 * peak)}%`,
    now: "today",
  },

  episodes: {
    head: band => `Last times at ${band}`,
    count: (b, w) => `${b} better · ${w} worse`,
    ordinary: x => `ordinary ${x}`,
    all: n => `All ${n} episodes`,
    fewer: "Newest 5",
    due: d => `due ${d}`,
    pts: v => `${signedInt(v)} pts`,
    ongoing: n => `${n}, ongoing`,
    cols: ["Started", "Days", "Uptrend", "BTC 30d", "Typical alt 30d", "vs ordinary", "Typical alt 60d"],
    column: (d, v) => `${dayDate(d)} · ${signedPct(v)}`,
    pending: d => `${dayDate(d)} · ${COPY.episodes.due(dayDate(d + 30, false))}`,
  },

  ft: {
    head: "Forward test",
    scored: n => `${n} of 6 scored`,
    past: "Past cases",
    worse: (n, m) => `${n} of ${m} worse`,
    table: "Table",
    cols: ["Started", "Days", "Share", "BTC 30d", "Typical alt 30d", "Typical alt 60d"],
    pending: "pending",
    square: (d, v) => (v == null ? `${dayDate(d)} · ongoing` : `${dayDate(d)} · ${signedPct(v)}`),
  },

  // Popovers: HelpTip, width 320, each 90 words or fewer. Each returns paragraphs.
  pop: {
    fanTitle: "How this is drawn",
    fan: ctx => {
      const stateWords = ctx.state === "on" ? "a risk-on run" : "a risk-off stretch";
      const side = ctx.side === "holding" ? "BTC holding its weekly band" : ctx.side === "below" ? "BTC below its weekly band"
        : "BTC either side of its weekly band";
      const main = fit([
        [9, `Days since ${ctx.since} in ${stateWords}, Uptrend within ${ctx.width} points of today's ${ctx.today}, ${side}, next 60 days closed; today's run left out.`],
        [8, `Each stretch counts once, from its first day: ${ctx.paths} paths, ${ctx.runs} runs, started at today's values.`],
        [5, "Line: median. Shading: middle half, 8 in 10. Dotted: an ordinary stretch."],
        [7, checkLine(ctx)],
        [9, liveLine(ctx.live)],
        [6, "Coins that died are missing, so past alts look better."],
      ]);
      return [main];
    },
    fanNone: ctx => [`No stretch since ${ctx.since} was close enough to today, in at least 3 separate runs, to draw past paths.`],
    uptrendTitle: "Uptrend share",
    uptrend: ctx => [`Share of ${ctx.coins} coins in Uptrend on Binance daily closes, run through the scanner's engine, on days with 40 or more coins since ${ctx.since}. The scanner's card counts its own markets, so the two can differ by a few points. Percentile: share of those days with a lower reading. The coin list is today's: coins that died are missing, and early years have fewer coins.`],
    bandTitle: "BTC weekly band",
    band: () => ["BTC's weekly bull market support band: the 20-week SMA and 21-week EMA of Sunday closes, each used from the day after its week closes. The figure is BTC's distance from the nearer edge. Red shading: days BTC closed below the band."],
    runsTitle: "Runs",
    runs: ctx => [ctx.on
      ? `A risk-on run starts on the first day with 55% or more of coins in Uptrend or Overheated and ends after 5 days in a row below 55%. Columns: runs that ended since ${ctx.since}, by length in days, oldest first; the outlined column is today's run. Solid line: today's day. Dotted line: 30 days later. Counts: runs that got that far.`
      : `A risk-off stretch starts after 5 days in a row below 55% of coins in Uptrend or Overheated and ends on the next day at 55% or more. Columns: stretches that ended since ${ctx.since}, by length in days, oldest first; the outlined column is today's. Solid line: today's day. Dotted line: 30 days later. Counts: stretches that got that far.`],
    episodesTitle: "Episodes",
    episodes: ctx => [`An episode is a stretch of days in this band (gaps of up to 5 days joined), measured from its first day. Columns: the typical alt's change over the next 30 days. Dotted line: an ordinary 30 days (typical alt ${ctx.alt}, BTC ${ctx.btc}; medians of all days, ${ctx.from} to ${ctx.to}). Above the line is better than ordinary, even below zero. Up to ${ctx.end}, ${ctx.better} of ${ctx.n} episodes did better: ${verdictWords(ctx.verdict)}. Paler columns: later episodes.`],
    ftTitle: "Forward test",
    ft: ctx => [`Declared ${ctx.declared} with fixed rules. An episode starts when BTC closes below the lower edge of its weekly band while ${ctx.share}% or more of coins are in Uptrend or Overheated. Only episodes after that date count. A square fills when an episode's 60 days close: red if the typical alt did worse than an ordinary 60 days (${ctx.base}). No verdict before 6; then it holds if at least 75% are red. Past cases were found on the same history, ${ctx.bear} of ${ctx.n} from the 2022 bear market.`],
    pastTitle: "Past cases",
    past: ctx => [`Where the idea came from: ${ctx.n} earlier episodes found on the same history, so it is a hypothesis. Columns: the typical alt over the 60 days after each one's first day. Dotted line: an ordinary 60 days (${ctx.base}). Red: worse than ordinary.`],
    fgTitle: "Fear & Greed",
    fg: ctx => [`Source: alternative.me, daily. The dial's bands are the scanner's own (20 / 40 / 60 / 80). At 70 or above the engine's Not greedy check fails on every market; at 40 or below the fear gate lets Accumulate setups in Accumulation and Capitulation revivals fire. Percentile: share of days since ${ctx.since} with a lower reading. No study has tested what followed each level, so this tab draws no paths.`],
  },
};

function verdictWords(v) {
  if (!v || v.direction === "too few episodes" || !v.alt) return "too few episodes to read";
  if (v.alt.direction === "mixed") return "a mixed record";
  return `it meets the study's 75% bar, on ${v.episodes} episodes`;
}

// Words: visible tokens with at least one letter (figures are not words). Popovers count every token.
export const countWords = s => String(s).split(/\s+/).filter(t => /[A-Za-z]/.test(t)).length;
export const popWords = s => String(s).split(/\s+/).filter(Boolean).length;

// ---------------------------------------------------------------- context shared by the drawer and the tests

export function breadthContext(data) {
  const t = data.today;
  const weekly = data.btc_band_weekly || [];
  const last = data.days?.[data.days.length - 1];
  const btc = last ? last[data.columns.indexOf("btc")] : null;
  const band = bandOn(weekly, t.day);
  const side = btcSide(btc, band);
  const dist = bandDistance(btc, band);
  const fan = data.fan || null;
  const c = data.cycle;
  const [from, to] = data.base_period || [t.since, data.end_day];
  return {
    t, btc, band, side, dist, fan, cycle: c, on: !c || c.type === "on",
    since: monthYear(t.since), from: monthYear(from), to: monthYear(to), end: dayDate(data.end_day),
    fanCtx: fan && {
      state: fan.state, since: monthYear(t.since), width: Math.round(100 * (fan.rule?.width ?? 0.05)),
      today: pctLabel(t.uptrend + (t.overheated || 0)), side: fan.rule?.btc_side || "holding",
      paths: fan.episodes.length, runs: fan.runs, tooFew: fan.too_few, check: fan.check, live: fan.live_check,
    },
  };
}

// The words a tab shows outside tables, popovers, axis ticks and tab/toggle labels (the word budget).
// Mirrors what MarketHistoryDrawer renders; the screenshots pass re-counts them on the page.
export function visibleTexts(tab, data, { range = "3m", band } = {}) {
  if (tab === "fear") {
    return [COPY.kpi.fg, COPY.kpi.pct(50), COPY.panel.btc, COPY.panel.fg, COPY.zones.greed, COPY.zones.fear,
      COPY.readout.btc, COPY.readout.fg, dayDate(data.today.day)];
  }
  const x = breadthContext(data);
  const b = band || data.bands.find(bb => bb.label === x.t.band) || data.bands[0];
  const eps = episodesOf(data, b);
  const base = data.base?.["30"]?.alt?.median;
  const counts = stripCounts(eps, base);
  const alt = range === "3m";
  const marks = runsMarks(x.cycle);
  const ft = data.forward_test;
  const b60 = data.base?.["60"]?.alt?.median;
  const out = [
    COPY.kpi.uptrend, COPY.kpi.pct(x.t.percentile),
    x.cycle && COPY.kpi.day(x.cycle.day), x.cycle && COPY.kpi.run(x.on), x.cycle?.below_days > 0 && COPY.kpi.under(x.cycle.below_days),
    x.side && COPY.kpi.band(x.side),
    x.fan ? COPY.caption(x.fan.episodes.length, x.fan.runs, x.fan.too_few) : COPY.tooFewDays,
    COPY.panel.btc, COPY.panel.uptrend, alt && COPY.panel.alt, COPY.riskOn,
    COPY.readout.today, COPY.axis.h(30), COPY.axis.h(60), COPY.readout.uptrend, COPY.readout.btc, COPY.readout.ordinary,
    alt && COPY.readout.alt, alt && COPY.readout.ordinary,
    marks && COPY.runs.head(x.on), marks?.now.text, marks?.later?.text,
    COPY.episodes.head(bandHead(b)), COPY.episodes.count(counts.better, counts.worse),
    base != null && COPY.episodes.ordinary(signedPct(base)), eps.length > 5 && COPY.episodes.all(eps.length),
  ];
  if (ft) {
    const worse = ft.history.filter(h => b60 != null && h[5] < b60).length;
    out.push(COPY.ft.head, COPY.ft.scored(ft.episodes.filter(e => e.h60).length), COPY.ft.past,
      COPY.ft.worse(worse, ft.history.length), COPY.ft.table);
  }
  return out.filter(Boolean);
}

export const visibleWords = (tab, data, opts) => visibleTexts(tab, data, opts).reduce((n, s) => n + countWords(s), 0);

// Log-scale ticks for BTC: 1, 2, 5 × powers of ten inside [lo, hi]; finer steps when that gives fewer than two.
export function logTicks(lo, hi) {
  const pick = ms => {
    const out = [];
    for (let p = Math.floor(Math.log10(lo)); p <= Math.ceil(Math.log10(hi)); p++) {
      for (const m of ms) {
        const v = Math.round(m * 10 ** p);
        if (v >= lo && v <= hi) out.push(v);
      }
    }
    return out;
  };
  const coarse = pick([1, 2, 5]);
  if (coarse.length >= 2) return coarse;
  const fine = pick([1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9]);
  return fine.length > 4 ? fine.filter((_, i) => i % Math.ceil(fine.length / 4) === 0) : fine;
}

export const compactUsd = v => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${Math.round(v)}`);

// Ticks for the typical-alt panel: 0 and a round step either side.
export function altTicks(m) {
  const step = [200, 100, 50, 25, 20, 10, 5].find(s => s <= m * 0.9) || 5;
  return [-step, 0, step];
}
