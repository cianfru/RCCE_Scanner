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

// The row's reason, short. An emerging setup's reason is the engine's formula
// ("MARKUP + z=-0.02 + conf=11% + … [7.0/9 effective (78%) — insufficient]"); the row shows
// its count ("7 of 9 conditions, not enough yet") and keeps the formula for the tooltip.
export function oppReasonShort(reason) {
  const text = String(reason || "");
  const m = text.match(/\[(\d+(?:\.\d+)?)\/(\d+) effective[^\]]*\]/);
  if (!m) return text;
  const met = Number(m[1]), of = Number(m[2]);
  const count = `${Number.isInteger(met) ? met : met.toFixed(1)} of ${of} conditions`;
  return /insufficient/i.test(m[0]) ? `${count}, not enough yet` : count;
}
