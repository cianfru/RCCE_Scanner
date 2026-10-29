import test from 'node:test';
import assert from 'node:assert/strict';
import { COINS, DCOPY, RANGES, deriveRows, inRange, money, priceCoin, putScale, topsIn, weekly } from './deriveWallets.js';
import { popWords } from './marketHistory.js';

const FORBIDDEN = /\b(will|expect\w*|likely|predict\w*|forecast\w*|probab\w*|odds|target\w*)\b/i;
const FIELDS = ['pit_long', 'pit_short', 'now_long', 'now_short', 'pit_puts', 'now_puts'];
const cols = ['day', 'btc', 'eth', ...['BTC', 'ETH', 'ALL'].flatMap(c => FIELDS.map(f => `${c}.${f}`))];
const row = (day, btc, eth, k) => [day, btc, eth, ...[0, 1, 2].flatMap(j => [10 + k + j, 5 + j, 3, 9, 1000 * (k + 1), 5000])];
const DATA = { columns: cols, rows: [row(20360, 110000, 4000, 0), row(20361, 111000, 4100, 1), row(20367, 124000, 4500, 2)],
  tops: { BTC: [20367], ETH: [20361] }, through: 20367, smart_today: 483 };

test('rows per coin: the coin\'s counts and puts, BTC\'s price for all coins', () => {
  const btc = deriveRows(DATA, 'BTC');
  assert.deepEqual(btc[0], { day: 20360, price: 110000, pitL: 10, pitS: 5, nowL: 3, nowS: 9, pitPuts: 1000, nowPuts: 5000 });
  assert.equal(deriveRows(DATA, 'ETH')[1].price, 4100);
  assert.equal(deriveRows(DATA, 'ETH')[0].pitL, 11);
  assert.equal(deriveRows(DATA, 'ALL')[0].price, 110000);
  assert.equal(deriveRows(DATA, 'ALL')[0].pitS, 7);
  assert.deepEqual(deriveRows(null, 'BTC'), []);
  assert.deepEqual(deriveRows({ ...DATA, columns: ['day', 'btc', 'eth'] }, 'BTC'), [], 'a feed without the fields draws nothing');
  assert.equal(priceCoin('ALL'), 'BTC');
  assert.deepEqual(COINS.map(c => c.key), ['BTC', 'ETH', 'ALL']);
});

test("after the looking-back day the rows carry the ranked-at-the-time counts only", () => {
  const live = [20368, 112000, 4200, ...[0, 1, 2].flatMap(() => [12, 6, null, null, null, null])];
  const rows = deriveRows({ ...DATA, rows: [...DATA.rows, live] }, 'BTC');
  assert.deepEqual(rows[3], { day: 20368, price: 112000, pitL: 12, pitS: 6, nowL: null, nowS: null, pitPuts: null, nowPuts: null });
  assert.deepEqual(weekly(rows, 'pitPuts').at(-1), { day: 20367, sum: 3000, days: 2 }, 'a day without puts adds nothing');
});

test('weeks start on Monday and sum the days they hold', () => {
  // Day 20360 (29 Sep 2025) is a Monday, 20361 the Tuesday after; 20367 is the next Monday.
  const w = weekly(deriveRows(DATA, 'BTC'), 'pitPuts');
  assert.deepEqual(w, [{ day: 20360, sum: 3000, days: 2 }, { day: 20367, sum: 3000, days: 1 }]);
  assert.equal(new Date(20360 * 86400000).getUTCDay(), 1);
  assert.deepEqual(weekly([{ day: 20363, pitPuts: 5 }], 'pitPuts'), [{ day: 20360, sum: 5, days: 1 }], 'a Thursday joins its Monday');
});

test('range, tops and the puts scale', () => {
  const rows = Array.from({ length: 800 }, (_, i) => ({ day: 20000 + i }));
  assert.equal(inRange(rows, '1y')[0].day, 20799 - 365);
  assert.equal(inRange(rows, 'all').length, 800);
  assert.deepEqual(RANGES.map(r => r.key), ['1y', 'all']);
  assert.deepEqual(topsIn(DATA, 'ALL', 20360, 20367), [20367], 'all coins use BTC\'s tops');
  assert.deepEqual(topsIn(DATA, 'ETH', 20362, 20367), []);
  assert.equal(putScale([]), 10_000 * 1.08);
  const weeks = Array.from({ length: 40 }, (_, i) => ({ sum: i === 39 ? 3_000_000 : 20_000 }));
  assert.equal(putScale(weeks), 20_000 * 1.08, 'one huge week does not flatten the rest');
  assert.deepEqual([money(2_285_174), money(33_000), money(950), money(null)], ['$2.3M', '$33k', '$950', '—']);
});

test('copy: no forecast words, popovers within 90 words', () => {
  const texts = [DCOPY.open, DCOPY.title, DCOPY.sub(20753), DCOPY.panel.price('ETH'), DCOPY.panel.pit, DCOPY.panel.now(20753),
    DCOPY.panel.now(null), DCOPY.panel.puts, DCOPY.readout.counts(27, 10), DCOPY.readout.counts(null, null),
    DCOPY.readout.price('ALL'), DCOPY.readout.now(20753), DCOPY.readout.now(null)];
  for (const pop of [DCOPY.pop.about(), DCOPY.pop.price(), DCOPY.pop.pit(), DCOPY.pop.now(483, 20753), DCOPY.pop.now(null, null), DCOPY.pop.puts()]) {
    assert.ok(popWords(pop.join(' ')) <= 90, `${popWords(pop.join(' '))}: ${pop.join(' ')}`);
    texts.push(...pop);
  }
  for (const t of texts) {
    assert.doesNotMatch(t, FORBIDDEN, t);
    assert.doesNotMatch(t, /larsson/i, t);
    assert.doesNotMatch(t, /undefined|NaN|null/, t);
  }
  assert.equal(DCOPY.sub(20756), "Derive's best options traders against the price, data to 30 Oct 2026.");
  assert.equal(DCOPY.panel.now(20753), 'Smart wallets of 27 Oct 2026, looking back');
  assert.match(DCOPY.pop.now(483, 20753).join(' '), /the 483 Smart wallets of 27 Oct 2026, each in its past/);
  assert.match(DCOPY.pop.now(483, 20753).join(' '), /This panel ends on that day; the one above runs on/);
  assert.equal(DCOPY.readout.counts(null, null), '—', 'after the looking-back day');
});
