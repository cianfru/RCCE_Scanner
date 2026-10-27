// Spot buys pay their fee in the token bought (data review: HYPE, KNTQ, USDT0, ...).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { feeUsd, feeText } from "./fees.js";
import { dailyPnl } from "./calendar.js";
import { pricesByName } from "./totals.js";

const fx = name => JSON.parse(readFileSync(new URL(`./__fixtures__/${name}.json`, import.meta.url), "utf8"));

test("a fee in USDC is dollars; a fee in a token is valued at its mid", () => {
  const px = new Map([["HYPE", 77.5]]);
  assert.equal(feeUsd({ fee: "0.12", feeToken: "USDC" }, px), 0.12);
  assert.equal(feeUsd({ fee: "0.12" }, px), 0.12);
  assert.ok(Math.abs(feeUsd({ fee: "0.12", feeToken: "HYPE" }, px) - 9.3) < 1e-9);
  assert.equal(feeUsd({ fee: "0.12", feeToken: "KNTQ" }, px), null);
  assert.equal(feeText({ fee: "0.12", feeToken: "HYPE" }), "0.12 HYPE");
  assert.equal(feeText({ fee: "0.12", feeToken: "USDC" }), "0.12");
});

test("the calendar subtracts a spot buy's fee at the token's mid, not as dollars", () => {
  const fills = [{ time: Date.UTC(2026, 9, 20, 12), closedPnl: "0", fee: "1.5", feeToken: "HYPE", dir: "Buy" }];
  const day = dailyPnl(fills, [], new Map([["HYPE", 80]])).get("2026-10-20");
  assert.equal(day.fees, 120);
  assert.equal(day.net, -120);
});

test("prices by token name from spotMeta and mids", () => {
  const px = pricesByName(fx("spotMeta"), fx("allMids"));
  assert.equal(px.get("USDC"), 1);
  assert.ok(px.get("HYPE") > 1);
});
