import { T, m } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";
import FearGreedGauge from "./FearGreedGauge.jsx";
import StablecoinWidget from "./StablecoinWidget.jsx";

export default function MarketContext({ globalMetrics, altSeason, sentiment, stablecoin, isMobile }) {
  if (!globalMetrics?.btc_dominance && !altSeason && !sentiment && !stablecoin) return null;

  return (
    <FadeIn delay={380}>
      <div style={{
        display: "flex", gap: isMobile ? 8 : 8,
        marginTop: isMobile ? T.sp3 : T.sp2,
        flexWrap: "wrap",
        alignItems: "center",
      }}>
        {/* Fear & Greed */}
        {sentiment?.fear_greed_value != null && (
          <GlassCard style={{
            padding: isMobile ? "10px 14px" : "10px 16px",
            display: "flex", alignItems: "center",
            flex: isMobile ? "1 1 calc(50% - 4px)" : "1 1 auto",
            minWidth: isMobile ? undefined : 200,
          }}>
            <FearGreedGauge value={sentiment.fear_greed_value} />
          </GlassCard>
        )}

        {/* BTC Dominance */}
        {globalMetrics?.btc_dominance > 0 && (
          <GlassCard style={{
            padding: isMobile ? "10px 14px" : "10px 16px",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
            flex: isMobile ? "1 1 calc(50% - 4px)" : undefined,
          }}>
            <span style={{ fontSize: m(11, isMobile), color: T.text3, letterSpacing: "0.08em", fontFamily: T.font, fontWeight: 600, textTransform: "uppercase" }}>
              BTC.D
            </span>
            <span style={{
              fontFamily: T.mono, fontSize: m(13, isMobile), fontWeight: 700,
              color: globalMetrics.btc_dominance > 55 ? T.yellow : globalMetrics.btc_dominance > 45 ? T.text1 : T.green,
            }}>
              {globalMetrics.btc_dominance.toFixed(1)}%
            </span>
            {globalMetrics.eth_dominance > 0 && (
              <>
                <div style={{ width: 1, height: 14, background: T.border }} />
                <span style={{ fontSize: m(11, isMobile), color: T.text4, letterSpacing: "0.08em", fontFamily: T.font, fontWeight: 500 }}>ETH.D</span>
                <span style={{ fontFamily: T.mono, fontSize: m(13, isMobile), fontWeight: 600, color: T.text2 }}>
                  {globalMetrics.eth_dominance.toFixed(1)}%
                </span>
              </>
            )}
          </GlassCard>
        )}

        {/* Alt Season */}
        {altSeason && (
          <GlassCard style={{
            padding: isMobile ? "10px 14px" : "10px 16px",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
            flex: isMobile ? "1 1 calc(50% - 4px)" : undefined,
            border: `1px solid ${altSeason.label === "HOT" ? "#f8717120" : altSeason.label === "ACTIVE" ? "#34d39920" : T.border}`,
          }}>
            <span style={{ fontSize: m(11, isMobile), color: T.text3, letterSpacing: "0.08em", fontFamily: T.font, fontWeight: 600, textTransform: "uppercase" }}>
              Alt Season
            </span>
            <span style={{
              padding: isMobile ? "3px 10px" : "2px 10px", borderRadius: "20px",
              background: altSeason.label === "HOT" ? "rgba(248,113,113,0.1)" :
                         altSeason.label === "ACTIVE" ? "rgba(52,211,153,0.1)" :
                         altSeason.label === "NEUTRAL" ? "rgba(251,191,36,0.1)" : "rgba(82,82,91,0.1)",
              color: altSeason.label === "HOT" ? "#f87171" :
                     altSeason.label === "ACTIVE" ? "#34d399" :
                     altSeason.label === "NEUTRAL" ? "#fbbf24" :
                     altSeason.label === "WEAK" ? "#fb923c" : T.text4,
              fontSize: m(11, isMobile), fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
            }}>
              {altSeason.label}
            </span>
            <span style={{ fontFamily: T.mono, fontSize: m(12, isMobile), color: T.text3, fontWeight: 500 }}>
              {altSeason.score?.toFixed(0)}
            </span>
          </GlassCard>
        )}

        {/* Stablecoin Widget */}
        {stablecoin && (
          <GlassCard style={{
            padding: isMobile ? "10px 14px" : "10px 16px",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            flex: isMobile ? "1 1 calc(50% - 4px)" : undefined,
          }}>
            <StablecoinWidget
              trend={stablecoin.trend}
              changePct={stablecoin.change_7d_pct}
              totalCap={stablecoin.total_cap}
            />
          </GlassCard>
        )}
      </div>
    </FadeIn>
  );
}
