import test from 'node:test';
import assert from 'node:assert/strict';
import { FCOPY, fundingByDay } from './funding.js';

const feed = rows => ({ columns: ['day', 'btc', 'eth'], rows });

test('funding: the two coins averaged, a 7-day mean once 5 of 7 days are there', () => {
  const m = fundingByDay(feed([[1, 10, 20], [2, 10, 20], [3, 10, 20], [4, 10, 20], [5, 30, 40], [6, null, 5]]));
  assert.equal(m.get(1).avg, 15);
  assert.equal(m.get(4).avg7, null, 'four days are too few');
  assert.equal(m.get(5).avg7, (15 * 4 + 35) / 5);
  assert.ok(!m.has(6), 'a day missing one coin is left out');
  assert.equal(fundingByDay(null).size, 0);
});

test('funding legend reads in yearly percent, no forecast words', () => {
  const t = FCOPY.legend({ avg7: 9.4, btc: 10.9, eth: 7.8 });
  assert.equal(t, '9% a year · BTC 11% · ETH 8%');
  assert.doesNotMatch(FCOPY.label + t, /\b(will|expect\w*|likely|predict\w*|probab\w*|odds|target\w*)\b/i);
});
