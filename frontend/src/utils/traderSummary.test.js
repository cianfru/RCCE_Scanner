import test from 'node:test';
import assert from 'node:assert/strict';
import { SUMMARY_MIN, summaryRows, majoritySide, entryGap, dayChange, sideCounts, longDollarShare, moneyBar,
  topWallets, fmtDelta, fmtGap } from './traderSummary.js';

const row = (coin, L, S, extra = {}) => ({ coin, mark: 100,
  long: { n: L, usd: L * 1000, median_entry: 90 }, short: { n: S, usd: S * 1000, median_entry: 110 }, ...extra });

test('coins are sorted by traders, then dollars; thin coins wait behind Show more', () => {
  const rows = [row('A', 1, 1), row('B', 5, 0), row('C', 2, 3), row('D', 0, 0),
    { ...row('E', 4, 1), long: { n: 4, usd: 1e9 } }];
  const { shown, more } = summaryRows(rows);
  assert.deepEqual(shown.map(r => r.coin), ['E', 'B', 'C']);
  assert.deepEqual(more.map(r => r.coin), ['A']);                    // D has nobody: dropped
  assert.equal(SUMMARY_MIN, 3);
});

test('a filter searches every coin, thin ones included', () => {
  const { shown, more } = summaryRows([row('SUI', 1, 0), row('SUSHI', 6, 0), row('BTC', 9, 1)], ' su');
  assert.deepEqual(shown.map(r => r.coin), ['SUSHI', 'SUI']);
  assert.deepEqual(more, []);
});

test('the majority side goes by traders, then dollars', () => {
  assert.equal(majoritySide(row('A', 5, 2)), 'long');
  assert.equal(majoritySide(row('A', 2, 5)), 'short');
  assert.equal(majoritySide({ long: { n: 2, usd: 10 }, short: { n: 2, usd: 50 } }), 'short');
  assert.equal(majoritySide({}), 'long');
});

test('price against the larger side\'s entry, and whether that side is winning', () => {
  const l = entryGap(row('A', 5, 1));
  assert.equal(l.side, 'long');
  assert.ok(Math.abs(l.pct - 11.111) < 0.01);
  assert.equal(l.winning, true);
  const s = entryGap(row('A', 1, 5));                                // shorts at 110, price 100
  assert.equal(s.side, 'short');
  assert.ok(s.pct < 0 && s.winning);
  assert.equal(entryGap({ ...row('A', 5, 0), mark: 80 }).winning, false);
  assert.equal(entryGap({ long: { n: 3 }, short: { n: 0 }, mark: 1 }), null);
});

test('24h change needs the record from a day ago', () => {
  assert.deepEqual(dayChange(row('A', 5, 1, { day_ago: { long: 3, short: 2 } })), { long: 2, short: -1 });
  assert.equal(dayChange(row('A', 5, 1)), null);
  assert.equal(dayChange(row('A', 5, 1, { day_ago: null })), null);
});

test('side counts: 15% more on one side, else mixed', () => {
  assert.deepEqual(sideCounts([row('A', 6, 1), row('B', 1, 6), row('C', 3, 3), row('D', 1, 1)]),
    { long: 1, short: 1, mixed: 1 });                                // D is under three traders
});

test('long share of the dollars', () => {
  assert.equal(longDollarShare(row('A', 3, 1)), 0.75);
  assert.equal(longDollarShare(row('A', 0, 0)), null);
});

test('the dollars bar is scaled to the largest coin in the list', () => {
  const a = row('A', 6, 2), b = row('B', 3, 1);                      // $8K and $4K
  assert.deepEqual(moneyBar(a, [a, b]), { long: 0.75, short: 0.25 });
  assert.deepEqual(moneyBar(b, [a, b]), { long: 0.375, short: 0.125 });
  assert.deepEqual(moneyBar(b, []), { long: 0, short: 0 });
});

test('top wallets per side: the group only, largest first', () => {
  const p = (a, side, size, cohorts = ['money_printer']) => ({ address: a, side, size_usd: size, cohorts });
  const t = topWallets([p('a', 'LONG', 5), p('b', 'LONG', 9), p('c', 'SHORT', 3), p('d', 'LONG', 1),
    p('e', 'LONG', 7), p('f', 'LONG', 99, ['smart_money'])], 'money_printer');
  assert.deepEqual(t.long.map(x => x.address), ['b', 'e', 'a']);
  assert.deepEqual(t.short.map(x => x.address), ['c']);
  assert.equal(t.longTotal, 4);
  assert.equal(topWallets(null, 'money_printer').long.length, 0);
});

test('formats', () => {
  assert.equal(fmtDelta(2), '+2');
  assert.equal(fmtDelta(-1), '−1');
  assert.equal(fmtDelta(0), '0');
  assert.equal(fmtGap(3.21), '+3.2%');
  assert.equal(fmtGap(-44.4), '−44%');
  assert.equal(fmtGap(0.01), '0.0%');
  assert.equal(fmtGap(null), '--');
});
