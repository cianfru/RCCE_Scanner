import { T, m, SIGNAL_META, getBaseSymbol } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

export default function NotableSignals({ notable4h, notable1d, onSelect, isMobile }) {
  if (notable4h.length === 0 && notable1d.length === 0) return null;

  return (
    <FadeIn delay={420}>
      <div style={{ position: "relative", marginTop: isMobile ? T.sp2 : T.sp3 }}>
        <GlassCard
          className="notable-scroll"
          style={{
            padding: isMobile ? "8px 12px" : "8px 16px",
            display: "flex",
            gap: isMobile ? 6 : 8,
            flexWrap: isMobile ? "nowrap" : "wrap",
            overflowX: isMobile ? "auto" : "visible",
            WebkitOverflowScrolling: "touch",
            alignItems: "center",
            scrollbarWidth: "none",
            msOverflowStyle: "none",
          }}
        >
          <span style={{
            fontSize: m(T.textSm, isMobile), color: T.text3, letterSpacing: "0.1em",
            fontFamily: T.font, fontWeight: 700, marginRight: 6,
            textTransform: "uppercase",
            flexShrink: 0,
          }}>
            Notable
          </span>
          {[...notable4h.map(r => ({ ...r, tf: "4H" })), ...notable1d.map(r => ({ ...r, tf: "1D" }))]
            .filter((r, i, a) => a.findIndex(x => x.symbol === r.symbol && x.tf === r.tf) === i)
            .slice(0, 14)
            .map(r => {
              const sm = SIGNAL_META[r.signal] || SIGNAL_META.WAIT;
              return (
                <span
                  key={`${r.symbol}-${r.tf}`}
                  onClick={() => onSelect(r)}
                  style={{
                    padding: isMobile ? "6px 14px" : "4px 12px", borderRadius: "20px", cursor: "pointer",
                    background: `${sm.color}10`, border: `1px solid ${sm.color}20`,
                    color: sm.color, fontSize: m(T.textSm, isMobile), fontFamily: T.mono, fontWeight: 600,
                    display: "inline-flex", alignItems: "center", gap: 4,
                    transition: "all 0.2s ease",
                    flexShrink: 0,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = `${sm.color}18`; e.currentTarget.style.boxShadow = `0 0 10px ${sm.color}15`; }}
                  onMouseLeave={e => { e.currentTarget.style.background = `${sm.color}08`; e.currentTarget.style.boxShadow = "none"; }}
                >
                  {getBaseSymbol(r.symbol)}
                  <span style={{ fontSize: m(T.textXs, isMobile), opacity: 0.5 }}>{r.tf}</span>
                </span>
              );
            })}
        </GlassCard>
        {isMobile && (
          <div style={{
            position: "absolute", top: 1, right: 1, bottom: 1,
            width: 32, borderRadius: "0 13px 13px 0",
            background: "linear-gradient(90deg, transparent, rgba(10,10,12,0.85))",
            pointerEvents: "none",
          }} />
        )}
      </div>
    </FadeIn>
  );
}
