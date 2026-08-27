import { useState, useEffect, useCallback } from "react";
import { T, heatColor, phaseColor, exhaustMeta, fmt, zBar, getBaseSymbol, getTVSymbol } from "../theme.js";
import { ZScoreBar, RegimeBadge, SignalDot } from "./badges.jsx";
import BMSBChart from "./BMSBChart.jsx";
import ConditionsScorecard from "./ConditionsScorecard.jsx";
import ConfluencePanel from "./ConfluencePanel.jsx";
import PositioningPanel from "./PositioningPanel.jsx";

// ---------------------------------------------------------------------------
// DetailPanel
// ---------------------------------------------------------------------------

export default function DetailPanel({ selected, isMobile, isTablet, onClose, api }) {
  if (!selected) return null;

  const tvUrl = `https://www.tradingview.com/chart/?symbol=${getTVSymbol(selected.symbol)}`;
  const hlCoin = selected.symbol.split("/")[0];
  const hlUrl = `https://app.hyperliquid.xyz/trade/${hlCoin}`;

  return (
    <>
      {/* Click-outside overlay (mobile: opaque, desktop: transparent) */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, zIndex: 199,
          background: isMobile ? T.shadowDeep : "transparent",
        }}
      />

      <div style={{
        position: "fixed", right: 0, top: 0, bottom: 0,
        left: isMobile ? 0 : undefined,
        width: isMobile ? "100%" : isTablet ? 580 : 820,
        background: T.drawerBg,
        backdropFilter: "blur(32px) saturate(1.4)", WebkitBackdropFilter: "blur(32px) saturate(1.4)",
        borderLeft: isMobile ? "none" : `1px solid ${T.border}`,
        padding: isMobile ? "20px 16px" : "28px 32px",
        overflowY: "auto", zIndex: 200,
        transition: "transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94)",
        boxShadow: isMobile ? "none" : `-8px 0 40px ${T.shadowDeep}`,
      }}>
        {/* Mobile drag handle */}
        {isMobile && (
          <div style={{
            width: 36, height: 4, borderRadius: 2,
            background: T.overlay15,
            margin: "0 auto 16px auto",
          }} />
        )}

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: isMobile ? 20 : 22, fontWeight: 700, color: T.text1, fontFamily: T.font, letterSpacing: "-0.02em" }}>
              {getBaseSymbol(selected.symbol)}
            </div>
            <div style={{ fontSize: 10, color: T.text4, letterSpacing: "0.06em", fontFamily: T.mono, marginTop: 4 }}>
              {selected.symbol} {"\u00b7"} {(selected.timeframe || "").toUpperCase()}
            </div>
          </div>
          <button
            className="apple-btn"
            onClick={onClose}
            style={{
              borderRadius: "50%", padding: 0,
              width: isMobile ? 36 : 28,
              height: isMobile ? 36 : 28,
              fontSize: isMobile ? 14 : 12,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >{"\u2715"}</button>
        </div>

        {/* BMSB Chart */}
        <BMSBChart
          symbol={selected.symbol}
          timeframe={selected.timeframe === "1d" ? "1d" : "4h"}
          height={isMobile ? 300 : isTablet ? 420 : 520}
          signal={selected.signal}
          regime={selected.regime}
          heat={selected.heat}
          conditions={selected.conditions_met}
          conditionsTotal={selected.conditions_total}
          exhaustionState={selected.exhaustion_state}
          floorConfirmed={selected.floor_confirmed}
          signalConfidence={selected.signal_confidence}
          momentum={selected.momentum}
        />

        {/* Regime + Signal badges */}
        <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center", flexWrap: "wrap" }}>
          <RegimeBadge regime={selected.regime} />
          <SignalDot signal={selected.signal} />
          {selected.signal_confidence != null && (
            <span style={{
              padding: "3px 8px", borderRadius: "20px",
              background: T.surface, border: `1px solid ${T.border}`,
              fontSize: 9, fontFamily: T.mono, fontWeight: 500,
              color: selected.signal_confidence >= 0.8 ? "#34d399" : selected.signal_confidence >= 0.5 ? "#fbbf24" : T.text3,
            }}>
              {Math.round(selected.signal_confidence * 100)}%
            </span>
          )}
          {selected.signal_age_seconds != null && selected.signal_age_seconds > 0 && (() => {
            const s = selected.signal_age_seconds;
            const label = s < 60 ? "just now"
              : s < 3600 ? `${Math.round(s / 60)}m`
              : s < 86400 ? `${(s / 3600).toFixed(1)}h`
              : `${(s / 86400).toFixed(1)}d`;
            const color =
              s < 24 * 3600 ? "#34d399" :
              s < 3 * 24 * 3600 ? T.text2 :
              s < 7 * 24 * 3600 ? "#fbbf24" :
              T.text4;
            return (
              <span
                title="Time since signal label last changed"
                style={{
                  padding: "3px 8px", borderRadius: "20px",
                  background: "transparent", border: `1px solid ${T.border}`,
                  fontSize: 9, fontFamily: T.mono, fontWeight: 500,
                  color,
                }}
              >
                fired {label}{s >= 24 * 3600 ? " ago" : ""}
              </span>
            );
          })()}
        </div>

        {/* Conditions Scorecard */}
        <ConditionsScorecard
          conditions={selected.conditions_detail}
          met={selected.conditions_met}
          total={selected.conditions_total}
        />

        {/* Signal reason */}
        {selected.signal_reason && (
          <div style={{
            padding: "12px 14px", borderRadius: T.radiusSm,
            background: T.glassBg,
            border: `1px solid ${T.border}`,
            marginBottom: 14,
            backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
          }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, marginBottom: 6,
            }}>
              <div style={{ width: 3, height: 12, borderRadius: 2, background: T.text3, flexShrink: 0 }} />
              <span style={{ fontSize: T.textXs, color: T.text4, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 600, textTransform: "uppercase" }}>
                Signal Reason
              </span>
            </div>
            <div style={{ fontSize: T.textSm, color: T.text2, fontFamily: T.mono, lineHeight: 1.6, paddingLeft: 11 }}>
              {selected.signal_reason}
            </div>
          </div>
        )}

        {/* Signal warnings */}
        {selected.signal_warnings && selected.signal_warnings.length > 0 && (
          <div style={{
            padding: "12px 14px", borderRadius: T.radiusSm,
            background: "rgba(251,191,36,0.03)",
            border: "1px solid rgba(251,191,36,0.12)",
            marginBottom: 14,
            backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
          }}>
            {selected.signal_warnings.map((w, i) => (
              <div key={i} style={{
                fontSize: T.textXs, color: "#fbbf24", fontFamily: T.mono, lineHeight: 1.7,
                display: "flex", gap: 6, alignItems: "flex-start",
              }}>
                <span style={{ flexShrink: 0 }}>{"\u26a0"}</span>
                <span>{w}</span>
              </div>
            ))}
          </div>
        )}

        {/* Raw vs Final signal */}
        {selected.raw_signal && selected.raw_signal !== selected.signal && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginBottom: 12,
            fontSize: T.textXs, color: T.text4, fontFamily: T.mono,
          }}>
            <span>Raw: </span>
            <SignalDot signal={selected.raw_signal} />
            <span style={{ color: T.text4 }}>{"\u2192"}</span>
            <span>Final: </span>
            <SignalDot signal={selected.signal} />
          </div>
        )}

        {/* Agent layer override indicator */}
        {selected.agent_signal && selected.agent_signal !== selected.signal && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginBottom: 12,
            fontSize: T.textXs, color: "#a78bfa", fontFamily: T.mono,
          }}>
            <span>{"\U0001f916"} Agent: </span>
            <SignalDot signal={selected.signal} />
            <span style={{ color: T.text4 }}>{"\u2192"}</span>
            <SignalDot signal={selected.agent_signal} />
            {selected.agent_filters_fired && selected.agent_filters_fired.length > 0 && (
              <span style={{ color: T.text4, fontSize: T.textXs }}>
                ({selected.agent_filters_fired.join(", ")})
              </span>
            )}
          </div>
        )}

        {/* Confluence Panel */}
        <ConfluencePanel confluence={selected.confluence} />

        {/* Market Structure — Positioning + CoinGlass signals unified */}
        <PositioningPanel
          positioning={selected.positioning}
          cvdTrend={selected.cvd_trend}
          cvdDiv={selected.cvd_divergence}
          bsr={selected.buy_sell_ratio}
          vpin={selected.vpin}
          vpinLabel={selected.vpin_label}
          vpinHistory={selected.vpin_history}
          oiContext={selected.oi_context}
        />

        {/* Z-Score Bar */}
        <div style={{ marginBottom: 16 }}>
          <ZScoreBar z={selected.zscore} isMobile={isMobile} />
        </div>

        {/* Detailed Metrics */}
        <div style={{
          background: T.glassBg,
          border: `1px solid ${T.border}`,
          borderRadius: T.radius,
          padding: "14px 16px",
          marginBottom: 14,
          backdropFilter: "blur(20px) saturate(1.3)",
          WebkitBackdropFilter: "blur(20px) saturate(1.3)",
          boxShadow: `0 2px 12px ${T.shadow}`,
        }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            marginBottom: 12, paddingBottom: 10,
            borderBottom: `1px solid ${T.overlay06}`,
          }}>
            <div style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
            <span style={{
              fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em",
              fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
            }}>
              Engine Metrics
            </span>
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
            if (!label) return <div key={i} style={{ height: 1, background: T.overlay06, margin: "4px 0" }} />;
            return (
              <div key={label} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "7px 0",
              }}>
                <span style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.font, fontWeight: 500, letterSpacing: "0.04em" }}>{label}</span>
                <span style={{ fontFamily: T.mono, fontSize: isMobile ? T.textSm : T.textBase, color: valColor || T.text1, fontWeight: 600 }}>{value}</span>
              </div>
            );
          })}
        </div>
        {/* External links */}
        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <a
            href={hlUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="apple-btn apple-btn-accent"
            style={{
              flex: 1, display: "block", padding: isMobile ? "14px 16px" : "12px 16px",
              borderRadius: 12, fontFamily: T.font,
              fontSize: 12, textDecoration: "none", textAlign: "center",
              letterSpacing: "0.06em", fontWeight: 700,
            }}
          >
            Trade on Hyperliquid {"\u2197"}
          </a>
          <a
            href={tvUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="apple-btn"
            style={{
              flex: 1, display: "block", padding: isMobile ? "14px 16px" : "12px 16px",
              borderRadius: 12, fontFamily: T.font,
              fontSize: 12, textDecoration: "none", textAlign: "center",
              letterSpacing: "0.06em", fontWeight: 700,
              border: `1px solid ${T.border}`, color: T.text2,
            }}
          >
            Open in TradingView {"\u2197"}
          </a>
        </div>
      </div>
    </>
  );
}
