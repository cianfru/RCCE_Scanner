// Account totals across every Hyperliquid venue (Portfolio v2, section 6.1). The formula follows the
// account's mode (Hyperliquid's userAbstraction):
//
// Standard ("disabled", "default", and the discontinued "dexAbstraction"): separate perps, spot and
// dex balances. Equity = Σ perps accountValue over main, xyz and every other dex with a balance
// (marginSummary, never crossMarginSummary, which leaves isolated margin out) + spot balances at mid
// + Earn supply minus borrow + staked HYPE + vault equities.
//
// Unified account and portfolio margin: Hyperliquid keeps "all balances and holds" in the spot
// clearinghouse state and the per-dex perps states "are not meaningful" (docs, account abstraction
// modes). Equity = Σ spot balances at mid (USDC included, a negative total kept) + staked HYPE + vault
// equities; Earn is not added (supplied tokens are already in spot). Both match Hyperliquid's own
// account value (tests: one fixture per mode, from real accounts).
//
// Prices: USDC 1, other tokens at the mid of their pair against USDC (spotMeta), staked HYPE at the
// HYPE mid. A failed venue feed, a mode not read yet, or a balance with no price makes the total
// "partial" and names what is missing: the page never shows a silently smaller number.
import { num } from "./format.js";

export const PARTS = ["perps", "tradfi", "other", "spot", "earn", "staked", "vaults"];
const STABLE = new Set(["USDC"]);
export const SPOT_MODES = new Set(["unifiedAccount", "portfolioMargin"]);
// "standard", "unifiedAccount" or "portfolioMargin"; null while the mode is unknown.
export const modeKind = mode => (mode == null ? null : SPOT_MODES.has(mode) ? mode : "standard");

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

// Token name -> USD price (a fee is charged in a token named by feeToken).
export function pricesByName(spotMeta, mids) {
  const byIndex = tokenPrices(spotMeta, mids);
  const out = new Map([["USDC", 1]]);
  for (const t of spotMeta?.tokens || []) if (byIndex.has(t.index)) out.set(t.name, byIndex.get(t.index));
  return out;
}

export function spotRows(spot, spotMeta, mids) {
  const prices = tokenPrices(spotMeta, mids);
  const rows = [];
  for (const b of spot?.balances || []) {
    const total = num(b.total) || 0;
    if (!total) continue;
    const p = STABLE.has(b.coin) ? 1 : prices.get(b.token);
    rows.push({ coin: b.coin, token: b.token, total, px: p ?? null, usd: p != null ? total * p : 0, priced: p != null });
  }
  return rows;
}

// Earn supply minus borrow at mid; tokens with no price are listed in `unpriced`.
export function earnParts(earn, spotMeta, mids) {
  const prices = tokenPrices(spotMeta, mids);
  const names = new Map((spotMeta?.tokens || []).map(t => [t.index, t.name]));
  let v = 0;
  const unpriced = [];
  for (const [token, st] of earn?.tokenToState || []) {
    const n = (num(st?.supply?.value) || 0) - (num(st?.borrow?.value) || 0);
    if (!n) continue;
    const p = prices.get(token);
    if (p == null) { unpriced.push(names.get(token) || `#${token}`); continue; }
    v += n * p;
  }
  return { value: v, unpriced };
}
export const earnValue = (earn, spotMeta, mids) => earnParts(earn, spotMeta, mids).value;

export const stakedHype = delegator => (delegator ? (num(delegator.delegated) || 0) + (num(delegator.undelegated) || 0) + (num(delegator.totalPendingWithdrawal) || 0) : 0);
export function stakedValue(delegator, hypeMid) {
  return stakedHype(delegator) * (num(hypeMid) || 0);
}

export const vaultsValue = vaults => (vaults || []).reduce((s, v) => s + (num(v.equity) || 0), 0);
export const accountValue = state => num(state?.marginSummary?.accountValue) || 0;

// Standard mode, per venue: cross maintenance margin over the cross account value (Hyperliquid
// liquidates cross positions at 100%). Isolated margin is left out of the denominator: cross
// positions cannot use it.
export function marginRatio(state) {
  const av = num(state?.crossMarginSummary?.accountValue) || 0;
  const mm = num(state?.crossMaintenanceMarginUsed) || 0;
  if (av > 0) return mm / av;
  return mm > 0 ? Infinity : null;
}

// Unified account: Hyperliquid's unified account ratio (docs, computeUnifiedAccountRatio): per
// collateral token, Σ cross maintenance margin of the dexes using it over (spot total of the token −
// isolated margin on those dexes); the largest. states: [[dex, state]]; collateral: dex -> token index
// ("main" defaults to USDC, 0). null when a dex with margin in use has no known collateral token yet.
export function unifiedRatio(states, spot, collateral = new Map()) {
  const cross = new Map(), iso = new Map();
  for (const [dex, st] of states) {
    if (!st) continue;
    const mm = num(st.crossMaintenanceMarginUsed) || 0;
    const isoM = (st.assetPositions || []).reduce((s, ap) => s + (ap.position?.leverage?.type === "isolated" ? num(ap.position?.marginUsed) || 0 : 0), 0);
    if (!mm && !isoM) continue;
    const token = collateral.get(dex) ?? (dex === "main" ? 0 : undefined);
    if (token === undefined) return null;
    cross.set(token, (cross.get(token) || 0) + mm);
    iso.set(token, (iso.get(token) || 0) + isoM);
  }
  let max = 0;
  for (const [token, mm] of cross) {
    const total = num((spot?.balances || []).find(b => b.token === token)?.total) || 0;
    const available = total - (iso.get(token) || 0);
    if (available > 0) max = Math.max(max, mm / available);
  }
  return max;
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

// states: { main, dexs: {xyz: state, para: state, ...} }; mode: userAbstraction's answer (null while
// unknown); failed: feed names that did not answer ("Perps", "TradFi", "Other venues", "Spot", ...);
// collateral: dex -> collateral token (assetCtx), for the unified ratio.
export function computeTotals({ main, dexs = {}, spot, spotMeta, mids, earn, delegator, vaults, mode = "disabled", failed = [], collateral }) {
  const kind = modeKind(mode);
  const parts = { perps: 0, tradfi: 0, other: 0, spot: 0, earn: 0, staked: 0, vaults: 0 };
  const unpriced = [];
  let openPnl = 0;
  const states = [["main", main], ...Object.entries(dexs)];
  let positions = 0;
  for (const [venue, st] of states) {
    if (!st) continue;
    const ps = positionsOf(st, venue);
    positions += ps.length;
    openPnl += ps.reduce((s, p) => s + p.upnl, 0);
  }
  const sr = spotRows(spot, spotMeta, mids);
  for (const r of sr) if (!r.priced) unpriced.push(r.coin);
  parts.spot = sr.reduce((s, r) => s + r.usd, 0);
  const hype = num(mids?.HYPE);
  parts.staked = stakedValue(delegator, hype);
  if (stakedHype(delegator) > 0 && !(hype > 0)) unpriced.push("Staked HYPE");
  parts.vaults = vaultsValue(vaults);

  let venues;
  let withdrawable;
  if (kind === "standard" || kind == null) {
    parts.perps = accountValue(main);
    parts.tradfi = accountValue(dexs.xyz);
    for (const [dex, st] of Object.entries(dexs)) if (dex !== "xyz") parts.other += accountValue(st);
    const e = earnParts(earn, spotMeta, mids);
    parts.earn = e.value;
    unpriced.push(...e.unpriced);
    venues = states.filter(([, st]) => st).map(([venue, st]) => ({ venue, value: accountValue(st), margin: marginRatio(st), positions: positionsOf(st, venue).length }));
    // Every perps venue's withdrawable (main, xyz and the other builder dexes).
    withdrawable = [main, ...Object.values(dexs)].reduce((s, st) => s + (num(st?.withdrawable) || 0), 0);
  } else {
    const usdc = (spot?.balances || []).find(b => b.coin === "USDC");
    withdrawable = Math.max(0, (num(usdc?.total) || 0) - (num(usdc?.hold) || 0));
    // Portfolio margin has its own health measure, not shown here: no ratio rather than a wrong one.
    const ratio = kind === "unifiedAccount" ? unifiedRatio(states, spot, collateral) : null;
    venues = positions ? [{ venue: kind, value: null, margin: ratio, positions }] : [];
  }
  const equity = kind == null ? null : PARTS.reduce((s, k) => s + parts[k], 0);
  const missing = [...failed];
  return {
    equity, parts, openPnl, venues, spotRows: sr, withdrawable, mode: kind,
    unpriced: [...new Set(unpriced)],
    partial: kind == null || missing.length > 0 || unpriced.length > 0, failed: missing,
  };
}

// The worst venue's margin ratio: {ratio, venue}; null when no venue has one.
export function worstMargin(venues) {
  let best = null;
  for (const v of venues || []) if (v.margin != null && (best == null || v.margin > best.ratio)) best = { ratio: v.margin, venue: v.venue };
  return best;
}
