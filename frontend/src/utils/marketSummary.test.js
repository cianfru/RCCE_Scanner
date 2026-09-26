import test from 'node:test';
import assert from 'node:assert/strict';
import { SIGNAL_KEYS, matchesSignal, signalCounts, regimeMix, fgBand, fgNote, dialRotation, sharePct } from './marketSummary.js';

const rows = (spec, field) => Object.entries(spec).flatMap(([k, n]) => Array.from({ length: n }, () => ({ [field]: k })));

test('signal counts sum to n and match the grid filter', () => {
  const rs = rows({ STRONG_LONG: 3, LIGHT_LONG: 5, WAIT: 4, TRIM: 1, TRIM_HARD: 2, REVIVAL_SEED: 1 }, 'signal');
  const { n, counts, other } = signalCounts(rs);
  assert.equal(n, 16);
  assert.equal(counts.TRIM, 3);
  assert.equal(other, 1);
  assert.equal(SIGNAL_KEYS.reduce((a, k) => a + counts[k], 0) + other, n);
  for (const k of SIGNAL_KEYS) assert.equal(rs.filter(r => matchesSignal(r, k)).length, counts[k]);
});

test('regime mix puts the deciding bucket first', () => {
  const rs = rows({ MARKUP: 137, REACC: 22, ACCUM: 14, FLAT: 5 }, 'regime');
  const m = regimeMix(rs, 'RISK-ON');
  assert.deepEqual([m.n, m.p, m.N], [137, 77, 178]);
  assert.deepEqual(m.anchor, ['MARKUP']);
  assert.deepEqual(m.order, ['MARKUP', 'REACC', 'ACCUM', 'FLAT']);
  assert.deepEqual(regimeMix(rs, 'ACCUMULATION').anchor, ['REACC', 'ACCUM', 'CAP']);
  const mixed = regimeMix(rows({ MARKUP: 40, MARKDOWN: 50, ACCUM: 10 }, 'regime'), 'MIXED');
  assert.equal(mixed.bucket, 'RISK-OFF');
  assert.equal(mixed.order[0], 'MARKDOWN');
});

test('Fear & Greed bands match the backend labels', () => {
  const edges = [[20, 0], [21, 1], [40, 1], [41, 2], [60, 2], [61, 3], [80, 3], [81, 4], [0, 0], [100, 4]];
  for (const [v, b] of edges) assert.equal(fgBand(v), b, `v=${v}`);
  assert.equal(fgBand(null), null);
});

test('Fear & Greed notes follow the engine thresholds', () => {
  assert.match(fgNote(40, true), /fear gate is open/);
  assert.match(fgNote(41, true), /Not\u00a0greedy passes/);
  assert.match(fgNote(69, true), /Not\u00a0greedy passes/);
  assert.match(fgNote(70, true), /fails on every market/);
  assert.match(fgNote(null, true), /No reading/);
  assert.match(fgNote(null, false), /Waiting/);
});

test('dial rotation', () => {
  assert.deepEqual([0, 50, 74, 100, -5, 120].map(dialRotation), [-90, 0, 43.2, 90, -90, 90]);
});

test('share near the 55% line keeps a decimal and rounds away from it', () => {
  assert.equal(sharePct(77, 100), 77);
  assert.equal(sharePct(5455, 10000), '54.5');
  assert.equal(sharePct(5501, 10000), '55.1');
  assert.equal(sharePct(5499, 10000), '54.9');
});
