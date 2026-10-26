// WHILE HELD: what the scanner showed since the position opened. One segment per 4H regime (its
// colour at 35%), 1px ticks for 4H changes, full-height ticks for 1D, and exit signals as small ticks
// above in their own colour. A position opened before the fills on hand or the 30-day window starts
// at the window with a break mark. Hover lists the events.
import { REGIME_META, SIGNAL_META } from "../../theme.js";
import { EXIT_SIGNALS } from "../../utils/portfolio/checks.js";
import { age, stamp, px, dayMonth } from "../../utils/portfolio/format.js";
import { Hover } from "./parts.jsx";
import { sigWord, sigColor } from "./ScannerCell.jsx";

const regColor = reg => REGIME_META[reg]?.color || "var(--t-text4)";
const regFill = reg => `color-mix(in srgb, ${regColor(reg)} 35%, transparent)`;

// From the events body: the segments and ticks between `from` and `now` (seconds).
export function heldModel(ev, from, now) {
  if (!ev || !ev.at_start) return null;
  const ws = ev.windowStart;
  const broken = from == null || from < ws;
  const t0 = broken ? ws : from;
  let reg = ev.at_start.h4?.regime || null;
  const all = (ev.events || []).slice().sort((a, b) => a.t - b.t);
  for (const e of all) if (e.t <= t0 && e.tf === "4h" && e.kind === "regime") reg = e.to;
  const segs = [];
  let start = t0;
  const ticks = [];
  for (const e of all) {
    if (e.t <= t0 || e.t > now) continue;
    if (e.tf === "4h" && e.kind === "regime") { segs.push({ a: start, b: e.t, reg }); reg = e.to; start = e.t; }
    ticks.push(e);
  }
  segs.push({ a: start, b: now, reg });
  return { t0, now, broken, segs, ticks };
}

export default function HeldStrip({ ev, from, now = Date.now() / 1000, w = 120, covered = true }) {
  const mdl = covered ? heldModel(ev, from, now) : null;
  if (!mdl) return <div className="pf-held pf-none">{"—"}</div>;
  const X = t => ((t - mdl.t0) / Math.max(1, mdl.now - mdl.t0)) * w;
  const list = mdl.ticks.filter(e => e.kind === "signal");
  // The key first: each regime stretch with its colour and dates, then the signal changes.
  const segs = mdl.segs.filter(s => s.reg && s.b > s.a);
  const card = segs.length || list.length ? <div className="pf-pop">
    {segs.slice(-6).map((s, i) => <div key={`r${i}`} className="pf-pop-row">
      <span><i className="pf-regsw" style={{ background: regFill(s.reg), boxShadow: `inset 0 0 0 1px ${regColor(s.reg)}` }} />{REGIME_META[s.reg]?.name || s.reg}</span>
      <b className="m pf-t2">{dayMonth(s.a * 1000)}–{dayMonth(s.b * 1000)}</b></div>)}
    {segs.length > 0 && list.length > 0 && <div className="pf-pop-sep" />}
    {list.slice(-8).map((e, i) => <div key={i} className="pf-pop-row">
      <span style={{ color: sigColor(e.to) }}>{sigWord(e.to)} {e.tf === "4h" ? "4H" : "1D"}</span><b className="m">{stamp(e.t * 1000)} · {px(e.px)}</b></div>)}</div> : null;
  return <div className="pf-held">
    <Hover content={card} width={300} className="pf-held-box">
      <svg width={w} height="16" viewBox={`0 0 ${w} 16`} aria-hidden="true">
        {mdl.segs.map((s, i) => <rect key={i} x={X(s.a)} y="5" width={Math.max(0.5, X(s.b) - X(s.a))} height="10"
          fill={regFill(s.reg)} />)}
        {mdl.ticks.map((e, i) => e.kind === "signal" && e.tf === "4h" && !EXIT_SIGNALS.has(e.to)
          ? <rect key={i} x={X(e.t) - 0.5} y="5" width="1" height="10" className="pf-held-4h" /> : null)}
        {mdl.ticks.map((e, i) => e.tf === "1d" ? <rect key={`d${i}`} x={X(e.t) - 0.5} y="3" width="1" height="13" className="pf-held-1d" /> : null)}
        {mdl.ticks.map((e, i) => e.kind === "signal" && EXIT_SIGNALS.has(e.to)
          ? <rect key={`x${i}`} x={X(e.t) - 1} y="0" width="2" height="6" fill={SIGNAL_META[e.to]?.color} /> : null)}
        {mdl.broken && <g className="pf-r-break"><line x1="1" y1="15" x2="4" y2="5" /><line x1="5" y1="15" x2="8" y2="5" /></g>}
      </svg>
    </Hover>
    <span className="pf-t3 m pf-held-age">{from ? age(now - from, { long: true }) : "—"}</span>
  </div>;
}
