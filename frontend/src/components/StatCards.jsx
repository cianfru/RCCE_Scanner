import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

export default function StatCards({ results, isMobile, isTablet }) {
  const signals = { STRONG_LONG: 0, LIGHT_LONG: 0, ACCUMULATE: 0, TRIM: 0, TRIM_HARD: 0, RISK_OFF: 0 };
  results.forEach(r => { if (signals[r.signal] !== undefined) signals[r.signal]++; });

  const cards = [
    { label: "STRONG LONG", value: signals.STRONG_LONG, color: "#34d399" },
    { label: "LIGHT LONG",  value: signals.LIGHT_LONG,  color: "#6ee7b7" },
    { label: "ACCUMULATE",  value: signals.ACCUMULATE,   color: "#22d3ee" },
    { label: "TRIM",        value: signals.TRIM + signals.TRIM_HARD, color: "#fbbf24" },
    { label: "RISK-OFF",    value: signals.RISK_OFF,     color: "#f87171" },
  ];

  const gridCols = isMobile ? "repeat(2, 1fr)" : isTablet ? "repeat(3, 1fr)" : "repeat(5, 1fr)";

  return (
    <div style={{ display: "grid", gridTemplateColumns: gridCols, gap: isMobile ? 8 : 10, marginTop: isMobile ? 12 : 16 }}>
      {cards.map((c, i) => (
        <FadeIn key={c.label} delay={i * 60} style={isMobile && i === 4 ? { gridColumn: "1 / -1" } : undefined}>
          <GlassCard
            hoverable
            glow={c.value > 0 ? `${c.color}08` : null}
            style={{
              padding: isMobile ? "12px 14px" : "16px 18px",
              border: `1px solid ${c.value > 0 ? c.color + "22" : T.border}`,
              transition: "border-color 0.3s, box-shadow 0.3s",
            }}
          >
            <div style={{
              fontSize: isMobile ? 26 : 32, fontWeight: 700, fontFamily: T.mono,
              color: c.value > 0 ? c.color : T.text4,
              lineHeight: 1,
              filter: c.value > 0 ? `drop-shadow(0 0 8px ${c.color}30)` : "none",
            }}>
              {c.value}
            </div>
            <div style={{
              fontSize: 10, color: c.value > 0 ? T.text2 : T.text4,
              fontFamily: T.font, fontWeight: 600,
              letterSpacing: "0.1em", marginTop: 6,
              textTransform: "uppercase",
            }}>
              {c.label}
            </div>
          </GlassCard>
        </FadeIn>
      ))}
    </div>
  );
}
