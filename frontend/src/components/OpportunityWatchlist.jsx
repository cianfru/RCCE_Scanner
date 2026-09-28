import { OppList, OppRow } from "./OpportunityActivity.jsx";

const WAITING = ["emerging", "blocked", "invalidated", "expired", "unavailable"];

export default function OpportunityWatchlist({ rows, onSelect }) {
  const candidates = rows.filter(r => r.opportunity && WAITING.includes(r.opportunity.status))
    .sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0)).slice(0, 10);
  return <OppList title="Awaiting confirmation or reassessment" items={candidates} render={row =>
    <OppRow key={`${row.symbol}:${row.timeframe}`} symbol={row.symbol} timeframe={row.timeframe} status={row.opportunity.status}
      reason={row.opportunity.reason} ts={row.opportunity.trigger_at} onClick={() => onSelect(row)} />} />;
}
