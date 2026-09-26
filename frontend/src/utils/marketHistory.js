// Pure helpers for the market history drawer (/api/market-history).

const DAY_MS = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MINUS = "−";

export const RANGES = [{ key: "1y", label: "1Y", days: 365 }, { key: "3y", label: "3Y", days: 3 * 365 }, { key: "all", label: "All", days: null }];

export function dayDate(day, withYear = true) {
  const d = new Date(day * DAY_MS);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${withYear ? ` ${d.getUTCFullYear()}` : ""}`;
}

export const monthYear = day => { const d = new Date(day * DAY_MS); return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };

export const signedPct = (x, digits = 1) => (x == null ? "—" : `${x > 0 ? "+" : x < 0 ? MINUS : ""}${Math.abs(x).toFixed(digits)}%`);

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

// Share of values strictly below v (the drawer's "higher than N% of days").
export function percentileOf(values, v) {
  const xs = values.filter(x => x != null);
  return xs.length ? Math.round((100 * xs.filter(x => x < v).length) / xs.length) : null;
}

// Episode rows as objects; later ones (after the study's end day) carry no outcomes.
export function episodesOf(data, band) {
  if (!band) return [];
  const cols = data.episode_columns;
  const scored = band.episodes.map(e => ({ ...Object.fromEntries(cols.map((c, i) => [c, e[i]])), scored: true }));
  const later = (band.later || []).map(([start, end, breadth]) => ({ start, end, breadth, scored: false }));
  return [...scored, ...later].sort((a, b) => b.start - a.start);
}

// The band's record in words: counts, never a forecast (docs/reviews/market-breadth-study.md).
export function bandSummary(band) {
  const v = band?.verdict;
  if (!v || v.direction === "too few episodes" || !v.alt) {
    return `${v?.episodes ?? 0} past episodes: too few to read.`;
  }
  const lead = `In ${v.episodes} past episodes, the typical alt did better than an ordinary 30 days in ${v.alt.above_base} and BTC in ${v.btc.above_base}.`;
  const mixed = v.alt.direction === "mixed" && v.btc.direction === "mixed";
  return mixed ? `${lead} The record is mixed: no direction.`
    : `${lead} That meets the study's 75% bar on ${v.alt.direction !== "mixed" ? "alts" : "BTC"}, but it is a count of ${v.episodes} episodes, not a forecast.`;
}

// Log-scale ticks for BTC: 1, 2, 5 × powers of ten inside [lo, hi].
export function logTicks(lo, hi) {
  const out = [];
  for (let p = Math.floor(Math.log10(lo)); p <= Math.ceil(Math.log10(hi)); p++) {
    for (const m of [1, 2, 5]) {
      const v = m * 10 ** p;
      if (v >= lo && v <= hi) out.push(v);
    }
  }
  return out;
}

export const compactUsd = v => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${Math.round(v)}`);
