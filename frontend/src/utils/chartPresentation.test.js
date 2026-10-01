import test from "node:test";
import assert from "node:assert/strict";
import { trendNote } from "./chartPresentation.js";

test("trend note: days on 1D, bars on 4H, the average on short histories", () => {
  assert.equal(trendNote({ kind: "regression", bars: 300 }, "1d"), "300-day trend line of price (log scale).");
  assert.equal(trendNote({ kind: "regression", bars: 300 }, "4h"), "300-bar trend line of price (log scale).");
  assert.equal(trendNote(null, "1d"), "300-day trend line of price (log scale).");
  assert.equal(trendNote({ kind: "average", bars: 200 }, "1d"),
    "200-day average of price (log scale): too little history for the 300-day trend line.");
});
