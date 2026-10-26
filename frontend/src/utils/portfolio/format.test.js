import test from "node:test";
import assert from "node:assert/strict";
import { pct, atrNum, pxFixed, decimalsByCoin, usd } from "./format.js";

test("pct: never rounds up to 100% from below", () => {
  assert.equal(pct(-99.9), "−99.9%");
  assert.equal(pct(-99.96), "−99.9%");
  assert.equal(pct(99.5), "99.9%");
  assert.equal(pct(100), "100%");
  assert.equal(pct(12.4), "12%");
  assert.equal(pct(0.4, { sign: true }), "+0.4%");
});

test("ATRs: one decimal under 10, whole from 10", () => {
  assert.equal(atrNum(1.44), "1.4");
  assert.equal(atrNum(9.96), "10.0");
  assert.equal(atrNum(14.04), "14");
  assert.equal(atrNum(null), "—");
});

test("fill prices line up per coin", () => {
  const d = decimalsByCoin([{ coin: "HYPE", px: "80" }, { coin: "HYPE", px: "79.883" }, { coin: "BTC", px: "80221.0" }]);
  assert.equal(d.get("HYPE"), 3);
  assert.equal(d.get("BTC"), 0);
  assert.equal(pxFixed("80", d.get("HYPE")), "80.000");
  assert.equal(pxFixed(80221, 0), "80,221");
  assert.equal(usd(-22.4, { sign: true }), "−$22");
});
