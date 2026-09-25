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
test('terminal and blocked opportunity states never advertise fresh entries', () => {
  for (const status of ['expired', 'invalidated', 'blocked', 'unavailable', 'emerging']) {
    assert.equal(selectOpportunity(row('LIGHT_LONG', '4h', { unified_signal: 'LIGHT_LONG', opportunity: { status } }), row('LIGHT_LONG', '1d')), null);
  }
  assert.equal(selectOpportunity(row('TRIM', '4h', { opportunity: { status: 'risk_warning' } }), null).signal, 'TRIM');
});
test('backend single-timeframe entry stays visible when the supporting timeframe is watching', () => {
  const primary = row('LIGHT_LONG', '4h', { unified_signal: 'LIGHT_LONG', opportunity: { status: 'confirmed' } });
  const supporting = row('WAIT', '1d', { opportunity: { status: 'emerging' } });
  assert.equal(selectOpportunity(primary, supporting).signal, 'LIGHT_LONG');
});
