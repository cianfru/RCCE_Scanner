// Account totals across every Hyperliquid venue (Portfolio v2, section 6.1).
// Equity = Σ perps accountValue over main, xyz and every other dex with a balance (marginSummary,
// never crossMarginSummary, which leaves isolated margin out) + spot balances at mid (spotMeta's @n
// pair; USDC = 1) + Earn supply minus borrow + staked HYPE (delegated, undelegated, pending) at the
// HYPE mid + vault equities. A failed venue feed makes the total "partial": the page never shows a
// silently smaller number.
import { num } from "./format.js";

export const PARTS = ["perps", "tradfi", "other", "spot", "earn", "staked", "vaults"];
const STABLE = new Set(["USDC"]);

// Token index -> USD price: USDC 1, others from the mid of their pair against USDC.
export function tokenPrices(spotMeta, mids) {
  const out = new Map([[0, 1]]);
  if (!spotMeta?.universe) return out;
  const usdc = spotMeta.tokens?.find(t => t.name === "USDC")?.index ?? 0;
  out.set(usdc, 1);
  for (const u of spotMeta.universe) {
    const [base, quote] = u.tokens || [];
    if (quote !== usdc || out.has(base)) continue;
    const m = num(mids?.[u.name]);
    if (m != null && m > 0) out.set(base, m);
  }
  return out;
}

export function spotRows(spot, spotMeta, mids, { unified = false } = {}) {
  const prices = tokenPrices(spotMeta, mids);
  const rows = [];
  for (const b of spot?.balances || []) {
    const total = num(b.total) || 0;
    if (!total) continue;
    if (unified && STABLE.has(b.coin)) continue;     // already inside the perps account value
    const p = STABLE.has(b.coin) ? 1 : prices.get(b.token);
    rows.push({ coin: b.coin, token: b.token, total, px: p ?? null, usd: p != null ? total * p : 0, priced: p != null });
  }
  return rows;
}

export function earnValue(earn, spotMeta, mids) {
  const prices = tokenPrices(spotMeta, mids);
  let v = 0;
  for (const [token, st] of earn?.tokenToState || []) {
    const p = prices.get(token);
    if (p == null) continue;
    v += ((num(st?.supply?.value) || 0) - (num(st?.borrow?.value) || 0)) * p;
  }
  return v;
}

export function stakedValue(delegator, hypeMid) {
  if (!delegator) return 0;
  const n = (num(delegator.delegated) || 0) + (num(delegator.undelegated) || 0) + (num(delegator.totalPendingWithdrawal) || 0);
  return n * (num(hypeMid) || 0);
}

export const vaultsValue = vaults => (vaults || []).reduce((s, v) => s + (num(v.equity) || 0), 0);
export const accountValue = state => num(state?.marginSummary?.accountValue) || 0;

// Maintenance margin over account value, per venue (Hyperliquid liquidates at 100%).
export function marginRatio(state) {
  const av = accountValue(state);
  const mm = num(state?.crossMaintenanceMarginUsed) || 0;
  return av > 0 ? mm / av : null;
}

// One venue's open positions, normalised. mark = positionValue / |szi| (Hyperliquid's own mark).
export function positionsOf(state, venue = "main") {
  const out = [];
  for (const ap of state?.assetPositions || []) {
    const p = ap.position || ap;
    const szi = num(p.szi) || 0;
    if (!szi) continue;
    const value = Math.abs(num(p.positionValue) || 0);
    out.push({
      coin: p.coin, venue, szi, side: szi > 0 ? "long" : "short", isLong: szi > 0,
      entry: num(p.entryPx), mark: value / Math.abs(szi), value,
      upnl: num(p.unrealizedPnl) || 0, roe: (num(p.returnOnEquity) || 0) * 100,
      liq: num(p.liquidationPx), lev: p.leverage?.value ?? null, iso: p.leverage?.type === "isolated",
      margin: num(p.marginUsed) || 0, funding: -(num(p.cumFunding?.sinceOpen) || 0),
    });
  }
  return out;
}

// states: { main, dexs: {xyz: state, para: state, ...} }; failed: feed names that did not answer
// ("Perps", "TradFi", "Other venues", "Spot", "Earn", "Staking", "Vaults").
export function computeTotals({ main, dexs = {}, spot, spotMeta, mids, earn, delegator, vaults, unified = false, failed = [] }) {
  const parts = { perps: accountValue(main), tradfi: accountValue(dexs.xyz), other: 0, spot: 0, earn: 0, staked: 0, vaults: 0 };
  let openPnl = 0;
  const venues = [];
  for (const [dex, st] of Object.entries(dexs)) {
    if (dex !== "xyz") parts.other += accountValue(st);
  }
  for (const [venue, st] of [["main", main], ...Object.entries(dexs)]) {
    if (!st) continue;
    const ps = positionsOf(st, venue);
    openPnl += ps.reduce((s, p) => s + p.upnl, 0);
    venues.push({ venue, value: accountValue(st), margin: marginRatio(st), positions: ps.length });
  }
  const sr = spotRows(spot, spotMeta, mids, { unified });
  parts.spot = sr.reduce((s, r) => s + r.usd, 0);
  parts.earn = earnValue(earn, spotMeta, mids);
  parts.staked = stakedValue(delegator, mids?.HYPE);
  parts.vaults = vaultsValue(vaults);
  const equity = PARTS.reduce((s, k) => s + parts[k], 0);
  return {
    equity, parts, openPnl, venues, spotRows: sr,
    withdrawable: num(main?.withdrawable) || 0,
    partial: failed.length > 0, failed: [...failed],
  };
}

// The worst venue's margin ratio: {ratio, venue}.
export function worstMargin(venues) {
  let best = null;
  for (const v of venues || []) if (v.margin != null && (best == null || v.margin > best.ratio)) best = { ratio: v.margin, venue: v.venue };
  return best;
}
