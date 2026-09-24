import test from 'node:test';
import assert from 'node:assert/strict';
import { researchPercent, researchNumber, evidenceLabel, strategyLabel } from './researchSetups.js';
test('unknown costs and results are not displayed as zero or a win rate', () => {
  assert.equal(researchPercent(null), 'Unknown');
  assert.equal(researchPercent(0), '0.00%');
  assert.equal(researchNumber(NaN), 'Unknown');
  assert.equal(evidenceLabel({closed_trades:5, fully_costed_trades:2}), '2/5 closed trades have complete funding costs');
});
test('comparator and empty evidence remain explicitly labeled', () => {
  assert.equal(strategyLabel('trend_comparator'), 'Simple trend comparator');
  assert.equal(evidenceLabel({closed_trades:0}), 'No closed paper trades yet');
});
