import { T, m, SIGNAL_META, getBaseSymbol } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

// Entry signals that show conditions progress
const ENTRY_SIGNALS = new Set([
  "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
]);

// Exit / risk signals
const EXIT_SIGNALS = new Set([
  "TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG",
]);

/**
 * Unified signal bar — merges Notable + WarmingUp into one row.
 *
 * Shows all actionable signals (entry + exit) across both timeframes,
 * deduped and sorted by priority. Each chip is self-descriptive:
 * symbol + signal type + timeframe + conditions (for entry signals).
 */
export default function SignalBar({ data4h, data1d, onSelect, isMobile }) {
  // Collect all actionable signals from both timeframes
  const ACTIONABLE = new Set([
    "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE",
    "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
    "TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG",
  ]);

  const chips = [];
  const seen = new Set();

  // Helper to add chips from a dataset
  const collect = (data, tf) => {
    for (const r of data) {
      if (!ACTIONABLE.has(r.signal)) continue;
      const key = `${r.symbol}-${tf}`;
      if (seen.has(key)) continue;
      seen.add(key);
      chips.push({ ...r, tf });
    }
  };

  collect(data4h, "4H");
  collect(data1d, "1D");

  // Sort: exit signals first (urgent), then by priority score desc
  chips.sort((a, b) => {
    const aExit = EXIT_SIGNALS.has(a.signal) ? 0 : 1;
    const bExit = EXIT_SIGNALS.has(b.signal) ? 0 : 1;
    if (aExit !== bExit) return aExit - bExit;
    return (b.priority_score || 0) - (a.priority_score || 0);
  });

  if (chips.length === 0) return null;

  // Compact signal labels
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

  return (
    <FadeIn delay={420}>
      <div style={{ position: "relative", marginTop: isMobile ? T.sp2 : T.sp3 }}>
        <GlassCard
          className="notable-scroll"
          style={{
            padding: isMobile ? "8px 12px" : "8px 16px",
            display: "flex",
            gap: isMobile ? 6 : 8,
            flexWrap: "nowrap",
            overflowX: "auto",
            WebkitOverflowScrolling: "touch",
            alignItems: "center",
            scrollbarWidth: "none",
            msOverflowStyle: "none",
          }}
        >
          <span style={{
            fontSize: m(T.textSm, isMobile),
            color: T.text3,
            letterSpacing: "0.1em",
            fontFamily: T.font,
            fontWeight: 700,
            marginRight: 6,
            textTransform: "uppercase",
            flexShrink: 0,
          }}>
            SIGNALS
          </span>

          {chips.slice(0, 16).map(r => {
            const sm = SIGNAL_META[r.signal] || SIGNAL_META.WAIT;
            const isEntry = ENTRY_SIGNALS.has(r.signal);
            const showCond = isEntry && r.conditions_met != null;

            return (
              <span
                key={`${r.symbol}-${r.tf}`}
                onClick={() => onSelect(r)}
                style={{
                  padding: isMobile ? "6px 12px" : "4px 10px",
                  borderRadius: "20px",
                  cursor: "pointer",
                  background: `${sm.color}10`,
                  border: `1px solid ${sm.color}20`,
                  color: sm.color,
                  fontSize: m(T.textSm, isMobile),
                  fontFamily: T.mono,
                  fontWeight: 600,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  transition: "all 0.2s ease",
                  flexShrink: 0,
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = `${sm.color}18`;
                  e.currentTarget.style.boxShadow = `0 0 10px ${sm.color}15`;
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = `${sm.color}10`;
                  e.currentTarget.style.boxShadow = "none";
                }}
              >
                {/* Symbol name */}
                {getBaseSymbol(r.symbol)}

                {/* Signal type */}
                <span style={{
                  fontSize: m(T.textXs, isMobile),
                  opacity: 0.7,
                  fontWeight: 700,
                  letterSpacing: "0.04em",
                }}>
                  {SIGNAL_SHORT[r.signal] || r.signal}
                </span>

                {/* Conditions badge (entry signals only) */}
                {showCond && (
                  <span style={{
                    padding: "1px 5px",
                    borderRadius: "10px",
                    background: `${sm.color}18`,
                    fontSize: m(T.textXs, isMobile),
                    fontWeight: 700,
                  }}>
                    {r.conditions_met}/{r.conditions_total || 10}
                  </span>
                )}

                {/* Timeframe tag */}
                <span style={{
                  fontSize: m(T.textXs, isMobile),
                  opacity: 0.4,
                }}>
                  {r.tf}
                </span>
              </span>
            );
          })}
        </GlassCard>

        {/* Fade edge on mobile */}
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
