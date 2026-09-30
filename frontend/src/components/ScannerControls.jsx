import Tabs from "./Tabs.jsx";

const MARKETS = [{ key: "perpetual", label: "Perps" }, { key: "spot", label: "Spot" }];

// Timeframe tabs and the Perps | Spot pair (768px and wider), in the title row. Search lives in
// the header (GlobalSearch), on every page.
export default function ScannerControls({ activeTab, onTabChange, marketKind, onMarketChange }) {
  return <>
    <div className="scanner-timeframes" role="group" aria-label="Analysis timeframe">
      {[["4h", "4H"], ["1d", "1D"]].map(([key, label]) =>
        <button key={key} type="button" aria-pressed={activeTab === key} onClick={() => onTabChange?.(key)}>{label}</button>)}
    </div>
    {onMarketChange && <div className="scanner-market">
      <span className="scanner-market-rule" aria-hidden="true" />
      <Tabs label="Market" items={MARKETS} value={marketKind} onChange={k => { if (k !== marketKind) onMarketChange(k); }} />
    </div>}
  </>;
}
