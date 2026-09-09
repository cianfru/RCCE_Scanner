import { formatPercent } from "../utils/marketPresentation.js";
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DataTable from '../components/DataTable.jsx';
import { Mark } from './Mark';
import { SCANNER_COLUMNS } from '../scannerColumns.js';
import '../terminal.css';

const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const COINS = new Set(['BTC', 'ETH', 'SOL', 'HYPE', 'LINK']);

export default function LiveScannerPreview() {
  const tf = '1d';
  const [exampleCoin, setExampleCoin] = useState('BTC');
  const [state, setState] = useState({ rows: [], loading: true, error: '', updated: null });
  const [sort, setSort] = useState('priority_score');
  const navigate = useNavigate();
  useEffect(() => {
    let disposed = false, timer;
    const controller = new AbortController();
    setState({ rows: [], loading: true, error: '', updated: null });
    async function refresh() {
      const request = new AbortController();
      const abort = () => request.abort();
      controller.signal.addEventListener('abort', abort, { once: true });
      const timeout = setTimeout(abort, 12000);
      try {
        const response = await fetch(`${API_BASE}/api/scan?timeframe=${tf}`, { signal: request.signal });
        if (!response.ok) throw new Error('Scanner unavailable');
        const data = await response.json();
        if (!Array.isArray(data.results)) throw new Error('Invalid scan response');
        const rows = data.results.filter(row => COINS.has((row.symbol || '').split('/')[0]) && /\/(USDT|USD)$/.test(row.symbol));
        // One current quote per asset, preferring USDT when both pairs exist.
        const unique = new Map();
        rows.sort((a,b) => Number(b.symbol.endsWith('/USDT')) - Number(a.symbol.endsWith('/USDT'))).forEach(row => {
          const base = row.symbol.split('/')[0]; if (!unique.has(base)) unique.set(base, row);
        });
        if (!disposed) setState({ rows: [...unique.values()], loading: false, error: '', updated: new Date() });
      } catch {
        if (!disposed) setState(previous => ({ ...previous, loading: false, error: 'The scanner feed is temporarily unavailable.' }));
      } finally {
        clearTimeout(timeout);
        controller.signal.removeEventListener('abort', abort);
        if (!disposed) timer = setTimeout(refresh, 60000);
      }
    }
    refresh();
    return () => { disposed = true; controller.abort(); clearTimeout(timer); };
  }, [tf]);
  const rows = [...state.rows].sort((a,b) => sort === 'symbol' ? a.symbol.localeCompare(b.symbol) : sort === 'regime' ? String(a.regime).localeCompare(String(b.regime)) : (b[sort] || 0) - (a[sort] || 0));
  const example = state.rows.find(row => row.symbol.split('/')[0] === exampleCoin);
  return <div className="r-terminal-wrap"><div className="r-terminal glass">
    <div className="r-terminal-bar"><span className="r-terminal-title"><Mark size={22}/> reflex <i/> scanner</span><span className="r-terminal-data">{state.error ? 'Feed unavailable' : state.loading ? 'Connecting to scanner' : 'Latest scanner snapshot'}</span></div>
    <div style={{ padding: '24px clamp(12px, 3vw, 32px)' }}>
      <div className="r-terminal-heading"><div><span className="r-meta">THE MAIN MARKETS</span><h3>Inside the terminal</h3></div><span className="r-meta">DAILY · 1D</span></div>
      <p className="r-scroll-hint">Scroll horizontally to explore all 16 columns. The symbol stays in view.</p>
      <div className="reflex-terminal" style={{ marginTop: 24 }}>
        {state.error && <p role="status" style={{ padding: '16px 0' }}>{state.error}{state.rows.length > 0 ? ' Showing the last received snapshot.' : ' Open the terminal to check the connection.'}</p>}
        {!state.loading && !state.error && !rows.length ? <p role="status">The next scan will populate these markets.</p> : (!state.error || rows.length > 0) && <DataTable results={rows} sortKey={sort} onSort={setSort} visibleColumns={SCANNER_COLUMNS} loading={state.loading} isMobile={false} onSelect={row => navigate(`/scanner/${row.symbol.split('/')[0]}`)} onToggleFavorite={() => navigate('/scanner')}/>}
      </div>
      <div className="r-terminal-bottom"><span>{state.updated ? `Received ${state.updated.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})} · refreshes every minute` : 'Signals from the same API as the terminal'}</span><a href="/scanner">Open full scanner ↗</a></div>
    </div></div>
    {example && <section className="r-reading-example" aria-label="Reading a real setup">
      <div className="r-reading-heading"><div><span className="r-meta">READ THE EVIDENCE</span><h3>One market. Three questions.</h3></div>
      <label>Market <select aria-label="Example market" value={exampleCoin} onChange={event=>setExampleCoin(event.target.value)}>{[...COINS].map(coin=><option key={coin}>{coin}</option>)}</select></label></div>
      <div className="r-reading-grid">
        <article><span>01 / What is the phase?</span><h4>{example.regime}</h4><p>{exampleCoin} is classified in this daily regime, with a Z-score of {example.zscore?.toFixed(2) ?? '—'}. The phase describes structure; it is not a forecast.</p></article>
        <article><span>02 / What supports it?</span><h4>{example.conditions_met} / {example.conditions_total} checks</h4><p>{formatPercent(example.signal_confidence)} of entry conditions are met. The current signal is {String(example.signal || 'WAIT').replaceAll('_',' ').toLowerCase()}; this percentage is not a probability of profit.</p></article>
        <article><span>03 / What needs checking?</span><h4>{example.confluence ? `${Math.round(example.confluence.score)} / 100 agreement` : 'Inspect the counter-evidence'}</h4><p>{example.confluence ? `The 4H and daily signals ${example.confluence.signal_aligned ? 'agree' : 'differ'}. ` : ''}{example.signal_warnings?.length ? `${example.signal_warnings.length} engine warning${example.signal_warnings.length===1?'':'s'} accompany this snapshot.` : 'Review positioning and entry conditions before interpreting the signal.'}</p></article>
      </div><a href={`/scanner/${exampleCoin}`}>Inspect the full {exampleCoin} setup ↗</a><p className="r-reading-footnote">Uses the same received daily snapshot as the table above.</p>
    </section>}
    </div>;
}
