import test from "node:test";
import assert from "node:assert/strict";
import { barIndex, placeSessions, ticks, valueArea, composite, spread, mergeTicks } from "./valueLayer.js";

const H4 = 14400, DAY = 86400;
const T0 = 1788739200;                                    // Monday 2026-09-07 00:00 UTC
const times = Array.from({ length: 15 }, (_, i) => T0 + i * H4);   // 2.5 days of 4h candles

test("a time sits on the first candle at or after it; past the last candle bars are counted on", () => {
  assert.equal(barIndex(times, T0, H4), 0);
  assert.equal(barIndex(times, T0 + DAY, H4), 6);
  assert.equal(barIndex(times, T0 + DAY + 1, H4), 7);
  assert.equal(barIndex(times, T0 + 3 * DAY, H4), 18);      // the running day ends 4 bars after the last candle
});

test("sessions get their span in candles; ones that ended before the chart are dropped", () => {
  const sessions = [
    { start: T0 - DAY, end: T0 }, { start: T0, end: T0 + DAY }, { start: T0 + 2 * DAY, end: T0 + 3 * DAY, live: true },
  ];
  assert.deepEqual(placeSessions(sessions, times, H4).map(s => [s.from, s.to]), [[0, 6], [12, 18]]);
  assert.deepEqual(placeSessions(sessions, [], H4), []);
});

test("ticks: the levels, the previous outer session's value area and older untouched POCs", () => {
  const body = {
    outer_period: "week", levels: { d_open: 100, pd_high: 110, pd_low: 90, w_open: 95 },
    outer: [
      { start: 1, poc: 70, vah: 75, val: 65, live: false, touched: null },
      { start: 2, poc: 80, vah: 85, val: 78, live: false, touched: 5 },
      { start: 3, poc: 99, vah: 104, val: 96, live: false, touched: null },
      { start: 4, poc: 101, vah: 102, val: 100, live: true, touched: null },
    ],
  };
  assert.deepEqual(ticks(body).map(t => `${t.label} ${t.price}`),
    ["D open 100", "PDH 110", "PDL 90", "W open 95", "PW VAH 104", "PW POC 99", "PW VAL 96", "W nPOC 70"]);
  assert.deepEqual(ticks({ outer_period: "month", levels: { pw_high: 9 }, outer: [{ poc: 5, vah: 6, val: 4, live: false }] }).map(t => t.label),
    ["PWH", "PM VAH", "PM POC", "PM VAL"]);
  assert.deepEqual(ticks(null), []);
});

test("the first hour's high and low are ticks on the 1-hour chart only", () => {
  const body = { outer_period: "week", levels: { d_open: 100, ib_high: 103, ib_low: 98 }, outer: [] };
  assert.deepEqual(ticks(body).map(t => t.label), ["D open"]);
  assert.deepEqual(ticks(body, { firstHour: true }).map(t => `${t.label} ${t.price}`), ["D open 100", "IB high 103", "IB low 98"]);
});

test("no forecast words in the tick labels", () => {
  const labels = ticks({ outer_period: "week", levels: { d_open: 1, pd_high: 1, pd_low: 1, w_open: 1, m_open: 1, pw_high: 1, pw_low: 1 },
    outer: [{ poc: 1, vah: 1, val: 1, live: false, touched: null }, { poc: 1, vah: 1, val: 1, live: false }] }).map(t => t.label).join(" ");
  assert.doesNotMatch(labels, /\b(will|expect|likely|predict|target|probability|odds)\b/i);
});

test("value area: two rows at a time towards more volume, the same rule as the server", () => {
  assert.deepEqual(valueArea([1, 1, 5, 9, 20, 9, 8, 8, 1, 1]), { poc: 4, lo: 2, hi: 6, max: 20 });
  assert.equal(valueArea([7, 1, 1, 7, 1, 1, 1]).poc, 3);    // a tie goes to the row nearest the middle
  assert.equal(valueArea([0, 0, 0]), null);
});

test("the profile in view adds the sessions overlapping the visible candles", () => {
  const placed = [
    { from: 0, to: 6, bins: { from: 2, v: [10, 30] } },
    { from: 6, to: 12, bins: { from: 3, v: [5, 50, 5] } },
    { from: 12, to: 18, bins: { from: 0, v: [99] } },
  ];
  const p = composite(placed, 6, 0, 11.5);
  assert.deepEqual(p.v, [0, 0, 10, 35, 50, 5]);
  assert.equal(p.poc, 4);
  assert.equal(composite(placed, 6, 14, 20).poc, 0);
  assert.equal(composite(placed, 6, 30, 40), null);
});

test("labels that would overlap are pushed down, the rest stay put", () => {
  assert.deepEqual(spread([10, 14, 40, 45, 46], 12), [10, 22, 40, 52, 64]);
  assert.deepEqual(spread([], 12), []);
});

test("ticks at one price share a label, and a word they end in", () => {
  const rows = [{ label: "W open", y: 100.4, kind: "level" }, { label: "PDH", y: 60, kind: "level" }, { label: "D open", y: 100, kind: "level" },
    { label: "M open", y: 100.9, kind: "level" }, { label: "PW POC", y: 101.2, kind: "poc" }, { label: "PDL", y: 140, kind: "level" }];
  assert.deepEqual(mergeTicks(rows).map(t => [t.label, t.y, t.kind]),
    [["PDH", 60, "level"], ["D \u00b7 W \u00b7 M open \u00b7 PW POC", 100, "poc"], ["PDL", 140, "level"]]);
});
