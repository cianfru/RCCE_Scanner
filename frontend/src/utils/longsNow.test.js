import test from "node:test";
import assert from "node:assert/strict";
import { longsNow, pctText, strengthBar } from "./longsNow.js";

test("long signals in priority order, joined to their Radar reading", () => {
  const rows = [
    { symbol: "A/USDT", signal: "LIGHT_LONG", priority_score: 60 },
    { symbol: "B/USDT", signal: "STRONG_LONG", priority_score: 70 },
    { symbol: "C/USDT", signal: "WAIT", priority_score: 90 },
    { symbol: "D/USDT", signal: "ACCUMULATE", priority_score: 80 },
    { symbol: "E/USDC", signal: "LIGHT_LONG", priority_score: 99, market_kind: "spot" },
    { symbol: "F/USDT", signal: "REVIVAL_SEED", priority_score: 60 },
  ];
  const out = longsNow(rows, [{ symbol: "A/USDT", coin: "A" }]);
  assert.deepEqual(out.map(x => x.row.symbol), ["B/USDT", "A/USDT", "F/USDT"]);
  assert.equal(out[1].c.coin, "A");
  assert.equal(out[0].c, null);
  assert.deepEqual(longsNow(null, null), []);
});

test("strength bar and text", () => {
  assert.equal(strengthBar(20), 0.5);
  assert.equal(strengthBar(-90), -1);
  assert.equal(strengthBar(null), 0);
  assert.equal(pctText(18.4), "+18%");
  assert.equal(pctText(-3.25), "−3.3%");
  assert.equal(pctText(0), "0.0%");
});
