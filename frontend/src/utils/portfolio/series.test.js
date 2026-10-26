import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resample, nearestPoint, extremes, PERIOD_STEP } from "./series.js";

test("resample: equal steps by linear interpolation, ending on the last real point", () => {
  const pts = [{ time: 0, value: 0 }, { time: 100, value: 10 }, { time: 130, value: 40 }];
  const out = resample(pts, 25);
  assert.deepEqual(out.map(p => p.time), [0, 25, 50, 75, 100, 125, 130]);
  assert.equal(out[1].value, 2.5);
  assert.equal(out[5].value, 35);
  assert.equal(out.at(-1).value, 40);
  for (let i = 1; i < out.length - 1; i++) assert.equal(out[i].time - out[i - 1].time, 25);
});

test("resample: a grid aligned to the step, unsorted and bad points ignored", () => {
  const out = resample([{ time: 70, value: 7 }, { time: 10, value: 1 }, { time: 40, value: NaN }], 30);
  assert.deepEqual(out.map(p => p.time), [30, 60, 70]);
  assert.ok(Math.abs(out[0].value - 3) < 1e-12);
  assert.deepEqual(resample([{ time: 5, value: 1 }], 30), [{ time: 5, value: 1 }]);
});

test("the real month history: uneven spacing becomes 6 h steps", () => {
  const raw = JSON.parse(readFileSync(new URL("./__fixtures__/portfolio.json", import.meta.url), "utf8"));
  const month = (Array.isArray(raw) ? Object.fromEntries(raw) : raw).month;
  const pts = month.pnlHistory.map(([t, v]) => ({ time: Math.floor(t / 1000), value: parseFloat(v) }));
  const out = resample(pts, PERIOD_STEP.month);
  const gaps = new Set(out.slice(1, -1).map((p, i) => p.time - out[i].time));
  assert.deepEqual([...gaps], [PERIOD_STEP.month]);
  assert.equal(out.at(-1).value, pts.at(-1).value);
});

test("nearest point and extremes sit on drawn steps, with the raw values", () => {
  const drawn = [{ time: 0, value: 0 }, { time: 10, value: 5 }, { time: 20, value: 2 }];
  assert.equal(nearestPoint(drawn, 14).time, 10);
  assert.equal(nearestPoint(drawn, -1), null);
  const e = extremes([{ time: 0, value: 0 }, { time: 12, value: 9 }, { time: 19, value: -3 }], drawn);
  assert.deepEqual(e, { hi: { value: 9, time: 10 }, lo: { value: -3, time: 20 } });
});
