import test from 'node:test';
import assert from 'node:assert/strict';
import { SEEN_KEY, markHistorySeen, showHistoryDot, sparkGeometry } from './marketSpark.js';

const days = Array.from({ length: 90 }, (_, i) => [1000 + i, 0.3 + (i % 10) / 50]);
const stub = { k: [0, 5, 10, 15, 20, 25, 30], lo: [0.48, 0.4, 0.3, 0.2, 0.2, 0.15, 0.1], hi: [0.48, 0.7, 0.9, 1, 1, 1, 0.99] };
const spark = { days, today: 1089, stub };

const pts = d => d.replace(/[MZ]/g, '').split('L').map(p => p.split(',').map(Number));

test('the line spans the history part and ends at today', () => {
  const g = sparkGeometry(spark);
  const p = pts(g.line);
  assert.equal(p.length, 90);
  assert.equal(p[0][0], 1.5);
  assert.deepEqual(g.end, p[p.length - 1]);
  // 89 of 119 days: the stub takes about a quarter of the width.
  const frac = (g.w - 1.5 - g.end[0]) / (g.w - 3);
  assert.ok(frac > 0.22 && frac < 0.28, String(frac));
  assert.ok(p.every(([x, y]) => x >= 1.5 && x <= g.w - 1.5 && y >= 1.5 && y <= g.h - 1.5));
});

test('the stub is a closed envelope from today, hi forward then lo back, no middle line', () => {
  const g = sparkGeometry(spark);
  assert.ok(g.stub.startsWith('M') && g.stub.endsWith('Z'));
  const p = pts(g.stub);
  assert.equal(p.length, 14);
  assert.equal(p[0][0], g.end[0]);                  // anchored at today's x
  assert.equal(p[p.length - 1][0], g.end[0]);
  assert.equal(p[6][0], g.w - 1.5);                 // +30 at the right edge
  for (let i = 0; i < 7; i++) assert.ok(p[i][1] <= p[13 - i][1]);   // hi above lo (smaller y)
  assert.equal(Object.keys(g).includes('median'), false);
});

test('no stub: the history fills the width; bad stubs are dropped', () => {
  for (const s of [null, { k: [0], lo: [0.5], hi: [0.5] }, { ...stub, lo: stub.hi, hi: stub.lo }, { ...stub, lo: [0.1] }, { ...stub, k: [5, 10, 15, 20, 25, 30, 35] }]) {
    const g = sparkGeometry({ ...spark, stub: s });
    assert.equal(g.stub, null);
    assert.equal(g.end[0], g.w - 1.5);
  }
});

test('nothing to draw gives null (the plain icon stays)', () => {
  assert.equal(sparkGeometry(null), null);
  assert.equal(sparkGeometry({ days: [[1, 0.5]] }), null);
  assert.equal(sparkGeometry({ days: 'x' }), null);
});

test('fixed 0-100% scale, values clipped', () => {
  const g = sparkGeometry({ days: [[1, 0], [2, 1], [3, 1.4]], today: 3, stub: null }, { w: 20, h: 12, pad: 1 });
  assert.deepEqual(pts(g.line).map(p => p[1]), [11, 1, 1]);
});

function mem() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k), m };
}

test('dot until the drawer is opened once, then never again', () => {
  const s = mem();
  assert.equal(showHistoryDot(s), true);
  assert.equal(s.m.size, 0);                        // the write probe leaves nothing behind
  assert.equal(markHistorySeen(s), true);
  assert.equal(s.getItem(SEEN_KEY), '1');
  assert.equal(showHistoryDot(s), false);
});

test('no usable storage: no dot, and nothing throws', () => {
  const throws = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() {} };
  const readOnly = { getItem: () => null, setItem() { throw new Error('quota'); }, removeItem() {} };
  assert.equal(showHistoryDot(null), false);
  assert.equal(showHistoryDot(throws), false);
  assert.equal(showHistoryDot(readOnly), false);
  assert.equal(markHistorySeen(throws), false);
  assert.equal(markHistorySeen(null), false);
});
