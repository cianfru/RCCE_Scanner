import { T } from "../../theme.js";
import { S } from "./styles.js";
import GlassCard from "../GlassCard.jsx";
import { ChainBadge } from "./badges.jsx";
import { truncAddr, fmtUsd } from "./helpers.js";

export default function TrendingView({ trending, onTrack }) {
  if (!trending || trending.length === 0) {
    return (
      <div
        style={{
          padding: "32px 0",
          textAlign: "center",
          color: T.text4,
          fontSize: 12,
          fontFamily: T.mono,
        }}
      >
        No trending tokens detected yet. The system needs tracked tokens and
        whale activity to surface trends.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {trending.map((t, i) => (
        <GlassCard key={`${t.contract}-${i}`} style={{ padding: "10px 14px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <ChainBadge chain={t.chain} />
            <span
              style={{
                fontFamily: T.mono,
                fontSize: 13,
                fontWeight: 700,
                color: T.text1,
              }}
            >
              {t.symbol || truncAddr(t.contract)}
            </span>
            {t.name && (
              <span style={{ fontSize: 10, color: T.text4, fontFamily: T.mono }}>
                {t.name}
              </span>
            )}
            <div
              style={{
                marginLeft: "auto",
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span
                style={{
                  fontSize: 10,
                  color: T.accent,
                  fontFamily: T.mono,
                  fontWeight: 600,
                }}
              >
                {t.whale_tx_count} whales
              </span>
              {t.whale_volume_usd > 0 && (
                <span
                  style={{
                    fontSize: 10,
                    color: "#fbbf24",
                    fontFamily: T.mono,
                    fontWeight: 600,
                  }}
                >
                  {fmtUsd(t.whale_volume_usd)} vol
                </span>
              )}
              <button
                onClick={() => onTrack(t.chain, t.contract)}
                style={{ ...S.btn, padding: "4px 12px", fontSize: 10 }}
              >
                Track
              </button>
            </div>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}
