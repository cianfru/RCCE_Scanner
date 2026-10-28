import test from 'node:test';
import assert from 'node:assert/strict';
import { GROUPS, WCOPY, Z_MIN, Z_WINDOW, byDay, firstDay, groupRows, latestOf, ofWallets, pct, signedZ, trailingZ }
  from './walletHistory.js';
import { popWords } from './marketHistory.js';

const FORBIDDEN = /\b(will|expect\w*|likely|predict\w*|forecast\w*|probab\w*|odds|target\w*)\b/i;
const COLS = ['day', 'wallets', 'positioned', 'long', 'short', 'long_usd', 'short_usd', 'sampled'];

test('a day is read against the days before it, never against itself', () => {
  const rows = Array.from({ length: 40 }, (_, i) => ({ day: i, v: i < 39 ? (i % 2 ? 0.4 : 0.6) : 0.9 }));
  const z = trailingZ(rows, 'v', 90, 30);
  assert.equal(z[29], null, 'fewer than 30 earlier days');
  // Day 39 against days 0..38 (20 at 0.6, 19 at 0.4): population mean and sd of those 39 values.
  const mean = (20 * 0.6 + 19 * 0.4) / 39, sd = Math.sqrt((20 * 0.36 + 19 * 0.16) / 39 - mean * mean);
  assert.ok(Math.abs(z[39] - (0.9 - mean) / sd) < 1e-9, String(z[39]));
  // Adding the spike itself to the window would shrink it; the value only depends on earlier days.
  const again = trailingZ([...rows.slice(0, 39), { day: 39, v: 5 }], 'v', 90, 30);
  assert.ok(again[39] > z[39]);
  assert.deepEqual(again.slice(0, 39), z.slice(0, 39));
});

test('the window counts days, so a gap shrinks it rather than reaching further back', () => {
  const rows = [...Array.from({ length: 40 }, (_, i) => ({ day: i, v: 0.2 + 0.01 * (i % 3) })),
    ...Array.from({ length: 40 }, (_, i) => ({ day: 200 + i, v: 0.5 + 0.01 * (i % 3) }))];
  const z = trailingZ(rows, 'v', 90, 30);
  assert.equal(z[40], null, 'day 200: days 0-39 are more than 90 days back');
  assert.equal(z[69], null);
  assert.notEqual(z[70], null, 'day 230 has 30 earlier days in its window');
  assert.ok(Math.abs(z[70]) < 3, 'measured against the new level only');
});

test('no spread or a missing value gives no z-score', () => {
  const flat = Array.from({ length: 35 }, (_, i) => ({ day: i, v: 0.3 }));
  assert.deepEqual(trailingZ(flat, 'v').filter(v => v != null), []);
  const holes = Array.from({ length: 35 }, (_, i) => ({ day: i, v: i % 2 ? null : 0.3 + 0.01 * i }));
  const z = trailingZ(holes, 'v', 90, 10);
  assert.equal(z[33], null, 'the day itself is missing');
  assert.notEqual(z[34], null);
});

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
  assert.equal(firstDay(data), 10);
  assert.equal(byDay(data).smart.get(12).long, 100);
  assert.equal(ofWallets(rows[2]), '100 long · 40 short of 200');
});

test('z-scores ride along on every row once the window has enough days', () => {
  const groups = { smart: [], whales: [] };
  for (let d = 0; d < 120; d++) {
    const shortShare = d < 110 ? 0.2 + 0.02 * Math.sin(d) : 0.4;          // shorts jump at the end
    groups.smart.push([d, 1000, 700, 450, Math.round(1000 * shortShare), 0, 0, 1000]);
    groups.whales.push([d, 300, 250, 150, 90, 0, 0, 300]);
  }
  const rows = groupRows({ columns: COLS, groups }, 'smart');
  assert.equal(rows[Z_MIN - 1].zS, null);
  assert.notEqual(rows[Z_MIN].zS, null);
  assert.ok(rows[115].zS > 3, 'more shorts than usual is a large positive short z, drawn downward');
  assert.ok(Z_WINDOW >= Z_MIN);
});

test('copy: no forecast words, popovers within the word budget', () => {
  const ctx = { rebuiltTo: 20750, recordedFrom: 20722, overlap: { days: 30, long_pts: 2.4, short_pts: 3.1 } };
  const texts = [WCOPY.from(20330), WCOPY.readout({ L: 0.41, S: 0.23, zL: 1.234, zS: -0.4 }, 'z'),
    WCOPY.readout({ L: 0.41, S: 0.23 }, 'share'), WCOPY.readout(null), ...GROUPS.map(g => g.label)];
  for (const g of GROUPS) {
    const paras = WCOPY.pop.group(g, ctx);
    texts.push(...paras);
    assert.ok(popWords(paras.join(' ')) <= 90, `${g.key}: ${popWords(paras.join(' '))} words`);
    assert.ok(popWords(WCOPY.pop.group(g, {}).join(' ')) <= 90);
    assert.match(WCOPY.pop.group(g, { rebuiltTo: 20750 }).join(' '), /Rebuilt from Hyperliquid fills/);
    assert.match(WCOPY.pop.group(g, {}).join(' '), /Recorded by Reflex/);
    const share = WCOPY.pop.group(g, { ...ctx, mode: 'share' });
    texts.push(...share);
    assert.ok(popWords(share.join(' ')) <= 90);
  }
  for (const t of texts) {
    assert.doesNotMatch(t, FORBIDDEN, t);
    assert.doesNotMatch(t, /larsson/i, t);
  }
  assert.equal(WCOPY.readout({ L: 0.41, S: 0.23, zL: 1.234, zS: -0.4 }, 'z'), '41% long · 23% short · z +1.2 / −0.4');
  assert.equal(signedZ(0.001), '0.0');
  assert.equal(pct(null), '—');
});
