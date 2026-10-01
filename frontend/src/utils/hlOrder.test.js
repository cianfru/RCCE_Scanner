import test from "node:test";
import assert from "node:assert/strict";
import { metaIndex, assetFor, marketOrderWire, closeOrderWire, formatVolume, formatPrice } from "./hlOrder.js";
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
  assert.equal(w.order.p, "0.010626");                         // 0.01052 x 1.01 = 0.0106252, a buy rounds up
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
  assert.deepEqual(w.order, { a: 0, b: true, p: "81810", s: "0.01234", r: false, t: { limit: { tif: "Ioc" } } });
  assert.equal(marketOrderWire({ coin: "BONK", isBuy: true, sizeUsd: 10 }, byName, mids).order.a, 3);   // not kBONK
  assert.equal(marketOrderWire({ coin: "KAS", isBuy: true, sizeUsd: 10 }, byName, mids).order.a, 6);
  assert.throws(() => marketOrderWire({ coin: "NOPE", isBuy: true, sizeUsd: 10 }, byName, mids), /Unknown asset: NOPE/);
  assert.throws(() => marketOrderWire({ coin: "KPEPE", isBuy: true, sizeUsd: 0.001 }, byName, mids), /Volume too small/);
  assert.equal(formatVolume(1.23456789, 5), 1.23456);
});

// Hyperliquid's perp price rule, checked independently of formatPrice: at most 5 significant figures
// and at most (6 - szDecimals) decimals, unless the price is an integer.
function obeysPriceRule(p, szDecimals) {
  assert.match(p, /^\d+(\.\d*[1-9])?$/);                     // plain decimal, no trailing zeros
  if (!p.includes(".")) return true;
  const decimals = p.split(".")[1].length;
  const sig = p.replace(".", "").replace(/^0+/, "").length;
  return decimals <= 6 - szDecimals && sig <= 5;
}

test("prices follow Hyperliquid's rule across magnitudes, buy up and sell down", () => {
  // [price, szDecimals, nearest, buy (up), sell (down)]
  const table = [
    [97123.45, 5, "97123", "97124", "97123"],            // BTC: 5 sig figs leave no decimals
    [3456.789, 4, "3456.8", "3456.8", "3456.7"],          // ETH
    [1.23456, 1, "1.2346", "1.2346", "1.2345"],
    [1.23456, 3, "1.235", "1.235", "1.234"],              // the decimal cap (6 - 3) binds first
    [0.523456, 0, "0.52346", "0.52346", "0.52345"],       // ADA-like: 6 decimals would be 6 sig figs
    [0.4142857, 1, "0.41429", "0.41429", "0.41428"],      // kNEIRO-like
    [0.0105234, 0, "0.010523", "0.010524", "0.010523"],   // kPEPE-like
    [0.000012345, 0, "0.000012", "0.000013", "0.000012"], // the decimal cap leaves 2 sig figs
    [123456.7, 5, "123457", "123457", "123456"],          // rounds to an integer
    [9.99996, 2, "10", "10", "9.9999"],                    // rounding up across a power of ten
    [0.0999996, 0, "0.1", "0.1", "0.099999"],
  ];
  for (const [px, sz, nearest, up, down] of table) {
    assert.equal(formatPrice(px, sz), nearest, `${px} nearest`);
    assert.equal(formatPrice(px, sz, "up"), up, `${px} up`);
    assert.equal(formatPrice(px, sz, "down"), down, `${px} down`);
    for (const p of [nearest, up, down]) assert.ok(obeysPriceRule(p, sz), `${p} at szDecimals ${sz}`);
    assert.ok(Number(up) >= px && Number(down) <= px, `${px} stays on the marketable side`);
  }
  // Integer prices are always allowed, whatever their significant figures; an exact price is kept.
  assert.equal(formatPrice(81810, 5, "up"), "81810");
  assert.equal(formatPrice(123456, 5, "down"), "123456");
  assert.equal(formatPrice(81000 * 1.01, 5, "up"), "81810");    // float noise does not add a tick
  assert.equal(formatPrice(0.52346, 0, "up"), "0.52346");
  assert.equal(formatPrice(3456.7, 4, "down"), "3456.7");
  assert.throws(() => formatPrice(0.0000004, 0, "down"), /rounds to zero/);
  assert.throws(() => formatPrice(0, 0), /Invalid price/);
});

test("every price the panel sends obeys the rule, on the marketable side", () => {
  const { byName: meta } = metaIndex([
    { name: "ADA", szDecimals: 0, maxLeverage: 10 }, { name: "kNEIRO", szDecimals: 1, maxLeverage: 5 },
    { name: "BTC", szDecimals: 5, maxLeverage: 40 }, { name: "ETH", szDecimals: 4, maxLeverage: 25 },
    { name: "kPEPE", szDecimals: 0, maxLeverage: 10 }, { name: "TINY", szDecimals: 0, maxLeverage: 3 },
  ]);
  const book = { ADA: "0.523456", kNEIRO: "0.4142857", BTC: "97123.45", ETH: "3456.789", kPEPE: "0.0105234", TINY: "0.000012345" };
  for (const coin of ["ADA", "KNEIRO", "BTC", "ETH", "KPEPE", "TINY"]) {
    const { name, szDecimals } = assetFor(coin, meta);
    const mid = Number(book[name]);
    for (const isBuy of [true, false]) {
      const o = marketOrderWire({ coin, isBuy, sizeUsd: 1000, slippage: 0.01 }, meta, book).order;
      assert.ok(obeysPriceRule(o.p, szDecimals), `${coin} ${isBuy ? "buy" : "sell"} ${o.p}`);
      assert.ok(isBuy ? Number(o.p) >= mid * 1.01 : Number(o.p) <= mid * 0.99, `${coin} limit ${o.p}`);
      const c = closeOrderWire({ coin, size: 5, isLong: !isBuy, slippage: 0.02 }, meta, book).order;
      assert.ok(obeysPriceRule(c.p, szDecimals), `${coin} close ${c.p}`);
      assert.ok(isBuy ? Number(c.p) >= mid * 1.02 : Number(c.p) <= mid * 0.98, `${coin} close limit ${c.p}`);
    }
  }
  assert.equal(marketOrderWire({ coin: "ADA", isBuy: true, sizeUsd: 100 }, meta, book).order.p, "0.5287");    // 0.52869056 up; was "0.528691"
  assert.equal(marketOrderWire({ coin: "ADA", isBuy: false, sizeUsd: 100 }, meta, book).order.p, "0.51822"); // was "0.518221"
});

test("sizes floor to szDecimals and a close never exceeds the position", () => {
  assert.equal(formatVolume(0.123456789, 5), 0.12345);                // BTC
  assert.equal(formatVolume(1.23456789, 4), 1.2345);                  // ETH
  assert.equal(formatVolume(95057.9, 0), 95057);                      // a k market
  assert.equal(formatVolume(0.29, 2), 0.29);                          // 0.29 * 100 is 28.999999999999996 in floats
  for (const [size, sz] of [[0.29, 2], [0.0123456789, 5], [950.7, 0], [1.005, 2], [3.3, 1]]) {
    const v = formatVolume(size, sz);
    assert.ok(v <= size && size - v < Math.pow(10, -sz), `${size} at ${sz}: ${v}`);
  }
  for (const size of [0.29, 0.0123456789, 3.3, 2.71828]) {
    const w = closeOrderWire({ coin: "ETH", size, isLong: true }, byName, { ETH: "3456.789" });
    assert.ok(Number(w.order.s) <= size && w.order.r === true && w.order.b === false);
  }
  assert.throws(() => closeOrderWire({ coin: "BTC", size: 0.000004, isLong: true }, byName, mids), /Volume too small/);
});
