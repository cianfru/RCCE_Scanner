import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { T, heatColor, phaseColor, exhaustMeta, fmt, zBar, getBaseSymbol, getTVSymbol } from "../theme.js";
import { RegimeBadge, SignalDot } from "../components/badges.jsx";
import useViewport from "../hooks/useViewport.js";
import BMSBChart from "../components/BMSBChart.jsx";
import ConditionsScorecard from "../components/ConditionsScorecard.jsx";
import ConfluencePanel from "../components/ConfluencePanel.jsx";
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
        <span style={{ fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 700, textTransform: "uppercase" }}>
          Engine Metrics
        </span>
      </div>
      {rows.map(([label, value, valColor], i) => {
        if (!label) return <div key={i} style={{ height: 1, background: T.overlay06, margin: "6px 0" }} />;
        return (
          <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 0" }}>
            <span style={{ fontSize: T.textSm, color: T.text3, fontFamily: T.font, fontWeight: 500, letterSpacing: "0.04em" }}>{label}</span>
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
        <a
          href={`https://www.tradingview.com/chart/?symbol=${getTVSymbol(data.symbol)}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            marginTop: 10, padding: "5px 12px", borderRadius: 8,
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
        <ConfluencePanel confluence={data.confluence} />

        {/* Positioning */}
        <PositioningPanel
          positioning={data.positioning}
          cvdTrend={data.cvd_trend}
          cvdDiv={data.cvd_divergence}
          bsr={data.buy_sell_ratio}
        />

        {/* Whale Consensus */}
        <SmartMoneyPanel data={data} />

        {/* Confidence Sparkline */}
        <ConfidenceSparkline history={data.confidence_history} current={data.confidence} />

        {/* Engine Metrics (includes Z-Score) */}
        <EngineMetrics data={data} isMobile={isMobile} />
      </div>
    </div>
  );
}
