import test from "node:test";
import assert from "node:assert/strict";
import { CYCOPY, marketCycles, shareBelow } from "./marketCycles.js";

// Days 0-9 at 60% (a run under way on the first day), 10-19 at 30% (a downturn of 10 days), 20-29 at 60% (a run of
// 10 days), then 30% from day 30.
const series = (lastDay, tail = []) => {
  const rows = [];
  for (let d = 0; d <= lastDay; d++) {
    const v = d < 10 ? 0.6 : d < 20 ? 0.3 : d < 30 ? 0.6 : 0.3;
    rows.push({ day: d, uptrend: v, btc: 100 + d });
  }
  for (const [day, v] of tail) rows.push({ day, uptrend: v, btc: 100 + day });
  return rows;
};

test("in a downturn: past downturns with their lengths, today's counted from day 1", () => {
  const c = marketCycles(series(36));
  assert.equal(c.kind, "down");
  assert.equal(c.today.start, 30);
  assert.equal(c.today.days, 7, "days 30 to 36, today included");
  assert.equal(c.today.path[0].d, 1);
  assert.equal(c.past.length, 1);
  assert.deepEqual([c.past[0].start, c.past[0].end, c.past[0].days], [10, 20, 10]);
  assert.equal(c.past[0].path.at(-1).d, 11, "the path runs to the day it ended (back at 55%)");
  assert.equal(c.past[0].low, 0.3);
  assert.equal(c.past[0].btc, 120 / 110 - 1);
  assert.equal(c.sooner, 0, "the 10-day downturn lasted longer than today's 7 days");
});

test("sooner counts the past ones shorter than today's, on one scale", () => {
  const c = marketCycles(series(41));
  assert.equal(c.today.days, 12);
  assert.equal(c.sooner, 1);
  assert.deepEqual(CYCOPY.sooner(c.sooner, c.past.length, c.kind), "1 of 1 ended sooner");
});

test("in a broad uptrend: past uptrends (not the one under way on the first day)", () => {
  const tail = [];
  for (let d = 37; d <= 45; d++) tail.push([d, 0.7]);
  const c = marketCycles(series(36, tail));
  assert.equal(c.kind, "up");
  assert.equal(c.today.start, 37);
  assert.equal(c.today.days, 9);
  assert.deepEqual(c.past.map(p => [p.start, p.end, p.days]), [[20, 30, 10]]);
  assert.equal(c.past[0].high, 0.6);
});

test("no rows, or a first day inside no phase: nothing", () => {
  assert.equal(marketCycles([]), null);
  assert.equal(marketCycles([{ day: 0, uptrend: 0.3 }, { day: 1, uptrend: 0.3 }]), null);
});

test("shareBelow: the share of values strictly under v", () => {
  assert.equal(shareBelow([1, 2, 3, 4], 3), 0.5);
  assert.equal(shareBelow([1, null, 3], 2), 0.5);
  assert.equal(shareBelow([], 1), null);
});

test("copy: no forecast words", () => {
  const words = [...CYCOPY.pop("down"), ...CYCOPY.pop("up"), CYCOPY.head("down"), CYCOPY.head("up"), CYCOPY.lasted,
    ...CYCOPY.tip({ start: 0, end: 10, days: 10, low: 0.1, high: 0.8, btc: -0.2 }, "down", d => `${d}`)].join(" ");
  assert.doesNotMatch(words, /\b(will|expect|likely|predict|target|probability|odds)\b/i);
});
