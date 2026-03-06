import { useState, useEffect, useCallback, useRef } from "react";

// ─── CONFIG ───────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const REGIME_META = {
  MARKUP:    { color: "#34d399", bg: "rgba(52,211,153,0.08)", glow: "rgba(52,211,153,0.25)", label: "MARKUP",    glyph: "\u2197" },
  BLOWOFF:   { color: "#f87171", bg: "rgba(248,113,113,0.08)", glow: "rgba(248,113,113,0.25)", label: "BLOWOFF",   glyph: "\u25b2\u25b2" },
  REACC:     { color: "#22d3ee", bg: "rgba(34,211,238,0.08)",  glow: "rgba(34,211,238,0.25)",  label: "REACC",     glyph: "\u25c6" },
  MARKDOWN:  { color: "#fb923c", bg: "rgba(251,146,60,0.08)",  glow: "rgba(251,146,60,0.25)",  label: "MARKDOWN",  glyph: "\u25bc" },
  CAP:       { color: "#c084fc", bg: "rgba(192,132,252,0.08)", glow: "rgba(192,132,252,0.25)", label: "CAP",       glyph: "\u25bc\u25bc" },
  ACCUM:     { color: "#6ee7b7", bg: "rgba(110,231,183,0.08)", glow: "rgba(110,231,183,0.25)", label: "ACCUM",     glyph: "\u25c7" },
  ABSORBING: { color: "#d8b4fe", bg: "rgba(216,180,254,0.08)", glow: "rgba(216,180,254,0.25)", label: "ABSORBING", glyph: "\u2715" },
  FLAT:      { color: "#52525b", bg: "rgba(82,82,91,0.06)",    glow: "rgba(82,82,91,0.15)",    label: "FLAT",      glyph: "\u2014" },
};

const SIGNAL_META = {
  STRONG_LONG:  { color: "#34d399", label: "STRONG LONG",  dot: "\u25cf" },
  LIGHT_LONG:   { color: "#6ee7b7", label: "LIGHT LONG",   dot: "\u25cf" },
  ACCUMULATE:   { color: "#22d3ee", label: "ACCUMULATE",    dot: "\u25c6" },
  REVIVAL_SEED: { color: "#67e8f9", label: "REVIVAL",       dot: "\u25cf" },
  WAIT:         { color: "#52525b", label: "WAIT",          dot: "\u25cb" },
  TRIM:         { color: "#fbbf24", label: "TRIM",          dot: "\u25cf" },
  TRIM_HARD:    { color: "#f87171", label: "TRIM HARD",     dot: "\u25cf" },
  RISK_OFF:     { color: "#ef4444", label: "RISK-OFF",      dot: "\u25cf" },
  NO_LONG:      { color: "#d8b4fe", label: "NO LONG",       dot: "\u2715" },
};

const REGIME_ORDER = ["BLOWOFF","MARKUP","REACC","ACCUM","CAP","MARKDOWN","ABSORBING","FLAT"];

// ─── DESIGN TOKENS ───────────────────────────────────────────────────────────

const T = {
  bg:        "#000000",
  surface:   "rgba(255,255,255,0.02)",
  surfaceH:  "rgba(255,255,255,0.04)",
  border:    "rgba(255,255,255,0.06)",
  borderH:   "rgba(255,255,255,0.10)",
  text1:     "#e4e4e7",
  text2:     "#a1a1aa",
  text3:     "#71717a",
  text4:     "#3f3f46",
  accent:    "#22d3ee",
  accentDim: "rgba(34,211,238,0.15)",
  font:      "'Inter', -apple-system, sans-serif",
  mono:      "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
  radius:    "12px",
  radiusSm:  "8px",
  radiusXs:  "6px",
};

// ─── VIEWPORT HOOK ──────────────────────────────────────────────────────────

function useViewport() {
  const [vp, setVp] = useState(() => {
    const w = typeof window !== "undefined" ? window.innerWidth : 1280;
    return { width: w, isMobile: w < 768, isTablet: w >= 768 && w < 1024, isDesktop: w >= 1024 };
  });

  useEffect(() => {
    let ticking = false;
    const update = () => {
      const w = window.innerWidth;
      setVp({ width: w, isMobile: w < 768, isTablet: w >= 768 && w < 1024, isDesktop: w >= 1024 });
    };
    const onResize = () => {
      if (!ticking) {
        requestAnimationFrame(() => { update(); ticking = false; });
        ticking = true;
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return vp;
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

function fmt(val, decimals = 2, suffix = "") {
  if (val === null || val === undefined || isNaN(val)) return "\u2014";
  return `${Number(val).toFixed(decimals)}${suffix}`;
}

function zBar(z) {
  if (z === null || z === undefined) return null;
  const clamped = Math.max(-3, Math.min(3, z));
  const pct = ((clamped + 3) / 6) * 100;
  let color = "#71717a";
  if (z <= -1) color = "#c084fc";
  else if (z <= 0) color = "#22d3ee";
  else if (z <= 1.2) color = "#34d399";
  else if (z <= 2.0) color = "#fbbf24";
  else color = "#f87171";
  return { pct, color };
}

function getBaseSymbol(sym) { return sym.replace("/USDT", ""); }

function formatCacheAge(seconds) {
  if (!seconds) return "\u2014";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

function heatColor(heat) {
  if (heat == null) return "#3f3f46";
  if (heat >= 80) return "#f87171";
  if (heat >= 60) return "#fb923c";
  if (heat >= 40) return "#fbbf24";
  if (heat >= 20) return "#34d399";
  return "#3f3f46";
}

function phaseColor(phase) {
  return { Exhaustion: "#fbbf24", Entry: "#34d399", Fading: "#fb923c", Extension: "#22d3ee", Neutral: "#52525b" }[phase] || "#52525b";
}

function exhaustMeta(state) {
  return {
    EXHAUSTED_FLOOR: { color: "#22d3ee", text: "FLOOR" },
    CLIMAX:          { color: "#fbbf24", text: "CLIMAX" },
    ABSORBING:       { color: "#67e8f9", text: "ABSORB" },
    BEAR_ZONE:       { color: "#f87171", text: "BEAR" },
    NEUTRAL:         { color: "#3f3f46", text: "\u2014" },
  }[state] || { color: "#3f3f46", text: "\u2014" };
}

// ─── ANIMATED WRAPPER ────────────────────────────────────────────────────────

function FadeIn({ children, delay = 0, style = {} }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.opacity = "0";
    el.style.transform = "translateY(6px)";
    const t = setTimeout(() => {
      el.style.transition = "opacity 0.4s ease, transform 0.4s ease";
      el.style.opacity = "1";
      el.style.transform = "translateY(0)";
    }, delay);
    return () => clearTimeout(t);
  }, [delay]);
  return <div ref={ref} style={style}>{children}</div>;
}

// ─── COLUMN DEFINITIONS ─────────────────────────────────────────────────────
// [sortKey, label, minViewportWidth]

const COLUMNS = [
  ["symbol",   "SYMBOL",  0],
  ["regime",   "REGIME",  0],
  [null,       "SIGNAL",  0],
  ["zscore",   "Z-SCORE", 480],
  ["momentum", "MOM",     480],
  [null,       "PRICE",   480],
  ["heat",     "HEAT",    768],
  [null,       "DIV",     768],
  [null,       "EXHAUST", 768],
  [null,       "ENERGY",  1024],
  [null,       "PHASE",   1024],
  [null,       "FLOOR",   1024],
];

// ─── SUBCOMPONENTS ────────────────────────────────────────────────────────────

function ZScoreBar({ z, isMobile }) {
  const bar = zBar(z);
  if (!bar) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: isMobile ? 80 : 110 }}>
      <div style={{
        flex: 1, height: 3, background: "rgba(255,255,255,0.04)", borderRadius: 2,
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
          width: 1, background: "rgba(255,255,255,0.08)"
        }} />
      </div>
      <span style={{ color: bar.color, fontFamily: T.mono, fontSize: isMobile ? 9 : 10, minWidth: 36, textAlign: "right", fontWeight: 500 }}>
        {fmt(z, 2)}
      </span>
    </div>
  );
}

function RegimeBadge({ regime }) {
  const m = REGIME_META[regime] || REGIME_META.FLAT;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 10px", borderRadius: "20px",
      background: m.bg, color: m.color,
      fontSize: 9, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.06em",
      border: `1px solid ${m.color}18`,
      boxShadow: `0 0 12px ${m.glow}`,
      whiteSpace: "nowrap",
    }}>
      <span style={{ fontSize: 8, opacity: 0.8 }}>{m.glyph}</span>
      {m.label}
    </span>
  );
}

function SignalDot({ signal, reason, warnings, isMobile }) {
  const m = SIGNAL_META[signal] || SIGNAL_META.WAIT;
  const [showTip, setShowTip] = useState(false);
  const hasInfo = reason || (warnings && warnings.length > 0);

  return (
    <span
      style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        color: m.color, fontFamily: T.mono, fontSize: 10, whiteSpace: "nowrap",
        fontWeight: 500, position: "relative", cursor: hasInfo ? "help" : "default",
      }}
      onMouseEnter={() => hasInfo && !isMobile && setShowTip(true)}
      onMouseLeave={() => setShowTip(false)}
      onClick={(e) => { if (hasInfo && isMobile) { e.stopPropagation(); setShowTip(!showTip); } }}
    >
      <span style={{
        fontSize: 8,
        filter: signal !== "WAIT" ? `drop-shadow(0 0 3px ${m.color})` : "none",
      }}>{m.dot}</span>
      {m.label}
      {warnings && warnings.length > 0 && (
        <span style={{ fontSize: 7, color: "#fbbf24", marginLeft: 2 }}>{"\u26a0"}</span>
      )}
      {showTip && hasInfo && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 8px)", left: 0,
          background: "rgba(0,0,0,0.95)", border: `1px solid ${T.borderH}`,
          borderRadius: T.radiusSm, padding: "10px 12px",
          minWidth: 220, maxWidth: 300, zIndex: 300,
          boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
          backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
        }}
          onClick={e => e.stopPropagation()}
        >
          {reason && (
            <div style={{ fontSize: 9, color: T.text2, fontFamily: T.mono, lineHeight: 1.5, marginBottom: warnings?.length ? 8 : 0 }}>
              {reason}
            </div>
          )}
          {warnings && warnings.length > 0 && (
            <div style={{ borderTop: reason ? `1px solid ${T.border}` : "none", paddingTop: reason ? 6 : 0 }}>
              {warnings.map((w, i) => (
                <div key={i} style={{ fontSize: 8, color: "#fbbf24", fontFamily: T.mono, lineHeight: 1.5, display: "flex", gap: 4, alignItems: "flex-start" }}>
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

function DivergencePill({ div }) {
  if (!div) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const color = div.includes("BULL") ? "#34d399" : "#f87171";
  return (
    <span style={{
      padding: "2px 8px", borderRadius: "20px",
      background: `${color}10`, color,
      fontSize: 9, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.06em", border: `1px solid ${color}20`,
    }}>
      {div}
    </span>
  );
}

function HeatCell({ heat }) {
  if (heat == null) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const color = heatColor(heat);
  const pct = Math.min(heat, 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 50 }}>
      <div style={{
        width: 28, height: 3, background: "rgba(255,255,255,0.04)",
        borderRadius: 2, overflow: "hidden",
      }}>
        <div style={{
          width: `${pct}%`, height: "100%", background: color, borderRadius: 2,
          boxShadow: pct > 60 ? `0 0 6px ${color}40` : "none",
        }} />
      </div>
      <span style={{ fontFamily: T.mono, fontSize: 10, color, fontWeight: 500 }}>
        {Math.round(heat)}
      </span>
    </div>
  );
}

function PhaseCell({ phase }) {
  if (!phase) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  return (
    <span style={{ fontFamily: T.mono, fontSize: 9, color: phaseColor(phase), fontWeight: 500, letterSpacing: "0.03em" }}>
      {phase}
    </span>
  );
}

function ExhaustBadge({ state }) {
  const meta = exhaustMeta(state);
  if (meta.text === "\u2014") return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  return (
    <span style={{
      padding: "2px 7px", borderRadius: "20px",
      background: `${meta.color}10`, color: meta.color,
      fontSize: 9, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.04em", border: `1px solid ${meta.color}15`,
    }}>
      {meta.text}
    </span>
  );
}

function FloorCell({ confirmed }) {
  if (confirmed) {
    return <span style={{
      color: "#34d399", fontFamily: T.mono, fontSize: 11, fontWeight: 700,
      filter: "drop-shadow(0 0 4px rgba(52,211,153,0.5))",
    }}>{"\u2713"}</span>;
  }
  return <span style={{ color: T.text4, fontSize: 11 }}>{"\u2014"}</span>;
}

// Cell renderer for column-based rendering
function CellContent({ colLabel, row, isMobile }) {
  const cellPad = isMobile ? "8px 10px" : "10px 12px";
  switch (colLabel) {
    case "SYMBOL":
      return (
        <td style={{ padding: isMobile ? "8px 10px" : "10px 14px", fontFamily: T.mono, fontWeight: 600, color: T.text1, fontSize: isMobile ? 10 : 11, letterSpacing: "0.02em" }}>
          {getBaseSymbol(row.symbol)}
        </td>
      );
    case "REGIME":
      return <td style={{ padding: cellPad }}><RegimeBadge regime={row.regime} /></td>;
    case "SIGNAL":
      return <td style={{ padding: cellPad }}><SignalDot signal={row.signal} reason={row.signal_reason} warnings={row.signal_warnings} isMobile={isMobile} /></td>;
    case "Z-SCORE":
      return <td style={{ padding: cellPad }}><ZScoreBar z={row.zscore} isMobile={isMobile} /></td>;
    case "ENERGY":
      return <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: isMobile ? 9 : 10, color: T.text3 }}>{fmt(row.energy, 2)}</td>;
    case "MOM":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: isMobile ? 9 : 10 }}>
          <span style={{ color: row.momentum >= 0 ? "#34d399" : "#f87171" }}>
            {row.momentum != null ? `${row.momentum >= 0 ? "+" : ""}${fmt(row.momentum, 1)}%` : "\u2014"}
          </span>
        </td>
      );
    case "DIV":
      return <td style={{ padding: cellPad }}><DivergencePill div={row.divergence} /></td>;
    case "PRICE":
      return (
        <td style={{ padding: cellPad, fontFamily: T.mono, fontSize: isMobile ? 9 : 10, color: T.text2 }}>
          {row.price ? `$${row.price < 1 ? fmt(row.price, 5) : fmt(row.price, 2)}` : "\u2014"}
        </td>
      );
    case "HEAT":
      return <td style={{ padding: cellPad }}><HeatCell heat={row.heat} /></td>;
    case "PHASE":
      return <td style={{ padding: cellPad }}><PhaseCell phase={row.heat_phase} /></td>;
    case "EXHAUST":
      return <td style={{ padding: cellPad }}><ExhaustBadge state={row.exhaustion_state} /></td>;
    case "FLOOR":
      return <td style={{ padding: cellPad }}><FloorCell confirmed={row.floor_confirmed} /></td>;
    default:
      return <td style={{ padding: cellPad }}>{"\u2014"}</td>;
  }
}

function SymbolRow({ row, selected, onSelect, index, visibleColumns, isMobile }) {
  const rm = REGIME_META[row.regime] || REGIME_META.FLAT;
  const isHighlight = ["STRONG_LONG", "LIGHT_LONG", "TRIM_HARD", "RISK_OFF"].includes(row.signal);

  return (
    <tr
      onClick={() => onSelect(row)}
      style={{
        cursor: "pointer",
        borderBottom: `1px solid ${T.border}`,
        background: selected ? "rgba(34,211,238,0.04)" : isHighlight ? rm.bg : "transparent",
        transition: "background 0.2s ease",
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = T.surfaceH; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = selected ? "rgba(34,211,238,0.04)" : isHighlight ? rm.bg : "transparent"; }}
    >
      {visibleColumns.map(([, label]) => (
        <CellContent key={label} colLabel={label} row={row} isMobile={isMobile} />
      ))}
    </tr>
  );
}

// ─── GLASS CARD ──────────────────────────────────────────────────────────────

function GlassCard({ children, style = {}, glow = null }) {
  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      borderRadius: T.radius,
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)",
      boxShadow: glow ? `0 0 30px ${glow}` : "0 1px 3px rgba(0,0,0,0.3)",
      ...style,
    }}>
      {children}
    </div>
  );
}

// ─── SUMMARY BAR ─────────────────────────────────────────────────────────────

function SummaryBar({ results }) {
  const counts = {};
  REGIME_ORDER.forEach(r => counts[r] = 0);
  results.forEach(r => { if (counts[r.regime] !== undefined) counts[r.regime]++; });
  const total = results.length;

  return (
    <div style={{
      display: "flex", gap: 1, height: 4, borderRadius: 4, overflow: "hidden",
      background: "rgba(255,255,255,0.02)",
    }}>
      {REGIME_ORDER.filter(r => counts[r] > 0).map(r => {
        const m = REGIME_META[r];
        const pct = (counts[r] / total) * 100;
        return (
          <div
            key={r}
            title={`${m.label}: ${counts[r]}`}
            style={{
              flex: pct,
              background: `linear-gradient(90deg, ${m.color}cc, ${m.color})`,
              minWidth: 2,
              boxShadow: `0 0 8px ${m.glow}`,
            }}
          />
        );
      })}
    </div>
  );
}

// ─── STAT CARDS ──────────────────────────────────────────────────────────────

function StatCards({ results, isMobile, isTablet }) {
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
            glow={c.value > 0 ? `${c.color}08` : null}
            style={{
              padding: isMobile ? "12px 14px" : "16px 18px",
              border: `1px solid ${c.value > 0 ? c.color + "22" : T.border}`,
              transition: "border-color 0.3s, box-shadow 0.3s",
            }}
          >
            <div style={{
              fontSize: isMobile ? 22 : 28, fontWeight: 700, fontFamily: T.mono,
              color: c.value > 0 ? c.color : T.text4,
              lineHeight: 1,
              filter: c.value > 0 ? `drop-shadow(0 0 8px ${c.color}30)` : "none",
            }}>
              {c.value}
            </div>
            <div style={{
              fontSize: 9, color: c.value > 0 ? T.text3 : T.text4,
              fontFamily: T.font, fontWeight: 500,
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

// ─── CONSENSUS BAR ───────────────────────────────────────────────────────────

function ConsensusBar({ consensus, isMobile }) {
  if (!consensus) return null;
  const colorMap = {
    "RISK-ON": "#34d399", "EUPHORIA": "#fbbf24", "RISK-OFF": "#f87171",
    "ACCUMULATION": "#22d3ee", "MIXED": "#52525b",
  };
  const color = colorMap[consensus.consensus] || "#52525b";

  return (
    <FadeIn delay={350}>
      <GlassCard glow={`${color}08`} style={{
        padding: isMobile ? "12px 14px" : "14px 20px",
        marginTop: isMobile ? 12 : 16,
        display: "flex",
        flexDirection: isMobile ? "column" : "row",
        alignItems: isMobile ? "stretch" : "center",
        justifyContent: "space-between",
        gap: isMobile ? 10 : 0,
        border: `1px solid ${color}15`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{
            fontSize: 9, color: T.text3, letterSpacing: "0.12em", fontFamily: T.font, fontWeight: 500,
            textTransform: "uppercase",
          }}>Consensus</span>
          <span style={{
            padding: "4px 14px", borderRadius: "20px",
            background: `${color}12`, color,
            fontSize: 11, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
            border: `1px solid ${color}20`,
            boxShadow: `0 0 16px ${color}15`,
          }}>
            {consensus.consensus}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: isMobile ? 1 : undefined }}>
          <span style={{ fontSize: 9, color: T.text4, letterSpacing: "0.08em", fontFamily: T.font, fontWeight: 500 }}>STR</span>
          <div style={{
            width: isMobile ? undefined : 100,
            flex: isMobile ? 1 : undefined,
            height: 3, background: "rgba(255,255,255,0.04)",
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
            fontFamily: T.mono, fontSize: 11, color, fontWeight: 600,
            minWidth: 32, textAlign: "right",
          }}>{Math.round(consensus.strength)}%</span>
        </div>
      </GlassCard>
    </FadeIn>
  );
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

export default function App() {
  const { width, isMobile, isTablet, isDesktop } = useViewport();
  const hPad = isMobile ? 16 : isTablet ? 24 : 32;

  const [data4h, setData4h] = useState([]);
  const [data1d, setData1d] = useState([]);
  const [consensus4h, setConsensus4h] = useState(null);
  const [consensus1d, setConsensus1d] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanRunning, setScanRunning] = useState(false);
  const [cacheAge, setCacheAge] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [filterRegime, setFilterRegime] = useState("ALL");
  const [filterSignal, setFilterSignal] = useState("ALL");
  const [sortKey, setSortKey] = useState("regime");
  const [activeTab, setActiveTab] = useState("4h");
  const [lastRefresh, setLastRefresh] = useState(null);

  // Global metrics & alt season
  const [globalMetrics, setGlobalMetrics] = useState(null);
  const [altSeason, setAltSeason] = useState(null);

  // Watchlist modal
  const [showWatchlist, setShowWatchlist] = useState(false);
  const [watchlistSymbols, setWatchlistSymbols] = useState([]);
  const [watchlistSearch, setWatchlistSearch] = useState("");
  const [watchlistResults, setWatchlistResults] = useState([]);
  const [watchlistLoading, setWatchlistLoading] = useState(false);

  // Force off split view on mobile
  useEffect(() => {
    if (isMobile && activeTab === "split") setActiveTab("4h");
  }, [isMobile, activeTab]);

  const fetchData = useCallback(async (tf) => {
    const params = new URLSearchParams({ timeframe: tf });
    if (filterRegime !== "ALL") params.append("regime", filterRegime);
    if (filterSignal !== "ALL") params.append("signal", filterSignal);
    const res = await fetch(`${API_BASE}/api/scan?${params}`);
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  }, [filterRegime, filterSignal]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [r4h, r1d] = await Promise.all([fetchData("4h"), fetchData("1d")]);
      setData4h(r4h.results || []);
      setData1d(r1d.results || []);
      setConsensus4h(r4h.consensus || null);
      setConsensus1d(r1d.consensus || null);
      setScanRunning(r4h.scan_running);
      setCacheAge(r4h.cache_age_seconds);
      setLastRefresh(new Date());

      // Fetch global metrics & alt season (non-blocking)
      try {
        const [gm, as] = await Promise.all([
          fetch(`${API_BASE}/api/global-metrics`).then(r => r.json()),
          fetch(`${API_BASE}/api/alt-season?timeframe=${activeTab === "1d" ? "1d" : "4h"}`).then(r => r.json()),
        ]);
        setGlobalMetrics(gm);
        setAltSeason(as);
      } catch (_) { /* metrics are optional */ }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [fetchData, activeTab]);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [loadAll]);

  const triggerScan = async () => {
    await fetch(`${API_BASE}/api/scan/refresh`, { method: "POST" });
    setScanRunning(true);
    setTimeout(loadAll, 3000);
  };

  // Watchlist management
  const loadWatchlist = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/watchlist`);
      const data = await res.json();
      setWatchlistSymbols(data.symbols || []);
    } catch (_) {}
  }, []);

  const searchSymbols = useCallback(async (q) => {
    if (!q || q.length < 1) { setWatchlistResults([]); return; }
    setWatchlistLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      setWatchlistResults(data.results || []);
    } catch (_) {
      setWatchlistResults([]);
    } finally {
      setWatchlistLoading(false);
    }
  }, []);

  const addSymbol = async (symbol) => {
    try {
      const res = await fetch(`${API_BASE}/api/watchlist/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol }),
      });
      if (res.ok) {
        await loadWatchlist();
        setWatchlistSearch("");
        setWatchlistResults([]);
      }
    } catch (_) {}
  };

  const removeSymbol = async (symbol) => {
    try {
      await fetch(`${API_BASE}/api/watchlist/${encodeURIComponent(symbol)}`, { method: "DELETE" });
      await loadWatchlist();
    } catch (_) {}
  };

  const resetWatchlist = async () => {
    try {
      await fetch(`${API_BASE}/api/watchlist/reset`, { method: "POST" });
      await loadWatchlist();
    } catch (_) {}
  };

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => searchSymbols(watchlistSearch), 300);
    return () => clearTimeout(timer);
  }, [watchlistSearch, searchSymbols]);

  // Load watchlist when modal opens
  useEffect(() => {
    if (showWatchlist) loadWatchlist();
  }, [showWatchlist, loadWatchlist]);

  const sortResults = (results) => {
    return [...results].sort((a, b) => {
      if (sortKey === "regime") {
        const ri = REGIME_ORDER.indexOf(a.regime) - REGIME_ORDER.indexOf(b.regime);
        if (ri !== 0) return ri;
        return (b.zscore || 0) - (a.zscore || 0);
      }
      if (sortKey === "zscore") return (b.zscore || 0) - (a.zscore || 0);
      if (sortKey === "momentum") return (b.momentum || 0) - (a.momentum || 0);
      if (sortKey === "symbol") return a.symbol.localeCompare(b.symbol);
      if (sortKey === "heat") return (b.heat || 0) - (a.heat || 0);
      return 0;
    });
  };

  const sorted4h = sortResults(data4h);
  const sorted1d = sortResults(data1d);
  const SIGNALS_NOTABLE = ["STRONG_LONG", "LIGHT_LONG", "TRIM_HARD", "TRIM", "RISK_OFF"];
  const notable4h = sorted4h.filter(r => SIGNALS_NOTABLE.includes(r.signal));
  const notable1d = sorted1d.filter(r => SIGNALS_NOTABLE.includes(r.signal));
  const activeConsensus = activeTab === "1d" ? consensus1d : consensus4h;

  // Visible columns based on viewport width
  const visibleColumns = COLUMNS.filter(([, , minW]) => width >= (minW || 0));

  const tabOptions = isMobile
    ? [["4h", "4H"], ["1d", "1D"]]
    : [["4h", "4H"], ["1d", "1D"], ["split", "SPLIT"]];

  const TableHeader = ({ onSort, currentSort }) => (
    <thead>
      <tr style={{ borderBottom: `1px solid ${T.border}` }}>
        {visibleColumns.map(([key, label]) => (
          <th
            key={label}
            onClick={() => key && onSort(key)}
            style={{
              padding: isMobile ? "8px 10px" : "10px 14px", textAlign: "left",
              fontFamily: T.font, fontSize: isMobile ? 8 : 9, fontWeight: 600,
              color: currentSort === key ? T.accent : T.text4,
              letterSpacing: "0.12em", cursor: key ? "pointer" : "default",
              userSelect: "none", whiteSpace: "nowrap",
              textTransform: "uppercase",
              transition: "color 0.2s",
            }}
          >
            {label}{key && currentSort === key ? " \u25bc" : ""}
          </th>
        ))}
      </tr>
    </thead>
  );

  const DataTable = ({ results, label }) => (
    <div style={{ flex: 1, minWidth: 0 }}>
      {label && (
        <div style={{
          fontFamily: T.font, fontSize: 9, color: T.text4, fontWeight: 600,
          letterSpacing: "0.15em", marginBottom: 10, paddingLeft: isMobile ? 10 : 14,
          textTransform: "uppercase",
        }}>{label}</div>
      )}
      <GlassCard style={{ overflow: "hidden" }}>
        <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <TableHeader onSort={setSortKey} currentSort={sortKey} />
            <tbody>
              {results.length === 0 ? (
                <tr><td colSpan={visibleColumns.length} style={{
                  padding: "60px 14px", textAlign: "center",
                  color: T.text4, fontFamily: T.mono, fontSize: 11,
                }}>
                  {loading ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                      <span style={{ animation: "spin 1.5s linear infinite", display: "inline-block" }}>{"\u25e0"}</span>
                      SCANNING...
                    </span>
                  ) : "NO DATA"}
                </td></tr>
              ) : (
                results.map((row, i) => (
                  <SymbolRow
                    key={row.symbol}
                    row={row}
                    index={i}
                    selected={selected?.symbol === row.symbol}
                    onSelect={setSelected}
                    visibleColumns={visibleColumns}
                    isMobile={isMobile}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.text1 }}>
      {/* Fonts & Global Styles */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: ${T.bg}; -webkit-font-smoothing: antialiased; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.14); }
        tr:hover td { background: transparent !important; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes glow { 0%,100%{box-shadow: 0 0 12px rgba(34,211,238,0.15);} 50%{box-shadow: 0 0 20px rgba(34,211,238,0.3);} }
        select { outline: none; appearance: none; -webkit-appearance: none; }
        select option { background: #18181b; color: #a1a1aa; }
        .notable-scroll::-webkit-scrollbar { display: none; }
        .notable-scroll { scrollbar-width: none; -ms-overflow-style: none; }
      `}</style>

      {/* ── HEADER ── */}
      <div style={{
        padding: `${isMobile ? 12 : 18}px ${hPad}px`,
        borderBottom: `1px solid ${T.border}`,
        display: "flex",
        flexDirection: isMobile ? "column" : "row",
        alignItems: isMobile ? "stretch" : "center",
        justifyContent: "space-between",
        gap: isMobile ? 10 : 0,
        background: "rgba(0,0,0,0.6)",
        backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div>
            <div style={{
              fontSize: isMobile ? 13 : 15, fontWeight: 700, letterSpacing: "0.08em",
              fontFamily: T.font,
              background: "linear-gradient(135deg, #22d3ee, #a78bfa)",
              WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
            }}>
              RCCE SCANNER
            </div>
            <div style={{ fontSize: isMobile ? 9 : 10, color: T.text4, letterSpacing: "0.06em", fontFamily: T.font, fontWeight: 400, marginTop: 2 }}>
              Reflexive Crypto Cycle Engine {"\u00b7"} {data4h.length} symbols
            </div>
          </div>
          {scanRunning && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "4px 12px",
              background: T.accentDim,
              border: `1px solid ${T.accent}20`,
              borderRadius: "20px",
              fontSize: 9, color: T.accent, letterSpacing: "0.08em",
              fontFamily: T.mono, fontWeight: 600,
              animation: "glow 2s ease infinite",
            }}>
              <span style={{ animation: "pulse 1s infinite" }}>{"\u25cf"}</span> SCANNING
            </div>
          )}
        </div>

        <div style={{
          display: "flex", alignItems: "center", gap: isMobile ? 10 : 14,
          justifyContent: isMobile ? "space-between" : "flex-end",
        }}>
          {lastRefresh && (
            <span style={{ fontSize: 9, color: T.text4, letterSpacing: "0.06em", fontFamily: T.font }}>
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          {cacheAge != null && (
            <span style={{
              fontSize: 9, color: T.text4, fontFamily: T.mono,
              padding: "2px 8px", background: T.surface, borderRadius: "20px",
              border: `1px solid ${T.border}`,
            }}>{formatCacheAge(cacheAge)}</span>
          )}
          <button
            onClick={triggerScan}
            style={{
              padding: isMobile ? "10px 20px" : "6px 16px", background: T.surface,
              border: `1px solid ${T.border}`, borderRadius: "20px",
              color: T.text3, fontFamily: T.font, fontSize: 10, fontWeight: 500,
              cursor: "pointer", letterSpacing: "0.06em",
              transition: "all 0.25s ease",
            }}
            onMouseEnter={e => { e.target.style.borderColor = T.accent + "40"; e.target.style.color = T.accent; e.target.style.boxShadow = `0 0 12px ${T.accentDim}`; }}
            onMouseLeave={e => { e.target.style.borderColor = T.border; e.target.style.color = T.text3; e.target.style.boxShadow = "none"; }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* ── CONTROLS ── */}
      <div style={{
        padding: `12px ${hPad}px`,
        borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", gap: isMobile ? 8 : 12, flexWrap: "wrap",
      }}>
        {/* Timeframe tabs */}
        <div style={{
          display: "flex", gap: 2, background: T.surface,
          borderRadius: "20px", padding: 3, border: `1px solid ${T.border}`,
          flex: isMobile ? "1 1 100%" : undefined,
        }}>
          {tabOptions.map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              style={{
                padding: isMobile ? "8px 16px" : "5px 16px", borderRadius: "20px", border: "none",
                background: activeTab === key ? T.accent : "transparent",
                color: activeTab === key ? "#000" : T.text3,
                fontFamily: T.mono, fontSize: 10, cursor: "pointer",
                fontWeight: 600, letterSpacing: "0.06em",
                transition: "all 0.2s ease",
                flex: isMobile ? 1 : undefined,
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {!isMobile && <div style={{ width: 1, height: 18, background: T.border }} />}

        {/* Manage Watchlist */}
        <button
          onClick={() => setShowWatchlist(true)}
          style={{
            padding: isMobile ? "8px 14px" : "5px 14px",
            background: T.surface,
            border: `1px solid ${T.border}`, borderRadius: "20px",
            color: T.text3, fontFamily: T.mono, fontSize: 10, fontWeight: 500,
            cursor: "pointer", letterSpacing: "0.04em",
            transition: "all 0.25s ease",
            display: "flex", alignItems: "center", gap: 6,
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = T.accent + "40"; e.currentTarget.style.color = T.accent; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.text3; }}
        >
          <span style={{ fontSize: 12 }}>{"\u2699"}</span>
          {!isMobile && "Watchlist"}
        </button>

        {!isMobile && <div style={{ width: 1, height: 18, background: T.border }} />}

        {/* Filters */}
        {[
          { value: filterRegime, onChange: e => setFilterRegime(e.target.value), all: "All Regimes", options: Object.keys(REGIME_META) },
          { value: filterSignal, onChange: e => setFilterSignal(e.target.value), all: "All Signals", options: Object.keys(SIGNAL_META) },
        ].map((f, i) => (
          <select
            key={i}
            value={f.value}
            onChange={f.onChange}
            style={{
              padding: isMobile ? "8px 28px 8px 12px" : "5px 28px 5px 12px",
              background: T.surface,
              border: `1px solid ${T.border}`, borderRadius: "20px",
              color: T.text2, fontFamily: T.mono, fontSize: 10, fontWeight: 500,
              cursor: "pointer", letterSpacing: "0.04em",
              flex: isMobile ? 1 : undefined,
              minWidth: 0,
              backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2371717a'/%3E%3C/svg%3E")`,
              backgroundRepeat: "no-repeat",
              backgroundPosition: "right 10px center",
              transition: "border-color 0.2s",
            }}
            onFocus={e => e.target.style.borderColor = T.accent + "40"}
            onBlur={e => e.target.style.borderColor = T.border}
          >
            <option value="ALL">{f.all}</option>
            {f.options.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        ))}
      </div>

      {/* ── ERROR ── */}
      {error && (
        <div style={{ padding: `0 ${hPad}px`, marginTop: 16 }}>
          <GlassCard style={{
            padding: "12px 18px",
            border: "1px solid rgba(248,113,113,0.15)",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <span style={{ color: "#f87171", fontSize: 14 }}>{"\u26a0"}</span>
            <span style={{ fontSize: 11, color: "#fca5a5", fontFamily: T.mono }}>
              API Error: {error} {"\u2014"} ensure backend is running on {API_BASE}
            </span>
          </GlassCard>
        </div>
      )}

      {/* ── MAIN CONTENT ── */}
      <div style={{ padding: `${isMobile ? 16 : 20}px ${hPad}px`, paddingBottom: isMobile ? 80 : 60 }}>

        {/* Summary + Stats */}
        {(data4h.length > 0 || data1d.length > 0) && (
          <FadeIn>
            <SummaryBar results={activeTab === "1d" ? sorted1d : sorted4h} />
            <StatCards results={activeTab === "1d" ? sorted1d : sorted4h} isMobile={isMobile} isTablet={isTablet} />
          </FadeIn>
        )}

        {/* Consensus + Market Context */}
        <ConsensusBar consensus={activeConsensus} isMobile={isMobile} />

        {/* BTC Dominance & Alt Season */}
        {(globalMetrics?.btc_dominance > 0 || altSeason) && (
          <FadeIn delay={380}>
            <div style={{
              display: "flex", gap: isMobile ? 8 : 10,
              marginTop: isMobile ? 10 : 12,
              flexWrap: "wrap",
            }}>
              {globalMetrics?.btc_dominance > 0 && (
                <GlassCard style={{
                  padding: isMobile ? "8px 14px" : "10px 16px",
                  display: "flex", alignItems: "center", gap: 10,
                  flex: isMobile ? "1 1 auto" : undefined,
                }}>
                  <span style={{ fontSize: 9, color: T.text4, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 500, textTransform: "uppercase" }}>
                    BTC.D
                  </span>
                  <span style={{
                    fontFamily: T.mono, fontSize: 13, fontWeight: 700,
                    color: globalMetrics.btc_dominance > 55 ? "#fbbf24" : globalMetrics.btc_dominance > 45 ? T.text1 : "#34d399",
                  }}>
                    {globalMetrics.btc_dominance.toFixed(1)}%
                  </span>
                  {globalMetrics.eth_dominance > 0 && (
                    <>
                      <div style={{ width: 1, height: 14, background: T.border }} />
                      <span style={{ fontSize: 9, color: T.text4, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 500 }}>ETH.D</span>
                      <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 600, color: T.text2 }}>
                        {globalMetrics.eth_dominance.toFixed(1)}%
                      </span>
                    </>
                  )}
                </GlassCard>
              )}
              {altSeason && (
                <GlassCard style={{
                  padding: isMobile ? "8px 14px" : "10px 16px",
                  display: "flex", alignItems: "center", gap: 10,
                  flex: isMobile ? "1 1 auto" : undefined,
                  border: `1px solid ${altSeason.label === "HOT" ? "#f8717120" : altSeason.label === "ACTIVE" ? "#34d39920" : T.border}`,
                }}>
                  <span style={{ fontSize: 9, color: T.text4, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 500, textTransform: "uppercase" }}>
                    Alt Season
                  </span>
                  <span style={{
                    padding: "2px 10px", borderRadius: "20px",
                    background: altSeason.label === "HOT" ? "rgba(248,113,113,0.1)" :
                               altSeason.label === "ACTIVE" ? "rgba(52,211,153,0.1)" :
                               altSeason.label === "NEUTRAL" ? "rgba(251,191,36,0.1)" : "rgba(82,82,91,0.1)",
                    color: altSeason.label === "HOT" ? "#f87171" :
                           altSeason.label === "ACTIVE" ? "#34d399" :
                           altSeason.label === "NEUTRAL" ? "#fbbf24" :
                           altSeason.label === "WEAK" ? "#fb923c" : T.text4,
                    fontSize: 10, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
                  }}>
                    {altSeason.label}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text3, fontWeight: 500 }}>
                    {altSeason.score?.toFixed(0)}
                  </span>
                </GlassCard>
              )}
            </div>
          </FadeIn>
        )}

        {/* Notable Signals */}
        {(notable4h.length > 0 || notable1d.length > 0) && (
          <FadeIn delay={420}>
            <GlassCard
              className="notable-scroll"
              style={{
                marginTop: isMobile ? 12 : 16,
                padding: isMobile ? "10px 14px" : "12px 18px",
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
                fontSize: 9, color: T.text4, letterSpacing: "0.12em",
                fontFamily: T.font, fontWeight: 600, marginRight: 6,
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
                      onClick={() => setSelected(r)}
                      style={{
                        padding: "3px 10px", borderRadius: "20px", cursor: "pointer",
                        background: `${sm.color}08`, border: `1px solid ${sm.color}15`,
                        color: sm.color, fontSize: 10, fontFamily: T.mono, fontWeight: 500,
                        display: "inline-flex", alignItems: "center", gap: 4,
                        transition: "all 0.2s ease",
                        flexShrink: 0,
                      }}
                      onMouseEnter={e => { e.currentTarget.style.background = `${sm.color}18`; e.currentTarget.style.boxShadow = `0 0 10px ${sm.color}15`; }}
                      onMouseLeave={e => { e.currentTarget.style.background = `${sm.color}08`; e.currentTarget.style.boxShadow = "none"; }}
                    >
                      {getBaseSymbol(r.symbol)}
                      <span style={{ fontSize: 8, opacity: 0.5 }}>{r.tf}</span>
                    </span>
                  );
                })}
            </GlassCard>
          </FadeIn>
        )}

        {/* Tables */}
        <div style={{
          display: "flex",
          flexDirection: isDesktop ? "row" : "column",
          gap: isDesktop ? 20 : 16,
          marginTop: isMobile ? 16 : 20,
        }}>
          {(activeTab === "4h" || activeTab === "split") && (
            <FadeIn delay={500} style={{ flex: 1, minWidth: 0 }}>
              <DataTable results={sorted4h} label={activeTab === "split" ? "4H TIMEFRAME" : null} />
            </FadeIn>
          )}
          {activeTab === "split" && (
            <div style={{
              width: isDesktop ? 1 : "100%",
              height: isDesktop ? undefined : 1,
              background: T.border, flexShrink: 0,
            }} />
          )}
          {(activeTab === "1d" || activeTab === "split") && (
            <FadeIn delay={activeTab === "split" ? 600 : 500} style={{ flex: 1, minWidth: 0 }}>
              <DataTable results={sorted1d} label={activeTab === "split" ? "DAILY TIMEFRAME" : null} />
            </FadeIn>
          )}
        </div>
      </div>

      {/* ── WATCHLIST MODAL ── */}
      {showWatchlist && (
        <>
          <div
            onClick={() => setShowWatchlist(false)}
            style={{
              position: "fixed", inset: 0, zIndex: 299,
              background: "rgba(0,0,0,0.6)",
            }}
          />
          <div style={{
            position: "fixed",
            top: isMobile ? "5%" : "50%",
            left: isMobile ? "3%" : "50%",
            transform: isMobile ? "none" : "translate(-50%, -50%)",
            width: isMobile ? "94%" : 480,
            maxHeight: isMobile ? "90vh" : "80vh",
            background: "rgba(0,0,0,0.95)",
            backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)",
            border: `1px solid ${T.borderH}`,
            borderRadius: T.radius,
            zIndex: 300,
            display: "flex", flexDirection: "column",
            boxShadow: "0 20px 60px rgba(0,0,0,0.8)",
          }}>
            {/* Modal Header */}
            <div style={{
              padding: "18px 20px", borderBottom: `1px solid ${T.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: T.text1, fontFamily: T.font, letterSpacing: "-0.01em" }}>
                  Manage Watchlist
                </div>
                <div style={{ fontSize: 10, color: T.text4, fontFamily: T.mono, marginTop: 3 }}>
                  {watchlistSymbols.length} symbols tracked
                </div>
              </div>
              <button
                onClick={() => setShowWatchlist(false)}
                style={{
                  background: T.surface, border: `1px solid ${T.border}`,
                  borderRadius: "50%", width: 28, height: 28,
                  color: T.text3, cursor: "pointer", fontSize: 12,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}
              >{"\u2715"}</button>
            </div>

            {/* Search */}
            <div style={{ padding: "12px 20px", borderBottom: `1px solid ${T.border}` }}>
              <div style={{ position: "relative" }}>
                <input
                  type="text"
                  placeholder="Search symbols (e.g. DOGE, SUI)..."
                  value={watchlistSearch}
                  onChange={e => setWatchlistSearch(e.target.value)}
                  style={{
                    width: "100%", padding: "10px 14px", paddingLeft: 36,
                    background: T.surface, border: `1px solid ${T.border}`,
                    borderRadius: T.radiusSm, color: T.text1,
                    fontFamily: T.mono, fontSize: 12, outline: "none",
                    transition: "border-color 0.2s",
                  }}
                  onFocus={e => e.target.style.borderColor = T.accent + "40"}
                  onBlur={e => e.target.style.borderColor = T.border}
                />
                <span style={{
                  position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)",
                  fontSize: 14, color: T.text4,
                }}>{"\ud83d\udd0d"}</span>
              </div>

              {/* Search results dropdown */}
              {watchlistSearch && watchlistResults.length > 0 && (
                <div style={{
                  marginTop: 6, maxHeight: 200, overflowY: "auto",
                  background: "rgba(24,24,27,0.98)", border: `1px solid ${T.border}`,
                  borderRadius: T.radiusSm,
                }}>
                  {watchlistResults.slice(0, 20).map(r => {
                    const inList = watchlistSymbols.includes(r.symbol);
                    return (
                      <div
                        key={r.symbol}
                        onClick={() => !inList && addSymbol(r.symbol)}
                        style={{
                          padding: "8px 14px", cursor: inList ? "default" : "pointer",
                          display: "flex", justifyContent: "space-between", alignItems: "center",
                          borderBottom: `1px solid ${T.border}`,
                          opacity: inList ? 0.4 : 1,
                          transition: "background 0.15s",
                        }}
                        onMouseEnter={e => { if (!inList) e.currentTarget.style.background = T.surfaceH; }}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                      >
                        <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text1, fontWeight: 500 }}>
                          {r.base}<span style={{ color: T.text4 }}>/USDT</span>
                        </span>
                        {inList ? (
                          <span style={{ fontSize: 9, color: T.text4, fontFamily: T.mono }}>{"\u2713"} Added</span>
                        ) : (
                          <span style={{ fontSize: 9, color: T.accent, fontFamily: T.mono, fontWeight: 600 }}>+ Add</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {watchlistSearch && watchlistResults.length === 0 && !watchlistLoading && (
                <div style={{ marginTop: 8, fontSize: 10, color: T.text4, fontFamily: T.mono, textAlign: "center" }}>
                  No matches found
                </div>
              )}
            </div>

            {/* Current watchlist */}
            <div style={{ flex: 1, overflowY: "auto", padding: "12px 20px" }}>
              <div style={{
                display: "flex", flexWrap: "wrap", gap: 6,
              }}>
                {watchlistSymbols.map(sym => (
                  <span
                    key={sym}
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 6,
                      padding: "5px 10px", borderRadius: "20px",
                      background: T.surface, border: `1px solid ${T.border}`,
                      fontFamily: T.mono, fontSize: 10, color: T.text2, fontWeight: 500,
                    }}
                  >
                    {getBaseSymbol(sym)}
                    <span
                      onClick={() => removeSymbol(sym)}
                      style={{
                        cursor: "pointer", color: T.text4, fontSize: 10,
                        display: "flex", alignItems: "center",
                        transition: "color 0.15s",
                      }}
                      onMouseEnter={e => e.currentTarget.style.color = "#f87171"}
                      onMouseLeave={e => e.currentTarget.style.color = T.text4}
                    >{"\u2715"}</span>
                  </span>
                ))}
              </div>
            </div>

            {/* Modal Footer */}
            <div style={{
              padding: "12px 20px", borderTop: `1px solid ${T.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <button
                onClick={resetWatchlist}
                style={{
                  padding: "7px 16px", background: "transparent",
                  border: `1px solid ${T.border}`, borderRadius: "20px",
                  color: T.text3, fontFamily: T.mono, fontSize: 10, fontWeight: 500,
                  cursor: "pointer", letterSpacing: "0.04em",
                  transition: "all 0.2s",
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "#fb923c40"; e.currentTarget.style.color = "#fb923c"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.text3; }}
              >
                Reset to Defaults
              </button>
              <button
                onClick={() => { setShowWatchlist(false); triggerScan(); }}
                style={{
                  padding: "7px 20px", background: T.accent,
                  border: "none", borderRadius: "20px",
                  color: "#000", fontFamily: T.mono, fontSize: 10, fontWeight: 700,
                  cursor: "pointer", letterSpacing: "0.06em",
                  transition: "all 0.2s",
                }}
                onMouseEnter={e => e.currentTarget.style.opacity = "0.85"}
                onMouseLeave={e => e.currentTarget.style.opacity = "1"}
              >
                Scan Now
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── DETAIL PANEL ── */}
      {selected && isMobile && (
        <div
          onClick={() => setSelected(null)}
          style={{
            position: "fixed", inset: 0, zIndex: 199,
            background: "rgba(0,0,0,0.6)",
          }}
        />
      )}
      {selected && (
        <div style={{
          position: "fixed", right: 0, top: 0, bottom: 0,
          left: isMobile ? 0 : undefined,
          width: isMobile ? "100%" : isTablet ? 300 : 320,
          background: isMobile ? "rgba(0,0,0,0.95)" : "rgba(0,0,0,0.85)",
          backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)",
          borderLeft: isMobile ? "none" : `1px solid ${T.border}`,
          padding: isMobile ? "20px 16px" : "24px 22px",
          overflowY: "auto", zIndex: 200,
          transition: "transform 0.3s ease",
        }}>
          {/* Mobile drag handle */}
          {isMobile && (
            <div style={{
              width: 36, height: 4, borderRadius: 2,
              background: "rgba(255,255,255,0.15)",
              margin: "0 auto 16px auto",
            }} />
          )}

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
            <div>
              <div style={{ fontSize: isMobile ? 20 : 22, fontWeight: 700, color: T.text1, fontFamily: T.font, letterSpacing: "-0.02em" }}>
                {getBaseSymbol(selected.symbol)}
              </div>
              <div style={{ fontSize: 10, color: T.text4, letterSpacing: "0.06em", fontFamily: T.mono, marginTop: 4 }}>
                {selected.symbol} {"\u00b7"} {(selected.timeframe || "").toUpperCase()}
              </div>
            </div>
            <button
              onClick={() => setSelected(null)}
              style={{
                background: T.surface, border: `1px solid ${T.border}`,
                borderRadius: "50%",
                width: isMobile ? 36 : 28,
                height: isMobile ? 36 : 28,
                color: T.text3, cursor: "pointer", fontSize: isMobile ? 14 : 12,
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.2s",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = T.borderH; e.currentTarget.style.color = T.text1; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.text3; }}
            >{"\u2715"}</button>
          </div>

          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <RegimeBadge regime={selected.regime} />
            <SignalDot signal={selected.signal} />
          </div>

          {/* Signal reason */}
          {selected.signal_reason && (
            <div style={{
              padding: "8px 12px", borderRadius: T.radiusXs,
              background: T.surface, border: `1px solid ${T.border}`,
              marginBottom: 12,
            }}>
              <div style={{ fontSize: 8, color: T.text4, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 500, marginBottom: 4, textTransform: "uppercase" }}>
                Signal Reason
              </div>
              <div style={{ fontSize: 10, color: T.text2, fontFamily: T.mono, lineHeight: 1.5 }}>
                {selected.signal_reason}
              </div>
            </div>
          )}

          {/* Signal warnings */}
          {selected.signal_warnings && selected.signal_warnings.length > 0 && (
            <div style={{
              padding: "8px 12px", borderRadius: T.radiusXs,
              background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.1)",
              marginBottom: 16,
            }}>
              {selected.signal_warnings.map((w, i) => (
                <div key={i} style={{
                  fontSize: 9, color: "#fbbf24", fontFamily: T.mono, lineHeight: 1.6,
                  display: "flex", gap: 6, alignItems: "flex-start",
                }}>
                  <span style={{ flexShrink: 0 }}>{"\u26a0"}</span>
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}

          {/* Raw vs Final signal comparison */}
          {selected.raw_signal && selected.raw_signal !== selected.signal && (
            <div style={{
              display: "flex", alignItems: "center", gap: 8, marginBottom: 16,
              fontSize: 9, color: T.text4, fontFamily: T.mono,
            }}>
              <span>Raw: </span>
              <SignalDot signal={selected.raw_signal} />
              <span style={{ color: T.text4 }}>{"\u2192"}</span>
              <span>Final: </span>
              <SignalDot signal={selected.signal} />
            </div>
          )}

          <div style={{ marginBottom: 20 }}>
            <ZScoreBar z={selected.zscore} isMobile={isMobile} />
          </div>

          {[
            ["Z-Score", fmt(selected.zscore, 3), zBar(selected.zscore)?.color],
            ["Energy", fmt(selected.energy, 3), null],
            ["Momentum", `${selected.momentum >= 0 ? "+" : ""}${fmt(selected.momentum, 2)}%`, selected.momentum >= 0 ? "#34d399" : "#f87171"],
            ["Price", selected.price ? `$${selected.price < 1 ? fmt(selected.price, 5) : fmt(selected.price, 2)}` : "\u2014", null],
            ["Divergence", selected.divergence || "None", selected.divergence ? "#fbbf24" : null],
            [null],
            ["Heat", selected.heat != null ? Math.round(selected.heat) : "\u2014", heatColor(selected.heat)],
            ["Phase", selected.heat_phase || "\u2014", phaseColor(selected.heat_phase)],
            ["ATR Regime", selected.atr_regime || "\u2014", null],
            ["Deviation", selected.deviation_pct != null ? `${fmt(selected.deviation_pct, 2)}%` : "\u2014", null],
            [null],
            ["Exhaustion", selected.exhaustion_state || "\u2014", exhaustMeta(selected.exhaustion_state).color],
            ["Floor", selected.floor_confirmed ? "Confirmed" : "No", selected.floor_confirmed ? "#34d399" : null],
            ["Absorption", selected.is_absorption ? "Yes" : "No", selected.is_absorption ? "#67e8f9" : null],
            ["Climax", selected.is_climax ? "Yes" : "No", selected.is_climax ? "#fbbf24" : null],
            ["Effort", selected.effort != null ? fmt(selected.effort, 3) : "\u2014", null],
            ["Rel Volume", selected.rel_vol != null ? fmt(selected.rel_vol, 2) + "x" : "\u2014", null],
          ].map(([label, value, valColor], i) => {
            if (!label) return <div key={i} style={{ height: 1, background: T.border, margin: "8px 0" }} />;
            return (
              <div key={label} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "8px 0",
              }}>
                <span style={{ fontSize: 10, color: T.text4, fontFamily: T.font, fontWeight: 500, letterSpacing: "0.04em" }}>{label}</span>
                <span style={{ fontFamily: T.mono, fontSize: isMobile ? 11 : 12, color: valColor || T.text2, fontWeight: 500 }}>{value}</span>
              </div>
            );
          })}

          <a
            href={`https://www.tradingview.com/chart/?symbol=BINANCE:${getBaseSymbol(selected.symbol)}USDT`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "block", marginTop: 24, padding: isMobile ? "12px 16px" : "10px 16px",
              background: T.surface, border: `1px solid ${T.border}`,
              borderRadius: "20px", color: T.text3, fontFamily: T.font,
              fontSize: 11, textDecoration: "none", textAlign: "center",
              letterSpacing: "0.04em", transition: "all 0.25s ease",
              fontWeight: 500,
            }}
            onMouseEnter={e => { e.target.style.borderColor = T.accent + "40"; e.target.style.color = T.accent; e.target.style.boxShadow = `0 0 16px ${T.accentDim}`; }}
            onMouseLeave={e => { e.target.style.borderColor = T.border; e.target.style.color = T.text3; e.target.style.boxShadow = "none"; }}
          >
            Open in TradingView {"\u2197"}
          </a>
        </div>
      )}
    </div>
  );
}
