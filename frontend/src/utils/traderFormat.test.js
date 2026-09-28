import test from 'node:test';
import assert from 'node:assert/strict';
import {changeLine, shortAddr} from './traderFormat.js';

test('change lines and short addresses', () => {
  assert.equal(changeLine({kind:'add', side:'long', coin:'SUI', usd:45000, delta_usd:15000, px:3.1}), 'Added to long SUI $15K, now $45K at 3.1');
  assert.equal(shortAddr('0x5740affc8faf8913f9f2d5fbb9bdc6e8119ea9da'), '0x5740…a9da');
});
