// Pure helpers for one trader row on a coin (Traders card, chart panel): relative time,
// size-bar scaling and where price sits against the trader's entry.

const MINUS = "−";

// A signed percentage with a true minus sign: "+1.2%", "−0.4%". digits: decimals.
export function signedPct(v, digits = 1) {
  if (v == null || !Number.isFinite(v)) return "—";
  const s = Math.abs(v).toFixed(digits);
  if (Number(s) === 0) return `${s}%`;
  return `${v > 0 ? "+" : MINUS}${s}%`;
}

// P&L on margin: one decimal under 10%, whole numbers above ("+9.6%", "+116%", "−29%").
export const pnlPct = v => signedPct(v, v != null && Math.abs(v) < 9.95 ? 1 : 0);

// "just now", "12m ago", "5h ago", "3d ago", "5w ago", "4mo ago". tSec: unix seconds.
export function timeAgo(tSec, nowMs = Date.now()) {
  if (!Number.isFinite(tSec)) return null;
  const m = Math.max(0, Math.floor((nowMs / 1000 - tSec) / 60));
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 28) return `${d}d ago`;
  if (d < 70) return `${Math.floor(d / 7)}w ago`;
  return `${Math.max(2, Math.floor(d / 30.44))}mo ago`;
}

// When a trader's position opened, as row text: "2d ago"; "over 19d ago" when the opening is
// older than the fills on hand (covered_from); "…" while loading; null when unknown.
export function openedAgo(tr, nowMs = Date.now()) {
  if (!tr || tr.pending) return tr ? "…" : null;
  if (tr.opened_at) return timeAgo(tr.opened_at, nowMs);
  if (tr.covered_from) {
    const t = timeAgo(tr.covered_from, nowMs);
    return t && t !== "just now" ? `over ${t}` : t;
  }
  return null;
}

// A position's share of the largest one in the list, for its size bar: 0..1, never thinner
// than `min` for a real position so the smallest still shows.
export function sizeShare(size, max, min = 0.03) {
  if (!(size > 0) || !(max > 0)) return 0;
  return Math.min(1, Math.max(min, size / max));
}

// Price against a trader's entry in percent (+1.2 = price is 1.2% above the entry); null
// without both prices.
export function priceVsEntry(entry, price) {
  if (!(entry > 0) || !(price > 0)) return null;
  return (price / entry - 1) * 100;
}

// The dim hint under an entry: "now +1.2%" ("at entry" within 0.05%); null without a price.
export function vsNowLabel(entry, price) {
  const d = priceVsEntry(entry, price);
  if (d == null) return null;
  return Math.abs(d) < 0.05 ? "at entry" : `now ${signedPct(d, Math.abs(d) < 10 ? 1 : 0)}`;
}
