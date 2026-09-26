import { traderLean, usd } from "../utils/traders.js";
import HelpTip from "./HelpTip.jsx";
import SignalContext, { CONTEXT_META } from "./SignalContext.jsx";
import { signalContext, friendlyReason } from "../utils/signalPresentation.js";
import { col, T, m, REGIME_META, SIGNAL_META, heatColor, phaseColor, exhaustMeta, fmt, zBar } from "../theme.js";
import RegimeIcon from "./RegimeIcon.jsx";

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
      <span style={{ color: T.text1, fontFamily: T.mono, fontSize: m(isMobile ? 12 : 13, isMobile), minWidth: 40, textAlign: "right", fontWeight: 600 }}>
        {fmt(z, 2)}
      </span>
    </div>
  );
}

export function RegimeBadge({ regime, isMobile, noHistory = false }) {
  // No candle history means no measured regime: say so instead of showing Flat.
  if (noHistory) return <span className="terminal-status" title="Not enough candle history to measure a regime. Left out of the market consensus."
    style={{ color: T.text4, fontSize: m(12, isMobile), fontWeight: 600, letterSpacing: "0.02em", whiteSpace: "nowrap" }}>No history</span>;
  const rm = REGIME_META[regime] || REGIME_META.FLAT;
  // Icon + plain-English phase name. The engine code stays in the tooltip for
  // anyone who wants it. No capsule: status reads through type and color.
  return (
    <span className="terminal-status" title={`${rm.label} — ${rm.hint}`} style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      color: rm.color, fontSize: m(12, isMobile), fontWeight: 600,
      letterSpacing: "0.02em", whiteSpace: "nowrap",
    }}>
      <RegimeIcon regime={regime} size={m(14, isMobile)} />
      {rm.name}
    </span>
  );
}

export function SignalDot({ signal, reason, warnings, context, isMobile, marketWide }) {
  const sm = SIGNAL_META[signal] || {color:T.text3, label:signal?.replaceAll('_',' ') || 'WAIT'};
  const row = context || {signal, signal_reason:reason, signal_warnings:warnings};
  const items = signalContext(row, { marketWide });
  const kinds = [...new Set(items.map(i => i.kind))].sort((a,b) => ['conflict','caution','missing','bearish','bullish','info'].indexOf(a) - ['conflict','caution','missing','bearish','bullish','info'].indexOf(b));
  return <span className="signal-label" style={{display:'inline-flex',alignItems:'center',gap:6,color:sm.color,fontFamily:T.mono,fontSize:m(12,isMobile),fontWeight:600,whiteSpace:'nowrap'}}>
    {sm.label}
    {(reason || items.length > 0) && <HelpTip className="signal-context-trigger" title="Signal context" width={360} label={kinds.map(k=>CONTEXT_META[k].label).join(', ') || 'Signal explanation'} size={20}
      buttonStyle={{width:'auto',minWidth:22,height:26,border:0,borderRadius:4,display:'inline-flex',alignItems:'center',gap:3,padding:'2px 3px'}}
      icon={<>{(kinds.length ? kinds.slice(0,2) : ['info']).map(k=>{const {Icon,color}=CONTEXT_META[k];return <Icon key={k} size={13} color={col(color)}/>;})}</>}>
      <SignalContext row={row} marketWide={marketWide}/>
      {reason && <p style={{borderTop:`1px solid ${T.border}`,paddingTop:8,fontSize:T.textXs,color:T.text3}}>{friendlyReason(reason)}</p>}
    </HelpTip>}
  </span>;
}

export function DivergencePill({ div }) {
  if (!div) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const isBull = div.includes("BULL");
  const color = isBull ? "#34d399" : "#f87171";
  const glyph = isBull ? "\u25b2" : "\u25bc";
  return (
    <span className="terminal-status" style={{
      padding: "3px 8px", borderRadius: "20px",
      background: `${color}14`, color,
      fontSize: 10, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.04em", border: `1px solid ${color}28`,
      whiteSpace: "nowrap",
    }}>
      {glyph} DIV
    </span>
  );
}

const PHASE_ABBR = { Entry: "ENTR", Extension: "EXT", Exhaustion: "EXHS", Fading: "FADE" };

export function HeatCell({ heat, phase, isMobile }) {
  if (heat == null) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  const color = heatColor(heat);
  const pct = Math.min(heat, 100);
  const abbr = phase && phase !== "Neutral" ? PHASE_ABBR[phase] || phase.slice(0, 4).toUpperCase() : null;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
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
      {abbr && (
        <span style={{
          fontFamily: T.mono, fontSize: 8, color: phaseColor(phase),
          fontWeight: 700, letterSpacing: "0.06em", opacity: 0.75, lineHeight: 1,
        }}>
          {abbr}
        </span>
      )}
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

export function ExhaustBadge({ state, floorConfirmed }) {
  const meta = exhaustMeta(state);
  if (meta.text === "\u2014") return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  // "FLOOR ✓" when confirmed, "FLOOR" when forming-but-unconfirmed
  const label = state === "FLOOR"
    ? (floorConfirmed ? "FLOOR \u2713" : "FLOOR")
    : meta.text;
  const glowColor = state === "FLOOR" && floorConfirmed ? "#34d399" : meta.color;
  return (
    <span className="terminal-status" style={{
      padding: "3px 9px", borderRadius: "20px",
      background: `${glowColor}14`, color: glowColor,
      fontSize: 11, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.04em", border: `1px solid ${glowColor}25`,
    }}>
      {label}
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
    <span className="terminal-status" style={{
      padding: "3px 8px", borderRadius: "20px",
      background: `${meta.color}14`, color: meta.color,
      fontSize: 11, fontFamily: T.mono, fontWeight: 600,
      letterSpacing: "0.04em", border: `1px solid ${meta.color}25`,
    }}>
      {meta.label}
    </span>
  );
}

export function CVDBadge({ trend, divergence, bsr, isMobile }) {
  if (!trend || trend === "NEUTRAL") return null;
  if (trend === "UNAVAILABLE") return (
    <span style={{
      fontFamily: T.mono, fontSize: isMobile ? 10 : 11,
      color: T.text4, opacity: 0.5,
    }}>{"\u2014"}</span>
  );

  const COLORS = {
    BULLISH: T.green,
    BEARISH: T.red,
  };
  const ICONS = {
    BULLISH: "\u25b2",
    BEARISH: "\u25bc",
  };

  const color = COLORS[trend] || T.text4;
  const icon = ICONS[trend] || "\u25cf";

  return (
    <span className="terminal-status" style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      padding: "3px 8px", borderRadius: 20,
      background: color + "14",
      border: `1px solid ${color}25`,
      fontFamily: T.mono, fontSize: isMobile ? 10 : 11,
      color,
      fontWeight: 600,
      letterSpacing: "0.04em",
    }}>
      {icon} {trend === "BULLISH" ? "BUY" : "SELL"}
      {divergence && (
        <span style={{ fontSize: 9, color: "#f59e0b", marginLeft: 2 }} title="CVD/Price divergence">{"\u26a1"}</span>
      )}
      {bsr != null && (
        <span style={{ fontSize: 9, color, opacity: 0.7, marginLeft: 2 }}>{bsr.toFixed(2)}x</span>
      )}
    </span>
  );
}

// Profitable traders on this market (grid column "SM"); all tracked wallets in the tooltip.
export function SmartMoneyBadge({ sm }) {
  if (!sm) return null;
  const l = traderLean(sm.profitable);
  const all = sm.trend ? `All tracked wallets, weighted by size: ${sm.trend.toLowerCase()} (${sm.long_count} long / ${sm.short_count} short)` : "";
  if (!l.side || l.side === "mixed") return (
    <span title={[l.n ? `Profitable traders: ${l.long} long / ${l.short} short` : "Fewer than 3 profitable traders positioned", all].filter(Boolean).join("\n")}
      style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, opacity: 0.6 }}>{l.side === "mixed" ? "mixed" : "\u2014"}</span>
  );
  const color = l.side === "long" ? T.green : T.red;
  return (
    <span
      title={`Profitable traders: ${l.long} long (${usd(l.longUsd)}) / ${l.short} short (${usd(l.shortUsd)})\n${all}`}
      className="terminal-status" style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "3px 7px", borderRadius: 20,
        background: color + "14", border: `1px solid ${color}25`,
        fontFamily: T.mono, fontSize: 10, color, fontWeight: 600,
      }}
    >
      {l.side === "long" ? "\u25b2" : "\u25bc"}
      <span style={{ fontSize: 9, opacity: 0.8 }}>{l.side === "long" ? l.long : l.short}/{l.n}</span>
    </span>
  );
}


export function ConfluenceBadge({ score, label }) {
  if (score == null && !label) return <span style={{ color: T.text4 }}>{"\u2014"}</span>;
  // Agreement strength in one hue (bright when strong, dim when weak); amber and red
  // stay reserved for caution and downside.
  const color = (score ?? 0) >= 75 ? col("#34d399") : (score ?? 0) >= 50 ? col("#6ee7b7") : col("#52525b");
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
      <span style={{ fontFamily: T.mono, fontSize: 12, color: T.text1, fontWeight: 600 }}>
        {score != null ? Math.round(score) : "\u2014"}
      </span>
    </div>
  );
}
