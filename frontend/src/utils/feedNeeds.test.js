import test from "node:test";
import assert from "node:assert/strict";
import { feedNeeds, needsKey } from "./feedNeeds.js";

test("the scanner keeps only the timeframe on screen fresh, with Fear & Greed", () => {
  assert.deepEqual(feedNeeds("1d"), { scan: ["1d"], tradfi: false, sentiment: true });
  assert.deepEqual(feedNeeds("4h"), { scan: ["4h"], tradfi: false, sentiment: true });
});

test("coin page, Radar and Signal Log show both timeframes", () => {
  for (const tab of ["radar", "signals"]) assert.deepEqual(feedNeeds(tab).scan, ["4h", "1d"]);
  assert.deepEqual(feedNeeds("1d", { coinPage: true }).scan, ["4h", "1d"]);
  assert.equal(feedNeeds("1d", { coinPage: true }).sentiment, false);
});

test("TradFi polls only TradFi while the live connection keeps the clock", () => {
  assert.deepEqual(feedNeeds("tradfi"), { scan: [], tradfi: true, sentiment: false });
  assert.deepEqual(feedNeeds("executor"), { scan: [], tradfi: false, sentiment: false });
});

test("without the live connection other pages poll the last scanner timeframe for the clock", () => {
  assert.deepEqual(feedNeeds("traders", { wsConnected: false, lastScannerTf: "4h" }).scan, ["4h"]);
  assert.deepEqual(feedNeeds("tradfi", { wsConnected: false }).scan, ["1d"]);
  assert.deepEqual(feedNeeds("1d", { wsConnected: false }).scan, ["1d"]);
});

test("needsKey is stable and distinguishes needs", () => {
  assert.equal(needsKey({ scan: ["1d", "4h"], tradfi: false, sentiment: false }), needsKey({ scan: ["4h", "1d"], tradfi: false, sentiment: false }));
  assert.notEqual(needsKey(feedNeeds("1d")), needsKey(feedNeeds("4h")));
  assert.notEqual(needsKey(feedNeeds("tradfi")), needsKey(feedNeeds("executor")));
});
