import test from "node:test";
import assert from "node:assert/strict";
import { createKeyedCache } from "./keyedCache.js";

// A fake clock with manual timers.
function rig({ refresh = true, fail = () => false } = {}) {
  let t = 1_000_000, id = 0, hidden = false;
  const timers = new Map(), calls = [];
  const cache = createKeyedCache({
    ttl: 300_000,
    refresh,
    now: () => t,
    isHidden: () => hidden,
    setTimer: (fn, ms) => { timers.set(++id, { fn, at: t + ms }); return id; },
    clearTimer: k => timers.delete(k),
    fetcher: async key => {
      calls.push(key);
      if (fail(key, calls.length)) throw new Error("HTTP 500");
      return { key, n: calls.length };
    },
  });
  const flush = () => new Promise(r => setImmediate(r));
  const advance = async ms => {
    t += ms;
    for (const [k, x] of [...timers].sort((a, b) => a[1].at - b[1].at)) {
      if (x.at <= t && timers.has(k)) { timers.delete(k); x.fn(); await flush(); }
    }
    await flush();
  };
  return { cache, calls, timers, flush, advance, setHidden: v => { hidden = v; } };
}

test("concurrent loads share one request", async () => {
  const { cache, calls } = rig();
  const [a, b] = await Promise.all([cache.load("1d"), cache.load("1d")]);
  assert.equal(calls.length, 1);
  assert.equal(a, b);
});

test("data younger than the ttl is served from the cache; force reloads", async () => {
  const { cache, calls, advance } = rig({ refresh: false });
  await cache.load("1d");
  await advance(299_000);
  await cache.load("1d");
  assert.equal(calls.length, 1);
  await advance(1_000);
  await cache.load("1d");
  assert.equal(calls.length, 2);
  await cache.load("1d", { force: true });
  assert.equal(calls.length, 3);
});

test("keys are cached separately", async () => {
  const { cache, calls } = rig();
  await cache.load("1d");
  await cache.load("4h");
  await cache.load("1d");
  assert.deepEqual(calls, ["1d", "4h"]);
});

test("remounting subscribers within the ttl makes no new request", async () => {
  const { cache, calls, flush, advance } = rig();
  let un = cache.subscribe("1d", () => {});
  await flush();
  assert.equal(calls.length, 1);
  await advance(15_000);
  un();
  un = cache.subscribe("1d", () => {});           // navigate away and back
  const un2 = cache.subscribe("1d", () => {});    // a second consumer
  await flush();
  await advance(100_000);
  un(); un2();
  cache.subscribe("1d", () => {});
  await flush();
  assert.equal(calls.length, 1);
});

test("the refresh timer reloads every ttl while subscribed, anchored to the data's age", async () => {
  const { cache, calls, flush, advance, timers } = rig();
  let un = cache.subscribe("1d", () => {});
  await flush();
  await advance(200_000);
  un();
  assert.equal(timers.size, 0, "no timer without subscribers");
  un = cache.subscribe("1d", () => {});
  await flush();
  assert.equal(calls.length, 1);
  await advance(100_000);                 // 300s after the first read
  assert.equal(calls.length, 2);
  await advance(299_000);
  assert.equal(calls.length, 2);
  await advance(1_000);
  assert.equal(calls.length, 3);
  un();
  await advance(900_000);
  assert.equal(calls.length, 3, "stops when the last subscriber leaves");
});

test("no reload while the page is hidden; resume() reloads stale keys", async () => {
  const { cache, calls, flush, advance, setHidden } = rig();
  cache.subscribe("1d", () => {});
  await flush();
  setHidden(true);
  await advance(900_000);
  assert.equal(calls.length, 1);
  setHidden(false);
  cache.resume();
  await flush();
  assert.equal(calls.length, 2);
  await advance(300_000);
  assert.equal(calls.length, 3, "the timer is back after resume");
});

test("snapshots are stable and change on load start and end", async () => {
  const { cache, flush } = rig();
  const s0 = cache.get("1d");
  assert.equal(s0.data, undefined);
  assert.equal(cache.get("1d"), s0);
  let seen = 0;
  cache.subscribe("1d", () => { seen++; });
  const loading = cache.get("1d");
  assert.equal(loading.loading, true);
  await flush();
  const done = cache.get("1d");
  assert.equal(done.loading, false);
  assert.deepEqual(done.data, { key: "1d", n: 1 });
  assert.equal(cache.get("1d"), done);
  assert.equal(seen, 2);
});

test("a failed read keeps the last data and records the error", async () => {
  const { cache, calls } = rig({ refresh: false, fail: (k, n) => n === 2 });
  await cache.load("1d");
  await cache.load("1d", { force: true });
  assert.equal(calls.length, 2);
  assert.deepEqual(cache.get("1d").data, { key: "1d", n: 1 });
  assert.match(String(cache.get("1d").error), /HTTP 500/);
  await cache.load("1d", { force: true });
  assert.equal(cache.get("1d").error, null);
});
