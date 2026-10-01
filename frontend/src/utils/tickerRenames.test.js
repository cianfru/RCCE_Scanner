import test from "node:test";
import assert from "node:assert/strict";
import { currentSymbol, currentSymbols } from "./tickerRenames.js";

test("old tickers map to the current names", () => {
  assert.equal(currentSymbol("MATIC/USDT"), "POL/USDT");
  assert.equal(currentSymbol("RNDR/USDT"), "RENDER/USDT");
  assert.equal(currentSymbol("FTM"), "S");
  assert.equal(currentSymbol("S/USDT"), "S/USDT");
  assert.equal(currentSymbol("FTMX/USDT"), "FTMX/USDT");
  assert.equal(currentSymbol("toString"), "toString");
  assert.equal(currentSymbol(""), "");
  assert.equal(currentSymbol(null), null);
});

test("saved lists are mapped once, without duplicates", () => {
  assert.deepEqual(currentSymbols(["BTC/USDT", "MATIC/USDT", "POL/USDT", "RNDR/USDT"]),
    { list: ["BTC/USDT", "POL/USDT", "RENDER/USDT"], changed: true });
  assert.deepEqual(currentSymbols(["BTC/USDT", "S/USDT"]), { list: ["BTC/USDT", "S/USDT"], changed: false });
  assert.deepEqual(currentSymbols(null), { list: [], changed: false });
});

test("search: a renamed ticker typed in full finds the current market", async () => {
  const { searchCoins } = await import("./search.js");
  const coins = [{ ticker: "POL", name: "Polygon", volume: 1, oi: 1 }, { ticker: "S", name: "Sonic", volume: 1, oi: 1 },
    { ticker: "RENDER", name: "Render", volume: 1, oi: 1 }, { ticker: "MATICX", name: "Other", volume: 1, oi: 1 }];
  assert.deepEqual(searchCoins("matic", coins).map(c => c.ticker), ["POL"]);
  assert.deepEqual(searchCoins("FTM", coins).map(c => c.ticker), ["S"]);
  assert.deepEqual(searchCoins("rndr", coins).map(c => c.ticker), ["RENDER"]);
  assert.deepEqual(searchCoins("mati", coins).map(c => c.ticker), ["MATICX"]);
});
