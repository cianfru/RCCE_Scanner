import test from "node:test";
import assert from "node:assert/strict";
import { points, candleOf, candleBars, rebuildCandles, latest, recorded, count } from "./coinPositioning.js";
import { groupDefinitions, COIN_GROUPS } from "./traderGroups.js";

const H4 = 14400, D = 86400;
const c0 = 1793448000;                     // 31 Oct 2026 12:00 UTC, a 4h candle open

test("points pick the measure and keep gaps", () => {
  const g = { t: [10, 20], ln: [1, null], sn: [2, null], lu: [100, null], su: [5, null] };
  assert.deepEqual(points(g, "n")[1], { t: 20, long: null, short: null });
  assert.deepEqual(points(g, "usd")[0], { t: 10, long: 100, short: 5 });
  assert.deepEqual(points(null, "n"), []);
});

test("a reading at a close, or up to 30 minutes after it, belongs to the candle that closed", () => {
  assert.equal(candleOf(c0 + H4 - 15, H4), c0);            // profitable traders: the close minus 15 s
  assert.equal(candleOf(c0 + H4 + 21 * 60, H4), c0);       // the sweep: 21 minutes after the close
  assert.equal(candleOf(c0 + H4 + 3 * 3600, H4), c0 + H4); // a live reading inside the next candle
  assert.equal(candleOf(c0 + 12 * 3600 + 900, D), c0 - 12 * 3600);   // daily: 15 min after midnight, the day that closed
});

test("one bar pair per chart candle, the last reading in it; no bar without a candle or a reading", () => {
  const g = { t: [c0 - 15, c0 + H4 - 15, c0 + H4 + 1260, c0 + 2 * H4 + 3600, c0 + 9 * H4], ln: [5, 6, 7, 8, 9], sn: [1, 1, 2, null, 3] };
  const times = [c0 - H4, c0, c0 + H4];
  assert.deepEqual(candleBars(g, "n", H4, times).map(b => [b.time, b.long, b.short]),
    [[c0 - H4, 5, 1], [c0, 7, 2]]);                          // c0 + H4: its reading is a gap; c0 + 9 H4: no candle
});

test("rebuilds per candle, joined summed, the rules change kept", () => {
  const r = [{ t: c0 + 3600, joined: 20 }, { t: c0 + 7200, joined: 14, left: 3 }, { t: c0 + H4 + 60, note: "rules" }];
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
