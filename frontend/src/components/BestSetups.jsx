import { useCallback, useMemo, useState } from "react";
import { bestEntrySetups } from "../utils/marketPresentation.js";
import { REGIME_META, SIGNAL_META, getBaseSymbol } from '../theme.js';
import { cardLine, crowdRead, formingSetups, setupSide } from "../utils/intel.js";
import useSetupIntel from "../hooks/useSetupIntel.js";
import HelpTip from './HelpTip.jsx';
import SetupIntelDrawer, { CROWD_COLOR } from "./SetupIntelDrawer.jsx";

function Squares({ observed, required, color }) {
  return <span className="regime-progress" aria-hidden="true">
    {Array.from({ length: required }, (_, i) => <i key={i} style={i < observed ? { background: color, borderColor: color } : { borderColor: `${color}80` }} />)}
  </span>;
}

function Crowd({ row, intel }) {
  const read = crowdRead(setupSide(row), intel);
  return read ? <b className="best-setup-crowd" style={{ color: CROWD_COLOR[read.key] }}>{read.label}</b> : null;
}

export default function BestSetups({ results, timeframe, onSelect }) {
  const rows = useMemo(() => bestEntrySetups(results), [results]);
  const forming = useMemo(() => formingSetups(results, new Set(rows.map(r => r.symbol))), [results, rows]);
  const data = useSetupIntel([...rows, ...forming.map(f => f.row)].map(r => getBaseSymbol(r.symbol)));
  const [open, setOpen] = useState(null);
  const close = useCallback(() => setOpen(null), []);
  const intelOf = row => data?.coins?.[getBaseSymbol(row.symbol)] || null;
  const openChart = useCallback(row => { setOpen(null); onSelect(row); }, [onSelect]);
  if (!results.length) return null;
  const tfName = timeframe.toUpperCase();
  return <section className="best-setups">
    <div className="best-setups-heading"><h2>Best setups right now <HelpTip title="Setup ranking"><p>The three highest-priority confirmed long or short setups in this timeframe’s latest scanner snapshot, at most one per sector so the three are different bets. Ranked by the existing priority score, which combines conditions, band proximity, floor confirmation, momentum, heat room and volume. This is a research shortlist, not a performance forecast. Warnings remain visible in the full setup.</p><p>Each card shows how many profitable Hyperliquid traders hold the coin and how they sit against the setup. Open a card for the full picture: timing, entries, recent opens and context notes.</p></HelpTip></h2><span>{tfName} · latest scanner snapshot</span></div>
    {rows.length ? <div className="best-setups-grid">{rows.map(row => {
      const regime = REGIME_META[row.regime] || REGIME_META.FLAT; const signal = SIGNAL_META[row.signal] || SIGNAL_META.WAIT; const intel = intelOf(row);
      return <button type="button" key={row.symbol} onClick={() => setOpen(row)} style={{ '--regime-color': regime.color }}>
        <div><strong>{getBaseSymbol(row.symbol)}</strong><span>Priority {Math.round(row.priority_score)} / 100</span></div>
        <p>{regime.name} · {signal.label}</p>
        {row.sector && row.sector !== 'Other' && <em className="best-setup-sector">{[row.sector, row.ecosystem, row.size_tier && `${row.size_tier} size`].filter(Boolean).join(' · ')}</em>}
        <small>{row.conditions_met}/{row.conditions_total} checks {row.signal_warnings?.length ? ` · ${row.signal_warnings.length} context note${row.signal_warnings.length === 1 ? '' : 's'}` : ''}</small>
        {intel && <small className="best-setup-traders"><Crowd row={row} intel={intel} /> {cardLine(intel)}</small>}
        <small className="best-setup-open">Intel <span aria-hidden="true">→</span></small>
      </button>;
    })}</div> : <p>No qualifying entry setups in this snapshot.</p>}
    {forming.length > 0 && <div className="best-forming">
      <span className="best-forming-label">Forming <HelpTip title="Forming setups"><p>Coins whose regime is changing into Uptrend on the {tfName}, nearest to confirming first. Each square is one candle; the change happens when all are filled, and the percentage is how often past changes at this point completed. Before confirmation there is no entry signal: entering early did not pay on average in the transition study, so these are for watching.</p></HelpTip></span>
      {forming.map(({ row, left, odds }) => {
        const t = row.regime_transition, to = REGIME_META.MARKUP, intel = intelOf(row);
        return <button type="button" key={row.symbol} onClick={() => setOpen(row)}>
          <strong>{getBaseSymbol(row.symbol)}</strong>
          <span>{(REGIME_META[row.regime] || REGIME_META.FLAT).name} → {to.name}</span>
          <Squares observed={Math.min(t.observed_bars, t.required_bars)} required={t.required_bars} color={to.color} />
          <span>{left} more {tfName} close{left === 1 ? '' : 's'}{odds != null ? ` · ${odds}%` : ''}</span>
          {intel && <span><Crowd row={row} intel={intel} /></span>}
        </button>;
      })}
    </div>}
    {open && <SetupIntelDrawer row={open} intel={intelOf(open)} pulse={data?.pulse} onOpenChart={openChart} onClose={close} />}
  </section>;
}
