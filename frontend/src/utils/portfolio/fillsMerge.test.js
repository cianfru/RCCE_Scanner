import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { mergeWindow, nextStart, trimWindow, mergeFunding } from "./fillsMerge.js";

const fills = JSON.parse(readFileSync(new URL("./__fixtures__/fills.json", import.meta.url), "utf8"));
const key = f => `${f.tid}|${f.time}|${f.sz}`;

test("window replace at the inclusive boundary loses and duplicates nothing", () => {
  const all = [...fills].sort((a, b) => a.time - b.time);
  const cut = Math.floor(all.length * 0.7);
  const cached = all.slice(0, cut);
  const start = nextStart(cached);
  assert.equal(start, all[cut - 1].time);
  // Hyperliquid answers from startTime inclusive: the boundary fills come back again.
  const incoming = all.filter(f => f.time >= start);
  const merged = mergeWindow(cached, incoming, start);
  assert.equal(merged.length, all.length);
  assert.deepEqual(merged.map(key).sort(), all.map(key).sort());
  assert.equal(new Set(merged.map(key)).size, merged.length);
});

test("fills sharing the boundary millisecond are all kept once", () => {
  const t = 1_000_000;
  const cached = [{ tid: 1, time: t - 5, sz: "1" }, { tid: 2, time: t, sz: "1" }];
  const incoming = [{ tid: 2, time: t, sz: "1" }, { tid: 3, time: t, sz: "2" }, { tid: 4, time: t + 9, sz: "1" }];
  const m = mergeWindow(cached, incoming, t);
  assert.deepEqual(m.map(f => f.tid), [1, 2, 3, 4]);
});

test("an aggregated fill that grew since the last read is replaced, not added twice", () => {
  const t = 2_000_000;
  const cached = [{ tid: 7, time: t, sz: "1" }];
  const m = mergeWindow(cached, [{ tid: 7, time: t, sz: "3" }], t);
  assert.equal(m.length, 1);
  assert.equal(m[0].sz, "3");
});

test("first read 30 days back; the cache is trimmed to 30 days; funding merges the same way", () => {
  const now = 100 * 86400_000;
  assert.equal(nextStart([], now), now - 30 * 86400_000);
  assert.deepEqual(trimWindow([{ time: now - 31 * 86400_000 }, { time: now - 29 * 86400_000 }], now).length, 1);
  const f = mergeFunding([{ time: 1, delta: { coin: "A" } }, { time: 5, delta: { coin: "A" } }], [{ time: 5, delta: { coin: "A" } }, { time: 5, delta: { coin: "B" } }], 5);
  assert.deepEqual(f.map(x => `${x.time}${x.delta.coin}`), ["1A", "5A", "5B"]);
});
