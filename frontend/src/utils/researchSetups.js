export const strategyLabel = value => ({ continuation_pullback: 'Trend pullback · original', confirmed_reversal: 'Confirmed-base reversal · original', trend_comparator: 'Simple trend comparator', adaptive_breakout: 'Confirmed breakout', adaptive_trend: 'Confirmed trend', adaptive_recovery: 'Recovery setup', adaptive_pullback: 'Confirmed pullback' })[value] || value;
export const entryRuleLabel = contract => contract.entry_mode === 'next_open' ? 'Confirmed close / next opening' : 'Trigger: completed 4h close above';
export const exitRuleLabel = contract => ({ none: 'Frozen stop and target; no automatic break-even', be_5pct: 'Cost-aware protection after a confirmed 5% gain', legacy_be_5pct: 'Entry-price protection after a confirmed 5% gain', be_2r: 'Cost-aware protection after a confirmed 2R gain', trail_2r: 'Trail after a confirmed 2R gain' })[contract.parameters?.protection || 'none'];
export const researchPercent = value => value == null || !Number.isFinite(value) ? 'Unknown' : `${(value * 100).toFixed(2)}%`;
export const researchNumber = value => value == null || !Number.isFinite(value) ? 'Unknown' : value.toLocaleString(undefined, { maximumSignificantDigits: 7 });
export const researchTime = value => value ? new Date(value * 1000).toLocaleString() : 'Not yet';
export function evidenceLabel(summary) {
  if (!summary?.closed_trades) return 'No closed paper trades yet';
  return `${summary.fully_costed_trades}/${summary.closed_trades} closed trades have complete funding costs`;
}
