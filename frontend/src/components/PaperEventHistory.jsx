import { useEffect, useRef, useState } from 'react';
import { researchTime as stamp, researchNumber as number, researchPercent as pct } from '../utils/researchSetups.js';
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export default function PaperEventHistory({ id }) {
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(false);
  const pending = useRef(null);
  useEffect(() => () => pending.current?.abort(), []);
  const load = async () => {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller;
    try {
      const response = await fetch(`${API}/api/research/setups/${encodeURIComponent(id)}/events`, { signal: controller.signal });
      if (!response.ok) throw new Error('Unavailable');
      setEvents((await response.json()).events); setError(false);
    } catch { if (!controller.signal.aborted) setError(true); }
    finally { pending.current = null; }
  };
  return <details onToggle={event => { if (event.currentTarget.open) load(); }}>
    <summary>Observation and fill history</summary>
    {error ? <p>History unavailable. Reopen to retry.</p> : events == null ? <p>Loading history…</p> : <ol>{events.map(e => <li key={e.id}>
      {stamp(e.observed_at)} · {e.event.replaceAll('_', ' ')} — {e.state.reason}
      {e.state.entry != null && <span> · Paper entry {number(e.state.entry)}</span>}
      {e.state.exit != null && <span> · Paper exit {number(e.state.exit)} · Modeled net {pct(e.state.net_return)}</span>}
    </li>)}</ol>}
  </details>;
}
