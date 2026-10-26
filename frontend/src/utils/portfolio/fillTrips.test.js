// The Python cases of backend/tests/test_trader_profile.py, ported.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { classifyFills, roundTrips, isPerpFill, thinMarks } from "./fillTrips.js";

const close = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

function fill(t, side, px, sz, start = null, { coin = "ETH", pnl = 0, fee = 0, d = null, twap = false } = {}) {
  const f = { coin, time: Math.round(t * 1000), side, px: String(px), sz: String(sz),
    dir: d || (side === "B" ? "Open Long" : "Close Long"), closedPnl: String(pnl), fee: String(fee), twap };
  if (start != null) f.startPosition = String(start);
  return f;
}

// open 10 @100, add 5 @110, trim 5 @120, close 10 @130; open 4 @125, flip to short 6 @120, close @110
const SEQ = [
  fill(0, "B", 100, 10, 0, { fee: 1 }),
  fill(60, "B", 110, 5, 10, { fee: 1 }),
  fill(120, "A", 120, 5, 15, { pnl: 83.33, fee: 1 }),
  fill(180, "A", 130, 10, 10, { pnl: 266.67, fee: 1 }),
  fill(240, "B", 125, 4, 0, { fee: 1 }),
  fill(300, "A", 120, 10, 4, { pnl: -20, fee: 2.5, d: "Long > Short" }),
  fill(360, "B", 110, 6, -6, { pnl: 60, fee: 1, d: "Close Short" }),
];

test("fill classification: open, add, trim, close, flip", () => {
  const cl = classifyFills(SEQ);
  assert.deepEqual(cl.map(f => f.kind), ["open", "add", "trim", "close", "open", "flip", "close"]);
  assert.deepEqual(cl.map(f => f.side), ["long", "long", "long", "long", "long", "short", "short"]);
  assert.deepEqual(cl.map(f => f.after), [10, 15, 10, 0, 4, -6, 0]);
  assert.equal(cl[0].avgEntry, 100);
  close(cl[1].avgEntry, (100 * 10 + 110 * 5) / 15);
  close(cl[2].avgEntry, (100 * 10 + 110 * 5) / 15);          // a trim keeps the average
  assert.equal(cl[3].avgEntry, null);
  assert.equal(cl[5].avgEntry, 120);                          // flat, then the flip's price
  close(cl[2].pnl, 82.33);                                    // closed PnL net of the fee
});

test("without startPosition the running size is used", () => {
  const seq = SEQ.map(f => { const { startPosition, ...rest } = f; return rest; });
  assert.deepEqual(classifyFills(seq).map(f => f.kind), ["open", "add", "trim", "close", "open", "flip", "close"]);
});

test("same-millisecond fills chain; spot, repeated TWAP slices and builder fills are left out", () => {
  const seq = [
    fill(0, "B", 1, 5, 0), fill(10, "A", 1, 2, 2), fill(10, "A", 1, 3, 5),
    fill(10, "A", 1, 3, 5, { twap: true }),
    fill(5, "B", 1, 1, 0, { coin: "@107", d: "Buy" }), fill(5, "B", 1, 1, 0, { coin: "xyz:TSLA" }),
  ];
  assert.deepEqual(classifyFills(seq).map(f => [f.kind, f.after]), [["open", 5], ["trim", 2], ["close", 0]]);
  // The page reads builder-dex fills too (includeDex).
  assert.equal(classifyFills(seq, { includeDex: true }).filter(f => f.coin === "xyz:TSLA").length, 1);
  assert.equal(isPerpFill({ coin: "@107", dir: "Buy" }, { includeDex: true }), false);
});

test("round trips", () => {
  const { closed, open } = roundTrips(classifyFills(SEQ));
  assert.deepEqual(closed.map(t => [t.side, t.openedAt, t.closedAt]), [["short", 300, 360], ["long", 240, 300], ["long", 0, 180]]);
  const first = closed.at(-1);
  close(first.entryPx, (100 * 10 + 110 * 5) / 15);
  close(first.exitPx, (120 * 5 + 130 * 10) / 15);
  close(first.pnl, 83.33 + 266.67 - 4);
  assert.equal(first.adds, 1); assert.equal(first.trims, 1); assert.equal(first.fills, 4); assert.equal(first.peakSize, 15);
  close(closed[1].pnl, -20 - 1 - 1);                           // its open fee, and 4/10 of the flip's fee
  close(closed[0].pnl, 60 - 1 - 1.5);                          // 6/10 of the flip's fee, the close's fee
  assert.deepEqual(open, {});
  close(closed[1].fees, 1 + 1);
  close(closed[0].fees, 1.5 + 1);
});

test("a position opened before the fills on hand is partial", () => {
  const seq = [fill(0, "A", 10, 5, 8, { pnl: 5 }), fill(60, "A", 11, 3, 3, { pnl: 6 }), fill(120, "B", 9, 2, 0)];
  const trips = roundTrips(classifyFills(seq));
  assert.ok(trips.closed[0].partial);
  assert.equal(trips.closed[0].entryPx, null);
  assert.equal(trips.open.ETH.openedAt, 120);
});

test("busy books: adds and trims net per bucket, opens and closes stay", () => {
  const marks = [{ index: 0, kind: "open", side: "long", sz: 1, px: 10, usd: 10, n: 1 }];
  for (let i = 1; i <= 200; i++) marks.push({ index: i, kind: i % 2 ? "add" : "trim", side: "long", sz: i % 2 ? 2 : 1, px: 10, usd: 10, n: 1 });
  marks.push({ index: 201, kind: "close", side: "long", sz: 101, px: 11, usd: 1111, n: 1 });
  const out = thinMarks(marks, 40);
  assert.ok(out.length <= 42);
  assert.equal(out[0].kind, "open");
  assert.equal(out.at(-1).kind, "close");
  const net = out.filter(m => m.kind === "add").reduce((s, m) => s + m.sz, 0) - out.filter(m => m.kind === "trim").reduce((s, m) => s + m.sz, 0);
  assert.ok(Math.abs(net - 100) < 1e-9);                       // 100 adds of 2 and 100 trims of 1
  assert.ok(out.filter(m => m.kind === "add").every(m => m.buy === true));
  assert.deepEqual(thinMarks(marks.slice(0, 5), 40), marks.slice(0, 5));
});

test("real fills: every open position has a trip, sizes chain without drift", () => {
  const fills = JSON.parse(readFileSync(new URL("./__fixtures__/fills.json", import.meta.url), "utf8"));
  const cl = classifyFills(fills, { includeDex: true });
  assert.ok(cl.length > 100);
  for (const f of cl) assert.ok(Number.isFinite(f.after) && Number.isFinite(f.before));
  const { open } = roundTrips(cl);
  assert.ok(Object.keys(open).length > 0);
});
