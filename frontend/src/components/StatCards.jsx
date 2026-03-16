import { T, m } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

export default function StatCards({ results, isMobile, isTablet, activeSignalFilter, onSignalFilter }) {
  const signals = { STRONG_LONG: 0, LIGHT_LONG: 0, ACCUMULATE: 0, TRIM: 0, TRIM_HARD: 0, RISK_OFF: 0 };
  results.forEach(r => { if (signals[r.signal] !== undefined) signals[r.signal]++; });

  const cards = [
    { label: "STRONG LONG", filterKey: "STRONG_LONG", value: signals.STRONG_LONG, color: T.green },
    { label: "LIGHT LONG",  filterKey: "LIGHT_LONG",  value: signals.LIGHT_LONG,  color: T.greenDim },
    { label: "ACCUMULATE",  filterKey: "ACCUMULATE",   value: signals.ACCUMULATE,   color: T.cyan },
    { label: "TRIM",        filterKey: "TRIM",         value: signals.TRIM + signals.TRIM_HARD, color: T.yellow },
    { label: "RISK-OFF",    filterKey: "RISK_OFF",     value: signals.RISK_OFF,     color: T.red },
  ];

  const gridCols = isMobile ? "repeat(2, 1fr)" : isTablet ? "repeat(3, 1fr)" : "repeat(5, 1fr)";

  return (
    <div style={{ display: "grid", gridTemplateColumns: gridCols, gap: isMobile ? 8 : 8, marginTop: isMobile ? T.sp3 : T.sp3 }}>
      {cards.map((c, i) => {
        const isActive = activeSignalFilter === c.filterKey;
        return (
          <FadeIn key={c.label} delay={i * 60} style={isMobile && i === 4 ? { gridColumn: "1 / -1" } : undefined}>
            <GlassCard
              hoverable
              glow={c.value > 0 ? `${c.color}08` : null}
              style={{
                padding: isMobile ? "12px 14px" : "12px 16px",
                border: `1px solid ${isActive ? c.color + "60" : c.value > 0 ? c.color + "22" : T.border}`,
                transition: "border-color 0.3s, box-shadow 0.3s",
                cursor: c.value > 0 ? "pointer" : "default",
                boxShadow: isActive ? `0 0 16px ${c.color}20, inset 0 0 0 1px ${c.color}30` : "none",
              }}
              onClick={() => {
                if (c.value === 0) return;
                onSignalFilter?.(isActive ? null : c.filterKey);
              }}
            >
              <div style={{
                fontSize: isMobile ? 26 : 26, fontWeight: 700, fontFamily: T.mono,
                color: c.value > 0 ? c.color : T.text4,
                lineHeight: 1,
                filter: c.value > 0 ? `drop-shadow(0 0 8px ${c.color}30)` : "none",
              }}>
                {c.value}
              </div>
              <div style={{
                fontSize: m(T.textSm, isMobile), color: isActive ? c.color : c.value > 0 ? T.text2 : T.text4,
                fontFamily: T.font, fontWeight: 600,
                letterSpacing: "0.08em", marginTop: T.sp1,
                textTransform: "uppercase",
              }}>
                {c.label}
              </div>
            </GlassCard>
          </FadeIn>
        );
      })}
    </div>
  );
}
