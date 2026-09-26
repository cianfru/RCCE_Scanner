import test from 'node:test';
import assert from 'node:assert/strict';
import {engineSide, tradersSide, matchOf, vsEntry, MAP_FILTERS} from './positioning.js';

const row = (L, S, sig, regime='MARKUP') => ({long:{n:L, median_entry:2}, short:{n:S, median_entry:null}, mark:2.2,
  engine:{'4h':{signal:sig, regime}}, opens_24h:{long:0, short:0}, convergence:null});

test('engine stance from signal and regime', () => {
  assert.equal(engineSide({signal:'ACCUMULATE', regime:'REACC'}), 'long');
  assert.equal(engineSide({signal:'TRIM', regime:'MARKUP'}), 'bearish');
  assert.equal(engineSide({signal:'WAIT', regime:'MARKDOWN'}), 'bearish');
  assert.equal(engineSide({signal:'WAIT', regime:'MARKUP'}), 'neutral');
  assert.equal(engineSide(undefined), null);
});

test('traders need two wallets and a lean', () => {
  assert.equal(tradersSide(row(1,0)), null);
  assert.equal(tradersSide(row(2,0)), 'long');
  assert.equal(tradersSide(row(1,1)), 'mixed');
  assert.equal(tradersSide(row(1,3)), 'short');
});

test('agreement, opposition and filters', () => {
  assert.equal(matchOf(row(3,0,'LIGHT_LONG')), 'agree');
  assert.equal(matchOf(row(0,2,'TRIM')), 'agree');
  assert.equal(matchOf(row(3,0,'RISK_OFF')), 'opposed');
  assert.equal(matchOf(row(0,2,'STRONG_LONG')), 'opposed');
  assert.equal(matchOf(row(3,0,'WAIT')), null);
  assert.equal(Math.round(vsEntry(row(3,0,'WAIT'), 'long')), 10);
  assert.equal(MAP_FILTERS.agree(row(3,0,'LIGHT_LONG')), true);
  assert.equal(MAP_FILTERS.new(row(3,0,'WAIT')), false);
});
