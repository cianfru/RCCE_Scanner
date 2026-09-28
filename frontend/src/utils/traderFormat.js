// Shared wording for tracked traders (coin chart grid, Following tab).

import { col, isLightMode } from "../theme.js";

export const SIDE_COLOR = { long: "#7dd3fc", short: "#fda4af", exit: "#8b8f94" };
// Theme-aware side colour for rendered UI (light mode maps to a darker hue).
export const sideColor = s => col(SIDE_COLOR[s]);
// Split bars only: a deeper sky and pink in dark, so a bar reads its direction at a glance
// while staying off the profit and loss colours (light keeps the mapped side colours).
const SIDE_BAR_DARK = { long: "#38bdf8", short: "#fb7185" };
export const sideBarColor = s => (isLightMode() ? sideColor(s) : SIDE_BAR_DARK[s] || sideColor(s));

export const fmtPx = v => (v == null ? "—" : new Intl.NumberFormat("en", { maximumSignificantDigits: 5 }).format(v));
export const fmtUsd = v => (v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${Math.round(v / 1e3)}K` : `$${Math.round(v || 0)}`);
export const fmtWhen = t => new Date(t * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
export const shortAddr = a => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "");

// Plain sentence for one recorded change of a followed trader.
export function changeLine(e) {
  const verb = { open: "Opened", close: "Closed", add: "Added to", cut: "Cut" }[e.kind] || e.kind;
  const size = e.kind === "add" || e.kind === "cut" ? `${fmtUsd(e.delta_usd)}, now ${fmtUsd(e.usd)}` : fmtUsd(e.usd);
  return `${verb} ${e.side} ${e.coin} ${size} at ${fmtPx(e.px)}`;
}
