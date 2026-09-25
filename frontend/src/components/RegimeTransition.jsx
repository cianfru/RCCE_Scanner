import HelpTip from './HelpTip.jsx';
import { REGIME_META, T } from '../theme.js';

export default function RegimeTransition({ data, compact = false }) {
  const transition = data?.regime_transition;
  const limited = data?.history_bars > 0 && data.normalization_ready === false;
  if (!transition && !limited) return null;
  const text = [transition && `→ ${REGIME_META[transition.candidate]?.name || transition.candidate} ${transition.observed_bars}/${transition.required_bars}`,
    limited && (compact ? 'Short history' : 'Limited history')].filter(Boolean).join(' · ');
  return <span className={compact ? 'regime-note-compact' : undefined} onClick={event => event.stopPropagation()} style={{ display: 'inline-flex', flexWrap: compact ? 'nowrap' : 'wrap', alignItems: 'center', gap: compact ? 4 : 6,
    fontSize: compact ? 10 : 11, lineHeight: compact ? '14px' : 1.6, height: compact ? 14 : undefined, fontFamily: T.mono, color: T.text3, maxWidth: '100%', whiteSpace: compact ? 'nowrap' : undefined }}>
    <span style={compact ? { overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 } : undefined}>{compact ? text : <>{transition && <span>→ {REGIME_META[transition.candidate]?.name || transition.candidate} pending · {transition.observed_bars}/{transition.required_bars}</span>}{transition && limited && ' · '}{limited && <span>Limited history</span>}</>}</span>
    <HelpTip title="Regime confirmation" size={compact ? 14 : undefined}>
      {transition && <p>The engine is considering {REGIME_META[transition.candidate]?.name || transition.candidate}. It has observed {transition.observed_bars} of the {transition.required_bars} consecutive candidate candles required to change the regime. The latest candle may still be forming, so this count can change. The existing regime remains in effect; this is not a new trading signal.</p>}
      {limited && <p>Only {data.history_bars} candles are available. Full regression and normalization need at least 499 candles. Treat this reading as provisional until enough history exists.</p>}
    </HelpTip>
  </span>;
}
