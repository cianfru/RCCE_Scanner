import test from "node:test";
import assert from "node:assert/strict";
import { briefRows, crowdRead, fmtIn, medianGap, nextCloses, setupSide } from "./intel.js";

const side = (n, entry) => ({ n, usd: n * 1e5, median_entry: entry, in_profit: 0 });
const intel = (o = {}) => ({ mark: 1.0, profitable: { long: side(0, null), short: side(0, null) },
  large: { long: side(0, null), short: side(0, null) }, new_24h: { profitable: { long: 0, short: 0 } }, recent: [], ...o });

test("setup side follows the entry signal, else the pending regime", () => {
  assert.equal(setupSide({ signal: "LIGHT_LONG" }), "long");
  assert.equal(setupSide({ signal: "LIGHT_SHORT" }), "short");
  assert.equal(setupSide({ signal: "WAIT", regime_transition: { candidate: "MARKUP" } }), "long");
  assert.equal(setupSide({ signal: "WAIT" }), null);
});

test("crowd read: quiet, against, crowded, early, holding", () => {
  assert.equal(crowdRead("long", intel()).key, "quiet");
  assert.equal(crowdRead("long", intel({ profitable: { long: side(1, 1), short: side(3, 1) } })).key, "against");
  assert.equal(crowdRead("long", intel({ profitable: { long: side(8, 1), short: side(0, null) } })).key, "crowded");
  assert.equal(crowdRead("long", intel({ profitable: { long: side(3, 0.8), short: side(0, null) } })).key, "crowded"); // +25%
  assert.equal(crowdRead("long", intel({ profitable: { long: side(2, 0.98), short: side(0, null) },
    new_24h: { profitable: { long: 1, short: 0 } } })).key, "early");
  assert.equal(crowdRead("long", intel({ profitable: { long: side(2, 0.8), short: side(0, null) },
    new_24h: { profitable: { long: 1, short: 0 } } })).key, "holding");                                          // new, but far from price
  assert.equal(crowdRead("short", intel({ profitable: { long: side(0, null), short: side(3, 1.3) } })).key, "crowded"); // shorts 23% in
});

test("next closes are UTC-aligned", () => {
  const now = Date.UTC(2026, 8, 27, 14, 5);
  assert.deepEqual(nextCloses("4h", now, 2), [Date.UTC(2026, 8, 27, 16), Date.UTC(2026, 8, 27, 20)]);
  assert.deepEqual(nextCloses("1d", now), [Date.UTC(2026, 8, 28)]);
  assert.equal(fmtIn(115 * 60000), "1h 55m");
  assert.equal(fmtIn(26 * 3600000), "1d 2h");
});

test("drawer rows read like the focus panel", () => {
  const i = intel({ mark: 0.71, profitable: { long: side(4, 0.55), short: side(0, null) },
    new_24h: { profitable: { long: 2, short: 0 } }, recent: [{ t: 1e9, side: "long", cohort: "profitable", px: 0.67, usd: 1e5 }] });
  const row = { regime: "ACCUM", signal: "WAIT", timeframe: "4h", conditions_met: 5, conditions_total: 9,
    regime_transition: { candidate: "MARKUP", observed_bars: 3, required_bars: 5 } };
  const rows = briefRows(row, i, 1e9 * 1000 + 2 * 3600e3, { fmt: v => String(v) });
  const kv = Object.fromEntries(rows.map(r => [r.k, r.v]));
  assert.deepEqual(rows.map(r => r.k).slice(0, 4), ["Entry checks", "Crowd", "Their entry", "Candles to confirm"]);
  // Only the checks: regime and signal are the SetupPair capsule's, not repeated as a row.
  assert.equal(kv["Entry checks"], "5 of 9");
  assert.equal(rows[0].met, 5);
  assert.equal(rows[0].total, 9);
  assert.equal(kv.Crowd, "4 long · 0 short");
  assert.equal(rows[1].key, "crowded");                                     // 4 long, price 29% past their entry
  assert.equal(kv["Their entry"], "long 0.55 · +29% for them");
  assert.match(kv["Candles to confirm"], /^3 of 5 · last in /);
  // Short: the SetupPair above names the regime ("→ Uptrend") the odds are for.
  assert.equal(kv["Completion odds"], "81% completed from here");
  assert.match(kv["Next close"], /^4H in /);
  assert.equal(rows[rows.length - 1].k, "Next close");
  // No trader reading: checks and timing only; no checks row without a checks count.
  assert.deepEqual(briefRows({ regime: "MARKUP", signal: "STRONG_LONG", timeframe: "1d", conditions_met: 9, conditions_total: 11 }, null, 0,
    { fmt: String }).map(r => r.k), ["Entry checks", "Next close"]);
  assert.deepEqual(briefRows({ regime: "MARKUP", signal: "STRONG_LONG", timeframe: "1d" }, null, 0,
    { fmt: String }).map(r => r.k), ["Next close"]);
});

test("price against their median entry", () => {
  const row = { signal: "STRONG_LONG", price: 1 };
  assert.equal(medianGap(row, intel({ mark: 0.49, profitable: { long: side(1, 0.38), short: side(0, null) } })), "+29% above their median");
  assert.equal(medianGap(row, intel({ mark: 0.9, profitable: { long: side(1, 1), short: side(0, null) } })), "−10% below their median");
  assert.equal(medianGap(row, intel()), null);
  assert.equal(medianGap(row, null), null);
});
