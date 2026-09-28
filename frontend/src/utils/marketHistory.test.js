import test from 'node:test';
import assert from 'node:assert/strict';
import { rowsOf, inRange, percentileOf, episodesOf, bandSummary, cycleLine, logTicks, dayDate, signedPct } from './marketHistory.js';

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

test('episodes: newest first, scored once 30 or 60 days have closed', () => {
  const band = { episodes: [[10, 12, 0.7, 1, 2, 3, 4, 5, 6]],
    later: [[40, 41, 0.72, 1, 2, 3, 4, null, null], [70, 71, 0.8, 1, 2, null, null, null, null]] };
  const eps = episodesOf({ ...data, today: { day: 100 }, scored_through: 100 }, band);
  assert.deepEqual(eps.map(e => [e.start, e.due30, e.due60]), [[70, null, 130], [40, null, null], [10, null, null]]);
  assert.equal(eps[2].alt30, 4);
  assert.equal(eps[1].alt30, 4);
  assert.equal(eps[1].alt60, null);                    // closed on day 100 but no data: shown as a dash
  const pending = episodesOf({ ...data, today: { day: 95 } }, band);
  assert.deepEqual(pending.map(e => [e.start, e.due30, e.due60]), [[70, 100, 130], [40, null, 100], [10, null, null]]);
  // An older payload (later rows without outcomes) still reads.
  const old = episodesOf({ ...data, today: { day: 100 } }, { episodes: [], later: [[90, 91, 0.6]] });
  assert.deepEqual([old[0].due30, old[0].alt30], [120, null]);
});

test('risk-on line: counts from the study, no forecast words', () => {
  const c = { type: 'on', start: 20685, day: 39, threshold: 0.55, off_days: 5, below_days: 0, past: 12, median: 47,
    reached: 7, more: 30, lasted_more: 5 };
  assert.equal(cycleLine(c), 'This risk-on run: day 39 (since 20 Aug 2026). Past runs (12): half lasted longer than 47 days; ' +
    'of those that reached day 39, 5 of 7 lasted another 30 days.');
  assert.match(cycleLine({ ...c, below_days: 2 }), /since 20 Aug 2026; under 55% for 2 days, 5 in a row end it\)/);
  assert.match(cycleLine({ ...c, reached: 3, lasted_more: 1 }), /1 of 3 lasted another 30 days \(too few to read\)\.$/);
  assert.match(cycleLine({ ...c, day: 160, reached: 0, lasted_more: 0 }), /none reached day 160\.$/);
  assert.match(cycleLine({ ...c, type: 'off', median: 67, past: 13 }), /^This risk-off stretch: day 39 .* Past stretches \(13\)/);
  assert.match(cycleLine({ ...c, median: 47.5 }), /longer than 47\.5 days/);
  assert.doesNotMatch(cycleLine(c), /will|likely|probab|expect/i);
  assert.equal(cycleLine(null), null);
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
