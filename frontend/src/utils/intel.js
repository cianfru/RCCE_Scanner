// Setup intel: the scanner's setups read together with what tracked traders are doing.
// Pure helpers for SetupIntelDrawer and the Radar (tested in intel.test.js).
import { ENTRY_SIGNALS } from "./opportunities.js";
import { completionOdds } from "./regimeOdds.js";

const SHORT_SIGNALS = new Set(["LIGHT_SHORT", "STRONG_SHORT"]);
const TF_S = { "4h": 4 * 3600, "1d": 86400 };

// The side a setup points to: its entry signal, or the regime it is changing into.
export function setupSide(row) {
  if (!row) return null;
  if (ENTRY_SIGNALS.has(row.signal)) return "long";
  if (SHORT_SIGNALS.has(row.signal)) return "short";
  const to = row.regime_transition?.candidate;
  if (to === "MARKUP" || to === "REACC") return "long";
  if (to === "MARKDOWN" || to === "CAP") return "short";
  return null;
}

// Candles still needed for the pending regime change (0 when none is pending).
export function barsLeft(row) {
  const t = row?.regime_transition;
  if (!t) return 0;
  return Math.max(0, (t.required_bars || 0) - Math.min(t.observed_bars || 0, t.required_bars || 0));
}

// Next candle closes (ms), UTC-aligned as on the exchanges.
export function nextCloses(timeframe, nowMs, n = 1) {
  const step = (TF_S[timeframe] || TF_S["4h"]) * 1000;
  const first = Math.floor(nowMs / step) * step + step;
  return Array.from({ length: n }, (_, i) => first + i * step);
}

export function fmtIn(ms) {
  const m = Math.max(0, Math.round(ms / 60000));
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (d >= 1) return `${d}d ${h % 24}h`;
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

export function fmtAgo(tSec, nowMs) {
  const m = Math.max(0, Math.round((nowMs / 1000 - tSec) / 60));
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

const opp = s => (s === "long" ? "short" : "long");
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;

// Price's move past a side's median entry, in that side's favour (+0.1 = 10% in profit).
export function pastEntry(side, mark, entry) {
  if (!mark || !entry) return null;
  return side === "long" ? mark / entry - 1 : 1 - mark / entry;
}

// How profitable traders sit relative to a setup: one word and one sentence.
//   quiet    nobody holds it
//   against  2+ hold the other side and outnumber the setup's side
//   crowded  8+ on the setup's side, or 3+ with price 15% or more past their median entry
//   early    someone opened on the setup's side in the last 24h, still holds, near today's price
//   holding  otherwise
export function crowdRead(side, intel) {
  if (!intel) return null;
  const pro = intel.profitable || {};
  if (!side) {
    const n = (pro.long?.n || 0) + (pro.short?.n || 0);
    return n ? { key: "holding", label: "Holding", text: `${plural(n, "profitable trader")} hold it.` }
      : { key: "quiet", label: "Quiet", text: "No profitable trader holds it." };
  }
  const w = pro[side]?.n || 0, a = pro[opp(side)]?.n || 0;
  const fresh = intel.new_24h?.profitable?.[side] || 0;
  const past = pastEntry(side, intel.mark, pro[side]?.median_entry);
  if (!w && !a) return { key: "quiet", label: "Quiet", text: "No profitable trader holds it. The setup has no crowd either way." };
  if (a >= 2 && a > w) return { key: "against", label: "Against", text: `${a} profitable traders are ${opp(side)}, against ${w} ${side}.` };
  if (w >= 8 || (w >= 3 && past != null && past >= 0.15)) {
    return { key: "crowded", label: "Crowded", text: `${w} profitable traders are already ${side}${past != null ? `, and price is ${Math.round(100 * past)}% past their median entry` : ""}.` };
  }
  if (w >= 1 && fresh >= 1 && (past == null || Math.abs(past) <= 0.05)) {
    return { key: "early", label: "Early", text: `${plural(fresh, "profitable trader")} opened ${side} in the last 24h, near today's price.` };
  }
  return { key: "holding", label: "Holding", text: `${w} profitable trader${w === 1 ? " is" : "s are"} ${side}${a ? `, ${a} ${opp(side)}` : ""}.` };
}

// The drawer's readings as key/value rows, named like the Radar's focus panel: Entry checks,
// Crowd, Their entry, Candles to confirm, Completion odds, Converged, Next close. Regime and
// signal are not repeated here: the drawer's SetupPair capsule above the rows shows them, and
// names the regime the odds are for ("→ Uptrend"). fmt: price formatter.
export function briefRows(row, intel, nowMs, { fmt }) {
  const out = [];
  const tf = String(row.timeframe || "4h").toUpperCase();
  if (row.conditions_total) {
    const met = Math.min(row.conditions_met || 0, row.conditions_total);
    out.push({ k: "Entry checks", met, total: row.conditions_total, v: `${met} of ${row.conditions_total}` });
  }
  const side = setupSide(row);
  if (intel) {
    const p = intel.profitable || {};
    const read = crowdRead(side, intel);
    out.push({ k: "Crowd", key: read?.key, label: read?.label, v: `${p.long?.n || 0} long · ${p.short?.n || 0} short` });
    const s = side || ((p.short?.n || 0) > (p.long?.n || 0) ? "short" : "long");
    const past = pastEntry(s, intel.mark, p[s]?.median_entry);
    if (p[s]?.median_entry) out.push({ k: "Their entry", v: `${s} ${fmt(p[s].median_entry)}${past != null ? ` · ${past >= 0 ? "+" : ""}${Math.round(100 * past)}% for them` : ""}` });
  }
  const t = row.regime_transition;
  if (t) {
    const left = barsLeft(row);
    const closes = nextCloses(row.timeframe, nowMs, Math.max(1, left));
    out.push({ k: "Candles to confirm", v: `${Math.min(t.observed_bars, t.required_bars)} of ${t.required_bars} · `
      + (left ? `last in ${fmtIn(closes[closes.length - 1] - nowMs)}` : "the next close confirms") });
    const odds = completionOdds(row.timeframe, row.regime, t.candidate, Math.min(t.observed_bars, t.required_bars));
    if (odds != null) out.push({ k: "Completion odds", v: `${odds}% completed from here` });
  }
  if (intel?.convergence) {
    const c = intel.convergence;
    out.push({ k: "Converged", v: `${c.n} ${c.side} ${fmtAgo(c.ts, nowMs)}, ${fmt(Math.min(c.first_px, c.last_px))} to ${fmt(Math.max(c.first_px, c.last_px))}` });
  }
  const [next] = nextCloses(row.timeframe, nowMs, 1);
  out.push({ k: "Next close", v: `${tf} in ${fmtIn(next - nowMs)}` });
  return out;
}

// Price against the profitable traders' median entry on the setup's side: "+29% above their median".
export function medianGap(row, intel) {
  if (!intel) return null;
  const p = intel.profitable || {};
  const side = setupSide(row) || ((p.short?.n || 0) > (p.long?.n || 0) ? "short" : "long");
  const e = p[side]?.median_entry, mark = intel.mark || row?.price;
  if (!e || !mark) return null;
  const g = mark / e - 1, n = Math.round(100 * Math.abs(g));
  return n === 0 ? "At their median" : `${g >= 0 ? "+" : "−"}${n}% ${g >= 0 ? "above" : "below"} their median`;
}
