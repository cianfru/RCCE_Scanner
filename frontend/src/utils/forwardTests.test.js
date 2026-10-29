import test from 'node:test';
import assert from 'node:assert/strict';
import { FWCOPY } from './forwardTests.js';
import { popWords } from './marketHistory.js';

test('forward status: days while collecting, numbers from interim, the verdict at the end', () => {
  assert.equal(FWCOPY.status({ status: 'collecting', days: 12, needed: 365 }), '12 of 365 days');
  assert.equal(FWCOPY.status({ status: 'interim', days: 200, needed: 365, partial: -0.123 }), '200 of 365 days · -0.12');
  assert.equal(FWCOPY.status({ status: 'verdict', days: 400, needed: 365, partial: 0.21, verdict: 'met' }), 'bar met · +0.21');
  assert.equal(FWCOPY.status(null), '—');
});

test('forward copy stays short and free of forecast words', () => {
  const pop = FWCOPY.pop().join(' ');
  assert.ok(popWords(pop) <= 90, `${popWords(pop)} words`);
  assert.doesNotMatch(pop, /\b(will|expect\w*|likely|predict\w*|probab\w*|odds|target\w*)\b/i);
});
