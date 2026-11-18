import test from "node:test";
import assert from "node:assert/strict";
import { barIndex, barAt, placeRanges, placeLevels, lastDone, ticks, rangeTicks, pocRule, histogram, spread, mergeTicks, fibBands, fibTicks, FIB_LABEL,
  describe, describeAll, distanceNote, rangeNote, hitKey } from "./valueLayer.js";

const H4 = 14400, DAY = 86400;
const T0 = 1788739200;                                    // Monday 2026-09-07 00:00 UTC
const times = Array.from({ length: 15 }, (_, i) => T0 + i * H4);   // 2.5 days of 4h candles

test("a time sits on the first candle at or after it; past the last candle bars are counted on", () => {
  assert.equal(barIndex(times, T0, H4), 0);
  assert.equal(barIndex(times, T0 + DAY, H4), 6);
  assert.equal(barIndex(times, T0 + DAY + 1, H4), 7);
  assert.equal(barIndex(times, T0 + 3 * DAY, H4), 18);      // 4 bars after the last candle
});

test("a moment is inside the last candle that opened at or before it", () => {
  assert.equal(barAt(times, T0), 0);
  assert.equal(barAt(times, T0 + H4 - 1), 0);
  assert.equal(barAt(times, T0 + H4), 1);
  assert.equal(barAt(times, T0 + DAY + 3600), 6);
  assert.equal(barAt(times, T0 - DAY), 0);                  // before the chart: its first candle
  assert.equal(barAt(times, T0 + 9 * DAY), 14);             // after it: its last
});

// A rise that began an hour into the chart and ended in the fifth candle, the fall after it still running.
const RISE = { direction: 1, start: T0 + 3600, end: T0 + 4 * H4 + 7200, live: false, low: 100, high: 160, poc: 121, vah: 140, val: 112,
  bins: { low: 100, step: 10, v: [50, 200, 1000, 400, 0, 20] } };
const FALL = { direction: -1, start: T0 + 4 * H4 + 3600, end: T0 + 15 * H4, live: true, low: 130, high: 160, poc: 150, vah: 156, val: 141,
  bins: { low: 130, step: 5, v: [10, 20, 30, 1000, 60, 5] } };

test("swings get their span in candles, from the candle holding their start to the one holding their end", () => {
  const placed = placeRanges([{ ...RISE, start: T0 - 9 * DAY, end: T0 - DAY }, RISE, FALL], times);
  assert.deepEqual(placed.map(r => [r.direction, r.from, r.to]), [[1, 0, 5], [-1, 4, 15]]);     // the one that ended before the chart is dropped
  assert.deepEqual(placeRanges([{ ...RISE, start: T0 - DAY }], times).map(r => [r.from, r.to]), [[0, 5]]);   // began before it: clipped
  assert.deepEqual(placeRanges([RISE], []), []);
  assert.deepEqual(placeRanges(null, times), []);
  assert.equal(lastDone(placed).direction, 1);              // the last swing that has ended
  assert.equal(lastDone(placeRanges([FALL], times)), null);
});

// Swing levels: a high made before the chart and still open, a low swept two candles in, a high broken later.
const OPEN = { side: "high", price: 160, time: T0 - 3 * DAY, known: T0 - DAY, taken: null, back: null, extreme: null };
const SWEPT = { side: "low", price: 100, time: T0 + 3600, known: T0 + DAY, taken: T0 + DAY + 2 * H4 + 3600, back: T0 + DAY + 2 * H4 + 7200, extreme: 98.5 };
const BROKEN = { side: "high", price: 150, time: T0 + H4, known: T0 + DAY, taken: T0 + 2 * DAY, back: null, extreme: 158 };

test("swing levels run from their swing's candle to the candle that traded through them", () => {
  const placed = placeLevels({ swing_levels: [OPEN, SWEPT, BROKEN, { ...BROKEN, time: T0 - 9 * DAY, taken: T0 - DAY }] }, times);
  assert.deepEqual(placed.map(v => [v.side, v.before, v.from, v.to, v.swept]),
    [["high", true, 0, null, false], ["low", false, 0, 8, true], ["high", false, 1, 12, false]]);     // taken before the chart: dropped
  assert.deepEqual(placeLevels({ swing_levels: [OPEN] }, []), []);
  assert.deepEqual(placeLevels({}, times), []);
  assert.deepEqual(placeLevels(null, times), []);
});

test("a swing level says where price turned, what became of it and how traders use it", () => {
  const fmt = x => `at ${x}`;
  const open = describe({ kind: "level", v: OPEN }, {}, fmt);
  assert.equal(open.title, "Swing high not traded through");
  assert.equal(open.price, 160);
  assert.ok(open.lines[0].startsWith("Price turned down at at 160 on 4 Sep"), open.lines[0]);
  assert.ok(open.lines[0].endsWith("and has not traded above it since."), open.lines[0]);
  assert.ok(open.lines[1].includes("stop orders rest just above a swing high like this (they call it liquidity)"), open.lines[1]);
  assert.ok(open.lines[2].startsWith("Tested here on 71 coins since 2021: trading back into the range after such a push lost about 0.3%"), open.lines[2]);
  const swept = describe({ kind: "level", v: SWEPT }, {}, fmt);
  assert.equal(swept.title, "Swing low swept");
  assert.ok(swept.lines[0].includes("it traded below it, as far as at 98.5, and an hourly candle closed back over it within the hour."), swept.lines[0]);
  assert.ok(swept.lines[1].includes("swing failure when it is quick and a failed auction when it takes hours"), swept.lines[1]);
  assert.ok(swept.lines[2].includes("9 in 10 swing levels that price traded through were swept like this"), swept.lines[2]);
  const slow = describe({ kind: "level", v: { ...SWEPT, back: SWEPT.taken + 7 * 3600 } }, {}, fmt);
  assert.ok(slow.lines[0].endsWith("closed back over it 7 hours later."), slow.lines[0]);
  const broken = describe({ kind: "level", v: BROKEN }, { as_of: BROKEN.taken + 9 * DAY }, fmt);
  assert.equal(broken.title, "Swing high traded through");
  assert.ok(broken.lines[0].endsWith("as far as at 158, and no hourly candle closed back under it in the three days after."), broken.lines[0]);
  const fresh = describe({ kind: "level", v: BROKEN }, { as_of: BROKEN.taken + 5 * 3600 }, fmt);       // traded through five hours ago
  assert.ok(broken.lines[2].startsWith("Counted here on 71 coins since 2021: 1 in 10"), broken.lines[2]);
  assert.ok(fresh.lines[0].endsWith("and no hourly candle has closed back under it so far."), fresh.lines[0]);
  assert.equal(fresh.lines.length, 2);                      // still inside the three days: not counted as broken yet
});

test("the last finished swing's value area and point of control are ticks", () => {
  const placed = placeRanges([RISE, FALL], times);
  assert.deepEqual(rangeTicks(placed).map(t => [t.key, t.label, t.price, t.kind]),
    [["r_vah", "VAH", 140, "edge"], ["r_poc", "POC", 121, "poc"], ["r_val", "VAL", 112, "edge"]]);
  assert.equal(rangeTicks(placed)[0].range.direction, 1);
  assert.deepEqual(rangeTicks(placeRanges([FALL], times)), []);
});

test("the rule on the last finished swing: short from its POC below its value area, long from it above", () => {
  assert.equal(pocRule(RISE, 111.9), "short");
  assert.equal(pocRule(RISE, 140.1), "long");
  assert.equal(pocRule(RISE, 112), null);                   // on the edge is inside
  assert.equal(pocRule(RISE, 130), null);
  assert.equal(pocRule(RISE, undefined), null);
  assert.equal(pocRule(null, 100), null);
  const placed = placeRanges([RISE, FALL], times);
  assert.deepEqual(rangeTicks(placed, 100).map(t => t.label), ["VAH", "POC \u00b7 short", "VAL"]);
  assert.deepEqual(rangeTicks(placed, 150).map(t => t.label), ["VAH", "POC \u00b7 long", "VAL"]);
  assert.deepEqual(rangeTicks(placed, 120).map(t => [t.label, t.rule || null]), [["VAH", null], ["POC", null], ["VAL", null]]);
  // The tag and the dashed line it sits on say the same, with what the rule's test found.
  const tag = describe({ kind: "tick", tick: rangeTicks(placed, 100)[1] }, {}, fmt);
  assert.deepEqual([tag.title, tag.tag], ["Most-traded price of the rise", "POC \u00b7 short"]);
  assert.equal(tag.lines[1], "Price is now below the rise's main trading range (under $112). The method's rule then: sell (go short) at this price if price climbs back to it.");
  assert.equal(tag.lines[2], "Tested here on 71 coins since 2021: the rule made about 0.3% a trade after fees, too little to tell from nothing.");
  assert.deepEqual(describe({ kind: "rline", which: "poc", r: RISE, rule: "short" }, {}, fmt).lines, tag.lines);
  assert.equal(describe({ kind: "rline", which: "poc", r: RISE, rule: null }, {}, fmt).lines[2], "Not tested here.");
  assert.equal(describe({ kind: "rline", which: "poc", r: RISE, rule: "long" }, {}, fmt).lines[1],
    "Price is now above the rise's main trading range (over $140). The method's rule then: buy (go long) at this price if price dips back to it.");
  assert.equal(describe({ kind: "rline", which: "poc", r: RISE, rule: null }, {}, fmt).lines[1], "Traders use a price like this as the place to take profit.");
});

test("a swing's histogram: its rows by price, the point of control's row and the value area marked", () => {
  const rows = histogram(RISE);
  assert.deepEqual(rows.map(r => [r.low, r.high, r.share, r.kind]),
    [[100, 110, 0.05, "rest"], [110, 120, 0.2, "value"], [120, 130, 1, "poc"], [130, 140, 0.4, "value"], [150, 160, 0.02, "rest"]]);   // the empty row is left out
  assert.deepEqual(histogram({}), []);
  assert.deepEqual(histogram({ bins: { low: 1, step: 0, v: [1] } }), []);
});

test("each chart shows its own levels: the day's on 1H and 4H, the week's on 1D, the first hour on 1H only", () => {
  const body = { levels: { d_open: 100, pd_high: 110, pd_low: 90, w_open: 95, m_open: 80, pw_high: 120, pw_low: 70, ib_high: 103, ib_low: 98 } };
  assert.deepEqual(ticks(body, "4h").map(t => `${t.label} ${t.price}`), ["D open 100", "PDH 110", "PDL 90", "W open 95", "M open 80"]);
  assert.deepEqual(ticks(body, "1h").map(t => t.label), ["D open", "PDH", "PDL", "W open", "M open", "IB high", "IB low"]);
  assert.deepEqual(ticks(body, "1d").map(t => `${t.label} ${t.price}`), ["W open 95", "M open 80", "PWH 120", "PWL 70"]);
  assert.deepEqual(ticks({ levels: { d_open: 100 } }, "1d"), []);
  assert.deepEqual(ticks(null), []);
});

test("no forecast words in the tick labels", () => {
  const all = { d_open: 1, pd_high: 1, pd_low: 1, w_open: 1, m_open: 1, pw_high: 1, pw_low: 1, ib_high: 1, ib_low: 1 };
  const labels = [...ticks({ levels: all }, "1h"), ...ticks({ levels: all }, "1d"), ...rangeTicks(placeRanges([RISE], times))].map(t => t.label).join(" ");
  assert.doesNotMatch(labels, /\b(will|expect|likely|predict|target|probability|odds)\b/i);
});

test("labels that would overlap are pushed down, the rest stay put", () => {
  assert.deepEqual(spread([10, 14, 40, 45, 46], 12), [10, 22, 40, 52, 64]);
  assert.deepEqual(spread([], 12), []);
});

test("ticks at one price share a label, and a word they end in", () => {
  const rows = [{ label: "W open", y: 100.4, kind: "level" }, { label: "PDH", y: 60, kind: "level" }, { label: "D open", y: 100, kind: "level" },
    { label: "M open", y: 100.9, kind: "level" }, { label: "POC", y: 101.2, kind: "poc" }, { label: "PDL", y: 140, kind: "level" }];
  assert.deepEqual(mergeTicks(rows).map(t => [t.label, t.y, t.kind]),
    [["PDH", 60, "level"], ["D · W · M open · POC", 100, "poc"], ["PDL", 140, "level"]]);
  assert.deepEqual(mergeTicks(rows)[1].members.map(t => t.label), ["D open", "W open", "M open", "POC"]);   // each is still told apart
});

test("retracement bands: where they start, the leg they measure, and whether a finished swing's point of control sits in them", () => {
  const body = {
    fib: [{ direction: 1, base_time: T0 + DAY, base: 100, extreme_time: T0 + 2 * DAY, extreme: 160, from: 122.92, to: 120.4, touched: false },
      { direction: -1, base_time: T0 - 9 * DAY, base: 160, extreme_time: T0 + DAY, extreme: 100, from: 137.08, to: 139.6, touched: true }],
    ranges: [{ poc: 121, live: false }, { poc: 138, live: true }],
  };
  const bands = fibBands(body, times, H4);
  assert.deepEqual(bands.map(b => [b.top, b.bottom, b.from, b.touched, b.poc]),
    [[122.92, 120.4, 6, false, true],        // the finished swing's POC (121) is inside
      [139.6, 137.08, 0, true, false]]);     // the leg began before the chart; 138 belongs to the move still running
  assert.deepEqual(bands[0].leg, { from: 6, base: 100, to: 12, extreme: 160 });
  assert.equal(bands[1].leg, null);          // its start is off the chart: the band only
  assert.deepEqual([bands[0].base, bands[0].extreme, bands[0].direction], [100, 160, 1]);
  assert.deepEqual(fibTicks(bands).map(t => [t.label, t.kind]), [[`${FIB_LABEL} · POC`, "fib"], [FIB_LABEL, "fib"]]);
  assert.equal(fibTicks(bands)[0].price, (122.92 + 120.4) / 2);
  assert.deepEqual(fibBands({ fib: [] }, times, H4), []);
  assert.deepEqual(fibBands(body, [], H4), []);
});

const fmt = p => `$${p}`;
const tick = (key, label, kind = "level") => ({ kind: "tick", tick: { key, label, price: 100, kind } });

test("the opens and prior extremes say what they are and how traders use them", () => {
  assert.deepEqual(describe(tick("d_open", "D open"), {}), { title: "Today's opening price", tag: "D open", price: 100, range: null,
    lines: ["The price when today began (00:00 UTC).", "Traders read price above it as buyers being ahead today, below it as sellers being ahead."] });
  assert.equal(describe(tick("m_open", "M open"), {}).title, "This month's opening price");
  // Yesterday's extremes carry the finding of the study on fading them; last week's were not tested.
  const pdh = describe(tick("pd_high", "PDH"), {});
  assert.equal(pdh.title, "Yesterday's high");
  assert.deepEqual(pdh.lines.map(l => l.split(" ")[0]), ["The", "Traders", "Tested"]);
  assert.match(describe(tick("pd_low", "PDL"), {}).lines[2], /buying those dips made nothing before fees/);
  assert.equal(describe(tick("pw_low", "PWL"), {}).title, "Last week's low");
  assert.equal(describe(tick("pw_low", "PWL"), {}).lines.length, 2);
  assert.equal(describe(tick("ib_low", "IB low"), {}).title, "Low of today's first hour");
});

test("a swing's box says the move it covers, where it traded most and how traders use that", () => {
  const d = describe({ kind: "range", r: RISE }, {}, fmt);
  assert.equal(d.title, "Trading by price in the rise, 7 Sept");                    // began and ended the same day
  assert.deepEqual(d.range, [100, 160]);
  assert.equal(d.price, null);
  assert.equal(d.tag, null);
  assert.equal(d.lines[0], "Price rose from $100 to $160. Each bar is how much was traded at that price on the way: longer means more.");
  assert.equal(d.lines[1], "70% of it was traded between $112 and $140 (the value area, the brighter bars). The gold line, $121, is the single most-traded price (the point of control, POC).");
  assert.match(d.lines[2], /^Traders treat that band as the move's fair prices/);
  assert.equal(d.lines[3], "Not tested here.");
  const live = describe({ kind: "range", r: FALL }, {}, fmt);
  assert.equal(live.title, "Trading by price in the fall, 7 Sept to 9 Sept");
  assert.equal(live.tag, "so far");
  assert.match(live.lines[0], /^Price fell from \$160 to \$130 and the move is still running\./);
});

test("a swing's lines, and the tags that carry them on, give the same words", () => {
  const vah = describe({ kind: "rline", which: "vah", r: RISE }, {}, fmt);
  assert.equal(vah.title, "Top of the rise's main trading range");
  assert.equal(vah.price, 140);
  assert.equal(vah.lines[0], "70% of the trading in the rise from $100 to $160 happened between $112 and $140. This is the top of that band (its value area high, VAH).");
  assert.match(vah.lines[1], /Above it they watch whether price holds up there or falls back in\.$/);
  const val = describe({ kind: "rline", which: "val", r: FALL }, {}, fmt);
  assert.equal(val.title, "Bottom of the fall's main trading range");
  assert.equal([val.price, val.tag].join(), "141,so far");
  assert.match(val.lines[0], /^70% of the trading in the fall from \$160 to \$130 so far happened between \$141 and \$156\. This is the bottom of that band \(its value area low, VAL\)\.$/);
  const poc = describe({ kind: "rline", which: "poc", r: RISE }, {}, fmt);
  assert.equal(poc.title, "Most-traded price of the rise");
  assert.deepEqual(poc.lines, ["More was traded at this price than at any other in the rise from $100 to $160 (its point of control, POC).",
    "Traders use a price like this as the place to take profit.", "Not tested here."]);
  const [t] = rangeTicks(placeRanges([RISE], times));
  const tagged = describe({ kind: "tick", tick: t }, {}, fmt);
  assert.deepEqual([tagged.title, tagged.tag, tagged.price, tagged.lines], [vah.title, "VAH", 140, vah.lines]);
});

test("the pullback zone is described with the swing it measures", () => {
  const leg = { from: 6, base: 100, to: 12, extreme: 160 };
  const up = { top: 122.92, bottom: 120.4, direction: 1, base: 100, extreme: 160, leg, poc: true, touched: false };
  const d = describe({ kind: "fib", band: up }, {}, fmt);
  assert.equal(d.title, "Pullback zone (0.618 to 0.66)");
  assert.deepEqual(d.range, [120.4, 122.92]);
  assert.equal(d.lines[0], "Price rose from $100 to $160 (the dotted line). This band is where a dip has given back about two thirds of that rise (61.8% to 66%).");
  assert.equal(d.lines[1], "Traders use it as the place to buy the dip.");
  assert.match(d.lines[2], /^Tested here on 71 coins: .* turned back 47 times in 100/);
  assert.match(d.lines[3], /^A most-traded price \(POC\) sits inside the band/);
  assert.equal(d.lines.length, 4);
  // A fall, with its start off the chart (no dotted line), already traded into, and no POC inside.
  const down = { top: 139.6, bottom: 137.08, direction: -1, base: 160, extreme: 100, leg: null, poc: false, touched: true };
  const e = describe({ kind: "fib", band: down }, {}, fmt);
  assert.equal(e.lines[0], "Price fell from $160 to $100. This band is where a bounce has taken back about two thirds of that fall (61.8% to 66%).");
  assert.equal(e.lines[1], "Traders use it as the place to sell the bounce.");
  assert.equal(e.lines[3], "Price has already traded into this band.");
  assert.deepEqual(describe({ kind: "tick", tick: { key: "fib_1", label: FIB_LABEL, price: 138.34, kind: "fib" }, bands: [up, down] }, {}, fmt), e);
});

test("a tag standing for several levels describes each", () => {
  const merged = mergeTicks([{ key: "d_open", label: "D open", price: 100, y: 50, kind: "level" }, { key: "w_open", label: "W open", price: 100, y: 50.5, kind: "level" }])[0];
  assert.deepEqual(describeAll({ kind: "tick", tick: merged }, {}).map(d => d.title), ["Today's opening price", "This week's opening price"]);
  assert.equal(describeAll({ kind: "range", r: RISE }, {}).length, 1);
});

test("no forecast words and no bare shorthand in any description", () => {
  const words = /\b(will|expect|expected|likely|predict|target|probability|odds)\b/i;
  const keys = ["d_open", "w_open", "m_open", "pd_high", "pd_low", "pw_high", "pw_low", "ib_high", "ib_low"];
  const band = { top: 2, bottom: 1, direction: 1, base: 1, extreme: 3, leg: {}, poc: true, touched: true };
  const hits = [...keys.map(key => tick(key, "x")), ...rangeTicks(placeRanges([RISE], times)).map(t => ({ kind: "tick", tick: t })),
    ...[RISE, FALL].flatMap(r => [{ kind: "range", r }, ...["vah", "val", "poc"].map(which => ({ kind: "rline", which, r }))]),
    { kind: "rline", which: "poc", r: RISE, rule: "short" }, { kind: "rline", which: "poc", r: FALL, rule: "long" },
    { kind: "fib", band }, { kind: "fib", band: { ...band, direction: -1 } },
    ...[OPEN, SWEPT, BROKEN, { ...OPEN, side: "low" }, { ...SWEPT, side: "high" }, { ...BROKEN, side: "low" }].map(v => ({ kind: "level", v }))];
  for (const h of hits) {
    const d = describe(h, {});
    assert.ok(d.lines.length >= 2, d.title);
    const all = `${d.title} ${d.lines.join(" ")}`;
    assert.doesNotMatch(all, words, d.title);
    assert.doesNotMatch(d.title, /\b(POC|VAH|VAL|IB|PDH|PDL|PWH|PWL)\b/, d.title);             // titles are plain words
    assert.doesNotMatch(all, /undefined|NaN|null/, d.title);
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

test("what is under the pointer has a stable name", () => {
  assert.equal(hitKey({ kind: "rline", which: "poc", r: RISE }), `rline:${RISE.start}:poc`);
  assert.equal(hitKey({ kind: "range", r: FALL }), `range:${FALL.start}:`);
  assert.equal(hitKey(tick("d_open", "D open")), "tick:d_open:");
  assert.equal(hitKey({ kind: "level", v: SWEPT }), `level:${SWEPT.time}:low`);
  assert.equal(hitKey(null), "");
});
