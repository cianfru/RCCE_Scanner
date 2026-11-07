import test from "node:test";
import assert from "node:assert/strict";
import { STRETCH_LINE, stretchReading, stretchByDay } from "./bandStretch.js";

test("the coin reading signs the value and marks the line", () => {
  assert.equal(stretchReading(null), null);
  assert.equal(stretchReading({ available: false }), null);
  assert.equal(stretchReading({ available: true, a: null }), null);
  assert.deepEqual(stretchReading({ available: true, a: 1.6, pct: 34.4 }), { value: "+1.60", pct: "+34%", tone: "hot" });
  assert.deepEqual(stretchReading({ available: true, a: -0.42, pct: -8.6 }), { value: "-0.42", pct: "-9%", tone: null });
  assert.equal(stretchReading({ available: true, a: -STRETCH_LINE, pct: -30 }).tone, "cold");
});

test("the market rows by day carry the share", () => {
  const m = stretchByDay({ stretch: { columns: ["day", "coins", "above", "median"], rows: [[10, 100, 25, 0.4], [11, 0, 0, null]] } });
  assert.deepEqual(m.get(10), { coins: 100, above: 25, median: 0.4, share: 0.25 });
  assert.equal(m.get(11).share, null);
  assert.equal(stretchByDay({}).size, 0);
});
