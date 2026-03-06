import { T } from "../theme.js";

function fundingColor(rate) {
  if (rate == null) return T.text4;
  if (rate < 0) return "#34d399";       // Negative = bullish (shorts paying longs)
  if (rate > 0.01) return "#f87171";    // High positive = bearish
  if (rate > 0.005) return "#fbbf24";   // Elevated
  return T.text2;                        // Normal
}

function oiTrendMeta(trend) {
  switch (trend) {
    case "BUILDING":
      return { color: "#34d399", arrow: "\u2191", label: "BUILDING" };
    case "SQUEEZE":
      return { color: "#fbbf24", arrow: "\u26a1", label: "SQUEEZE" };
    case "LIQUIDATING":
      return { color: "#f87171", arrow: "\u2193\u2193", label: "LIQUIDATING" };
    case "SHORTING":
      return { color: "#c084fc", arrow: "\u2193", label: "SHORTING" };
    default:
      return { color: T.text4, arrow: "\u2014", label: trend || "\u2014" };
  }
}

function leverageColor(risk) {
  switch (risk) {
    case "HIGH":   return "#f87171";
    case "MEDIUM": return "#fbbf24";
    case "LOW":    return "#34d399";
    default:       return T.text4;
  }
}

function fundingRegimeColor(regime) {
  switch (regime) {
    case "NEGATIVE":  return "#34d399";
    case "NEUTRAL":   return T.text3;
    case "ELEVATED":  return "#fbbf24";
    case "EXTREME":   return "#f87171";
    default:          return T.text4;
  }
}

function formatVolume(vol) {
  if (vol == null) return "\u2014";
  if (vol >= 1e9) return `$${(vol / 1e9).toFixed(2)}B`;
  if (vol >= 1e6) return `$${(vol / 1e6).toFixed(1)}M`;
  if (vol >= 1e3) return `$${(vol / 1e3).toFixed(0)}K`;
  return `$${vol.toFixed(0)}`;
}

export default function PositioningPanel({ positioning }) {
  if (!positioning) return null;

  const {
    funding_regime,
    funding_rate,
    oi_trend,
    oi_value,
    leverage_risk,
    predicted_funding,
    volume_24h,
  } = positioning;

  const oiMeta = oiTrendMeta(oi_trend);

  const rows = [
    {
      label: "Funding Rate",
      value: (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            fontFamily: T.mono,
            fontSize: 12,
            fontWeight: 600,
            color: fundingColor(funding_rate),
          }}>
            {funding_rate != null ? `${(funding_rate * 100).toFixed(4)}%` : "\u2014"}
          </span>
          {funding_regime && (
            <span style={{
              padding: "2px 7px",
              borderRadius: "20px",
              background: `${fundingRegimeColor(funding_regime)}10`,
              color: fundingRegimeColor(funding_regime),
              fontSize: 8,
              fontFamily: T.mono,
              fontWeight: 600,
              letterSpacing: "0.04em",
              border: `1px solid ${fundingRegimeColor(funding_regime)}15`,
            }}>
              {funding_regime}
            </span>
          )}
        </div>
      ),
    },
    {
      label: "OI Trend",
      value: (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            padding: "2px 8px",
            borderRadius: "20px",
            background: `${oiMeta.color}10`,
            color: oiMeta.color,
            fontSize: 9,
            fontFamily: T.mono,
            fontWeight: 600,
            letterSpacing: "0.04em",
            border: `1px solid ${oiMeta.color}15`,
            display: "inline-flex",
            alignItems: "center",
            gap: 3,
          }}>
            <span style={{ fontSize: 9 }}>{oiMeta.arrow}</span>
            {oiMeta.label}
          </span>
          {oi_value != null && (
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text3 }}>
              {formatVolume(oi_value)}
            </span>
          )}
        </div>
      ),
    },
    {
      label: "Leverage Risk",
      value: (
        <span style={{
          padding: "2px 8px",
          borderRadius: "20px",
          background: `${leverageColor(leverage_risk)}10`,
          color: leverageColor(leverage_risk),
          fontSize: 9,
          fontFamily: T.mono,
          fontWeight: 600,
          letterSpacing: "0.04em",
          border: `1px solid ${leverageColor(leverage_risk)}15`,
        }}>
          {leverage_risk || "\u2014"}
        </span>
      ),
    },
    {
      label: "Pred. Funding",
      value: (
        <span style={{
          fontFamily: T.mono,
          fontSize: 11,
          fontWeight: 500,
          color: fundingColor(predicted_funding),
        }}>
          {predicted_funding != null ? `${(predicted_funding * 100).toFixed(4)}%` : "\u2014"}
        </span>
      ),
    },
  ];

  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      borderRadius: T.radiusSm,
      padding: "12px",
      marginBottom: 12,
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)",
    }}>
      <div style={{
        fontSize: 8,
        color: T.text4,
        letterSpacing: "0.12em",
        fontFamily: T.font,
        fontWeight: 600,
        marginBottom: 10,
        textTransform: "uppercase",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}>
        <span>Positioning</span>
        {volume_24h != null && (
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.text3, fontWeight: 500, letterSpacing: "0.02em" }}>
            Vol {formatVolume(volume_24h)}
          </span>
        )}
      </div>
      {rows.map((row, i) => (
        <div key={row.label} style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "7px 0",
          borderTop: i > 0 ? `1px solid ${T.border}` : "none",
        }}>
          <span style={{
            fontSize: 9,
            color: T.text4,
            fontFamily: T.font,
            fontWeight: 500,
            letterSpacing: "0.04em",
          }}>
            {row.label}
          </span>
          {row.value}
        </div>
      ))}
    </div>
  );
}
