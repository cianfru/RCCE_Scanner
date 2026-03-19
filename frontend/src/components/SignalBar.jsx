import { useState, useMemo } from "react";
import { T, m, SIGNAL_META, getBaseSymbol } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

const ENTRY_SIGNALS = new Set([
  "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
]);
const EXIT_SIGNALS = new Set([
  "TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG",
]);
const ALL_ACTIONABLE = new Set([
  "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE",
  "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
  "TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG",
]);

const SIGNAL_SHORT = {
  STRONG_LONG: "STRONG",
  LIGHT_LONG: "LIGHT",
  ACCUMULATE: "ACCUM",
  REVIVAL_SEED: "SEED",
  REVIVAL_SEED_CONFIRMED: "SEED+",
  TRIM: "TRIM",
  TRIM_HARD: "TRIM!",
  RISK_OFF: "RISK OFF",
  NO_LONG: "NO LONG",
};

/**
 * Compute a confluence score (0–7) for a scan result.
 *
 * Each independent engine / factor that agrees with the signal adds +1:
 *   1. Strong RCCE conditions (≥ 60% met)
 *   2. OI trend confirms direction
 *   3. Heat in the right zone
 *   4. Exhaustion engine confirms
 *   5. Cross-timeframe agreement (4H + 1D same direction) — set externally
 *   6. CVD confirms direction (taker buy flow)
 *   7. Spot dominance confirms (organic demand)
 */
export function computeConfluence(r, crossTfMatch = false) {
  let score = 0;
  const isExit = EXIT_SIGNALS.has(r.signal);
  const positioning = r.positioning || {};
  const oi  = positioning.oi_trend  || "";
  const fr  = positioning.funding_regime || "NEUTRAL";
  const met = r.conditions_met   ?? 0;
  const tot = Math.max(r.conditions_total ?? 10, 1);
  const heat = r.heat ?? 50;

  // 1. RCCE conditions (≥ 60% of RCCE conditions satisfied)
  if (met / tot >= 0.6) score++;

  // 2. OI confirms direction
  if (isExit) {
    if (["LIQUIDATING", "SQUEEZE"].includes(oi) || fr === "CROWDED_LONG") score++;
  } else {
    // entry: OI building alongside price, or crowd is short (squeeze potential)
    if (["BUILDING", "STABLE"].includes(oi) || fr === "CROWDED_SHORT") score++;
  }

  // 3. Heat zone
  if (isExit) {
    if (heat > 70) score++;
  } else {
    if (heat < 60) score++;
  }

  // 4. Exhaustion engine
  if (isExit) {
    if (r.is_climax) score++;
  } else {
    if (r.floor_confirmed || r.is_absorption) score++;
  }

  // 5. Cross-timeframe agreement (caller sets this)
  if (crossTfMatch) score++;

  // 6. CVD confirms direction (taker buy/sell flow)
  if (isExit) {
    if (r.cvd_trend === "BEARISH") score++;
  } else {
    if (r.cvd_trend === "BULLISH") score++;
  }

  // 7. Spot dominance confirms (organic demand, not leverage-driven)
  if (positioning.spot_dominance === "SPOT_LED") score++;

  return score;
}

/**
 * Unified signal bar — CROSS-TIMEFRAME ONLY.
 *
 * Only shows coins where BOTH 4H and 1D agree on signal direction.
 * Single-TF signals are suppressed — they produce too much noise.
 *
 * Confluence filter (applied on top of the cross-TF requirement):
 *   HIGH (≥4): strong multi-engine alignment — very few, highest quality
 *   MED  (≥3): solid alignment — manageable set
 *   ALL:       all cross-TF matches regardless of confluence
 */
export default function SignalBar({ data4h, data1d, onSelect, isMobile }) {
  const [filter, setFilter] = useState("MED"); // HIGH | MED | ALL

  const { chips, hiddenCount } = useMemo(() => {
    const map4h = new Map();
    const map1d = new Map();
    for (const r of data4h) if (ALL_ACTIONABLE.has(r.signal)) map4h.set(r.symbol, r);
    for (const r of data1d) if (ALL_ACTIONABLE.has(r.signal)) map1d.set(r.symbol, r);

    const rawChips = [];

    // Cross-timeframe matches only — both TFs must agree on direction
    for (const [sym, r4] of map4h) {
      const r1 = map1d.get(sym);
      if (!r1) continue;
      const bothExit   = EXIT_SIGNALS.has(r4.signal)   && EXIT_SIGNALS.has(r1.signal);
      const bothEntry  = ENTRY_SIGNALS.has(r4.signal)  && ENTRY_SIGNALS.has(r1.signal);
      const bothStrong = r4.signal === "STRONG_LONG"   && r1.signal === "STRONG_LONG";
      if (!bothExit && !bothEntry && !bothStrong) continue;

      // Use whichever TF has the stronger signal (higher priority score)
      const primary = (r4.priority_score || 0) >= (r1.priority_score || 0) ? r4 : r1;
      rawChips.push({
        ...primary,
        tf: "4H+1D",
        crossTf: true,
        confluence: computeConfluence(primary, true),
      });
    }

    // Sort: exits first, then confluence desc, then priority_score desc
    rawChips.sort((a, b) => {
      const aExit = EXIT_SIGNALS.has(a.signal) ? 0 : 1;
      const bExit = EXIT_SIGNALS.has(b.signal) ? 0 : 1;
      if (aExit !== bExit) return aExit - bExit;
      if (b.confluence !== a.confluence) return b.confluence - a.confluence;
      return (b.priority_score || 0) - (a.priority_score || 0);
    });

    // Apply confluence filter (all are already cross-TF confirmed)
    const minScore = filter === "HIGH" ? 4 : filter === "MED" ? 3 : 0;
    const visible = rawChips.filter(c => c.confluence >= minScore);
    const hidden  = rawChips.length - visible.length;

    return { chips: visible.slice(0, 15), hiddenCount: hidden };
  }, [data4h, data1d, filter]);

  if (chips.length === 0 && hiddenCount === 0) return null;

  const FILTER_OPTIONS = ["HIGH", "MED", "ALL"];
  const FILTER_LABELS  = { HIGH: "●●●●+", MED: "●●●+", ALL: "4H+1D" };

  return (
    <FadeIn delay={420}>
      <div style={{ position: "relative", marginTop: isMobile ? T.sp2 : T.sp3 }}>
        <GlassCard
          className="notable-scroll"
          style={{
            padding: isMobile ? "6px 10px" : "6px 14px",
            display: "flex",
            gap: isMobile ? 5 : 7,
            flexWrap: "nowrap",
            overflowX: "auto",
            WebkitOverflowScrolling: "touch",
            alignItems: "center",
            scrollbarWidth: "none",
            msOverflowStyle: "none",
          }}
        >
          {/* Label */}
          <span style={{
            fontSize: m(T.textSm, isMobile),
            color: T.text3,
            letterSpacing: "0.1em",
            fontFamily: T.font,
            fontWeight: 700,
            textTransform: "uppercase",
            flexShrink: 0,
            marginRight: 2,
          }}>
            4H+1D
          </span>

          {/* Filter toggles */}
          <div style={{ display: "flex", gap: 3, flexShrink: 0, marginRight: 4 }}>
            {FILTER_OPTIONS.map(opt => {
              const active = filter === opt;
              return (
                <button
                  key={opt}
                  onClick={() => setFilter(opt)}
                  style={{
                    padding: "2px 7px",
                    borderRadius: 10,
                    border: `1px solid ${active ? T.accent : T.border}`,
                    background: active ? `${T.accent}18` : "transparent",
                    color: active ? T.accent : T.text4,
                    fontSize: 10,
                    fontFamily: T.mono,
                    fontWeight: 700,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                    letterSpacing: "0.04em",
                  }}
                >
                  {FILTER_LABELS[opt]}
                </button>
              );
            })}
          </div>

          {/* Divider */}
          <div style={{ width: 1, height: 18, background: T.border, flexShrink: 0 }} />

          {/* Chips */}
          {chips.length === 0 ? (
            <span style={{ fontSize: 11, fontFamily: T.mono, color: T.text4, fontStyle: "italic" }}>
              No 4H+1D confirmed signals at this confluence level
            </span>
          ) : chips.map(r => {
            const sm = SIGNAL_META[r.signal] || SIGNAL_META.WAIT;
            const isEntry = ENTRY_SIGNALS.has(r.signal);
            const showCond = isEntry && r.conditions_met != null;

            return (
              <span
                key={`${r.symbol}-${r.tf}`}
                onClick={() => onSelect(r)}
                title={`Confluence: ${r.confluence}/7 | Priority: ${r.priority_score}`}
                style={{
                  padding: isMobile ? "5px 10px" : "3px 9px",
                  borderRadius: "20px",
                  cursor: "pointer",
                  background: r.crossTf ? `${sm.color}18` : `${sm.color}10`,
                  border: `1px solid ${r.crossTf ? sm.color + "50" : sm.color + "20"}`,
                  color: sm.color,
                  fontSize: m(T.textSm, isMobile),
                  fontFamily: T.mono,
                  fontWeight: 600,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  transition: "all 0.2s ease",
                  flexShrink: 0,
                  boxShadow: r.crossTf ? `0 0 8px ${sm.color}18` : "none",
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = `${sm.color}22`;
                  e.currentTarget.style.boxShadow = `0 0 10px ${sm.color}20`;
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = r.crossTf ? `${sm.color}18` : `${sm.color}10`;
                  e.currentTarget.style.boxShadow = r.crossTf ? `0 0 8px ${sm.color}18` : "none";
                }}
              >
                {/* Symbol */}
                {getBaseSymbol(r.symbol)}

                {/* Signal type */}
                <span style={{ fontSize: m(T.textXs, isMobile), opacity: 0.7, fontWeight: 700, letterSpacing: "0.04em" }}>
                  {SIGNAL_SHORT[r.signal] || r.signal}
                </span>

                {/* Conditions badge (entry signals) */}
                {showCond && (
                  <span style={{
                    padding: "1px 4px", borderRadius: "10px",
                    background: `${sm.color}18`,
                    fontSize: m(T.textXs, isMobile), fontWeight: 700,
                  }}>
                    {r.conditions_met}/{r.conditions_total || 10}
                  </span>
                )}

                {/* Confluence dots */}
                <span style={{ fontSize: 8, opacity: 0.65, letterSpacing: "-1px" }}>
                  {"●".repeat(r.confluence)}{"○".repeat(7 - r.confluence)}
                </span>

                {/* Timeframe tag */}
                <span style={{
                  fontSize: m(T.textXs, isMobile),
                  opacity: r.crossTf ? 0.85 : 0.4,
                  fontWeight: r.crossTf ? 700 : 400,
                }}>
                  {r.tf}
                </span>
              </span>
            );
          })}

          {/* Hidden count pill */}
          {hiddenCount > 0 && (
            <span
              onClick={() => setFilter("ALL")}
              style={{
                padding: "2px 8px", borderRadius: 12, flexShrink: 0,
                border: `1px solid ${T.border}`,
                fontSize: 10, fontFamily: T.mono, color: T.text4,
                cursor: "pointer", whiteSpace: "nowrap",
              }}
              title="Click to show all signals"
            >
              +{hiddenCount} more
            </span>
          )}
        </GlassCard>

        {/* Right fade edge */}
        <div style={{
          position: "absolute", top: 1, right: 1, bottom: 1,
          width: 32, borderRadius: "0 13px 13px 0",
          background: "linear-gradient(90deg, transparent, rgba(10,10,12,0.85))",
          pointerEvents: "none",
        }} />
      </div>
    </FadeIn>
  );
}
