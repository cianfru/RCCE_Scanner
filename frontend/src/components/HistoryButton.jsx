import { useEffect, useState } from "react";
import { getStorage, markHistorySeen, showHistoryDot } from "../utils/marketSpark.js";

// Every button that opens the Market history drawer notes it here: the one-time dot on the card's sparkline
// goes away for good, also when the drawer was opened from the Fear & Greed dial.
const listeners = new Set();
let seenThisTab = false;

export function noteHistoryOpened() {
  seenThisTab = true;
  markHistorySeen(getStorage());
  listeners.forEach(fn => fn());
}

export function useHistoryDot() {
  const [dot, setDot] = useState(() => !seenThisTab && showHistoryDot(getStorage()));
  useEffect(() => {
    const off = () => setDot(false);
    listeners.add(off);
    return () => { listeners.delete(off); };
  }, []);
  return dot;
}

// Small chart icon beside an (i): opens the market history drawer.
export default function HistoryButton({ label, onClick, dot = false }) {
  return <button type="button" className="history-btn" aria-label={label} title={label}
    onClick={e => { noteHistoryOpened(); onClick?.(e); }}>
    <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
      <polyline points="1,9 4,5.5 6.5,7.5 11,2" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    {dot && <span className="history-dot" aria-hidden="true" />}
  </button>;
}
