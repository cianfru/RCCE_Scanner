import test from 'node:test';
import assert from 'node:assert/strict';
import { altBaseline, groupStats, median } from './sectors.js';
import { bestEntrySetups } from './marketPresentation.js';

const row = (symbol, sector, extra = {}) => ({ symbol, sector, regime: 'MARKUP', signal: 'LIGHT_LONG', priority_score: 60, sparkline: [100, 110], ...extra });

// A market whose 2-candle sparkline moves by pct percent.
const mv = (symbol, sector, pct, extra = {}) => row(symbol, sector, { sparkline: [100, 100 + pct], ...extra });

test('true median, and the baseline is the typical alt (BTC excluded)', () => {
  assert.equal(median([20, 30]), 25);
  assert.equal(median([3, 1, 2]), 2);
  const rows = [mv('BTC/USDT', 'Majors', 100), mv('A/USDT', 'X', 10), mv('B/USDT', 'X', 20), mv('C/USDT', 'Y', 30)];
  const b = altBaseline(rows);
  assert.ok(Math.abs(b.M - 0.2) < 1e-9);          // median of the alts only
  assert.ok(Math.abs(b.vsBtc - (20 - 100)) < 1e-9);
});

test('scale D from the 90th percentile gap, clamped to 10..60', () => {
  const alts = Array.from({ length: 10 }, (_, i) => mv(`A${i}/USDT`, 'X', i < 9 ? 0 : 38));   // one market 38 points out
  assert.equal(altBaseline([mv('BTC/USDT', 'Majors', 0), ...alts]).D, 10);
  const wide = Array.from({ length: 10 }, (_, i) => mv(`W${i}/USDT`, 'X', i % 2 ? 38 : -38));
  assert.equal(altBaseline(wide).D, 40);
  const huge = Array.from({ length: 10 }, (_, i) => mv(`H${i}/USDT`, 'X', i % 2 ? 300 : -300));
  assert.equal(altBaseline(huge).D, 60);
});

// Groups built around a typical alt of +0%: each member's move equals its gap in points.
function scene(groups) {
  const rows = [mv('BTC/USDT', 'Majors', -20)];
  const pad = Array.from({ length: 41 }, (_, i) => mv(`PAD${i}/USDT`, undefined, 0));
  for (const [name, es] of Object.entries(groups)) es.forEach((e, i) => rows.push(mv(`${name}${i}/USDT`, name, e)));
  return [...rows, ...pad];
}

test('size shrinkage: a strong five-coin group ranks below larger, less extreme ones', () => {
  const g = groupStats(scene({
    Privacy: [64.1, 23.4, 16.4, 4.6, -13.8],
    AI: Array.from({ length: 13 }, (_, i) => (i < 7 ? 13.9 + i : 13.9 - (i - 6))),
    DeFi: Array.from({ length: 22 }, (_, i) => (i < 11 ? 9.2 + i : 9.2 - (i - 10))),
  }));
  const ranked = g.filter(x => !x.tail).map(x => [x.name, x.shown]);
  assert.deepEqual(ranked.slice(0, 3).map(([n]) => n), ['AI', 'DeFi', 'Privacy']);
  const privacy = g.find(x => x.name === 'Privacy');
  assert.equal(privacy.shown, 5);                       // 16.4 x 5/15 = 5.47
  assert.ok(privacy.small);
  assert.deepEqual(privacy.exTop, { sym: 'Privacy0', shown: 3 });
  assert.equal(privacy.ahead, 4);
});

test('ties go to the larger group; no ex-top note for an even group', () => {
  const g = groupStats(scene({ Big: Array(20).fill(3), Small: Array(10).fill(4.5), Even: [5, 4, 3, 2, 1] }));
  const big = g.findIndex(x => x.name === 'Big'), small = g.findIndex(x => x.name === 'Small');
  assert.equal(g[big].shown, g[small].shown);
  assert.ok(big < small);
  assert.equal(g.find(x => x.name === 'Even').exTop, null);
});

test('Other and two-market groups follow the ranked ones; single markets are hidden', () => {
  const g = groupStats(scene({ Other: [50, 40, 30, 20, 10, 5], Pair: [80, 70], Solo: [90], Main: [1, 2, 3, 4, 5] }));
  assert.deepEqual(g.map(x => [x.name, x.tail]), [['Main', false], ['Other', true], ['Pair', true]]);
});

test('uptrend, long signals and locked setups are still counted', () => {
  const rows = [mv('BTC/USDT', 'Majors', 5), mv('WIF/USDT', 'Memes', 30), mv('BONK/USDT', 'Memes', 20, { regime: 'ACCUM', signal: 'WAIT' }),
    mv('PEPE/USDT', 'Memes', 10)];
  const memes = groupStats(rows).find(x => x.name === 'Memes');
  assert.equal(memes.uptrend, 2);
  assert.equal(memes.longs, 2);
});

test('best setups take at most one market per sector', () => {
  const rows = [row('A/USDT', 'Memes', { priority_score: 90 }), row('B/USDT', 'Memes', { priority_score: 89 }),
    row('C/USDT', 'AI', { priority_score: 80 }), row('D/USDT', 'Other', { priority_score: 79 }), row('E/USDT', 'Other', { priority_score: 78 })];
  assert.deepEqual(bestEntrySetups(rows).map(r => r.symbol), ['A/USDT', 'C/USDT', 'D/USDT']);
});

import { rebase, raceLines, pocketGrid } from "./sectorRace.js";

test("rebase starts the window at 100", () => {
  assert.deepEqual(rebase([50, 100, 200, 300], 2), [100, 200, 300]);
});

test("race lines against BTC and pocket grid", () => {
  const data = {
    dates: [1, 2, 3], btc: [100, 110, 120],
    groups: {
      "sector:AI": { n: 3, coins: [], index: [100, 120, 150] },
      "ecosystem:Solana": { n: 4, coins: [], index: [100, 100, 120] },
      "pocket:AI|Solana": { n: 2, coins: [], index: [100, 130, 180] },
    },
  };
  const { lines } = raceLines(data, "sector", 2, "rel");
  assert.equal(lines.length, 1);
  assert.equal(lines[0].values[0], 100);
  assert.equal(Math.round(lines[0].last), 125);          // 150 / 120
  const g = pocketGrid(data, 2);
  assert.deepEqual([g.rows, g.cols], [["AI"], ["Solana"]]);
  assert.equal(Math.round(g.cells["AI|Solana"].rel), 50); // 180 / 120 - 1
});

test('typical alt leaves out BTC by base (UBTC on spot) and pegged markets', () => {
  const rows = [mv('UBTC/USDC', 'Majors', 50), mv('USDT0/USDC', 'RWA & Stablecoins', 0), mv('A/USDC', 'X', 10), mv('B/USDC', 'X', 30)];
  const b = altBaseline(rows);
  assert.equal(b.nAlts, 2);
  assert.ok(b.vsBtc != null);
});
