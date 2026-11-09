import test from "node:test";
import assert from "node:assert/strict";
import { stretchByDay } from "./bandStretch.js";

test("the market rows by day carry the share", () => {
  const m = stretchByDay({ stretch: { columns: ["day", "coins", "above", "median"], rows: [[10, 100, 25, 0.4], [11, 0, 0, null]] } });
  assert.deepEqual(m.get(10), { coins: 100, above: 25, median: 0.4, share: 0.25 });
  assert.equal(m.get(11).share, null);
  assert.equal(stretchByDay({}).size, 0);
});
