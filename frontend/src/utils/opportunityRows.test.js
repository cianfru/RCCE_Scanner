import test from 'node:test';
import assert from 'node:assert/strict';
import { ageShort, oppStatusWord, OPP_STATUS_HEX } from './opportunityRows.js';

test('status words read as plain sentence-case words', () => {
  assert.equal(oppStatusWord('confirmed'), 'Confirmed');
  assert.equal(oppStatusWord('needs_review'), 'Needs review');
  assert.equal(oppStatusWord(''), '—');
  assert.equal(OPP_STATUS_HEX.expired, undefined);
});

test('compact ages', () => {
  const now = 1_000_000;
  assert.equal(ageShort(now - 30, now), '30s');
  assert.equal(ageShort(now - 90, now), '2m');
  assert.equal(ageShort(now - 3 * 3600, now), '3h');
  assert.equal(ageShort(now - 2 * 86400, now), '2d');
  assert.equal(ageShort(now + 50, now), '0s');
  assert.equal(ageShort(undefined, now), '');
});
