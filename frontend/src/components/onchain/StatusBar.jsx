import { T } from "../../theme.js";
import { S } from "./styles.js";
import { ChainBadge } from "./badges.jsx";
import { fmtTime } from "./helpers.js";

export default function StatusBar({ status }) {
  if (!status) return null;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        flexWrap: "wrap",
        marginBottom: 12,
        padding: "8px 14px",
        borderRadius: 10,
        background: T.overlay04,
        border: `1px solid ${T.border}`,
      }}
    >
      <span style={S.label}>CHAINS</span>
      {status.active_chains?.length > 0 ? (
        status.active_chains.map((c) => <ChainBadge key={c} chain={c} />)
      ) : (
        <span style={{ fontSize: 10, color: "#fbbf24", fontFamily: T.mono }}>
          No API keys set
        </span>
      )}
      <span style={{ ...S.label, marginLeft: "auto" }}>
        {status.tracked_token_count} tokens {"\u00b7"}{" "}
        {status.transfer_count} txns {"\u00b7"} {status.alert_count} alerts
      </span>
      {status.last_poll && (
        <span style={{ fontSize: 9, color: T.text4, fontFamily: T.mono }}>
          Last: {fmtTime(status.last_poll)}
        </span>
      )}
    </div>
  );
}
