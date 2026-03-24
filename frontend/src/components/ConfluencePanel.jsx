import { T, REGIME_META, SIGNAL_META } from "../theme.js";

function scoreColor(score) {
  if (score >= 75) return "#34d399";
  if (score >= 50) return "#facc15";
  if (score >= 25) return "#fb923c";
  return "#f87171";
}

function labelColor(label) {
  switch (label) {
    case "STRONG":      return "#34d399";
    case "MODERATE":    return "#facc15";
    case "WEAK":        return "#fb923c";
    case "CONFLICTING": return "#f87171";
    default:            return T.text4;
  }
}

export default function ConfluencePanel({ confluence }) {
  if (!confluence) return null;

  const {
    score,
    label,
    regime_aligned,
    signal_aligned,
    regime_4h,
    regime_1d,
    signal_4h,
    signal_1d,
  } = confluence;

  const color = scoreColor(score ?? 0);
  const lColor = labelColor(label);

  const regime4hMeta = REGIME_META[regime_4h] || REGIME_META.FLAT;
  const regime1dMeta = REGIME_META[regime_1d] || REGIME_META.FLAT;
  const signal4hMeta = SIGNAL_META[signal_4h] || SIGNAL_META.WAIT;
  const signal1dMeta = SIGNAL_META[signal_1d] || SIGNAL_META.WAIT;

  return (
    <div style={{
      background: T.glassBg,
      border: `1px solid ${T.border}`,
      borderRadius: 12,
      padding: "16px 20px",
      backdropFilter: "blur(20px) saturate(1.3)",
      WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 14, paddingBottom: 10,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
        <span style={{
          fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em",
          fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
        }}>
          Confluence
        </span>
      </div>

      {/* Score bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div style={{
          flex: 1, height: 5, background: T.overlay04,
          borderRadius: 3, overflow: "hidden",
        }}>
          <div style={{
            width: `${Math.min(score ?? 0, 100)}%`,
            height: "100%",
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            borderRadius: 3,
            boxShadow: `0 0 8px ${color}30`,
            transition: "width 0.6s ease",
          }} />
        </div>
        <span style={{
          fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700,
          color, minWidth: 32, textAlign: "right",
        }}>
          {score != null ? Math.round(score) : "\u2014"}
        </span>
      </div>

      {/* Label badge + alignment */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{
          padding: "4px 12px", borderRadius: 20,
          background: `${lColor}15`, color: lColor,
          fontSize: T.textSm, fontFamily: T.mono, fontWeight: 700,
          letterSpacing: "0.06em", border: `1px solid ${lColor}25`,
        }}>
          {label || "\u2014"}
        </span>

        <div style={{ display: "flex", gap: 10, marginLeft: "auto" }}>
          <span style={{
            fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600,
            color: regime_aligned ? "#34d399" : "#f87171",
            display: "flex", alignItems: "center", gap: 4,
          }}>
            {regime_aligned ? "\u2713" : "\u2717"}
            <span style={{ fontSize: T.textXs, color: T.text4 }}>Regime</span>
          </span>
          <span style={{
            fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600,
            color: signal_aligned ? "#34d399" : "#f87171",
            display: "flex", alignItems: "center", gap: 4,
          }}>
            {signal_aligned ? "\u2713" : "\u2717"}
            <span style={{ fontSize: T.textXs, color: T.text4 }}>Signal</span>
          </span>
        </div>
      </div>

      {/* Divider */}
      <div style={{ height: 1, background: T.overlay06, margin: "10px 0" }} />

      {/* Timeframe rows */}
      {[
        { tf: "4H", regime: regime_4h, regimeMeta: regime4hMeta, signal: signal_4h, signalMeta: signal4hMeta },
        { tf: "1D", regime: regime_1d, regimeMeta: regime1dMeta, signal: signal_1d, signalMeta: signal1dMeta },
      ].map(row => (
        <div key={row.tf} style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "8px 0",
        }}>
          <span style={{
            fontSize: T.textSm, color: T.text4, fontFamily: T.mono,
            fontWeight: 600, letterSpacing: "0.08em", minWidth: 28,
          }}>
            {row.tf}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{
              padding: "3px 10px", borderRadius: 20,
              background: row.regimeMeta.bg, color: row.regimeMeta.color,
              fontSize: T.textXs, fontFamily: T.mono, fontWeight: 600,
              letterSpacing: "0.04em", border: `1px solid ${row.regimeMeta.color}20`,
            }}>
              {row.regime || "\u2014"}
            </span>
            <span style={{ color: T.text4, fontSize: T.textSm }}>{"\u2192"}</span>
            <span style={{
              fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600,
              color: row.signalMeta.color,
              display: "inline-flex", alignItems: "center", gap: 4,
            }}>
              <span style={{
                fontSize: 9,
                filter: row.signal !== "WAIT" ? `drop-shadow(0 0 3px ${row.signalMeta.color})` : "none",
              }}>
                {row.signalMeta.dot}
              </span>
              {row.signalMeta.label}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
