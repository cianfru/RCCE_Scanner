import test from 'node:test';
import assert from 'node:assert/strict';
import { selectOpportunity } from './opportunities.js';
const row = (signal, timeframe = '4h', extra = {}) => ({ symbol: 'BTC/USDT', signal, timeframe, ...extra });
test('mixed-strength bullish pairs are visible using the weaker signal', () => {
  assert.equal(selectOpportunity(row('STRONG_LONG'), row('LIGHT_LONG', '1d')).signal, 'LIGHT_LONG');
  assert.equal(selectOpportunity(row('STRONG_LONG'), row('ACCUMULATE', '1d')).signal, 'ACCUMULATE');
});
test('shorts align with shorts, never long entries', () => {
  assert.equal(selectOpportunity(row('LIGHT_SHORT'), row('LIGHT_SHORT', '1d')).signal, 'LIGHT_SHORT');
  assert.equal(selectOpportunity(row('LIGHT_SHORT'), row('STRONG_LONG', '1d')), null);
});
test('exit warnings remain visible without matching timeframe', () => {
  assert.equal(selectOpportunity(row('TRIM'), undefined).signal, 'TRIM');
  assert.equal(selectOpportunity(row('STRONG_LONG'), row('RISK_OFF', '1d')).signal, 'RISK_OFF');
});
test('backend blocks and unavailable decisions are respected', () => {
  assert.equal(selectOpportunity(row('STRONG_LONG', '4h', { unified_signal: 'WAIT' }), row('LIGHT_LONG', '1d')), null);
  assert.equal(selectOpportunity(row('STRONG_LONG', '4h', { signal_status: 'unavailable' }), row('LIGHT_LONG', '1d')), null);
});
