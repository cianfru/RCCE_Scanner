// Shared badge components for on-chain views
import { T } from "../../theme.js";
import { S, CHAIN_META, ALERT_COLORS, ACTIVITY_COLORS, ADDRESS_TYPE_COLORS } from "./styles.js";
import { truncAddr } from "./helpers.js";

export function ChainBadge({ chain, small }) {
  const meta = CHAIN_META[chain] || { label: chain?.toUpperCase(), color: T.text4 };
  const style = small
    ? { ...S.chip(meta.color), padding: "2px 6px", fontSize: 8 }
    : S.chip(meta.color);
  return <span style={style}>{meta.label}</span>;
}

export function DirectionBadge({ direction }) {
  const color =
    direction === "BUY" ? "#34d399" : direction === "SELL" ? "#f87171" : T.text4;
  return (
    <span style={{ ...S.chip(color), minWidth: 36, justifyContent: "center" }}>
      {direction}
    </span>
  );
}

export function AlertTypeBadge({ type }) {
  const color = ALERT_COLORS[type] || T.text4;
  const label = type?.replace("_", " ") || "UNKNOWN";
  return <span style={S.chip(color)}>{label}</span>;
}

export function ActivityBadge({ activity }) {
  const color = ACTIVITY_COLORS[activity] || T.text4;
  const label = activity || "UNKNOWN";
  return (
    <span style={{ ...S.chip(color), fontSize: 8, padding: "2px 8px" }}>
      {label}
    </span>
  );
}

export function AddressTypeBadge({ type }) {
  if (!type || type === "WALLET") return null;
  const color = ADDRESS_TYPE_COLORS[type] || T.text4;
  return (
    <span
      style={{
        ...S.chip(color),
        fontSize: 7,
        padding: "1px 5px",
        lineHeight: "1.2",
      }}
    >
      {type}
    </span>
  );
}

export function ClickableAddr({ addr, label, onClick, chain }) {
  return (
    <span
      title={addr}
      onClick={(e) => {
        e.stopPropagation();
        if (onClick) onClick(chain, addr);
      }}
      style={{
        color: label ? T.accent : T.text2,
        cursor: onClick ? "pointer" : "default",
        borderBottom: onClick ? `1px dashed ${T.overlay15}` : "none",
        transition: "color 0.15s",
      }}
      onMouseEnter={(e) => onClick && (e.target.style.color = T.accent)}
      onMouseLeave={(e) =>
        onClick && (e.target.style.color = label ? T.accent : T.text2)
      }
    >
      {label || truncAddr(addr)}
    </span>
  );
}
