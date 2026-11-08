import { useEffect, useMemo, useRef, useState } from "react";
import Tabs from "./Tabs.jsx";
import MarketChart from "./MarketChart.jsx";
import { Info } from "./MarketHistorySections.jsx";
import { HCOPY, INDICATORS, heatSeries, heatState, heatTurns, pickIndicators } from "../utils/marketHeat.js";
import { RANGES, dayDate } from "../utils/marketHistory.js";

// The market page's Chart tab: Market heat today, then one large chart with the indicators the reader picks, on the
// price, as marks on their panes, or in panes under it. Where the market stands today is in the tiles above the tabs.

const KEY = "reflex-market-indicators-4";      // -4: the marks moved onto their panes (6 Nov 2026)
const loadPicks = () => { try { return pickIndicators(JSON.parse(localStorage.getItem(KEY))); } catch { return pickIndicators(null); } };
const savePicks = keys => { try { localStorage.setItem(KEY, JSON.stringify(keys)); } catch { /* the pick still holds for this visit */ } };
const pct = v => `${Math.round(100 * v)}%`;

// Market heat today, above the chart: its value and its state (hot, cooling, cold, lifting or neutral) since when.
function HeatLine({ rows }) {
  const series = useMemo(() => heatSeries(rows), [rows]);
  const turns = useMemo(() => heatTurns(series), [series]);
  const hs = heatState(series, turns);
  if (!hs) return null;
  return <div className="mch-head">
    <span className="mch-side">{HCOPY.title} <b>{Math.round(hs.heat)}</b>
      <span className={`mch-state is-${hs.word.toLowerCase()}`}>{HCOPY.states[hs.word]}
        {hs.since != null && <i>{HCOPY.since(dayDate(hs.since, false))}</i>}</span>
      <Info title={HCOPY.title} paras={HCOPY.pop()} /></span>
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
  // Turning a pane off takes the marks that sit on it with it; turning a mark on brings its pane.
  const toggle = key => setPicks(picks.includes(key)
    ? picks.filter(k => k !== key && INDICATORS.find(i => i.key === k)?.pane !== key)
    : pickIndicators([...picks, key]));
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
      {group("marks", HCOPY.marks)}
      {group("pane", HCOPY.below)}
    </div>}
  </div>;
}

export default function MarketChartView({ rows }) {
  const [picks, setPicksState] = useState(loadPicks);
  const [range, setRange] = useState("1y");
  const setPicks = keys => { setPicksState(keys); savePicks(keys); };
  return <div className="mch">
    <HeatLine rows={rows} />
    <div className="mch-tools">
      <Tabs small label="Range" items={RANGES} value={range} onChange={setRange} />
      <IndicatorMenu picks={picks} setPicks={setPicks} />
    </div>
    <MarketChart rows={rows} indicators={picks} range={range} />
  </div>;
}
