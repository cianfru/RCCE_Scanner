import { Link2, Unlink, Minus, CircleDashed } from 'lucide-react';
import { T, col } from '../theme.js';
import { setupAlignment, signalDirection } from '../utils/signalPresentation.js';
import { RegimeBadge, SignalDot } from './badges.jsx';
import HelpTip from './HelpTip.jsx';
import RegimeTransition from './RegimeTransition.jsx';

export default function SetupPair({ row, isMobile, transition = false, compact = false, marketWide }) {
  const alignment = setupAlignment(row, { marketWide });
  const color = col(({bullish:'#97FCE4',bearish:'#cf9185',conflict:'#fb923c',caution:'#fbbf24'})[alignment.state] || '#52525b');
  const direction = signalDirection(row.signal);
  const relationship = alignment.strength ? `The broader trend supports this ${direction === "bearish" ? "short" : "long"} setup.` : alignment.state === "conflict" ? "The current signal runs against the broader trend." : alignment.state === "incomplete" ? "Required context is missing. Check the information icon beside the signal." : "The market structure does not currently confirm a directional entry.";
  const Icon = alignment.strength ? Link2 : alignment.state === 'conflict' ? Unlink : alignment.state === 'incomplete' ? CircleDashed : Minus;
  return <div className="setup-pair-wrap">
    <div className="setup-pair" data-strength={alignment.strength} aria-label={`Regime and signal: ${alignment.label}`}
      style={{'--setup-color':color,'--setup-fill':alignment.strength ? `${color}${alignment.strength === 2 ? '10' : '06'}` : 'transparent'}}>
      <span className="setup-pair-regime"><RegimeBadge regime={row.regime} isMobile={isMobile}/></span>
      <HelpTip title={alignment.label} label={`Setup alignment: ${alignment.label}`} width={300} size={16}
        buttonStyle={{border:0,color,background:'transparent'}} icon={<Icon size={13}/> }>
        <p>{relationship}</p>
        <p>Signal strength controls emphasis. Alignment is not an independent confirmation or a win probability.</p>
      </HelpTip>
      <span className="setup-pair-signal"><SignalDot signal={row.signal} reason={row.signal_reason} warnings={row.signal_warnings} context={row} marketWide={marketWide} isMobile={isMobile}/></span>
    </div>
    {transition && <RegimeTransition data={row} compact={compact}/>}
  </div>;
}
