export const strategyLabel = value => ({ continuation_pullback: 'Trend pullback', confirmed_reversal: 'Confirmed-base reversal', trend_comparator: 'Simple trend comparator' })[value] || value;
export const researchPercent = value => value == null || !Number.isFinite(value) ? 'Unknown' : `${(value * 100).toFixed(2)}%`;
export const researchNumber = value => value == null || !Number.isFinite(value) ? 'Unknown' : value.toLocaleString(undefined, { maximumSignificantDigits: 7 });
export const researchTime = value => value ? new Date(value * 1000).toLocaleString() : 'Not yet';
export function evidenceLabel(summary) {
  if (!summary?.closed_trades) return 'No closed paper trades yet';
  return `${summary.fully_costed_trades}/${summary.closed_trades} closed trades have complete funding costs`;
}
