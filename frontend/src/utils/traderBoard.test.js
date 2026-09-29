import test from "node:test";
import assert from "node:assert/strict";
import {
  addressFromPath, barIndex, chartTimeframe, coinStrip, fillMarks, fmtDuration, fmtMoney, fmtPnl, fmtRoi,
  isBuy, kindCounts, markRadius, profilePath, sizeBand, topCoins, tripRange,
} from "./traderBoard.js";

const ADDR = "0x91867345424fb158888ff9c5f1b1b2e7cd7d65d5";

test("profile route: lowercase full address only", () => {
  assert.equal(profilePath(ADDR.toUpperCase().replace("0X", "0x")), `/trader/${ADDR}`);
  assert.equal(addressFromPath(`/trader/${ADDR}`), ADDR);
  assert.equal(addressFromPath(`/trader/${ADDR}/`), ADDR);
  assert.equal(addressFromPath(`/trader/${ADDR.toUpperCase().replace("0X", "0x")}`), ADDR.toUpperCase().replace("0X", "0x"));
  for (const bad of ["/trader/0x123", "/trader/", `/trader/${ADDR}/extra`, "/traders/leaderboard", `/trader/${ADDR.slice(0, -1)}g`])
    assert.equal(addressFromPath(bad), null, bad);
});

test("money, PnL and ROI formats", () => {
  assert.equal(fmtMoney(1_589_095), "$1.59M");
  assert.equal(fmtMoney(12_400_000), "$12.4M");
  assert.equal(fmtMoney(482_300), "$482K");
  assert.equal(fmtPnl(1_589_095), "+$1.59M");
  assert.equal(fmtPnl(-24_342), "−$24K");
  assert.equal(fmtPnl(null), "—");
  assert.equal(fmtRoi(1133.5), "+1,134%");
  assert.equal(fmtRoi(-4.25), "−4.3%");
  assert.equal(fmtRoi(null), "—");
});

test("size bands match the API", () => {
  assert.deepEqual([null, 60e3, 300e3, 2e6, 20e6].map(sizeBand), [null, "$50K–250K", "$250K–1M", "$1M–10M", "$10M+"]);
});

test("coin strip: five logos and the rest as a count", () => {
  assert.deepEqual(coinStrip(["A", "B", "C", "D", "E", "F", "G"]), { shown: ["A", "B", "C", "D", "E"], more: 2 });
  assert.deepEqual(coinStrip(undefined), { shown: [], more: 0 });
});

test("durations", () => {
  assert.equal(fmtDuration(40), "40s");
  assert.equal(fmtDuration(12 * 60), "12m");
  assert.equal(fmtDuration(5 * 3600 + 20 * 60), "5h 20m");
  assert.equal(fmtDuration(3 * 86400 + 4 * 3600), "3d 4h");
  assert.equal(fmtDuration(45 * 86400), "45d");
});

test("chart timeframe and candle index", () => {
  const now = 1_000 * 86400;
  assert.equal(chartTimeframe(now - 10 * 86400, now), "4h");
  assert.equal(chartTimeframe(now - 200 * 86400, now), "1d");
  assert.equal(chartTimeframe(null, now), "1d");
  const times = [100, 200, 300];
  assert.deepEqual([50, 100, 199, 200, 999].map(t => barIndex(times, t)), [-1, 0, 0, 1, 2]);
});

test("fill marks: one per candle, kind and side, at the average price", () => {
  const times = [0, 3600, 7200];
  const fills = [
    { t: 10, kind: "open", side: "long", px: 100, sz: 1, usd: 100 },
    { t: 20, kind: "add", side: "long", px: 110, sz: 1, usd: 110 },
    { t: 30, kind: "add", side: "long", px: 130, sz: 3, usd: 390 },
    { t: 3700, kind: "trim", side: "long", px: 140, sz: 1, usd: 140, pnl: 30 },
    { t: 7300, kind: "flip", side: "short", px: 120, sz: 5, usd: 600 },
    { t: 7400, kind: "close", side: "short", px: 110, sz: 4, usd: 440 },
    { t: -5, kind: "open", side: "long", px: 1, sz: 1, usd: 1 },               // before the first candle
  ];
  const m = fillMarks(fills, times);
  assert.deepEqual(m.map(x => [x.index, x.kind, x.n]), [[0, "open", 1], [0, "add", 2], [1, "trim", 1], [2, "flip", 1], [2, "close", 1]]);
  assert.equal(m[1].px, 125);                                                  // (110 + 390) / 4
  assert.deepEqual(m.map(x => x.buy), [true, true, false, false, true]);
  assert.equal(m[2].pnl, 30);
});

test("buy or sell by kind and side", () => {
  assert.equal(isBuy("open", "long"), true);
  assert.equal(isBuy("add", "short"), false);
  assert.equal(isBuy("trim", "short"), true);
  assert.equal(isBuy("close", "long"), false);
  assert.equal(isBuy("flip", "long"), true);
});

test("mark radius grows with dollars, trims smaller", () => {
  assert.equal(markRadius(100, 100, "add"), 9);
  assert.equal(markRadius(0, 100, "add"), 3.5);
  assert.ok(markRadius(100, 100, "trim") < 9);
});

test("kind counts, trip range and top coins", () => {
  assert.deepEqual(kindCounts([{ kind: "add" }, { kind: "add" }, { kind: "trim" }]), { open: 0, add: 2, trim: 1, close: 0, flip: 0 });
  const r = tripRange({ opened_at: 10_000, closed_at: 20_000 }, 1e9);
  assert.equal(r.since, 9_940);
  assert.equal(r.until, 20_060);
  assert.ok(r.from < 10_000 && r.to > 20_000);
  assert.deepEqual(topCoins([{ coin: "BTC" }, { coin: "ETH" }, { coin: "ETH" }, { coin: "AAVE" }], 2), ["ETH", "AAVE"]);
});
