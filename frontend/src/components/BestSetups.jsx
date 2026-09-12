import { bestEntrySetups } from "../utils/marketPresentation.js";
import { REGIME_META, SIGNAL_META, getBaseSymbol } from '../theme.js';
import HelpTip from './HelpTip.jsx';
export default function BestSetups({ results, timeframe, onSelect }) {
  const rows=bestEntrySetups(results);
  if(!results.length) return null;
  return <section className="best-setups">
    <div className="best-setups-heading"><h2>Best setups right now <HelpTip title="Setup ranking"><p>The three highest-priority long or accumulation signals in this timeframe’s latest scanner snapshot. Ranked by the existing priority score, which combines conditions, band proximity, floor confirmation, momentum, heat room and volume. This is a research shortlist, not a performance forecast. Warnings remain visible in the full setup.</p></HelpTip></h2><span>{timeframe.toUpperCase()} · latest scanner snapshot</span></div>
    {rows.length ? <div className="best-setups-grid">{rows.map(row=>{const regime=REGIME_META[row.regime] || REGIME_META.FLAT;const signal=SIGNAL_META[row.unified_signal || row.signal] || SIGNAL_META.WAIT;return <button type="button" key={row.symbol} onClick={()=>onSelect(row)} style={{'--regime-color':regime.color}}><div><strong>{getBaseSymbol(row.symbol)}</strong><span>Priority {Math.round(row.priority_score)} / 100</span></div><p>{regime.name} · {signal.label}</p><small>{row.conditions_met}/{row.conditions_total} checks · {row.signal_warnings?.length || 0} warnings <span aria-hidden="true">↗</span></small></button>})}</div> : <p>No qualifying entry setups in this snapshot.</p>}
  </section>;
}
