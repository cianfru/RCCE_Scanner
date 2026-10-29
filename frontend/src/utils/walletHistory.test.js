import test from 'node:test';
import assert from 'node:assert/strict';
import { GROUPS, SCOPES, WCOPY, byDay, firstDay, groupRows, latestOf, pct, shareScale } from './walletHistory.js';
import { popWords } from './marketHistory.js';

const FORBIDDEN = /\b(will|expect\w*|likely|predict\w*|forecast\w*|probab\w*|odds|target\w*)\b/i;
const COLS = ['day', 'wallets', 'positioned', 'long', 'short', 'long_usd', 'short_usd', 'sampled'];
const CROWD = { columns: ['day', 'long', 'short', 'long_share', 'rebuilt'], coin_columns: ['day', 'long', 'short', 'rebuilt'],
  rows: [[8, null, null, 0.7, 1], [9, null, null, 0.66, 1], [10, 30, 10, 0.75, 0], [11, 0, 0, null, 0]],
  coins: { BTC: [[10, 3, 1, 0]] }, rebuilt: { from: 8, to: 9, picked: 10 }, recorded_from: 10, overlap: null };

test('shares count flat wallets in the total and the rebuilt days are marked', () => {
  const data = { columns: [...COLS, 'rebuilt'], rebuilt: { from: 10, to: 11 },
    groups: { smart: [[12, 200, 150, 100, 40, 1, 2, 200, 0], [10, 100, 80, 50, 20, 1, 2, 30, 1], [11, 0, 0, 0, 0, 0, 0, 0, 1]] } };
  const rows = groupRows(data, 'smart');
  assert.deepEqual(rows.map(r => r.day), [10, 11, 12]);
  assert.equal(rows[0].L, 0.5);
  assert.equal(rows[0].S, 0.2);
  assert.equal(rows[1].L, null, 'no wallets that day');
  assert.deepEqual(rows.map(r => r.rebuilt), [true, true, false]);
  assert.deepEqual(groupRows(data, 'whales'), []);
  assert.equal(latestOf(data, 'smart').day, 12);
  assert.equal(firstDay(data, 'smart'), 10);
  assert.equal(byDay(data).smart.get(12).long, 100);
});

test('no longs reads zero, not below it: shares never go negative', () => {
  const data = { columns: COLS, groups: { smart: [[1, 100, 30, 0, 30, 0, 0, 100], [2, 100, 0, 0, 0, 0, 0, 100]] } };
  const rows = groupRows(data, 'smart');
  assert.deepEqual(rows.map(r => [r.L, r.S]), [[0, 0.3], [0, 0]]);
  assert.ok(rows.every(r => r.L >= 0 && r.S >= 0));
});

test("a coin scope counts that coin out of the group's wallets", () => {
  const data = { columns: [...COLS, 'rebuilt'], coin_columns: ['day', 'long', 'short', 'rebuilt'],
    groups: { smart: [[10, 100, 80, 50, 20, 0, 0, 30, 1], [11, 200, 150, 100, 40, 0, 0, 200, 0]] },
    coins: { BTC: { smart: [[10, 30, 10, 1], [11, 40, 60, 0], [12, 5, 5, 0]] } } };
  const rows = groupRows(data, 'smart', { scope: 'BTC' });
  assert.deepEqual(rows.map(r => [r.day, r.L, r.S, r.rebuilt]), [[10, 0.3, 0.1, true], [11, 0.2, 0.3, false]],
    'day 12 has no group row, so no total');
  assert.equal(latestOf(data, 'smart', 'BTC').S, 0.3);
  assert.deepEqual(groupRows(data, 'smart', { scope: 'ETH' }), []);
  assert.equal(byDay(data, { scope: 'BTC' }).smart.get(10).long, 30);
  assert.deepEqual(SCOPES.map(s => s.key), ['all', 'BTC', 'ETH', 'SOL', 'HYPE']);
  assert.equal(WCOPY.label(GROUPS[0], 'BTC'), 'Smart money · BTC');
  assert.equal(WCOPY.label(GROUPS[0], 'all'), 'Smart money');
  assert.match(WCOPY.pop.group(GROUPS[0], { scope: 'BTC' }).join(' '), /long or short BTC/);
});

test('profitable traders: the share of positions long, rebuilt days carrying the share only', () => {
  const data = { crowd: CROWD };
  const rows = groupRows(data, 'crowd');
  assert.deepEqual(rows.map(r => [r.day, r.L, r.positions, r.rebuilt]), [[8, 0.7, null, true], [9, 0.66, null, true], [10, 0.75, 40, false]],
    'a recorded day with no positions is left out');
  assert.ok(Math.abs(rows[0].S - 0.3) < 1e-9, 'the two shares sum to 100%');
  assert.deepEqual(groupRows(data, 'crowd', { scope: 'BTC' }).map(r => [r.day, r.L, r.positions]), [[10, 0.75, 4]]);
  assert.deepEqual(groupRows(data, 'crowd', { scope: 'SOL' }), []);
  assert.deepEqual(groupRows({}, 'crowd'), []);
  assert.equal(firstDay(data, 'crowd'), 8);
  assert.equal(byDay(data).crowd.get(10).L, 0.75);
  const g = GROUPS.find(x => x.key === 'crowd');
  assert.equal(WCOPY.readout(rows[2], g), '75% long · 25% short of 40 positions');
  assert.equal(WCOPY.readout(rows[0], g), '70% long · 30% short of positions');
  assert.equal(WCOPY.kpi.sub(g, 'all'), 'positions long · short');
  assert.equal(WCOPY.kpi.sub(GROUPS[0], 'ETH'), 'wallets long · short ETH');
});

test('each panel has its own scale: a round step above its largest share', () => {
  const rows = [{ wallet: { smart: { L: 0.41, S: 0.23 }, crowd: { L: 0.78, S: 0.22 } } }, { wallet: {} }];
  assert.equal(shareScale(rows, ['smart']), 0.5);
  assert.equal(shareScale(rows, ['crowd']), 1, '78% needs more room than the 80% step');
  assert.equal(shareScale([{ wallet: { smart: { L: 0.05, S: 0.02 } } }], ['smart']), 0.2);
});

test("the hover box's wallet line: shares coloured apart, the count on its own line", () => {
  const crowd = GROUPS.find(g => g.key === 'crowd');
  assert.deepEqual(WCOPY.tip({ L: 0.19, S: 0.81, positions: 1161 }, crowd), { long: '19% long', short: '81% short', of: 'of 1,161 positions' });
  assert.deepEqual(WCOPY.tip({ L: 0.4, S: 0.3, wallets: 1694 }, GROUPS[0]), { long: '40% long', short: '30% short', of: 'of 1,694 wallets' });
  assert.equal(WCOPY.tip({ L: 0.7, S: 0.3, positions: null }, crowd).of, null, 'rebuilt days carry the share only');
  assert.equal(WCOPY.tip(undefined, crowd), null);
});

test('copy: no forecast words, popovers within the word budget', () => {
  const ctx = { rebuiltTo: 20750, recordedFrom: 20722, overlap: { days: 30, long_pts: 2.4, short_pts: 3.1 }, crowd: CROWD };
  const texts = [WCOPY.from(20330), ...GROUPS.map(g => g.label)];
  const smart = GROUPS[0];
  texts.push(WCOPY.readout({ L: 0.41, S: 0.23, wallets: 1694 }, smart), WCOPY.readout({ L: 0.41, S: 0.23 }, smart), WCOPY.readout(null, smart));
  assert.equal(WCOPY.readout({ L: 0.41, S: 0.23, wallets: 1694 }, smart), '41% long · 23% short of 1,694 wallets');
  const aligned = { ...CROWD, overlap: { days: 29, from: 20726, to: 20754, offset_pts: -12.6, gap_pts: 13.4 } };
  for (const g of GROUPS) {
    for (const c of [ctx, {}, { rebuiltTo: 20750 }, { ...ctx, scope: 'BTC' }, { ...ctx, scope: 'HYPE' }, { ...ctx, crowd: { ...CROWD, rebuilt: null } },
      { ...ctx, scope: 'HYPE', crowd: aligned }]) {
      const paras = WCOPY.pop.group(g, c);
      texts.push(...paras);
      assert.ok(popWords(paras.join(' ')) <= 90, `${g.key}: ${popWords(paras.join(' '))} words: ${paras.join(' ')}`);
    }
    texts.push(WCOPY.kpi.sub(g, 'all'), WCOPY.kpi.sub(g, 'SOL'));
  }
  assert.match(WCOPY.pop.group(smart, { rebuiltTo: 20750 }).join(' '), /Rebuilt from Hyperliquid fills/);
  assert.match(WCOPY.pop.group(smart, {}).join(' '), /Recorded by Reflex/);
  assert.match(WCOPY.pop.group(smart, {}).join(' '), /up from zero/);
  const crowd = WCOPY.pop.group(GROUPS[2], ctx).join(' ');
  assert.match(crowd, /Outrider's crowd/);
  assert.match(crowd, /Picked again every day/);
  assert.match(crowd, /Before 11 Jan 1970: rebuilt with the same pick/);
  assert.match(crowd, /last month's winners, they lean the way that month went/);
  assert.match(crowd, /set to the recorded level\. Since/, 'no gap quoted without an overlap');
  assert.match(WCOPY.pop.group(GROUPS[2], { crowd: aligned }).join(' '), /set to the recorded level \(13 points apart where both exist\)/);
  assert.match(WCOPY.pop.group(GROUPS[2], { crowd: aligned, scope: 'BTC' }).join(' '), /set to the recorded level\. Since/,
    "the gap quoted is all markets', not the coin's");
  assert.match(WCOPY.pop.group(smart, ctx).join(' '), /set to the recorded level \(3 points apart where both exist\)/);
  assert.match(WCOPY.pop.group(smart, { ...ctx, scope: 'BTC' }).join(' '), /set to the recorded level; since/);
  assert.match(WCOPY.pop.group(GROUPS[2], { crowd: { ...CROWD, recorded_from: null } }).join(' '), /^Picked again every day.* Rebuilt with the same pick/);
  assert.match(WCOPY.pop.group(GROUPS[2], { crowd: { ...CROWD, rebuilt: null } }).join(' '), /Recorded by Reflex at each 00:00 UTC close/);
  for (const t of texts) {
    assert.doesNotMatch(t, FORBIDDEN, t);
    assert.doesNotMatch(t, /larsson/i, t);
    assert.doesNotMatch(t, /undefined|NaN|null/, t);
  }
  assert.equal(pct(null), '—');
});
