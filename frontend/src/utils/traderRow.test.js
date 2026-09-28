import test from 'node:test';
import assert from 'node:assert/strict';
import { openedAgo, pnlPct, priceVsEntry, signedPct, sizeShare, timeAgo, vsNowLabel } from './traderRow.js';

const NOW = Date.UTC(2026, 8, 28, 12, 0, 0);
const ago = s => NOW / 1000 - s;

test('relative time steps from minutes to months', () => {
  assert.equal(timeAgo(ago(20), NOW), 'just now');
  assert.equal(timeAgo(ago(12 * 60), NOW), '12m ago');
  assert.equal(timeAgo(ago(5 * 3600 + 59 * 60), NOW), '5h ago');
  assert.equal(timeAgo(ago(47 * 3600), NOW), '47h ago');
  assert.equal(timeAgo(ago(3 * 86400), NOW), '3d ago');
  assert.equal(timeAgo(ago(35 * 86400), NOW), '5w ago');
  assert.equal(timeAgo(ago(120 * 86400), NOW), '3mo ago');
  assert.equal(timeAgo(NOW / 1000 + 600, NOW), 'just now', 'a clock ahead of ours is not negative');
  assert.equal(timeAgo(undefined, NOW), null);
});

test('opened: exact, older than the fills on hand, loading, unknown', () => {
  assert.equal(openedAgo({ opened_at: ago(2 * 86400) }, NOW), '2d ago');
  assert.equal(openedAgo({ opened_at: null, covered_from: ago(19 * 86400) }, NOW), 'over 19d ago');
  assert.equal(openedAgo({ pending: true, opened_at: ago(60) }, NOW), '…');
  assert.equal(openedAgo({ opened_at: null, covered_from: null }, NOW), null);
  assert.equal(openedAgo(null, NOW), null);
});

test('size bars scale to the largest position, with a visible floor', () => {
  assert.equal(sizeShare(33e6, 33e6), 1);
  assert.equal(sizeShare(16.5e6, 33e6), 0.5);
  assert.equal(sizeShare(10e3, 33e6), 0.03);
  assert.equal(sizeShare(10e3, 33e6, 0), 10e3 / 33e6);
  assert.equal(sizeShare(40e6, 33e6), 1, 'never past the track');
  assert.equal(sizeShare(0, 33e6), 0);
  assert.equal(sizeShare(5e6, 0), 0);
  assert.equal(sizeShare(null, 1), 0);
});

test('price against entry', () => {
  assert.ok(Math.abs(priceVsEntry(100, 101.2) - 1.2) < 1e-9);
  assert.ok(Math.abs(priceVsEntry(100, 97) + 3) < 1e-9);
  assert.equal(priceVsEntry(0, 100), null);
  assert.equal(priceVsEntry(100, null), null);
  assert.equal(vsNowLabel(100, 101.23), 'now +1.2%');
  assert.equal(vsNowLabel(100, 96.6), 'now −3.4%');
  assert.equal(vsNowLabel(100, 131), 'now +31%');
  assert.equal(vsNowLabel(100, 100.02), 'at entry');
  assert.equal(vsNowLabel(100, undefined), null);
});

test('signed percentages use a true minus and no sign on zero', () => {
  assert.equal(signedPct(1.24), '+1.2%');
  assert.equal(signedPct(-0.4), '−0.4%');
  assert.equal(signedPct(0.01), '0.0%');
  assert.equal(signedPct(NaN), '—');
  assert.equal(pnlPct(9.6), '+9.6%');
  assert.equal(pnlPct(116.4), '+116%');
  assert.equal(pnlPct(-29.2), '−29%');
  assert.equal(pnlPct(9.97), '+10%');
});
