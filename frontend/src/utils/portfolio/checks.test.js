import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildRow, positionChecks, ordersFor, orderKinds, liqDistance, sortRows, countChecks, filterRows, alignment, reflexShares, flagsOf, quietNoStop, nearestLiq, carryPerDay, carryShown } from "./checks.js";
import { positionsOf } from "./totals.js";

const fx = name => JSON.parse(readFileSync(new URL(`./__fixtures__/${name}.json`, import.meta.url), "utf8"));

const pos = (o = {}) => ({ coin: "HYPE", venue: "main", szi: 10, side: "long", isLong: true, entry: 75, mark: 80, value: 800, upnl: 50, roe: 6, liq: 40, ...o });
const ctx = (o = {}) => ({ covered: true, h4: { signal: "STRONG_LONG", heat: 60 }, d1: { signal: "LIGHT_LONG" }, band: { lo: 70, hi: 74, state: "above" }, atr_1d: 3,
  traders: { long: { n: 9, n_day_ago: 10 }, short: { n: 2, n_day_ago: 1 } }, ...o });
const stop = px => ({ px });

test("exit signal: a long under TRIM, TRIM_HARD, RISK_OFF or NO_LONG on 4H or 1D", () => {
  for (const s of ["TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"]) {
    assert.ok(positionChecks(pos(), ctx({ h4: { signal: s } }), { stops: [stop(70)] }).has("exit"));
    assert.ok(positionChecks(pos(), ctx({ d1: { signal: s } }), { stops: [stop(70)] }).has("exit"));
  }
  assert.ok(!positionChecks(pos({ isLong: false, side: "short" }), ctx({ h4: { signal: "TRIM" } }), { stops: [stop(90)] }).has("exit"));
});

test("heat 95 with TRIM counts once", () => {
  const rows = [buildRow(pos(), ctx({ h4: { signal: "TRIM", heat: 97 } }), [{ coin: "HYPE", side: "A", isTrigger: true, orderType: "Stop Market", triggerPx: "70", reduceOnly: true }])];
  const c = countChecks(rows);
  assert.equal(c.exit, 1);
  assert.equal(Object.values(c).reduce((s, v) => s + v, 0), 1);
});

test("1D against: an opposite entry signal; a 1D TRIM is an exit, not 1D against", () => {
  assert.ok(positionChecks(pos(), ctx({ d1: { signal: "LIGHT_SHORT" } }), { stops: [stop(70)] }).has("d1against"));
  const trim = positionChecks(pos(), ctx({ d1: { signal: "TRIM" } }), { stops: [stop(70)] });
  assert.ok(trim.has("exit") && !trim.has("d1against"));
  const short = pos({ isLong: false, side: "short", liq: 120 });
  for (const s of ["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"])
    assert.ok(positionChecks(short, ctx({ d1: { signal: s } }), { stops: [stop(110)] }).has("d1against"));
  assert.ok(!positionChecks(short, ctx({ d1: { signal: "TRIM" } }), { stops: [stop(110)] }).has("d1against"));
});

test("under band: a long whose last weekly close was under the band", () => {
  assert.ok(positionChecks(pos(), ctx({ band: { lo: 90, hi: 95, state: "closed_under" } }), { stops: [stop(70)] }).has("underband"));
  assert.ok(!positionChecks(pos(), ctx({ band: { lo: 90, hi: 95, state: "under_now" } }), { stops: [stop(70)] }).has("underband"));
});

test("no stop, and xyz rows without an order read give no No stop", () => {
  assert.ok(positionChecks(pos(), ctx(), { stops: [] }).has("nostop"));
  assert.ok(!positionChecks(pos(), ctx(), { stops: [stop(70)] }).has("nostop"));
  const x = buildRow(pos({ coin: "xyz:MSTR", venue: "xyz" }), { covered: false }, [], { ordersRead: false });
  assert.ok(!x.checks.has("nostop"));
  const y = buildRow(pos({ coin: "xyz:MSTR", venue: "xyz" }), { covered: false }, [], { ordersRead: true });
  assert.ok(y.checks.has("nostop"));
});

test("stop past liq: long stop under liq, short stop above liq", () => {
  assert.ok(positionChecks(pos({ liq: 60 }), ctx(), { stops: [stop(55)] }).has("stoppastliq"));
  assert.ok(!positionChecks(pos({ liq: 60 }), ctx(), { stops: [stop(65)] }).has("stoppastliq"));
  assert.ok(positionChecks(pos({ isLong: false, side: "short", liq: 100 }), ctx(), { stops: [stop(105)] }).has("stoppastliq"));
});

test("liq < 2 ATR, with 15% where there is no ATR", () => {
  assert.ok(positionChecks(pos({ liq: 75 }), ctx({ atr_1d: 3 }), { stops: [stop(76)] }).has("liq2atr"));       // 5 / 3 = 1.7 ATR
  assert.ok(!positionChecks(pos({ liq: 70 }), ctx({ atr_1d: 3 }), { stops: [stop(76)] }).has("liq2atr"));      // 3.3 ATR
  assert.ok(positionChecks(pos({ liq: 70 }), { covered: false }, { stops: [stop(76)] }).has("liq2atr"));      // 12.5%
  assert.ok(!positionChecks(pos({ liq: 60 }), { covered: false }, { stops: [stop(76)] }).has("liq2atr"));     // 25%
});

test("liq above band and traders left", () => {
  assert.ok(positionChecks(pos({ liq: 76 }), ctx(), { stops: [stop(77)] }).has("liqaboveband"));
  const left = ctx({ traders: { long: { n: 5, n_day_ago: 8 }, short: { n: 2, n_day_ago: 2 } } });
  assert.ok(positionChecks(pos(), left, { stops: [stop(70)] }).has("tradersleft"));
  const few = ctx({ traders: { long: { n: 2, n_day_ago: 4 }, short: { n: 0, n_day_ago: 0 } } });
  assert.ok(!positionChecks(pos(), few, { stops: [stop(70)] }).has("tradersleft"));     // fewer than 5 a day ago
});

test("orders: stops on the closing side, take-profit limits beyond the mark", () => {
  const ps = positionsOf(fx("ch"), "main");
  const orders = fx("orders");
  const btc = ps.find(p => p.coin === "BTC");
  const o = ordersFor(btc, orders);
  assert.ok(o.stops.length >= 2);
  assert.ok(o.stops.every(s => s.o.side === "A" && s.o.reduceOnly));
  assert.ok(o.stops[0].px > 70000);                         // nearest first: 80,097 before 79.7
  const link = ps.find(p => p.coin === "LINK");
  const lo = ordersFor(link, orders);
  assert.equal(lo.stops.length, 0);
  assert.ok(lo.tps.length > 0 && lo.tps.every(t => t.px > link.mark));
});

test("sort: liquidation facts first, then checks hit, then nearest liquidation", () => {
  const a = { coin: "A", checks: new Set(["nostop"]), liqFact: false, dist: { pct: 40, atr: 8 }, value: 10, upnl: 1 };
  const b = { coin: "B", checks: new Set(["liq2atr", "nostop"]), liqFact: true, dist: { pct: 9, atr: 1.2 }, value: 5, upnl: -3 };
  const c = { coin: "C", checks: new Set(["nostop", "exit"]), liqFact: false, dist: null, value: 50, upnl: 9 };
  const d = { coin: "D", checks: new Set(["nostop"]), liqFact: false, dist: { pct: 12, atr: null }, value: 1, upnl: 0 };
  assert.deepEqual(sortRows([a, b, c, d]).map(r => r.coin), ["B", "C", "D", "A"]);
  assert.deepEqual(sortRows([a, b, c, d], "size").map(r => r.coin), ["C", "A", "B", "D"]);
  assert.deepEqual(sortRows([a, b, c, d], "pnl").map(r => r.coin), ["C", "A", "D", "B"]);
  assert.deepEqual(filterRows([a, b, c, d], new Set(["exit", "liq2atr"])).map(r => r.coin), ["B", "C"]);
  assert.deepEqual(nearestLiq([a, b, c, d]).map(r => r.coin), ["B", "D", "A"]);
});

test("flags, alignment and REFLEX shares", () => {
  assert.deepEqual(flagsOf(new Set(["underband", "nostop", "stoppastliq"])), { first: "stoppastliq", more: ["nostop", "underband"] });
  // "no stop" on half the rows or more: said once by the checks row, left off the rows.
  assert.deepEqual(flagsOf(new Set(["nostop"]), { quietNoStop: true }), { first: null, more: [] });
  assert.deepEqual(flagsOf(new Set(["nostop", "underband"]), { quietNoStop: true }), { first: "underband", more: [] });
  assert.equal(quietNoStop({ nostop: 11 }, 12), true);
  assert.equal(quietNoStop({ nostop: 2 }, 12), false);
  assert.equal(alignment("STRONG_LONG", true), "with");
  assert.equal(alignment("TRIM", true), "against");
  assert.equal(alignment("LIGHT_SHORT", false), "with");
  assert.equal(alignment("WAIT", true), "none");
  const s = reflexShares([
    { value: 70, isLong: true, covered: true, ctx: { h4: { signal: "STRONG_LONG" } } },
    { value: 20, isLong: true, covered: true, ctx: { h4: { signal: "TRIM" } } },
    { value: 5, isLong: true, covered: true, ctx: { h4: { signal: "WAIT" } } },
    { value: 5, isLong: true, covered: false, ctx: null },
  ]);
  assert.deepEqual(s, { with: 70, against: 20, none: 5, uncovered: 5, total: 100 });
  assert.equal(liqDistance(pos({ liq: null }), 3), null);
});

test("Orders tab kinds: the rail's stop-loss rule; a stop entry is just a stop", () => {
  const btc = fx("orders").filter(o => o.coin === "BTC");
  assert.deepEqual(orderKinds(btc, true), { tp: 0, sl: 3, stop: 1, limit: 0 });
  assert.equal(ordersFor({ coin: "BTC", isLong: true, mark: 80221 }, btc).stops.length, 3);
  // No position on the coin: nothing is a stop-loss.
  assert.deepEqual(orderKinds(btc, null), { tp: 0, sl: 0, stop: 4, limit: 0 });
});

test("funding carry: per day at the current rate, shown from 0.1% of notional", () => {
  // A $1,600 short at −0.08%/h pays 1.92% a day: −$30.72.
  const short = { isLong: false, value: 1600 };
  assert.ok(Math.abs(carryPerDay(short, -0.0008) + 30.72) < 1e-9);
  assert.ok(Math.abs(carryShown(short, -0.0008) + 30.72) < 1e-9);
  // −0.0024%/h on the same short is 0.057% a day: not shown.
  assert.equal(carryShown(short, -0.000023915), null);
  // A long receives when the rate is negative.
  assert.ok(carryPerDay({ isLong: true, value: 1000 }, -0.0001) > 0);
  assert.equal(carryShown(short, NaN), null);
});
