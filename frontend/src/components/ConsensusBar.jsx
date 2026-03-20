import { T, m, REGIME_META } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

// Regime distribution bar segment config
const REGIME_SEGMENTS = [
  { key: "markup",   label: "MARKUP",   color: REGIME_META.MARKUP.color },
  { key: "accum",    label: "ACCUM",    color: REGIME_META.ACCUM.color },
  { key: "blowoff",  label: "BLOWOFF",  color: REGIME_META.BLOWOFF.color },
  { key: "markdown", label: "MARKDOWN", color: REGIME_META.MARKDOWN.color },
];

export default function ConsensusBar({ consensus, pulse, isMobile, activeTab, onTabChange, searchTerm, onSearchChange }) {
  if (!consensus) return null;
  const colorMap = {
    "RISK-ON": T.green, "EUPHORIA": T.yellow, "RISK-OFF": T.red,
    "ACCUMULATION": T.cyan, "MIXED": T.gray,
  };
  const color = colorMap[consensus.consensus] || "#52525b";

  const tfOptions = isMobile
    ? [["4h", "4H"], ["1d", "1D"]]
    : [["4h", "4H"], ["1d", "1D"], ["split", "SPLIT"]];

  const counts = pulse?.regime_counts || {};
  const total = counts.total || 0;

  return (
    <FadeIn delay={350}>
      <GlassCard glow={`${color}08`} style={{
        padding: isMobile ? "10px 14px" : "10px 16px",
        marginTop: isMobile ? T.sp3 : T.sp3,
        display: "flex",
        flexDirection: "column",
        gap: isMobile ? 8 : 8,
        border: `1px solid ${color}15`,
      }}>
        {/* Row 1: TF toggle + search + consensus badge + strength */}
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: isMobile ? 8 : 14,
          flexWrap: "wrap",
        }}>
          {/* Left: TF toggle + search + consensus */}
          <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 8 : 12, flexWrap: isMobile ? "wrap" : "nowrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, ...(isMobile ? { flex: "1 1 100%" } : {}) }}>
              {onTabChange && (
                <div style={{
                  display: "flex", borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  overflow: "hidden", flexShrink: 0,
                }}>
                  {tfOptions.map(([key, label]) => {
                    const isActive = activeTab === key;
                    return (
                      <button
                        key={key}
                        onClick={() => onTabChange(key)}
                        style={{
                          padding: isMobile ? "7px 14px" : "5px 12px",
                          border: "none",
                          background: isActive ? T.accent : "transparent",
                          color: isActive ? T.bg : T.text3,
                          fontFamily: T.font, fontSize: m(T.textSm, isMobile), fontWeight: isActive ? 700 : 500,
                          cursor: "pointer", letterSpacing: "0.04em",
                          transition: "all 0.15s ease",
                        }}
                      >{label}</button>
                    );
                  })}
                </div>
              )}
              {/* Search */}
              <div style={{ position: "relative", display: "flex", alignItems: "center", flex: isMobile ? 1 : undefined }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={T.text4} strokeWidth="2.5" strokeLinecap="round"
                  style={{ position: "absolute", left: 8, pointerEvents: "none" }}>
                  <circle cx="10.5" cy="10.5" r="7" /><line x1="15.5" y1="15.5" x2="21" y2="21" />
                </svg>
                <input
                  value={searchTerm || ""}
                  onChange={e => onSearchChange?.(e.target.value)}
                  placeholder="Search..."
                  style={{
                    width: isMobile ? "100%" : 120, height: 28,
                    padding: "0 8px 0 26px",
                    fontSize: 11, fontFamily: T.mono,
                    background: T.overlay04, color: T.text1,
                    border: `1px solid ${T.border}`, borderRadius: 8,
                    outline: "none",
                  }}
                />
              </div>
            </div>
            <span style={{
              fontSize: m(T.textBase, isMobile), color: T.text2, letterSpacing: "0.08em", fontFamily: T.font, fontWeight: 600,
              textTransform: "uppercase",
            }}>Consensus</span>
            <span style={{
              padding: isMobile ? "6px 16px" : "5px 16px", borderRadius: "20px",
              background: `${color}15`, color,
              fontSize: m(T.textMd, isMobile), fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
              border: `1px solid ${color}28`,
              boxShadow: `0 0 16px ${color}15`,
            }}>
              {consensus.consensus}
            </span>
          </div>

          {/* Right: strength bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flex: isMobile ? "1 1 100%" : undefined }}>
            <span style={{ fontSize: m(T.textSm, isMobile), color: T.text3, letterSpacing: "0.08em", fontFamily: T.font, fontWeight: 600 }}>STR</span>
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
              fontFamily: T.mono, fontSize: m(T.textMd, isMobile), color, fontWeight: 700,
              minWidth: 36, textAlign: "right",
            }}>{Math.round(consensus.strength)}%</span>
          </div>
        </div>

        {/* Row 2: Narrative + regime distribution (only when pulse data available) */}
        {pulse?.narrative && (
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: isMobile ? 8 : 14,
            flexWrap: "wrap",
          }}>
            {/* Narrative text */}
            <span style={{
              fontSize: m(T.textSm, isMobile),
              fontFamily: T.mono,
              color: T.text3,
              letterSpacing: "0.02em",
              lineHeight: 1.4,
            }}>
              {pulse.narrative}
            </span>

            {/* Regime distribution mini-bar */}
            {total > 0 && (
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginLeft: isMobile ? 0 : "auto",
                flex: isMobile ? "1 1 100%" : undefined,
              }}>
                <div style={{
                  display: "flex",
                  width: isMobile ? "100%" : 140,
                  height: 4,
                  borderRadius: 2,
                  overflow: "hidden",
                  background: T.overlay04,
                }}>
                  {REGIME_SEGMENTS.map(seg => {
                    const count = counts[seg.key] || 0;
                    const pct = (count / total) * 100;
                    if (pct === 0) return null;
                    return (
                      <div
                        key={seg.key}
                        title={`${seg.label}: ${count}/${total}`}
                        style={{
                          width: `${pct}%`,
                          height: "100%",
                          background: seg.color,
                          transition: "width 0.6s ease",
                        }}
                      />
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </GlassCard>
    </FadeIn>
  );
}
