import test from "node:test";
import assert from "node:assert/strict";
import { asOfLabel, stalest } from "./asOf.js";

const at = (y, mo, d, h, mi) => new Date(y, mo, d, h, mi).getTime() / 1000;

test("nothing while the data is current or has no time", () => {
  assert.equal(asOfLabel(null), null);
  assert.equal(asOfLabel({ as_of: at(2026, 8, 30, 14, 5), stale: false }), null);
  assert.equal(asOfLabel({ stale: true }), null);
  assert.equal(asOfLabel({ stale: true, as_of: null }), null);
  assert.equal(asOfLabel({ stale: true, as_of: "x" }), null);
});

test("HH:MM today, with the date on another day", () => {
  const now = new Date(2026, 8, 30, 18, 0).getTime();
  assert.equal(asOfLabel({ stale: true, as_of: at(2026, 8, 30, 14, 5) }, now), "as of 14:05");
  assert.equal(asOfLabel({ stale: true, as_of: at(2026, 8, 29, 23, 59) }, now), "as of 29 Sep 23:59");
});

test("no forecast words, no punctuation noise", () => {
  const label = asOfLabel({ stale: true, as_of: at(2026, 8, 30, 9, 0) }, new Date(2026, 8, 30, 10).getTime());
  assert.match(label, /^as of \d\d:\d\d$/);
});

test("stalest picks the oldest stale body", () => {
  const a = { stale: true, as_of: 200 };
  const b = { stale: true, as_of: 100 };
  const c = { stale: false, as_of: 50 };
  assert.equal(stalest(a, b, c), b);
  assert.equal(stalest(c, null, undefined), null);
});
