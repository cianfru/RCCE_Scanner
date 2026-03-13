import { T } from "../theme.js";

function formatCap(cap) {
  if (cap == null) return "\u2014";
  if (cap >= 1e12) return `$${(cap / 1e12).toFixed(1)}T`;
  if (cap >= 1e9) return `$${(cap / 1e9).toFixed(1)}B`;
  if (cap >= 1e6) return `$${(cap / 1e6).toFixed(1)}M`;
  return `$${cap.toFixed(0)}`;
}

function trendMeta(trend) {
  switch (trend) {
    case "EXPANDING":
      return { arrow: "\u2191", color: T.green, label: "EXPANDING" };
    case "CONTRACTING":
      return { arrow: "\u2193", color: T.red, label: "CONTRACT" };
    case "STABLE":
    default:
      return { arrow: "\u2192", color: T.gray, label: "STABLE" };
  }
}

export default function StablecoinWidget({ trend, changePct, totalCap }) {
  if (!trend && changePct == null && totalCap == null) return null;

  const meta = trendMeta(trend);

  return (
    <>
      <span style={{
        fontSize: T.textSm,
        color: T.text4,
        letterSpacing: "0.1em",
        fontFamily: T.font,
        fontWeight: 500,
        textTransform: "uppercase",
      }}>
        Stables
      </span>

      {/* Trend arrow + badge */}
      <span style={{
        padding: "2px 10px",
        borderRadius: "20px",
        background: `${meta.color}10`,
        color: meta.color,
        fontSize: T.textXs,
        fontFamily: T.mono,
        fontWeight: 700,
        letterSpacing: "0.06em",
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
      }}>
        <span style={{ fontSize: T.textSm }}>{meta.arrow}</span>
        {meta.label}
      </span>

      {/* Percentage change */}
      {changePct != null && (
        <>
          <div style={{ width: 1, height: 14, background: T.border }} />
          <span style={{
            fontFamily: T.mono,
            fontSize: T.textSm,
            fontWeight: 600,
            color: changePct >= 0 ? T.green : T.red,
          }}>
            {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
          </span>
        </>
      )}

      {/* Total cap */}
      {totalCap != null && (
        <>
          <div style={{ width: 1, height: 14, background: T.border }} />
          <span style={{
            fontFamily: T.mono,
            fontSize: T.textXs,
            color: T.text3,
            fontWeight: 500,
          }}>
            {formatCap(totalCap)}
          </span>
        </>
      )}
    </>
  );
}
