import test from 'node:test';
import assert from 'node:assert/strict';
import {activitySummary, holdingsLine, changeLine, shortAddr} from './traderFormat.js';

test('activity counts buys and sells by position side', () => {
  assert.equal(activitySummary([{kind:'open', side:'long'}, {kind:'open', side:'long'}, {kind:'close', side:'long'}]), '2 buys, 1 sell');
  assert.equal(activitySummary([{kind:'open', side:'short'}]), '1 sell');
  assert.equal(activitySummary([]), 'no fills in range');
});

test('holdings line shows the largest and a count', () => {
  const ps = [{coin:'HYPE', side:'long', size_usd:120000}, {coin:'ETH', side:'short', size_usd:50000}, {coin:'SOL', side:'long', size_usd:9000}];
  assert.equal(holdingsLine(ps), 'long HYPE $120K, short ETH $50K +1');
  assert.equal(holdingsLine([]), 'nothing else');
});

test('change lines and short addresses', () => {
  assert.equal(changeLine({kind:'add', side:'long', coin:'SUI', usd:45000, delta_usd:15000, px:3.1}), 'Added to long SUI $15K, now $45K at 3.1');
  assert.equal(shortAddr('0x5740affc8faf8913f9f2d5fbb9bdc6e8119ea9da'), '0x5740…a9da');
});
