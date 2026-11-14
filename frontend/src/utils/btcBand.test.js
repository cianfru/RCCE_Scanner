import test from "node:test";
import assert from "node:assert/strict";
import { bandWords } from "./btcBand.js";

test("go / no-go words from the band block", () => {
  assert.equal(bandWords(null), null);
  assert.equal(bandWords({ available: false }), null);
  assert.deepEqual(bandWords({ available: true, blocked: true, weeks_below: 2 }),
    { go: false, head: "New longs paused", line: "BTC closed under its weekly band 2 weeks in a row" });
  assert.equal(bandWords({ available: true, blocked: false, weeks_below: 1 }).line, "BTC closed one week under its weekly band");
  assert.equal(bandWords({ available: true, blocked: false, weeks_below: 0 }).head, "New longs allowed");
  for (const w of [2, 1, 0]) {
    const t = Object.values(bandWords({ available: true, blocked: w >= 2, weeks_below: w })).join(" ");
    assert.doesNotMatch(t, /\b(will|expect|likely|predict|target|probability|odds)\b/i);
  }
});
