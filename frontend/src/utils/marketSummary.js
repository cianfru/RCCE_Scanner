// Pure helpers for the scanner's market summary card (signals, regime mix, Fear & Greed dial).
import { REGIME_ORDER } from "../theme.js";

export const SIGNAL_KEYS = ["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "WAIT", "TRIM", "RISK_OFF"];

// TRIM covers Trim hard too; every other key matches exactly.
export function matchesSignal(row, key) {
  const s = row?.signal;
  return key === "TRIM" ? s === "TRIM" || s === "TRIM_HARD" : s === key;
}

export function signalCounts(rows) {
  const counts = Object.fromEntries(SIGNAL_KEYS.map(k => [k, 0]));
  for (const r of rows) {
    const key = SIGNAL_KEYS.find(k => matchesSignal(r, k));
    if (key) counts[key] += 1;
  }
  const n = rows.length;
  return { n, counts, other: n - SIGNAL_KEYS.reduce((a, k) => a + counts[k], 0) };
}

// Mirrors backend scanner.compute_consensus: a label when one bucket holds more than 55%.
export const CONSENSUS_LINE = 55;
export const CONSENSUS_BUCKETS = {
  "RISK-ON": ["MARKUP"],
  EUPHORIA: ["BLOWOFF"],
  "RISK-OFF": ["MARKDOWN"],
  ACCUMULATION: ["REACC", "ACCUM", "CAP"],
};
const BUCKET_NAMES = { "RISK-ON": "in Uptrend", EUPHORIA: "Overheated", "RISK-OFF": "in Downtrend", ACCUMULATION: "basing" };
const BUCKET_SHORT = { "RISK-ON": "Uptrend", EUPHORIA: "Overheated", "RISK-OFF": "Downtrend", ACCUMULATION: "basing" };

export function regimeMix(rows, label) {
  const counts = {};
  for (const r of rows) {
    const k = r?.regime || "FLAT";
    counts[k] = (counts[k] || 0) + 1;
  }
  const N = rows.length;
  const size = key => CONSENSUS_BUCKETS[key].reduce((a, r) => a + (counts[r] || 0), 0);
  let bucket = CONSENSUS_BUCKETS[label] ? label : null;
  if (!bucket) {                          // MIXED (or unknown): the largest bucket decides the order
    bucket = Object.keys(CONSENSUS_BUCKETS).reduce((best, k) => (size(k) > size(best) ? k : best), "RISK-ON");
  }
  const anchor = CONSENSUS_BUCKETS[bucket];
  const n = size(bucket);
  const known = [...REGIME_ORDER, ...Object.keys(counts).filter(k => !REGIME_ORDER.includes(k))];
  const order = [...anchor.filter(r => counts[r]), ...known.filter(r => counts[r] && !anchor.includes(r))];
  return { N, counts, bucket, anchor, anchorName: BUCKET_NAMES[bucket], anchorShort: BUCKET_SHORT[bucket],
           n, p: N ? Math.round((100 * n) / N) : 0, order };
}

export const CONSENSUS_NOTES = {
  "RISK-ON": "More than 55% in Uptrend: the consensus check passes for long signals.",
  ACCUMULATION: "More than 55% basing: the consensus check passes for long signals.",
  EUPHORIA: "More than 55% Overheated: the consensus check fails for long signals.",
  "RISK-OFF": "More than 55% in Downtrend: the consensus check fails, Accumulate is blocked and Risk-off exits can fire.",
  MIXED: "No group above 55%: the consensus check fails for long signals.",
};

// Fear & Greed: bands mirror backend market_data._fng_label; the lines are the engine's.
export const FG_CUTS = [20, 40, 60, 80];
export const FG_NAMES = ["Extreme fear", "Fear", "Neutral", "Greed", "Extreme greed"];
export const FNG_GREED = 70;      // signal_synthesizer.FNG_GREED: Not greedy fails at or above
export const FNG_FEAR = 40;       // signal_synthesizer.FNG_FEAR: fear gate opens at or below

export function fgBand(v) {
  if (v == null || !Number.isFinite(v)) return null;
  const i = FG_CUTS.findIndex(c => v <= c);
  return i === -1 ? 4 : i;
}

export function fgNote(v, loaded) {
  if (!loaded) return "Waiting for today's reading.";
  if (v == null || !Number.isFinite(v)) return "No reading: the Not greedy check counts as failed.";
  if (v >= FNG_GREED) return "70 or above: the Not greedy check fails on every market.";
  if (v <= FNG_FEAR) return "40 or below: the fear gate is open. Not greedy passes.";
  return "Not greedy passes. The fear gate opens at 40 or below.";
}

export const dialRotation = v => Math.round((1.8 * Math.max(0, Math.min(100, v)) - 90) * 100) / 100;
