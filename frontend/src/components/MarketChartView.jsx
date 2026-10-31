import { useEffect, useMemo, useRef, useState } from "react";
import Tabs from "./Tabs.jsx";
import MarketChart from "./MarketChart.jsx";
import { Info } from "./MarketHistorySections.jsx";
import { BCOPY, HCOPY, INDICATORS, broadRuns, broadState, heatSeries, heatState, heatTurns, pickIndicators }
  from "../utils/marketHeat.js";
import { RANGES, dayDate } from "../utils/marketHistory.js";

// The market history page's Chart view: the share of coins in uptrend leads (owner, 29 October 2026: the market itself
// matters as much as BTC), with the broad uptrend's (or downturn's) day against past ones, its high (or low) and four
// marks; Market heat beside it; then one large chart with the indicators the reader picks, on the price or under it.

const KEY = "reflex-market-indicators-3";
const loadPicks = () => { try { return pickIndicators(JSON.parse(localStorage.getItem(KEY))); } catch { return pickIndicators(null); } };
const savePicks = keys => { try { localStorage.setItem(KEY, JSON.stringify(keys)); } catch { /* the pick still holds for this visit */ } };
const pct = v => `${Math.round(100 * v)}%`;

function Marks({ st, last }) {
  const crowd = last.wallet?.crowd?.L == null ? null : `${(100 * last.wallet.crowd.L).toFixed(1)}%`;   // one decimal beside a 30% or 86% line
  const vals = st.on ? { greed: st.fgHigh, crowd } : { fear: st.fgLow, short: crowd };
  return <span className="mch-marks">{Object.entries(st.on ? BCOPY.marks : BCOPY.downMarks).map(([k, label]) =>
    <span key={k} className={st.marks[k] ? "is-on" : ""}><i aria-hidden="true" />{label}
      {vals[k] != null && <b>{vals[k]}</b>}<span className="mch-sr">{st.marks[k] ? " (yes)" : " (no)"}</span></span>)}
  </span>;
}

function Headline({ rows }) {
  const br = useMemo(() => broadRuns(rows), [rows]);
  const series = useMemo(() => heatSeries(rows), [rows]);
  const turns = useMemo(() => heatTurns(series), [series]);
  const st = broadState(rows, br);
  const hs = heatState(series, turns);
  if (!st) return null;
  const last = rows[rows.length - 1];
  const run = st.run, down = st.down;
  const older = st.longer?.k > 0 && (st.on ? BCOPY.longer : BCOPY.downLonger)(st.longer.k, st.longer.n);
  return <div className="mch-head">
    <span className="mch-title">{BCOPY.title}<Info title={BCOPY.title} paras={st.on || !down ? BCOPY.pop() : BCOPY.downPop()} /></span>
    <strong className="mch-heat">{pct(st.share)}</strong>
    {st.on && <span className="mch-run">{BCOPY.on(st.age)}{older && <i>{older}</i>}
      <i>{BCOPY.high(pct(run.high), dayDate(run.highDay, false))}</i></span>}
    {!st.on && down && <span className="mch-run">{BCOPY.down(st.age)}{older && <i>{older}</i>}
      <i>{BCOPY.low(pct(down.low), dayDate(down.lowDay, false))}</i></span>}
    {!st.on && !down && run && <span className="mch-run">{BCOPY.ended(dayDate(run.end, false), run.end - run.start)}
      <i>{BCOPY.high(pct(run.high), dayDate(run.highDay, false))}</i></span>}
    {(st.on || down) && <Marks st={st} last={last} />}
    {hs && <span className="mch-side">{HCOPY.title} <b>{Math.round(hs.heat)}</b>
      <span className={`mch-state is-${hs.word.toLowerCase()}`}>{HCOPY.states[hs.word]}
        {hs.since != null && <i>{HCOPY.since(dayDate(hs.since, false))}</i>}</span>
      <Info title={HCOPY.title} paras={HCOPY.pop()} /></span>}
  </div>;
}

function IndicatorMenu({ picks, setPicks }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const off = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = e => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", off);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", off); document.removeEventListener("keydown", esc); };
  }, [open]);
  const toggle = key => setPicks(picks.includes(key) ? picks.filter(k => k !== key) : pickIndicators([...picks, key]));
  const group = (where, title) => <div className="mch-group" role="group" aria-label={title}>
    <h4>{title}</h4>
    {INDICATORS.filter(i => i.where === where).map(i => <label key={i.key}>
      <input type="checkbox" checked={picks.includes(i.key)} onChange={() => toggle(i.key)} />{i.label}</label>)}
  </div>;
  return <div className="mch-menu" ref={ref}>
    <button type="button" className="mch-menu-btn" aria-expanded={open} aria-controls="mch-menu-pop" onClick={() => setOpen(v => !v)}>
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 11 L5 6 L8 9 L13 3" fill="none" strokeWidth="1.6" /></svg>
      {HCOPY.indicators}</button>
    {open && <div id="mch-menu-pop" className="mch-menu-pop">
      {group("price", HCOPY.onPrice)}
      {group("pane", HCOPY.below)}
    </div>}
  </div>;
}

export default function MarketChartView({ rows }) {
  const [picks, setPicksState] = useState(loadPicks);
  const [range, setRange] = useState("1y");
  const setPicks = keys => { setPicksState(keys); savePicks(keys); };
  return <div className="mch">
    <Headline rows={rows} />
    <div className="mch-tools">
      <Tabs small label="Range" items={RANGES} value={range} onChange={setRange} />
      <IndicatorMenu picks={picks} setPicks={setPicks} />
    </div>
    <MarketChart rows={rows} indicators={picks} range={range} />
  </div>;
}
