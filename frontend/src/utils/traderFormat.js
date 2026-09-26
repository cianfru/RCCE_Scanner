// Shared wording for tracked traders (coin chart grid, Following tab).

export const SIDE_COLOR = { long: "#7dd3fc", short: "#fda4af", exit: "#8b8f94" };

export const fmtPx = v => (v == null ? "—" : new Intl.NumberFormat("en", { maximumSignificantDigits: 5 }).format(v));
export const fmtUsd = v => (v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${Math.round(v / 1e3)}K` : `$${Math.round(v || 0)}`);
export const fmtWhen = t => new Date(t * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
export const shortAddr = a => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "");

// "3 buys, 1 sell" for a trader's bursts on this coin; buying/selling follows the position side.
export function activitySummary(bursts = []) {
  let buys = 0, sells = 0;
  for (const b of bursts) {
    const buy = (b.kind === "open") === (b.side === "long");
    if (buy) buys += 1; else sells += 1;
  }
  const part = (n, w) => (n ? `${n} ${w}${n > 1 ? "s" : ""}` : "");
  return [part(buys, "buy"), part(sells, "sell")].filter(Boolean).join(", ") || "no fills in range";
}

// The trader's other positions in one short line: the largest few, then a count.
export function holdingsLine(positions = [], max = 2) {
  if (!positions.length) return "nothing else";
  const top = positions.slice(0, max).map(p => `${p.side} ${p.coin} ${fmtUsd(p.size_usd)}`).join(", ");
  return positions.length > max ? `${top} +${positions.length - max}` : top;
}

// Plain sentence for one recorded change of a followed trader.
export function changeLine(e) {
  const verb = { open: "Opened", close: "Closed", add: "Added to", cut: "Cut" }[e.kind] || e.kind;
  const size = e.kind === "add" || e.kind === "cut" ? `${fmtUsd(e.delta_usd)}, now ${fmtUsd(e.usd)}` : fmtUsd(e.usd);
  return `${verb} ${e.side} ${e.coin} ${size} at ${fmtPx(e.px)}`;
}
