import { useState, useEffect, useCallback, useRef } from "react";
import {
  createChart, AreaSeries, ColorType, LineStyle, CrosshairMode,
} from "lightweight-charts";
import { T } from "../theme.js";
import { useWallet } from "../WalletContext.jsx";
import * as hlClient from "../services/hlClient.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(ts) {
  if (!ts) return "\u2014";
  const s = typeof ts === "number" && ts > 1e12 ? ts / 1000 : ts;
  const diff = (Date.now() / 1000) - s;
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${(diff / 3600).toFixed(1)}h ago`;
  return `${(diff / 86400).toFixed(1)}d ago`;
}

function fmtUsd(v) {
  if (v == null) return "\u2014";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (isNaN(n)) return "\u2014";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPrice(p) {
  if (!p) return "\u2014";
  const n = typeof p === "string" ? parseFloat(p) : p;
  if (isNaN(n)) return "\u2014";
  if (n >= 1000) return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (n >= 1) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(6)}`;
}

function fmtPnl(pct) {
  if (pct == null) return "\u2014";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function fmtVlm(v) {
  if (!v) return "$0";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtBps(rate) {
  if (!rate) return "\u2014";
  const bps = parseFloat(rate) * 10000;
  return `${bps.toFixed(2)} bps`;
}

function pnlColor(v) {
  if (v == null || v === 0) return T.text3;
  return v > 0 ? "#34d399" : "#f87171";
}

function parseNum(v) {
  if (v == null) return 0;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}

// ---------------------------------------------------------------------------
// Scanner context helpers
// ---------------------------------------------------------------------------

const ENTRY_SIGNALS = new Set(["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED"]);
const EXIT_SIGNALS  = new Set(["TRIM", "TRIM_HARD", "RISK_OFF"]);

const SIGNAL_COMPACT = {
  STRONG_LONG:  "STRONG",
  LIGHT_LONG:   "LIGHT",
  ACCUMULATE:   "ACCUM",
  REVIVAL_SEED: "SEED",
  TRIM:         "TRIM",
  TRIM_HARD:    "TRIM!",
  RISK_OFF:     "RISK OFF",
  NO_LONG:      "NO LONG",
  WAIT:         "WAIT",
};

const SIGNAL_COLOR = {
  STRONG_LONG:  "#34d399",
  LIGHT_LONG:   "#6ee7b7",
  ACCUMULATE:   "#22d3ee",
  REVIVAL_SEED: "#a78bfa",
  TRIM:         "#fbbf24",
  TRIM_HARD:    "#f97316",
  RISK_OFF:     "#f87171",
  NO_LONG:      "#9ca3af",
  WAIT:         "#6b7280",
};

const REGIME_COLOR = {
  MARKUP:   "#34d399",
  BLOWOFF:  "#fbbf24",
  REACC:    "#22d3ee",
  MARKDOWN: "#f87171",
  CAP:      "#f87171",
  ACCUM:    "#a78bfa",
};

const ALIGN_STYLE = {
  ALIGNED:     { color: "#34d399", bg: "rgba(52,211,153,0.12)",   border: "rgba(52,211,153,0.3)" },
  CONFLICTING: { color: "#f87171", bg: "rgba(248,113,113,0.12)",  border: "rgba(248,113,113,0.3)" },
  NEUTRAL:     { color: "#9ca3af", bg: "rgba(156,163,175,0.08)",  border: "rgba(156,163,175,0.18)" },
};

function computeAlignment(signal, isLong) {
  if (ENTRY_SIGNALS.has(signal)) return isLong ? "ALIGNED" : "CONFLICTING";
  if (EXIT_SIGNALS.has(signal))  return isLong ? "CONFLICTING" : "ALIGNED";
  return "NEUTRAL";
}

function heatColor(heat) {
  if (heat >= 80) return "#f87171";
  if (heat >= 60) return "#fbbf24";
  if (heat >= 40) return "#22d3ee";
  return "#6b7280";
}

// ---------------------------------------------------------------------------
// Glassmorphism Design Tokens
// ---------------------------------------------------------------------------

const GLASS = {
  bg: "rgba(255,255,255,0.03)",
  bgHover: "rgba(255,255,255,0.055)",
  border: "rgba(255,255,255,0.08)",
  borderBright: "rgba(255,255,255,0.14)",
  blur: "blur(24px)",
  shadow: "0 4px 32px rgba(0,0,0,0.35), 0 1px 0 rgba(255,255,255,0.04) inset",
  shadowSubtle: "0 2px 16px rgba(0,0,0,0.2)",
  glow: (color, intensity = 0.12) => `0 0 32px rgba(${color},${intensity}), 0 0 8px rgba(${color},${intensity * 0.6})`,
  displayFont: "'Outfit', 'Inter', sans-serif",
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const S = {
  panel: { padding: 0, maxWidth: 1200, margin: "0 auto" },
  section: {
    background: GLASS.bg,
    backdropFilter: GLASS.blur,
    WebkitBackdropFilter: GLASS.blur,
    border: `1px solid ${GLASS.border}`,
    borderRadius: 16, marginBottom: 20, overflow: "hidden",
    boxShadow: GLASS.shadow,
    transition: "all 0.25s ease",
  },
  sectionHeader: {
    padding: "16px 24px",
    borderBottom: `1px solid ${GLASS.border}`,
    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
    background: "rgba(255,255,255,0.015)",
  },
  title: {
    fontSize: 13, fontWeight: 700, fontFamily: GLASS.displayFont, color: T.text1,
    letterSpacing: "0.04em", textTransform: "uppercase",
  },
  btn: {
    padding: "7px 16px", borderRadius: 8,
    border: `1px solid ${GLASS.border}`,
    background: "rgba(255,255,255,0.04)",
    backdropFilter: "blur(12px)",
    color: T.text1, fontSize: 11, fontFamily: T.mono,
    fontWeight: 600, cursor: "pointer",
    transition: "all 0.2s ease",
    boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
  },
  btnDanger: {
    background: "rgba(248,113,113,0.1)",
    borderColor: "rgba(248,113,113,0.25)",
    color: "#f87171",
    boxShadow: "0 1px 8px rgba(248,113,113,0.1)",
  },
  label: { fontSize: 11, fontFamily: T.font, color: T.text3, fontWeight: 500 },
  value: { fontSize: 13, fontFamily: T.mono, color: T.text1, fontWeight: 600 },
  badge: (bg, color, border) => ({
    display: "inline-flex", alignItems: "center", padding: "4px 12px", borderRadius: 6,
    background: bg, color, border: `1px solid ${border}`,
    fontSize: 10, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
    backdropFilter: "blur(8px)",
    boxShadow: `0 1px 6px ${bg}`,
  }),
  pillBtn: (active) => ({
    padding: "6px 14px", borderRadius: 8, cursor: "pointer",
    border: active ? "1px solid rgba(34,211,238,0.45)" : `1px solid ${GLASS.border}`,
    background: active
      ? "linear-gradient(135deg, rgba(34,211,238,0.15), rgba(34,211,238,0.06))"
      : "rgba(255,255,255,0.03)",
    color: active ? "#22d3ee" : T.text3,
    fontSize: 10, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
    transition: "all 0.2s ease",
    backdropFilter: "blur(8px)",
    boxShadow: active ? "0 0 12px rgba(34,211,238,0.12)" : "none",
  }),
  empty: {
    padding: "32px 24px", textAlign: "center",
    color: T.text4, fontSize: 12, fontFamily: T.mono,
  },
};

const cellStyle = {
  padding: "12px 16px", fontSize: 12, fontFamily: T.mono, color: T.text2,
  borderBottom: `1px solid ${GLASS.border}`, whiteSpace: "nowrap",
};
const headerCell = {
  padding: "12px 16px", fontSize: 9, fontFamily: T.mono, fontWeight: 700,
  color: T.text3, letterSpacing: "0.12em", textTransform: "uppercase",
  borderBottom: `1px solid ${GLASS.borderBright}`, textAlign: "left",
  background: "rgba(255,255,255,0.01)",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatBox({ label, value, color, small }) {
  return (
    <div style={{
      textAlign: "center", minWidth: small ? 80 : 100,
      padding: small ? "8px 10px" : "10px 14px",
      borderRadius: 10,
      background: "rgba(255,255,255,0.02)",
      border: `1px solid rgba(255,255,255,0.04)`,
      transition: "all 0.2s ease",
    }}>
      <div style={{
        fontSize: small ? 15 : 20,
        fontFamily: GLASS.displayFont,
        fontWeight: 700,
        color: color || T.text1,
        lineHeight: 1.2,
        letterSpacing: "-0.01em",
      }}>
        {value}
      </div>
      <div style={{
        fontSize: 9, fontFamily: T.mono, color: T.text4,
        marginTop: 4, letterSpacing: "0.1em", fontWeight: 600, textTransform: "uppercase",
      }}>
        {label}
      </div>
    </div>
  );
}

// ─── Portfolio Chart ────────────────────────────────────────────────────────

const PERIODS = [
  { key: "1D", label: "1D", sdk: "perpDay" },
  { key: "1W", label: "1W", sdk: "perpWeek" },
  { key: "1M", label: "1M", sdk: "perpMonth" },
  { key: "ALL", label: "ALL", sdk: "perpAllTime" },
];

function PortfolioChart({ portfolio, period, onPeriodChange, mode, onModeChange }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !portfolio) return;
    const sdkPeriod = PERIODS.find(p => p.key === period)?.sdk || "perpAllTime";
    const data = portfolio[sdkPeriod];
    if (!data) return;

    const series = mode === "value" ? data.accountValueHistory : data.pnlHistory;
    if (!series || series.length === 0) return;

    // Deduplicate by time (keep last value)
    const seen = new Map();
    for (const pt of series) {
      seen.set(pt.time, pt.value);
    }
    const chartData = [...seen.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([time, value]) => ({ time, value }));

    if (chartData.length === 0) return;

    // Clean up previous chart
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch (_) { /* */ }
      chartRef.current = null;
    }

    const lastVal = chartData[chartData.length - 1].value;
    const isPositive = lastVal >= 0;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 280,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#98989f",
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.02)" },
        horzLines: { color: "rgba(255,255,255,0.025)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(34,211,238,0.15)", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#1a1a1e" },
        horzLine: { color: "rgba(34,211,238,0.15)", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#1a1a1e" },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.06)",
        timeVisible: true, secondsVisible: false,
        rightOffset: 3, minBarSpacing: 1,
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.06)",
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });
    chartRef.current = chart;

    const lineColor = mode === "value"
      ? "#22d3ee"
      : (isPositive ? "#34d399" : "#f87171");
    const topColor = mode === "value"
      ? "rgba(34,211,238,0.18)"
      : (isPositive ? "rgba(52,211,153,0.18)" : "rgba(248,113,113,0.18)");

    const areaSeries = chart.addSeries(AreaSeries, {
      topColor,
      bottomColor: "transparent",
      lineColor,
      lineWidth: 2,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderWidth: 1,
      crosshairMarkerBorderColor: lineColor,
      priceFormat: { type: "custom", formatter: (v) => `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}` },
    });
    areaSeries.setData(chartData);
    chart.timeScale().fitContent();

    // ResizeObserver
    const ro = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch (_) { /* */ }
        chartRef.current = null;
      }
    };
  }, [portfolio, period, mode]);

  const sdkPeriod = PERIODS.find(p => p.key === period)?.sdk || "perpAllTime";
  const vlm = portfolio?.[sdkPeriod]?.vlm;

  return (
    <div style={S.section}>
      <div style={S.sectionHeader}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={S.title}>Portfolio</span>
          {vlm > 0 && (
            <span style={{
              fontSize: 10, fontFamily: T.mono, color: T.text4,
              padding: "3px 8px", borderRadius: 6,
              background: "rgba(255,255,255,0.03)",
              border: `1px solid rgba(255,255,255,0.05)`,
            }}>
              Vol: {fmtVlm(vlm)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          {/* Mode toggle */}
          <button style={S.pillBtn(mode === "value")} onClick={() => onModeChange("value")}>VALUE</button>
          <button style={S.pillBtn(mode === "pnl")} onClick={() => onModeChange("pnl")}>PnL</button>
          <div style={{ width: 1, height: 16, background: GLASS.border, margin: "0 4px" }} />
          {/* Period toggle */}
          {PERIODS.map(p => (
            <button key={p.key} style={S.pillBtn(period === p.key)} onClick={() => onPeriodChange(p.key)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} style={{
        height: 280, width: "100%",
        background: "radial-gradient(ellipse at 50% 80%, rgba(34,211,238,0.03) 0%, transparent 70%)",
      }} />
    </div>
  );
}

// ─── Scanner Context Strip ───────────────────────────────────────────────────

function ScannerContext({ coin, scanMap4h, scanMap1d, isLong, posWarnings }) {
  const ctx4h = scanMap4h[coin];
  const ctx1d  = scanMap1d[coin];
  if (!ctx4h) return null;

  const alignment  = computeAlignment(ctx4h.signal, isLong);
  const alignStyle = ALIGN_STYLE[alignment];
  const sigColor   = SIGNAL_COLOR[ctx4h.signal] || T.text3;
  const regColor   = REGIME_COLOR[ctx4h.regime]  || T.text3;
  const hc         = heatColor(ctx4h.heat);

  return (
    <div style={{
      marginTop: 12,
      padding: "10px 14px",
      background: "rgba(255,255,255,0.02)",
      backdropFilter: "blur(12px)",
      borderRadius: 10,
      border: `1px solid ${GLASS.border}`,
      boxShadow: "0 2px 12px rgba(0,0,0,0.12)",
    }}>
      {/* Top row: badges */}
      <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
        <span style={{
          fontSize: 9, fontFamily: T.mono, color: T.text4,
          letterSpacing: "0.12em", fontWeight: 700,
        }}>
          SCANNER
        </span>

        {/* 4H Signal */}
        <span style={{
          fontSize: 9, fontFamily: T.mono, fontWeight: 700,
          padding: "3px 8px", borderRadius: 5,
          background: sigColor + "18", color: sigColor,
          letterSpacing: "0.04em",
          border: `1px solid ${sigColor}25`,
          boxShadow: `0 0 8px ${sigColor}10`,
        }}>
          {SIGNAL_COMPACT[ctx4h.signal] || ctx4h.signal} · 4H
        </span>

        {/* Regime */}
        <span style={{
          fontSize: 9, fontFamily: T.mono, fontWeight: 700,
          padding: "3px 8px", borderRadius: 5,
          background: regColor + "14", color: regColor,
          border: `1px solid ${regColor}20`,
        }}>
          {ctx4h.regime}
        </span>

        {/* Heat */}
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ fontSize: 9, fontFamily: T.mono, color: T.text4, letterSpacing: "0.06em" }}>HEAT</span>
          <div style={{
            width: 44, height: 5, borderRadius: 3,
            background: "rgba(255,255,255,0.06)",
            overflow: "hidden",
          }}>
            <div style={{
              width: `${ctx4h.heat}%`, height: "100%",
              borderRadius: 3, background: hc,
              boxShadow: `0 0 6px ${hc}50`,
              transition: "width 0.3s ease",
            }} />
          </div>
          <span style={{ fontSize: 9, fontFamily: T.mono, color: hc, fontWeight: 700 }}>
            {ctx4h.heat}
          </span>
        </div>

        {/* 1D signal if different */}
        {ctx1d && ctx1d.signal !== ctx4h.signal && (
          <span style={{
            fontSize: 9, fontFamily: T.mono, fontWeight: 600,
            padding: "3px 8px", borderRadius: 5,
            background: (SIGNAL_COLOR[ctx1d.signal] || T.text4) + "14",
            color: SIGNAL_COLOR[ctx1d.signal] || T.text4,
            border: `1px solid ${(SIGNAL_COLOR[ctx1d.signal] || T.text4)}20`,
          }}>
            {SIGNAL_COMPACT[ctx1d.signal] || ctx1d.signal} · 1D
          </span>
        )}

        {/* Alignment badge — pinned right */}
        <span style={{
          marginLeft: "auto",
          fontSize: 9, fontFamily: T.mono, fontWeight: 700,
          padding: "3px 10px", borderRadius: 5,
          background: alignStyle.bg, color: alignStyle.color,
          border: `1px solid ${alignStyle.border}`,
          letterSpacing: "0.06em", flexShrink: 0,
          boxShadow: `0 0 8px ${alignStyle.bg}`,
        }}>
          {alignment}
        </span>
      </div>

      {/* Warnings for this coin */}
      {posWarnings.length > 0 && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
          {posWarnings.map((w, i) => {
            const wc = w.severity === "critical" ? "#f87171" : w.severity === "high" ? "#fbbf24" : "#eab308";
            return (
              <div key={i} style={{
                display: "flex", alignItems: "flex-start", gap: 6,
                fontSize: 9, fontFamily: T.mono, color: wc,
                padding: "4px 8px", borderRadius: 5,
                background: wc + "08",
                border: `1px solid ${wc}12`,
              }}>
                <span style={{ flexShrink: 0, fontSize: 7, marginTop: 2 }}>&#9650;</span>
                <span style={{ lineHeight: 1.5 }}>{w.detail}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Portfolio Health Card ───────────────────────────────────────────────────

function PortfolioHealthCard({ positions, scanMap4h, warnings }) {
  if (positions.length === 0) return null;

  // Per-position health scoring
  const positionScores = positions.map(ap => {
    const p      = ap.position || ap;
    const coin   = p.coin;
    const szi    = parseNum(ap.position?.szi ?? ap.szi);
    const isLong = szi > 0;
    const ctx    = scanMap4h[coin];
    const entryPx = parseNum(p.entryPx);
    const liqPx  = p.liquidationPx ? parseNum(p.liquidationPx) : null;

    let health = 65; // base

    if (ctx) {
      const alignment = computeAlignment(ctx.signal, isLong);
      if (alignment === "ALIGNED")     health += 20;
      if (alignment === "CONFLICTING") health -= 30;

      if (ctx.heat >= 85)      health -= 20;
      else if (ctx.heat >= 70) health -= 10;

      if (ctx.is_climax)         health -= 15;
      if (ctx.floor_confirmed && !isLong) health -= 10;
    }

    if (liqPx && entryPx) {
      const currentPrice = ctx?.price || entryPx;
      const liqDist = Math.abs(currentPrice - liqPx) / currentPrice * 100;
      if (liqDist < 8)       health -= 30;
      else if (liqDist < 15) health -= 15;
      else if (liqDist < 25) health -= 5;
    }

    // Penalise for active critical/high warnings
    const coinWarnings = warnings.filter(w => w.symbol === coin || w.symbol === `${coin}/USDT`);
    coinWarnings.forEach(w => {
      if (w.severity === "critical") health -= 15;
      else if (w.severity === "high") health -= 8;
    });

    return { coin, isLong, health: Math.max(0, Math.min(100, health)), ctx };
  });

  const avgHealth = positionScores.reduce((s, v) => s + v.health, 0) / positionScores.length;

  // Categorise
  const aligned     = positionScores.filter(ps => ps.ctx && computeAlignment(ps.ctx.signal, ps.isLong) === "ALIGNED").length;
  const conflicting = positionScores.filter(ps => ps.ctx && computeAlignment(ps.ctx.signal, ps.isLong) === "CONFLICTING").length;
  const neutral     = positionScores.length - aligned - conflicting;

  const hc    = avgHealth >= 68 ? "#34d399" : avgHealth >= 45 ? "#fbbf24" : "#f87171";
  const label = avgHealth >= 68 ? "HEALTHY"  : avgHealth >= 45 ? "MODERATE" : "AT RISK";

  // Suggested actions from scanner signals
  const actions = positionScores
    .filter(ps => ps.ctx)
    .map(ps => {
      const sig = ps.ctx.signal;
      const side = ps.isLong ? "LONG" : "SHORT";
      if (sig === "TRIM" || sig === "TRIM_HARD") return { coin: ps.coin, text: `TRIM ${ps.coin} ${side} — scanner says ${sig}`, color: "#fbbf24" };
      if (sig === "RISK_OFF") return { coin: ps.coin, text: `CLOSE ${ps.coin} — RISK OFF signal`, color: "#f87171" };
      if ((sig === "STRONG_LONG" || sig === "LIGHT_LONG") && !ps.isLong) return { coin: ps.coin, text: `COVER ${ps.coin} SHORT — bullish signal`, color: "#f97316" };
      if (sig === "STRONG_LONG" && ps.isLong && ps.ctx.heat < 70) return { coin: ps.coin, text: `HOLD / ADD ${ps.coin} — strong regime`, color: "#34d399" };
      return null;
    })
    .filter(Boolean);

  // SVG arc for the circular gauge
  const gaugeRadius = 38;
  const gaugeCircumference = 2 * Math.PI * gaugeRadius;
  const gaugeArc = (avgHealth / 100) * gaugeCircumference * 0.75; // 270° arc
  const gaugeRGB = hc === "#34d399" ? "52,211,153" : hc === "#fbbf24" ? "251,191,36" : "248,113,113";

  return (
    <div style={{
      ...S.section,
      marginBottom: 20,
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Radial glow background tied to health color */}
      <div style={{
        position: "absolute", top: -40, left: -20,
        width: 200, height: 200,
        borderRadius: "50%",
        background: `radial-gradient(circle, rgba(${gaugeRGB},0.08) 0%, transparent 70%)`,
        pointerEvents: "none",
        filter: "blur(20px)",
      }} />

      {/* Header */}
      <div style={{
        padding: "14px 24px",
        borderBottom: `1px solid ${GLASS.border}`,
        display: "flex", alignItems: "center", gap: 12,
        background: "rgba(255,255,255,0.015)",
        position: "relative",
      }}>
        <span style={S.title}>Portfolio Health</span>
        <span style={{
          fontSize: 10, fontFamily: GLASS.displayFont, fontWeight: 700,
          padding: "3px 10px", borderRadius: 6,
          background: `rgba(${gaugeRGB},0.12)`, color: hc,
          border: `1px solid rgba(${gaugeRGB},0.25)`,
          letterSpacing: "0.04em",
          boxShadow: `0 0 10px rgba(${gaugeRGB},0.1)`,
        }}>
          {label}
        </span>
      </div>

      {/* Score + breakdowns */}
      <div style={{
        display: "flex", alignItems: "center", gap: 28,
        padding: "20px 24px", flexWrap: "wrap",
        borderBottom: actions.length > 0 ? `1px solid ${GLASS.border}` : "none",
        position: "relative",
      }}>
        {/* Circular gauge */}
        <div style={{ position: "relative", width: 90, height: 90, flexShrink: 0 }}>
          <svg width="90" height="90" viewBox="0 0 90 90" style={{ transform: "rotate(-225deg)" }}>
            {/* Background arc */}
            <circle
              cx="45" cy="45" r={gaugeRadius}
              fill="none"
              stroke="rgba(255,255,255,0.06)"
              strokeWidth="6"
              strokeDasharray={`${gaugeCircumference * 0.75} ${gaugeCircumference * 0.25}`}
              strokeLinecap="round"
            />
            {/* Health arc */}
            <circle
              cx="45" cy="45" r={gaugeRadius}
              fill="none"
              stroke={hc}
              strokeWidth="6"
              strokeDasharray={`${gaugeArc} ${gaugeCircumference - gaugeArc}`}
              strokeLinecap="round"
              style={{ transition: "stroke-dasharray 0.6s ease", filter: `drop-shadow(0 0 6px rgba(${gaugeRGB},0.4))` }}
            />
          </svg>
          {/* Center score */}
          <div style={{
            position: "absolute", top: "50%", left: "50%",
            transform: "translate(-50%, -50%)",
            textAlign: "center",
          }}>
            <div style={{
              fontSize: 26, fontFamily: GLASS.displayFont, fontWeight: 800,
              color: hc, lineHeight: 1, letterSpacing: "-0.02em",
            }}>
              {Math.round(avgHealth)}
            </div>
            <div style={{
              fontSize: 8, fontFamily: T.mono, color: T.text4,
              letterSpacing: "0.12em", marginTop: 2,
            }}>
              /100
            </div>
          </div>
        </div>

        {/* Divider */}
        <div style={{ width: 1, height: 56, background: GLASS.border, flexShrink: 0 }} />

        {/* Alignment stats */}
        <div style={{ display: "flex", gap: 16 }}>
          {aligned > 0 && (
            <div style={{
              textAlign: "center", padding: "8px 12px", borderRadius: 10,
              background: "rgba(52,211,153,0.05)",
              border: "1px solid rgba(52,211,153,0.1)",
            }}>
              <div style={{ fontSize: 22, fontFamily: GLASS.displayFont, fontWeight: 700, color: "#34d399" }}>{aligned}</div>
              <div style={{ fontSize: 9, fontFamily: T.mono, color: "#34d399", marginTop: 3, letterSpacing: "0.08em", opacity: 0.8 }}>ALIGNED</div>
            </div>
          )}
          {neutral > 0 && (
            <div style={{
              textAlign: "center", padding: "8px 12px", borderRadius: 10,
              background: "rgba(255,255,255,0.02)",
              border: `1px solid rgba(255,255,255,0.05)`,
            }}>
              <div style={{ fontSize: 22, fontFamily: GLASS.displayFont, fontWeight: 700, color: T.text3 }}>{neutral}</div>
              <div style={{ fontSize: 9, fontFamily: T.mono, color: T.text4, marginTop: 3, letterSpacing: "0.08em" }}>NEUTRAL</div>
            </div>
          )}
          {conflicting > 0 && (
            <div style={{
              textAlign: "center", padding: "8px 12px", borderRadius: 10,
              background: "rgba(248,113,113,0.05)",
              border: "1px solid rgba(248,113,113,0.1)",
            }}>
              <div style={{ fontSize: 22, fontFamily: GLASS.displayFont, fontWeight: 700, color: "#f87171" }}>{conflicting}</div>
              <div style={{ fontSize: 9, fontFamily: T.mono, color: "#f87171", marginTop: 3, letterSpacing: "0.08em", opacity: 0.8 }}>CONFLICT</div>
            </div>
          )}
        </div>

        {/* Per-position mini gauges */}
        {positionScores.length > 1 && (
          <>
            <div style={{ width: 1, height: 56, background: GLASS.border, flexShrink: 0 }} />
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              {positionScores.map(ps => {
                const phc = ps.health >= 68 ? "#34d399" : ps.health >= 45 ? "#fbbf24" : "#f87171";
                return (
                  <div key={ps.coin} style={{
                    textAlign: "center", padding: "6px 8px", borderRadius: 8,
                    background: "rgba(255,255,255,0.02)",
                    border: `1px solid rgba(255,255,255,0.04)`,
                    minWidth: 48,
                  }}>
                    <div style={{ fontSize: 9, fontFamily: T.mono, color: T.text3, marginBottom: 4, fontWeight: 600 }}>{ps.coin}</div>
                    <div style={{
                      width: 40, height: 4, borderRadius: 2,
                      background: "rgba(255,255,255,0.06)", margin: "0 auto",
                      overflow: "hidden",
                    }}>
                      <div style={{
                        width: `${ps.health}%`, height: "100%",
                        borderRadius: 2, background: phc,
                        boxShadow: `0 0 6px ${phc}40`,
                        transition: "width 0.4s ease",
                      }} />
                    </div>
                    <div style={{
                      fontSize: 10, fontFamily: GLASS.displayFont, color: phc,
                      fontWeight: 700, marginTop: 3,
                    }}>
                      {Math.round(ps.health)}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* Suggested actions */}
      {actions.length > 0 && (
        <div style={{ padding: "14px 24px", display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{
            fontSize: 9, fontFamily: T.mono, color: T.text4,
            letterSpacing: "0.1em", fontWeight: 700, marginBottom: 2,
          }}>
            SUGGESTED ACTIONS
          </div>
          {actions.map((a, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 10,
              fontSize: 11, fontFamily: T.mono, color: a.color,
              padding: "6px 12px", borderRadius: 8,
              background: a.color + "08",
              border: `1px solid ${a.color}15`,
            }}>
              <span style={{ fontSize: 7, opacity: 0.8 }}>&#9654;</span>
              <span style={{ lineHeight: 1.4 }}>{a.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Position Card ──────────────────────────────────────────────────────────

function PositionCard({ pos, onClose, closing, scanMap4h, scanMap1d, posWarnings }) {
  const szi = parseNum(pos.position?.szi ?? pos.szi);
  const isLong = szi > 0;
  const side = isLong ? "LONG" : "SHORT";
  const sideColor = isLong ? "#34d399" : "#f87171";
  const sideBg = isLong ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)";
  const sideBorder = isLong ? "rgba(52,211,153,0.25)" : "rgba(248,113,113,0.25)";

  const p = pos.position || pos;
  const coin = p.coin;
  const leverage = p.leverage?.value ?? "?";
  const leverageType = p.leverage?.type === "isolated" ? "ISO" : "CROSS";
  const entryPx = parseNum(p.entryPx);
  const posValue = parseNum(p.positionValue);
  const unrealizedPnl = parseNum(p.unrealizedPnl);
  const roe = parseNum(p.returnOnEquity) * 100;
  const liqPx = p.liquidationPx ? parseNum(p.liquidationPx) : null;
  const marginUsed = parseNum(p.marginUsed);
  const fundingSinceOpen = parseNum(p.cumFunding?.sinceOpen);

  // Liquidation proximity
  const ctx4h = scanMap4h[coin];
  const liqDistPct = liqPx && ctx4h?.price
    ? Math.abs(ctx4h.price - liqPx) / ctx4h.price * 100
    : null;
  const liqDanger = liqDistPct !== null && liqDistPct < 15;

  // Warnings for this coin
  const coinWarnings = (posWarnings || []).filter(
    w => w.symbol === coin || w.symbol === `${coin}/USDT`
  );

  const pnlRGB = unrealizedPnl >= 0 ? "52,211,153" : "248,113,113";

  return (
    <div style={{
      padding: "18px 24px",
      borderBottom: `1px solid ${GLASS.border}`,
      position: "relative",
      transition: "background 0.2s ease",
    }}>
      {/* Subtle PnL glow */}
      <div style={{
        position: "absolute", top: 0, right: 0, width: 160, height: "100%",
        background: `linear-gradient(270deg, rgba(${pnlRGB},0.03) 0%, transparent 100%)`,
        pointerEvents: "none",
      }} />

      {/* Row 1: Coin + badges + PnL */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap", position: "relative" }}>
        <span style={{
          fontSize: 17, fontFamily: GLASS.displayFont, fontWeight: 700,
          color: T.text1, letterSpacing: "-0.01em",
        }}>
          {coin}
        </span>
        <span style={S.badge(sideBg, sideColor, sideBorder)}>{side}</span>
        <span style={S.badge("rgba(139,92,246,0.1)", "#a78bfa", "rgba(139,92,246,0.2)")}>
          {leverage}x {leverageType}
        </span>
        {liqDanger && (
          <span style={{
            ...S.badge("rgba(239,68,68,0.12)", "#f87171", "rgba(239,68,68,0.3)"),
            animation: "none",
            boxShadow: "0 0 10px rgba(239,68,68,0.15)",
          }}>
            LIQ {liqDistPct.toFixed(1)}%
          </span>
        )}
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{
            fontSize: 16, fontFamily: GLASS.displayFont, fontWeight: 700,
            color: pnlColor(unrealizedPnl), letterSpacing: "-0.01em",
          }}>
            {unrealizedPnl >= 0 ? "+" : ""}{fmtUsd(unrealizedPnl)}
          </div>
          <div style={{ fontSize: 10, fontFamily: T.mono, color: pnlColor(roe), opacity: 0.85 }}>
            ROE {roe >= 0 ? "+" : ""}{roe.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Row 2: Details — grid-like with subtle containers */}
      <div style={{
        display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center",
      }}>
        {[
          { label: "Entry", val: fmtPrice(entryPx) },
          { label: "Size", val: Math.abs(szi).toFixed(4) },
          { label: "Value", val: fmtUsd(posValue) },
          { label: "Margin", val: fmtUsd(marginUsed) },
          ...(liqPx ? [{ label: "Liq", val: fmtPrice(liqPx), color: liqDanger ? "#f87171" : undefined }] : []),
          ...(fundingSinceOpen !== 0 ? [{ label: "Funding", val: `${fundingSinceOpen >= 0 ? "-" : "+"}${fmtUsd(Math.abs(fundingSinceOpen))}`, color: pnlColor(-fundingSinceOpen) }] : []),
        ].map((d, i) => (
          <div key={i} style={{
            padding: "5px 10px", borderRadius: 7,
            background: "rgba(255,255,255,0.02)",
            border: `1px solid rgba(255,255,255,0.04)`,
          }}>
            <span style={{ ...S.label, fontSize: 9, letterSpacing: "0.06em" }}>{d.label} </span>
            <span style={{ ...S.value, fontSize: 12, color: d.color || T.text1 }}>{d.val}</span>
          </div>
        ))}
        <button
          onClick={() => onClose(coin, Math.abs(szi), isLong)}
          disabled={closing}
          style={{
            ...S.btn, ...S.btnDanger, marginLeft: "auto",
            opacity: closing ? 0.5 : 1, cursor: closing ? "not-allowed" : "pointer",
            borderRadius: 8, padding: "7px 16px",
          }}
        >
          {closing ? "Closing..." : "Close"}
        </button>
      </div>

      {/* Scanner context strip */}
      <ScannerContext
        coin={coin}
        scanMap4h={scanMap4h}
        scanMap1d={scanMap1d}
        isLong={isLong}
        posWarnings={coinWarnings}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile section tabs
// ---------------------------------------------------------------------------

const SECTION_TABS = [
  { key: "positions", label: "POSITIONS" },
  { key: "orders",   label: "ORDERS" },
  { key: "fills",    label: "FILLS" },
  { key: "funding",  label: "FUNDING" },
  { key: "fees",     label: "FEES" },
];

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function TradingPanel({ api }) {
  const { address, isConnected, walletClient, connect, error: walletError } = useWallet();

  // Core data
  const [chState, setChState]     = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [openOrders, setOpenOrders] = useState([]);
  const [fills, setFills]         = useState([]);
  const [funding, setFunding]     = useState([]);
  const [fees, setFees]           = useState(null);
  const [history, setHistory]     = useState({ trades: [], stats: {} });

  // Scanner context
  const [scanMap4h, setScanMap4h] = useState({});
  const [scanMap1d, setScanMap1d] = useState({});
  const [posWarnings, setPosWarnings] = useState([]);

  // UI state
  const [chartPeriod, setChartPeriod] = useState("ALL");
  const [chartMode, setChartMode]     = useState("value");
  const [activeSection, setActiveSection] = useState("positions");
  const [closing, setClosing]     = useState(null);
  const [cancelling, setCancelling] = useState(null);

  // --- Data fetching ---

  const fetchFast = useCallback(async () => {
    if (!isConnected || !address) return;
    try {
      const [state, orders] = await Promise.all([
        hlClient.getClearinghouseState(address).catch(() => null),
        hlClient.getOpenOrders(address).catch(() => null),
      ]);
      if (state) setChState(state);
      if (orders) setOpenOrders(orders);
    } catch (e) { console.error("Portfolio fast fetch:", e); }
  }, [address, isConnected]);

  const fetchMedium = useCallback(async () => {
    if (!isConnected || !address) return;
    try {
      const f = await hlClient.getUserFills(address).catch(() => []);
      setFills(f || []);
    } catch (e) { console.error("Portfolio medium fetch:", e); }
  }, [address, isConnected]);

  const fetchSlow = useCallback(async () => {
    if (!isConnected || !address) return;
    try {
      const [p, fund, fe, histResp] = await Promise.all([
        hlClient.getPortfolio(address).catch(() => null),
        hlClient.getUserFunding(address).catch(() => []),
        hlClient.getUserFees(address).catch(() => null),
        fetch(`${api}/api/trade/history`).then(r => r.ok ? r.json() : { trades: [], stats: {} }).catch(() => ({ trades: [], stats: {} })),
      ]);
      if (p) setPortfolio(p);
      setFunding(fund || []);
      if (fe) setFees(fe);
      setHistory(histResp);
    } catch (e) { console.error("Portfolio slow fetch:", e); }
  }, [address, isConnected, api]);

  // Fetch scanner context + position warnings
  const fetchScannerContext = useCallback(async () => {
    try {
      const [res4h, res1d] = await Promise.all([
        fetch(`${api}/api/scan?timeframe=4h`).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(`${api}/api/scan?timeframe=1d`).then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      if (res4h?.results) {
        const map = {};
        res4h.results.forEach(r => {
          const coin = r.symbol.replace("/USDT", "").replace("/USD", "");
          map[coin] = r;
        });
        setScanMap4h(map);
      }
      if (res1d?.results) {
        const map = {};
        res1d.results.forEach(r => {
          const coin = r.symbol.replace("/USDT", "").replace("/USD", "");
          map[coin] = r;
        });
        setScanMap1d(map);
      }
    } catch (e) { console.error("Scanner fetch:", e); }
  }, [api]);

  const fetchWarnings = useCallback(async () => {
    if (!address) { setPosWarnings([]); return; }
    try {
      const res = await fetch(`${api}/api/notifications/position-warnings?address=${address}`);
      if (!res.ok) return;
      const data = await res.json();
      setPosWarnings(data.warnings || []);
    } catch (_) {}
  }, [address, api]);

  useEffect(() => {
    if (!isConnected || !address) return;
    fetchFast();
    fetchMedium();
    fetchSlow();
    fetchScannerContext();
    fetchWarnings();

    const fastInterval   = setInterval(fetchFast, 15_000);
    const medInterval    = setInterval(fetchMedium, 30_000);
    const scanInterval   = setInterval(fetchScannerContext, 60_000);
    const warnInterval   = setInterval(fetchWarnings, 60_000);

    return () => {
      clearInterval(fastInterval);
      clearInterval(medInterval);
      clearInterval(scanInterval);
      clearInterval(warnInterval);
    };
  }, [fetchFast, fetchMedium, fetchSlow, fetchScannerContext, fetchWarnings, isConnected, address]);

  // --- Actions ---

  const closePosition = async (coin, size, isLong) => {
    if (!walletClient) return;
    if (!window.confirm(`Close ${coin} position?`)) return;
    setClosing(coin);
    try {
      const result = await hlClient.closePosition(walletClient, { coin, size, isLong, slippage: 0.02 });
      await fetch(`${api}/api/trade/log-close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: `${coin}/USDT`,
          exit_price: result.avgPx,
          close_order_id: String(result.oid || ""),
        }),
      });
      await fetchFast();
    } catch (e) {
      console.error("Close error:", e);
      alert(e.message || "Failed to close position");
    }
    setClosing(null);
  };

  const cancelOrd = async (coin, oid) => {
    if (!walletClient) return;
    setCancelling(oid);
    try {
      await hlClient.cancelOrder(walletClient, { coin, oid });
      await fetchFast();
    } catch (e) {
      console.error("Cancel error:", e);
      alert(e.message || "Failed to cancel order");
    }
    setCancelling(null);
  };

  // --- Derived data ---

  const marginSummary = chState?.crossMarginSummary || chState?.marginSummary;
  const accountValue  = parseNum(marginSummary?.accountValue);
  const marginUsedVal = parseNum(marginSummary?.totalMarginUsed);
  const withdrawable  = parseNum(chState?.withdrawable);
  const positions     = (chState?.assetPositions || []).filter(ap => parseNum(ap.position?.szi) !== 0);
  const totalUnrealizedPnl = positions.reduce((sum, ap) => sum + parseNum(ap.position?.unrealizedPnl), 0);

  // All-time total PnL from portfolio
  const allTimePnl = portfolio?.perpAllTime?.pnlHistory;
  const totalPnl   = allTimePnl?.length > 0 ? allTimePnl[allTimePnl.length - 1].value : null;

  // Fee rates
  const takerRate = fees?.userCrossRate;
  const makerRate = fees?.userAddRate;
  const dailyVlm  = fees?.dailyUserVlm || [];
  const volume30d = dailyVlm.slice(-30).reduce((s, d) => s + parseNum(d.userCross) + parseNum(d.userAdd), 0);

  // Funding summary
  const totalFunding = funding.reduce((s, f) => s + parseNum(f.delta?.usdc), 0);

  return (
    <div style={{ ...S.panel, padding: "0 4px" }}>

      {/* ─── NOT CONNECTED ─── */}
      {!isConnected && (
        <div style={{
          ...S.section, padding: "48px 24px", textAlign: "center",
          position: "relative", overflow: "hidden",
        }}>
          {/* Decorative gradient */}
          <div style={{
            position: "absolute", top: "-50%", left: "50%", transform: "translateX(-50%)",
            width: 300, height: 300, borderRadius: "50%",
            background: "radial-gradient(circle, rgba(139,92,246,0.06) 0%, transparent 70%)",
            pointerEvents: "none",
          }} />
          <div style={{
            fontSize: 14, fontFamily: GLASS.displayFont, color: T.text3,
            marginBottom: 18, fontWeight: 500, position: "relative",
          }}>
            Connect your wallet to view portfolio
          </div>
          <button
            onClick={connect}
            style={{
              padding: "12px 36px", borderRadius: 12,
              border: "1px solid rgba(139,92,246,0.3)",
              background: "linear-gradient(135deg, rgba(139,92,246,0.12), rgba(139,92,246,0.04))",
              backdropFilter: "blur(12px)",
              color: "#a78bfa",
              fontSize: 13, fontFamily: GLASS.displayFont, fontWeight: 700,
              cursor: "pointer", letterSpacing: "0.04em",
              boxShadow: "0 0 24px rgba(139,92,246,0.1), 0 2px 8px rgba(0,0,0,0.2)",
              transition: "all 0.25s ease",
              position: "relative",
            }}
          >
            Connect Wallet
          </button>
          {walletError && (
            <div style={{
              marginTop: 10, fontSize: 10, color: "#f87171",
              fontFamily: T.mono, position: "relative",
            }}>
              {walletError}
            </div>
          )}
        </div>
      )}

      {/* ─── ACCOUNT SUMMARY BAR ─── */}
      {isConnected && (
        <div style={{ ...S.section, position: "relative", overflow: "hidden" }}>
          {/* Subtle accent glow */}
          <div style={{
            position: "absolute", top: -20, right: -20, width: 180, height: 180,
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(34,211,238,0.04) 0%, transparent 70%)",
            pointerEvents: "none",
          }} />
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={S.title}>Hyperliquid Portfolio</span>
              <span style={{
                ...S.badge("rgba(52,211,153,0.1)", "#34d399", "rgba(52,211,153,0.25)"),
                boxShadow: "0 0 10px rgba(52,211,153,0.1)",
              }}>
                LIVE
              </span>
            </div>
            <span style={{
              fontSize: 10, fontFamily: T.mono, color: T.text4,
              padding: "3px 8px", borderRadius: 5,
              background: "rgba(255,255,255,0.03)",
              border: `1px solid rgba(255,255,255,0.05)`,
            }}>
              {address?.slice(0, 6)}...{address?.slice(-4)}
            </span>
          </div>
          <div style={{
            display: "flex", justifyContent: "space-around",
            padding: "18px 20px", gap: 12, flexWrap: "wrap",
            position: "relative",
          }}>
            <StatBox label="ACCOUNT VALUE"  value={fmtUsd(accountValue)} />
            <StatBox label="UNREALIZED PnL" value={`${totalUnrealizedPnl >= 0 ? "+" : ""}${fmtUsd(totalUnrealizedPnl)}`} color={pnlColor(totalUnrealizedPnl)} />
            <StatBox label="TOTAL PnL"      value={totalPnl != null ? `${totalPnl >= 0 ? "+" : ""}${fmtUsd(totalPnl)}` : "\u2014"} color={pnlColor(totalPnl)} />
            <StatBox label="AVAILABLE"      value={fmtUsd(withdrawable)} />
            <StatBox label="MARGIN USED"    value={fmtUsd(marginUsedVal)} color={marginUsedVal > 0 ? "#fbbf24" : T.text3} />
          </div>
        </div>
      )}

      {/* ─── PORTFOLIO CHART ─── */}
      {isConnected && portfolio && (
        <PortfolioChart
          portfolio={portfolio}
          period={chartPeriod}
          onPeriodChange={setChartPeriod}
          mode={chartMode}
          onModeChange={setChartMode}
        />
      )}

      {/* ─── SECTION TAB BAR ─── */}
      {isConnected && (
        <div style={{
          display: "flex", gap: 6, marginBottom: 20, flexWrap: "wrap",
          padding: "12px 16px",
          background: "rgba(255,255,255,0.015)",
          backdropFilter: "blur(16px)",
          borderRadius: 12,
          border: `1px solid ${GLASS.border}`,
          boxShadow: GLASS.shadowSubtle,
        }}>
          {SECTION_TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveSection(tab.key)}
              style={{
                ...S.pillBtn(activeSection === tab.key),
                padding: "8px 16px", fontSize: 11,
                fontFamily: GLASS.displayFont,
              }}
            >
              {tab.label}
              {tab.key === "positions" && positions.length > 0 && ` (${positions.length})`}
              {tab.key === "orders"    && openOrders.length > 0 && ` (${openOrders.length})`}
            </button>
          ))}
        </div>
      )}

      {/* ─── OPEN POSITIONS ─── */}
      {isConnected && activeSection === "positions" && (
        <>
          {/* Portfolio health card — only when there are positions + scanner data */}
          {positions.length > 0 && Object.keys(scanMap4h).length > 0 && (
            <PortfolioHealthCard
              positions={positions}
              scanMap4h={scanMap4h}
              warnings={posWarnings}
            />
          )}

          <div style={S.section}>
            <div style={S.sectionHeader}>
              <span style={S.title}>
                Open Positions {positions.length > 0 && `(${positions.length})`}
              </span>
            </div>
            {positions.length === 0 ? (
              <div style={S.empty}>No open positions</div>
            ) : (
              positions.map(ap => (
                <PositionCard
                  key={ap.position?.coin || ap.coin}
                  pos={ap}
                  onClose={closePosition}
                  closing={closing === (ap.position?.coin || ap.coin)}
                  scanMap4h={scanMap4h}
                  scanMap1d={scanMap1d}
                  posWarnings={posWarnings}
                />
              ))
            )}
          </div>
        </>
      )}

      {/* ─── OPEN ORDERS ─── */}
      {isConnected && activeSection === "orders" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Open Orders {openOrders.length > 0 && `(${openOrders.length})`}
            </span>
          </div>
          {openOrders.length === 0 ? (
            <div style={S.empty}>No open orders</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Coin</th>
                    <th style={headerCell}>Type</th>
                    <th style={headerCell}>Side</th>
                    <th style={headerCell}>Price</th>
                    <th style={headerCell}>Trigger</th>
                    <th style={headerCell}>Size</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {openOrders.map((o, i) => {
                    const isBuy = o.side === "B";
                    const typeLabel = o.orderType || "Limit";
                    const typeBg = o.isTrigger ? "rgba(251,191,36,0.12)" : T.overlay04;
                    const typeColor = o.isTrigger ? "#fbbf24" : T.text2;
                    const typeBorder = o.isTrigger ? "rgba(251,191,36,0.3)" : T.overlay12;
                    return (
                      <tr key={o.oid || i}>
                        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{o.coin}</td>
                        <td style={cellStyle}>
                          <span style={S.badge(typeBg, typeColor, typeBorder)}>{typeLabel}</span>
                          {o.isPositionTpsl && (
                            <span style={{ ...S.badge("rgba(139,92,246,0.12)", "#8b5cf6", "rgba(139,92,246,0.3)"), marginLeft: 4 }}>TP/SL</span>
                          )}
                        </td>
                        <td style={cellStyle}>
                          <span style={{ color: isBuy ? "#34d399" : "#f87171", fontWeight: 600 }}>
                            {isBuy ? "BUY" : "SELL"}
                          </span>
                        </td>
                        <td style={cellStyle}>{fmtPrice(o.limitPx)}</td>
                        <td style={cellStyle}>{o.isTrigger ? fmtPrice(o.triggerPx) : "\u2014"}</td>
                        <td style={cellStyle}>{o.sz}</td>
                        <td style={{ ...cellStyle, textAlign: "right" }}>
                          <button
                            onClick={() => cancelOrd(o.coin, o.oid)}
                            disabled={cancelling === o.oid}
                            style={{
                              ...S.btn, ...S.btnDanger, padding: "4px 10px", fontSize: 10,
                              opacity: cancelling === o.oid ? 0.5 : 1,
                            }}
                          >
                            {cancelling === o.oid ? "..." : "Cancel"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ─── TRADE FILLS ─── */}
      {isConnected && activeSection === "fills" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Recent Fills {fills.length > 0 && `(${fills.length})`}
            </span>
          </div>
          {fills.length === 0 ? (
            <div style={S.empty}>No trade fills</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Time</th>
                    <th style={headerCell}>Coin</th>
                    <th style={headerCell}>Side</th>
                    <th style={headerCell}>Size</th>
                    <th style={headerCell}>Price</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Closed PnL</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Fee</th>
                  </tr>
                </thead>
                <tbody>
                  {fills.slice(0, 50).map((f, i) => {
                    const isBuy = f.side === "B";
                    const closedPnl = parseNum(f.closedPnl);
                    const fee = parseNum(f.fee);
                    return (
                      <tr key={f.tid || f.oid || i} style={{
                        background: closedPnl > 0 ? "rgba(52,211,153,0.03)" : closedPnl < 0 ? "rgba(248,113,113,0.03)" : "transparent",
                      }}>
                        <td style={cellStyle}>{timeAgo(f.time)}</td>
                        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{f.coin}</td>
                        <td style={cellStyle}>
                          <span style={{ color: isBuy ? "#34d399" : "#f87171", fontWeight: 600 }}>
                            {isBuy ? "BUY" : "SELL"}
                          </span>
                        </td>
                        <td style={cellStyle}>{f.sz}</td>
                        <td style={cellStyle}>{fmtPrice(f.px)}</td>
                        <td style={{ ...cellStyle, textAlign: "right", fontWeight: closedPnl !== 0 ? 700 : 400, color: pnlColor(closedPnl) }}>
                          {closedPnl !== 0 ? `${closedPnl >= 0 ? "+" : ""}${fmtUsd(closedPnl)}` : "\u2014"}
                        </td>
                        <td style={{ ...cellStyle, textAlign: "right", color: T.text3 }}>
                          {fee !== 0 ? `$${Math.abs(fee).toFixed(4)}` : "\u2014"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ─── FUNDING HISTORY ─── */}
      {isConnected && activeSection === "funding" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={S.title}>Funding History</span>
              {funding.length > 0 && (
                <span style={{ fontSize: 11, fontFamily: T.mono, color: pnlColor(-totalFunding) }}>
                  Total: {totalFunding >= 0 ? "-" : "+"}{fmtUsd(Math.abs(totalFunding))}
                </span>
              )}
            </div>
          </div>
          {funding.length === 0 ? (
            <div style={S.empty}>No funding payments</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Time</th>
                    <th style={headerCell}>Coin</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Amount</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {funding.slice(0, 50).map((f, i) => {
                    const amt  = parseNum(f.delta?.usdc);
                    const rate = parseNum(f.delta?.fundingRate);
                    return (
                      <tr key={f.hash || i}>
                        <td style={cellStyle}>{timeAgo(f.time)}</td>
                        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{f.delta?.coin}</td>
                        <td style={{ ...cellStyle, textAlign: "right", fontWeight: 600, color: pnlColor(amt) }}>
                          {amt >= 0 ? "+" : ""}{fmtUsd(amt)}
                        </td>
                        <td style={{ ...cellStyle, textAlign: "right", color: T.text3 }}>
                          {(rate * 100).toFixed(4)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ─── FEE TIER INFO ─── */}
      {isConnected && activeSection === "fees" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>Fee Tier</span>
          </div>
          <div style={{
            display: "flex", justifyContent: "space-around",
            padding: "18px 20px", gap: 12, flexWrap: "wrap",
          }}>
            <StatBox label="TAKER RATE" value={fmtBps(takerRate)} small />
            <StatBox label="MAKER RATE" value={fmtBps(makerRate)} small />
            <StatBox label="30D VOLUME" value={fmtVlm(volume30d)} small />
            {fees?.activeReferralDiscount && parseNum(fees.activeReferralDiscount) > 0 && (
              <StatBox label="REFERRAL DISC." value={`${(parseNum(fees.activeReferralDiscount) * 100).toFixed(1)}%`} color="#8b5cf6" small />
            )}
          </div>

          {/* Fee tiers */}
          {fees?.feeSchedule?.tiers?.vip && (
            <div style={{ padding: "0 20px 16px", overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Tier</th>
                    <th style={headerCell}>Volume Req</th>
                    <th style={headerCell}>Taker</th>
                    <th style={headerCell}>Maker</th>
                  </tr>
                </thead>
                <tbody>
                  {fees.feeSchedule.tiers.vip.map((tier, i) => {
                    const cutoff = parseNum(tier.ntlCutoff);
                    const isCurrentTier = volume30d >= cutoff && (
                      !fees.feeSchedule.tiers.vip[i + 1] || volume30d < parseNum(fees.feeSchedule.tiers.vip[i + 1].ntlCutoff)
                    );
                    return (
                      <tr key={i} style={{
                        background: isCurrentTier ? "rgba(34,211,238,0.06)" : "transparent",
                      }}>
                        <td style={{ ...cellStyle, fontWeight: isCurrentTier ? 700 : 400, color: isCurrentTier ? "#22d3ee" : T.text2 }}>
                          VIP {i}{isCurrentTier ? " \u2190" : ""}
                        </td>
                        <td style={cellStyle}>{fmtVlm(cutoff)}</td>
                        <td style={cellStyle}>{fmtBps(tier.cross)}</td>
                        <td style={cellStyle}>{fmtBps(tier.add)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
