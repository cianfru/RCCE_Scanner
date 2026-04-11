/**
 * PositioningPanel — Signal-forward market structure display.
 *
 * Layout:
 *   Row 1  (badges):  FUNDING REGIME | OI TREND
 *   Row 2  (badges):  CVD SIGNAL     | SPOT DOMINANCE
 *   Row 3  (badges):  SMART MONEY    | LIQ INTENSITY
 *   ─────────────────────────────────────────
 *   Numbers strip:    Rate · OI · LSR · 24h Liq  (secondary detail)
 *
 * Props:
 *   positioning — PositioningResponse (Binance/HL native data + CoinGlass enrich)
 *   cvdTrend    — "BULLISH" | "BEARISH" | "NEUTRAL"
 *   cvdDiv      — bool
 *   bsr         — number (buy/sell ratio)
 *   vpin        — number 0..1 (volume-synchronized probability of informed trading)
 *   vpinLabel   — "BALANCED" | "ELEVATED" | "TOXIC"
 *   vpinHistory — number[] (rolling 48-tick history 0..1)
 *   oiContext   — string (contextual OI interpretation from backend, e.g. "confirms entry")
 */
import { useState } from "react";
import { T } from "../theme.js";

// ─── Inline tooltip ───────────────────────────────────────────────────────────

function InfoTip({ title, text }) {
  const [show, setShow] = useState(false);
  return (
    <span
      style={{ position: "relative", display: "inline-flex", alignItems: "center", flexShrink: 0 }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span style={{
        fontSize: 7, color: T.text4, cursor: "help",
        fontFamily: T.mono, fontWeight: 700,
        width: 12, height: 12, borderRadius: "50%",
        border: `1px solid ${T.border}`,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        lineHeight: 1, userSelect: "none",
        transition: "all 0.15s",
      }}>
        i
      </span>
      {show && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 6px)", left: "50%",
          transform: "translateX(-50%)",
          background: "rgba(16,16,20,0.95)",
          backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)",
          border: `1px solid ${T.border}`,
          borderRadius: 8, padding: "10px 12px",
          zIndex: 9999, width: 220, pointerEvents: "none",
          boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        }}>
          {title && (
            <div style={{
              fontSize: T.textSm, color: T.text1, fontFamily: T.mono,
              fontWeight: 700, marginBottom: 4, letterSpacing: "0.04em",
            }}>
              {title}
            </div>
          )}
          <div style={{
            fontSize: T.textXs, color: T.text3, fontFamily: T.font,
            fontWeight: 400, lineHeight: 1.55,
          }}>
            {text}
          </div>
        </div>
      )}
    </span>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(v) {
  if (v == null) return "\u2014";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

// ─── Signal badge cell ────────────────────────────────────────────────────────

function Badge({ icon, label, sub, color, bg, empty, info, context, contextColor }) {
  if (empty) {
    return (
      <div style={{
        flex: "1 1 48%", padding: "10px 12px", borderRadius: 10,
        background: T.overlay02,
        border: `1px solid ${T.border}`,
        display: "flex", flexDirection: "column", gap: 2, minWidth: 0,
      }}>
        <span style={{ fontSize: 9, color: T.text4, fontFamily: T.font, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em" }}>{"\u2014"}</span>
      </div>
    );
  }
  const c = color || T.text2;
  return (
    <div style={{
      flex: "1 1 48%", padding: "10px 12px", borderRadius: 10,
      background: `${c}08`,
      border: `1px solid ${c}18`,
      display: "flex", flexDirection: "column", gap: 4, minWidth: 0,
      transition: "all 0.2s ease",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
        {icon && <span style={{ fontSize: 10, lineHeight: 1 }}>{icon}</span>}
        <span style={{
          fontSize: T.textSm, color: c, fontFamily: T.mono,
          fontWeight: 700, letterSpacing: "0.06em", lineHeight: 1.2,
        }}>
          {label}
        </span>
        {info && <InfoTip title={info.title} text={info.text} />}
      </div>
      {sub && (
        <span style={{
          fontSize: T.textXs, color: T.text4, fontFamily: T.font,
          fontWeight: 500, letterSpacing: "0.03em",
        }}>
          {sub}
        </span>
      )}
      {context && (
        <span style={{
          fontSize: 9, color: contextColor || T.text4, fontFamily: T.mono,
          fontWeight: 600, letterSpacing: "0.04em", opacity: 0.9,
        }}>
          {context}
        </span>
      )}
    </div>
  );
}

// ─── Signal factories ─────────────────────────────────────────────────────────

const BADGE_INFO = {
  funding: {
    title: "Funding Regime",
    text: "Perpetual futures funding rate direction. Positive = longs pay shorts (crowded longs). Negative = shorts pay longs (crowded shorts). CROWDED_LONG is a caution signal \u2014 condition 8 in the conviction score.",
  },
  oi: {
    title: "Open Interest Trend",
    text: "Direction of futures open interest \u2014 sourced from CoinGlass multi-exchange aggregated 4h change (more accurate than single-exchange). BUILDING = new money entering with price (confirmed move). SQUEEZE = OI falling as price rises (shorts closing, not new longs). LIQUIDATING = OI falling with price (long cascade). SHORTING = OI rising as price falls (aggressive shorts opening).",
  },
  cvd: {
    title: "Cumulative Volume Delta",
    text: "Net taker buy/sell pressure from CoinGlass futures data. TAKERS BUYING = aggressive buyers initiating trades. \u26a1DIV = CVD diverges from price (potential reversal). CVD can upgrade ACCUMULATE \u2192 LIGHT_LONG or downgrade STRONG_LONG \u2192 TRIM.",
  },
  spot: {
    title: "Spot Dominance",
    text: "Ratio of spot volume vs futures volume. SPOT-LED = organic demand driving price (higher quality move). FUTURES-LED = leverage-driven rally (lower quality, more fragile). SPOT_LED combined with bullish CVD can trigger signal upgrade.",
  },
  smartMoney: {
    title: "Smart Money LSR",
    text: "Long/Short Ratio split by account tier (CoinGlass). 'Pro' = top-tier trader accounts. 'Retail' = overall market LSR. Wired into signal decisions: Pro LSR < 0.7 downgrades STRONG_LONG \u2192 LIGHT_LONG. Pro LSR < 0.8 adds caution warning. Pro LSR > 1.5 reinforces entry signals.",
  },
  liq: {
    title: "Liquidation Intensity",
    text: "Total liquidated positions in 24h. LONGS FLUSHED (\u226570% long liquidations) often marks capitulation \u2014 a contrarian buy signal. SHORTS SQUEEZED (\u226570% short liquidations) may mark a local top. HIGH LIQ without directional skew = general deleveraging.",
  },
};

function fundingBadge(regime, rate) {
  const rateStr = rate != null ? `${(rate * 100).toFixed(4)}% per 8h` : null;
  switch (regime) {
    case "CROWDED_LONG":
      return { icon: "\u26a0\ufe0f", label: "LONGS CROWDED", sub: rateStr, color: "#f87171", info: BADGE_INFO.funding };
    case "CROWDED_SHORT":
      return { icon: "\ud83c\udfaf", label: "SHORTS CROWDED", sub: rateStr, color: "#34d399", info: BADGE_INFO.funding };
    default: {
      if (rate == null) return { icon: null, label: "FUNDING", sub: "\u2014", color: T.text4, info: BADGE_INFO.funding };
      const c = rate < 0 ? "#34d399" : rate > 0.01 ? "#f87171" : rate > 0.005 ? "#fbbf24" : T.text3;
      return { icon: rate < 0 ? "\u2193" : "\u2191", label: "FUNDING OK", sub: rateStr, color: c, info: BADGE_INFO.funding };
    }
  }
}

function oiBadge(trend, oiValue, oiChangePct) {
  const sub = oiValue ? `${fmt(oiValue)}${oiChangePct ? ` \u00b7 ${oiChangePct >= 0 ? "+" : ""}${oiChangePct.toFixed(1)}%` : ""}` : null;
  switch (trend) {
    case "BUILDING":    return { icon: "\u2191",  label: "OI BUILDING",    sub, color: "#34d399", info: BADGE_INFO.oi };
    case "SQUEEZE":     return { icon: "\u26a1", label: "OI SQUEEZE",     sub, color: "#fbbf24", info: BADGE_INFO.oi };
    case "LIQUIDATING": return { icon: "\u2193\u2193", label: "LIQUIDATING",   sub, color: "#f87171", info: BADGE_INFO.oi };
    case "SHORTING":    return { icon: "\u2193",  label: "SHORTING INTO",  sub, color: "#c084fc", info: BADGE_INFO.oi };
    default:            return { icon: "\u2192",  label: trend || "OI STABLE", sub, color: T.text4, info: BADGE_INFO.oi };
  }
}

function cvdBadge(cvdTrend, cvdDiv, bsr) {
  const divTag = cvdDiv ? " \u26a1DIV" : "";
  const sub = bsr != null && bsr !== 1 ? `BSR ${bsr.toFixed(3)}x` : null;
  switch (cvdTrend) {
    case "BULLISH": return { icon: "\u25b2", label: `TAKERS BUYING${divTag}`,  sub, color: "#34d399", info: BADGE_INFO.cvd };
    case "BEARISH": return { icon: "\u25bc", label: `TAKERS SELLING${divTag}`, sub, color: "#f87171", info: BADGE_INFO.cvd };
    default:        return { icon: "\u2192", label: "CVD NEUTRAL",             sub, color: T.text4,   info: BADGE_INFO.cvd };
  }
}

function spotBadge(spotDom, spotRatio) {
  const pct = spotRatio > 0 ? `${(spotRatio * 100).toFixed(0)}% spot vol` : null;
  switch (spotDom) {
    case "SPOT_LED":    return { icon: "\ud83d\udfe2", label: "SPOT-LED",    sub: pct || "organic demand",  color: "#34d399", info: BADGE_INFO.spot };
    case "FUTURES_LED": return { icon: "\u26a1", label: "FUTURES-LED", sub: pct || "leverage driven", color: "#f87171", info: BADGE_INFO.spot };
    default:            return { icon: "\u25ce",  label: "MIXED FLOW",  sub: pct,                      color: T.text4,   info: BADGE_INFO.spot };
  }
}

function smartMoneyBadge(topLsr, retailLsr) {
  if (!topLsr || topLsr === 1) return { icon: null, label: "LSR NEUTRAL", sub: retailLsr ? `Retail ${retailLsr.toFixed(2)}` : null, color: T.text4, info: BADGE_INFO.smartMoney };
  const lsrSub = retailLsr ? `Retail ${retailLsr.toFixed(2)} \u00b7 Pro ${topLsr.toFixed(2)}` : `Pro ${topLsr.toFixed(2)}`;
  if (topLsr > 1.3)  return { icon: "\u2191", label: "TOP LONGS HEAVY",  sub: lsrSub, color: "#fbbf24", info: BADGE_INFO.smartMoney };
  if (topLsr < 0.8)  return { icon: "\u2193", label: "TOP SHORTS HEAVY", sub: lsrSub, color: "#c084fc", info: BADGE_INFO.smartMoney };
  return { icon: "\u2192", label: "TOP BALANCED", sub: lsrSub, color: T.text3, info: BADGE_INFO.smartMoney };
}

function liqBadge(liq24h, longLiq, shortLiq) {
  if (!liq24h) return { icon: null, label: "NO LIQ DATA", sub: null, color: T.text4, info: BADGE_INFO.liq };
  const total = liq24h;
  const longPct = longLiq && total ? Math.round((longLiq / total) * 100) : null;
  const intensity = total >= 100e6 ? "HIGH" : total >= 10e6 ? "MED" : "LOW";
  const intColor = intensity === "HIGH" ? "#f87171" : intensity === "MED" ? "#fbbf24" : T.text4;

  if (longPct != null && longPct >= 70) {
    return { icon: "\ud83d\udd34", label: "LONGS FLUSHED",   sub: `${fmt(total)} \u00b7 ${longPct}% long liq`,      color: "#34d399", info: BADGE_INFO.liq };
  }
  if (longPct != null && longPct <= 30) {
    return { icon: "\ud83d\udfe2", label: "SHORTS SQUEEZED", sub: `${fmt(total)} \u00b7 ${100-longPct}% short liq`, color: "#f87171", info: BADGE_INFO.liq };
  }
  return { icon: "\u2696\ufe0f", label: `${intensity} LIQ`, sub: `${fmt(total)} 24h`, color: intColor, info: BADGE_INFO.liq };
}

// ─── Stat pill ───────────────────────────────────────────────────────────────

const STAT_INFO = {
  "RATE /8H": "Funding rate per 8-hour settlement window. Positive = longs pay shorts (bullish crowding). Above 0.01% = crowded longs (caution). Negative = shorts pay longs (bearish crowding).",
  "OPEN INT": "Total USD value of all open perpetual futures positions. Rising OI alongside price confirms a real move. Falling OI during a rally suggests a short squeeze.",
  "LSR":      "Long/Short Ratio \u2014 ratio of accounts holding long vs short positions. >1 = more longs. >1.3 = crowded long (increases liquidation risk). <0.8 = crowded short (squeeze potential).",
  "LIQ 24H":  "Total USD value of liquidated futures positions in the last 24 hours. High liquidations indicate forced deleveraging.",
  "LIQ 4H":   "Liquidations in the last 4 hours \u2014 a more recent read on deleveraging pressure. Spike here = active flush in progress.",
  "LIQ 1H":   "Liquidations in the last 1 hour \u2014 real-time stress indicator. Elevated 1H liq relative to 4H suggests an active cascade.",
  "VOL 24H":  "Total 24-hour trading volume (spot + futures combined). High volume during a breakout adds conviction. Low volume = weak move.",
  "LEV RISK": "Composite leverage risk score based on OI/volume ratio and funding extremes. HIGH = market is over-leveraged, sharp moves likely. LOW = clean positioning.",
};

function Stat({ label, value, color }) {
  const infoText = STAT_INFO[label];
  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 3,
      padding: "6px 10px", borderRadius: 8,
      background: T.overlay02,
      border: `1px solid ${T.overlay06}`,
      minWidth: 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
        <span style={{
          fontSize: T.textXs, color: T.text4, fontFamily: T.font,
          fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em",
          whiteSpace: "nowrap",
        }}>{label}</span>
        {infoText && <InfoTip text={infoText} />}
      </div>
      <span style={{
        fontSize: T.textSm, color: color || T.text2, fontFamily: T.mono,
        fontWeight: 700, whiteSpace: "nowrap",
      }}>{value}</span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

// OI context → color mapping
const OI_CTX_COLOR = {
  "confirms entry": "#34d399",
  "confirms exit": "#34d399",
  "short-cover rally": "#fbbf24",
  "counter-trend OI": "#fbbf24",
  "long cascade — caution": "#f87171",
  "bears aggressive": "#f87171",
  "capitulation": "#fbbf24",
};

// ─── VPIN gauge ───────────────────────────────────────────────────────────────

const VPIN_INFO = {
  title: "VPIN — Flow Toxicity",
  text: "Volume-Synchronized Probability of Informed Trading. Measures how one-sided taker flow has been across recent volume buckets. BALANCED (<30%) = healthy two-way flow. ELEVATED (30-55%) = directional pressure building. TOXIC (>55%) = persistent one-sided flow, often signals informed trading before a move. Market makers pull quotes when VPIN is high, amplifying volatility.",
};

// Mini sparkline — 0..1 VPIN values mapped against the 0-55 zones so the
// threshold lines stay at the same visual position as the main gauge bar.
function VpinSparkline({ history }) {
  if (!history || history.length < 2) return null;
  const w = 100, h = 22, pad = 1;
  const n = history.length;
  const xStep = (w - pad * 2) / Math.max(n - 1, 1);

  const yFor = (v) => {
    const clamped = Math.max(0, Math.min(1, v));
    return h - pad - clamped * (h - pad * 2);
  };

  const points = history.map((v, i) => `${pad + i * xStep},${yFor(v)}`).join(" ");

  // Threshold lines at 30% and 55% (matching the gauge)
  const y30 = yFor(0.30);
  const y55 = yFor(0.55);

  // Color the stroke by the latest value
  const latest = history[history.length - 1];
  const stroke =
    latest >= 0.55 ? "#f87171" :
    latest >= 0.30 ? "#fbbf24" :
    "#34d399";

  return (
    <svg
      width={w}
      height={h}
      style={{ flexShrink: 0 }}
      viewBox={`0 0 ${w} ${h}`}
    >
      {/* Elevated zone tint */}
      <rect x="0" y={y55} width={w} height={y30 - y55} fill="#fbbf2410" />
      {/* Toxic zone tint */}
      <rect x="0" y="0" width={w} height={y55} fill="#f8717110" />
      {/* Threshold lines */}
      <line x1="0" y1={y30} x2={w} y2={y30} stroke="#fbbf2430" strokeDasharray="2 2" />
      <line x1="0" y1={y55} x2={w} y2={y55} stroke="#f8717130" strokeDasharray="2 2" />
      {/* Main line */}
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Latest dot */}
      <circle
        cx={pad + (n - 1) * xStep}
        cy={yFor(latest)}
        r="2"
        fill={stroke}
      />
    </svg>
  );
}

function VpinGauge({ vpin, vpinLabel, vpinHistory }) {
  if (vpin == null || vpin === 0) return null;
  const pct = Math.max(0, Math.min(1, vpin)) * 100;
  // Thresholds mirror backend labels: 30% / 55%
  const color =
    vpinLabel === "TOXIC" ? "#f87171" :
    vpinLabel === "ELEVATED" ? "#fbbf24" :
    "#34d399";
  const displayLabel =
    vpinLabel === "TOXIC" ? "TOXIC FLOW" :
    vpinLabel === "ELEVATED" ? "ELEVATED" :
    "BALANCED";

  return (
    <div style={{
      padding: "8px 10px", borderRadius: 8,
      background: T.overlay02,
      border: `1px solid ${T.overlay06}`,
      marginBottom: 14,
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 6, gap: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{
            fontSize: T.textXs, color: T.text4, fontFamily: T.mono,
            fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em",
          }}>
            VPIN
          </span>
          <InfoTip {...VPIN_INFO} />
        </div>
        <span style={{
          fontSize: T.textXs, color, fontFamily: T.mono, fontWeight: 700,
          letterSpacing: "0.06em",
        }}>
          {displayLabel} · {pct.toFixed(0)}%
        </span>
      </div>
      {/* Track */}
      <div style={{
        position: "relative", height: 6, borderRadius: 3,
        background: T.overlay06, overflow: "hidden",
      }}>
        {/* Zone markers: green 0-30, yellow 30-55, red 55-100 */}
        <div style={{
          position: "absolute", left: "30%", top: 0, bottom: 0,
          width: 1, background: T.overlay12 || T.border,
        }} />
        <div style={{
          position: "absolute", left: "55%", top: 0, bottom: 0,
          width: 1, background: T.overlay12 || T.border,
        }} />
        {/* Fill */}
        <div style={{
          position: "absolute", left: 0, top: 0, bottom: 0,
          width: `${pct}%`,
          background: color,
          boxShadow: `0 0 8px ${color}66`,
          transition: "width 0.4s ease",
        }} />
      </div>
      {/* History sparkline */}
      {vpinHistory && vpinHistory.length >= 2 && (
        <div style={{
          marginTop: 6,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          gap: 10,
        }}>
          <span style={{
            fontSize: 9, color: T.text4, fontFamily: T.mono,
            fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase",
          }}>
            {vpinHistory.length} ticks
          </span>
          <VpinSparkline history={vpinHistory} />
        </div>
      )}
    </div>
  );
}

export default function PositioningPanel({ positioning, cvdTrend, cvdDiv, bsr, vpin, vpinLabel, vpinHistory, oiContext }) {
  if (!positioning) return null;

  const {
    funding_regime, funding_rate,
    oi_trend, oi_value, oi_change_pct,
    leverage_risk,
    volume_24h,
    long_short_ratio, top_trader_lsr,
    liquidation_24h_usd, long_liq_usd, short_liq_usd,
    liquidation_4h_usd, liquidation_1h_usd,
    spot_dominance, spot_futures_ratio,
    source,
  } = positioning;

  // ── Badge data ──────────────────────────────────────────────────────────────
  const b1 = fundingBadge(funding_regime, funding_rate);
  const b2 = oiBadge(oi_trend, oi_value, oi_change_pct);
  if (oiContext) {
    b2.context = oiContext;
    b2.contextColor = OI_CTX_COLOR[oiContext] || T.text4;
  }
  const b3 = cvdBadge(cvdTrend, cvdDiv, bsr);
  const b4 = spotBadge(spot_dominance, spot_futures_ratio);
  const b5 = smartMoneyBadge(top_trader_lsr, long_short_ratio);
  const b6 = liqBadge(liquidation_24h_usd, long_liq_usd, short_liq_usd);

  // ── Secondary stats ─────────────────────────────────────────────────────────
  const stats = [
    funding_rate != null && { label: "RATE /8H", value: `${(funding_rate * 100).toFixed(4)}%`, color: funding_rate < 0 ? "#34d399" : funding_rate > 0.01 ? "#f87171" : T.text2 },
    oi_value > 0 && { label: "OPEN INT", value: fmt(oi_value), color: T.text2 },
    long_short_ratio > 0 && { label: "LSR", value: long_short_ratio.toFixed(2), color: long_short_ratio > 1.3 ? "#f87171" : long_short_ratio < 0.8 ? "#34d399" : T.text2 },
    liquidation_24h_usd > 0 && { label: "LIQ 24H", value: fmt(liquidation_24h_usd), color: T.text3 },
    liquidation_4h_usd > 0 && { label: "LIQ 4H", value: fmt(liquidation_4h_usd), color: T.text3 },
    liquidation_1h_usd > 0 && { label: "LIQ 1H", value: fmt(liquidation_1h_usd), color: T.text3 },
    volume_24h > 0 && { label: "VOL 24H", value: fmt(volume_24h), color: T.text3 },
    leverage_risk && leverage_risk !== "UNKNOWN" && { label: "LEV RISK", value: leverage_risk, color: leverage_risk === "HIGH" ? "#f87171" : leverage_risk === "MEDIUM" ? "#fbbf24" : "#34d399" },
  ].filter(Boolean);

  return (
    <div style={{
      background: T.glassBg,
      border: `1px solid ${T.border}`,
      borderRadius: T.radius,
      padding: 16,
      marginBottom: 14,
      backdropFilter: "blur(20px) saturate(1.3)",
      WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 12, paddingBottom: 10,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 3, height: 14, borderRadius: 2,
            background: T.accent, flexShrink: 0,
          }} />
          <span style={{
            fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em",
            fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
          }}>
            Market Structure
          </span>
        </div>
        {source && (
          <span style={{
            fontSize: T.textXs, color: T.accent,
            fontFamily: T.mono, fontWeight: 600,
            padding: "2px 8px", borderRadius: 6,
            background: `${T.accent}12`,
            border: `1px solid ${T.accent}20`,
            letterSpacing: "0.06em",
          }}>
            {source.slice(0, 3).toUpperCase()}
          </span>
        )}
      </div>

      {/* Badge grid — 2 columns \u00d7 3 rows */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
        <Badge {...b1} />
        <Badge {...b2} />
        <Badge {...b3} />
        <Badge {...b4} />
        <Badge {...b5} />
        <Badge {...b6} />
      </div>

      {/* VPIN flow toxicity gauge */}
      <VpinGauge vpin={vpin} vpinLabel={vpinLabel} vpinHistory={vpinHistory} />

      {/* Numbers strip */}
      {stats.length > 0 && (
        <>
          <div style={{
            height: 1, background: T.overlay06, marginBottom: 12,
          }} />
          <div style={{
            display: "flex", flexWrap: "wrap", gap: 6,
          }}>
            {stats.map(s => <Stat key={s.label} {...s} />)}
          </div>
        </>
      )}
    </div>
  );
}
