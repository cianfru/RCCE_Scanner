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
        fontSize: 8, color: T.text4, cursor: "help",
        fontFamily: T.mono, fontWeight: 700,
        width: 11, height: 11, borderRadius: "50%",
        border: `1px solid ${T.border}`,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        lineHeight: 1, userSelect: "none",
      }}>
        i
      </span>
      {show && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 6px)", left: "50%",
          transform: "translateX(-50%)",
          background: "#16161a",
          border: `1px solid ${T.border}`,
          borderRadius: 6, padding: "8px 10px",
          zIndex: 9999, width: 210, pointerEvents: "none",
          boxShadow: "0 6px 20px rgba(0,0,0,0.6)",
        }}>
          {title && (
            <div style={{
              fontSize: 10, color: T.text1, fontFamily: T.mono,
              fontWeight: 700, marginBottom: 4, letterSpacing: "0.04em",
            }}>
              {title}
            </div>
          )}
          <div style={{
            fontSize: 10, color: T.text3, fontFamily: T.font,
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
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

// ─── Signal badge cell ────────────────────────────────────────────────────────

function Badge({ icon, label, sub, color, bg, empty, info }) {
  if (empty) {
    return (
      <div style={{
        flex: "1 1 48%", padding: "10px 12px", borderRadius: 6,
        background: "transparent", border: `1px solid ${T.border}`,
        display: "flex", flexDirection: "column", gap: 2, minWidth: 0,
      }}>
        <span style={{ fontSize: 9, color: T.text4, fontFamily: T.font, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em" }}>—</span>
      </div>
    );
  }
  const c = color || T.text2;
  const bg_ = bg || `${c}14`;
  return (
    <div style={{
      flex: "1 1 48%", padding: "10px 12px", borderRadius: 6,
      background: bg_, border: `1px solid ${c}28`,
      display: "flex", flexDirection: "column", gap: 3, minWidth: 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
        {icon && <span style={{ fontSize: 11 }}>{icon}</span>}
        <span style={{ fontSize: 10, color: c, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em", lineHeight: 1.2 }}>
          {label}
        </span>
        {info && <InfoTip title={info.title} text={info.text} />}
      </div>
      {sub && (
        <span style={{ fontSize: 9, color: `${c}99`, fontFamily: T.font, fontWeight: 500, letterSpacing: "0.04em" }}>
          {sub}
        </span>
      )}
    </div>
  );
}

// ─── Signal factories ─────────────────────────────────────────────────────────

const BADGE_INFO = {
  funding: {
    title: "Funding Regime",
    text: "Perpetual futures funding rate direction. Positive = longs pay shorts (crowded longs). Negative = shorts pay longs (crowded shorts). CROWDED_LONG is a caution signal — condition 8 in the conviction score.",
  },
  oi: {
    title: "Open Interest Trend",
    text: "Direction of futures open interest — sourced from CoinGlass multi-exchange aggregated 4h change (more accurate than single-exchange). BUILDING = new money entering with price (confirmed move). SQUEEZE = OI falling as price rises (shorts closing, not new longs). LIQUIDATING = OI falling with price (long cascade). SHORTING = OI rising as price falls (aggressive shorts opening).",
  },
  cvd: {
    title: "Cumulative Volume Delta",
    text: "Net taker buy/sell pressure from CoinGlass futures data. TAKERS BUYING = aggressive buyers initiating trades. ⚡DIV = CVD diverges from price (potential reversal). CVD can upgrade ACCUMULATE → LIGHT_LONG or downgrade STRONG_LONG → TRIM.",
  },
  spot: {
    title: "Spot Dominance",
    text: "Ratio of spot volume vs futures volume. SPOT-LED = organic demand driving price (higher quality move). FUTURES-LED = leverage-driven rally (lower quality, more fragile). SPOT_LED combined with bullish CVD can trigger signal upgrade.",
  },
  smartMoney: {
    title: "Smart Money LSR",
    text: "Long/Short Ratio split by account tier (CoinGlass). 'Pro' = top-tier trader accounts. 'Retail' = overall market LSR. Wired into signal decisions: Pro LSR < 0.7 downgrades STRONG_LONG → LIGHT_LONG. Pro LSR < 0.8 adds caution warning. Pro LSR > 1.5 reinforces entry signals.",
  },
  liq: {
    title: "Liquidation Intensity",
    text: "Total liquidated positions in 24h. LONGS FLUSHED (≥70% long liquidations) often marks capitulation — a contrarian buy signal. SHORTS SQUEEZED (≥70% short liquidations) may mark a local top. HIGH LIQ without directional skew = general deleveraging.",
  },
};

function fundingBadge(regime, rate) {
  const rateStr = rate != null ? `${(rate * 100).toFixed(4)}% per 8h` : null;
  switch (regime) {
    case "CROWDED_LONG":
      return { icon: "⚠️", label: "LONGS CROWDED", sub: rateStr, color: "#f87171", info: BADGE_INFO.funding };
    case "CROWDED_SHORT":
      return { icon: "🎯", label: "SHORTS CROWDED", sub: rateStr, color: "#34d399", info: BADGE_INFO.funding };
    default: {
      if (rate == null) return { icon: null, label: "FUNDING", sub: "—", color: T.text4, info: BADGE_INFO.funding };
      const c = rate < 0 ? "#34d399" : rate > 0.01 ? "#f87171" : rate > 0.005 ? "#fbbf24" : T.text3;
      return { icon: rate < 0 ? "↓" : "↑", label: "FUNDING OK", sub: rateStr, color: c, info: BADGE_INFO.funding };
    }
  }
}

function oiBadge(trend, oiValue, oiChangePct) {
  const sub = oiValue ? `${fmt(oiValue)}${oiChangePct ? ` · ${oiChangePct >= 0 ? "+" : ""}${oiChangePct.toFixed(1)}%` : ""}` : null;
  switch (trend) {
    case "BUILDING":    return { icon: "↑",  label: "OI BUILDING",    sub, color: "#34d399", info: BADGE_INFO.oi };
    case "SQUEEZE":     return { icon: "⚡", label: "OI SQUEEZE",     sub, color: "#fbbf24", info: BADGE_INFO.oi };
    case "LIQUIDATING": return { icon: "↓↓", label: "LIQUIDATING",   sub, color: "#f87171", info: BADGE_INFO.oi };
    case "SHORTING":    return { icon: "↓",  label: "SHORTING INTO",  sub, color: "#c084fc", info: BADGE_INFO.oi };
    default:            return { icon: "→",  label: trend || "OI STABLE", sub, color: T.text4, info: BADGE_INFO.oi };
  }
}

function cvdBadge(cvdTrend, cvdDiv, bsr) {
  const divTag = cvdDiv ? " ⚡DIV" : "";
  const sub = bsr != null && bsr !== 1 ? `BSR ${bsr.toFixed(3)}x` : null;
  switch (cvdTrend) {
    case "BULLISH": return { icon: "▲", label: `TAKERS BUYING${divTag}`,  sub, color: "#34d399", info: BADGE_INFO.cvd };
    case "BEARISH": return { icon: "▼", label: `TAKERS SELLING${divTag}`, sub, color: "#f87171", info: BADGE_INFO.cvd };
    default:        return { icon: "→", label: "CVD NEUTRAL",             sub, color: T.text4,   info: BADGE_INFO.cvd };
  }
}

function spotBadge(spotDom, spotRatio) {
  const pct = spotRatio > 0 ? `${(spotRatio * 100).toFixed(0)}% spot vol` : null;
  switch (spotDom) {
    case "SPOT_LED":    return { icon: "🟢", label: "SPOT-LED",    sub: pct || "organic demand",  color: "#34d399", info: BADGE_INFO.spot };
    case "FUTURES_LED": return { icon: "⚡", label: "FUTURES-LED", sub: pct || "leverage driven", color: "#f87171", info: BADGE_INFO.spot };
    default:            return { icon: "◎",  label: "MIXED FLOW",  sub: pct,                      color: T.text4,   info: BADGE_INFO.spot };
  }
}

function smartMoneyBadge(topLsr, retailLsr) {
  if (!topLsr || topLsr === 1) return { icon: null, label: "LSR NEUTRAL", sub: retailLsr ? `Retail ${retailLsr.toFixed(2)}` : null, color: T.text4, info: BADGE_INFO.smartMoney };
  const lsrSub = retailLsr ? `Retail ${retailLsr.toFixed(2)} · Pro ${topLsr.toFixed(2)}` : `Pro ${topLsr.toFixed(2)}`;
  if (topLsr > 1.3)  return { icon: "↑", label: "TOP LONGS HEAVY",  sub: lsrSub, color: "#fbbf24", info: BADGE_INFO.smartMoney };
  if (topLsr < 0.8)  return { icon: "↓", label: "TOP SHORTS HEAVY", sub: lsrSub, color: "#c084fc", info: BADGE_INFO.smartMoney };
  return { icon: "→", label: "TOP BALANCED", sub: lsrSub, color: T.text3, info: BADGE_INFO.smartMoney };
}

function liqBadge(liq24h, longLiq, shortLiq) {
  if (!liq24h) return { icon: null, label: "NO LIQ DATA", sub: null, color: T.text4, info: BADGE_INFO.liq };
  const total = liq24h;
  const longPct = longLiq && total ? Math.round((longLiq / total) * 100) : null;
  const intensity = total >= 100e6 ? "HIGH" : total >= 10e6 ? "MED" : "LOW";
  const intColor = intensity === "HIGH" ? "#f87171" : intensity === "MED" ? "#fbbf24" : T.text4;

  if (longPct != null && longPct >= 70) {
    return { icon: "🔴", label: "LONGS FLUSHED",   sub: `${fmt(total)} · ${longPct}% long liq`,      color: "#34d399", info: BADGE_INFO.liq };
  }
  if (longPct != null && longPct <= 30) {
    return { icon: "🟢", label: "SHORTS SQUEEZED", sub: `${fmt(total)} · ${100-longPct}% short liq`, color: "#f87171", info: BADGE_INFO.liq };
  }
  return { icon: "⚖️", label: `${intensity} LIQ`, sub: `${fmt(total)} 24h`, color: intColor, info: BADGE_INFO.liq };
}

// ─── Numbers strip ────────────────────────────────────────────────────────────

const STAT_INFO = {
  "RATE /8H": "Funding rate per 8-hour settlement window. Positive = longs pay shorts (bullish crowding). Above 0.01% = crowded longs (caution). Negative = shorts pay longs (bearish crowding).",
  "OPEN INT": "Total USD value of all open perpetual futures positions. Rising OI alongside price confirms a real move. Falling OI during a rally suggests a short squeeze.",
  "LSR":      "Long/Short Ratio — ratio of accounts holding long vs short positions. >1 = more longs. >1.3 = crowded long (increases liquidation risk). <0.8 = crowded short (squeeze potential).",
  "LIQ 24H":  "Total USD value of liquidated futures positions in the last 24 hours. High liquidations indicate forced deleveraging.",
  "LIQ 4H":   "Liquidations in the last 4 hours — a more recent read on deleveraging pressure. Spike here = active flush in progress.",
  "LIQ 1H":   "Liquidations in the last 1 hour — real-time stress indicator. Elevated 1H liq relative to 4H suggests an active cascade.",
  "VOL 24H":  "Total 24-hour trading volume (spot + futures combined). High volume during a breakout adds conviction. Low volume = weak move.",
  "LEV RISK": "Composite leverage risk score based on OI/volume ratio and funding extremes. HIGH = market is over-leveraged, sharp moves likely. LOW = clean positioning.",
};

function Stat({ label, value, color }) {
  const infoText = STAT_INFO[label];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
        <span style={{ fontSize: 9, color: T.text4, fontFamily: T.font, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", whiteSpace: "nowrap" }}>{label}</span>
        {infoText && <InfoTip text={infoText} />}
      </div>
      <span style={{ fontSize: 12, color: color || T.text2, fontFamily: T.mono, fontWeight: 700, whiteSpace: "nowrap" }}>{value}</span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function PositioningPanel({ positioning, cvdTrend, cvdDiv, bsr }) {
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
      background: T.surface,
      border: `1px solid ${T.border}`,
      borderRadius: T.radiusSm,
      padding: "14px",
      marginBottom: 12,
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)",
    }}>
      {/* Header */}
      <div style={{
        fontSize: 10, color: T.text4, letterSpacing: "0.12em",
        fontFamily: T.font, fontWeight: 700, marginBottom: 10,
        textTransform: "uppercase", display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span>MARKET STRUCTURE</span>
        {source && (
          <span style={{ fontSize: 9, color: T.text4, fontFamily: T.mono, fontWeight: 500, letterSpacing: "0.04em" }}>
            {source.slice(0, 3).toUpperCase()}
          </span>
        )}
      </div>

      {/* Badge grid — 2 columns × 3 rows */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
        <Badge {...b1} />
        <Badge {...b2} />
        <Badge {...b3} />
        <Badge {...b4} />
        <Badge {...b5} />
        <Badge {...b6} />
      </div>

      {/* Numbers strip */}
      {stats.length > 0 && (
        <div style={{
          display: "flex", flexWrap: "wrap", gap: "8px 16px",
          paddingTop: 10, borderTop: `1px solid ${T.border}`,
        }}>
          {stats.map(s => <Stat key={s.label} {...s} />)}
        </div>
      )}
    </div>
  );
}
