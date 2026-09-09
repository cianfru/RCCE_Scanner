import { T } from '../theme.js';
import HelpTip from './HelpTip.jsx';
const explanations = {
  STRONG_LONG: 'The engine finds strong weighted support for a long setup in a supportive market phase. It checks trend, price extension, heat, divergence and available positioning data. Markup setups face stricter entry rules; crowding or repeated regime changes can reduce the label to Light long.',
  LIGHT_LONG: 'A long setup has support, but it does not meet the stricter Strong long criteria or a caution reduces its strength. Reasons can include a more extended price, crowded funding, unstable market phases or weaker confirmation.',
  ACCUMULATE: 'The engine sees potential basing, absorption or reaccumulation, without full confirmation for a stronger long label. It can also result when a reaccumulation setup lacks demand confirmation. This is an early setup to investigate, not a confirmed breakout.',
  TRIM: 'The engine detects overextension or a blowoff phase that triggers its reduction rules. This count includes Trim and the more urgent Trim hard. An exit warning on either timeframe takes priority over entry signals.',
  RISK_OFF: 'The engine identifies a markdown phase together with risk-off market consensus, triggering its defensive exit label. This is not the same as a short-entry signal. Exit warnings take priority across timeframes.',
};
export default function StatCards({ results, activeSignalFilter, onSignalFilter }) {
  const count = {};
  results.forEach(row => { const key = row.unified_signal || row.signal; count[key] = (count[key] || 0) + 1; });
  const items = [['Strong long','STRONG_LONG',count.STRONG_LONG || 0,T.green],['Light long','LIGHT_LONG',count.LIGHT_LONG || 0,T.greenDim],['Accumulate','ACCUMULATE',count.ACCUMULATE || 0,'#91b9e8'],['Trim','TRIM',(count.TRIM || 0)+(count.TRIM_HARD || 0),T.yellow],['Risk-off','RISK_OFF',count.RISK_OFF || 0,T.red]];
  return <div className="scanner-signal-summary" aria-label="Filter by signal">{items.map(([label,key,value,color]) => <div className="scanner-signal-item" key={key} style={{'--signal-color':color}}>
    <button type="button" aria-pressed={activeSignalFilter===key} disabled={!value && activeSignalFilter!==key} onClick={()=>onSignalFilter?.(activeSignalFilter===key ? null : key)}><span>{label}</span><strong>{value}</strong></button>
    <HelpTip title={label}><p>{explanations[key]}</p><p>These counts use the combined 4H/1D signal when available: exit warnings win, and when both timeframes have entry signals the weaker label wins. Open a coin’s “Why this signal?” and entry conditions for its exact reasons. Strength is not a win probability.</p></HelpTip>
  </div>)}</div>;
}
