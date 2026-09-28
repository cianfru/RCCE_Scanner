// Shared helpers for the compact opportunity rows inside "Market context & recent activity".

// Status word colours: confirmed reads as a go, blocked as a caution, invalidated as a miss;
// expired and unavailable stay grey. Hex values go through col() for the light theme.
export const OPP_STATUS_HEX = {
  confirmed: "#34d399",
  blocked: "#fbbf24",
  invalidated: "#cf9185",
};

export function oppStatusWord(status) {
  const s = String(status || "").replaceAll("_", " ");
  return s ? s[0].toUpperCase() + s.slice(1) : "—";
}

// Compact age: 45s, 12m, 3h, 2d.
export function ageShort(ts, now = Date.now() / 1000) {
  if (!Number.isFinite(ts)) return "";
  const d = Math.max(0, now - ts);
  if (d < 60) return `${Math.round(d)}s`;
  if (d < 3600) return `${Math.round(d / 60)}m`;
  if (d < 86400) return `${Math.round(d / 3600)}h`;
  return `${Math.round(d / 86400)}d`;
}
