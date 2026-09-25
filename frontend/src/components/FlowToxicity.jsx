import { T } from '../theme.js';
import HelpTip from './HelpTip.jsx';

export default function FlowToxicity({ vpin, vpinHistory = [] }) {
  const valid = Number.isFinite(vpin) && vpin >= 0 && vpin <= 1;
  const history = vpinHistory.filter(v => Number.isFinite(v) && v >= 0 && v <= 1);
  const pct = valid ? vpin * 100 : null;
  const label = !valid ? 'Unavailable' : pct >= 55 ? 'High imbalance' : pct >= 30 ? 'Elevated' : 'Balanced';
  const color = !valid ? T.text3 : pct >= 55 ? '#c6a46d' : pct >= 30 ? '#b6a07c' : '#91b9e8';
  const delta = history.length >= 2 ? (history.at(-1) - history[0]) * 100 : null;
  const w = 360, h = 118, left = 32, right = 350, top = 8, bottom = 100;
  const y = value => bottom - value * (bottom - top);
  const points = history.map((v,i) => `${left+i*(right-left)/Math.max(1,history.length-1)},${y(v)}`).join(' ');
  return <section aria-label="Flow toxicity" className="flow-toxicity">
    <div className="flow-toxicity-header">
      <div><span className="flow-toxicity-title">Flow toxicity <span style={{color:T.text4,fontSize:10}}> / VPIN</span></span> <HelpTip title="VPIN · flow imbalance" width={340}>
        <p>Reflex averages |taker buys − taker sells| / (taker buys + taker sells) across provider bars. This is a flow imbalance proxy; the percentage is not a probability of informed trading.</p>
        <p>Balanced: below 30%. Elevated: 30% to below 55%. High imbalance: 55% and above. Higher readings indicate more one-sided flow. Direction is shown separately in CVD.</p>
        <p>History contains scanner observations without timestamps. Spacing represents observations, not elapsed time.</p>
      </HelpTip></div>
      <div className="flow-toxicity-value"><span>{label}</span><strong style={{color}}>{valid ? `${pct.toFixed(0)}%` : '—'}</strong></div>
    </div>
    {history.length >= 2 ? <>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`VPIN history across ${history.length} observations. Thresholds at 30 and 55 percent.`} className="flow-toxicity-history">
        <rect x={left} y={top} width={right-left} height={y(.55)-top} fill="#f59e0b12"/>
        <rect x={left} y={y(.55)} width={right-left} height={y(.3)-y(.55)} fill="#fbbf2409"/>
        {[0,.3,.55,1].map(v=><g key={v}><line x1={left} x2={right} y1={y(v)} y2={y(v)} stroke={v===.3 || v===.55 ? '#fbbf2440' : '#91b9e825'} strokeDasharray="3 4"/><text x={left-6} y={y(v)+3} fill="#94a3b8" fontSize="9" textAnchor="end">{Math.round(v*100)}</text></g>)}
        <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round"/>
        <circle cx={right} cy={y(history.at(-1))} r="3" fill={color}/>
        <text x={left} y={116} fill="#94a3b8" fontSize="9">Older</text><text x={right} y={116} fill="#94a3b8" fontSize="9" textAnchor="end">Latest observation</text>
      </svg>
      <p className="flow-toxicity-caption">{Math.abs(delta)<.05 ? 'Unchanged' : `${delta>0 ? 'Rising' : 'Falling'} · ${delta>0?'+':''}${delta.toFixed(1)} percentage points`} across {history.length} observations</p>
    </> : <p style={{fontSize:11,color:T.text3,margin:'12px 0'}}>History unavailable — at least two observations are needed.</p>}

  </section>;
}
