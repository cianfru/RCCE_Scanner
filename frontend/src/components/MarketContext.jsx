import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";
import FearGreedGauge from "./FearGreedGauge.jsx";
import StablecoinWidget from "./StablecoinWidget.jsx";

export default function MarketContext({ globalMetrics, altSeason, sentiment, stablecoin, isMobile }) {
  if (!globalMetrics?.btc_dominance && !altSeason && !sentiment && !stablecoin) return null;

  return (
    <FadeIn delay={380}>
      <div style={{
        display: "flex", gap: isMobile ? 8 : 10,
        marginTop: isMobile ? 10 : 12,
        flexWrap: "wrap",
        alignItems: "center",
      }}>
        {/* Fear & Greed Gauge */}
        {sentiment?.fear_greed_value != null && (
          <GlassCard style={{
            padding: "4px 8px",
            display: "flex", alignItems: "center",
            flex: isMobile ? "1 1 calc(50% - 4px)" : undefined,
            justifyContent: "center",
          }}>
            <FearGreedGauge value={sentiment.fear_greed_value} label={sentiment.fear_greed_label || "Fear & Greed"} />
          </GlassCard>
        )}

        {/* BTC Dominance */}
        {globalMetrics?.btc_dominance > 0 && (
          <GlassCard style={{
            padding: isMobile ? "8px 14px" : "10px 16px",
            display: "flex", alignItems: "center", gap: 10,
            flex: isMobile ? "1 1 calc(50% - 4px)" : undefined,
          }}>
            <span style={{ fontSize: 10, color: T.text3, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 600, textTransform: "uppercase" }}>
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

        {/* Alt Season */}
        {altSeason && (
          <GlassCard style={{
            padding: isMobile ? "8px 14px" : "10px 16px",
            display: "flex", alignItems: "center", gap: 10,
            flex: isMobile ? "1 1 calc(50% - 4px)" : undefined,
            border: `1px solid ${altSeason.label === "HOT" ? "#f8717120" : altSeason.label === "ACTIVE" ? "#34d39920" : T.border}`,
          }}>
            <span style={{ fontSize: 10, color: T.text3, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 600, textTransform: "uppercase" }}>
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

        {/* Stablecoin Widget */}
        {stablecoin && (
          <div style={{ flex: isMobile ? "1 1 calc(50% - 4px)" : undefined }}>
            <StablecoinWidget
              trend={stablecoin.trend}
              changePct={stablecoin.change_7d_pct}
              totalCap={stablecoin.total_cap}
            />
          </div>
        )}
      </div>
    </FadeIn>
  );
}
