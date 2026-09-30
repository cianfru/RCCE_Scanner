import test from "node:test";
import assert from "node:assert/strict";
import { previewRows, PREVIEW_REFRESH_MS } from "./previewRows.js";

test("keeps one row per preview coin, USDT first", () => {
  const rows = previewRows([
    { symbol: "HYPE/USDC", regime: "A" },
    { symbol: "HYPE/USDT", regime: "B" },
    { symbol: "BTC/USDT" },
    { symbol: "DOGE/USDT" },
    { symbol: "ETH/BTC" },
  ]);
  assert.deepEqual(rows.map(r => r.symbol).sort(), ["BTC/USDT", "HYPE/USDT"]);
});

test("falls back to another quote and tolerates bad input", () => {
  assert.deepEqual(previewRows([{ symbol: "HYPE/USDC" }]).map(r => r.symbol), ["HYPE/USDC"]);
  assert.deepEqual(previewRows(null), []);
  assert.deepEqual(previewRows([null, {}]), []);
});

test("refreshes every five minutes", () => {
  assert.equal(PREVIEW_REFRESH_MS, 300000);
});
