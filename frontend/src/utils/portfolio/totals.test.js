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

// Real accounts in each mode (data review, 27 Oct 2026; addresses left out): the page's total against
// Hyperliquid's own account value (portfolio "day", last point) read at the same time.
const modeFx = name => {
  const d = fx(`modes/${name}`);
  return { d, args: { main: d.main, dexs: { xyz: d.xyz, ...d.others }, spot: d.spot, spotMeta: d.spotMeta, mids: d.mids, earn: d.earn,
    delegator: d.delegator, vaults: d.vaults, mode: d.abstraction, collateral: new Map([["main", 0], ["xyz", 0]]) }, hl: parseFloat(d.hlAccountValue) };
};

test("unified accounts: every balance is in spot; the perps states are not added", () => {
  for (const name of ["unified-a", "unified-b"]) {
    const { d, args, hl } = modeFx(name);
    assert.equal(d.abstraction, "unifiedAccount");
    const t = computeTotals(args);
    const off = Math.abs(t.equity - hl) / hl;
    assert.ok(off < 0.005, `${name}: equity ${t.equity.toFixed(0)} against Hyperliquid ${hl} (${(off * 100).toFixed(2)}%)`);
    assert.equal(t.parts.perps + t.parts.tradfi + t.parts.other + t.parts.earn, 0);
    assert.equal(t.partial, false);
    // The standard formula on the same reads: perps plus USDC counted twice (the bug this replaces).
    const wrong = computeTotals({ ...args, mode: "disabled" }).equity;
    assert.ok(Math.abs(wrong - hl) / hl > 0.25, `${name}: the standard formula should be far off`);
  }
  // Withdrawable: spot USDC total minus hold.
  const { d, args } = modeFx("unified-a");
  const usdc = d.spot.balances.find(b => b.coin === "USDC");
  assert.ok(Math.abs(computeTotals(args).withdrawable - (parseFloat(usdc.total) - parseFloat(usdc.hold))) < 1e-6);
});

test("unified accounts: the margin bar is Hyperliquid's unified account ratio", () => {
  const { d, args } = modeFx("unified-a");
  const t = computeTotals(args);
  const cross = parseFloat(d.main.crossMaintenanceMarginUsed) + parseFloat(d.xyz.crossMaintenanceMarginUsed);
  const iso = [d.main, d.xyz].flatMap(s => s.assetPositions).filter(ap => ap.position.leverage.type === "isolated").reduce((s, ap) => s + parseFloat(ap.position.marginUsed), 0);
  const usdc = parseFloat(d.spot.balances.find(b => b.coin === "USDC").total);
  const w = worstMargin(t.venues);
  assert.equal(w.venue, "unifiedAccount");
  assert.ok(Math.abs(w.ratio - cross / (usdc - iso)) < 1e-12);
  assert.ok(w.ratio > 0.019 && w.ratio < 0.022, `ratio ${w.ratio}`);                    // 2.1%, not the per-venue 8.2%
  // A dex with margin in use and no collateral token known yet: no ratio rather than a wrong one.
  assert.equal(worstMargin(computeTotals({ ...args, collateral: new Map() }).venues), null);
});

test("portfolio margin: spot at mid, staked and vaults; Earn not added; no margin ratio", () => {
  const { d, args, hl } = modeFx("portfolio-margin");
  assert.equal(d.abstraction, "portfolioMargin");
  const t = computeTotals(args);
  const off = Math.abs(t.equity - hl) / hl;
  assert.ok(off < 0.005, `equity ${t.equity.toFixed(0)} against Hyperliquid ${hl} (${(off * 100).toFixed(2)}%)`);
  assert.equal(t.parts.earn, 0);
  assert.ok(t.spotRows.some(r => r.coin === "USDC" && r.total < 0));                     // the USDC borrow is kept
  assert.equal(worstMargin(t.venues), null);
});

test("the account mode: unknown means no number; default and disabled are standard", () => {
  const unknown = computeTotals({ ...all, mode: null });
  assert.equal(unknown.equity, null);
  assert.equal(unknown.partial, true);
  for (const mode of ["disabled", "default", "dexAbstraction"]) assert.equal(computeTotals({ ...all, mode }).equity, computeTotals(all).equity);
});

test("a balance with no price makes the total partial and names it", () => {
  const t = computeTotals({ ...all, mids: {} });
  assert.equal(t.partial, true);
  assert.ok(t.unpriced.includes("HYPE") && t.unpriced.includes("Staked HYPE"), JSON.stringify(t.unpriced));
  const noMeta = computeTotals({ ...all, spotMeta: null });
  assert.equal(noMeta.partial, true);
  assert.ok(noMeta.unpriced.includes("UBTC"));
});

test("standard accounts: the margin ratio leaves isolated margin out", () => {
  const r = marginRatio(xyz);
  assert.equal(r, 0);                                                                    // every xyz position is isolated
  const fake = { ...xyz, crossMaintenanceMarginUsed: "680.48" };
  assert.ok(Math.abs(marginRatio(fake) - 680.48 / parseFloat(xyz.crossMarginSummary.accountValue)) < 1e-12);
});

test("spot rows: USDC at 1 and a negative total kept", () => {
  const rows = spotRows({ balances: [{ coin: "USDC", token: 0, total: "-10" }] }, spotMeta, mids);
  assert.deepEqual(rows.map(r => [r.coin, r.usd]), [["USDC", -10]]);
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
