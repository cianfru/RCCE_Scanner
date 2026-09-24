import PaperEventHistory from "./PaperEventHistory.jsx";
import { useEffect, useState } from 'react';
import { T } from '../theme.js';
import { strategyLabel, evidenceLabel, researchPercent as pct, researchNumber as number, researchTime as stamp } from '../utils/researchSetups.js';
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export default function SetupResearchDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch(`${API}/api/research/setups`, { signal: controller.signal });
        if (!response.ok) throw new Error('Unavailable');
        setData(await response.json()); setError(false);
      } catch { if (!controller.signal.aborted) setError(true); }
    };
    refresh(); const timer = setInterval(refresh, 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  return <section style={{ color: T.text2, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16, margin: '12px 0' }}>
    <h2>Setup research · forward paper record</h2>
    <p>BTC, ETH and SOL · 4h with daily context · long only · unvalidated</p>
    {error || data?.error ? <p role="status">Research updates unavailable. Previously recorded results may be stale.</p> : null}
    {!data?.available ? <p>No forward observations available yet. Collection starts when the updated backend runs.</p> : <>
      <p>Last collection: {stamp(data.updated_at)}. Paper results are hypothetical; no orders are placed.</p>
      <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', textAlign: 'left', borderSpacing: 10 }}>
        <thead><tr><th>Strategy</th><th>Closed / fully costed</th><th>Modeled net expectancy</th><th>Mean R</th><th>Losing fraction</th><th>Realized drawdown R</th></tr></thead>
        <tbody>{Object.entries(data.strategies || {}).map(([key, value]) => <tr key={key}>
          <td>{strategyLabel(key.split(':')[1])}<small style={{ display: 'block' }}>{key.split(':')[0]}</small></td>
          <td>{value.summary.closed_trades} / {value.summary.fully_costed_trades}</td>
          <td>{pct(value.summary.expectancy)}</td><td>{number(value.summary.expectancy_r)}</td>
          <td>{pct(value.summary.losing_fraction)}</td><td>{number(value.summary.realized_drawdown_r)}</td>
        </tr>)}</tbody>
      </table></div>
      <p>Net statistics exclude missing funding. Drawdown uses a fixed one-unit-risk sequence per strategy, not portfolio equity. Same-bar stop/target conflicts assume the stop was hit first.</p>
      {Object.entries(data.strategies || {}).map(([key, value]) => <details key={key}>
        <summary>{strategyLabel(key.split(':')[1])} · {evidenceLabel(value.summary)}</summary>
        <p>Lifecycle: {Object.entries(value.summary.states).map(([name, n]) => `${name}: ${n}`).join(' · ')}</p>
        <p>Mean favorable / adverse excursion: {pct(value.summary.mean_mfe)} / {pct(value.summary.mean_mae)} · Ambiguous trades: {value.summary.ambiguous_trades}</p>
        <ul>{Object.entries(value.assets).map(([symbol, stats]) => <li key={symbol}>{symbol}: {stats.fully_costed_trades} fully costed · expectancy {pct(stats.expectancy)}</li>)}</ul>
        <ul>{Object.entries(value.regimes).map(([regime, stats]) => <li key={regime}>{regime}: {stats.fully_costed_trades} fully costed · expectancy {pct(stats.expectancy)}</li>)}</ul>
      </details>)}
      <details><summary>Recent immutable setup observations</summary>
        <ul>{(data.records || []).map(({ contract: c, state: s }) => <li key={c.id}>{c.symbol} · {strategyLabel(c.strategy)} · {stamp(c.observed_at)} · {s.status} — {s.reason}<PaperEventHistory id={c.id} /></li>)}</ul>
      </details>
    </>}
  </section>;
}
