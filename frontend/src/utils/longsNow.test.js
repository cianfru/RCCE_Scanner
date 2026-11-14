import test from "node:test";
import assert from "node:assert/strict";
import { dayText, longsNow, pctText, sparkPaths, vsBtcLine } from "./longsNow.js";

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

test("texts", () => {
  assert.equal(pctText(18.4), "+18%");
  assert.equal(pctText(-3.25), "−3.3%");
  assert.equal(pctText(0), "0.0%");
  assert.equal(dayText(20581, 2026), "8 May");                     // 20581 = 8 May 2026
  assert.equal(dayText(20581, 2027), "8 May 2026");
  assert.equal(vsBtcLine({ state: "above", trend: "up", since: 20581 }, 2026), "Above · since 8 May");
  assert.equal(vsBtcLine({ state: "inside", trend: null, since: null }, 2026), "Inside");
  assert.equal(vsBtcLine(null), "");
});

test("sparkline paths share one scale and skip missing band points", () => {
  const p = sparkPaths({ r: [1, 2, 3], lo: [null, 1, 1], hi: [null, 2, 2] }, 100, 20, 0);
  assert.equal(p.line, "M0.0,20.0 L50.0,10.0 L100.0,0.0");
  assert.equal(p.band, "M50.0,10.0 L100.0,10.0 L100.0,20.0 L50.0,20.0 Z");
  assert.deepEqual(p.end, { x: 100, y: 0 });
  assert.equal(sparkPaths({ r: [1] }, 10, 10), null);
});
