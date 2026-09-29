import test from "node:test";
import assert from "node:assert/strict";
import { overlayPrices, priceMoves } from "./livePrices.js";

test("overlayPrices lays the latest ticks over scan rows", () => {
  const rows = [{ symbol: "BTC/USDT", price: 100 }, { symbol: "ETH/USDT", price: 10 }];
  const next = overlayPrices(rows, new Map([["BTC/USDT", 101]]));
  assert.deepEqual(next, [{ symbol: "BTC/USDT", price: 101 }, { symbol: "ETH/USDT", price: 10 }]);
  assert.equal(next[1], rows[1]);
});

test("overlayPrices returns the same array when nothing changes", () => {
  const rows = [{ symbol: "BTC/USDT", price: 100 }];
  assert.equal(overlayPrices(rows, new Map([["BTC/USDT", 100]])), rows);
  assert.equal(overlayPrices(rows, new Map()), rows);
  assert.equal(overlayPrices([], new Map([["BTC/USDT", 1]])).length, 0);
});

test("priceMoves flags direction and records prices; first sight does not flash", () => {
  const known = new Map([["BTC/USDT", 100]]);
  const f = priceMoves(known, { "BTC/USDT": 99, "NEW/USDT": 5 });
  assert.deepEqual([...f], [["BTC/USDT", "down"]]);
  assert.equal(known.get("NEW/USDT"), 5);
  assert.deepEqual([...priceMoves(known, { "BTC/USDT": 99.5 })], [["BTC/USDT", "up"]]);
  assert.equal(priceMoves(known, { "BTC/USDT": 99.5 }).size, 0);
});
