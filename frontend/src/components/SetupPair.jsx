import { Lock, Unlink, Minus, CircleDashed } from 'lucide-react';
import { T, col } from '../theme.js';
import { setupAlignment, signalDirection } from '../utils/signalPresentation.js';
import { RegimeBadge, SignalDot } from './badges.jsx';
import HelpTip from './HelpTip.jsx';
import RegimeTransition from './RegimeTransition.jsx';

const SETUP_HUES = { bullish: '#97FCE4', bearish: '#cf9185', conflict: '#fb923c', caution: '#fbbf24' };
export function setupColor(alignment) {
  return col(SETUP_HUES[alignment.state] || '#52525b');
}

export default function SetupPair({ row, isMobile, transition = false, compact = false, marketWide }) {
  const alignment = setupAlignment(row, { marketWide });
  const color = setupColor(alignment);
  const direction = signalDirection(row.signal);
  const relationship = alignment.strength ? `The broader trend supports this ${direction === "bearish" ? "short" : "long"} setup.` : alignment.state === "conflict" ? "The current signal runs against the broader trend." : alignment.state === "incomplete" ? "Required context is missing. Check the information icon beside the signal." : "The market structure does not currently confirm a directional entry.";
  // Locked in: the regime's trend and the entry signal point the same way. The pair
  // becomes one outlined unit with a lock; Strong signals get the stronger outline.
  const locked = alignment.strength > 0;
  const Icon = locked ? Lock : alignment.state === 'conflict' ? Unlink : alignment.state === 'incomplete' ? CircleDashed : Minus;
  return <div className="setup-pair-wrap">
    <div className="setup-pair" data-locked={locked} data-strength={alignment.strength} aria-label={`Regime and signal: ${alignment.label}`}
      style={{'--setup-color':color}}>
      <span className="setup-pair-regime"><RegimeBadge regime={row.regime} isMobile={isMobile} noHistory={row.history_bars === 0}/></span>
      <HelpTip className="setup-pair-link" title={alignment.label} label={`Setup alignment: ${alignment.label}`} width={300} size={16}
        buttonStyle={{border:0,color,background:'transparent'}} icon={<Icon size={locked ? 12 : 13} strokeWidth={locked ? 2.4 : 2}/> }>
        <p>{relationship}</p>
        <p>{locked ? 'Locked in: the trend and the entry signal agree, so this setup ranks first under “Aligned setups first”. ' : ''}Signal strength controls emphasis. Alignment is not an independent confirmation or a win probability.</p>
      </HelpTip>
      <span className="setup-pair-signal"><SignalDot signal={row.signal} reason={row.signal_reason} warnings={row.signal_warnings} context={row} marketWide={marketWide} isMobile={isMobile}/></span>
    </div>
    {transition && <RegimeTransition data={row} compact={compact}/>}
  </div>;
}
