import test from "node:test";
import assert from "node:assert/strict";
import { mergeSparklines, withFullRow, rowQuery } from "./scanRows.js";
import { edgePath, withEdgeKey, EDGE_PATHS } from "./edgeUrl.js";
import { readFileSync } from "node:fs";

test("sparklines go back on the list rows by symbol", () => {
  const rows = [{ symbol: "BTC/USDT" }, { symbol: "ETH/USDT" }, { symbol: "OLD/USDT", sparkline: [9] }];
  const out = mergeSparklines(rows, { "BTC/USDT": [1, 2] });
  assert.deepEqual(out[0].sparkline, [1, 2]);
  assert.deepEqual(out[1].sparkline, []);          // missing: an empty line, never undefined
  assert.deepEqual(out[2].sparkline, [9]);         // a full row keeps its own
  assert.deepEqual(mergeSparklines(rows, null)[0].sparkline, []);
  assert.equal(mergeSparklines(null, {}), null);
});

test("the full row wins except for the live price", () => {
  const list = { symbol: "BTC/USDT", price: 101, conditions_detail: [], positioning: { oi_trend: "UP" }, sparkline: [1, 2] };
  const full = { symbol: "BTC/USDT", price: 100, conditions_detail: [{ name: "a" }, { name: "b" }],
    positioning: { oi_trend: "UP", mark_price: 100 }, sparkline: [1, 2], cto: { x: 1 } };
  const out = withFullRow(list, full);
  assert.equal(out.price, 101);
  assert.equal(out.conditions_detail.length, 2);
  assert.equal(out.positioning.mark_price, 100);
  assert.deepEqual(out.cto, { x: 1 });
  // Another coin's row or none: the list row as it is.
  assert.equal(withFullRow(list, { symbol: "ETH/USDT" }), list);
  assert.equal(withFullRow(list, null), list);
  assert.equal(withFullRow(null, full), null);
});

test("row query carries timeframe, market and the pass", () => {
  assert.equal(rowQuery({ symbol: "BTC/USDT", timeframe: "1d", market_kind: "perpetual" }, 1234),
    "/api/scan/row?symbol=BTC%2FUSDT&timeframe=1d&market=perpetual&v=1234");
  assert.equal(rowQuery({ symbol: "SOL/USDT" }), "/api/scan/row?symbol=SOL%2FUSDT&timeframe=4h");
});

test("CDN paths and keys", () => {
  assert.ok(edgePath("/api/scan?timeframe=4h&view=list"));
  assert.ok(edgePath("/api/hyperlens/positioning?cohort=large"));
  assert.ok(!edgePath("/api/traders/0xabc"));
  assert.ok(!edgePath("/api/scan/refresh"));
  assert.ok(!edgePath("/api/notifications"));
  assert.equal(withEdgeKey("/edge/api/scan?timeframe=4h", "K 1"), "/edge/api/scan?timeframe=4h&k=K%201");
  assert.equal(withEdgeKey("/edge/api/sectors", "K"), "/edge/api/sectors?k=K");
  assert.equal(withEdgeKey("/edge/api/sectors", ""), "/edge/api/sectors");
});

test("the three lists of CDN paths agree (page, worker, API)", () => {
  const worker = readFileSync(new URL("../../public/shared-worker.js", import.meta.url), "utf8");
  const api = readFileSync(new URL("../../../backend/edge.py", import.meta.url), "utf8");
  const workerPaths = new Set([...worker.match(/const EDGE_PATHS = new Set\(\[([\s\S]*?)\]\)/)[1].matchAll(/"([^"]+)"/g)].map(m => m[1]));
  const apiPaths = new Set([...api.match(/EDGE_PATHS = frozenset\(\{([\s\S]*?)\}\)/)[1].matchAll(/"([^"]+)"/g)].map(m => m[1]));
  assert.deepEqual([...workerPaths].sort(), [...EDGE_PATHS].sort());
  assert.deepEqual([...apiPaths].sort(), [...EDGE_PATHS].sort());
});
