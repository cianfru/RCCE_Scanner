import { T } from '../theme.js';
export default function StatCards({ results, activeSignalFilter, onSignalFilter }) {
  const count = {};
  results.forEach(row => { const key = row.unified_signal || row.signal; count[key] = (count[key] || 0) + 1; });
  const items = [['Strong long','STRONG_LONG',count.STRONG_LONG || 0,T.green],['Light long','LIGHT_LONG',count.LIGHT_LONG || 0,T.greenDim],['Accumulate','ACCUMULATE',count.ACCUMULATE || 0,'#91b9e8'],['Trim','TRIM',(count.TRIM || 0)+(count.TRIM_HARD || 0),T.yellow],['Risk-off','RISK_OFF',count.RISK_OFF || 0,T.red]];
  return <div className="scanner-signal-summary" aria-label="Filter by signal">{items.map(([label,key,value,color]) => <button key={key} type="button" aria-pressed={activeSignalFilter===key} disabled={!value && activeSignalFilter!==key} onClick={()=>onSignalFilter?.(activeSignalFilter===key ? null : key)} style={{'--signal-color':color}}><span>{label}</span><strong>{value}</strong></button>)}</div>;
}
