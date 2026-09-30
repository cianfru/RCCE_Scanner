// The shared worker (public/shared-worker.js) is a classic script; it runs here in a
// sandbox with a fake fetch and fake ports.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SOURCE = readFileSync(new URL("../../public/shared-worker.js", import.meta.url), "utf8");

// A server that answers with an ETag and honours If-None-Match; `versions` bumps a feed.
function makeWorker() {
  const calls = [];
  const versions = {};
  const fetch = async (url, init = {}) => {
    const path = url.replace("http://api", "");
    const etag = `"${path}#${versions[path] || 0}"`;
    const sentTag = init.headers?.["If-None-Match"];
    calls.push({ path, conditional: !!sentTag });
    if (sentTag === etag) return { status: 304, ok: false, headers: { get: () => etag }, json: async () => { throw new Error("no body"); } };
    return { status: 200, ok: true, headers: { get: h => (h === "ETag" ? etag : null) },
      json: async () => ({ path, v: versions[path] || 0, results: [], cache_age_seconds: 12 }) };
  };
  const timers = [];
  const ctx = {
    self: {}, fetch, URLSearchParams, Promise, Date, Map, Set, Error,
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
  };
  vm.createContext(ctx);
  vm.runInContext(SOURCE, ctx);
  const tab = (hidden = false) => {
    const posted = [];
    const port = { postMessage: m => posted.push(m), start() {} };
    ctx.self.onconnect({ ports: [port] });
    const send = msg => port.onmessage({ data: msg });
    return { posted, send, main: () => posted.filter(m => m.type === "main-data") };
  };
  return { ctx, calls, versions, tab };
}

const settle = () => new Promise(r => setTimeout(r, 10));
const scanCalls = calls => calls.filter(c => c.path.startsWith("/api/scan"));

test("start loads every feed once, then polls only the timeframe on screen", async () => {
  const w = makeWorker();
  const t = w.tab();
  t.send({ type: "set-needs", needs: { scan: ["1d"], tradfi: false, sentiment: true } });
  t.send({ type: "connect", apiBase: "http://api" });
  await settle();
  const first = w.calls.map(c => c.path).sort();
  assert.deepEqual(first, ["/api/notifications/anomalies", "/api/notifications/exhaustion-opportunities",
    "/api/notifications/market-setups?min_score=3", "/api/notifications?limit=10",
    "/api/scan/sparklines?timeframe=1d", "/api/scan/sparklines?timeframe=4h",
    "/api/scan?timeframe=1d&view=list", "/api/scan?timeframe=4h&view=list", "/api/sentiment",
    "/api/tradfi?timeframe=1d", "/api/tradfi?timeframe=4h"]);
  const data = t.main().at(-1).payload;
  assert.ok(data.r4h && data.r1d && data.tradfi4h && data.tradfi1d && data.sentiment);
  assert.equal(data.cacheAge, 12);

  w.calls.length = 0;
  t.send({ type: "refresh" });
  await settle();
  assert.deepEqual(w.calls.map(c => c.path).sort(),
    ["/api/scan/sparklines?timeframe=1d", "/api/scan?timeframe=1d&view=list"]);   // sentiment waits 5 minutes
  assert.ok(w.calls.every(c => c.conditional));
});

test("an unchanged scan is a 304 and is not re-broadcast; a new one is", async () => {
  const w = makeWorker();
  const t = w.tab();
  t.send({ type: "set-needs", needs: { scan: ["1d"], tradfi: false, sentiment: false } });
  t.send({ type: "connect", apiBase: "http://api" });
  await settle();
  const before = t.main().length;
  t.send({ type: "refresh" });
  await settle();
  assert.equal(t.main().length, before);
  w.versions["/api/scan?timeframe=1d&view=list"] = 1;
  t.send({ type: "refresh" });
  await settle();
  assert.equal(t.main().length, before + 1);
  assert.equal(t.main().at(-1).payload.r1d.v, 1);
});

test("switching timeframe fetches the new one at once", async () => {
  const w = makeWorker();
  const t = w.tab();
  t.send({ type: "set-needs", needs: { scan: ["1d"], tradfi: false, sentiment: true } });
  t.send({ type: "connect", apiBase: "http://api" });
  await settle();
  w.calls.length = 0;
  t.send({ type: "set-needs", needs: { scan: ["4h"], tradfi: false, sentiment: true } });
  await settle();
  assert.deepEqual(scanCalls(w.calls).map(c => c.path).sort(),
    ["/api/scan/sparklines?timeframe=4h", "/api/scan?timeframe=4h&view=list"]);
  w.calls.length = 0;
  t.send({ type: "set-needs", needs: { scan: [], tradfi: true, sentiment: false } });   // TradFi page
  await settle();
  assert.deepEqual(w.calls.map(c => c.path).sort(), ["/api/tradfi?timeframe=1d", "/api/tradfi?timeframe=4h"]);
});

test("hidden tabs do not count; several refreshes fold into one follow-up", async () => {
  const w = makeWorker();
  const a = w.tab();
  const b = w.tab();
  a.send({ type: "set-needs", needs: { scan: ["1d"], tradfi: false, sentiment: false } });
  b.send({ type: "set-needs", needs: { scan: ["4h"], tradfi: false, sentiment: false } });
  a.send({ type: "connect", apiBase: "http://api" });
  b.send({ type: "connect", apiBase: "http://api" });
  await settle();
  b.send({ type: "visibility", hidden: true });
  w.calls.length = 0;
  a.send({ type: "refresh" });
  a.send({ type: "refresh" });
  a.send({ type: "refresh" });
  await settle();
  const scans = scanCalls(w.calls).map(c => c.path);
  assert.ok(scans.every(p => p.includes("timeframe=1d")));
  assert.ok(scans.length <= 4, `expected at most 2 polls, got ${scans.length / 2}`);
});

test("union and plan helpers", () => {
  const w = makeWorker();
  const { unionNeeds, planMainFetches } = w.ctx;
  const needs = unionNeeds(new Map([[1, { scan: ["1d"] }], [2, { scan: ["4h"], tradfi: true }]]), new Map([[1, true], [2, false]]));
  assert.deepEqual([...needs.scan], ["1d"]);
  assert.equal(needs.tradfi, false);
  // A tab that never said what it shows gets everything (older pages).
  const legacy = unionNeeds(new Map(), new Map([[1, true]]));
  assert.deepEqual([...legacy.scan].sort(), ["1d", "4h"]);
  const loaded = new Map([["scan:4h", 0], ["scan:1d", 0], ["tradfi:4h", 0], ["tradfi:1d", 0], ["sentiment", 0]]);
  assert.deepEqual([...planMainFetches({ scan: new Set(), tradfi: false, sentiment: true }, loaded, 299_999)], []);
  assert.deepEqual([...planMainFetches({ scan: new Set(), tradfi: false, sentiment: true }, loaded, 300_000)], ["sentiment"]);
});

// ── CDN path (backend/edge.py) ──────────────────────────────────────────────

function makeEdgeWorker({ enabled = true, edgeAnswers = "json" } = {}) {
  const calls = [];
  const json = body => ({ status: 200, ok: true,
    headers: { get: h => (h.toLowerCase() === "content-type" ? "application/json" : h === "ETag" ? '"e"' : null) },
    json: async () => body });
  const fetch = async (url, init = {}) => {
    calls.push({ url, auth: !!init.headers?.Authorization });
    if (url === "http://api/api/edge/key") {
      return json(enabled ? { enabled: true, prefix: "/edge", key: "K1", expires_at: 9e12 } : { enabled: false });
    }
    if (url.startsWith("/edge/") && edgeAnswers === "html") {
      return { status: 200, ok: true, headers: { get: h => (h.toLowerCase() === "content-type" ? "text/html" : null) },
        json: async () => { throw new Error("html"); } };
    }
    if (url.startsWith("/edge/") && edgeAnswers === "401") {
      return { status: 401, ok: false, headers: { get: () => "application/json" }, json: async () => ({}) };
    }
    if (url.includes("/api/scan/sparklines")) return json({ sparklines: { "BTC/USDT": [1, 2, 3] } });
    if (url.includes("/api/scan")) return json({ results: [{ symbol: "BTC/USDT", price: 1 }], as_of: 5, stale: false });
    return json({ results: [] });
  };
  const ctx = {
    self: {}, fetch, URLSearchParams, Promise, Date, Map, Set, Error,
    setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
  };
  vm.createContext(ctx);
  vm.runInContext(SOURCE, ctx);
  const posted = [];
  const port = { postMessage: m => posted.push(m), start() {} };
  ctx.self.onconnect({ ports: [port] });
  const send = msg => port.onmessage({ data: msg });
  return { calls, send, posted };
}

test("CDN feeds go through /edge with the key and no token; sparklines are merged back", async () => {
  const w = makeEdgeWorker();
  w.send({ type: "set-needs", needs: { scan: ["4h"], tradfi: false, sentiment: false } });
  w.send({ type: "connect", apiBase: "http://api", token: "T", edge: true });
  await settle();
  const scan = w.calls.find(c => c.url.startsWith("/edge/api/scan?timeframe=4h&view=list"));
  assert.ok(scan, "scan list through /edge");
  assert.ok(scan.url.endsWith("k=K1"));
  assert.equal(scan.auth, false);
  assert.ok(w.calls.some(c => c.url.startsWith("/edge/api/scan/sparklines?timeframe=4h")));
  assert.ok(w.calls.some(c => c.url === "http://api/api/sentiment" && c.auth), "other feeds stay direct");
  assert.ok(w.calls.some(c => c.url === "http://api/api/notifications?limit=10"), "notifications stay direct");
  const main = w.posted.filter(m => m.type === "main-data").at(-1).payload;
  assert.deepEqual(main.r4h.results[0].sparkline, [1, 2, 3]);

  // A scan notice's pass goes into the URL, so the CDN cannot answer with an older copy.
  w.calls.length = 0;
  w.send({ type: "refresh", version: 1234.5 });
  await settle();
  assert.ok(w.calls.some(c => c.url.startsWith("/edge/api/scan?timeframe=4h&view=list&v=1234.5&k=K1")));
});

test("the API switch off, a missing rewrite or a stale key fall back to direct calls", async () => {
  for (const opts of [{ enabled: false }, { edgeAnswers: "html" }, { edgeAnswers: "401" }]) {
    const w = makeEdgeWorker(opts);
    w.send({ type: "set-needs", needs: { scan: ["4h"], tradfi: false, sentiment: false } });
    w.send({ type: "connect", apiBase: "http://api", token: "T", edge: true });
    await settle();
    assert.ok(w.calls.some(c => c.url === "http://api/api/scan?timeframe=4h&view=list" && c.auth), JSON.stringify(opts));
    const main = w.posted.filter(m => m.type === "main-data").at(-1).payload;
    assert.equal(main.r4h.results[0].symbol, "BTC/USDT");
    assert.ok(!w.posted.some(m => m.type === "auth-expired"), "an edge 401 is not a logout");
  }
});

test("the page can keep the CDN off", async () => {
  const w = makeEdgeWorker();
  w.send({ type: "connect", apiBase: "http://api", token: "T", edge: false });
  await settle();
  assert.ok(!w.calls.some(c => c.url.startsWith("/edge/") || c.url.includes("/api/edge/key")));
});
