import test from "node:test";
import assert from "node:assert/strict";
import { compactUsd } from "./money.js";

test("three significant digits with a unit", () => {
  assert.equal(compactUsd(1_240_000), "$1.24M");
  assert.equal(compactUsd(840_000), "$840K");
  assert.equal(compactUsd(12_345), "$12.3K");
  assert.equal(compactUsd(950), "$950");
  assert.equal(compactUsd(6_290_000_000), "$6.29B");
  assert.equal(compactUsd(3_196_789.43), "$3.2M");
});

test("trailing zeros drop, so an axis reads $40M", () => {
  assert.equal(compactUsd(40_000_000), "$40M");
  assert.equal(compactUsd(10_000_000), "$10M");
  assert.equal(compactUsd(1_200_000), "$1.2M");
  assert.equal(compactUsd(12_000), "$12K");
});

test("rounding up crosses into the next unit", () => {
  assert.equal(compactUsd(999_999), "$1M");
  assert.equal(compactUsd(999.7), "$1K");
  assert.equal(compactUsd(999_950_000), "$1B");
});

test("signs: minus always, plus only when asked, none on zero", () => {
  assert.equal(compactUsd(-2_541_769.05), "-$2.54M");
  assert.equal(compactUsd(18_723.9, { sign: true }), "+$18.7K");
  assert.equal(compactUsd(-43.92, { sign: true }), "-$44");
  assert.equal(compactUsd(0, { sign: true }), "$0");
  assert.equal(compactUsd(-0.001), "$0");
});

test("small, string and missing values", () => {
  assert.equal(compactUsd(0.53), "$0.53");
  assert.equal(compactUsd("2118.63"), "$2.12K");
  assert.equal(compactUsd(null), "—");
  assert.equal(compactUsd(undefined), "—");
  assert.equal(compactUsd("abc"), "—");
  assert.equal(compactUsd(Infinity), "—");
});
