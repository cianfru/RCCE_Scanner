import { useEffect, useRef } from "react";
import Tabs from "./Tabs.jsx";

const MARKETS = [{ key: "perpetual", label: "Perps" }, { key: "spot", label: "Spot" }];

// Typing in a field (or a rich-text box) keeps its own "/".
const typing = t => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));

// Timeframe tabs, the Perps | Spot pair (768px and wider) and search, in the title row.
export default function ScannerControls({ activeTab, onTabChange, searchTerm, onSearchChange, marketKind, onMarketChange }) {
  const input = useRef(null);
  // "/" focuses the search, the way most scanners and code hosts do it.
  useEffect(() => {
    const onKey = e => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented || typing(e.target)) return;
      if (window.location.pathname.replace(/\/+$/, "") !== "/scanner") return;
      e.preventDefault();
      input.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return <>
    <div className="scanner-timeframes" role="group" aria-label="Analysis timeframe">
      {[["4h", "4H"], ["1d", "1D"]].map(([key, label]) =>
        <button key={key} type="button" aria-pressed={activeTab === key} onClick={() => onTabChange?.(key)}>{label}</button>)}
    </div>
    {onMarketChange && <div className="scanner-market">
      <span className="scanner-market-rule" aria-hidden="true" />
      <Tabs label="Market" items={MARKETS} value={marketKind} onChange={k => { if (k !== marketKind) onMarketChange(k); }} />
    </div>}
    <div className="scanner-search">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/></svg>
      <input ref={input} aria-label="Search scanner markets" aria-keyshortcuts="/" placeholder="Search Hyperliquid markets…" value={searchTerm || ""} onChange={e => onSearchChange?.(e.target.value)}/>
      {searchTerm
        ? <button type="button" aria-label="Clear search" onClick={() => onSearchChange?.("")}>×</button>
        : <kbd className="search-hint" aria-hidden="true" title="Press / to search">/</kbd>}
    </div>
  </>;
}
