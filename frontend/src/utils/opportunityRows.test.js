import test from 'node:test';
import assert from 'node:assert/strict';
import { ageShort, oppReasonShort, oppStatusWord, OPP_STATUS_HEX } from './opportunityRows.js';

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

test("an emerging setup's engine formula shows as its condition count", () => {
  assert.equal(oppReasonShort("MARKUP + z=-0.02 + conf=11% + consensus=RISK-ON + heat=16 [7.0/9 effective (78%) — insufficient]"), "7 of 9 conditions, not enough yet");
  assert.equal(oppReasonShort("MARKUP + z=0.3 [8.5/9 effective (94%)]"), "8.5 of 9 conditions");
  assert.equal(oppReasonShort("Setup age limit reached; await a new setup"), "Setup age limit reached; await a new setup");
  assert.equal(oppReasonShort(undefined), "");
});
