import { formatPercent, signalAgreement } from "../utils/marketPresentation.js";
import { friendlyReason } from "../utils/signalPresentation.js";
import { PREVIEW_COINS } from "../utils/previewRows.js";
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DataTable from '../components/DataTable.jsx';
import { Mark } from './Mark';
import { SCANNER_COLUMNS } from '../scannerColumns.js';
import useViewport from '../hooks/useViewport.js';
import { REGIME_META, themeVars } from '../theme.js';
import { usePreviewFeed } from './previewFeed.js';
import '../terminal.css';

// The landing is always dark, so the embedded table keeps the dark palette even when the app is in light mode.
const DARK_VARS = themeVars('dark');
// Phones: the coin, its regime/signal pair and its rank, so the table fits without scrolling.
const PHONE_COLUMNS = ['SYMBOL', 'REGIME', 'SIGNAL', 'PRI'].map(label => SCANNER_COLUMNS.find(([, l]) => l === label));

export default function LiveScannerPreview() {
  const [exampleCoin, setExampleCoin] = useState('BTC');
  const state = usePreviewFeed();
  const [sort, setSort] = useState('priority_score');
  const navigate = useNavigate();
  const { width } = useViewport();
  const phone = width <= 640;
  const columns = phone ? PHONE_COLUMNS : SCANNER_COLUMNS;
  const rows = [...state.rows].sort((a,b) => sort === 'symbol' ? a.symbol.localeCompare(b.symbol) : sort === 'regime' ? String(a.regime).localeCompare(String(b.regime)) : (b[sort] || 0) - (a[sort] || 0));
  const example = state.rows.find(row => row.symbol.split('/')[0] === exampleCoin);
  return <div className="r-terminal-wrap"><div className="r-terminal glass">
    <div className="r-terminal-bar"><span className="r-terminal-title"><Mark size={22}/> reflex <i/> scanner</span><span className="r-terminal-data">{state.error ? 'Feed unavailable' : state.loading ? 'Connecting to scanner' : 'Latest scanner snapshot'}</span></div>
    <div className="r-terminal-body">
      <div className="r-terminal-heading"><div><span className="r-meta">THE MAIN MARKETS</span><h2>Inside the terminal</h2></div><span className="r-meta">DAILY · 1D</span></div>
      <p className="r-scroll-hint">{phone ? `${PHONE_COLUMNS.length - 1} of ${SCANNER_COLUMNS.length} columns at this width. The app has them all.` : `Scroll horizontally to explore all ${SCANNER_COLUMNS.length} columns. The symbol stays in view.`}</p>
      <div className="reflex-terminal r-preview-table-wrap" data-phone={phone || undefined} style={DARK_VARS}>
        {state.error && <p role="status" style={{ padding: '16px 0' }}>{state.error}{state.rows.length > 0 ? ' Showing the last received snapshot.' : ' Open the terminal to check the connection.'}</p>}
        {!state.loading && !state.error && !rows.length ? <p role="status">No markets in this snapshot yet.</p> : (!state.error || rows.length > 0) && <DataTable results={rows} sortKey={sort} onSort={setSort} visibleColumns={columns} loading={state.loading} isMobile={phone} onSelect={row => navigate(`/scanner/${row.symbol.split('/')[0]}`)}/>}
      </div>
      <div className="r-terminal-bottom"><span>{state.updated ? `Received ${state.updated.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})} · refreshes every 5 minutes` : 'Signals from the same API as the terminal'}</span><a href="/scanner">Open full scanner ↗</a></div>
    </div></div>
    {example && <section className="r-reading-example" aria-label="Reading a real setup">
      <div className="r-reading-heading"><div><span className="r-meta">READ THE EVIDENCE</span><h3>One market. Three questions.</h3></div>
      <label>Market <select aria-label="Example market" value={exampleCoin} onChange={event=>setExampleCoin(event.target.value)}>{PREVIEW_COINS.map(coin=><option key={coin}>{coin}</option>)}</select></label></div>
      <div className="r-reading-grid">
        <article><span>01 / What is the phase?</span><h4>{REGIME_META[example.regime]?.name ?? example.regime}</h4><p>{exampleCoin} is classified in this daily regime, with a Z-score of {example.zscore?.toFixed(2) ?? '—'}. The phase describes structure; it is not a forecast.</p></article>
        <article><span>02 / What supports it?</span><h4>{example.conditions_met} / {example.conditions_total} checks</h4><p>{formatPercent(example.signal_confidence)} of entry conditions are met. The current signal is {String(example.signal || 'WAIT').replaceAll('_',' ').toLowerCase()}; the share counts checks, not outcomes.</p></article>
        <article><span>03 / What needs checking?</span><h4>{example.confluence ? `${Math.round(example.confluence.score)} / 100 agreement` : 'Inspect the counter-evidence'}</h4><p>{example.confluence ? ({waiting:'Both timeframes are waiting. ', agree:'The 4H and daily signals agree. ', differ:'The 4H and daily signals differ. '})[signalAgreement(example.confluence)] : ''}{example.signal_warnings?.length ? `${example.signal_warnings.length} engine warning${example.signal_warnings.length===1?' accompanies':'s accompany'} this snapshot: ${friendlyReason(example.signal_warnings[0]?.message ?? example.signal_warnings[0]).replace(/[^.!?]$/, '$&.')}` : 'Review positioning and entry conditions before interpreting the signal.'}</p></article>
      </div><a href={`/scanner/${exampleCoin}`}>Inspect the full {exampleCoin} setup ↗</a><p className="r-reading-footnote">Uses the same received daily snapshot as the table above.</p>
    </section>}
    </div>;
}
