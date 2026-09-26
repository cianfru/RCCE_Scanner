// Timeframe tabs and search, in the title row.
export default function ScannerControls({ activeTab, onTabChange, searchTerm, onSearchChange }) {
  return <>
    <div className="scanner-timeframes" role="group" aria-label="Analysis timeframe">
      {[["4h", "4H"], ["1d", "1D"]].map(([key, label]) =>
        <button key={key} type="button" aria-pressed={activeTab === key} onClick={() => onTabChange?.(key)}>{label}</button>)}
    </div>
    <div className="scanner-search">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/></svg>
      <input aria-label="Search scanner markets" placeholder="Search Hyperliquid markets…" value={searchTerm || ""} onChange={e => onSearchChange?.(e.target.value)}/>
      {searchTerm && <button type="button" aria-label="Clear search" onClick={() => onSearchChange?.("")}>×</button>}
    </div>
  </>;
}
