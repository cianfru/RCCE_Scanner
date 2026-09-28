import { useEffect, useState } from "react";
import { col, getBaseSymbol } from "../theme.js";
import TokenLogo from "./TokenLogo.jsx";
import { OPP_STATUS_HEX, ageShort, oppStatusWord } from "../utils/opportunityRows.js";
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const PREVIEW = 5;
const PREVIEW_PHONE = 3;

// One compact row: logo, ticker, timeframe, status word in its colour, reason, age.
export function OppRow({ symbol, timeframe, status, reason, ts, onClick }) {
  const hex = OPP_STATUS_HEX[status];
  const body = <>
    <TokenLogo symbol={symbol} size={16} />
    <b className="opp-sym">{getBaseSymbol(symbol || "?")}</b>
    <span className="opp-tf">{String(timeframe || "").toUpperCase()}</span>
    <span className="opp-status" data-status={status} style={hex ? { color: col(hex) } : undefined}>{oppStatusWord(status)}</span>
    <span className="opp-reason">{reason}</span>
    <span className="opp-age">{ageShort(ts)}</span>
  </>;
  return onClick
    ? <button type="button" className="opp-row" title={reason} onClick={onClick}>{body}</button>
    : <div className="opp-row" title={reason}>{body}</div>;
}

// A titled block of rows showing the first few, with "Show all N" for the rest.
export function OppList({ title, items, render }) {
  const [all, setAll] = useState(false);
  const [phone, setPhone] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(max-width: 767px)").matches);
  useEffect(() => {
    const mq = window.matchMedia?.("(max-width: 767px)");
    if (!mq) return undefined;
    const on = () => setPhone(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  if (!items.length) return null;
  const preview = phone ? PREVIEW_PHONE : PREVIEW;
  return <section className="opp-list" aria-label={title}>
    <h3 className="opp-list-head">{title} <span>{items.length}</span></h3>
    <div className="opp-rows">{(all ? items : items.slice(0, preview)).map(render)}</div>
    {items.length > preview && <button type="button" className="te-link opp-more" aria-expanded={all} onClick={() => setAll(a => !a)}>
      {all ? "Show fewer" : `Show all ${items.length}`}</button>}
  </section>;
}

export default function OpportunityActivity({ onSelect }) {
  const [events, setEvents] = useState([]);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch(`${API}/api/opportunities/transitions?limit=12`, { signal: controller.signal });
        if (response.ok) setEvents((await response.json()).events || []);
      } catch { /* The scanner remains usable if activity history is unavailable. */ }
    };
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  return <OppList title="Recent opportunity changes" items={events} render={e =>
    <OppRow key={e.id} symbol={e.symbol} timeframe={e.timeframe} status={e.status} reason={e.opportunity?.reason} ts={e.observed_at}
      onClick={onSelect ? () => onSelect({ symbol: e.symbol, timeframe: e.timeframe }) : undefined} />} />;
}
