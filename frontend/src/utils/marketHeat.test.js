import test from 'node:test';
import assert from 'node:assert/strict';
import { COLD, DEFAULT_ON, HCOPY, HOT, INDICATORS, TURN, heatOf, heatSeries, heatState, heatTurns, pickIndicators, zoneOf }
  from './marketHeat.js';
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
  assert.ok(DEFAULT_ON.includes('heat') && DEFAULT_ON.includes('uptrend') && DEFAULT_ON.includes('crowd'));
  assert.equal(new Set(INDICATORS.map(i => i.key)).size, INDICATORS.length);
  const pop = HCOPY.pop().join(' ');
  assert.ok(popWords(pop) <= 90, `${popWords(pop)} words`);
  for (const t of [pop, ...INDICATORS.map(i => i.label), ...Object.values(HCOPY.states), ...Object.values(HCOPY.parts)]) {
    assert.doesNotMatch(t, FORBIDDEN, t);
    assert.doesNotMatch(t, /larsson/i, t);
  }
});
