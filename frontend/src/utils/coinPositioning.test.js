import test from "node:test";
import assert from "node:assert/strict";
import { points, closeOf, candleEndingAt, candleBars, rebuildCandles, latest, recorded, count } from "./coinPositioning.js";
import { groupDefinitions, COIN_GROUPS } from "./traderGroups.js";

const H4 = 14400, D = 86400;
const c0 = 1793448000;                     // 31 Oct 2026 12:00 UTC, a 4h candle open

test("points pick the measure and keep gaps", () => {
  const g = { t: [10, 20], ln: [1, null], sn: [2, null], lu: [100, null], su: [5, null] };
  assert.deepEqual(points(g, "n")[1], { t: 20, long: null, short: null });
  assert.deepEqual(points(g, "usd")[0], { t: 10, long: 100, short: 5 });
  assert.deepEqual(points(null, "n"), []);
});

test("a stored reading belongs to the candle that closed; the sweep's lands minutes later", () => {
  assert.equal(closeOf(c0 + H4, "profitable"), c0 + H4);             // stored at the close
  assert.equal(closeOf(c0 + H4 + 21 * 60, "winners"), c0 + H4);      // first snapshot after it
  assert.equal(closeOf(c0 + H4 + 50 * 60, "whales"), c0 + H4);       // a late one still describes that close
  assert.equal(candleEndingAt(c0 + H4, H4), c0);
  assert.equal(candleEndingAt(c0 + 12 * 3600, D), c0 - 12 * 3600);  // daily: the midnight close ends that day
  assert.equal(candleEndingAt(c0 + 8 * 3600, D), c0 - 12 * 3600);   // a 20:00 close is inside the same day
});

test("one bar pair per candle; the live reading goes to the current candle, never over a close", () => {
  const prof = { t: [c0, c0 + H4, c0 + H4 + 600], ln: [5, 6, 7], sn: [1, 1, 2], live: true };
  const times = [c0 - H4, c0, c0 + H4];
  assert.deepEqual(candleBars(prof, "n", H4, times, "profitable").map(b => [b.time, b.long, b.live]),
    [[c0 - H4, 5, false], [c0, 6, false], [c0 + H4, 7, true]]);  // 10 min after the close: its own candle
  const sweep = { t: [c0 + 1260, c0 + H4 + 1500, c0 + H4 + 1800 * 2], ln: [3, null, 4], sn: [1, null, 2], live: true };
  assert.deepEqual(candleBars(sweep, "n", H4, times, "winners").map(b => [b.time, b.long]),
    [[c0 - H4, 3], [c0 + H4, 4]]);                              // c0: its reading is a gap
  assert.deepEqual(candleBars({ t: [c0 + 9 * H4], ln: [1], sn: [1] }, "n", H4, times, "winners"), []);  // no candle
});

test("rebuilds per candle, joined summed, the rules change kept", () => {
  const r = [{ t: c0 + 3600, joined: 20 }, { t: c0 + 7200, joined: 14, left: 3 }, { t: c0 + 2 * H4, note: "rules" }];
  assert.deepEqual(rebuildCandles(r, H4, [c0, c0 + H4]), [
    { time: c0, joined: 34, left: 3, rules: false }, { time: c0 + H4, joined: 0, left: 0, rules: true }]);
});

test("latest, recorded and counts", () => {
  const p = points({ t: [1, 2], ln: [3, null], sn: [1, null] }, "n");
  assert.equal(latest(p).t, 1);
  assert.equal(latest([]), null);
  assert.equal(recorded(p), true);
  assert.deepEqual([count(null), count(7), count(12_400)], ["—", "7", "12K"]);
});

test("definitions: live counts, the overlap, and no forecast words", () => {
  const d = groupDefinitions({ money_printer_count: 429, smart_money_count: 60, elite_count: 49 });
  assert.match(d.profitable, /429 on the list now/);
  assert.match(d.large, /^Large accounts: 60 Hyperliquid accounts .*among the 300 largest accounts \(49 now\)/);
  assert.match(d.tracked, /440 wallets/);
  assert.doesNotMatch(groupDefinitions().profitable, /on the list now/);
  assert.match(groupDefinitions().large, /^Large accounts: about 60 /);
  const zero = groupDefinitions({ money_printer_count: 0, smart_money_count: 0, elite_count: 0 });  // just after a start
  assert.doesNotMatch(zero.profitable, /on the list now/);
  assert.match(zero.large, /^Large accounts: about 60 /);
  assert.doesNotMatch(zero.tracked, /\d/);
  const words = /\b(will|expect\w*|likely|predict\w*|forecast\w*|probab\w*|odds|target\w*|proven|money printer|smart money|larsson)\b/i;
  for (const s of [...Object.values(d), ...COIN_GROUPS.flatMap(x => [x.name, x.sub])]) assert.doesNotMatch(s, words, s);
});
