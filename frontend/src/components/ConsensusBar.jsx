import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

export default function ConsensusBar({ consensus, activeTab, onTabChange, searchTerm, onSearchChange }) {
  const color = ({ "RISK-ON": T.green, EUPHORIA: T.yellow, "RISK-OFF": T.red,
    ACCUMULATION: T.cyan, MIXED: T.text2 })[consensus?.consensus] || T.text3;
  const strength = Math.max(0, Math.min(100, Number(consensus?.strength) || 0));
  return <FadeIn delay={350}>
    <GlassCard style={{ marginTop: T.sp3, padding: "16px 20px" }}>
      <div className="scanner-toolbar">
        <div className="scanner-timeframes" role="group" aria-label="Analysis timeframe">
          {[["4h", "4H"], ["1d", "1D"]].map(([key, label]) =>
            <button key={key} aria-pressed={activeTab === key} onClick={() => onTabChange?.(key)}>{label}</button>)}
        </div>
        <div className="scanner-search">
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/></svg>
          <input aria-label="Search scanner markets" placeholder="Search Hyperliquid markets…" value={searchTerm || ""} onChange={e => onSearchChange?.(e.target.value)}/>
          {searchTerm && <button aria-label="Clear search" onClick={() => onSearchChange?.("")}>×</button>}
        </div>
        <div className="scanner-consensus" style={{ "--consensus-color": color }}>
          <div><span>Market consensus</span><strong>{consensus?.consensus || "Awaiting analysis"}</strong></div>
          <div className="scanner-strength"><span>Strength <b>{consensus ? `${Math.round(strength)}%` : "—"}</b></span>
            <div className="scanner-strength-track"><i style={{ width: `${strength}%` }}/></div>
          </div>
        </div>
      </div>
    </GlassCard>
  </FadeIn>;
}
