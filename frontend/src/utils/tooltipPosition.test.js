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
test("fits above: sits above, clear of the anchor (the HEAT help from a low header)", () => {
  assert.deepEqual(placeVertical(877, 893, 600, 1000), { top: 877 - 600 - 10 });
});
test("too tall for either side: the roomier side, capped, never over the anchor", () => {
  // A 900px card from a header label low in a 1000px window: above, capped, ends above the label.
  const up = placeVertical(877, 893, 900, 1000);
  assert.deepEqual(up, { top: 16, maxHeight: 877 - 10 - 16 });
  assert.ok(up.top + up.maxHeight <= 877 - 10);
  // Near the top: below, capped at the viewport bottom.
  const down = placeVertical(100, 116, 1200, 1000);
  assert.deepEqual(down, { top: 126, maxHeight: 1000 - 16 - 126 });
});
