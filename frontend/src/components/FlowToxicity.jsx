import { T, col } from '../theme.js';
import HelpTip from './HelpTip.jsx';

// Current reading only: VPIN history is not persisted, so no trend is drawn.
export default function FlowToxicity({ vpin }) {
  const valid = Number.isFinite(vpin) && vpin >= 0 && vpin <= 1;
  const pct = valid ? vpin * 100 : null;
  const label = !valid ? 'Unavailable' : pct >= 55 ? 'High imbalance' : pct >= 30 ? 'Elevated' : 'Balanced';
  const color = !valid ? T.text3 : col(pct >= 55 ? '#c6a46d' : pct >= 30 ? '#b6a07c' : '#91b9e8');
  return <section aria-label="Flow toxicity" className="flow-toxicity">
    <div className="flow-toxicity-header">
      <div><span className="flow-toxicity-title">Flow toxicity <span style={{color:T.text4,fontSize:T.textXs}}> / VPIN</span></span> <HelpTip title="VPIN · flow imbalance" width={340}>
        <p>Reflex averages |taker buys − taker sells| / (taker buys + taker sells) across provider bars. This is a flow imbalance proxy; the percentage is not a probability of informed trading.</p>
        <p>Balanced: below 30%. Elevated: 30% to below 55%. High imbalance: 55% and above. Higher readings indicate more one-sided flow. Direction is shown separately in CVD.</p>
      </HelpTip></div>
      <div className="flow-toxicity-value"><span>{label}</span><strong style={{color}}>{valid ? `${pct.toFixed(0)}%` : '—'}</strong></div>
    </div>
  </section>;
}
