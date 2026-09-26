import test from 'node:test';
import assert from 'node:assert/strict';
import { groupStats } from './sectors.js';
import { bestEntrySetups } from './marketPresentation.js';

const row = (symbol, sector, extra = {}) => ({ symbol, sector, regime: 'MARKUP', signal: 'LIGHT_LONG', priority_score: 60, sparkline: [100, 110], ...extra });

test('groups rank by median move against BTC and count uptrend, longs and locked', () => {
  const rows = [row('BTC/USDT', 'Majors', { sparkline: [100, 105] }), row('ETH/USDT', 'Majors'),
    row('WIF/USDT', 'Memes', { sparkline: [100, 130] }), row('BONK/USDT', 'Memes', { sparkline: [100, 120], regime: 'ACCUM', signal: 'WAIT' }),
    row('SOLO/USDT', 'Solo')];
  const g = groupStats(rows);
  assert.equal(g[0].name, 'Memes');
  assert.equal(g[0].uptrend, 1);
  assert.equal(g[0].longs, 1);
  assert.ok(Math.abs(g[0].vsBtc - 0.25) < 1e-9);   // median of [+20%, +30%] -> upper median 30%, minus BTC 5%
  assert.ok(!g.some(x => x.name === 'Solo'));          // single-market groups are hidden
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
