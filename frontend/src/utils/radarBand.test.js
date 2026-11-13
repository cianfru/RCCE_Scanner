import test from "node:test";
import assert from "node:assert/strict";
import { xDomain, bandChanges, bandVisible, crossed, heatCount, placeBandLabels, pctFromBand, trailDelta, zText } from "./radarBand.js";

const coin = (o = {}) => ({ coin: "X", traders: { pl: 0, ps: 0 }, band_z: { z: 0.5, days: [0.4, 0.5] }, heat_signs: {}, ...o });

test("heat count counts true signs only", () => {
  assert.equal(heatCount(coin({ heat_signs: { band: true, heat: false, funding: null, traders: true } })), 2);
  assert.equal(heatCount(coin({ heat_signs: undefined })), 0);
});

test("crossings read the last eight days", () => {
  assert.equal(crossed(coin({ band_z: { z: 0.2, days: [-0.3, -0.1, null, 0.2] } })), "up");
  assert.equal(crossed(coin({ band_z: { z: -0.2, days: [0.3, -0.2] } })), "down");
  assert.equal(crossed(coin({ band_z: { z: 0.2, days: [0.1, 0.2] } })), null);
  assert.equal(crossed(coin({ band_z: null })), null);
});

test("trail delta and the change lists", () => {
  assert.equal(trailDelta(coin({ trail: { n: [1, null, 4] } })), 3);
  const cs = [
    coin({ coin: "A", band_z: { z: 0.1, days: [-0.5, 0.1] } }),
    coin({ coin: "B", band_z: { z: 0.9, days: [-0.2, 0.9] } }),
    coin({ coin: "C", band_z: { z: -0.4, days: [0.2, -0.4] }, trail: { n: [0, 2] } }),
    coin({ coin: "D", band_z: { z: 2.0, days: [2, 2] }, heat_signs: { band: true, heat: true, funding: true } }),
  ];
  const ch = bandChanges(cs);
  assert.deepEqual(ch.up.map(c => c.coin), ["B", "A"]);
  assert.deepEqual(ch.down.map(c => c.coin), ["C"]);
  assert.deepEqual(ch.arriving.map(c => c.coin), ["C"]);
  assert.deepEqual(ch.hot.map(c => c.coin), ["D"]);
});

test("the default view keeps coins with traders, heat, a crossing or kept", () => {
  const cs = [coin({ coin: "Q" }), coin({ coin: "T", traders: { pl: 1, ps: 0 } }), coin({ coin: "K" }), coin({ coin: "N", band_z: null, traders: { pl: 3 } })];
  assert.deepEqual(bandVisible(cs, { keep: new Set(["K"]) }).map(c => c.coin), ["T", "K"]);
  assert.deepEqual(bandVisible(cs, { all: true }).map(c => c.coin), ["Q", "T", "K"]);
});

test("labels never overlap and stay inside", () => {
  const items = [0, 1, 2, 3, 4].map(k => ({ key: `k${k}`, x: 100, y: 100, r: 5, w: 40, h: 12, rank: k }));
  const pos = placeBandLabels(items, 300, 200);
  assert.equal(pos.size, 4);
  assert.equal(pos.get("k4").anchor, "start");
  assert.equal(placeBandLabels([{ key: "e", x: 2, y: 2, r: 3, w: 400, h: 12, rank: 1 }], 300, 200).size, 0);
  const one = [{ key: "a", x: 100, y: 100, r: 4, w: 30, h: 12, rank: 1 }];
  assert.equal(placeBandLabels(one, 300, 200, 24, [{ key: "big", x: 120, y: 100, r: 15 }]).get("a").anchor, "end");
  assert.equal(placeBandLabels(one, 300, 200, 24, [{ key: "a", x: 100, y: 100, r: 30 }]).get("a").anchor, "start");
});

test("texts", () => {
  assert.equal(zText(-1.24), "−1.2");
  assert.equal(zText(2), "+2.0");
  assert.equal(pctFromBand(42.3), "+42%");
  assert.equal(pctFromBand(-4.56), "−4.6%");
});

test("x range keeps the band and the 1.6 line in view", () => {
  assert.deepEqual(xDomain([-2.4, 0.58]), [-3, 2.5]);
  assert.deepEqual(xDomain([]), [-1.5, 2.5]);
  assert.deepEqual(xDomain([-9, 9, null]), [-3.5, 4]);
});

import { MAX_ZOOM, VIEW0, clampView, panBy, pinch, zoomAt } from "./radarBand.js";
const BOX = { x0: 40, x1: 440, y0: 10, y1: 310 };

test("zoom keeps the point under the cursor and stays in bounds", () => {
  const v = zoomAt(VIEW0, 2, 240, 160, BOX);
  assert.equal(v.k, 2);
  assert.equal(v.tx + 2 * 240, 240);                 // the plot point at 240 is still at 240
  assert.deepEqual(zoomAt(v, 0.5, 100, 100, BOX), VIEW0);
  assert.equal(zoomAt(VIEW0, 99, 0, 0, BOX).k, MAX_ZOOM);
});

test("panning cannot leave the plot", () => {
  const v = zoomAt(VIEW0, 2, 240, 160, BOX);
  const far = panBy(v, 5000, 5000, BOX);
  assert.equal(far.tx + 2 * BOX.x0, BOX.x0);         // left edge pinned at the plot's left
  assert.equal(far.ty + 2 * BOX.y0, BOX.y0);
  assert.deepEqual(panBy(VIEW0, 50, 50, BOX), VIEW0);  // nothing to pan at zoom 1
  assert.deepEqual(clampView({ k: 0.3, tx: 9, ty: 9 }, BOX), VIEW0);
});

test("a pinch scales by the fingers' distance around their midpoint", () => {
  const v = pinch(VIEW0, 100, { x: 200, y: 150 }, 300, { x: 200, y: 150 }, BOX);
  assert.equal(v.k, 3);
  assert.equal(v.tx + 3 * 200, 200);
  assert.equal(v.ty + 3 * 150, 150);
});
