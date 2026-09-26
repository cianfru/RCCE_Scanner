import FlowToxicity from "./FlowToxicity.jsx";
import HelpTip from "./HelpTip.jsx";
import PanelHeader from "./PanelHeader.jsx";
/**
 * PositioningPanel — Signal-forward market structure display.
 *
 * Layout:
 *   Row 1  (badges):  FUNDING REGIME | OI TREND
 *   Row 2  (badges):  CVD SIGNAL     | SPOT DOMINANCE
 *   Row 3  (badges):  TOP-TRADER L/S | LIQ INTENSITY
 *   ─────────────────────────────────────────
 *   Numbers strip:    Liquidations · Volume · Leverage risk  (values the badges do not show)
 *
 * Props:
 *   positioning — PositioningResponse (Binance/HL native data + CoinGlass enrich)
 *   hasCoinglass — bool; without it the CoinGlass fields hold placeholders and read "Unavailable"
 *   cvdTrend    — "BULLISH" | "BEARISH" | "NEUTRAL"
 *   cvdDiv      — bool
 *   bsr         — number (buy/sell ratio)
 *   vpin        — number 0..1 (volume-synchronized probability of informed trading)
 *   oiContext   — string (contextual OI interpretation from backend, e.g. "confirms entry")
 */
import { T } from "../theme.js";
import { funding8hPct } from "../utils/marketPresentation.js";

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
        <span style={{ fontSize: 12, color: T.text4, fontFamily: T.font, fontWeight: 600, textTransform: "none", letterSpacing: "0.02em" }}>{"\u2014"}</span>
      </div>
    );
  }
  const c = color || T.text2;
  return (
    <div style={{
      // Flat: the reading's colour is carried by the text alone.
      flex: "1 1 48%", padding: "10px 12px", borderRadius: 10,
      background: T.overlay02,
      border: `1px solid ${T.border}`,
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
        {info && <HelpTip title={info.title} width={220}>{info.text}</HelpTip>}
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
          fontSize: 12, color: contextColor || T.text4, fontFamily: T.mono,
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
    text: "Perpetual funding rate from Hyperliquid (Binance for markets listed there), shown per 8 hours. Positive = longs pay shorts (crowded longs). Negative = shorts pay longs (crowded shorts). LONGS CROWDED fails the Funding OK entry check.",
  },
  oi: {
    title: "Open Interest Trend",
    text: "Direction of perpetual open interest. The value comes from Hyperliquid (Binance for markets listed there); the 4h change comes from CoinGlass when it covers this market, otherwise from the change between scans. BUILDING = new money entering with price (confirmed move). SQUEEZE = OI falling as price rises (shorts closing, not new longs). LIQUIDATING = OI falling with price (long cascade). SHORTING = OI rising as price falls (aggressive shorts opening).",
  },
  cvd: {
    title: "Cumulative Volume Delta",
    text: "Net taker buying minus selling, from CoinGlass futures data when it covers this market, otherwise from exchange trades. TAKERS BUYING = aggressive buyers initiating trades. DIV = CVD diverges from price (potential reversal). CVD can upgrade ACCUMULATE \u2192 LIGHT_LONG or downgrade STRONG_LONG \u2192 TRIM.",
  },
  spot: {
    title: "Spot Dominance",
    text: "Ratio of spot volume vs futures volume (CoinGlass). SPOT-LED = organic demand driving price (higher quality move). FUTURES-LED = leverage-driven rally (lower quality, more fragile). SPOT_LED combined with bullish CVD can trigger signal upgrade.",
  },
  topTrader: {
    title: "Top-trader long/short ratio",
    text: "Long/Short Ratio split by account tier (CoinGlass). 'Pro' = top-tier trader accounts. 'Retail' = overall market LSR. Wired into signal decisions: Pro LSR < 0.7 downgrades STRONG_LONG \u2192 LIGHT_LONG. Pro LSR < 0.8 adds caution warning. Pro LSR > 1.5 reinforces entry signals.",
  },
  liq: {
    title: "Liquidation Intensity",
    text: "Total liquidated positions in 24h (CoinGlass). LONGS FLUSHED (\u226570% long liquidations) often marks capitulation \u2014 a contrarian buy signal. SHORTS SQUEEZED (\u226570% short liquidations) may mark a local top. HIGH LIQ without directional skew = general deleveraging.",
  },
};

// Muted placeholder for a reading the data does not have: never shown as a value.
function unavailableBadge(label, info, detail) {
  return { icon: null, label, sub: detail ? `Unavailable \u00b7 ${detail}` : "Unavailable", color: T.text4, info, unavailable: true };
}

function fundingBadge(regime, rate) {
  const pct8h = funding8hPct(rate);
  const rateStr = pct8h != null ? `${pct8h.toFixed(4)}% per 8h` : null;
  switch (regime) {
    case "CROWDED_LONG":
      return { icon: "\u2191", label: "LONGS CROWDED", sub: rateStr, color: "#f87171", info: BADGE_INFO.funding };
    case "CROWDED_SHORT":
      return { icon: "\u2193", label: "SHORTS CROWDED", sub: rateStr, color: "#34d399", info: BADGE_INFO.funding };
    default: {
      if (pct8h == null) return { icon: null, label: "FUNDING", sub: "\u2014", color: T.text4, info: BADGE_INFO.funding };
      // Thresholds in percent per 8h: above 0.01% crowded, above 0.005% warming.
      const c = pct8h < 0 ? "#34d399" : pct8h > 0.01 ? "#f87171" : pct8h > 0.005 ? "#fbbf24" : T.text3;
      return { icon: pct8h < 0 ? "\u2193" : "\u2191", label: "FUNDING OK", sub: rateStr, color: c, info: BADGE_INFO.funding };
    }
  }
}

function oiBadge(trend, oiValue, oiChangePct, available = true) {
  if (!available || trend === "UNKNOWN") return unavailableBadge("OI TREND", BADGE_INFO.oi, oiValue ? `${fmt(oiValue)} open` : null);
  const sub = oiValue ? `${fmt(oiValue)}${oiChangePct ? ` \u00b7 ${oiChangePct >= 0 ? "+" : ""}${oiChangePct.toFixed(1)}%` : ""}` : null;
  switch (trend) {
    case "BUILDING":    return { icon: "\u2191",  label: "OI BUILDING",    sub, color: "#34d399", info: BADGE_INFO.oi };
    case "SQUEEZE":     return { icon: "\u2195", label: "OI SQUEEZE",     sub, color: "#fbbf24", info: BADGE_INFO.oi };
    case "LIQUIDATING": return { icon: "\u2193\u2193", label: "LIQUIDATING",   sub, color: "#f87171", info: BADGE_INFO.oi };
    case "SHORTING":    return { icon: "\u2193",  label: "SHORTING INTO",  sub, color: "#c084fc", info: BADGE_INFO.oi };
    default:            return { icon: "\u2192",  label: trend || "OI STABLE", sub, color: T.text4, info: BADGE_INFO.oi };
  }
}

function cvdBadge(cvdTrend, cvdDiv, bsr) {
  const divTag = cvdDiv ? " \u00b7 DIV" : "";
  const sub = bsr != null && bsr !== 1 ? `BSR ${bsr.toFixed(3)}x` : null;
  switch (cvdTrend) {
    case "BULLISH": return { icon: "\u25b2", label: `TAKERS BUYING${divTag}`,  sub, color: "#34d399", info: BADGE_INFO.cvd };
    case "BEARISH": return { icon: "\u25bc", label: `TAKERS SELLING${divTag}`, sub, color: "#f87171", info: BADGE_INFO.cvd };
    default:        return { icon: "\u2192", label: "CVD NEUTRAL",             sub, color: T.text4,   info: BADGE_INFO.cvd };
  }
}

function spotBadge(spotDom, spotRatio, available = true) {
  const pct = spotRatio > 0 ? `${(spotRatio * 100).toFixed(0)}% spot vol` : null;
  if (!available) return unavailableBadge("SPOT VS FUTURES", BADGE_INFO.spot);
  switch (spotDom) {
    case "SPOT_LED":    return { icon: null, label: "SPOT-LED",    sub: pct || "organic demand",  color: "#34d399", info: BADGE_INFO.spot };
    case "FUTURES_LED": return { icon: null, label: "FUTURES-LED", sub: pct || "leverage driven", color: "#f87171", info: BADGE_INFO.spot };
    case "UNAVAILABLE": return unavailableBadge("SPOT VS FUTURES", BADGE_INFO.spot);
    default:            return { icon: "\u25ce",  label: "MIXED FLOW",  sub: pct,                      color: T.text4,   info: BADGE_INFO.spot };
  }
}

function topTraderBadge(topLsr, retailLsr, available = true) {
  // 1.0 is the backend's missing-data sentinel, not a balanced reading.
  if (!available || !topLsr || topLsr === 1) return unavailableBadge("TOP-TRADER L/S", BADGE_INFO.topTrader);
  const lsrSub = retailLsr ? `Retail ${retailLsr.toFixed(2)} \u00b7 Pro ${topLsr.toFixed(2)}` : `Pro ${topLsr.toFixed(2)}`;
  if (topLsr > 1.3)  return { icon: "\u2191", label: "TOP LONGS HEAVY",  sub: lsrSub, color: "#fbbf24", info: BADGE_INFO.topTrader };
  if (topLsr < 0.8)  return { icon: "\u2193", label: "TOP SHORTS HEAVY", sub: lsrSub, color: "#c084fc", info: BADGE_INFO.topTrader };
  return { icon: "\u2192", label: "TOP BALANCED", sub: lsrSub, color: T.text3, info: BADGE_INFO.topTrader };
}

function liqBadge(liq24h, longLiq, shortLiq, available = true) {
  if (!available) return unavailableBadge("LIQUIDATIONS", BADGE_INFO.liq);
  if (!liq24h) return { icon: null, label: "NO LIQ DATA", sub: null, color: T.text4, info: BADGE_INFO.liq };
  const total = liq24h;
  const longPct = longLiq && total ? Math.round((longLiq / total) * 100) : null;
  const intensity = total >= 100e6 ? "HIGH" : total >= 10e6 ? "MED" : "LOW";
  const intColor = intensity === "HIGH" ? "#f87171" : intensity === "MED" ? "#fbbf24" : T.text4;

  if (longPct != null && longPct >= 70) {
    return { icon: "\u2193", label: "LONGS FLUSHED",   sub: `${fmt(total)} \u00b7 ${longPct}% long liq`,      color: "#34d399", info: BADGE_INFO.liq };
  }
  if (longPct != null && longPct <= 30) {
    return { icon: "\u2191", label: "SHORTS SQUEEZED", sub: `${fmt(total)} \u00b7 ${100-longPct}% short liq`, color: "#f87171", info: BADGE_INFO.liq };
  }
  return { icon: null, label: `${intensity} LIQ`, sub: `${fmt(total)} 24h`, color: intColor, info: BADGE_INFO.liq };
}

// ─── Stat pill ───────────────────────────────────────────────────────────────

const STAT_INFO = {
  "LIQ 24H":  "Total USD value of liquidated futures positions in the last 24 hours. High liquidations indicate forced deleveraging.",
  "LIQ 4H":   "Liquidations in the last 4 hours \u2014 a more recent read on deleveraging pressure. Spike here = active flush in progress.",
  "LIQ 1H":   "Liquidations in the last 1 hour \u2014 real-time stress indicator. Elevated 1H liq relative to 4H suggests an active cascade.",
  "VOL 24H":  "24-hour perpetual trading volume on Hyperliquid. High volume during a breakout adds conviction. Low volume = weak move.",
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
          fontWeight: 600, textTransform: "none", letterSpacing: "0.02em",
          whiteSpace: "nowrap",
        }}>{label}</span>
        {infoText && <HelpTip width={220}>{infoText}</HelpTip>}
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

export default function PositioningPanel({ positioning, hasCoinglass = false, cvdTrend, cvdDiv, bsr, vpin, oiContext }) {
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
    source, source_map = {},
  } = positioning;

  // ── Badge data ──────────────────────────────────────────────────────────────
  const b1 = fundingBadge(funding_regime, funding_rate);
  const b2 = oiBadge(oi_trend, oi_value, oi_change_pct, hasCoinglass || source_map.oi_trend !== "coinglass");
  if (oiContext && !b2.unavailable) {
    b2.context = oiContext;
    b2.contextColor = OI_CTX_COLOR[oiContext] || T.text4;
  }
  const b3 = cvdBadge(cvdTrend, cvdDiv, bsr);
  const b4 = spotBadge(spot_dominance, spot_futures_ratio, hasCoinglass && source_map.spot === "coinglass");
  const b5 = topTraderBadge(top_trader_lsr, long_short_ratio, hasCoinglass);
  const b6 = liqBadge(liquidation_24h_usd, long_liq_usd, short_liq_usd, hasCoinglass);

  // ── Secondary stats (funding, OI and L/S are already in the badges) ─────────
  const stats = [
    hasCoinglass && liquidation_24h_usd > 0 && { label: "LIQ 24H", value: fmt(liquidation_24h_usd), color: T.text3 },
    hasCoinglass && liquidation_4h_usd > 0 && { label: "LIQ 4H", value: fmt(liquidation_4h_usd), color: T.text3 },
    hasCoinglass && liquidation_1h_usd > 0 && { label: "LIQ 1H", value: fmt(liquidation_1h_usd), color: T.text3 },
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
      <PanelHeader title={<>
        Market structure <HelpTip title="Market structure"><p>Positioning and trading-flow context from available exchange data. Funding describes the cost of holding perpetual positions; open interest measures outstanding exposure; taker flow describes aggressive buying or selling. Read these together with price: none alone confirms direction.</p></HelpTip>
      </>}>
        {source && (
          <span style={{ fontSize: T.textXs, color: T.accent, fontFamily: T.mono, fontWeight: 600 }}>
            {{ binance: "Binance", hyperliquid: "Hyperliquid" }[source] || source}
          </span>
        )}
      </PanelHeader>

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
      <FlowToxicity vpin={vpin} />

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
