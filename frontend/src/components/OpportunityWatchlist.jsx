import { T } from "../theme.js";
export default function OpportunityWatchlist({ rows, onSelect }) {
  const candidates = rows.filter(r => r.opportunity && ['emerging', 'blocked', 'invalidated', 'expired', 'unavailable'].includes(r.opportunity.status))
    .sort((a,b) => (b.priority_score || 0) - (a.priority_score || 0)).slice(0, 10);
  if (!candidates.length) return null;
  return <details style={{ padding: 10, marginBottom: 8, color: T.text2, border: `1px solid ${T.border}`, borderRadius: 8 }}>
    <summary>Setups awaiting confirmation or reassessment</summary>
    <ul>{candidates.map(row => <li key={`${row.symbol}:${row.timeframe}`}>
      <button onClick={() => onSelect(row)} style={{ color: T.accent, background: 'none', border: 0, cursor: 'pointer' }}>{row.symbol} · {row.timeframe}</button>
      {row.opportunity.status}: {row.opportunity.reason}
    </li>)}</ul>
  </details>;
}
