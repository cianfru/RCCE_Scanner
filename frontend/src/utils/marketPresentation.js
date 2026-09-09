// API contracts: signal_confidence/confidence are 0–100; smart-money confidence is 0–1.
export function formatPercent(value, { ratio = false, digits = 0 } = {}) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return `${(Number(value) * (ratio ? 100 : 1)).toFixed(digits)}%`;
}
export function evidenceSummary(data) {
  const regime = ({MARKUP:'an upward market phase', ACCUM:'a base-building phase', REACC:'a pullback within an upward phase', MARKDOWN:'a downward market phase', BLOWOFF:'an extended upward phase', CAP:'a capitulation phase', FLAT:'a neutral market phase'})[data.regime] || String(data.regime || 'an unclassified phase').toLowerCase();
  return `The scanner identifies ${regime}. ${data.conditions_total > 0 ? `${data.conditions_met} of ${data.conditions_total} entry checks are satisfied.` : 'Entry checks are not available for this snapshot.'} ${data.confluence ? `The 4H and 1D regimes ${data.confluence.regime_aligned ? 'agree' : 'differ'}, while their signals ${data.confluence.signal_aligned ? 'agree' : 'differ'}.` : ''}`;
}

export function bestEntrySetups(results, limit = 3) {
 return [...results].filter(row => ['STRONG_LONG','LIGHT_LONG','ACCUMULATE'].includes(row.unified_signal || row.signal) && Number.isFinite(row.priority_score)).sort((a,b)=>b.priority_score-a.priority_score || a.symbol.localeCompare(b.symbol)).slice(0,limit);
}
