import { useState } from "react";
import { T, m, REGIME_META, SIGNAL_META, heatColor, phaseColor, exhaustMeta, fmt, zBar } from "../theme.js";

export function ZScoreBar({ z, isMobile }) {
  const bar = zBar(z);
  if (!bar) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: isMobile ? 90 : 110 }}>
      <div style={{
        flex: 1, height: isMobile ? 4 : 3, background: T.overlay04, borderRadius: 2,
        overflow: "hidden", position: "relative"
      }}>
        <div style={{
          position: "absolute",
          left: bar.pct >= 50 ? "50%" : `${bar.pct}%`,
          width: `${Math.abs(bar.pct - 50)}%`,
          height: "100%",
          background: `linear-gradient(90deg, ${bar.color}99, ${bar.color})`,
          borderRadius: 2,
          boxShadow: `0 0 8px ${bar.color}40`,
        }} />
        <div style={{
          position: "absolute", left: "50%", top: -1, bottom: -1,
          width: 1, background: T.overlay08
        }} />
      </div>
      <span style={{ color: bar.color, fontFamily: T.mono, fontSize: m(isMobile ? 12 : 13, isMobile), minWidth: 40, textAlign: "right", fontWeight: 600 }}>
        {fmt(z, 2)}
      </span>
    </div>
  );
}

export function RegimeBadge({ regime, isMobile }) {
  const rm = REGIME_META[regime] || REGIME_META.FLAT;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: isMobile ? "5px 12px" : "4px 12px", borderRadius: "20px",
      background: rm.bg, color: rm.color,
      fontSize: m(12, isMobile), fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.06em",
      border: `1px solid ${rm.color}25`,
      boxShadow: `0 0 12px ${rm.glow}`,
      whiteSpace: "nowrap",
    }}>
      <span style={{ fontSize: m(11, isMobile), opacity: 0.9 }}>{rm.glyph}</span>
      {rm.label}
    </span>
  );
}

export function SignalDot({ signal, reason, warnings, isMobile }) {
  const sm = SIGNAL_META[signal] || SIGNAL_META.WAIT;
  const [showTip, setShowTip] = useState(false);
  const hasInfo = reason || (warnings && warnings.length > 0);

  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        color: sm.color, fontFamily: T.mono, fontSize: m(12, isMobile), whiteSpace: "nowrap",
        fontWeight: 600, position: "relative", cursor: hasInfo ? "help" : "default",
      }}
      onMouseEnter={() => hasInfo && !isMobile && setShowTip(true)}
      onMouseLeave={() => setShowTip(false)}
      onClick={(e) => { if (hasInfo && isMobile) { e.stopPropagation(); setShowTip(!showTip); } }}
    >
      <span style={{
        fontSize: isMobile ? 11 : 9,
        filter: signal !== "WAIT" ? `drop-shadow(0 0 4px ${sm.color})` : "none",
      }}>{sm.dot}</span>
      {sm.label}
      {warnings && warnings.length > 0 && (
        <span style={{ fontSize: isMobile ? 10 : 8, color: "#fbbf24", marginLeft: 2 }}>{"\u26a0"}</span>
      )}
      {showTip && hasInfo && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 8px)", left: 0,
          background: T.popoverBg, border: `1px solid ${T.borderH}`,
          borderRadius: T.radiusSm, padding: isMobile ? "12px 14px" : "10px 12px",
          minWidth: 220, maxWidth: 300, zIndex: 300,
          boxShadow: `0 8px 32px ${T.shadowDeep}`,
          backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
        }}
          onClick={e => e.stopPropagation()}
        >
          {reason && (
            <div style={{ fontSize: m(10, isMobile), color: T.text2, fontFamily: T.mono, lineHeight: 1.6, marginBottom: warnings?.length ? 8 : 0 }}>
              {reason}
            </div>
          )}
          {warnings && warnings.length > 0 && (
            <div style={{ borderTop: reason ? `1px solid ${T.border}` : "none", paddingTop: reason ? 6 : 0 }}>
              {warnings.map((w, i) => (
                <div key={i} style={{ fontSize: m(9, isMobile), color: "#fbbf24", fontFamily: T.mono, lineHeight: 1.6, display: "flex", gap: 4, alignItems: "flex-start" }}>
                  <span style={{ flexShrink: 0 }}>{"\u26a0"}</span>
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </span>
  );
}

export function DivergencePill({ div }) {
  if (!div) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const color = div.includes("BULL") ? "#34d399" : "#f87171";
  return (
    <span style={{
      padding: "3px 10px", borderRadius: "20px",
      background: `${color}14`, color,
      fontSize: 11, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.06em", border: `1px solid ${color}28`,
    }}>
      {div}
    </span>
  );
}

export function HeatCell({ heat, isMobile }) {
  if (heat == null) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const color = heatColor(heat);
  const pct = Math.min(heat, 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 55 }}>
      <div style={{
        width: 32, height: isMobile ? 5 : 4, background: T.overlay06,
        borderRadius: 2, overflow: "hidden",
      }}>
        <div style={{
          width: `${pct}%`, height: "100%", background: color, borderRadius: 2,
          boxShadow: pct > 60 ? `0 0 6px ${color}40` : "none",
        }} />
      </div>
      <span style={{ fontFamily: T.mono, fontSize: m(12, isMobile), color, fontWeight: 600 }}>
        {Math.round(heat)}
      </span>
    </div>
  );
}

export function PhaseCell({ phase }) {
  if (!phase) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  return (
    <span style={{ fontFamily: T.mono, fontSize: 12, color: phaseColor(phase), fontWeight: 600, letterSpacing: "0.03em" }}>
      {phase}
    </span>
  );
}

export function ExhaustBadge({ state }) {
  const meta = exhaustMeta(state);
  if (meta.text === "\u2014") return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  return (
    <span style={{
      padding: "3px 9px", borderRadius: "20px",
      background: `${meta.color}14`, color: meta.color,
      fontSize: 11, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.04em", border: `1px solid ${meta.color}25`,
    }}>
      {meta.text}
    </span>
  );
}

export function FloorCell({ confirmed }) {
  if (confirmed) {
    return <span style={{
      color: "#34d399", fontFamily: T.mono, fontSize: 13, fontWeight: 700,
      filter: "drop-shadow(0 0 4px rgba(52,211,153,0.5))",
    }}>{"\u2713"}</span>;
  }
  return <span style={{ color: T.text4, fontSize: 12 }}>{"\u2014"}</span>;
}

export function FundingCell({ rate }) {
  if (rate == null) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const color = rate < 0 ? "#34d399" : rate > 0.01 ? "#f87171" : rate > 0.005 ? "#fbbf24" : T.text2;
  return (
    <span style={{ fontFamily: T.mono, fontSize: 12, color, fontWeight: 600 }}>
      {(rate * 100).toFixed(3)}%
    </span>
  );
}

export function OITrendBadge({ trend }) {
  if (!trend) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const meta = {
    BUILDING:    { color: "#34d399", label: "BUILD" },
    SQUEEZE:     { color: "#fbbf24", label: "SQUZ" },
    LIQUIDATING: { color: "#f87171", label: "LIQ" },
    SHORTING:    { color: "#c084fc", label: "SHORT" },
  }[trend] || { color: T.text4, label: trend.slice(0, 5) };
  return (
    <span style={{
      padding: "3px 8px", borderRadius: "20px",
      background: `${meta.color}14`, color: meta.color,
      fontSize: 11, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.04em", border: `1px solid ${meta.color}25`,
    }}>
      {meta.label}
    </span>
  );
}

export function ConfluenceBadge({ score, label }) {
  if (score == null && !label) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const color = (score ?? 0) >= 75 ? "#34d399" : (score ?? 0) >= 50 ? "#facc15" : (score ?? 0) >= 25 ? "#fb923c" : "#f87171";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{
        width: 24, height: 4, background: T.overlay06,
        borderRadius: 2, overflow: "hidden",
      }}>
        <div style={{
          width: `${Math.min(score ?? 0, 100)}%`, height: "100%",
          background: color, borderRadius: 2,
        }} />
      </div>
      <span style={{ fontFamily: T.mono, fontSize: 12, color, fontWeight: 700 }}>
        {score != null ? Math.round(score) : "\u2014"}
      </span>
    </div>
  );
}
