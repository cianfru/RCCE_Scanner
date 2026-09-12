import test from 'node:test';
import assert from 'node:assert/strict';
import { placeTooltip } from './tooltipPosition.js';

const viewport = { width: 1280, height: 800 };
const anchor = (left, top, size = 16) => ({ left, top, width: size, height: size, right: left + size, bottom: top + size });

test('centres the card on the anchor and opens below when there is room', () => {
  const p = placeTooltip({ anchor: anchor(600, 100), width: 400, height: 200, viewport });
  assert.deepEqual(p, { left: 408, top: 126, width: 400, placement: 'below' });
});

test('clamps to the left viewport edge instead of clipping (drawer-edge bug)', () => {
  const p = placeTooltip({ anchor: anchor(4, 300), width: 220, height: 120, viewport });
  assert.equal(p.left, 16);
  assert.equal(p.width, 220);
});

test('clamps to the right viewport edge', () => {
  const p = placeTooltip({ anchor: anchor(1270, 300), width: 280, height: 120, viewport });
  assert.equal(p.left, 1280 - 280 - 16);
});

test('flips above the anchor when the card would overflow the bottom', () => {
  const p = placeTooltip({ anchor: anchor(600, 700), width: 400, height: 200, viewport });
  assert.equal(p.placement, 'above');
  assert.equal(p.top, 700 - 200 - 10);
});

test('never places the card above the top margin, even when it fits nowhere', () => {
  const p = placeTooltip({ anchor: anchor(600, 30), width: 400, height: 900, viewport });
  assert.equal(p.top, 16);
});

test('shrinks the card to the viewport on narrow screens', () => {
  const p = placeTooltip({ anchor: anchor(10, 100), width: 400, height: 200, viewport: { width: 360, height: 640 } });
  assert.equal(p.width, 360 - 32);
  assert.equal(p.left, 16);
});

test('honours custom margin and gap', () => {
  const p = placeTooltip({ anchor: anchor(0, 0), width: 100, height: 50, viewport, margin: 4, gap: 2 });
  assert.equal(p.left, 4);
  assert.equal(p.top, 16 + 2);
});
