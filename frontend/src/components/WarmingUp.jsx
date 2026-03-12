import { T, getBaseSymbol } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

export default function WarmingUp({ data, onSelect, isMobile }) {
  const warmingUp = data
    .filter(r => (r.conditions_met || 0) >= 6 && r.signal === "WAIT")
    .sort((a, b) => (b.conditions_met || 0) - (a.conditions_met || 0))
    .slice(0, 12);

  if (warmingUp.length === 0) return null;

  return (
    <FadeIn delay={460}>
      <GlassCard
        className="notable-scroll"
        style={{
          marginTop: isMobile ? 10 : 14, padding: isMobile ? "10px 14px" : "10px 18px",
          display: "flex", gap: isMobile ? 6 : 8, flexWrap: "nowrap",
          overflowX: "auto", WebkitOverflowScrolling: "touch",
          alignItems: "center", scrollbarWidth: "none", msOverflowStyle: "none",
        }}
      >
        <span style={{
          fontSize: 12, color: "#fbbf24", letterSpacing: "0.08em",
          fontFamily: T.font, fontWeight: 700, marginRight: 6,
          textTransform: "uppercase", flexShrink: 0,
          display: "flex", alignItems: "center", gap: 5,
        }}>
          {"\ud83d\udd25"} Warming Up
        </span>
        {warmingUp.map(r => (
          <span
            key={r.symbol}
            onClick={() => onSelect(r)}
            style={{
              padding: "4px 12px", borderRadius: "20px", cursor: "pointer",
              background: "rgba(251,191,36,0.06)",
              border: "1px solid rgba(251,191,36,0.15)",
              color: "#fbbf24", fontSize: 12, fontFamily: T.mono, fontWeight: 600,
              display: "inline-flex", alignItems: "center", gap: 6,
              transition: "all 0.2s ease", flexShrink: 0,
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(251,191,36,0.12)"; e.currentTarget.style.boxShadow = "0 0 12px rgba(251,191,36,0.1)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "rgba(251,191,36,0.06)"; e.currentTarget.style.boxShadow = "none"; }}
          >
            {getBaseSymbol(r.symbol)}
            <span style={{
              padding: "1px 5px", borderRadius: "10px",
              background: "rgba(251,191,36,0.15)",
              fontSize: 10, fontWeight: 700,
            }}>
              {r.conditions_met}/{r.conditions_total || 10}
            </span>
          </span>
        ))}
      </GlassCard>
    </FadeIn>
  );
}
