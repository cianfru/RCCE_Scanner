import { T } from "../../theme.js";
import GlassCard from "../GlassCard.jsx";
import { ChainBadge, AlertTypeBadge, ClickableAddr } from "./badges.jsx";
import { fmtUsd, fmtTime } from "./helpers.js";

export default function AlertsView({ alerts, onSelectWallet, onNavigateToken }) {
  if (!alerts || alerts.length === 0) {
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
        No alerts yet. Track tokens to start detecting whale activity.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {alerts.map((a, i) => (
        <GlassCard
          key={`${a.address}-${a.timestamp}-${i}`}
          style={{ padding: "10px 14px", cursor: "pointer" }}
          onClick={() => onNavigateToken && onNavigateToken(a.contract)}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <ChainBadge chain={a.chain} />
            <AlertTypeBadge type={a.alert_type} />
            <span
              style={{
                fontFamily: T.mono,
                fontSize: 12,
                fontWeight: 700,
                color: T.text1,
                cursor: "pointer",
              }}
              onClick={(e) => {
                e.stopPropagation();
                onNavigateToken && onNavigateToken(a.contract);
              }}
            >
              {a.token_symbol}
            </span>
            <ClickableAddr
              addr={a.address}
              label={a.label}
              chain={a.chain}
              onClick={onSelectWallet}
            />
            {a.value_usd > 0 && (
              <span
                style={{
                  fontFamily: T.mono,
                  fontSize: 11,
                  fontWeight: 700,
                  color: "#fbbf24",
                }}
              >
                {fmtUsd(a.value_usd)}
              </span>
            )}
            <span
              style={{
                fontSize: 9,
                color: T.text4,
                fontFamily: T.mono,
                marginLeft: "auto",
              }}
            >
              {fmtTime(a.timestamp)}
            </span>
          </div>
          <div
            style={{
              fontSize: 10,
              color: T.text3,
              fontFamily: T.mono,
              marginTop: 4,
            }}
          >
            {a.details}
          </div>
        </GlassCard>
      ))}
    </div>
  );
}
