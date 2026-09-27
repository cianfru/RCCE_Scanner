import test from "node:test";
import assert from "node:assert/strict";
import { brief, crowdRead, fmtIn, nextCloses, setupSide } from "./intel.js";

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

test("brief reads plainly", () => {
  const i = intel({ mark: 0.71, profitable: { long: side(4, 0.68), short: side(0, null) },
    new_24h: { profitable: { long: 2, short: 0 } }, recent: [{ t: 1e9, side: "long", cohort: "profitable", px: 0.67, usd: 1e5 }] });
  const row = { regime: "ACCUM", signal: "WAIT", timeframe: "4h", conditions_met: 5, conditions_total: 9,
    regime_transition: { candidate: "MARKUP", observed_bars: 3, required_bars: 5 } };
  const lines = brief(row, i, 1e9 * 1000 + 2 * 3600e3, { regimeName: k => ({ ACCUM: "Accumulation", MARKUP: "Uptrend" })[k],
    signalLabel: () => "WAIT", fmt: v => String(v) });
  assert.match(lines[0], /^Accumulation on the 4H, no entry signal yet; 5 of 9/);
  assert.match(lines[1], /3 of 5 candles into a change to Uptrend: 2 more 4H closes decide it/);
  assert.match(lines[2], /4 long \(median entry 0.68, \+4% for them\), 0 short/);
  assert.match(lines[3], /2 opened long; the latest 2h ago at 0.67/);
  assert.match(lines[lines.length - 1], /^Next 4H close in /);
});
