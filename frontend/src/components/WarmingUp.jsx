import { T, m, getBaseSymbol, SIGNAL_META } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

// Entry signals that indicate the asset is building toward conviction
const ENTRY_SIGNALS = new Set([
  "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED",
]);

export default function WarmingUp({ data, onSelect, isMobile }) {
  const warmingUp = data
    .filter(r => {
      // ① Must already have a light entry signal — WAIT = no trade
      if (!ENTRY_SIGNALS.has(r.signal)) return false;
      // ② Not overheated — heat below 75 means room to run
      if ((r.heat ?? 0) >= 75) return false;
      // ③ Not in climax/blow-off exhaustion
      if (r.exhaustion_state === "CLIMAX") return false;
      // ④ Momentum not in freefall (allow mild pullbacks)
      if ((r.momentum ?? 0) < -5) return false;
      return true;
    })
    .sort((a, b) => {
      // Primary: conditions met (desc) — closer to STRONG_LONG upgrade
      const condDiff = (b.conditions_met || 0) - (a.conditions_met || 0);
      if (condDiff !== 0) return condDiff;
      // Tiebreak: priority score (desc)
      return (b.priority_score || 0) - (a.priority_score || 0);
    })
    .slice(0, 10);

  if (warmingUp.length === 0) return null;

  return (
    <FadeIn delay={460}>
      <div style={{ position: "relative", marginTop: isMobile ? T.sp2 : T.sp2 }}>
        <GlassCard
          className="notable-scroll"
          style={{
            padding: isMobile ? "8px 12px" : "8px 16px",
            display: "flex", gap: isMobile ? 6 : 8, flexWrap: "nowrap",
            overflowX: "auto", WebkitOverflowScrolling: "touch",
            alignItems: "center", scrollbarWidth: "none", msOverflowStyle: "none",
          }}
        >
          <span style={{
            fontSize: m(T.textSm, isMobile), color: T.yellow, letterSpacing: "0.08em",
            fontFamily: T.font, fontWeight: 700, marginRight: 6,
            textTransform: "uppercase", flexShrink: 0,
            display: "flex", alignItems: "center", gap: 5,
          }}>
            {"\ud83d\udd25"} Warming Up
          </span>
          {warmingUp.map(r => {
            const sm = SIGNAL_META[r.signal] || SIGNAL_META.WAIT;
            return (
              <span
                key={r.symbol}
                onClick={() => onSelect(r)}
                style={{
                  padding: isMobile ? "6px 14px" : "4px 12px", borderRadius: "20px", cursor: "pointer",
                  background: `${sm.color}10`,
                  border: `1px solid ${sm.color}20`,
                  color: sm.color, fontSize: m(T.textSm, isMobile), fontFamily: T.mono, fontWeight: 600,
                  display: "inline-flex", alignItems: "center", gap: 6,
                  transition: "all 0.2s ease", flexShrink: 0,
                }}
                onMouseEnter={e => { e.currentTarget.style.background = `${sm.color}18`; e.currentTarget.style.boxShadow = `0 0 10px ${sm.color}15`; }}
                onMouseLeave={e => { e.currentTarget.style.background = `${sm.color}10`; e.currentTarget.style.boxShadow = "none"; }}
              >
                {getBaseSymbol(r.symbol)}
                <span style={{
                  padding: "1px 5px", borderRadius: "10px",
                  background: `${sm.color}18`,
                  fontSize: m(T.textXs, isMobile), fontWeight: 700,
                }}>
                  {r.conditions_met}/{r.conditions_total || 10}
                </span>
              </span>
            );
          })}
        </GlassCard>
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
