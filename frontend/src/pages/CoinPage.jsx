import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { T, REGIME_META, SIGNAL_META, heatColor, phaseColor, exhaustMeta, fmt, zBar, getBaseSymbol, getTVSymbol } from "../theme.js";
import { RegimeBadge, SignalDot } from "../components/badges.jsx";
import useViewport from "../hooks/useViewport.js";
import BMSBChart from "../components/BMSBChart.jsx";
import ConditionsScorecard from "../components/ConditionsScorecard.jsx";
import PositioningPanel from "../components/PositioningPanel.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Confidence Sparkline — shows confidence history as a mini chart
// ---------------------------------------------------------------------------

function ConfidenceSparkline({ history, current }) {
  if (!history || history.length < 2) return null;

  const w = 140, h = 44, pad = 2;
  const vals = history;
  const n = vals.length;
  const min = 0, max = 100;
  const xStep = (w - pad * 2) / Math.max(n - 1, 1);

  const points = vals.map((v, i) => {
    const x = pad + i * xStep;
    const y = h - pad - ((v - min) / (max - min)) * (h - pad * 2);
    return `${x},${y}`;
  }).join(" ");

  // Color based on current value
  const color = current >= 60 ? "#34d399" : current >= 40 ? "#fbbf24" : "#f87171";

  // Threshold lines at 40% and 60%
  const y60 = h - pad - (60 / 100) * (h - pad * 2);
  const y40 = h - pad - (40 / 100) * (h - pad * 2);

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "14px 20px",
      backdropFilter: "blur(20px) saturate(1.3)", WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 10, paddingBottom: 8,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 3, height: 14, borderRadius: 2, background: color, flexShrink: 0 }} />
          <span style={{ fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 700, textTransform: "uppercase" }}>
            Confidence
          </span>
        </div>
        <span style={{ fontFamily: T.mono, fontSize: 14, fontWeight: 700, color }}>
          {current != null ? `${Math.round(current)}%` : "\u2014"}
        </span>
      </div>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", width: "100%" }}>
        {/* Threshold lines */}
        <line x1={pad} y1={y60} x2={w - pad} y2={y60} stroke={T.overlay06} strokeWidth="0.5" strokeDasharray="3,3" />
        <line x1={pad} y1={y40} x2={w - pad} y2={y40} stroke={T.overlay06} strokeWidth="0.5" strokeDasharray="3,3" />
        {/* Sparkline */}
        <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        {/* Current value dot */}
        {n > 0 && (() => {
          const lastX = pad + (n - 1) * xStep;
          const lastY = h - pad - ((vals[n - 1] - min) / (max - min)) * (h - pad * 2);
          return <circle cx={lastX} cy={lastY} r="2.5" fill={color} />;
        })()}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
        <span style={{ fontSize: 8, color: T.text4, fontFamily: T.mono }}>{n} ticks</span>
        <span style={{ fontSize: 8, color: T.text4, fontFamily: T.mono }}>
          {vals.length > 1 ? `${Math.round(Math.min(...vals))}-${Math.round(Math.max(...vals))}%` : ""}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Generic Metric Sparkline — auto-scaled, compact
// ---------------------------------------------------------------------------

function MetricSparkline({ label, history, current, unit, colorFn }) {
  if (!history || history.length < 2) return null;

  const w = 120, h = 32, pad = 2;
  const vals = history;
  const n = vals.length;
  const dataMin = Math.min(...vals);
  const dataMax = Math.max(...vals);
  const range = dataMax - dataMin || 1;
  const xStep = (w - pad * 2) / Math.max(n - 1, 1);

  const points = vals.map((v, i) => {
    const x = pad + i * xStep;
    const y = h - pad - ((v - dataMin) / range) * (h - pad * 2);
    return `${x},${y}`;
  }).join(" ");

  const color = colorFn ? colorFn(current) : (current >= vals[0] ? "#34d399" : "#f87171");
  const lastX = pad + (n - 1) * xStep;
  const lastY = h - pad - ((vals[n - 1] - dataMin) / range) * (h - pad * 2);

  const fmtVal = (v) => {
    if (v == null) return "\u2014";
    if (unit === "%") {
      // Use more decimals for very small values (e.g. funding rates)
      const abs = Math.abs(v);
      const decimals = abs > 0 && abs < 0.01 ? 4 : 2;
      return `${v.toFixed(decimals)}%`;
    }
    if (unit === "$") return v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v).toLocaleString()}`;
    if (unit === "x") return `${v.toFixed(3)}x`;
    return String(v);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: T.textSm, color: T.text3, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
          {label}
        </span>
        <span style={{ fontSize: T.textBase, color, fontFamily: T.mono, fontWeight: 700 }}>
          {fmtVal(current)}
        </span>
      </div>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", width: "100%" }}>
        <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.85" />
        <circle cx={lastX} cy={lastY} r="2.5" fill={color} />
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Combined Confluence + Win Rate card
// ---------------------------------------------------------------------------

function ConfluenceCard({ confluence }) {
  if (!confluence) return null;

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "16px 20px",
      backdropFilter: "blur(20px) saturate(1.3)", WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <ConfluenceSection confluence={confluence} />
    </div>
  );
}

// Confluence section (extracted from ConfluencePanel, no outer card wrapper)
function ConfluenceSection({ confluence }) {
  const { score, label, regime_aligned, signal_aligned,
    regime_4h, regime_1d, signal_4h, signal_1d } = confluence;

  const scoreColor = (s) => s >= 75 ? "#34d399" : s >= 50 ? "#facc15" : s >= 25 ? "#fb923c" : "#f87171";
  const labelColor = (l) => ({ STRONG: "#34d399", MODERATE: "#facc15", WEAK: "#fb923c", CONFLICTING: "#f87171" }[l] || T.text4);
  const color = scoreColor(score ?? 0);
  const lColor = labelColor(label);
  const r4h = REGIME_META[regime_4h] || REGIME_META.FLAT;
  const r1d = REGIME_META[regime_1d] || REGIME_META.FLAT;
  const s4h = SIGNAL_META[signal_4h] || SIGNAL_META.WAIT;
  const s1d = SIGNAL_META[signal_1d] || SIGNAL_META.WAIT;

  return (
    <>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 14, paddingBottom: 10, borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
        <span style={{
          fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em",
          fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
        }}>Confluence</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div style={{ flex: 1, height: 5, background: T.overlay04, borderRadius: 3, overflow: "hidden" }}>
          <div style={{
            width: `${Math.min(score ?? 0, 100)}%`, height: "100%",
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            borderRadius: 3, boxShadow: `0 0 8px ${color}30`, transition: "width 0.6s ease",
          }} />
        </div>
        <span style={{ fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700, color, minWidth: 32, textAlign: "right" }}>
          {score != null ? Math.round(score) : "\u2014"}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{
          padding: "4px 12px", borderRadius: 20,
          background: `${lColor}15`, color: lColor,
          fontSize: T.textSm, fontFamily: T.mono, fontWeight: 700,
          letterSpacing: "0.06em", border: `1px solid ${lColor}25`,
        }}>{label || "\u2014"}</span>
        <div style={{ display: "flex", gap: 10, marginLeft: "auto" }}>
          {[["Regime", regime_aligned], ["Signal", signal_aligned]].map(([lbl, ok]) => (
            <span key={lbl} style={{
              fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600,
              color: ok ? "#34d399" : "#f87171", display: "flex", alignItems: "center", gap: 4,
            }}>
              {ok ? "\u2713" : "\u2717"}
              <span style={{ fontSize: T.textXs, color: T.text4 }}>{lbl}</span>
            </span>
          ))}
        </div>
      </div>

      {[
        { tf: "4H", rm: r4h, regime: regime_4h, sm: s4h, signal: signal_4h },
        { tf: "1D", rm: r1d, regime: regime_1d, sm: s1d, signal: signal_1d },
      ].map(row => (
        <div key={row.tf} style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0",
        }}>
          <span style={{ fontSize: T.textSm, color: T.text4, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.08em", minWidth: 28 }}>
            {row.tf}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{
              padding: "3px 10px", borderRadius: 20, background: row.rm.bg, color: row.rm.color,
              fontSize: T.textXs, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.04em", border: `1px solid ${row.rm.color}20`,
            }}>{row.regime || "\u2014"}</span>
            <span style={{ color: T.text4, fontSize: T.textSm }}>{"\u2192"}</span>
            <span style={{
              fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600, color: row.sm.color,
              display: "inline-flex", alignItems: "center", gap: 4,
            }}>
              <span style={{ fontSize: 9, filter: row.signal !== "WAIT" ? `drop-shadow(0 0 3px ${row.sm.color})` : "none" }}>
                {row.sm.dot}
              </span>
              {row.sm.label}
            </span>
          </div>
        </div>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Metrics Panel — unified sparklines card
// ---------------------------------------------------------------------------

function MetricsPanel({ data }) {
  const pos = data.positioning || {};

  // Color functions for each metric
  const confColor = (v) => v >= 60 ? "#34d399" : v >= 40 ? "#fbbf24" : "#f87171";
  const fundColor = (v) => v < 0 ? "#34d399" : v > 0.01 ? "#f87171" : T.text3;
  const oiChgColor = (v) => v > 0 ? "#34d399" : v < 0 ? "#f87171" : T.text3;
  const lsrColor = (v) => v < 0.9 ? "#34d399" : v > 1.2 ? "#f87171" : T.text3;
  const bsrColor = (v) => v > 1 ? "#34d399" : v < 1 ? "#f87171" : T.text3;
  const spotColor = (v) => v > 0.5 ? "#34d399" : v < 0.3 ? "#f87171" : T.text3;

  const metrics = [
    { label: "Confidence", history: data.confidence_history, current: data.confidence, unit: "%", colorFn: confColor },
    { label: "Funding", history: data.funding_history, current: pos.funding_rate != null ? pos.funding_rate * 100 : null, unit: "%", colorFn: fundColor },
    { label: "Open Interest", history: data.oi_history, current: pos.oi_value, unit: "$", colorFn: null },
    { label: "OI Change", history: data.oi_change_history, current: pos.oi_change_pct, unit: "%", colorFn: oiChgColor },
    { label: "LSR", history: data.lsr_history, current: pos.long_short_ratio, unit: "x", colorFn: lsrColor },
    { label: "Buy/Sell", history: data.bsr_history, current: data.buy_sell_ratio, unit: "x", colorFn: bsrColor },
    { label: "Spot Ratio", history: data.spot_ratio_history, current: pos.spot_futures_ratio, unit: "x", colorFn: spotColor },
  ].filter(m => m.history && m.history.length >= 2);

  if (metrics.length === 0) return null;

  // Determine accent color from confidence
  const conf = data.confidence;
  const accent = conf >= 60 ? "#34d399" : conf >= 40 ? "#fbbf24" : "#f87171";

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "14px 20px",
      backdropFilter: "blur(20px) saturate(1.3)", WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 12, paddingBottom: 8,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: accent, flexShrink: 0 }} />
        <span style={{ fontSize: T.textBase, color: T.text2, letterSpacing: "0.1em", fontFamily: T.mono, fontWeight: 700, textTransform: "uppercase" }}>
          Metrics
        </span>
        <span style={{ fontSize: T.textXs, color: T.text4, fontFamily: T.mono, marginLeft: "auto" }}>
          {metrics[0].history.length} ticks
        </span>
      </div>
      <div style={{
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}>
        {metrics.map(m => (
          <MetricSparkline key={m.label} {...m} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Engine Metrics Grid (extracted from DetailPanel)
// ---------------------------------------------------------------------------

function EngineMetrics({ data, isMobile }) {
  const rows = [
    ["Z-Score", fmt(data.zscore, 3), zBar(data.zscore)?.color],
    ["Energy", fmt(data.energy, 3), null],
    ["Momentum", `${data.momentum >= 0 ? "+" : ""}${fmt(data.momentum, 2)}%`, data.momentum >= 0 ? "#34d399" : "#f87171"],
    ["Price", data.price ? `$${data.price < 1 ? fmt(data.price, 5) : fmt(data.price, 2)}` : "\u2014", null],
    ["Divergence", data.divergence || "None", data.divergence ? "#fbbf24" : null],
    [null],
    ["Heat", data.heat != null ? Math.round(data.heat) : "\u2014", heatColor(data.heat)],
    ["Phase", data.heat_phase || "\u2014", phaseColor(data.heat_phase)],
    ["ATR Regime", data.atr_regime || "\u2014", null],
    ["Deviation", data.deviation_pct != null ? `${fmt(data.deviation_pct, 2)}%` : "\u2014", null],
    [null],
    ["Exhaustion", data.exhaustion_state || "\u2014", exhaustMeta(data.exhaustion_state).color],
    ["Floor", data.floor_confirmed ? "Confirmed" : "No", data.floor_confirmed ? "#34d399" : null],
    ["Absorption", data.is_absorption ? "Yes" : "No", data.is_absorption ? "#67e8f9" : null],
    ["Climax", data.is_climax ? "Yes" : "No", data.is_climax ? "#fbbf24" : null],
    ["Effort", data.effort != null ? fmt(data.effort, 3) : "\u2014", null],
    ["Rel Volume", data.rel_vol != null ? fmt(data.rel_vol, 2) + "x" : "\u2014", null],
  ];

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: isMobile ? "14px 14px" : "16px 20px",
      backdropFilter: "blur(20px) saturate(1.3)", WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 14, paddingBottom: 10,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
        <span style={{ fontSize: T.textBase, color: T.text2, letterSpacing: "0.1em", fontFamily: T.mono, fontWeight: 700, textTransform: "uppercase" }}>
          Engine Metrics
        </span>
      </div>
      {rows.map(([label, value, valColor], i) => {
        if (!label) return <div key={i} style={{ height: 1, background: T.overlay06, margin: "6px 0" }} />;
        return (
          <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 0" }}>
            <span style={{ fontSize: T.textSm, color: T.text3, fontFamily: T.mono, fontWeight: 500, letterSpacing: "0.04em" }}>{label}</span>
            <span style={{ fontFamily: T.mono, fontSize: T.textBase, color: valColor || T.text1, fontWeight: 600 }}>{value}</span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Smart Money Panel (whale consensus for this symbol)
// ---------------------------------------------------------------------------

function SmartMoneyPanel({ data }) {
  const sm = data?.smart_money;
  if (!sm) return null;

  const trendColor = sm.trend === "BULLISH" ? "#34d399" : sm.trend === "BEARISH" ? "#f87171" : T.text4;
  const longPct = sm.long_count + sm.short_count > 0
    ? Math.round(sm.long_count / (sm.long_count + sm.short_count) * 100)
    : 50;

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "16px 20px",
      backdropFilter: "blur(20px) saturate(1.3)", WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 14, paddingBottom: 10,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: "#a78bfa", flexShrink: 0 }} />
        <span style={{ fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 700, textTransform: "uppercase" }}>
          Whale Consensus
        </span>
        <span style={{
          fontSize: T.textSm, fontWeight: 700, color: trendColor, fontFamily: T.mono,
          marginLeft: "auto", padding: "3px 10px", borderRadius: 20,
          background: `${trendColor}15`, border: `1px solid ${trendColor}28`,
        }}>
          {sm.trend}
        </span>
      </div>

      {/* L/S bar */}
      <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", marginBottom: 10 }}>
        <div style={{ width: `${longPct}%`, background: "#34d399", transition: "width 0.3s" }} />
        <div style={{ flex: 1, background: "#f87171" }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: T.textSm, fontFamily: T.mono, marginBottom: 10 }}>
        <span style={{ color: "#34d399" }}>{longPct}% LONG</span>
        <span style={{ color: "#f87171" }}>{100 - longPct}% SHORT</span>
      </div>

      {/* Stats */}
      {[
        ["Wallets Long", sm.long_count, "#34d399"],
        ["Wallets Short", sm.short_count, "#f87171"],
        ["Confidence", `${Math.round(sm.confidence * 100)}%`, trendColor],
        ["Net Ratio", sm.net_ratio > 0 ? `+${sm.net_ratio.toFixed(2)}` : sm.net_ratio.toFixed(2), sm.net_ratio > 0 ? "#34d399" : "#f87171"],
      ].map(([label, val, color]) => (
        <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "7px 0" }}>
          <span style={{ fontSize: T.textSm, color: T.text3, fontFamily: T.font }}>{label}</span>
          <span style={{ fontSize: T.textBase, color, fontFamily: T.mono, fontWeight: 600 }}>{val}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CoinPage — full analysis page for a single symbol
// ---------------------------------------------------------------------------

export default function CoinPage({ scanData4h, scanData1d, urlSymbol }) {
  const navigate = useNavigate();
  const { isMobile, isTablet } = useViewport();
  const [timeframe, setTimeframe] = useState("1d");

  // Find scan result matching URL symbol
  const data = useMemo(() => {
    const scanData = timeframe === "4h" ? scanData4h : scanData1d;
    if (!scanData || scanData.length === 0) return null;
    const sym = (urlSymbol || "").toUpperCase();
    return scanData.find(r => {
      const base = getBaseSymbol(r.symbol).replace("/", "").toUpperCase();
      return base === sym || r.symbol?.toUpperCase() === sym || r.symbol?.toUpperCase() === `${sym}/USDT`;
    });
  }, [scanData4h, scanData1d, urlSymbol, timeframe]);

  // Scroll to top on open
  useEffect(() => { window.scrollTo(0, 0); }, [urlSymbol]);

  // Set document title
  useEffect(() => {
    if (data) {
      document.title = `${getBaseSymbol(data.symbol)} | RCCE Scanner`;
    }
    return () => { document.title = "RCCE Scanner"; };
  }, [data]);

  if (!data) {
    return (
      <div style={{ padding: 40, textAlign: "center" }}>
        <div style={{ fontSize: 16, color: T.text3, fontFamily: T.mono, marginBottom: 16 }}>
          {urlSymbol ? `Loading ${urlSymbol.toUpperCase()}...` : "Symbol not found"}
        </div>
        <button
          onClick={() => navigate("/scanner")}
          className="apple-btn"
          style={{ padding: "8px 20px", fontSize: 12, fontFamily: T.mono, borderRadius: 8 }}
        >
          {"\u2190"} Back to Scanner
        </button>
      </div>
    );
  }

  const isWide = !isMobile && !isTablet;
  const coin = getBaseSymbol(data.symbol);

  return (
    <div style={{ padding: isMobile ? 16 : 24 }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, marginBottom: 20, flexWrap: "wrap",
      }}>
        <button
          onClick={() => navigate("/scanner")}
          className="apple-btn"
          style={{ padding: "7px 16px", fontSize: T.textSm, fontFamily: T.font, fontWeight: 600, borderRadius: 8, flexShrink: 0 }}
        >
          {"\u2190"} Scanner
        </button>
        <img
          src={`https://assets.coincap.io/assets/icons/${coin.toLowerCase()}@2x.png`}
          alt=""
          style={{
            width: isMobile ? 32 : 40, height: isMobile ? 32 : 40,
            borderRadius: "50%", flexShrink: 0, background: T.overlay04,
          }}
          onError={e => { e.target.style.display = "none"; }}
        />
        <span style={{ fontSize: isMobile ? 24 : 32, fontWeight: 700, color: T.text1, fontFamily: T.font, letterSpacing: "-0.02em" }}>
          {coin}
        </span>
        <RegimeBadge regime={data.regime} />
        <SignalDot signal={data.signal} />
        {data.signal_confidence != null && (
          <span style={{
            padding: "4px 12px", borderRadius: 20,
            background: T.surface, border: `1px solid ${T.border}`,
            fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600,
            color: data.signal_confidence >= 80 ? "#34d399" : data.signal_confidence >= 50 ? "#fbbf24" : T.text3,
          }}>
            {data.signal_confidence}%
          </span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", borderRadius: 8, border: `1px solid ${T.border}`, overflow: "hidden" }}>
          {["4h", "1d"].map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              style={{
                padding: isMobile ? "8px 14px" : "6px 14px", border: "none",
                background: timeframe === tf ? T.accent : "transparent",
                color: timeframe === tf ? T.bg : T.text3,
                fontFamily: T.font, fontSize: T.textSm, fontWeight: timeframe === tf ? 700 : 500,
                cursor: "pointer", letterSpacing: "0.04em", transition: "all 0.15s ease",
              }}>
              {tf.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Chart — full width */}
      <div style={{ marginBottom: 20 }}>
        <BMSBChart
          symbol={data.symbol}
          timeframe={timeframe}
          height={isMobile ? 380 : 520}
          signal={data.signal}
          regime={data.regime}
          heat={data.heat}
          conditions={data.conditions_met}
          conditionsTotal={data.conditions_total}
          exhaustionState={data.exhaustion_state}
          floorConfirmed={data.floor_confirmed}
          signalConfidence={data.signal_confidence}
          momentum={data.momentum}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
          <a
            href={`https://app.hyperliquid.xyz/trade/${data.symbol.split("/")[0]}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "5px 12px", borderRadius: 8,
              fontSize: T.textSm, fontFamily: T.font, fontWeight: 600,
              color: T.text4, textDecoration: "none",
              border: `1px solid ${T.border}`, background: "transparent",
              transition: "color 0.15s, border-color 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = "#22d3ee"; e.currentTarget.style.borderColor = "#22d3ee"; }}
            onMouseLeave={e => { e.currentTarget.style.color = T.text4; e.currentTarget.style.borderColor = T.border; }}
          >
            Trade on Hyperliquid {"\u2197"}
          </a>
          <a
            href={`https://www.tradingview.com/chart/?symbol=${getTVSymbol(data.symbol)}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "5px 12px", borderRadius: 8,
              fontSize: T.textSm, fontFamily: T.font, fontWeight: 600,
              color: T.text4, textDecoration: "none",
              border: `1px solid ${T.border}`, background: "transparent",
              transition: "color 0.15s, border-color 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = T.accent; e.currentTarget.style.borderColor = T.accent; }}
            onMouseLeave={e => { e.currentTarget.style.color = T.text4; e.currentTarget.style.borderColor = T.border; }}
          >
            Open in TradingView {"\u2197"}
          </a>
        </div>
      </div>

      {/* Signal Reason + Warnings — full width banner */}
      {(data.signal_reason || (data.signal_warnings && data.signal_warnings.length > 0)) && (
        <div style={{
          display: "flex", gap: 16, marginBottom: 20,
          flexDirection: isMobile ? "column" : "row",
        }}>
          {data.signal_reason && (
            <div style={{
              flex: 1, padding: "14px 18px", borderRadius: 12,
              background: T.glassBg, border: `1px solid ${T.border}`,
              backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <div style={{ width: 3, height: 14, borderRadius: 2, background: T.text3, flexShrink: 0 }} />
                <span style={{ fontSize: T.textSm, color: T.text4, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 600, textTransform: "uppercase" }}>Signal Reason</span>
              </div>
              <div style={{ fontSize: T.textBase, color: T.text2, fontFamily: T.mono, lineHeight: 1.7, paddingLeft: 11 }}>
                {data.signal_reason}
              </div>
            </div>
          )}
          {data.signal_warnings && data.signal_warnings.length > 0 && (
            <div style={{
              flex: 1, padding: "14px 18px", borderRadius: 12,
              background: "rgba(251,191,36,0.03)", border: "1px solid rgba(251,191,36,0.12)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <div style={{ width: 3, height: 14, borderRadius: 2, background: "#fbbf24", flexShrink: 0 }} />
                <span style={{ fontSize: T.textSm, color: "#fbbf24", letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 600, textTransform: "uppercase" }}>Warnings</span>
              </div>
              {data.signal_warnings.map((w, i) => (
                <div key={i} style={{ fontSize: T.textBase, color: "#fbbf24", fontFamily: T.mono, lineHeight: 1.7, display: "flex", gap: 6, alignItems: "flex-start" }}>
                  <span style={{ flexShrink: 0 }}>{"\u26a0"}</span>
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Data panels — responsive grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr" : isWide ? "1fr 1fr 1fr" : "1fr 1fr",
        gap: 16,
      }}>
        {/* Conditions */}
        <ConditionsScorecard
          conditions={data.conditions_detail}
          met={data.conditions_met}
          total={data.conditions_total}
        />

        {/* Confluence */}
        <ConfluenceCard confluence={data.confluence} />

        {/* Positioning */}
        <PositioningPanel
          positioning={data.positioning}
          cvdTrend={data.cvd_trend}
          cvdDiv={data.cvd_divergence}
          bsr={data.buy_sell_ratio}
          oiContext={data.oi_context}
        />

        {/* Whale Consensus */}
        <SmartMoneyPanel data={data} />

        {/* Metrics — unified sparklines panel */}
        <MetricsPanel data={data} />

        {/* Engine Metrics (includes Z-Score) */}
        <EngineMetrics data={data} isMobile={isMobile} />
      </div>
    </div>
  );
}
