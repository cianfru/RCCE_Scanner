import test from "node:test";
import assert from "node:assert/strict";
import { at, inBox, movement, movers, picks, pnl, trailPoints, visible } from "./setupMap.js";

const BOX = { z: [-0.5, 1.5], n: [1, 8] };
const coin = (o = {}) => ({ coin: "X", zscore: 0.5, priority: 50, stage: "running", zone: "watch", crowd: "holding",
  traders: { pl: 3, ps: 0 }, trail: { t: [1, 2, 3], z: [2.2, 1.0, 0.5], n: [0, null, 3] }, ...o });

test("trail fills gaps from the nearest earlier reading", () => {
  assert.deepEqual(trailPoints(coin()).map(p => p.n), [0, 0, 3]);
  assert.deepEqual(trailPoints(coin({ trail: { t: [1, 2], z: [0, 1], n: [null, 3] } })).map(p => p.n), [3, 3]);
  assert.equal(trailPoints(coin({ trail: null })), null);
});

test("movement: entering the box and traders arriving", () => {
  const m = movement(coin(), BOX);
  assert.equal(m.was, false); assert.equal(m.is, true); assert.equal(m.dn, 3);
  const mv = movers([coin(), coin({ coin: "Y", zone: "late", trail: { t: [1, 2], z: [1, 2.5], n: [2, 2] } })], BOX);
  assert.deepEqual(mv.entering.map(c => c.coin), ["X"]);
  assert.deepEqual(mv.leaving.map(c => c.coin), ["Y"]);
  assert.deepEqual(mv.arriving.map(c => c.coin), ["X"]);
});

test("picks rank box coins by priority plus movement", () => {
  const cs = [coin({ coin: "A", priority: 60, trail: null }), coin({ coin: "B", priority: 50, crowd: "early", stage: "fresh" }),
    coin({ coin: "C", zone: "late", priority: 99 })];
  assert.deepEqual(picks(cs, BOX).map(p => p.c.coin), ["B", "A"]);
});

test("default view hides coins with no setup or no traders", () => {
  const cs = [coin({ coin: "A" }), coin({ coin: "B", stage: "waiting" }), coin({ coin: "C", traders: { pl: 0, ps: 0 } }),
    coin({ coin: "D", traders: { pl: 0, ps: 0 }, stage: "forming" }), coin({ coin: "E", zscore: null })];
  assert.deepEqual(visible(cs).map(c => c.coin), ["A", "D"]);
  assert.deepEqual(visible(cs, { keep: new Set(["B"]) }).map(c => c.coin), ["A", "B", "D"]);
  assert.equal(visible(cs, { all: true }).length, 4);
});

test("helpers", () => {
  assert.deepEqual(at([{ z: 0, n: 0 }, { z: 2, n: 4 }], 0.5), { z: 1, n: 2 });
  assert.equal(inBox(BOX, 0, 1), true); assert.equal(inBox(BOX, 0, 9), false);
  assert.equal(Math.round(100 * pnl({ entry: 1, side: "long" }, 1.2)), 20);
  assert.equal(Math.round(100 * pnl({ entry: 1, side: "short" }, 1.2)), -20);
});
