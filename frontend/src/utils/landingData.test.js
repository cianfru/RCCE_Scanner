import test from "node:test";
import assert from "node:assert/strict";
import { hydrate } from "./landingData.js";

test("puts the shared closes back into each trail", () => {
  const out = hydrate({ t: [1, 2], coins: [{ coin: "A", trail: { z: [0, 1], n: [1, 2] } }, { coin: "B", trail: { t: [5, 6], z: [0, 1], n: [1, 2] } }] });
  assert.deepEqual(out.coins[0].trail.t, [1, 2]);
  assert.deepEqual(out.coins[1].trail.t, [5, 6]);
});

test("rejects a body without coins", () => {
  assert.equal(hydrate(null), null);
  assert.equal(hydrate({ coins: "x" }), null);
});
