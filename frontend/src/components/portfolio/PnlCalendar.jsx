// The P&L calendar: realised P&L per UTC day (closed trades net of fees, plus funding), colour only,
// five steps against the month's 90th percentile; W is the week's total. Today has an accent outline,
// the last-visit day a corner tick; days before the fills on hand are hatched.
import { useMemo, useState } from "react";
import { dailyPnl, monthGrid, steps } from "../../utils/portfolio/calendar.js";
import { usd, monthName } from "../../utils/portfolio/format.js";
import { Label, Hover, pnlClass } from "./parts.jsx";
import { INFO, CAL } from "./copy.js";

const STEP_PCT = [0, 16, 30, 46, 64, 84];

export default function PnlCalendar({ fills, funding, historyStart, lastVisit, phone }) {
  const days = useMemo(() => dailyPnl(fills, funding), [fills, funding]);
  const now = new Date();
  const [ym, setYm] = useState([now.getUTCFullYear(), now.getUTCMonth()]);
  const [y, m] = ym;
  const first = historyStart ? new Date(historyStart) : null;
  const canBack = first ? (y > first.getUTCFullYear() || (y === first.getUTCFullYear() && m > first.getUTCMonth())) : false;
  const canFwd = y < now.getUTCFullYear() || (y === now.getUTCFullYear() && m < now.getUTCMonth());
  const shift = d => setYm(([yy, mm]) => { const t = new Date(Date.UTC(yy, mm + d, 1)); return [t.getUTCFullYear(), t.getUTCMonth()]; });
  const weeks = monthGrid(y, m, days);
  const vals = weeks.flatMap(w => w.days.filter(Boolean).map(k => days.get(k)?.net || 0));
  const step = steps(vals);
  const today = now.toISOString().slice(0, 10);
  const visitDay = lastVisit ? new Date(lastVisit * 1000).toISOString().slice(0, 10) : null;
  const startKey = historyStart ? new Date(historyStart).toISOString().slice(0, 10) : null;
  const fill = v => {
    const k = step(v);
    if (!k) return "var(--t-overlay06)";
    return `color-mix(in srgb, ${v > 0 ? "var(--t-profit)" : "var(--t-loss)"} ${STEP_PCT[k]}%, var(--t-bg))`;
  };
  const cell = key => {
    if (!key) return <span className="pf-cal-c pf-cal-blank" />;
    const d = days.get(key);
    const pre = startKey && key < startKey;
    const future = key > today;
    const tip = d ? <div className="pf-pop">
      <div className="pf-pop-row"><span>{key}</span><b className={`m ${pnlClass(d.net)}`}>{usd(d.net, { sign: true })}</b></div>
      <div className="pf-pop-row"><span>{CAL.closes}</span><b className="m">{d.closes}</b></div>
      <div className="pf-pop-row"><span>{CAL.funding}</span><b className={`m ${pnlClass(d.funding)}`}>{usd(d.funding, { sign: true })}</b></div>
      <div className="pf-pop-row"><span>{CAL.fees}</span><b className="m">{usd(-d.fees)}</b></div></div> : null;
    return <Hover key={key} className={`pf-cal-c${pre ? " pf-cal-pre" : ""}${future ? " pf-cal-fut" : ""}${key === today ? " pf-cal-today" : ""}${key === visitDay ? " pf-cal-visit" : ""}`}
      style={{ background: pre || future ? undefined : fill(d?.net || 0) }} content={tip} width={200} aria-label={key} />;
  };
  return <div className="pf-cal">
    <div className="pf-cal-head">
      <Label info={INFO.calendar}>{monthName(y, m)}</Label>
      <span className="pf-cal-nav">
        <button type="button" className="pf-textbtn" disabled={!canBack} onClick={() => shift(-1)} aria-label={CAL.prev}>‹</button>
        <button type="button" className="pf-textbtn" disabled={!canFwd} onClick={() => shift(1)} aria-label={CAL.next}>›</button>
      </span>
    </div>
    <div className={`pf-cal-grid${phone ? " pf-cal-ph" : ""}`}>
      {CAL.days.map((d, i) => <span key={i} className="pf-cal-wd">{d}</span>)}<span className="pf-cal-wd">{CAL.week}</span>
      {weeks.map((w, i) => [...w.days.map((k, j) => <span key={`${i}-${j}`} className="pf-cal-slot">{cell(k)}</span>),
        <span key={`w${i}`} className={`pf-cal-w m ${pnlClass(w.week)}`}>{w.week ? usd(w.week, { sign: true }) : ""}</span>])}
    </div>
  </div>;
}
