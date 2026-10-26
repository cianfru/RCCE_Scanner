import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { computeTotals, positionsOf, marginRatio, tokenPrices, spotRows, worstMargin } from "./totals.js";

const fx = name => JSON.parse(readFileSync(new URL(`./__fixtures__/${name}.json`, import.meta.url), "utf8"));
const main = fx("ch"), xyz = fx("xyz"), dexs = fx("dexs"), spot = fx("spot"), spotMeta = fx("spotMeta"), mids = fx("allMids");
const delegator = fx("delegator"), vaults = fx("vaults"), earn = fx("earn"), portfolio = Object.fromEntries(fx("portfolio"));
const all = { main, dexs: { xyz, ...dexs }, spot, spotMeta, mids, earn, delegator, vaults };
// Hyperliquid's own total for the account at the same time (portfolio "day", last point).
const hlTotal = parseFloat(portfolio.day.accountValueHistory.at(-1)[1]);

test("release gate: the total matches Hyperliquid's within 0.5%", () => {
  const t = computeTotals(all);
  assert.ok(hlTotal > 100_000, `fixture total ${hlTotal}`);
  const off = Math.abs(t.equity - hlTotal) / hlTotal;
  assert.ok(off < 0.005, `equity ${t.equity.toFixed(2)} against Hyperliquid ${hlTotal} (${(off * 100).toFixed(3)}%)`);
  assert.equal(t.partial, false);
});

test("every part is counted: perps on all venues, spot at mid, earn, staked and vaults", () => {
  const t = computeTotals(all);
  assert.ok(Math.abs(t.parts.perps - 20426.886692) < 0.01);
  assert.ok(Math.abs(t.parts.tradfi - 12542.512615) < 0.01);
  assert.ok(t.parts.other > 759 && t.parts.other < 760);                 // para and vntl balances
  assert.ok(t.parts.spot > 48_000);                                       // UBTC valued at its @142 mid, not at cost
  assert.ok(t.parts.earn > 30_000);
  assert.ok(t.parts.staked > 8_000 && t.parts.vaults > 6_000);
});

test("withdrawable sums every perps venue, not the main one only", () => {
  const t = computeTotals(all);
  const each = [main, xyz, ...Object.values(dexs)].reduce((s, st) => s + (parseFloat(st.withdrawable) || 0), 0);
  assert.ok(Math.abs(t.withdrawable - each) < 1e-6);
  assert.ok(t.withdrawable > parseFloat(main.withdrawable) + 6000);
});

test("marginSummary, never crossMarginSummary: isolated margin is counted", () => {
  assert.ok(parseFloat(xyz.crossMarginSummary.accountValue) < parseFloat(xyz.marginSummary.accountValue));
  assert.equal(computeTotals(all).parts.tradfi, parseFloat(xyz.marginSummary.accountValue));
});

test("a failed venue gives partial and never a smaller number without saying so", () => {
  const full = computeTotals(all).equity;
  const t = computeTotals({ ...all, dexs: { ...dexs }, failed: ["TradFi"] });
  assert.equal(t.partial, true);
  assert.deepEqual(t.failed, ["TradFi"]);
  assert.ok(t.equity < full);
  // With the last good reading kept, the number stays and the partial mark still shows.
  const kept = computeTotals({ ...all, failed: ["TradFi"] });
  assert.equal(kept.partial, true);
  assert.equal(kept.equity, full);
});

test("unified accounts do not count spot USDC twice", () => {
  const a = spotRows(spot, spotMeta, mids).reduce((s, r) => s + r.usd, 0);
  const b = spotRows(spot, spotMeta, mids, { unified: true }).reduce((s, r) => s + r.usd, 0);
  assert.ok(Math.abs(a - b - 6792.10337308) < 1e-6);
});

test("token prices come from the @n pair against USDC", () => {
  const p = tokenPrices(spotMeta, mids);
  assert.equal(p.get(0), 1);
  assert.equal(p.get(150), parseFloat(mids["@107"]));
  assert.equal(p.get(197), parseFloat(mids["@142"]));
});

test("positions: mark from positionValue / |szi|, sides, isolated and funding sign", () => {
  const ps = positionsOf(main, "main");
  const hype = ps.find(p => p.coin === "HYPE");
  assert.ok(Math.abs(hype.mark - 29023.05 / 366.8) < 1e-9);
  assert.equal(hype.side, "long");
  assert.ok(hype.funding < 0);                                            // sinceOpen paid shows as a cost
  const uni = positionsOf(xyz, "xyz").find(p => p.coin === "xyz:UNITREE");
  assert.equal(uni.side, "short");
  assert.equal(uni.iso, true);
});

test("margin ratio per venue and the worst one", () => {
  const r = marginRatio(main);
  assert.ok(Math.abs(r - 1763.925235 / 20426.886692) < 1e-9);
  const t = computeTotals(all);
  assert.deepEqual(worstMargin(t.venues).venue, "main");
  assert.ok(t.openPnl !== 0);
});
