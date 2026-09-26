// Positioning map: where tracked traders are, next to what the engine says.

const ENGINE_LONG = new Set(["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"]);
const ENGINE_BEARISH = new Set(["TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG", "LIGHT_SHORT", "STRONG_SHORT"]);

// The engine's stance from one timeframe's reading: "long", "bearish" or "neutral".
export function engineSide(e) {
  if (!e) return null;
  if (ENGINE_LONG.has(e.signal)) return "long";
  if (ENGINE_BEARISH.has(e.signal) || e.regime === "MARKDOWN") return "bearish";
  return "neutral";
}

// Traders' side on a coin: needs at least two traders and a lean past 15%.
export const MAP_MIN_TRADERS = 2;
export function tradersSide(row) {
  const L = row?.long?.n || 0, S = row?.short?.n || 0, n = L + S;
  if (n < MAP_MIN_TRADERS) return null;
  const lean = (L - S) / n;
  return lean > 0.15 ? "long" : lean < -0.15 ? "short" : "mixed";
}

// "agree" when both point the same way, "opposed" when they point opposite ways, else null.
export function matchOf(row, tf = "4h") {
  const t = tradersSide(row), e = engineSide(row?.engine?.[tf]);
  if (!t || !e || t === "mixed" || e === "neutral") return null;
  if ((t === "long" && e === "long") || (t === "short" && e === "bearish")) return "agree";
  return "opposed";
}

// Price relative to a side's median entry, in percent (positive: price above the entry).
export function vsEntry(row, side) {
  const m = row?.[side]?.median_entry;
  return m && row.mark ? (row.mark / m - 1) * 100 : null;
}

export const MAP_FILTERS = {
  all: () => true,
  agree: r => matchOf(r) === "agree",
  opposed: r => matchOf(r) === "opposed",
  new: r => (r.opens_24h?.long || 0) + (r.opens_24h?.short || 0) > 0,
  converging: r => !!r.convergence,
};
