// Compact dollars for glanceable figures: "$1.24M", "$840K", "$12.3K", "$950".
// Three significant digits, trailing zeros dropped ("$40M" on a chart axis), a leading
// minus for losses and, with { sign: true }, a plus for gains. "—" when there is no number.
const UNITS = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];

function trim(s) {
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

export function compactUsd(v, { sign = false } = {}) {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (n == null || !Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  let body = null;
  for (let i = 0; i < UNITS.length; i++) {
    const [size, unit] = UNITS[i];
    if (abs < size) continue;
    const scaled = abs / size;
    const txt = trim(scaled.toPrecision(3));
    // 999,999 rounds to "1000K": move up a unit.
    body = parseFloat(txt) >= 1000 && i > 0
      ? `${trim((abs / UNITS[i - 1][0]).toPrecision(3))}${UNITS[i - 1][1]}`
      : `${txt}${unit}`;
    break;
  }
  if (body == null) {
    const r = abs >= 1 ? Math.round(abs) : Math.round(abs * 100) / 100;
    body = r >= 1000 ? "1K" : String(r);
  }
  const zero = parseFloat(body) === 0;
  const lead = zero ? "" : n < 0 ? "-" : sign ? "+" : "";
  return `${lead}$${body}`;
}
