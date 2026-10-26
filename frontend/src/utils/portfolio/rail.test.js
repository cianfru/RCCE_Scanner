import test from "node:test";
import assert from "node:assert/strict";
import { railDomain, railModel, placeLabels } from "./rail.js";

const W = 400;

test("domain: the near set, at least ±2% around the mark, padded 8% of the log span", () => {
  const d = railDomain({ mark: 100, entry: 101 });
  assert.ok(d.lo < 100 / 1.02 && d.hi > 102);
  const s = Math.log(102 / (100 / 1.02));
  assert.ok(Math.abs(Math.log(d.hi) - Math.log(102) - 0.08 * s) < 1e-12);
  const wide = railDomain({ mark: 100, entry: 80, band: { lo: 70, hi: 75 }, trend: 90, tradersEntry: 110 });
  assert.ok(wide.lo < 70 && wide.hi > 110);
  assert.equal(wide.brk, null);
});

test("liquidation joins the domain within 1.5x the span, otherwise the axis breaks at the costly end", () => {
  // Near set 90..102 (log span 0.125); with liq 85 the span is 0.182, within 1.5x.
  const near = railDomain({ mark: 100, entry: 90, liq: 85 });
  assert.equal(near.brk, null);
  assert.ok(near.lo < 85);
  assert.equal(railDomain({ mark: 100, entry: 90, liq: 80 }).brk, "left");     // 0.243: past 1.5x
  const far = railDomain({ mark: 100, entry: 98, liq: 40 });
  assert.equal(far.brk, "left");
  assert.ok(far.lo > 40);
  const short = railDomain({ mark: 100, entry: 102, liq: 180 });
  assert.equal(short.brk, "right");
});

test("broken axis: 10% kept, liq tick 4% from the edge, break strokes at 9%", () => {
  const m = railModel({ isLong: true, mark: 100, entry: 98, liq: 40, width: W });
  assert.equal(m.domain.brk, "left");
  assert.equal(m.m.liq, 0.04 * W);
  assert.equal(m.breakX, 0.09 * W);
  assert.ok(m.m.entry >= 0.10 * W && m.m.mark > m.m.entry);
  const s = railModel({ isLong: false, mark: 100, entry: 102, liq: 180, width: W });
  assert.equal(s.m.liq, 0.96 * W);
  assert.equal(s.breakX, 0.91 * W);
  assert.ok(s.m.entry <= 0.90 * W);
});

test("both sides keep the natural axis: higher prices sit further right", () => {
  for (const isLong of [true, false]) {
    const m = railModel({ isLong, mark: 100, entry: isLong ? 95 : 105, liq: isLong ? 85 : 115, stops: [{ px: isLong ? 92 : 108 }], width: W });
    const xs = isLong ? [m.m.liq, m.m.stop, m.m.entry, m.m.mark] : [m.m.mark, m.m.entry, m.m.stop, m.m.liq];
    for (let i = 1; i < xs.length; i++) assert.ok(xs[i] > xs[i - 1], `${isLong ? "long" : "short"} order at ${i}`);
  }
});

test("hatch runs from the liquidation tick to the costly edge", () => {
  const l = railModel({ isLong: true, mark: 100, entry: 95, liq: 85, width: W });
  assert.equal(l.hatch.x0, 0);
  assert.equal(l.hatch.x1, l.m.liq);
  const s = railModel({ isLong: false, mark: 100, entry: 105, liq: 115, width: W });
  assert.equal(s.hatch.x0, s.m.liq);
  assert.equal(s.hatch.x1, W);
  assert.equal(railModel({ isLong: true, mark: 100, entry: 95, width: W }).hatch, null);
});

test("labels: mark price > Liq > SL, the lowest dropped within 28 px, at most three", () => {
  assert.deepEqual(placeLabels([{ kind: "sl", x: 110, prio: 2 }, { kind: "mark", x: 100, prio: 0 }, { kind: "liq", x: 20, prio: 1 }]).map(l => l.kind), ["mark", "liq"]);
  assert.deepEqual(placeLabels([{ kind: "mark", x: 300, prio: 0 }, { kind: "liq", x: 20, prio: 1 }, { kind: "sl", x: 40, prio: 2 }]).map(l => l.kind), ["mark", "liq"]);
  assert.deepEqual(placeLabels([{ kind: "mark", x: 300, prio: 0 }, { kind: "liq", x: 20, prio: 1 }, { kind: "sl", x: 200, prio: 2 }]).map(l => l.kind), ["mark", "liq", "sl"]);
  const m = railModel({ isLong: true, mark: 100, entry: 99, liq: 99.5, stops: [{ px: 99.8 }], width: W });
  assert.equal(m.labels[0].kind, "mark");
  assert.ok(m.labels.length <= 3);
});

test("extra stops and take-profits are counted, the nearest is drawn", () => {
  const m = railModel({ isLong: true, mark: 100, entry: 99, stops: [{ px: 97 }, { px: 95 }, { px: 90 }], tps: [{ px: 104 }, { px: 108 }], width: W });
  assert.equal(m.moreStops, 2);
  assert.equal(m.moreTps, 1);
  assert.ok(m.m.stop < m.m.mark && m.m.tp > m.m.mark);
});
