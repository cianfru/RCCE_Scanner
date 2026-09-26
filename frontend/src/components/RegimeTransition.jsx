import HelpTip from './HelpTip.jsx';
import RegimeIcon from './RegimeIcon.jsx';
import { REGIME_META, T } from '../theme.js';
import { completionOdds } from '../utils/regimeOdds.js';

// Candles counted toward a pending regime change, one square per candle, filled in
// the incoming regime's colour. The regime changes when every square is filled.
function Progress({ observed, required, color }) {
  return <span className="regime-progress" role="img" aria-label={`${observed} of ${required} candles`}>
    {Array.from({ length: required }, (_, i) => (
      <i key={i} style={i < observed ? { background: color, borderColor: color } : { borderColor: `${color}80` }} />
    ))}
  </span>;
}

export default function RegimeTransition({ data, compact = false }) {
  const transition = data?.regime_transition;
  // With no history at all the regime cell already reads "No history" (RegimeBadge).
  if (data?.history_bars === 0) return null;
  const limited = data?.history_bars > 0 && data.normalization_ready === false;
  if (!transition && !limited) return null;
  const target = transition && (REGIME_META[transition.candidate] || REGIME_META.FLAT);
  const observed = transition ? Math.min(transition.observed_bars, transition.required_bars) : 0;
  const odds = transition ? completionOdds(data.timeframe, data.regime, transition.candidate, observed) : null;
  return <span className={compact ? 'regime-note regime-note-compact' : 'regime-note'} onClick={event => event.stopPropagation()}
    style={{ display: 'inline-flex', flexWrap: compact ? 'nowrap' : 'wrap', alignItems: 'center', gap: compact ? 6 : 8,
      fontSize: compact ? 10 : 11, lineHeight: compact ? '14px' : 1.6, height: compact ? 14 : undefined, fontFamily: T.mono,
      color: T.text3, maxWidth: '100%', whiteSpace: compact ? 'nowrap' : undefined }}>
    {transition && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: target.color, minWidth: 0 }}>
      <span aria-hidden="true">→</span>
      <RegimeIcon regime={transition.candidate} size={compact ? 11 : 12} />
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{target.name}</span>
      <Progress observed={observed} required={transition.required_bars} color={target.color} />
      {odds != null && <span title={`${odds}% of past changes at this square completed`} style={{ color: T.text3 }}>{odds}%</span>}
    </span>}
    {limited && <span>{compact ? 'Short history' : 'Limited history'}</span>}
    <HelpTip title="Regime confirmation" size={compact ? 14 : undefined}>
      {transition && <p>The engine is considering {target.name}. It has observed {transition.observed_bars} of the {transition.required_bars} consecutive candidate candles required to change the regime; each filled square is one candle. The latest candle may still be forming, so this count can change. The existing regime remains in effect; this is not a new trading signal.</p>}
      {transition && odds != null && <p>Historically, {odds}% of changes from {REGIME_META[data.regime]?.name || data.regime} to {target.name} seen at square {observed} went on to complete ({String(data.timeframe || '').toUpperCase()}, 2021 to March 2026). On the daily chart, entering before confirmation did not pay on average: the false starts cost more than the earlier price saved.</p>}
      {limited && <p>Only {data.history_bars} candles are available. Full regression and normalization need at least 499 candles. Treat this reading as provisional until enough history exists.</p>}
    </HelpTip>
  </span>;
}
