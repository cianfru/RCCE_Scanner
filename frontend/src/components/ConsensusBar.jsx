import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

export default function ConsensusBar({ consensus, isMobile }) {
  if (!consensus) return null;
  const colorMap = {
    "RISK-ON": T.green, "EUPHORIA": T.yellow, "RISK-OFF": T.red,
    "ACCUMULATION": T.cyan, "MIXED": T.gray,
  };
  const color = colorMap[consensus.consensus] || "#52525b";

  return (
    <FadeIn delay={350}>
      <GlassCard glow={`${color}08`} style={{
        padding: isMobile ? "8px 12px" : "10px 16px",
        marginTop: isMobile ? T.sp2 : T.sp3,
        display: "flex",
        flexDirection: isMobile ? "column" : "row",
        alignItems: isMobile ? "stretch" : "center",
        justifyContent: "space-between",
        gap: isMobile ? 10 : 0,
        border: `1px solid ${color}15`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{
            fontSize: T.textBase, color: T.text2, letterSpacing: "0.08em", fontFamily: T.font, fontWeight: 600,
            textTransform: "uppercase",
          }}>Consensus</span>
          <span style={{
            padding: "5px 16px", borderRadius: "20px",
            background: `${color}15`, color,
            fontSize: T.textMd, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
            border: `1px solid ${color}28`,
            boxShadow: `0 0 16px ${color}15`,
          }}>
            {consensus.consensus}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: isMobile ? 1 : undefined }}>
          <span style={{ fontSize: T.textSm, color: T.text3, letterSpacing: "0.08em", fontFamily: T.font, fontWeight: 600 }}>STR</span>
          <div style={{
            width: isMobile ? undefined : 100,
            flex: isMobile ? 1 : undefined,
            height: 5, background: T.overlay04,
            borderRadius: 2, overflow: "hidden",
          }}>
            <div style={{
              width: `${consensus.strength}%`, height: "100%",
              background: `linear-gradient(90deg, ${color}88, ${color})`,
              borderRadius: 2,
              boxShadow: `0 0 8px ${color}30`,
              transition: "width 0.6s ease",
            }} />
          </div>
          <span style={{
            fontFamily: T.mono, fontSize: T.textMd, color, fontWeight: 700,
            minWidth: 36, textAlign: "right",
          }}>{Math.round(consensus.strength)}%</span>
        </div>
      </GlassCard>
    </FadeIn>
  );
}
