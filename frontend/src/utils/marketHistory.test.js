import test from 'node:test';
import assert from 'node:assert/strict';
import { rowsOf, inRange, percentileOf, episodesOf, bandSummary, logTicks, dayDate, signedPct } from './marketHistory.js';

const data = {
  columns: ['day', 'n', 'uptrend'], days: [[100, 50, 0.2], [300, 50, 0.5], [500, 50, 0.8]],
  episode_columns: ['start', 'end', 'breadth', 'btc10', 'alt10', 'btc30', 'alt30', 'btc60', 'alt60'],
};

test('rows and ranges', () => {
  const rows = rowsOf(data);
  assert.deepEqual(rows[2], { day: 500, n: 50, uptrend: 0.8 });
  assert.equal(inRange(rows, '1y').length, 2);
  assert.equal(inRange(rows, 'all').length, 3);
});

test('percentile counts days strictly below', () => {
  assert.equal(percentileOf([1, 2, 3, 4], 3), 50);
  assert.equal(percentileOf([], 3), null);
});

test('episodes: newest first, later ones unscored', () => {
  const band = { episodes: [[10, 12, 0.7, 1, 2, 3, 4, 5, 6]], later: [[40, 41, 0.72]] };
  const eps = episodesOf(data, band);
  assert.deepEqual(eps.map(e => [e.start, e.scored]), [[40, false], [10, true]]);
  assert.equal(eps[1].alt30, 4);
});

test('band summary states counts, never a direction word', () => {
  const mixed = { verdict: { episodes: 18, alt: { above_base: 9, direction: 'mixed' }, btc: { above_base: 10, direction: 'mixed' } } };
  assert.match(bandSummary(mixed), /18 past episodes.*in 9 and BTC in 10.*mixed/);
  const strong = { verdict: { episodes: 9, alt: { above_base: 7, direction: 'continuation' }, btc: { above_base: 5, direction: 'mixed' } } };
  assert.doesNotMatch(bandSummary(strong), /continuation|pullback/);
  assert.match(bandSummary(strong), /not a forecast/);
  assert.match(bandSummary({ verdict: { direction: 'too few episodes', episodes: 3 } }), /too few/);
});

test('formatting', () => {
  assert.deepEqual(logTicks(15000, 110000), [20000, 50000, 100000]);
  assert.equal(dayDate(20721), '25 Sep 2026');
  assert.equal(signedPct(-7.4), '−7.4%');
});
