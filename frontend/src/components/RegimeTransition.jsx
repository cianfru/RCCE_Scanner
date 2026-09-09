import HelpTip from './HelpTip.jsx';
import { REGIME_META, T } from '../theme.js';

export default function RegimeTransition({ data }) {
  const transition = data?.regime_transition;
  const limited = data?.history_bars > 0 && data.normalization_ready === false;
  if (!transition && !limited) return null;
  return <span onClick={event => event.stopPropagation()} style={{ display: 'inline-flex', flexWrap: 'wrap', alignItems: 'center', gap: 6,
    fontSize: 11, lineHeight: 1.6, fontFamily: T.mono, color: T.text3, maxWidth: '100%' }}>
    {transition && <span>→ {REGIME_META[transition.candidate]?.label || transition.candidate} pending · {transition.observed_bars}/{transition.required_bars}</span>}
    {limited && <span>Limited history</span>}
    <HelpTip title="Regime confirmation">
      {transition && <p>The engine is considering {REGIME_META[transition.candidate]?.label || transition.candidate}. It has observed {transition.observed_bars} of the {transition.required_bars} consecutive candidate candles required to change the regime. The latest candle may still be forming, so this count can change. The existing regime remains in effect; this is not a new trading signal.</p>}
      {limited && <p>Only {data.history_bars} candles are available. Full regression and normalization need at least 499 candles. Treat this reading as provisional until enough history exists.</p>}
    </HelpTip>
  </span>;
}
