import test from 'node:test';
import assert from 'node:assert/strict';
import { fitColumns, neededWidth, RANKED, DROP_ORDER } from './gridFit.js';
import { SCANNER_COLUMNS } from '../scannerColumns.js';

const ALL = SCANNER_COLUMNS.map(([, label]) => label);
// 1D perps today: DIV and OI are empty on every row, so they are not candidates.
const D1 = ALL.filter(label => label !== 'DIV' && label !== 'OI');
// 4H: OI has readings.
const H4 = ALL.filter(label => label !== 'DIV');

test('drop order: cheap OI then #, then rank 3 (ENERGY) to 12 (Z-SCORE)', () => {
  assert.deepEqual(RANKED, ['ENERGY', 'CONF', 'EXHAUST', 'DIV', 'CVD', 'SM', 'HEAT', 'COND', 'SPARK', 'Z-SCORE']);
  assert.deepEqual(DROP_ORDER.slice(0, 2), ['OI', '#']);
});

test('needed widths match the spec table (1D set, 8px margin)', () => {
  assert.equal(neededWidth(D1, 12), 1366);
  assert.equal(neededWidth(D1, 10), 1314);
  assert.equal(neededWidth(D1.filter(l => l !== '#'), 8), 1225);
});

test('1D: wide windows keep every column at 12px', () => {
  for (const W of [1870, 1550, 1390]) {
    const fit = fitColumns(D1, W);
    assert.equal(fit.pad, 12, `W ${W}`);
    assert.deepEqual(fit.visible, D1, `W ${W}`);
    assert.deepEqual(fit.hidden, [], `W ${W}`);
    assert.equal(fit.phone, false);
  }
});

test('1D 1366: every column at 10px', () => {
  const fit = fitColumns(D1, 1316);
  assert.equal(fit.pad, 10);
  assert.deepEqual(fit.hidden, []);
});

test('1D 1280: only # leaves, at 8px', () => {
  const fit = fitColumns(D1, 1230);
  assert.equal(fit.pad, 8);
  assert.deepEqual(fit.hidden, ['#']);
  assert.ok(fit.visible.includes('ENERGY'));
});

test('1D 1024: ENERGY, CONF, EXHAUST and CVD leave; the core stays', () => {
  const fit = fitColumns(D1, 974);
  assert.equal(fit.pad, 8);
  for (const label of ['ENERGY', 'CONF', 'EXHAUST', 'CVD']) assert.ok(fit.hidden.includes(label), label);
  assert.deepEqual(fit.visible, ['PRI', 'SYMBOL', 'REGIME', 'SIGNAL', 'Z-SCORE', 'SPARK', 'COND', 'HEAT', 'SM']);
});

test('4H with OI: 1440 hides only OI at 12px', () => {
  const fit = fitColumns(H4, 1390);
  assert.equal(fit.pad, 12);
  assert.deepEqual(fit.hidden, ['OI']);
});

test('4H with OI: 1600 keeps everything', () => {
  const fit = fitColumns(H4, 1550);
  assert.equal(fit.pad, 12);
  assert.deepEqual(fit.hidden, []);
});

test('4H with OI: 1366 hides only OI at 10px', () => {
  const fit = fitColumns(H4, 1316);
  assert.equal(fit.pad, 10);
  assert.deepEqual(fit.hidden, ['OI']);
});

test('phone: rank, symbol and the pair at 8px', () => {
  const fit = fitColumns(D1, 356);
  assert.equal(fit.phone, true);
  assert.equal(fit.pad, 8);
  assert.deepEqual(fit.visible, ['PRI', 'SYMBOL', 'REGIME', 'SIGNAL']);
  assert.ok(fit.hidden.includes('#') && fit.hidden.includes('Z-SCORE'));
});

test('the never-dropped core survives any width', () => {
  const fit = fitColumns(D1, 700);
  assert.deepEqual(fit.visible, ['PRI', 'SYMBOL', 'REGIME', 'SIGNAL', 'Z-SCORE']);
  assert.deepEqual(fitColumns(D1, 641).visible, ['PRI', 'SYMBOL', 'REGIME', 'SIGNAL']);
});

test('safety net: extra drops remove the next column in drop order', () => {
  assert.deepEqual(fitColumns(D1, 1390, { extraDrops: 1 }).hidden, ['#']);
  assert.deepEqual(fitColumns(D1, 1390, { extraDrops: 2 }).hidden, ['#', 'ENERGY']);
  assert.deepEqual(fitColumns(H4, 1550, { extraDrops: 1 }).hidden, ['OI']);
  assert.deepEqual(fitColumns(D1, 1230, { extraDrops: 1 }).hidden, ['#', 'ENERGY']);
});
