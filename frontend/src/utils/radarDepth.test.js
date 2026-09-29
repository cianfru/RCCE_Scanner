import test from "node:test";
import assert from "node:assert/strict";
import { bandInfo, beeswarm, bubbleRadius, candidates, fmtUsd, haloRing, ladderCounts, ladderDomain, ladderRadius, legendSizes, logScale,
  maxMoney, moneyMode, niceTicks, pctText, sameSpot, shortAddr, shortSlice, spreadLabels, stepPick, topWallets, traderPath, walletPnl } from "./radarDepth.js";

const coin = (gross, share = 1, o = {}) => ({ coin: "X", money: { gross_usd: gross, long_usd: gross * share, short_usd: gross * (1 - share), net_long_share: gross ? share : null }, ...o });

test("bubble area is proportional to the dollars", () => {
  const G = 100e6;
  const a = bubbleRadius(coin(100e6), G, 30), b = bubbleRadius(coin(25e6), G, 30);
  assert.equal(a, 30);
  assert.ok(Math.abs((b * b) / (a * a) - 0.25) < 1e-9);            // a quarter of the money, a quarter of the area
  assert.equal(bubbleRadius(coin(1), G, 30), 3.2);                  // any money: at least 3.2px
  assert.equal(bubbleRadius(coin(0), G, 30), 2);                    // none: the small grey dot
  assert.equal(bubbleRadius({ coin: "Y" }, G, 30), 2);
  assert.equal(maxMoney([coin(5), coin(9), { coin: "Z" }]), 9);
  assert.equal(moneyMode([{ coin: "A" }]), false);
  assert.equal(moneyMode([{ coin: "A" }, coin(0)]), true);
});

test("size key: three round amounts under the largest", () => {
  const k = legendSizes(83e6, 30);
  assert.deepEqual(k.map(x => x.v), [1e6, 5e6, 25e6]);
  assert.ok(k.every(x => x.r <= 30));
  assert.deepEqual(legendSizes(0, 30), []);
});

test("short slice: from 2% on 8px bubbles, from 40% on smaller ones", () => {
  assert.equal(shortSlice(10, 0.99), null);
  assert.match(shortSlice(10, 0.9), /^M0,0 L0,-9\.50 A9\.50,9\.50 0 0 1 /);
  assert.equal(shortSlice(5, 0.7), null);
  assert.match(shortSlice(5, 0.5), / 0 0 1 /);
  assert.match(shortSlice(20, 0.2), / 0 1 1 /);                     // more than half short: the large arc
  assert.equal(shortSlice(20, null), null);
});

test("band halo: fill, violet inside or under now, red on a weekly close under", () => {
  const band = { lo: 90, hi: 100, week_close: 110 };
  const a = bandInfo(band, 115);
  assert.equal(a.state, "above"); assert.equal(a.tone, "halo"); assert.ok(Math.abs(a.fill - 0.5) < 1e-9);
  assert.equal(a.text, "+15.0% above the band");
  assert.equal(bandInfo(band, 140).fill, 0);                         // 30%+ above: empty
  assert.equal(bandInfo(band, 100).fill, 1);                         // at the top edge: full
  assert.deepEqual([bandInfo(band, 95).state, bandInfo(band, 95).tone], ["inside", "violet"]);
  const u = bandInfo({ ...band, week_close: 95 }, 85);
  assert.deepEqual([u.state, u.tone, u.tick, u.fill], ["under_now", "violet", true, 1]);
  assert.equal(u.text, "−5.6% under the band now · last close inside");
  const r = bandInfo({ ...band, week_close: 85 }, 120);              // the weekly close decides red
  assert.deepEqual([r.state, r.tone, r.fill], ["closed_under", "red", 1]);
  assert.equal(bandInfo(null, 10).tone, "none");
  assert.equal(bandInfo({ lo: null, hi: null }, 10).text, "no weekly band");
});

test("halo ring: tiny bubbles only from half full, inside or under", () => {
  const half = bandInfo({ lo: 90, hi: 100, week_close: 110 }, 115), low = bandInfo({ lo: 90, hi: 100, week_close: 110 }, 125);
  assert.equal(haloRing(4, half).show, true);
  assert.equal(haloRing(4, low).show, false);                        // tiny and under half: no ring
  assert.equal(haloRing(4, bandInfo({ lo: 90, hi: 100, week_close: 85 }, 95)).show, true);
  assert.equal(haloRing(4, half).track, false);                      // no empty track under 8px
  const big = haloRing(20, low);
  assert.equal(big.track, true); assert.equal(big.sw, 2.2);
  assert.ok(Math.abs(big.arc - low.fill * big.C) < 1e-9);
  assert.equal(haloRing(20, bandInfo(null, 1)).show, false);
  assert.equal(haloRing(20, bandInfo(null, 1)).outer, 20);
});

test("picking: nearest centre, small bubble inside a big one, empty coins last", () => {
  const items = [{ coin: "BTC", x: 100, y: 100, r: 30 }, { coin: "ETH", x: 110, y: 95, r: 12 }, { coin: "DOT", x: 104, y: 100, r: 2, empty: true },
    { coin: "TAO", x: 200, y: 200, r: 3 }];
  assert.deepEqual(candidates(items, 110, 96).map(i => i.coin), ["ETH", "BTC", "DOT"]);
  assert.deepEqual(candidates(items, 85, 100).map(i => i.coin), ["BTC"]);             // DOT is 19px away
  assert.deepEqual(candidates(items, 100, 100).map(i => i.coin), ["ETH", "BTC", "DOT"]);
  assert.deepEqual(candidates(items, 203, 201).map(i => i.coin), ["TAO"]);
  assert.deepEqual(candidates(items, 300, 300), []);
  assert.deepEqual(candidates(items, 218, 200, { touch: true }).map(i => i.coin), ["TAO"]);
});

test("click to step through stacked coins", () => {
  const list = [{ coin: "ETH" }, { coin: "BTC" }];
  const a = stepPick(list, 10, 10, null, null);
  assert.equal(a.coin, "ETH");
  const b = stepPick(list, 12, 11, a.last, "ETH");
  assert.equal(b.coin, "BTC");
  assert.equal(stepPick(list, 13, 11, b.last, "BTC").coin, "ETH");    // wraps
  assert.equal(stepPick(list, 60, 60, b.last, "ETH").coin, "BTC");    // elsewhere, first already followed
  assert.equal(stepPick([{ coin: "ETH" }], 10, 10, null, "ETH").coin, "ETH");
  assert.equal(stepPick([], 1, 1, null, null).coin, null);
  const pos = new Map([["A", { x: 0, y: 0 }], ["B", { x: 3, y: 4 }], ["C", { x: 10, y: 0 }]]);
  assert.deepEqual(sameSpot(pos, "A"), ["B"]);                       // 5px apart: the same spot
  assert.deepEqual(sameSpot(pos, "A", 4), []);
  assert.deepEqual(sameSpot(pos, "Q"), []);
});

test("ladder scale: log range with price, band, mean and clamped entries", () => {
  const d = ladderDomain(100, { band: { lo: 70, hi: 75 }, mean: 72, entries: [90, 110, 5000] });
  assert.ok(d.lo < 70 && d.hi > 400 && d.hi < 460);                  // 5000 clamped to price * 4
  const far = ladderDomain(100, { mean: 1000 });                     // a mean 10x away is left out
  assert.ok(far.hi < 110);
  const Y = logScale(10, 1000, 0, 100);
  assert.ok(Math.abs(Y(100) - 50) < 1e-9); assert.equal(Y(1000), 0); assert.equal(Y(1), 100);
  assert.deepEqual(niceTicks(62000, 88000, 6), [65000, 70000, 75000, 80000, 85000]);
  assert.deepEqual(niceTicks(1, 1, 6), []);
});

test("beeswarm: no overlaps, deterministic, inside the column", () => {
  const rows = Array.from({ length: 30 }, (_, i) => ({ i, y: 100 + 3 * i, r: 3 + (i % 4) }));
  const a = beeswarm(rows, 50, 40), b = beeswarm(rows, 50, 40);
  assert.deepEqual(a, b);
  for (const p of a) assert.ok(Math.abs(p.x - 50) <= 40);
  let overlaps = 0;
  for (let i = 0; i < a.length; i++) for (let j = i + 1; j < a.length; j++) if (Math.hypot(a[i].x - a[j].x, a[i].y - a[j].y) < a[i].r + a[j].r) overlaps++;
  assert.equal(overlaps, 0);
  assert.equal(beeswarm([{ y: 5, r: 4 }], 20, 10)[0].x, 20);
  assert.equal(ladderRadius(100, 100), 14);
  assert.equal(ladderRadius(1, 1e9), 2.4);
  assert.ok(ladderRadius(100, 100, { dense: 50 }) < 14);
});

test("labels spread apart and the formats", () => {
  assert.deepEqual(spreadLabels([{ y: 10, t: "a" }, { y: 15, t: "b" }, { y: 50, t: "c" }]).map(l => l.y), [10, 22, 50]);
  assert.equal(fmtUsd(82_812_000), "$82.8M");
  assert.equal(fmtUsd(250_000_000), "$250M");
  assert.equal(fmtUsd(55_400), "$55K");
  assert.equal(fmtUsd(0), "$0");
  assert.equal(fmtUsd(-1500), "−$2K");
  assert.equal(pctText(0.1301), "+13.0%");
  assert.equal(pctText(-0.02, 0), "−2%");
  assert.equal(shortAddr("0x93ab7dbdeb996806454de19c35c8247f4b2511f8"), "0x93ab...11f8");
  assert.deepEqual(ladderCounts({ traders: { pl: 3, ps: 1 }, money: { long_usd: 9, short_usd: 2 } }, null), { long: 3, short: 1, long_usd: 9, short_usd: 2 });
  assert.deepEqual(ladderCounts({}, { counts: { long: 1, short: 0, long_usd: 5, short_usd: 0 } }).long_usd, 5);
});

test("ladder wallets: profile address, the largest first, P&L on margin", () => {
  assert.equal(traderPath("0x93AB7dbdeb996806454DE19c35c8247f4b2511F8"), "/trader/0x93ab7dbdeb996806454de19c35c8247f4b2511f8");
  const ws = [{ address: "0xb", size_usd: 5 }, { address: "0xa", size_usd: 5 }, { address: "0xc", size_usd: 9 }, { address: "0xd" }];
  assert.deepEqual(topWallets(ws, 3).map(w => w.address), ["0xc", "0xa", "0xb"]);
  assert.deepEqual(topWallets(null), []);
  assert.equal(walletPnl({ roe: 12, move: 3 }), 0.12);
  assert.equal(walletPnl({ move: -3 }), -0.03);
  assert.equal(walletPnl({}), null);
});
