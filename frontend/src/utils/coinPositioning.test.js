import test from "node:test";
import assert from "node:assert/strict";
import { points, runs, peak, nearest, everHeld, niceMax, count, tickLabel } from "./coinPositioning.js";
import { groupDefinitions, COIN_GROUPS } from "./traderGroups.js";

const g = { t: [10, 20, 30, 40], ln: [1, null, 3, 0], sn: [2, null, 1, 0], lu: [100, null, 300, 0], su: [5, null, 9, 0] };

test("points pick the measure and keep gaps", () => {
  assert.deepEqual(points(g, "n")[1], { t: 20, long: null, short: null });
  assert.deepEqual(points(g, "usd")[2], { t: 30, long: 300, short: 9 });
  assert.deepEqual(points(null, "n"), []);
});

test("runs split at gaps; peak, nearest and everHeld read recorded points", () => {
  const p = points(g, "n");
  assert.deepEqual(runs(p).map(r => r.map(x => x.t)), [[10], [30, 40]]);
  assert.equal(peak(p), 3);
  assert.equal(nearest(p, 22, 15).t, 30);
  assert.equal(nearest(p, 200, 15), null);
  assert.equal(everHeld(p), true);
  assert.equal(everHeld(points({ t: [1], ln: [0], sn: [0] }, "n")), false);
});

test("scale and number formats", () => {
  assert.deepEqual([niceMax(0), niceMax(3), niceMax(13), niceMax(160), niceMax(4.2e8)], [1, 5, 20, 200, 5e8]);
  assert.deepEqual([count(null), count(7), count(12_400)], ["—", "7", "12K"]);
  assert.deepEqual([tickLabel(5e8, "usd"), tickLabel(1e9, "usd"), tickLabel(2e4, "usd"), tickLabel(500, "usd"), tickLabel(50, "n")],
    ["$500M", "$1B", "$20K", "$500", "50"]);
});

test("definitions: live counts, the overlap, and no forecast words", () => {
  const d = groupDefinitions({ money_printer_count: 429, smart_money_count: 60, elite_count: 49 });
  assert.match(d.profitable, /429 qualify now/);
  assert.match(d.large, /49 of them are also profitable traders/);
  assert.match(d.tracked, /440 wallets/);
  assert.doesNotMatch(groupDefinitions().profitable, /qualify now/);
  const words = /\b(will|expect\w*|likely|predict\w*|forecast\w*|probab\w*|odds|target\w*|proven|money printer|smart money|larsson)\b/i;
  for (const s of [...Object.values(d), ...COIN_GROUPS.flatMap(x => [x.name, x.sub])]) assert.doesNotMatch(s, words, s);
});
