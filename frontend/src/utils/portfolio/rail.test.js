import test from "node:test";
import assert from "node:assert/strict";
import { railDomain, railModel, placeLabels, GLYPHS, TRADERS_LIFTED } from "./rail.js";

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

test("labels: mark price > Liq > SL, a lower one dropped when it would overlap", () => {
  const band = [11, 20];
  const T = (kind, x, prio, extra = {}) => ({ kind, x, w: 16, text: kind, size: 11, band, prio, anchors: ["middle"], ...extra });
  assert.deepEqual(placeLabels([T("sl", 110, 2), T("liq", 105, 1), T("mark", 100, 0, { band: [-20, -10], keep: true })], [], { width: W }).map(l => l.kind), ["mark", "liq"]);
  assert.deepEqual(placeLabels([T("liq", 20, 1), T("sl", 200, 2)], [], { width: W }).map(l => l.kind), ["liq", "sl"]);
  // A text never leaves the rail: shifted back inside, or dropped when fixed.
  assert.equal(placeLabels([T("liq", 2, 1)], [], { width: W })[0].x0, 0);
  assert.deepEqual(placeLabels([T("tpMore", W - 4, 3, { fixed: true, anchors: ["start"] })], [], { width: W }), []);
  const m = railModel({ isLong: true, mark: 100, entry: 99, liq: 99.5, stops: [{ px: 99.8 }], width: W, text: { mark: "100" } });
  assert.equal(m.labels[0].kind, "mark");
});

test("labels: the mark price moves off a take-profit glyph; +n drops on a collision", () => {
  // NEAR: the take-profit sits a few px right of the mark, under the centred price.
  const m = railModel({ isLong: true, mark: 4.4922, entry: 4.53, tps: [{ px: 4.497 }, { px: 4.6 }], width: W, text: { mark: "4.4922" } });
  const mark = m.labels.find(l => l.kind === "mark");
  assert.ok(mark.x0 + mark.w <= m.m.tp - 3.5, "price ends left of the take-profit glyph");
  const more = m.labels.find(l => l.kind === "tpMore");
  if (more) assert.ok(more.x0 >= m.m.tp + 3.5 || more.x0 + more.w <= m.m.tp - 3.5);
  // BTC: a stop just under the mark with two more further out reads "SL +2" as one label under the
  // track, clear of the stop, entry and mark glyphs (they sit above y = 11), and of every other label.
  const b = railModel({ isLong: true, mark: 80221, entry: 80400, stops: [{ px: 80150 }, { px: 79000 }, { px: 78000 }], width: W, text: { mark: "80,221" } });
  const sl = b.labels.find(l => l.kind === "sl");
  assert.equal(sl.text, "SL +2");
  assert.equal(b.labels.find(l => l.kind === "slMore"), undefined);
  assert.ok(sl.x0 <= b.m.stop + 3.5 && sl.x0 + sl.w >= b.m.stop - 3.5, "under its stop glyph");
  const band = l => (l.kind === "mark" ? [-20, -10] : l.kind === "tpMore" ? [-13, -5] : [11, 20]);
  for (const p of b.labels) for (const q of b.labels) {
    if (p === q) continue;
    const overlap = p.x0 < q.x0 + q.w && q.x0 < p.x0 + p.w && band(p)[0] < band(q)[1] && band(q)[0] < band(p)[1];
    assert.ok(!overlap, `${p.kind} overlaps ${q.kind}`);
  }
  // On a phone card (compact) there is no SL text at all.
  const c = railModel({ isLong: true, mark: 80221, entry: 80400, stops: [{ px: 80150 }, { px: 79000 }], width: 340, compact: true, text: { mark: "80,221" } });
  assert.equal(c.labels.find(l => l.kind === "sl"), undefined);
});

test("labels: XMR (live data): the mark price ends left of a take-profit just right of the mark", () => {
  const x = railModel({ isLong: true, mark: 610.8, entry: 606.6, tps: [{ px: 612.1 }, { px: 640 }], band: { lo: 520, hi: 545 }, width: 591, text: { mark: "610.8" } });
  const mk = x.labels.find(l => l.kind === "mark");
  assert.ok(x.m.tp - x.m.mark > 4 && x.m.tp - x.m.mark < 12, `tp ${x.m.tp - x.m.mark} px right of the mark`);
  assert.ok(mk.x0 + mk.w <= x.m.tp - 3.5, "the price clears the take-profit glyph");
  assert.ok(Math.abs(mk.x0 + mk.w - x.m.mark) < 1e-9, "anchored at its end on the mark");
});

test("labels: the traders' diamond blocks a +n; Liq clears a broken axis", () => {
  const m = railModel({ isLong: true, mark: 100, entry: 99, tps: [{ px: 103 }, { px: 110 }], tradersEntry: 103.2, width: W, text: { mark: "100" } });
  assert.equal(m.labels.find(l => l.kind === "tpMore"), undefined);
  const far = railModel({ isLong: true, mark: 100, entry: 98, liq: 40, width: 340, compact: true, text: { mark: "100" } });
  const liq = far.labels.find(l => l.kind === "liq");
  assert.ok(liq && liq.x0 + liq.w < far.breakX - 5.5);
  // Phone: no Liq label when the break sits within 24 px of the edge.
  const narrow = railModel({ isLong: true, mark: 100, entry: 98, liq: 40, width: 200, compact: true, text: { mark: "100" } });
  assert.equal(narrow.labels.find(l => l.kind === "liq"), undefined);
});

test("the last visit's mark: drawn only inside the domain", () => {
  assert.ok(railModel({ isLong: true, mark: 100, entry: 99, visitMark: 99.5, width: W }).m.visit > 0);
  assert.equal(railModel({ isLong: true, mark: 100, entry: 99, visitMark: 60, width: W }).m.visit, null);
});

test("extra stops and take-profits are counted, the nearest is drawn", () => {
  const m = railModel({ isLong: true, mark: 100, entry: 99, stops: [{ px: 97 }, { px: 95 }, { px: 90 }], tps: [{ px: 104 }, { px: 108 }], width: W });
  assert.equal(m.moreStops, 2);
  assert.equal(m.moreTps, 1);
  assert.ok(m.m.stop < m.m.mark && m.m.tp > m.m.mark);
});

// Design review (phone NEAR card): the traders' diamond on the take-profit triangle rises one step.
test("the traders' diamond never sits on the take-profit triangle", () => {
  const base = { isLong: true, mark: 4.3, entry: 4.2, tps: [{ px: 4.6 }], width: 300, compact: true };
  const on = railModel({ ...base, tradersEntry: 4.601 });
  assert.deepEqual(on.tradersBand, TRADERS_LIFTED);
  const [ty0, ty1] = GLYPHS.tp;
  assert.ok(on.tradersBand[1] <= ty0, "lifted clear of the triangle");
  const off = railModel({ ...base, tradersEntry: 4.25 });
  assert.deepEqual(off.tradersBand, GLYPHS.traders);
  assert.ok(ty1 > ty0);
});
