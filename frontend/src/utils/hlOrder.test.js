import test from "node:test";
import assert from "node:assert/strict";
import { metaIndex, assetFor, marketOrderWire, closeOrderWire, formatVolume } from "./hlOrder.js";
import { hlName, kKey, kSymbol } from "./tickerRenames.js";

// A slice of Hyperliquid's meta; the asset index is the position in the list.
const { byName } = metaIndex([
  { name: "BTC", szDecimals: 5, maxLeverage: 40 },
  { name: "ETH", szDecimals: 4, maxLeverage: 25 },
  { name: "kPEPE", szDecimals: 0, maxLeverage: 10 },
  { name: "BONK", szDecimals: 0, maxLeverage: 5 },
  { name: "kBONK", szDecimals: 0, maxLeverage: 10 },
  { name: "kNEIRO", szDecimals: 1, maxLeverage: 5 },
  { name: "KAS", szDecimals: 0, maxLeverage: 5 },
  { name: "kNEWK", szDecimals: 0, maxLeverage: 3 },
]);
const mids = { BTC: "81000", kPEPE: "0.01052", BONK: "0.00002", kBONK: "0.02", kNEIRO: "0.41", KAS: "0.08", kNEWK: "0.5" };

test("the app's key and Hyperliquid's name, both ways", () => {
  for (const b of ["PEPE", "SHIB", "BONK", "LUNC", "FLOKI", "NEIRO"]) {
    assert.equal(hlName(`K${b}`), `k${b}`);
    assert.equal(kKey(`k${b}`), `K${b}`);
  }
  assert.equal(hlName("kPEPE"), "kPEPE");                    // Hyperliquid's own name passes through
  for (const c of ["BTC", "KAS", "KAITO", "BONK", "", null]) assert.equal(hlName(c, byName), c);
  assert.equal(hlName("KNEWK", byName), "kNEWK");             // a k market listed later, from the meta
  assert.equal(kKey("BTC"), "BTC");
  assert.equal(kKey("KAS"), "KAS");
  assert.equal(kSymbol("kPEPE/USDT"), "KPEPE/USDT");
  assert.equal(kSymbol("BTC/USDT"), "BTC/USDT");
});

test("a KPEPE order carries kPEPE's asset index and is sized in k-units", () => {
  const w = marketOrderWire({ coin: "KPEPE", isBuy: true, sizeUsd: 1000, slippage: 0.01 }, byName, mids);
  assert.equal(w.name, "kPEPE");
  assert.equal(w.order.a, 2);
  assert.equal(w.order.s, "95057");                           // $1,000 / 0.01052 per 1,000 PEPE, szDecimals 0
  assert.equal(w.order.p, "0.010625");
  assert.equal(w.order.r, false);
  assert.ok(Math.abs(Number(w.order.s) * 0.01052 - 1000) < 0.01052);
  assert.equal(assetFor("KPEPE", byName).szDecimals, 0);
  const n = marketOrderWire({ coin: "KNEIRO", isBuy: false, sizeUsd: 100 }, byName, mids);
  assert.equal(n.order.a, 5);
  assert.equal(n.order.s, "243.9");                           // kNEIRO's own szDecimals (1)
});

test("a close read back from Hyperliquid as kPEPE goes out as kPEPE, reduce-only", () => {
  const w = closeOrderWire({ coin: "kPEPE", size: -950.7, isLong: false }, byName, mids);
  assert.deepEqual({ a: w.order.a, b: w.order.b, s: w.order.s, r: w.order.r }, { a: 2, b: true, s: "950", r: true });
  assert.equal(closeOrderWire({ coin: "KPEPE", size: 950, isLong: true }, byName, mids).order.a, 2);
});

test("a normal coin is unchanged", () => {
  const w = marketOrderWire({ coin: "BTC", isBuy: true, sizeUsd: 1000 }, byName, mids);
  assert.deepEqual(w.order, { a: 0, b: true, p: "81810.0", s: "0.01234", r: false, t: { limit: { tif: "Ioc" } } });
  assert.equal(marketOrderWire({ coin: "BONK", isBuy: true, sizeUsd: 10 }, byName, mids).order.a, 3);   // not kBONK
  assert.equal(marketOrderWire({ coin: "KAS", isBuy: true, sizeUsd: 10 }, byName, mids).order.a, 6);
  assert.throws(() => marketOrderWire({ coin: "NOPE", isBuy: true, sizeUsd: 10 }, byName, mids), /Unknown asset: NOPE/);
  assert.throws(() => marketOrderWire({ coin: "KPEPE", isBuy: true, sizeUsd: 0.001 }, byName, mids), /Volume too small/);
  assert.equal(formatVolume(1.23456789, 5), 1.23456);
});
