import { ENTRY_SIGNALS } from "./opportunities.js";
// API contracts: signal_confidence/confidence are 0–100; smart-money confidence is 0–1.
export function formatPercent(value, { ratio = false, digits = 0 } = {}) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return `${(Number(value) * (ratio ? 100 : 1)).toFixed(digits)}%`;
}
export function evidenceSummary(data) {
  const regime = ({MARKUP:'an upward market phase', ACCUM:'a base-building phase', REACC:'a pullback within an upward phase', MARKDOWN:'a downward market phase', BLOWOFF:'an extended upward phase', CAP:'a capitulation phase', FLAT:'a neutral market phase'})[data.regime] || String(data.regime || 'an unclassified phase').toLowerCase();
  return `The scanner identifies ${regime}. ${data.conditions_total > 0 ? `${data.conditions_met} of ${data.conditions_total} entry checks are satisfied.` : 'Entry checks are not available for this snapshot.'} ${data.confluence ? `The 4H and 1D regimes ${data.confluence.regime_aligned ? 'agree' : 'differ'}, while their signals ${data.confluence.signal_aligned ? 'agree' : 'differ'}.` : ''}`;
}

// Highest-priority setups, at most one per sector, so the shortlist is three
// different bets rather than three versions of the same market move.
export function bestEntrySetups(results, limit = 3) {
 const ranked = [...results].filter(row => (ENTRY_SIGNALS.has(row.signal) || row.signal === 'LIGHT_SHORT') && row.signal_status !== 'unavailable' && (!row.opportunity || row.opportunity.status === 'confirmed') && Number.isFinite(row.priority_score)).sort((a,b)=>b.priority_score-a.priority_score || a.symbol.localeCompare(b.symbol));
 const picked = [], sectors = new Set();
 for (const row of ranked) {
  const sector = row.sector && row.sector !== 'Other' ? row.sector : null;
  if (sector && sectors.has(sector)) continue;
  picked.push(row);
  if (sector) sectors.add(sector);
  if (picked.length === limit) break;
 }
 return picked;
}
