import { useEffect, useMemo, useRef, useState } from "react";
import Tabs from "./Tabs.jsx";
import MarketChart from "./MarketChart.jsx";
import { Info } from "./MarketHistorySections.jsx";
import { HCOPY, INDICATORS, heatSeries, heatState, heatTurns, pickIndicators } from "../utils/marketHeat.js";
import { RANGES, dayDate } from "../utils/marketHistory.js";

// The market history page's Chart view: Market heat in one line on top (the number, its state and the three readings
// behind it), then one large chart with the indicators the reader picks, on the price or in panes under it.

const KEY = "reflex-market-indicators";
const loadPicks = () => { try { return pickIndicators(JSON.parse(localStorage.getItem(KEY))); } catch { return pickIndicators(null); } };
const savePicks = keys => { try { localStorage.setItem(KEY, JSON.stringify(keys)); } catch { /* the pick still holds for this visit */ } };

function Headline({ rows }) {
  const series = useMemo(() => heatSeries(rows), [rows]);
  const turns = useMemo(() => heatTurns(series), [series]);
  const st = heatState(series, turns);
  if (!st) return null;
  const last = series[series.length - 1];
  return <div className="mch-head">
    <span className="mch-title">{HCOPY.title}<Info title={HCOPY.title} paras={HCOPY.pop()} /></span>
    <strong className="mch-heat">{Math.round(st.heat)}</strong>
    <span className={`mch-state is-${st.word.toLowerCase()}`}>{HCOPY.states[st.word]}
      {st.since != null && <i>{HCOPY.since(dayDate(st.since, false))}</i>}</span>
    <span className="mch-parts">{["uptrend", "fg", "traders"].filter(k => last.parts[k] != null)
      .map(k => <span key={k}>{HCOPY.parts[k]} <b>{Math.round(last.parts[k])}</b></span>)}</span>
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
