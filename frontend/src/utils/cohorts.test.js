import test from 'node:test';
import assert from 'node:assert/strict';
import { displayName, orderedRows, gapSeries, leanPct, usd } from './cohorts.js';

test('display names never show the internal cohort keys', () => {
  assert.equal(displayName('pnl', 'Smart Money'), '$100K–1M profit');
  assert.equal(displayName('equity', 'Leviathan'), '$5M+ account');
  const rows = orderedRows([{ dimension: 'pnl', cohort: 'Money Printer' }, { dimension: 'pnl', cohort: 'Giga-Rekt' }, { dimension: 'equity', cohort: 'Whale' }], 'pnl');
  assert.deepEqual(rows.map(r => r.name), ['Lost $1M+', '$1M+ profit']);
});

test('gap: profitable minus losing lean at each reading', () => {
  const h = {
    'Money Printer': [{ ts: 1, long_usd: 30, short_usd: 10 }],
    'Smart Money': [{ ts: 1, long_usd: 10, short_usd: 10 }],
    'Full Rekt': [{ ts: 1, long_usd: 10, short_usd: 30 }],
    'Grinder': [{ ts: 1, long_usd: 999, short_usd: 0 }],
  };
  const [g] = gapSeries(h);
  assert.equal(g.winners, 20 / 60);
  assert.equal(g.losers, -0.5);
  assert.ok(Math.abs(g.gap - (20 / 60 + 0.5)) < 1e-9);
});

test('formatting', () => {
  assert.equal(leanPct(0.4368), '+44%');
  assert.equal(leanPct(-0.2), '−20%');
  assert.equal(leanPct(null), '—');
  assert.equal(leanPct(-0.004), '0%');
  assert.equal(usd(3730733624), '$3.7B');
  assert.equal(usd(-5561641), '$5.6M');
});
