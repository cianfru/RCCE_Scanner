import test from 'node:test';
import assert from 'node:assert/strict';
import { MIN_WALLETS, fmtSignedUsd, fmtSignedPct, cohortFields, trendCounts } from './hyperlens.js';

test('signed amounts put the sign before the dollar figure', () => {
  assert.equal(fmtSignedUsd(12_000), '+$12K');
  assert.equal(fmtSignedUsd(-3_400), '−$3K');
  assert.equal(fmtSignedUsd(0), '$0');
  assert.equal(fmtSignedUsd(null), '--');
  assert.equal(fmtSignedPct(-12), '−12%');
  assert.equal(fmtSignedPct(4.25, 1), '+4.3%');
});

test('cohort figures come from the nested block; net is the wallet-count balance', () => {
  const row = { long_count: 9, short_count: 1, trend: 'BULLISH', size_lean: 0.8,
    money_printer: { long_count: 2, short_count: 6, trend: 'BEARISH', net_ratio: 0.4, size_lean: -0.5 } };
  const all = cohortFields(row, 'all');
  assert.equal(all.positioned, 10);
  assert.equal(all.net_wallets, 0.8);
  assert.equal(all.lean, 0.8);
  const mp = cohortFields(row, 'money_printers');
  assert.equal(mp.trend, 'BEARISH');
  assert.equal(mp.net_wallets, -0.5);
  assert.equal(mp.lean, -0.5);
});

test('rows under the minimum get no trend and are counted apart', () => {
  const thin = { long_count: MIN_WALLETS - 1, short_count: 0, trend: 'BULLISH' };
  const wide = { long_count: 40, short_count: 10, trend: 'BULLISH' };
  assert.equal(cohortFields(thin, 'all').trend, 'THIN');
  assert.deepEqual(trendCounts([thin, wide], 'all'), { BULLISH: 1, BEARISH: 0, NEUTRAL: 0, THIN: 1 });
});
