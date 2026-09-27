import test from "node:test";
import assert from "node:assert/strict";
import { WATCH_MESSAGES, at, inBox, isAddress, labelBox, labelOrder, movement, movers, picks, placeLabels, pnl, pulseLine, radarHref, symlog, thumbExtent, trailPoints, visible, watchReason, watchToast } from "./setupMap.js";

const BOX = { z: [-0.5, 1.5], n: [1, 8] };
const coin = (o = {}) => ({ coin: "X", zscore: 0.5, priority: 50, stage: "running", zone: "watch", crowd: "holding",
  traders: { pl: 3, ps: 0 }, trail: { t: [1, 2, 3], z: [2.2, 1.0, 0.5], n: [0, null, 3] }, ...o });

test("trail fills gaps from the nearest earlier reading", () => {
  assert.deepEqual(trailPoints(coin()).map(p => p.n), [0, 0, 3]);
  assert.deepEqual(trailPoints(coin({ trail: { t: [1, 2], z: [0, 1], n: [null, 3] } })).map(p => p.n), [3, 3]);
  assert.equal(trailPoints(coin({ trail: null })), null);
});

test("movement: entering the box and traders arriving", () => {
  const m = movement(coin(), BOX);
  assert.equal(m.was, false); assert.equal(m.is, true); assert.equal(m.dn, 3);
  const mv = movers([coin(), coin({ coin: "Y", zone: "late", trail: { t: [1, 2], z: [1, 2.5], n: [2, 2] } })], BOX);
  assert.deepEqual(mv.entering.map(c => c.coin), ["X"]);
  assert.deepEqual(mv.leaving.map(c => c.coin), ["Y"]);
  assert.deepEqual(mv.arriving.map(c => c.coin), ["X"]);
});

test("picks rank box coins by priority plus movement", () => {
  const cs = [coin({ coin: "A", priority: 60, trail: null }), coin({ coin: "B", priority: 50, crowd: "early", stage: "fresh" }),
    coin({ coin: "C", zone: "late", priority: 99 })];
  assert.deepEqual(picks(cs, BOX).map(p => p.c.coin), ["B", "A"]);
});

test("default view hides coins with no setup or no traders", () => {
  const cs = [coin({ coin: "A" }), coin({ coin: "B", stage: "waiting" }), coin({ coin: "C", traders: { pl: 0, ps: 0 } }),
    coin({ coin: "D", traders: { pl: 0, ps: 0 }, stage: "forming" }), coin({ coin: "E", zscore: null })];
  assert.deepEqual(visible(cs).map(c => c.coin), ["A", "D"]);
  assert.deepEqual(visible(cs, { keep: new Set(["B"]) }).map(c => c.coin), ["A", "B", "D"]);
  assert.equal(visible(cs, { all: true }).length, 4);
});

test("helpers", () => {
  assert.deepEqual(at([{ z: 0, n: 0 }, { z: 2, n: 4 }], 0.5), { z: 1, n: 2 });
  assert.equal(inBox(BOX, 0, 1), true); assert.equal(inBox(BOX, 0, 9), false);
  assert.equal(Math.round(100 * pnl({ entry: 1, side: "long" }, 1.2)), 20);
  assert.equal(Math.round(100 * pnl({ entry: 1, side: "short" }, 1.2)), -20);
});

test("watch failures map to a reason and a message", () => {
  assert.equal(watchReason(403), "admin");
  assert.equal(watchReason(400), "cap");
  assert.equal(watchReason(500), "error");
  assert.equal(watchToast("TIA", { ok: false, reason: "admin" }), "Watching needs the admin key. Add it under Settings.");
  assert.equal(watchToast("TIA", { ok: false, reason: "cap" }), "At most 30 coins can be watched.");
  assert.equal(watchToast("TIA", { ok: false, reason: "error" }), WATCH_MESSAGES.error);
  assert.equal(watchToast("TIA", null), "Could not change the watch list.");
});

test("watch success keeps today's texts", () => {
  assert.equal(watchToast("TIA", { ok: true, watching: true }, "ready"), "Watching TIA. Alerts go to Telegram.");
  assert.equal(watchToast("TIA", { ok: true, watching: true }, "no_chat"), "Watching TIA. Telegram has no chat yet: send /watch to the bot once.");
  assert.equal(watchToast("TIA", { ok: true, watching: false }, "ready"), "Stopped watching TIA");
});

test("addresses are 0x plus 40 hex digits", () => {
  assert.equal(isAddress("0x880ac484a1743862989a441d6d867238c7aa311c"), true);
  assert.equal(isAddress("0x880AC484A1743862989A441D6D867238C7AA311C"), true);
  assert.equal(isAddress("0x880ac484a1743862989a441d6d867238c7aa311"), false);
  assert.equal(isAddress(""), false);
  assert.equal(isAddress(null), false);
});

// Dots as drawn on the 1D map at 1079x470 (wf/scanner-top/today_desk-dark_smap.png), where
// today's labels collided: "PENGU PEFARTCOIN", "ETHC" (ETH under BTC), TIA over RNDR.
const FIXTURE = [["BTC",733.4,50.5,10.5],["ETH",725.7,50.5,10.5],["SOL",783.1,72.4,9.7],["BNB",710.9,231,5.91],["APE",416.3,260.8,5.5],
  ["DOGE",723.5,142.6,7.82],["INJ",499.2,260.8,5.5],["CRV",630.9,209.9,6.23],["LDO",707.1,193.5,6.5],["LINK",792.2,99.4,8.62],
  ["GMX",638.1,260.8,5.5],["SNX",735.1,260.8,5.5],["XRP",785,150.3,7.96],["AAVE",779.5,135.6,7.66],["COMP",743,260.8,5.5],
  ["WLD",587.2,123.3,7.96],["TIA",544.1,260.8,5.5],["PENDLE",634.5,193.5,6.5],["FET",629.2,209.9,6.23],["JUP",687.1,180.1,6.74],
  ["ONDO",582.6,112.8,8.74],["STRK",782.6,231,5.91],["TAO",723.5,78.3,9.3],["ETHFI",760.2,193.5,6.5],["EIGEN",541.9,260.8,5.5],
  ["RNDR",563.1,260.8,5.5],["GRASS",526.7,150.3,7.66],["PURR",429.8,260.8,6.23],["XLM",543.4,260.8,5.5],["MOVE",741.8,260.8,5.5],
  ["VIRTUAL",719.6,180.1,6.74],["PENGU",589.4,193.5,6.5],["FARTCOIN",664.6,193.5,6.95],["MORPHO",390.9,231,6.5],["TRUMP",741.6,260.8,6.74],
  ["VVV",396.2,69.6,9.6],["ZORA",758.7,260.8,5.5]].map(([coin, x, y, r]) => ({ coin, x, y, r }));
// Today's labelled set on that map, in placement priority (in the box by engine priority,
// the largest trader lean, then movers).
const LABELLED = ["FET", "INJ", "PENDLE", "PURR", "PENGU", "TIA", "RNDR", "CRV", "BTC", "ETH", "BNB", "GRASS", "FARTCOIN", "MORPHO", "SNX", "WLD"];
const PLOT = { x0: 40, y0: 16, x1: 1065, y1: 430 };

function checkLayout(dots, others, placed, opts = {}) {
  const w = c => (opts.charW || 6.4) * c.length + 4;
  const boxes = [...placed].map(([coin, p]) => ({ coin, ...labelBox(p.x, p.y, p.anchor, w(coin)) }));
  for (const b of boxes) {
    assert.ok(b.x0 >= PLOT.x0 && b.x1 <= PLOT.x1 && b.y0 >= PLOT.y0 && b.y1 <= PLOT.y1, `${b.coin} leaves the plot`);
    for (const o of [...dots, ...others]) {
      if (o.coin === b.coin) continue;
      const dx = o.x - Math.max(b.x0, Math.min(o.x, b.x1)), dy = o.y - Math.max(b.y0, Math.min(o.y, b.y1));
      assert.ok(dx * dx + dy * dy >= (o.r + 2) ** 2, `${b.coin} covers the ${o.coin} dot`);
    }
  }
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    assert.ok(!(a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1), `${a.coin} overlaps ${b.coin}`);
  }
}

test("labels: no overlaps on the TIA / PENGU / FARTCOIN / ETH / PENDLE cluster", () => {
  const dots = LABELLED.map(c => FIXTURE.find(d => d.coin === c));
  const others = FIXTURE.filter(d => !LABELLED.includes(d.coin));
  const placed = placeLabels(dots, { bounds: PLOT, others });
  checkLayout(dots, others, placed);
  // Today's collisions are gone: each of these is labelled, or (FARTCOIN, boxed in by
  // PENDLE, LDO, JUP and CRV) left for hover rather than printed over a neighbour.
  for (const c of ["TIA", "PENGU", "ETH", "PENDLE", "BTC", "RNDR"]) assert.ok(placed.has(c), `${c} is labelled`);
  assert.ok(placed.size >= 12, `most labels fit (${placed.size} of ${dots.length})`);
  for (const [coin, p] of placed) {
    const d = FIXTURE.find(x => x.coin === coin);
    assert.ok(Math.abs(p.x - d.x) <= d.r + 4.01 && Math.abs(p.y - d.y) <= d.r + 12.01, `${coin} stays by its dot`);
  }
  // FARTCOIN's four sides all cross a neighbouring dot, so even first in line it stays
  // unlabelled (its name shows on hover) instead of covering PENDLE, LDO, JUP or CRV.
  const fart = FIXTURE.find(d => d.coin === "FARTCOIN");
  assert.equal(placeLabels([fart], { bounds: PLOT, others: FIXTURE.filter(d => d !== fart) }).has("FARTCOIN"), false);
});

test("labels: higher priority keeps its first choice", () => {
  const a = { coin: "AAA", x: 100, y: 100, r: 5 }, b = { coin: "BBB", x: 100, y: 112, r: 5 };
  const one = placeLabels([a, b], { width: 400, height: 300 });
  assert.equal(one.get("AAA").anchor, "start");
  assert.equal(one.get("BBB").anchor, "end");              // its right side is taken: it goes left
  const two = placeLabels([b, a], { width: 400, height: 300 });
  assert.equal(two.get("BBB").anchor, "start");
  assert.equal(two.get("BBB").x, 100 + 5 + 4);
  assert.equal(two.get("AAA").anchor, "end");
});

test("labels: hidden when there is no room", () => {
  // Boxed in by the plot edge on the right and by dots on the other three sides.
  const d = { coin: "PENDLE", x: 380, y: 100, r: 5 };
  const around = [{ coin: "L", x: 340, y: 100, r: 30 }, { coin: "U", x: 380, y: 70, r: 18 }, { coin: "D", x: 380, y: 130, r: 18 }];
  assert.equal(placeLabels([d], { width: 390, height: 300, others: around }).has("PENDLE"), false);
  // Two coins on the same spot in a thin plot: the first keeps its label, the second has none.
  const a = { coin: "AAAA", x: 60, y: 20, r: 8 }, b = { coin: "BBBB", x: 60, y: 20, r: 6 };
  const m = placeLabels([a, b], { width: 120, height: 40 });
  assert.equal(m.get("AAAA").anchor, "start");
  assert.equal(m.has("BBBB"), false);
});

test("labels: the followed coin always keeps its label", () => {
  // The same boxed-in coin as above: followed, it still gets a label, on the first side
  // clear of other labels (over a neighbour's dot) inside the plot.
  const d = { coin: "PENDLE", x: 380, y: 100, r: 5 };
  const around = [{ coin: "L", x: 340, y: 100, r: 30 }, { coin: "U", x: 380, y: 70, r: 18 }, { coin: "D", x: 380, y: 130, r: 18 }];
  const m = placeLabels([d], { width: 390, height: 300, others: around, force: "PENDLE" });
  assert.deepEqual(m.get("PENDLE"), { x: 371, y: 104, anchor: "end" });
  // Boxed in by fixed text too: it still shows, inside the plot.
  const walls = [{ x0: 0, y0: 0, x1: 390, y1: 300 }];
  const w = placeLabels([d], { width: 390, height: 300, others: around, avoid: walls, force: "PENDLE" }).get("PENDLE");
  assert.equal(w.anchor, "end");
  // FARTCOIN, boxed in by PENDLE, LDO, JUP and CRV, stays unlabelled unless followed;
  // followed, it keeps its label, and the other labels are placed around it.
  const dots = ["FARTCOIN", ...LABELLED.filter(c => c !== "FARTCOIN")].map(c => FIXTURE.find(x => x.coin === c));
  const others = FIXTURE.filter(x => !dots.includes(x));
  const placed = placeLabels(dots, { bounds: PLOT, others, force: "FARTCOIN" });
  assert.equal(placed.get("FARTCOIN").anchor, "start");
  const boxes = [...placed].map(([c, p]) => ({ c, ...labelBox(p.x, p.y, p.anchor, 6.4 * c.length + 4) }));
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    assert.ok(!(a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1), `${a.c} overlaps ${b.c}`);
  }
  // BTC sits on ETH: followed, it is labelled whatever else is around.
  const btc = FIXTURE.find(x => x.coin === "BTC");
  assert.ok(placeLabels([btc], { bounds: PLOT, others: FIXTURE.filter(x => x !== btc), force: "BTC" }).has("BTC"));
});

test("labels: small maps may cover a dot, never another label", () => {
  // A coin in a tight cluster: strict placement drops it, relaxed placement names it.
  const d = { coin: "TIA", x: 100, y: 100, r: 6 };
  const around = [{ coin: "A", x: 124, y: 100, r: 6 }, { coin: "B", x: 76, y: 100, r: 6 }, { coin: "C", x: 100, y: 80, r: 6 }, { coin: "D", x: 100, y: 118, r: 6 }];
  assert.equal(placeLabels([d], { width: 300, height: 300, others: around }).has("TIA"), false);
  assert.deepEqual(placeLabels([d], { width: 300, height: 300, others: around, relax: true }).get("TIA"), { x: 110, y: 104, anchor: "start" });
  // Only dots drawn under the label may be covered: A is drawn on top, so TIA goes left over B.
  const under = (_, o) => o.coin !== "A";
  assert.deepEqual(placeLabels([d], { width: 300, height: 300, others: around, relax: true, under }).get("TIA"), { x: 90, y: 104, anchor: "end" });
  // Nothing drawn under it: no label unless the coin is followed.
  assert.equal(placeLabels([d], { width: 300, height: 300, others: around, relax: true, under: () => false }).has("TIA"), false);
  assert.equal(placeLabels([d], { width: 300, height: 300, others: around, under: () => false, force: "TIA" }).get("TIA").anchor, "start");
  // Relaxed labels still never overlap each other.
  const e = { coin: "ENA", x: 100, y: 100, r: 6 };
  const m = placeLabels([d, e], { width: 140, height: 120, others: around, relax: true });
  const [pa, pb] = [m.get("TIA"), m.get("ENA")];
  if (pa && pb) {
    const a = labelBox(pa.x, pa.y, pa.anchor, 6.4 * 3 + 4), b = labelBox(pb.x, pb.y, pb.anchor, 6.4 * 3 + 4);
    assert.ok(!(a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1));
  }
  assert.ok(m.has("TIA"));
});

test("label order: focused, watched, mine, box by priority, lean, movers", () => {
  const c = (coin, o = {}) => ({ coin, zone: "outside", priority: 0, traders: { pl: 0, ps: 0 }, ...o });
  const coins = [c("MOV"), c("BIG", { traders: { pl: 20, ps: 0 } }), c("SMALL", { traders: { pl: 3, ps: 0 } }), c("BOX1", { zone: "watch", priority: 60 }),
    c("BOX2", { zone: "watch", priority: 70 }), c("MINE"), c("WAT"), c("FOC"), c("OFF")];
  const labelled = new Set(["MOV", "BIG", "SMALL", "BOX1", "BOX2", "MINE", "WAT"]);
  const order = labelOrder(coins, { labelled, focus: "FOC", watched: new Set(["WAT"]), mine: new Set(["MINE"]), movers: new Set(["MOV"]) }).map(x => x.coin);
  assert.deepEqual(order, ["FOC", "WAT", "MINE", "BOX2", "BOX1", "BIG", "SMALL", "MOV"]);
});

test("thumbnail extent: the trail and the box, padded", () => {
  const box = { z: [-0.5, 1.5], n: [1, 8] };
  const e = thumbExtent([], box);
  assert.deepEqual(e.x.map(v => +v.toFixed(3)), [-0.8, 1.8]);                     // 12% of 2 is 0.24: the 0.3 floor
  assert.deepEqual(e.y.map(v => +v.toFixed(3)), [+(symlog(1) - 0.3).toFixed(3), +(symlog(8) + 0.3).toFixed(3)]);
  const far = thumbExtent([{ z: -2, n: 0 }, { z: 3, n: 20 }], box);
  assert.deepEqual(far.x.map(v => +v.toFixed(3)), [-2.6, 3.6]);                   // span 5: 12% is 0.6
  assert.ok(far.y[0] < 0 && far.y[1] > symlog(20));
  // The box always shows: a tiny trail inside it still frames the whole box.
  const tiny = thumbExtent([{ z: 0.40, n: 1 }, { z: 0.45, n: 1 }], box);
  assert.ok(tiny.x[0] < -0.5 && tiny.x[1] > 1.5);
});

test("pulse line and Radar addresses", () => {
  assert.equal(pulseLine(null), null);
  assert.equal(pulseLine({ hours: 6, opens: 31, traders: 28, coins: 19 }), "Last 6h: 31 opens by 28 profitable traders, on 19 coins");
  assert.equal(pulseLine({ hours: 6, opens: 1, traders: 1, coins: 1 }), "Last 6h: 1 open by 1 profitable trader, on 1 coin");
  assert.equal(pulseLine({ hours: 6, opens: 0 }), "Last 6h: no opens by profitable traders");
  assert.equal(radarHref({ tf: "1d", focus: "TIA" }), "/radar?tf=1d&focus=TIA");
  assert.equal(radarHref({ tf: "4h", sector: "AI" }), "/radar?tf=4h&sector=AI");
  assert.equal(radarHref({ tf: "x", sector: "DeFi|Solana", view: "all" }), "/radar?tf=1d&sector=DeFi%7CSolana&view=all");
});
