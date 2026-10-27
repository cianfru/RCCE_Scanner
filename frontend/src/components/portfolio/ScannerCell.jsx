// SCANNER: the 4H signal in its own colour (the Scanner grid's signal type) and how long it has held.
// When an exit or the "1D against" check comes from the daily signal, line 1 says so ("· 1D RISK-OFF").
// Line 2: the heat bar with one tick at 95 (Trim) and, after a move of 3 or more, a ghost where it was.
import { SIGNAL_META } from "../../theme.js";
import { EXIT_SIGNALS } from "../../utils/portfolio/checks.js";
import { age } from "../../utils/portfolio/format.js";

export const sigWord = s => SIGNAL_META[s]?.label || String(s || "—").replaceAll("_", " ");
// WAIT and anything unnamed read in text tones (no signal); the rest in the scanner's colour.
export const sigColor = s => (!s || s === "WAIT" || !SIGNAL_META[s] ? "var(--t-text3)" : SIGNAL_META[s].color);
// The short words for the 1D tag.
const SHORT = { LIGHT_SHORT: "L.SHORT", STRONG_SHORT: "S.SHORT", LIGHT_LONG: "L.LONG", STRONG_LONG: "S.LONG", ACCUMULATE: "ACCUM",
  REVIVAL_SEED: "REVIVAL", REVIVAL_SEED_CONFIRMED: "REVIVAL" };
export const sigShort = s => SHORT[s] || sigWord(s);

export function HeatBar({ heat, prev, w = 56 }) {
  if (heat == null) return null;
  const at = v => `${Math.max(0, Math.min(100, v))}%`;
  return <span className="pf-hbar" style={{ width: w }} aria-hidden="true">
    <i className="pf-hbar-fill" style={{ width: at(heat) }} />
    <b className="pf-hbar-95" style={{ left: at(95) }} />
    {prev != null && Math.abs(heat - prev) >= 3 && <b className="pf-hbar-ghost" style={{ left: at(prev) }} />}
  </span>;
}

// The daily signal behind an exit or a "1D against" check, when it differs from the 4H word.
export function d1Tag(row) {
  const s4 = row.ctx?.h4?.signal, s1 = row.ctx?.d1?.signal;
  if (!s1 || s1 === s4) return null;
  const fromD1 = row.checks.has("d1against") || (row.checks.has("exit") && EXIT_SIGNALS.has(s1));
  return fromD1 ? s1 : null;
}

export default function ScannerCell({ row, now = Date.now(), compact = false }) {
  const ctx = row.ctx;
  if (!ctx?.h4) return <div className="pf-sc pf-none">{"—"}</div>;
  const h4 = ctx.h4, d1 = ctx.d1;
  const since = h4.since ? now / 1000 - h4.since : null;
  const tag = d1Tag(row);
  return <div className={`pf-sc${row.isLong ? "" : " pf-sc-short"}`} title={d1?.signal ? `1D ${sigWord(d1.signal)}` : undefined}>
    <div className="pf-sc-l1">
      <span className="pf-sig" style={{ color: sigColor(h4.signal) }}>{sigWord(h4.signal)}</span>
      {since != null && <span className="pf-t3 m">{age(since)}</span>}
      {tag && <span className="pf-sc-1d" style={{ color: sigColor(tag) }}><span className="pf-sep">· </span>1D {sigShort(tag)}</span>}
    </div>
    {!compact && <div className="pf-sc-l2">
      <HeatBar heat={h4.heat} prev={h4.heat_prev} />
      <span className={`m pf-heat-n${h4.heat >= 95 ? " pf-heat-hot" : ""}`}>{h4.heat ?? "—"}</span>
    </div>}
  </div>;
}
