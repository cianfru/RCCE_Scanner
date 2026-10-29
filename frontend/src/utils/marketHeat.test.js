import test from 'node:test';
import assert from 'node:assert/strict';
import { BCOPY, COLD, DEFAULT_ON, HCOPY, HOT, INDICATORS, TURN, broadRuns, broadState, heatOf, heatSeries, heatState,
  heatTurns, pickIndicators, zoneOf } from './marketHeat.js';
import { popWords } from './marketHistory.js';

const FORBIDDEN = /\b(will|expect\w*|likely|predict\w*|forecast\w*|probab\w*|odds|target\w*)\b/i;
const day = (d, heat) => ({ day: d, heat });

test('heat is the average of the readings a day has, Uptrend share required', () => {
  assert.deepEqual(heatOf({ uptrend: 0.9, fg: 78, wallet: { crowd: { L: 0.84 } } }),
    { heat: (90 + 78 + 84) / 3, parts: { uptrend: 90, fg: 78, traders: 84 }, n: 3 });
  assert.equal(heatOf({ uptrend: 0.4, fg: 50 }).heat, 45, 'before the traders reading: two readings');
  assert.equal(heatOf({ uptrend: 0.4 }), null, 'one reading is not a heat');
  assert.equal(heatOf({ fg: 50, wallet: { crowd: { L: 0.5 } } }), null, 'no Uptrend share, no heat');
  assert.deepEqual(heatSeries([{ day: 1, uptrend: 0.5, fg: 50 }, { day: 2, uptrend: null, fg: 40 }]).map(s => s.day), [1]);
});

test('a hot episode turns once, 10 points under its peak within 21 days', () => {
  const s = [day(1, 60), day(2, 78), day(3, 82), day(4, 80), day(5, 74), day(6, 71), day(7, 65), day(8, 76), day(9, 79)];
  const t = heatTurns(s);
  assert.deepEqual(t, [{ day: 6, kind: 'cooling', from: { day: 3, heat: 82 } }], '82 -> 71 is 11 points; 65 is the same episode');
  assert.equal(heatState(s, t).word, 'Cooling', 'the heat has not passed 82 again');
  assert.equal(heatState([...s, day(10, 85)]).word, 'Hot', 'a new high past the old peak');
  // A slow fade: 10 points off only after 21 days is not a turn.
  const slow = [day(1, 80), ...Array.from({ length: 25 }, (_, i) => day(2 + i, 79 - i * 0.2)), day(30, 60)];
  assert.deepEqual(heatTurns(slow), []);
});

test('a cold episode lifts, and the state words follow the zones otherwise', () => {
  const s = [day(1, 30), day(2, 22), day(3, 18), day(4, 24), day(5, 29)];
  assert.deepEqual(heatTurns(s), [{ day: 5, kind: 'lifting', from: { day: 3, heat: 18 } }]);
  assert.deepEqual(heatState(s), { word: 'Lifting', since: 5, heat: 29 });
  assert.deepEqual(heatState([day(1, 50), day(2, 76), day(3, 77)]), { word: 'Hot', since: 2, heat: 77 });
  assert.deepEqual(heatState([day(1, 50), day(2, 20)]), { word: 'Cold', since: 2, heat: 20 });
  assert.deepEqual(heatState([day(1, 50), day(2, 55)]), { word: 'Neutral', since: null, heat: 55 });
  const old = [day(1, 80), day(2, 69), ...Array.from({ length: 40 }, (_, i) => day(3 + i, 50))];
  assert.equal(heatState(old).word, 'Neutral', 'a turn shows for 30 days');
  assert.equal(heatState([]), null);
  assert.deepEqual([zoneOf(HOT), zoneOf(COLD), zoneOf(50), zoneOf(null)], ['hot', 'cold', null, null]);
  assert.equal(TURN, 10);
});

test('indicators: saved picks keep the catalogue order, defaults otherwise, copy within the rules', () => {
  assert.deepEqual(pickIndicators(['crowd', 'band', 'nope']), ['band', 'crowd']);
  assert.deepEqual(pickIndicators(null), DEFAULT_ON);
  assert.ok(DEFAULT_ON.includes('runs') && DEFAULT_ON.includes('uptrend') && DEFAULT_ON.includes('crowd'));
  assert.equal(new Set(INDICATORS.map(i => i.key)).size, INDICATORS.length);
  const pop = HCOPY.pop().join(' ');
  assert.ok(popWords(pop) <= 90, `${popWords(pop)} words`);
  const bpop = BCOPY.pop().join(' ');
  assert.ok(popWords(bpop) <= 90, `${popWords(bpop)} words`);
  for (const t of [pop, bpop, ...INDICATORS.map(i => i.label), ...Object.values(HCOPY.states), ...Object.values(HCOPY.parts),
    ...Object.values(BCOPY.marks), BCOPY.on(61), BCOPY.ended('22 Oct', 63)]) {
    assert.doesNotMatch(t, FORBIDDEN, t);
    assert.doesNotMatch(t, /larsson/i, t);
  }
});

const rowsOf = (shares, extra = {}) => shares.map((u, i) => ({ day: 1000 + i, uptrend: u, ...extra }));

test('broad uptrends: 55% starts one, the 5th day under ends it on the first of the five, shorter dips stay inside', () => {
  const shares = [0.5, 0.5, 0.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.5, 0.5, 0.5, 0.5, 0.6, 0.6, 0.6, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.6];
  const { days, runs } = broadRuns(rowsOf(shares));
  assert.deepEqual(runs.map(r => [r.start, r.end]), [[1003, 1015], [1021, null]], 'as research/late_uptrends.py');
  assert.equal(days.get(1010).age, 7);
  assert.ok(days.has(1018) && !days.has(1019), 'the 5th day under is outside');
});

test('broad uptrends: the high is its first touch, rolled over at 20 points under it, day 60 marked', () => {
  const { runs } = broadRuns(rowsOf([0.6, 0.8, 0.95, 0.95, 0.76, 0.74, 0.9]));
  assert.equal(runs[0].highDay, 1002);
  assert.equal(runs[0].roll, 1005, '95 -> 76 is 19 points; 74 is 21');
  assert.equal(broadRuns(rowsOf([0.95, 0.75])).runs[0].roll, 1001, 'exactly 20 points counts');
  const long = broadRuns(rowsOf(Array(70).fill(0.7))).runs[0];
  assert.equal(long.day60, 1060);
});

test('broad state: the marks inside a run, the last run outside one', () => {
  const rows = rowsOf(Array(65).fill(0.8)).map((r, i) => (i === 64 ? { ...r, fg: 72, wallet: { crowd: { L: 0.9 } } } : r));
  const st = broadState(rows);
  assert.equal(st.on, true);
  assert.equal(st.age, 64);
  assert.deepEqual(st.marks, { late: true, greed: true, crowd: true, rolled: false });
  const off = broadState([...rowsOf(Array(10).fill(0.8)), ...rowsOf(Array(6).fill(0.3)).map((r, i) => ({ ...r, day: 1010 + i }))]);
  assert.equal(off.on, false);
  assert.deepEqual([off.run.start, off.run.end], [1000, 1010]);
  assert.equal(broadState([]), null);
});
