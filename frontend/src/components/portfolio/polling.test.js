// The page's reads: never faster than the old page (TradingPanel.jsx), paused while the tab is
// hidden, and nothing at all for a page that is not shown (every timer is an effect's, cleared on
// unmount).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CADENCE } from "./usePortfolioFeeds.js";

const read = rel => readFileSync(new URL(rel, import.meta.url), "utf8");
const code = src => src.replace(/^\s*\/\/.*$/gm, "");
const FEEDS = code(read("./usePortfolioFeeds.js"));
const PAGE = code(read("./PortfolioPage.jsx"));
const OLD = read("../TradingPanel.jsx");

test("no read is faster than the old page's", () => {
  // The old page: positions, orders, TradFi and spot every 15 s; fills every 30 s; portfolio history
  // every 120 s; funding every 120 s while its view was open.
  assert.ok(OLD.includes("setInterval(fetchFast, 15_000)") && OLD.includes("setInterval(fetchMedium, 30_000)") && OLD.includes("setInterval(fetchSlow, 120_000)"));
  assert.ok(CADENCE.fast >= 15_000);
  assert.ok(CADENCE.orders >= 15_000 && CADENCE.spot >= 15_000);
  assert.ok(CADENCE.fills >= 30_000);
  assert.ok(CADENCE.portfolio >= 120_000 && CADENCE.slow >= 120_000);
  assert.ok(CADENCE.mids >= 15_000 && CADENCE.venues >= 15_000);
});

test("every poll pauses while the tab is hidden", () => {
  // Hyperliquid reads and the scanner's context: pollWhileVisible only, never a bare interval.
  assert.doesNotMatch(FEEDS, /setInterval\(/);
  const intervals = [...PAGE.matchAll(/setInterval\(([^,]+),/g)].map(m => m[1].trim());
  // The page's own intervals only move its clock (no request).
  assert.deepEqual(intervals, ["() => setNowMs(Date.now())"]);
  const polls = [...FEEDS.matchAll(/pollWhileVisible\(([^,]+), CADENCE\.(\w+)\)/g)].map(m => m[2]);
  assert.deepEqual(polls.sort(), ["fast", "fills", "mids", "orders", "portfolio", "slow", "slow", "spot", "venues"]);
  assert.match(PAGE, /return pollWhileVisible\(load, 300_000\);/);
  // A scan notice while hidden waits for the tab to come back.
  assert.match(PAGE, /if \(document\.hidden\) \{ missed\.current = true; return; \}/);
});

test("nothing is read without an address, and every timer stops with the page", () => {
  assert.match(FEEDS, /if \(!account\) return undefined;\n\s+let alive = true;/);
  assert.match(FEEDS, /stops\.forEach\(s => s\(\)\);/);
  assert.match(PAGE, /useSetupMap\(account \? "4h" : null\)/);
  // The context asks only with coins to ask about.
  assert.match(PAGE, /if \(!coinsKey\) return;/);
});
