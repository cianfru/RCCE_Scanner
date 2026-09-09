import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DataTable from '../components/DataTable.jsx';
import { Mark } from './Mark';
import { Tabs, TabsList, TabsTrigger } from './tabs';
import '../terminal.css';

const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const COINS = new Set(['BTC', 'ETH', 'SOL', 'HYPE', 'LINK']);
const COLUMNS = [[null, '#'], ['priority_score', 'PRI'], ['symbol', 'SYMBOL'], ['regime', 'REGIME'], [null, 'SIGNAL'], ['zscore', 'Z-SCORE']];

export default function LiveScannerPreview() {
  const [tf, setTf] = useState('1d');
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
  return <div className="r-terminal-wrap"><div className="r-terminal glass">
    <div className="r-terminal-bar"><span className="r-terminal-title"><Mark size={22}/> reflex <i/> scanner</span><span className="r-terminal-data">{state.error ? 'Feed unavailable' : state.loading ? 'Connecting to scanner' : 'Latest scanner snapshot'}</span></div>
    <div style={{ padding: '24px clamp(12px, 3vw, 32px)' }}>
      <div className="r-terminal-heading"><div><span className="r-meta">THE MAIN MARKETS</span><h3>Inside the terminal</h3></div><Tabs value={tf} onValueChange={setTf}><TabsList className="r-time-tabs" aria-label="Live preview timeframe"><TabsTrigger value="4h">4H</TabsTrigger><TabsTrigger value="1d">1D</TabsTrigger></TabsList></Tabs></div>
      <div className="reflex-terminal" style={{ marginTop: 24 }}>
        {state.error && <p role="status" style={{ padding: '16px 0' }}>{state.error}{state.rows.length > 0 ? ' Showing the last received snapshot.' : ' Open the terminal to check the connection.'}</p>}
        {!state.loading && !state.error && !rows.length ? <p role="status">The next scan will populate these markets.</p> : (!state.error || rows.length > 0) && <DataTable results={rows} sortKey={sort} onSort={setSort} visibleColumns={COLUMNS} loading={state.loading} isMobile={false} onSelect={row => navigate(`/scanner/${row.symbol.split('/')[0]}`)} onToggleFavorite={() => navigate('/scanner')}/>}
      </div>
      <div className="r-terminal-bottom"><span>{state.updated ? `Received ${state.updated.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})} · refreshes every minute` : 'Signals from the same API as the terminal'}</span><a href="/scanner">Open full scanner ↗</a></div>
    </div></div></div>;
}
