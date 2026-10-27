// Hyperliquid's per-IP weight: the page's first minute stays well under the limit, so a reload (or a
// second tab) plus a close always fit, and the 30-day history waits for room.
import test from "node:test";
import assert from "node:assert/strict";
import { Meter, weightOf, HISTORY_CAP, LIMIT } from "./weight.js";

test("weights from Hyperliquid's docs", () => {
  assert.equal(weightOf("clearinghouseState"), 2);
  assert.equal(weightOf("allMids"), 2);
  assert.equal(weightOf("frontendOpenOrders"), 20);
  assert.equal(weightOf("userFillsByTime", 2000), 120);
  assert.equal(weightOf("userFunding", 500), 45);
  assert.equal(weightOf("candleSnapshot", 168), 22);
});

test("the meter is a sliding minute", () => {
  const m = new Meter();
  m.add(100, 0); m.add(50, 30_000);
  assert.equal(m.spent(59_999), 150);
  assert.equal(m.spent(60_000), 50);
  assert.equal(m.allows(370, HISTORY_CAP, 60_000), true);
  assert.equal(m.allows(371, HISTORY_CAP, 60_000), false);
});

// The page's reads in its first minute for a busy account (13 positions, about 450 fills and 312
// funding rows a day), before any history page: the fast tick (main, its open orders, xyz) at 0, 15,
// 30 and 45 s; spot, mids, the account mode; portfolio; staking, vaults, Earn; spot names, the dex list
// and ten probes; the xyz orders; funding rates for two venues; the last 24 hours of fills and funding.
function firstMinute() {
  const m = new Meter();
  const fast = weightOf("clearinghouseState") * 2 + weightOf("frontendOpenOrders");
  for (const t of [0, 15_000, 30_000, 45_000]) m.add(fast, t);
  m.add(weightOf("spotClearinghouseState") + weightOf("allMids") + weightOf("userAbstraction"), 0);
  m.add(weightOf("portfolio"), 600);
  m.add(3 * weightOf("delegatorSummary"), 1200);
  m.add(weightOf("spotMeta") + weightOf("perpDexs") + 10 * weightOf("clearinghouseState"), 1800);
  m.add(weightOf("frontendOpenOrders") + 2 * weightOf("metaAndAssetCtxs"), 2000);
  m.add(weightOf("userFillsByTime", 450) + weightOf("userFunding", 312), 2500);
  return m;
}

test("first minute: well under the limit, with room for a reload and a close", () => {
  const m = firstMinute();
  const total = m.spent(59_000);
  assert.ok(total <= 420, `first minute ${total}`);
  // A reload inside the minute (no session-cached reads skipped, to be safe) and a close (meta 20,
  // allMids 2, the order 1).
  assert.ok(2 * total + 23 < LIMIT, `reload plus close ${2 * total + 23}`);
});

test("history pages wait while the minute is busy", () => {
  const m = firstMinute();
  // A full fills page (2000) right after first paint does not fit; it goes once the first
  // reads have left the window.
  assert.equal(m.allows(weightOf("userFillsByTime", 2000), HISTORY_CAP, 3_000), false);
  assert.equal(m.allows(weightOf("userFillsByTime", 2000), HISTORY_CAP, 63_000), true);
});
