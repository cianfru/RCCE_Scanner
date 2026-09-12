import test from "node:test";
import assert from "node:assert/strict";
import { clampLeft, placeVertical } from "./tooltipPosition.js";

test("centers on the anchor when there is room", () => {
  assert.equal(clampLeft(500, 14, 240, 1200), 500 + 7 - 120);
});
test("clamps at the left edge (the VPIN-at-drawer-edge case)", () => {
  assert.equal(clampLeft(20, 14, 240, 1200), 12);
});
test("clamps at the right edge", () => {
  assert.equal(clampLeft(1180, 14, 240, 1200), 1200 - 240 - 12);
});
test("prefers below, flips above when it would overflow", () => {
  assert.deepEqual(placeVertical(100, 120, 200, 800), { top: 130 });
  assert.deepEqual(placeVertical(700, 720, 200, 800), { top: 700 - 200 - 10 });
});
