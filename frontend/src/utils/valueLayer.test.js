import test from "node:test";
import assert from "node:assert/strict";
import { barIndex, placeSessions, ticks, valueArea, composite, spread, mergeTicks, fibBands, fibTicks, FIB_LABEL, describe, describeAll, distanceNote, rangeNote } from "./valueLayer.js";

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
  assert.deepEqual(mergeTicks(rows)[1].members.map(t => t.label), ["D open", "W open", "M open", "PW POC"]);   // each is still told apart
});

test("retracement bands: where they start, the leg they measure, and whether a point of control sits in them", () => {
  const body = {
    fib: [{ direction: 1, base_time: T0 + DAY, base: 100, extreme_time: T0 + 2 * DAY, extreme: 160, from: 122.92, to: 120.4, touched: false },
      { direction: -1, base_time: T0 - 9 * DAY, base: 160, extreme_time: T0 + DAY, extreme: 100, from: 137.08, to: 139.6, touched: true }],
    outer: [{ poc: 139, live: false, touched: 5 }, { poc: 50, live: false, touched: 7 }, { poc: 200, live: true }],
    sessions: [{ poc: 121, live: false, touched: null }, { poc: 138, live: false, touched: 9 }],
  };
  const bands = fibBands(body, times, H4);
  assert.deepEqual(bands.map(b => [b.top, b.bottom, b.from, b.touched, b.poc]),
    [[122.92, 120.4, 6, false, true],        // a daily POC not traded back to (121) is inside
      [139.6, 137.08, 0, true, false]]);     // the leg began before the chart; 139 and 138 were traded back to
  assert.deepEqual(bands[0].leg, { from: 6, base: 100, to: 12, extreme: 160 });
  assert.equal(bands[1].leg, null);          // its start is off the chart: the band only
  assert.deepEqual(fibTicks(bands).map(t => [t.label, t.kind]), [[`${FIB_LABEL} \u00b7 POC`, "fib"], [FIB_LABEL, "fib"]]);
  assert.equal(fibTicks(bands)[0].price, (122.92 + 120.4) / 2);
  assert.deepEqual(fibBands({ fib: [] }, times, H4), []);
  assert.deepEqual(fibBands(body, [], H4), []);
});

const BODY = { period: "day", outer_period: "week" };
const session = { start: T0, end: T0 + DAY, poc: 100, vah: 104, val: 97, live: false };

const WEEKS = { period: "week", outer_period: "month" };
const fmt = p => `$${p}`;

test("every tag and line says what it is, how traders use it, and what was found where it was tested", () => {
  const tick = (key, label, kind = "level") => ({ kind: "tick", tick: { key, label, price: 100, kind } });
  assert.deepEqual(describe(tick("d_open", "D open"), BODY), { title: "Today's opening price", tag: "D open", price: 100, range: null,
    lines: ["The price when today began (00:00 UTC).", "Traders read price above it as buyers being ahead today, below it as sellers being ahead."] });
  assert.equal(describe(tick("m_open", "M open"), BODY).title, "This month's opening price");

  // Yesterday's extremes carry the finding of the study on fading them; last week's were not tested.
  const pdh = describe(tick("pd_high", "PDH"), BODY);
  assert.equal(pdh.title, "Yesterday's high");
  assert.deepEqual(pdh.lines.map(l => l.split(" ")[0]), ["The", "Traders", "Tested"]);
  assert.match(describe(tick("pd_low", "PDL"), BODY).lines[2], /buying those dips made nothing before fees/);
  assert.equal(describe(tick("pw_low", "PWL"), BODY).title, "Last week's low");
  assert.equal(describe(tick("pw_low", "PWL"), BODY).lines.length, 2);
  assert.equal(describe(tick("ib_low", "IB low"), BODY).title, "Low of today's first hour");

  // The previous outer session's value area, with its own prices.
  const outer = { outer: [{ val: 90, vah: 110, poc: 101, live: false }, { val: 1, vah: 2, poc: 1.5, live: true }] };
  const vah = describe(tick("p_vah", "PW VAH", "edge"), { ...BODY, ...outer }, fmt);
  assert.equal(vah.title, "Top of last week's main trading range");
  assert.equal(vah.lines[0], "70% of last week's trading happened between $90 and $110. This is the top of that band (its value area high, VAH).");
  assert.match(describe(tick("p_val", "PM VAL", "edge"), { ...WEEKS, ...outer }, fmt).lines[0], /^70% of last month's trading .* \(its value area low, VAL\)\.$/);
  assert.equal(describe(tick("p_vah", "PW VAH", "edge"), BODY).lines[0], "This is the top of that band (its value area high, VAH).");   // no finished week yet
  assert.equal(describe(tick("p_poc", "PM POC", "poc"), WEEKS).title, "Last month's most-traded price");

  // A most-traded price not traded back to: the same words from its tag and from its dashed line.
  assert.equal(describe(tick(`n_${T0}`, "W nPOC", "poc"), BODY).title, "Most-traded price of the week of 7 Sept, not revisited");
  assert.equal(describe(tick(`n_${T0}`, "M nPOC", "poc"), WEEKS).title, "Most-traded price of the month of 7 Sept, not revisited");
  assert.equal(describe({ kind: "naked", s: session }, BODY).title, "Most-traded price of 7 Sept, not revisited");
  assert.deepEqual(describe({ kind: "naked", s: session }, WEEKS).lines, describe(tick(`n_${T0}`, "W nPOC", "poc"), BODY).lines);
  assert.equal(describe({ kind: "naked", s: session }, BODY).price, 100);

  assert.equal(describe({ kind: "poc", s: session }, BODY).title, "Most-traded price, 7 Sept");
  assert.equal(describe({ kind: "poc", s: { ...session, live: true } }, BODY).tag, "so far");
  assert.match(describe({ kind: "poc", s: { ...session, live: true } }, BODY).lines[0], /that day so far/);
  assert.deepEqual(describe({ kind: "value", s: session }, BODY).range, [97, 104]);
  assert.equal(describe({ kind: "value", s: session }, WEEKS).title, "Main trading range, the week of 7 Sept");

  // The carried edges quote the rule and what the study of it found; that study was on days.
  const edge = describe({ kind: "edge", which: "val", s: session }, BODY, fmt);
  assert.equal(edge.price, 97);
  assert.equal(edge.title, "Bottom of yesterday's main trading range");
  assert.equal(edge.lines[0], "70% of yesterday's trading happened between $97 and $104. This dashed line is the bottom of that band, carried into today.");
  assert.equal(edge.lines[2], "Tested here: it crossed 4 times in 10.");
  assert.equal(describe({ kind: "edge", which: "vah", s: session }, WEEKS).lines[2], "Tested here on days, not weeks: it crossed 4 times in 10.");
  assert.equal(describe({ kind: "profile" }, BODY).title, "Trading by price");
});

test("the pullback zone is described with the swing it measures", () => {
  const leg = { from: 6, base: 100, to: 12, extreme: 160 };
  const up = { top: 122.92, bottom: 120.4, direction: 1, base: 100, extreme: 160, leg, poc: true, touched: false };
  const d = describe({ kind: "fib", band: up }, BODY, fmt);
  assert.equal(d.title, "Pullback zone (0.618 to 0.66)");
  assert.deepEqual(d.range, [120.4, 122.92]);
  assert.equal(d.price, null);
  assert.equal(d.lines[0], "Price rose from $100 to $160 (the dotted line). This band is where a dip has given back about two thirds of that rise (61.8% to 66%).");
  assert.equal(d.lines[1], "Traders use it as the place to buy the dip.");
  assert.match(d.lines[2], /^Tested here on 71 coins: .* turned back 47 times in 100/);
  assert.match(d.lines[3], /^A most-traded price \(POC\) sits inside the band/);
  assert.equal(d.lines.length, 4);

  // A fall, with its start off the chart (no dotted line), already traded into, and no POC inside.
  const down = { top: 139.6, bottom: 137.08, direction: -1, base: 160, extreme: 100, leg: null, poc: false, touched: true };
  const e = describe({ kind: "fib", band: down }, BODY, fmt);
  assert.equal(e.lines[0], "Price fell from $160 to $100. This band is where a bounce has taken back about two thirds of that fall (61.8% to 66%).");
  assert.equal(e.lines[1], "Traders use it as the place to sell the bounce.");
  assert.equal(e.lines[3], "Price has already traded into this band.");

  // Its tag gives the same entry; the bands the layer builds carry the swing's two ends.
  assert.deepEqual(describe({ kind: "tick", tick: { key: "fib_1", label: FIB_LABEL, price: 138.34, kind: "fib" }, bands: [up, down] }, BODY, fmt), e);
  const built = fibBands({ fib: [{ direction: 1, base_time: T0 + DAY, base: 100, extreme_time: T0 + 2 * DAY, extreme: 160, from: 122.92, to: 120.4, touched: false }] }, times, H4)[0];
  assert.deepEqual([built.base, built.extreme, built.direction], [100, 160, 1]);
});

test("a tag standing for several levels describes each", () => {
  const merged = mergeTicks([{ key: "d_open", label: "D open", price: 100, y: 50, kind: "level" }, { key: "w_open", label: "W open", price: 100, y: 50.5, kind: "level" }])[0];
  assert.deepEqual(describeAll({ kind: "tick", tick: merged }, BODY).map(d => d.title), ["Today's opening price", "This week's opening price"]);
  assert.equal(describeAll({ kind: "profile" }, BODY).length, 1);
});

test("no forecast words and no bare shorthand in any description", () => {
  const words = /\b(will|expect|expected|likely|predict|target|probability|odds)\b/i;
  const keys = ["d_open", "w_open", "m_open", "pd_high", "pd_low", "pw_high", "pw_low", "ib_high", "ib_low", "p_vah", "p_val", "p_poc", "n_1"];
  const band = { top: 2, bottom: 1, direction: 1, base: 1, extreme: 3, leg: {}, poc: true, touched: true };
  const hits = [...keys.map(key => ({ kind: "tick", tick: { key, label: "x", price: 1, kind: "level" } })),
    { kind: "poc", s: session }, { kind: "poc", s: { ...session, live: true } }, { kind: "naked", s: session },
    { kind: "value", s: session }, { kind: "edge", which: "vah", s: session }, { kind: "edge", which: "val", s: session },
    { kind: "profile" }, { kind: "fib", band }, { kind: "fib", band: { ...band, direction: -1 } }];
  for (const body of [BODY, WEEKS]) {
    for (const h of hits) {
      const d = describe(h, { ...body, outer: [{ val: 1, vah: 2, poc: 1.5, live: false }] });
      assert.ok(d.lines.length >= 2, d.title);
      const all = `${d.title} ${d.lines.join(" ")}`;
      assert.doesNotMatch(all, words, d.title);
      assert.doesNotMatch(d.title, /\b(POC|VAH|VAL|IB|nPOC|PDH|PDL|PWH|PWL)\b/, d.title);             // titles are plain words
      assert.doesNotMatch(all, /undefined|NaN|null/, d.title);
    }
  }
});

test("distance from the last price, in words", () => {
  assert.equal(distanceNote(103.2, 100), "3.2% above the last price");
  assert.equal(distanceNote(82, 100), "18% below the last price");
  assert.equal(distanceNote(100.01, 100), "at the last price");
  assert.equal(distanceNote(null, 100), "");
  assert.equal(rangeNote([120, 125], 100), "20% above the last price");      // to the nearer edge
  assert.equal(rangeNote([80, 90], 100), "10% below the last price");
  assert.equal(rangeNote([97, 104], 100), "the last price is inside");
  assert.equal(rangeNote(null, 100), "");
});
