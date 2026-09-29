import test from "node:test";
import assert from "node:assert/strict";
import { WATCH_MESSAGES, at, inBox, isAddress, labelBox, labelOrder, movement, movers, newEarly, enteredAt, sinceText, tradersLine, picks, placeLabels, pnl, radarHref, symlog, thumbExtent, trailPoints, visible, watchReason, watchToast, forwardLine } from "./setupMap.js";

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

test("thumbnail extent: zoomed to the trail; a near box edge joins, a far one does not", () => {
  const box = { z: [-0.5, 1.5], n: [1, 8] };
  const r3 = v => v.map(x => +x.toFixed(3));
  const frac = (e, lo, hi) => (hi - lo) / (e[1] - e[0]);
  // No trail: the box itself, padded 14%.
  assert.deepEqual(r3(thumbExtent([], box).x), [-0.78, 1.78]);
  // A long trail sets the scale; the box edges sit inside it.
  assert.deepEqual(r3(thumbExtent([{ z: -2, n: 0 }, { z: 3, n: 20 }], box).x), [-2.7, 3.7]);
  // A small trail far from the box edges: the box does not set the scale (the old fit framed the
  // whole box and left a 4px squiggle), and the trail takes most of the width.
  const aztec = [0.13, 0.212, 0.222, 0.238, 0.281].map(z => ({ z, n: 2 }));
  const e = thumbExtent(aztec, box);
  assert.ok(e.x[0] > -0.5 && e.x[1] < 1.5);
  assert.ok(frac(e.x, 0.13, 0.281) >= 0.45);
  // Flat trader count: the minimum span centres it; the box floor (n 1) is close, so it shows.
  assert.ok(e.y[0] < symlog(1) && e.y[1] < symlog(8));
  assert.ok(symlog(2) > e.y[0] && symlog(2) < e.y[1]);
  // A trail that moved at least minZ spans at least half the view even when a box edge joins.
  const tia = [[0.342, 0], [0.616, 0], [0.65, 0], [0.583, 1], [0.594, 1]].map(([z, n]) => ({ z, n }));
  const t = thumbExtent(tia, box);
  assert.ok(frac(t.x, 0.342, 0.65) >= 0.5);
  assert.ok(t.y[1] >= symlog(1));               // it climbed onto the box floor: the edge shows
  const near = thumbExtent([{ z: 1.0, n: 3 }, { z: 1.4, n: 3 }], box);
  assert.ok(near.x[1] > 1.5);                   // the right edge 0.1 away joins the view
  assert.ok(frac(near.x, 1.0, 1.4) >= 0.5);
  // A still coin: one point, centred in a minimum-size view.
  const one = thumbExtent([{ z: 0.4, n: 1 }], box);
  assert.ok(Math.abs((one.x[0] + one.x[1]) / 2 - 0.4) < 1e-9 && one.x[1] - one.x[0] < 0.4);
});

test("Radar addresses", () => {
  assert.equal(radarHref({ tf: "1d", focus: "TIA" }), "/radar?tf=1d&focus=TIA");
  assert.equal(radarHref({ tf: "4h", sector: "AI" }), "/radar?tf=4h&sector=AI");
  assert.equal(radarHref({ tf: "x", sector: "DeFi|Solana", view: "all" }), "/radar?tf=1d&sector=DeFi%7CSolana&view=all");
});

test("new early setups: newest first, never a coin that sat in the box all along", () => {
  const cs = [
    coin({ coin: "OLD", trail: { t: [1, 2, 3, 4], z: [0.5, 0.5, 0.5, 0.5], n: [3, 3, 3, 3] } }),          // in the box all along
    coin({ coin: "EARLY", priority: 10, trail: { t: [1, 2, 3, 4], z: [2.5, 1.0, 1.0, 1.0], n: [3, 3, 3, 3] } }),
    coin({ coin: "LATEST", priority: 1, trail: { t: [1, 2, 3, 4], z: [2.5, 2.5, 2.5, 1.0], n: [3, 3, 3, 3] } }),
    coin({ coin: "LATE2", priority: 5, trail: { t: [1, 2, 3, 4], z: [0.5, 0.5, 0.5, 1.0], n: [0, 0, 0, 3] } }),
    coin({ coin: "OUT", zone: "late" }),
  ];
  assert.deepEqual(newEarly(cs, BOX).map(c => c.coin), ["LATE2", "LATEST", "EARLY"]);
  assert.deepEqual(newEarly(cs, BOX, 1).map(c => c.coin), ["LATE2"]);
});

test("labels: a big bubble takes its name inside, unless a smaller one covers it", () => {
  const big = { coin: "BTC", x: 100, y: 100, r: 30, core: 28 };
  const at1 = placeLabels([big], { width: 400, height: 400, insideMin: 13 }).get("BTC");
  assert.deepEqual(at1, { x: 100, y: 104, anchor: "middle", inside: true });
  const eth = { coin: "ETH", x: 104, y: 100, r: 10 };
  const at2 = placeLabels([big], { width: 400, height: 400, insideMin: 13, others: [eth] }).get("BTC");
  assert.notEqual(at2.inside, true);
  const small = { coin: "LONGNAMECOIN", x: 100, y: 100, r: 14 };
  assert.notEqual(placeLabels([small], { width: 400, height: 400, insideMin: 13 }).get("LONGNAMECOIN").inside, true);
});

test("new early setups: when each came into the box, and the list line", () => {
  const early = coin({ coin: "EARLY", trail: { t: [100, 200, 300, 400], z: [2.5, 1.0, 1.0, 1.0], n: [3, 3, 3, 3] } });
  assert.equal(enteredAt(early, BOX), 200);
  assert.equal(enteredAt(coin({ trail: { t: [1, 2], z: [0.5, 0.5], n: [3, 3] } }), BOX), null);   // in all along
  assert.equal(enteredAt(coin({ zone: "late" }), BOX), null);
  assert.equal(enteredAt(coin({ trail: { t: [1, 2], z: [2.5, 2.5], n: [3, 3] } }), BOX), 2);       // the server says in: the latest step
  assert.equal(sinceText(1000, 1000 + 1800), "now");
  assert.equal(sinceText(0, 8 * 3600 + 5), "8h");
  assert.equal(sinceText(0, 47 * 3600), "47h");
  assert.equal(sinceText(0, 72 * 3600), "3d");
  assert.equal(sinceText(null, 5), "");
  const usd = v => `$${v}`;
  assert.equal(tradersLine({ traders: { pl: 2, ps: 1 }, money: { gross_usd: 5 } }, usd), "3 traders · $5");
  assert.equal(tradersLine({ traders: { pl: 1, ps: 0 } }, usd), "1 trader");
});

test("forward test line: days logged and scored events against the minimum", () => {
  assert.equal(forwardLine(null), "");
  assert.equal(forwardLine({ days_logged: 0, H1: { scored: 0 }, min_events: 30 }), "Forward test: logging from the next daily close.");
  assert.equal(forwardLine({ days_logged: 1, H1: { scored: 1 }, min_events: 30 }), "Forward test: 1 day logged, 1 event scored (needs 30).");
  assert.equal(forwardLine({ days_logged: 12, H1: { scored: 3 }, min_events: 30 }), "Forward test: 12 days logged, 3 events scored (needs 30).");
});
