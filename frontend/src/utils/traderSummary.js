// Traders page: one row per coin for one wallet group (rows of /api/hyperlens/positioning).
import { LEAN_MIN_WALLETS, traderLean } from "./traders.js";

// A coin needs this many traders in the group to be listed before "Show more".
export const SUMMARY_MIN = LEAN_MIN_WALLETS;
export const TOP_WALLETS = 3;

const count = r => (r?.long?.n || 0) + (r?.short?.n || 0);
const dollars = r => (r?.long?.usd || 0) + (r?.short?.usd || 0);

// Most traders first, then most dollars; coins under SUMMARY_MIN go to `more`.
// A filter searches every coin, so a match under the minimum still shows.
export function summaryRows(rows, query = "") {
  const q = String(query || "").trim().toUpperCase();
  const all = (rows || []).filter(r => count(r) > 0 && (!q || String(r.coin).toUpperCase().includes(q)))
    .sort((a, b) => count(b) - count(a) || dollars(b) - dollars(a));
  if (q) return { shown: all, more: [] };
  return { shown: all.filter(r => count(r) >= SUMMARY_MIN), more: all.filter(r => count(r) < SUMMARY_MIN) };
}

// The side most of the group is on (by traders, then dollars): "long" or "short".
export function majoritySide(r) {
  const L = r?.long?.n || 0, S = r?.short?.n || 0;
  if (L !== S) return L > S ? "long" : "short";
  return (r?.short?.usd || 0) > (r?.long?.usd || 0) ? "short" : "long";
}

// Price against the larger side's median entry: { side, pct, entry, winning }, or null.
// winning: that side is in profit at the current price (longs above, shorts below).
export function entryGap(r) {
  const side = majoritySide(r);
  const entry = r?.[side]?.median_entry;
  if (!entry || !r?.mark) return null;
  const pct = (r.mark / entry - 1) * 100;
  return { side, pct, entry, winning: side === "long" ? pct > 0 : pct < 0 };
}

// Change in long and short traders since a day ago, or null when there is no record.
export function dayChange(r) {
  const d = r?.day_ago;
  if (!d) return null;
  return { long: (r.long?.n || 0) - (d.long || 0), short: (r.short?.n || 0) - (d.short || 0) };
}

// Coins by the group's side (at least 15% more on one side), over the listed coins.
export function sideCounts(rows) {
  const n = { long: 0, short: 0, mixed: 0 };
  for (const r of rows || []) {
    const s = traderLean({ long: r?.long?.n, short: r?.short?.n }).side;
    if (s) n[s] += 1;
  }
  return n;
}

// Long share of the group's dollars in a coin, 0..1, or null without dollars.
export function longDollarShare(r) {
  const t = dollars(r);
  return t > 0 ? (r.long?.usd || 0) / t : null;
}

// The dollars bar: long and short as shares of the track, the track being the largest coin's
// dollars in the list, so bar length compares coins and the colours split each one.
export function moneyBar(r, rows) {
  const max = Math.max(0, ...(rows || []).map(dollars));
  if (!max) return { long: 0, short: 0 };
  return { long: (r?.long?.usd || 0) / max, short: (r?.short?.usd || 0) / max };
}

// The group's largest wallets per side from /api/hyperlens/positions/{coin} rows.
// cohortTag: "money_printer" or "smart_money".
export function topWallets(positions, cohortTag, n = TOP_WALLETS) {
  const mine = (positions || []).filter(p => (p.cohorts || []).includes(cohortTag))
    .sort((a, b) => (b.size_usd || 0) - (a.size_usd || 0));
  const side = s => mine.filter(p => String(p.side).toUpperCase() === s);
  return { long: side("LONG").slice(0, n), short: side("SHORT").slice(0, n),
    longTotal: side("LONG").length, shortTotal: side("SHORT").length };
}

const MINUS = "−";
// "+2", "−1", "0".
export const fmtDelta = v => (v > 0 ? `+${v}` : v < 0 ? `${MINUS}${Math.abs(v)}` : "0");
// "+3.2%", "−0.4%": one decimal under 10%, none above.
export function fmtGap(pct) {
  if (pct == null || !isFinite(pct)) return "--";
  const a = Math.abs(pct);
  const s = a < 10 ? a.toFixed(1) : a.toFixed(0);
  if (Number(s) === 0) return "0.0%";
  return `${pct > 0 ? "+" : MINUS}${s}%`;
}
