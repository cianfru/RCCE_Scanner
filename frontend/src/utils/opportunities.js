export const ENTRY_SIGNALS = new Set([
  "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
]);
export const EXIT_SIGNALS = new Set(["TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"]);
const ENTRY_RANK = { REVIVAL_SEED: 0, REVIVAL_SEED_CONFIRMED: 1, ACCUMULATE: 2, LIGHT_LONG: 3, STRONG_LONG: 4 };
const EXIT_RANK = { NO_LONG: 0, TRIM: 1, TRIM_HARD: 2, RISK_OFF: 3 };

export function selectOpportunity(r4, r1) {
  const valid = [r4, r1].filter(r => r && r.signal_status !== "unavailable");
  // Exit warnings never require matching entries or a second timeframe.
  const exits = valid.filter(r => EXIT_SIGNALS.has(r.signal));
  if (exits.length) {
    const primary = exits.reduce((a, b) => EXIT_RANK[a.signal] >= EXIT_RANK[b.signal] ? a : b);
    return { ...primary, crossTf: exits.length === 2, tf: exits.length === 2 ? "4H+1D" : primary.timeframe?.toUpperCase() };
  }
  if (valid.length !== 2) return null;
  if (valid.some(r => (ENTRY_SIGNALS.has(r.signal) || r.signal === "LIGHT_SHORT") && r.opportunity && r.opportunity.status !== "confirmed")) return null;
  // Consume the backend's final cross-timeframe decision when supplied.
  const unified = r4.unified_signal ?? r1.unified_signal;
  if (unified != null) {
    if (!ENTRY_SIGNALS.has(unified) && unified !== "LIGHT_SHORT") return null;
    const primary = valid.find(r => r.signal === unified) ?? r4;
    return { ...primary, signal: unified, crossTf: r4.signal !== "WAIT" && r1.signal !== "WAIT", tf: "4H+1D" };
  }
  if (ENTRY_SIGNALS.has(r4.signal) && ENTRY_SIGNALS.has(r1.signal)) {
    const primary = ENTRY_RANK[r4.signal] <= ENTRY_RANK[r1.signal] ? r4 : r1;
    return { ...primary, crossTf: true, tf: "4H+1D" };
  }
  if (r4.signal === "LIGHT_SHORT" && r1.signal === "LIGHT_SHORT") {
    return { ...r4, crossTf: true, tf: "4H+1D" };
  }
  return null;
}
